"""Render sanitized canonical migration facts into one marked Markdown section.

Standard library only. No source discovery, code execution, model calls, flow
creation or acceptance decisions. Input/artifact hashes describe bytes observed
at refresh time; they do not establish behavior, provenance trust or readiness.
"""
import argparse
import hashlib
import heapq
import html
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from urllib.parse import quote


BEGIN = b"<!-- BEGIN GENERATED MIGRATION FACTS -->"
END = b"<!-- END GENERATED MIGRATION FACTS -->"
STATES = {"provided", "missing", "stale", "access-restricted", "deferred"}


class InvalidInput(ValueError):
    """The supplied view cannot be rendered without ambiguity."""


def fail(message):
    raise InvalidInput(message)


def obj(value, label):
    if not isinstance(value, dict):
        fail(f"{label} must be an object")
    return value


def array(value, label):
    if not isinstance(value, list):
        fail(f"{label} must be an array")
    return value


def string(value, label, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()):
        fail(f"{label} must be a {'possibly empty ' if empty else 'nonempty '}string")
    return value


def identifier(value, label):
    value = string(value, label)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", value):
        fail(f"{label} must contain only letters, digits, '_', '.', ':', or '-'")
    return value


def strings(value, label, ids=False):
    result = [(identifier if ids else string)(item, label) for item in array(value, label)]
    if len(result) != len(set(result)):
        fail(f"duplicate value in {label}")
    return sorted(result)


