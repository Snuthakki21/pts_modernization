"""Build and traverse an OKF projection of explicitly approved Endevor views."""
from __future__ import annotations

import argparse
import bisect
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid

VERSION = "1.0"
MAX_BYTES = 1024 * 1024
MAX_FILES = 2000
MAX_REFERENCES = 10000
MAX_QUERY_REFERENCES = 200
KINDS = {"cobol", "copybook", "jcl", "proc", "sql", "control", "other"}
OUTPUT = ("knowledge", "endevor")
TOKEN = re.compile(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|/\*[\s\S]*?(?:\*/|$)|[A-Za-z0-9_@$#&.-]+|[=(),*]")


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _json(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n").encode()


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _parse(data):
    return json.loads(data, object_pairs_hook=_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite JSON")))


def _root(root):
    root = Path(root).absolute()
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise ValueError("Use a platform supporting no-follow directory opens")
    for part in (root, *root.parents):
        if part.is_symlink():
            raise ValueError("Symlink roots are not accepted")
    if not root.is_dir():
        raise ValueError("Repository root is missing")
    return root


def _parts(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 512:
        raise ValueError("Invalid relative path")
    parts = value.split("/")
    if any(not re.fullmatch(r"[A-Za-z0-9_@$#][A-Za-z0-9_@$#. -]*", p)
           or p.endswith((".", " ")) or p.lower() in {"private", "source", "sources", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "credentials"}
           or p.lower().endswith((".private.json", ".private-rows.json", ".key", ".pem", ".cert", ".db", ".sqlite", ".json"))
           for p in parts):
        raise ValueError("Unsafe relative path")
    return tuple(parts)


def _directory(root, parts, create=False):
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read(root, parts, limit=MAX_BYTES):
    directory = _directory(root, parts[:-1])
    try:
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
                raise ValueError("Expected a bounded singly linked regular file")
            data = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            if len(data) > limit or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError("File changed during capture")
            return data
    finally:
        os.close(directory)


def _write(root, parts, data, replace=False):
    directory = _directory(root, parts[:-1], create=True)
    temporary = ".nav-" + uuid.uuid4().hex
    try:
        try:
            old = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            old = None
        if old is not None and (not stat.S_ISREG(old.st_mode) or old.st_nlink != 1):
            raise ValueError("Unsafe output file")
        if old is not None and not replace:
            if _read(root, parts, max(MAX_BYTES, len(data))) != data:
                raise ValueError("Existing generated artifact differs")
            return
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, parts[-1], src_dir_fd=directory, dst_dir_fd=directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        os.close(directory)


def _nonempty(value):
    return isinstance(value, str) and 0 < len(value.strip()) <= 2000 and not any(ord(c) < 32 for c in value)


def _inputs(root):
    manifest_bytes = _read(root, ("Endevor", "navigation.json"))
    manifest = _parse(manifest_bytes)
    if (not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int
            or manifest["schema_version"] != 1 or not _nonempty(manifest.get("approved_source_reference"))
            or not isinstance(manifest.get("files"), list) or not 1 <= len(manifest["files"]) <= MAX_FILES):
        raise ValueError("Expected an explicit approved-view manifest with files")
    records, seen, total = [], set(), 0
    for item in manifest["files"]:
        if not isinstance(item, dict):
            raise ValueError("Invalid file entry")
        parts = _parts(item.get("path"))
        path = "/".join(parts)
        if path.casefold() in seen or path.casefold() == "navigation.json":
            raise ValueError("Duplicate or case-colliding source path")
        seen.add(path.casefold())
        kind = item.get("kind")
        encoding = item.get("encoding")
        identity = item.get("source_identity") or item.get("source_reference")
        if kind not in KINDS or encoding not in {"utf-8", "cp037", "cp1047"} or not _nonempty(identity):
            raise ValueError("File needs kind, supported explicit encoding and qualified source identity")
        if kind in {"cobol", "copybook"} and item.get("format") not in {"fixed", "free"}:
            raise ValueError("COBOL and copybook views require fixed or free format")
        if "original_sha256" in item and not re.fullmatch(r"[0-9a-f]{64}", str(item["original_sha256"])):
            raise ValueError("Invalid original source digest")
        data = _read(root, ("Endevor", *parts))
        total += len(data)
        if total > 64 * MAX_BYTES:
            raise ValueError("Approved view set exceeds bounded capture size")
        try:
            text = data.decode(encoding, errors="strict")
        except (UnicodeError, LookupError) as exc:
            raise ValueError("Unsupported codec or invalid source encoding") from exc
        if "\0" in text:
            raise ValueError("Binary source is unsupported")
        records.append({"id": "file-" + _digest(path.encode())[:20], "path": path,
                        "kind": kind, "encoding": encoding, "format": item.get("format"),
                        "source_identity": identity, "sha256": _digest(data),
                        "original_sha256": item.get("original_sha256"), "text": text})
    return manifest, _digest(manifest_bytes), sorted(records, key=lambda r: r["path"])


def _without_comment(line, sql=False):
    quote, i = None, 0
    while i < len(line):
        c = line[i]
        if quote:
            if c == quote:
                if i + 1 < len(line) and line[i + 1] == quote:
                    i += 2
                    continue
                quote = None
        elif c in "'\"":
            quote = c
        elif line[i:i + 2] == "*>" or (sql and line[i:i + 2] == "--"):
            return line[:i]
        i += 1
    return line


def _tokens(text):
    newlines = [m.start() for m in re.finditer("\n", text)]
    result = []
    for match in TOKEN.finditer(text):
        raw = match.group()
        if raw.startswith("/*"):
            continue
        quoted = raw.startswith(("'", '"'))
        value = raw[1:-1].replace(raw[0] * 2, raw[0]) if quoted else raw.rstrip(".")
        result.append((value if quoted else value.upper(), quoted, bisect.bisect_left(newlines, match.start()) + 1))
    return result


def _scan(record):
    lines = record["text"].splitlines()
    refs, aliases = [], {Path(record["path"]).stem.upper()}

    def ref(relation, token, kinds, dynamic=False):
        value, quoted, line = token
        oversized = len(value) > 256
        refs.append({"source": record["id"], "relation": relation, "name": value,
                     "line": line, "source_sha256": record["sha256"],
                     "state": "unsupported" if oversized else "dynamic" if dynamic else "pending", "target": None,
                     "target_kinds": kinds})
        if oversized:
            refs[-1]["name"] = "unsupported-long-operand"
            refs[-1]["operand_sha256"] = _digest(value.encode())
        if len(refs) > 1000:
            raise ValueError("Source exceeds bounded reference count")

    if record["kind"] in {"cobol", "copybook", "sql"}:
        cleaned = []
        for number, line in enumerate(lines, 1):
            if record["format"] == "fixed":
                if len(line) > 6 and line[6].upper() in {"-", "D"}:
                    ref("unsupported-syntax", ("fixed-continuation-or-debug", False, number), [])
                    refs[-1]["state"] = "unsupported"
                    if line[6] == "-" and cleaned:
                        cleaned[-1] = ""
                    line = ""
                else:
                    line = "" if len(line) > 6 and line[6] in "*/" else line[7:72]
            cleaned.append(_without_comment(line, sql=True))
        tokens = _tokens("\n".join(cleaned))
        in_sql = False
        for i, token in enumerate(tokens):
            word, quoted, line = token
            if quoted:
                continue
            if word == "EXEC" and i + 1 < len(tokens) and tokens[i + 1][0] == "SQL":
                in_sql = True
            if word == "END-EXEC":
                in_sql = False
            if i + 1 >= len(tokens):
                continue
            following = tokens[i + 1]
            if word == "PROGRAM-ID":
                if len(following[0]) > 256 or len(aliases) >= 100:
                    raise ValueError("Unsupported program identity or alias count")
                aliases.add(following[0])
            elif in_sql and word == "INCLUDE" and i >= 2 and tokens[i - 2][0] == "EXEC" and tokens[i - 1][0] == "SQL":
                ref("sql-include", following, ["copybook", "sql"])
            elif not in_sql and word == "COPY":
                ref("copy", following, ["copybook"])
                if i + 2 < len(tokens) and tokens[i + 2][0] in {"IN", "OF"}:
                    refs[-1]["state"] = "qualified"
            elif not in_sql and word == "CALL":
                ref("call", following, ["cobol"], dynamic=not following[1])
    elif record["kind"] in {"jcl", "proc"}:
        instream = None
        for number, line in enumerate(lines, 1):
            if instream:
                delimiter, star = instream
                if line.strip() == delimiter:
                    instream = None
                    continue
                if star and line.startswith("//"):
                    instream = None
                else:
                    continue
            if not line.startswith("//") or line.startswith("//*"):
                continue
            statement = re.match(r"^//(\S*)\s+([A-Za-z]+)(?:\s+(.*))?$", line[:72])
            if not statement:
                if line[2:].strip():
                    ref("unsupported-syntax", ("jcl-continuation-or-statement", False, number), [])
                    refs[-1]["state"] = "unsupported"
                continue
            operation = statement[2].upper()
            arguments = statement[3] or ""
            # A blank outside a quoted value starts the JCL comment field.
            quote, end = None, len(arguments)
            i = 0
            while i < len(arguments):
                char = arguments[i]
                if quote:
                    if char == quote:
                        if i + 1 < len(arguments) and arguments[i + 1] == quote:
                            i += 2
                            continue
                        quote = None
                elif char in "'\"":
                    quote = char
                elif char.isspace():
                    end = i
                    break
                i += 1
            tokens = [(v, q, number) for v, q, _ in _tokens(arguments[:end])]
            if operation == "DD" and tokens and tokens[0][0] in {"DATA", "*"}:
                delimiter, star = "/*", tokens[0][0] == "*"
                for i, token in enumerate(tokens):
                    if token[0] == "DLM" and i + 2 < len(tokens) and tokens[i + 1][0] == "=":
                        delimiter, star = tokens[i + 2][0], False
                instream = (delimiter, star)
                ref("unsupported-syntax", ("in-stream-data-not-analyzed", False, number), [])
                refs[-1]["state"] = "unsupported"
            elif operation == "EXEC":
                if tokens and tokens[0][0] in {"PGM", "PROC"} and len(tokens) >= 3 and tokens[1][0] == "=":
                    operand = tokens[2]
                    ref("exec-pgm" if tokens[0][0] == "PGM" else "exec-proc", operand,
                        ["cobol"] if tokens[0][0] == "PGM" else ["proc"], "&" in operand[0])
                elif tokens and tokens[0][0] not in {"PGM", "PROC", "="}:
                    ref("exec-proc", tokens[0], ["proc"], "&" in tokens[0][0])
                else:
                    ref("unsupported-syntax", ("incomplete-exec", False, number), [])
                    refs[-1]["state"] = "unsupported"
            elif operation == "INCLUDE" and len(tokens) >= 3 and tokens[0][0] == "MEMBER" and tokens[1][0] == "=":
                ref("jcl-include", tokens[2], ["jcl", "proc", "control"], "&" in tokens[2][0])
            elif operation == "DD":
                for i, token in enumerate(tokens):
                    if not token[1] and token[0] in {"DSN", "DSNAME"} and i + 2 < len(tokens) and tokens[i + 1][0] == "=":
                        operand = tokens[i + 2]
                        if i + 5 < len(tokens) and tokens[i + 3][0] == "(" and tokens[i + 5][0] == ")":
                            operand = (operand[0] + "(" + tokens[i + 4][0] + ")", operand[1], number)
                        ref("dataset", operand, [], "&" in operand[0])
                        if refs[-1]["state"] == "pending":
                            refs[-1]["state"] = "external"
    if record["kind"] in {"sql", "control", "other"}:
        ref("unsupported-syntax", ("artifact-semantics-not-extracted", False, 1), [])
        refs[-1]["state"] = "unsupported"
    return sorted(a for a in aliases if a), refs


def _graph(manifest, manifest_hash, records):
    nodes, references = [], []
    for record in records:
        aliases, refs = _scan(record)
        nodes.append({k: v for k, v in record.items() if k != "text"} | {"aliases": aliases})
        references.extend(refs)
    if len(references) > MAX_REFERENCES:
        raise ValueError("Approved view set exceeds bounded reference count")
    lookup = {}
    for node in nodes:
        for alias in node["aliases"]:
            lookup.setdefault((node["kind"], alias), []).append(node["id"])
    for ref in references:
        target_kinds = ref.pop("target_kinds")
        candidates = sorted({identity for kind in target_kinds for identity in lookup.get((kind, ref["name"]), [])}) if ref["state"] == "pending" else []
        ref.pop("target_kinds", None)
        if ref["state"] == "pending":
            ref["state"] = "resolved" if len(candidates) == 1 else "ambiguous" if candidates else "missing"
            ref["target"] = candidates[0] if len(candidates) == 1 else None
        ref["candidates"] = candidates[:20]
        ref["candidate_count"] = len(candidates)
        ref["candidates_truncated"] = len(candidates) > 20
    return {"schema_version": 1, "generator": "endevor-nav/" + VERSION,
            "generator_sha256": _tool_sha256(), "input_manifest_sha256": manifest_hash,
            "approved_source_reference": manifest["approved_source_reference"],
            "nodes": nodes, "references": references,
            "limits": "Declared approved views only; conservative static navigation, not completeness, execution or acceptance evidence"}


def _tool_sha256():
    tool = Path(__file__).absolute()
    return _digest(_read(_root(tool.parent), (tool.name,)))


def _frontmatter(values):
    return "---\n" + "\n".join(k + ": " + json.dumps(v, ensure_ascii=True) for k, v in values.items()) + "\n---\n\n"


def _markdown(value):
    return re.sub(r"([\\`*_{}\[\]()<>!|])", r"\\\1", value)


def _bundle(graph, generated_at):
    files = {}
    names = {n["id"]: n["path"] for n in graph["nodes"]}
    root_index = '# Endevor navigation\n\n'
    root_index += "Approved sanitized mainframe views. Navigation does not establish conversion acceptance.\n\n"
    root_index += "- [Files](files/index.md) - Qualified mainframe artifacts and their dependency evidence.\n"
    files["index.md"] = root_index.encode()
    entries = {}
    for node in graph["nodes"]:
        name = node["id"] + ".md"
        entries.setdefault(node["kind"], []).append(f'- [{_markdown(node["path"])}]({name}) - source view {node["sha256"][:12]}.')
        values = {"type": "Mainframe " + node["kind"], "title": node["path"],
                  "description": "Approved source-view dependency navigation", "status": "draft",
                  "generated": {"by": "process:endevor-navigation", "at": generated_at},
                  "sources": [{"id": "approved-view", "resource": "Approved source identity: " + node["source_identity"]},
                              {"id": "source-approval", "resource": graph["approved_source_reference"]}],
                  "source_path": "Endevor/" + node["path"], "source_identity": node["source_identity"],
                  "source_view_sha256": node["sha256"]}
        if node["original_sha256"]:
            values["original_sha256"] = node["original_sha256"]
        body = _frontmatter(values) + "# Source\n\n" + _markdown(node["source_identity"]) + "\n\n"
        body += "Source lines below refer to the approved view, not necessarily original record positions.\n\n# Dependencies\n\n"
        outgoing = [r for r in graph["references"] if r["source"] == node["id"]]
        for ref in outgoing:
            target = f'[{_markdown(names[ref["target"]])}]({ref["target"]}.md)' if ref["target"] else f'{_markdown(ref["name"])} ({ref["state"]})'
            body += f'- {ref["relation"]}: {target}; approved-view line {ref["line"]}; source hash `{ref["source_sha256"]}`.\n'
        if not outgoing:
            body += "No supported static references found; this is not a dependency-completeness claim.\n"
        body += "\n# Dependents\n\n"
        incoming = [r for r in graph["references"] if r["target"] == node["id"]]
        for ref in incoming:
            body += f'- [{_markdown(names[ref["source"]])}]({ref["source"]}.md): {ref["relation"]}, line {ref["line"]}.\n'
        if not incoming:
            body += "No callers resolved within the declared view set.\n"
        files["files/" + name] = body.encode()
    groups = []
    for kind, rows in sorted(entries.items()):
        for page, offset in enumerate(range(0, len(rows), 50), 1):
            name = f"{kind}-{page}.md"
            groups.append(f"- [{kind}, page {page}]({name}) - {len(rows[offset:offset + 50])} source views.")
            files["files/" + name] = (_frontmatter({"type": "Navigation Page", "title": f"{kind}, page {page}", "status": "draft"}) + "# Source views\n\n" + "\n".join(rows[offset:offset + 50]) + "\n").encode()
    files["files/index.md"] = ("# Mainframe files\n\n" + "\n".join(groups) + "\n").encode()
    return files


def _load(root):
    pointer = _parse(_read(root, (*OUTPUT, "current.json")))
    snapshot = pointer.get("snapshot") if isinstance(pointer, dict) else None
    if not isinstance(snapshot, str) or not re.fullmatch(r"[0-9a-f]{64}", snapshot):
        raise ValueError("Invalid navigation snapshot")
    base = (*OUTPUT, "snapshots", snapshot)
    receipt_bytes = _read(root, (*base, "manifest.json"), 64 * MAX_BYTES)
    if _digest(receipt_bytes) != pointer.get("manifest_sha256"):
        raise ValueError("Navigation manifest changed")
    receipt = _parse(receipt_bytes)
    if _digest(_json(receipt["graph"])) != snapshot:
        raise ValueError("Navigation graph changed")
    for name, digest in receipt["artifacts"].items():
        if _digest(_read(root, (*base, *_parts(name)), 64 * MAX_BYTES)) != digest:
            raise ValueError("Navigation artifact changed")
    if _digest(_read(root, (*OUTPUT, "index.md"))) != pointer.get("index_sha256"):
        raise ValueError("Navigation entry point changed")
    return pointer, receipt


def _summary(pointer, graph):
    return {"status": "current", "snapshot": pointer["snapshot"],
            "index": "knowledge/endevor/index.md", "node_count": len(graph["nodes"]),
            "edge_count": sum(r["state"] == "resolved" for r in graph["references"]),
            "unresolved_count": sum(r["state"] != "resolved" for r in graph["references"]),
            "limits": graph["limits"]}


def build(root):
    """Capture the explicit view list and publish a new immutable OKF snapshot."""
    root = _root(root)
    manifest, manifest_hash, records = _inputs(root)
    graph = _graph(manifest, manifest_hash, records)
    snapshot = _digest(_json(graph))
    # Existing published content must still match before replacing its pointer.
    try:
        _load(root)
    except FileNotFoundError:
        for name in ("index.md", "current.json"):
            if (root.joinpath(*OUTPUT) / name).exists():
                raise ValueError("Incomplete existing navigation needs review")
    base = (*OUTPUT, "snapshots", snapshot)
    try:
        receipt_bytes = _read(root, (*base, "manifest.json"), 64 * MAX_BYTES)
        receipt = _parse(receipt_bytes)
        if receipt.get("graph") != graph:
            raise ValueError("Existing snapshot differs")
        files = _bundle(graph, receipt["generated_at"])
    except FileNotFoundError:
        generated_at = datetime.now(timezone.utc).isoformat()
        files = _bundle(graph, generated_at)
        receipt = {"graph": graph, "generated_at": generated_at,
                   "artifacts": {name: _digest(data) for name, data in files.items()}}
        receipt_bytes = _json(receipt)
    for name, data in files.items():
        _write(root, (*base, *_parts(name)), data)
    _write(root, (*base, "manifest.json"), receipt_bytes)
    # Re-capture before publication; never publish a mixed or stale source set.
    _, latest_hash, latest = _inputs(root)
    if latest_hash != manifest_hash or [(r["path"], r["sha256"]) for r in latest] != [(r["path"], r["sha256"]) for r in records]:
        raise ValueError("Approved inputs changed during build")
    index = ('---\nokf_version: "0.2"\n---\n\n# Endevor navigation\n\n'
             f'- [Current approved source bundle](snapshots/{snapshot}/index.md) - '
             f'{len(records)} declared views; navigation only.\n').encode()
    pointer = {"snapshot": snapshot, "manifest_sha256": _digest(receipt_bytes), "index_sha256": _digest(index)}
    _write(root, (*OUTPUT, "index.md"), index, replace=True)
    _write(root, (*OUTPUT, "current.json"), _json(pointer), replace=True)
    return check(root)


def _checked(root):
    """Capture and validate one snapshot; callers never reload a moving pointer."""
    root = _root(root)
    pointer, receipt = _load(root)
    manifest, digest, records = _inputs(root)
    graph = receipt["graph"]
    if graph.get("generator_sha256") != _tool_sha256() or digest != graph["input_manifest_sha256"] or [(n["path"], n["sha256"]) for n in graph["nodes"]] != [(r["path"], r["sha256"]) for r in records]:
        raise ValueError("Navigation is stale; rebuild from current approved inputs")
    return pointer, receipt


def check(root):
    """Validate generated artifacts and all declared current approved source views."""
    pointer, receipt = _checked(root)
    return _summary(pointer, receipt["graph"])


def walk(root, start, direction="dependencies", max_depth=2, max_nodes=40):
    """Return bounded navigation only after full source and artifact freshness checks."""
    if direction not in {"dependencies", "dependents", "both"} or type(max_depth) is not int or not 0 <= max_depth <= 20 or type(max_nodes) is not int or not 1 <= max_nodes <= 200:
        raise ValueError("Invalid traversal bounds")
    pointer, receipt = _checked(root)
    graph = receipt["graph"]
    summary = _summary(pointer, graph)
    matched = [n for n in graph["nodes"] if start in {n["id"], n["path"]}]
    if len(matched) != 1:
        raise ValueError("Use an exact declared file path or node ID")
    start_id = matched[0]["id"]
    depths, queue, truncated = {start_id: 0}, deque([start_id]), False
    while queue:
        current = queue.popleft()
        adjacent = set()
        for ref in graph["references"]:
            if ref["state"] != "resolved":
                continue
            if direction in {"dependencies", "both"} and ref["source"] == current:
                adjacent.add(ref["target"])
            if direction in {"dependents", "both"} and ref["target"] == current:
                adjacent.add(ref["source"])
        for neighbor in sorted(adjacent - depths.keys()):
            if depths[current] >= max_depth or len(depths) >= max_nodes:
                truncated = True
                continue
            depths[neighbor] = depths[current] + 1
            queue.append(neighbor)
    edges = [r for r in graph["references"] if r["source"] in depths and r["target"] in depths]
    unresolved = [r for r in graph["references"] if r["source"] in depths and r["state"] != "resolved"]
    references_truncated = len(edges) > MAX_QUERY_REFERENCES or len(unresolved) > MAX_QUERY_REFERENCES
    return summary | {"start": start_id, "direction": direction, "truncated": truncated or references_truncated,
                      "nodes": [{k: n[k] for k in ("id", "path", "kind", "sha256")} | {"depth": depths[n["id"]]} for n in graph["nodes"] if n["id"] in depths],
                      "edges": edges[:MAX_QUERY_REFERENCES], "unresolved": unresolved[:MAX_QUERY_REFERENCES],
                      "edges_total": len(edges), "unresolved_total": len(unresolved), "references_truncated": references_truncated}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build")
    commands.add_parser("check")
    traverse = commands.add_parser("walk")
    traverse.add_argument("--start", required=True)
    traverse.add_argument("--direction", choices=("dependencies", "dependents", "both"), default="dependencies")
    traverse.add_argument("--max-depth", type=int, default=2)
    traverse.add_argument("--max-nodes", type=int, default=40)
    args = parser.parse_args()
    try:
        result = walk(args.root, args.start, args.direction, args.max_depth, args.max_nodes) if args.command == "walk" else {"build": build, "check": check}[args.command](args.root)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "blocked", "reason": type(exc).__name__,
                          "action": "Check approved manifest, safe paths, supported inputs and current bundle; no acceptance produced"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
