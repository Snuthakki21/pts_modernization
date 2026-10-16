"""Create missing local state from tracked templates; never overwrite state.

This is a first-use file utility, not a scheduler or conversion engine. All plans
and existing files are checked before writing. A filesystem interruption can
still leave partial creation; the report identifies progress and the review path.
Existing state, decisions and repair allowances are never changed or migrated.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
STATE = {
    "state/inventory.json": "inventory.json",
    "state/decisions.json": "knowledge/decisions.json",
    "state/handoff.json": "knowledge/handoff.json",
    "state/local-index.json": "knowledge/local-index.json",
}
PROGRAM = {
    "program/program.json": "program.json",
    "program/source-map.json": "analysis/source-map.json",
    "program/rules.json": "analysis/rules.json",
    "program/questions.json": "analysis/questions.json",
    "program/design.json": "analysis/design.json",
}
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(1, 10)}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-finite JSON value")


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique,
                      parse_constant=_reject_constant)


def _ids(values):
    seen = set()
    for value in values:
        if (not isinstance(value, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value)
                or value.upper() in RESERVED or value.casefold() in seen):
            raise ValueError("Identifiers must be unique portable names: 1–64 ASCII letters, digits, underscores or hyphens; start with a letter/digit")
        seen.add(value.casefold())
    return list(values)


def _check_path(root, path, directory=False):
    """Reject aliases and unexpected filesystem objects without following them."""
    current = root
    parts = path.relative_to(root).parts
    for position, part in enumerate(parts):
        if current.exists():
            if any(child.name.casefold() == part.casefold() and child.name != part
                   for child in current.iterdir()):
                raise ValueError(f"Case-colliding path preserved: {path.relative_to(root)}")
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Symlink path preserved: {current.relative_to(root)}")
        if not current.exists():
            continue
        should_be_directory = position < len(parts) - 1 or directory
        if should_be_directory and not current.is_dir():
            raise ValueError(f"Expected directory; existing path preserved: {current.relative_to(root)}")
        if not should_be_directory:
            if not current.is_file() or current.stat().st_nlink != 1:
                raise ValueError(f"Non-regular or linked file preserved: {current.relative_to(root)}")


def _existing_matches(path, template):
    try:
        current = _read(path)
        if not isinstance(current, dict) or type(current.get("schema_version")) is not int:
            raise ValueError("Invalid root/schema")
        if current["schema_version"] != template["schema_version"]:
            raise ValueError("Different schema")
        for key, value in template.items():
            if key not in current or (value is not None and type(current[key]) is not type(value)):
                raise ValueError("Missing field or incompatible type")
        for key in ("program_id", "process_id"):
            if key in template and current[key] != template[key]:
                raise ValueError("Different identity")
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        raise ValueError(f"Existing {path.name} is preserved; review its schema/identity before initialization") from exc


def _write_new(path, content):
    # Exclusive creation also rejects a target appearing after preflight.
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def initialize(root, program_ids=(), process_ids=()):
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Root must be an existing directory, not a symlink")
    root = root.resolve()
    program_ids, process_ids = _ids(list(program_ids)), _ids(list(process_ids))
    plans = [(source, destination, {}) for source, destination in STATE.items()]
    extra_directories = set()
    for program in program_ids:
        base = f"programs/{program}"
        plans.extend((source, f"{base}/{destination}", {"__PROGRAM_ID__": program})
                     for source, destination in PROGRAM.items())
        extra_directories.update(root / base / part for part in ("source", "target", "tests", "runs"))
    for process in process_ids:
        plans.append(("process/process.json", f"processes/{process}/process.json",
                      {"__PROCESS_ID__": process}))
        extra_directories.add(root / "processes" / process / "integration/runs")

    files, directories = [], set(extra_directories)
    for source, destination, substitutions in plans:
        template = _read(TEMPLATES / source)
        if (not isinstance(template, dict) or type(template.get("schema_version")) is not int
                or template["schema_version"] != 1):
            raise ValueError(f"Invalid tracked template: {source}")
        text = json.dumps(template, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        for token, value in substitutions.items():
            text = text.replace(token, value)
        template = json.loads(text)
        path = root / destination
        files.append((path, text, template))
        directories.update(parent for parent in path.parents if parent != root and root in parent.parents)
    for path in tuple(directories):
        directories.update(parent for parent in path.parents if parent != root and root in parent.parents)

    # Complete preflight before creating even a directory.
    for path in directories:
        _check_path(root, path, directory=True)
    preserved = []
    for path, _, template in files:
        _check_path(root, path)
        if path.exists():
            _existing_matches(path, template)
            preserved.append(path.relative_to(root).as_posix())
    report = {"status": "unchanged", "created_files": [], "created_directories": [],
              "preserved_files": preserved, "acceptance_established": False}
    review_path = None
    try:
        for path in sorted(directories, key=lambda item: (len(item.parts), str(item))):
            review_path = path.relative_to(root).as_posix()
            _check_path(root, path, directory=True)
            if not path.exists():
                path.mkdir()
                report["created_directories"].append(review_path)
        for path, content, _ in files:
            review_path = path.relative_to(root).as_posix()
            if review_path in preserved:
                continue
            _check_path(root, path)
            _write_new(path, content)
            report["created_files"].append(review_path)
    except (OSError, ValueError) as exc:
        report.update(status="partial", review_path=review_path,
                      error=f"{type(exc).__name__}: creation interrupted; inspect the review path and preserved state before retrying")
        return report
    if report["created_files"] or report["created_directories"]:
        report["status"] = "initialized"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Existing checkout root")
    parser.add_argument("--program", action="append", default=[], help="Supplied program ID; repeatable")
    parser.add_argument("--process", action="append", default=[], help="Supplied process ID; repeatable")
    args = parser.parse_args()
    try:
        report = initialize(args.root, args.program, args.process)
    except (OSError, ValueError) as exc:
        report = {"status": "blocked", "error": str(exc), "acceptance_established": False}
    print(json.dumps(report, indent=2))
    return 2 if report["status"] in ("blocked", "partial") else 0


if __name__ == "__main__":
    raise SystemExit(main())