def unique(rows, key, label):
    result = {}
    for row in array(rows, label):
        row = obj(row, label)
        value = identifier(row.get(key), key)
        if value in result:
            fail(f"duplicate {key}: {value}")
        result[value] = row
    return result


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load(path):
    data = path.read_bytes()
    try:
        value = json.loads(data, object_pairs_hook=reject_duplicate_keys,
                           parse_constant=lambda value: fail(f"invalid JSON constant: {value}"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"invalid JSON in {path.name}: {exc}")
    return obj(value, path.name), hashlib.sha256(data).hexdigest()


def same_path(left, right):
    return left == right or (left.exists() and right.exists() and os.path.samefile(left, right))


def local_artifact(base, raw):
    raw = string(raw, "artifact path")
    if (Path(raw).is_absolute() or "\\" in raw or any(ord(c) < 32 for c in raw)
            or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", raw)):
        fail("artifact path must be a local relative path below the inventory directory")
    target = (base / raw).resolve()
    if not target.is_relative_to(base):
        fail("artifact path escapes the inventory directory")
    return target


def artifact_status(artifact, base, output):
    artifact = obj(artifact, "artifact")
    target = local_artifact(base, artifact.get("path"))
    if same_path(target, output):
        fail("output overlaps an artifact")
    declared = string(artifact.get("state"), "artifact state")
    if declared not in STATES:
        fail(f"invalid artifact state: {declared}")
    expected = artifact.get("sha256")
    if expected is not None and not (isinstance(expected, str) and re.fullmatch(r"[0-9a-fA-F]{64}", expected)):
        fail("artifact sha256 must be 64 hexadecimal characters or null")
    expected = expected.lower() if expected else None
    state, note, actual = declared, "declared; not verified", None
    # Deferred/restricted paths are references only and must not be opened.
    if declared not in {"deferred", "access-restricted"}:
        try:
            if not stat.S_ISREG(target.stat().st_mode):
                state, note = "missing", "not a regular file"
            else:
                with target.open("rb") as stream:
                    digest = hashlib.sha256()
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                actual = digest.hexdigest()
                if expected is None:
                    state, note = "stale", "unpinned; no expected SHA-256"
                elif expected != actual:
                    state, note = "stale", "SHA-256 mismatch"
                elif declared == "provided":
                    state, note = "provided", "SHA-256 matches; behavior unverified"
                else:
                    note = "SHA-256 matches; declared state retained"
        except FileNotFoundError:
            state, note = "missing", "not found"
        except PermissionError:
            state, note = "access-restricted", "not readable"
        except OSError:
            state, note = "access-restricted", "could not read"
    return {"path": artifact["path"], "target": target, "declared": declared,
            "state": state, "note": note, "expected": expected, "actual": actual}


def canonical(inventory_path, source_paths, output):
    all_inputs = [inventory_path, *source_paths]
    for index, path in enumerate(all_inputs):
        if same_path(path, output):
            fail("output overlaps a canonical input")
        if any(same_path(path, other) for other in all_inputs[:index]):
            fail("duplicate canonical input path")
    inventory, digest = load(inventory_path)
    provenance = [("inventory", inventory_path, digest)]
    programs = unique(inventory.get("programs"), "program_id", "programs")
    migrations = {}
    for program_id, program in sorted(programs.items()):
        for consumer in array(program.get("consumers"), "consumers"):
            obj(consumer, "consumer")
            for field in ("process_id", "step_id", "provider", "version"):
                string(consumer.get(field), f"consumer {field}")
        for migration_id, migration in unique(program.get("migrations"), "migration_id", "migrations").items():
            if migration_id in migrations:
                fail(f"duplicate migration_id: {migration_id}")
            for field in ("proposed_name", "stage"):
                string(migration.get(field), field)
            blocker = string(migration.get("blocker", ""), "blocker", empty=True)
            migrations[migration_id] = {
                **migration, "program_id": program_id, "blocker": blocker,
                "depends_on": strings(migration.get("depends_on"), "depends_on", ids=True),
                "python_symbols": strings(migration.get("python_symbols"), "python_symbols"),
                "retain_python": strings(migration.get("retain_python"), "retain_python"),
                "artifacts": [artifact_status(a, inventory_path.parent, output)
                              for a in array(migration.get("artifacts"), "artifacts")],
            }
    for migration_id, migration in migrations.items():
        for dependency in migration["depends_on"]:
            if dependency not in migrations:
                fail(f"{migration_id}: unknown dependency {dependency}")
    mapped_programs, mappings = set(), {}
    for path in sorted(source_paths, key=str):
        source_map, digest = load(path)
        program_id = identifier(source_map.get("program_id"), "program_id")
        if program_id not in programs:
            fail(f"source map has unknown program_id: {program_id}")
        if program_id in mapped_programs:
            fail(f"duplicate source map for program_id: {program_id}")
        mapped_programs.add(program_id)
        provenance.append((f"source map: {program_id}", path, digest))
        units = unique(source_map.get("source_units"), "source_id", "source_units")
        array(source_map.get("rules"), "rules")
        for migration_id, mapping in unique(source_map.get("migrations"), "migration_id", "source mappings").items():
            if migration_id not in migrations or migrations[migration_id]["program_id"] != program_id:
                fail(f"unknown migration_id for source map {program_id}: {migration_id}")
            source_ids = strings(mapping.get("source_ids"), "source_ids", ids=True)
            if not source_ids:
                fail(f"missing source mapping: {migration_id}")
            for source_id in source_ids:
                if source_id not in units:
                    fail(f"{migration_id}: unknown source_id {source_id}")
            mappings[migration_id] = source_ids
    for migration_id in migrations:
        if migration_id not in mappings:
            fail(f"missing source mapping: {migration_id}")
        migrations[migration_id]["source_ids"] = mappings[migration_id]
    return programs, migrations, provenance


def dependency_groups(migrations):
    """Iterative graph traversal avoids recursion limits on long real chains."""
    graph = {key: value["depends_on"] for key, value in migrations.items()}
    reverse = {key: [] for key in graph}
    for key, dependencies in graph.items():
        for dependency in dependencies:
            reverse[dependency].append(key)
    visited, finished = set(), []
    for root in sorted(graph):
        stack = [(root, False)]
        while stack:
            node, exiting = stack.pop()
            if exiting:
                finished.append(node)
            elif node not in visited:
                visited.add(node)
                stack.append((node, True))
                stack.extend((n, False) for n in reversed(graph[node]) if n not in visited)
    visited, cycles = set(), []
    for root in reversed(finished):
        if root in visited:
            continue
        group, stack = [], [root]
        visited.add(root)
        while stack:
            node = stack.pop()
            group.append(node)
            for successor in reverse[node]:
                if successor not in visited:
                    visited.add(successor)
                    stack.append(successor)
        if len(group) > 1 or root in graph[root]:
            cycles.append(sorted(group))
    cycles.sort()
    cyclic = {node for group in cycles for node in group}
    blocked, stack = set(cyclic), sorted(cyclic)
    while stack:
        for successor in reverse[stack.pop()]:
            if successor not in blocked:
                blocked.add(successor)
                stack.append(successor)
    pending = {node: len(graph[node]) for node in graph if node not in blocked}
    ready = [node for node, count in pending.items() if count == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        node = heapq.heappop(ready)
        order.append(node)
        for successor in reverse[node]:
            if successor in pending:
                pending[successor] -= 1
                if pending[successor] == 0:
                    heapq.heappush(ready, successor)
    return order, cycles, blocked - cyclic


def md(value):
    """Literal table/paragraph text, with HTML and automatic links disabled."""
    value = html.escape(" ".join(str(value).split()), quote=True)
    value = re.sub(r"([\\`*_\[\]{}|#!~])", r"\\\1", value)
    return value.replace(":", "&#58;").replace("@", "&#64;")


def joined(values):
    return ", ".join(md(value) for value in values) or "—"


def render(programs, migrations, provenance, output):
    order, cycles, downstream = dependency_groups(migrations)
    blocked = set(downstream) | {node for group in cycles for node in group}
    for key, migration in migrations.items():
        if (migration["blocker"] or migration["stage"] in {"blocked", "stale"}
                or any(a["state"] in {"missing", "stale", "access-restricted"} for a in migration["artifacts"])):
            blocked.add(key)
    lines = ["## Generated migration facts", "",
             f"Programs: {len(programs)}. Migration candidates: {len(migrations)}. Blocker count: {len(blocked)} (distinct candidates).", "",
             "Snapshot only: supplied milestones are declarations, not verified readiness. "
             "Hashes identify observed input bytes; artifact availability does not prove behavior. "
             "No flow is created and no Python acceptance gate is added.", "", "### Input provenance", "",
             "| Input | Local path | SHA-256 |", "|---|---|---|"]
    for label, path, digest in sorted(provenance, key=lambda row: (row[0], str(row[1]))):
        relative = os.path.relpath(path, output.parent)
        lines.append(f"| {md(label)} | {md(relative)} | {digest} |")
    lines += ["", "### Dependency order", "",
              "Structural prerequisite order only; declared blockers and stale artifacts still require resolution.", ""]
    lines += [f"{index}. {md(key)}" for index, key in enumerate(order, 1)] or ["No acyclic candidates available."]
    for group in cycles:
        lines += ["", f"- Cycle group: {joined(group)}. Blocked; no order asserted within this group."]
    for key in sorted(downstream):
        lines.append(f"- {md(key)}: blocked by cycle dependency.")
    lines += ["", "### Program consumers", "",
              "| Program | Process | Step | Active provider (declared) | Version |", "|---|---|---|---|---|"]
    for program_id, program in sorted(programs.items()):
        consumers = sorted(program["consumers"], key=lambda c: tuple(c[f] for f in ("process_id", "step_id", "provider", "version")))
        for consumer in consumers:
            lines.append("| " + " | ".join(md(v) for v in [program_id, consumer["process_id"], consumer["step_id"], consumer["provider"], consumer["version"]]) + " |")
        if not consumers:
            lines.append(f"| {md(program_id)} | Not supplied | — | Unverified | — |")
    if not migrations:
        lines += ["", "No migration candidates supplied; discovery completeness is unknown."]
    for key, migration in sorted(migrations.items()):
        reasons = []
        if migration["blocker"]:
            reasons.append(migration["blocker"])
        if migration["stage"] in {"blocked", "stale"}:
            reasons.append(f"declared stage {migration['stage']}")
        if key in downstream:
            reasons.append("blocked by cycle dependency")
        elif any(key in group for group in cycles):
            reasons.append("dependency cycle")
        if any(a["state"] in {"missing", "stale", "access-restricted"} for a in migration["artifacts"]):
            reasons.append("artifact availability unresolved")
        lines += ["", f"### Flow {md(key)}", "", "| Field | Supplied fact |", "|---|---|",
                  f"| Proposed name | {md(migration['proposed_name'])} |",
                  f"| Program | {md(migration['program_id'])} |",
                  f"| Declared stage | {md(migration['stage'])} |",
                  f"| Blocker | {joined(reasons) if reasons else 'None declared; readiness unverified'} |",
                  f"| Source IDs | {joined(migration['source_ids'])} |",
                  f"| Python ETL symbols | {joined(migration['python_symbols'])} |",
                  f"| Retain Python | {joined(migration['retain_python'])} |",
                  f"| Predecessors | {joined(migration['depends_on'])} |", "",
                  "| Artifact | Declared | Observed availability | Expected SHA-256 | Observed SHA-256 | Detail |",
                  "|---|---|---|---|---|---|"]
        for artifact in sorted(migration["artifacts"], key=lambda a: (a["path"], a["declared"], a["expected"] or "")):
            relative = os.path.relpath(artifact["target"], output.parent)
            link = f"[{md(artifact['path'])}]({quote(relative, safe='/.-_~')})"
            lines.append(f"| {link} | {artifact['declared']} | {artifact['state']} | {artifact['expected'] or 'Unpinned'} | {artifact['actual'] or 'Not read'} | {md(artifact['note'])} |")
        if not migration["artifacts"]:
            lines.append("| None supplied | — | Unverified | — | — | No artifact evidence supplied |")
    return ("\n" + "\n".join(lines) + "\n\n").encode("utf-8")


def refresh(inventory_path, source_paths, output):
    inventory_path, output = Path(inventory_path).resolve(), Path(output).resolve()
    source_paths = [Path(path).resolve() for path in source_paths]
    programs, migrations, provenance = canonical(inventory_path, source_paths, output)
    previous = output.read_bytes()
    if previous.count(BEGIN) != 1 or previous.count(END) != 1 or previous.index(BEGIN) > previous.index(END):
        fail("output must contain unique, ordered generated-section markers")
    start, stop = previous.index(BEGIN) + len(BEGIN), previous.index(END)
    updated = previous[:start] + render(programs, migrations, provenance, output) + previous[stop:]
    if updated == previous:
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=f".{output.name}.", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IMODE(output.stat().st_mode))
        # Do not overwrite commentary edited while inputs/artifacts were read.
        if output.read_bytes() != previous:
            fail("output changed during refresh; retry against current commentary")
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--source-map", action="append", default=[], type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        refresh(args.inventory, args.source_map, args.output)
    except (InvalidInput, OSError) as exc:
        parser.exit(2, f"render_migration: {exc}\n")


if __name__ == "__main__":
    main()
