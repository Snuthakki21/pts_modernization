"""Bounded Python symbol lookup; optional local Graphify API, no agent runtime."""
from __future__ import annotations

import argparse
import ast
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

GRAPHIFY_VERSION = "0.9.91"
MAX_FILE_BYTES = 1024 * 1024


def approved_file(root: Path, name: str) -> Path:
    """Limit this adapter to public examples/tools and converted target Python."""
    relative = Path(name)
    parts = relative.parts
    if (len(name) > 512 or relative.is_absolute() or ".." in parts or not parts
            or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts)):
        raise ValueError("Use a relative repository Python path without traversal")
    allowed = parts[0] in {"examples", "tools"} or (
        len(parts) >= 4 and parts[0] == "programs" and parts[2] == "target")
    if not allowed or relative.suffix != ".py" or any(
        part.lower() in {"private", "source", "sources"} or part.startswith(".")
        for part in parts
    ):
        raise ValueError("Lookup is limited to examples/, tools/, or programs/<id>/target/ Python")
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Symlink inputs are not accepted")
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Input must be an existing file inside the repository")
    if path.stat().st_nlink != 1 or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Input must be singly linked and no larger than 1 MiB")
    return path


def no_external_calls(event: str, args: tuple) -> None:
    """Defense in depth for Python calls; not an OS sandbox for native code."""
    if event.startswith(("socket.", "subprocess.")) or event in {
        "os.system", "os.exec", "os.posix_spawn", "os.fork", "os.spawn"
    }:
        raise RuntimeError("Network and child processes are disabled for this lookup")


def read_source(root: Path, name: str) -> bytes:
    """Open each path component without following links, then read bounded bytes."""
    approved_file(root, name)
    if os.open not in os.supports_dir_fd or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("This adapter requires no-follow directory opens; use Linux/WSL or macOS")
    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory = os.open(root, dir_flags)
    try:
        for part in Path(name).parts[:-1]:
            child = os.open(part, dir_flags, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(Path(name).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_FILE_BYTES:
                raise ValueError("Input must be a bounded, singly linked regular file")
            data = stream.read(MAX_FILE_BYTES + 1)
            after = os.fstat(stream.fileno())
            if (len(data) > MAX_FILE_BYTES or
                    (before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                raise ValueError("Source changed during capture; use a stable source version")
            return data
    finally:
        os.close(directory)


def extract_snapshot(data: bytes, root: Path, filename: str, extractor) -> dict:
    """The parser and advertised hash consume the same privately captured bytes."""
    with tempfile.TemporaryDirectory(prefix=".graphify-lookup-", dir=root) as directory:
        snapshot = Path(directory) / filename
        snapshot.write_bytes(data)
        snapshot.chmod(0o400)
        return extractor(snapshot, root=Path(directory))


def select(graph: dict, symbol: str, limit: int = 12) -> dict:
    if graph.get("error"):
        raise ValueError("Graphify could not parse the input; use the original source")
    matches = [node for node in graph.get("nodes", [])
               if node.get("file_type") == "code"
               and symbol.casefold() in node.get("label", "").casefold()]
    ids = {node["id"] for node in matches}
    names = {node["id"]: node.get("label", node["id"]) for node in graph.get("nodes", [])}
    calls = [edge for edge in graph.get("edges", []) if edge.get("relation") == "calls"
             and (edge.get("source") in ids or edge.get("target") in ids)]
    clipped = False

    def bounded(value: str | None) -> str | None:
        nonlocal clipped
        if value is not None and len(value) > 160:
            clipped = True
            return value[:157] + "..."
        return value

    symbols = [{"name": bounded(n["label"]), "line": bounded(n.get("source_location"))}
               for n in matches[:limit]]
    selected_calls = [{"from": bounded(names.get(e["source"], e["source"])),
                       "to": bounded(names.get(e["target"], e["target"])),
                       "line": bounded(e.get("source_location"))} for e in calls[:limit]]
    return {
        "match_count": len(matches), "call_count": len(calls),
        "truncated": clipped or len(matches) > limit or len(calls) > limit,
        "symbols": symbols, "calls": selected_calls,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="Explicit approved relative Python path")
    parser.add_argument("--symbol", required=True, help="Symbol name fragment, not source contents")
    args = parser.parse_args()
    try:
        if not 1 <= len(args.symbol) <= 100 or not re.fullmatch(r"[A-Za-z0-9_ .()-]+", args.symbol):
            raise ValueError("Supply a symbol fragment of 1–100 simple characters")
        root = Path(__file__).resolve().parents[1]
        path = approved_file(root, args.file)
        data = read_source(root, args.file)
        ast.parse(data, filename=args.file)
        if version("graphifyy") != GRAPHIFY_VERSION:
            raise ValueError("Install the pinned Graphify environment from docs/TOKEN_EFFICIENCY.md")
        # Do not invoke graphify.__main__: its CLI can refresh unrelated skills.
        sys.addaudithook(no_external_calls)
        from graphify.extract import extract_python
        result = select(extract_snapshot(data, root, path.name, extract_python), args.symbol)
        result.update({"source": args.file, "sha256": hashlib.sha256(data).hexdigest(),
                       "graphify_version": GRAPHIFY_VERSION,
                       "limits": "navigation only; per-file static calls; no completeness or behavior proof"})
        print(json.dumps(result, separators=(",", ":"), ensure_ascii=True))
        return 0
    except (ValueError, OSError, SyntaxError, PackageNotFoundError, ImportError, RuntimeError) as exc:
        print(json.dumps({"status": "blocked", "reason": type(exc).__name__,
                          "action": "Check approved input and pinned optional runtime; no acceptance evidence produced"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
