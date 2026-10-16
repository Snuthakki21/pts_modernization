"""Export a bounded, offline, whitelisted progress projection; not an auditor.

Only the explicitly supplied inventory is read. Evidence IDs are references,
never paths to open. A fresh output is published atomically without overwrite.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile


MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 20000
REQUIRED_GATES = ("unit_cases", "legacy_comparison", "record_trace", "code_quality", "security", "independent_audit")
GATE_STATES = {"passed", "failed", "pending", "blocked", "unknown"}
BLOCKER_CATEGORIES = {"dependency", "evidence", "clarification", "security", "quality", "validation", "access", "other"}
FINDING_STATES = {"open", "fixed_pending_verification", "closed_verified", "false_positive_with_evidence", "accepted_risk", "remediated", "accepted"}


class InvalidInput(ValueError):
    """The inventory cannot be projected without ambiguity."""


def fail(message):
    raise InvalidInput(message)


def obj(value, label):
    if not isinstance(value, dict):
        fail(f"{label} must be an object")
    return value


def rows(value, label):
    if not isinstance(value, list) or len(value) > MAX_ROWS:
        fail(f"{label} must be an array of at most {MAX_ROWS} items")
    return value


def identifier(value, label):
    if (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value)
            or value.lower() in {"constructor", "prototype", "__proto__"}):
        fail(f"{label} must be a safe opaque identifier (1-128 characters)")
    return value


def label(value, fallback):
    if value is None:
        return fallback
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _().:-]{0,79}", value):
        fail("display_label must be 1-80 plain ASCII label characters")
    return value


def choice(value, allowed, name):
    if not isinstance(value, str) or value not in allowed:
        fail(f"invalid {name}")
    return value


def count(value, name):
    if value is None:
        return None
    if type(value) is not int or not 0 <= value < 2 ** 53:
        fail(f"{name} must be a nonnegative, safely representable integer or null")
    return value


def unique(values, key, name):
    result = {}
    for row in rows(values, name):
        row = obj(row, name)
        identity = identifier(row.get(key), key)
        if identity in result:
            fail(f"duplicate {key}: {identity}")
        result[identity] = row
    return result


def refs(value):
    result = [identifier(item, "evidence_ref") for item in rows(value, "evidence_refs")]
    if len(result) != len(set(result)):
        fail("duplicate evidence_ref")
    return sorted(result)


def receipt(raw, version, states=GATE_STATES):
    raw = obj(raw, "receipt")
    declared_version = raw.get("version")
    if declared_version is not None:
        identifier(declared_version, "receipt version")
    return {"status": choice(raw.get("status", "unknown"), states | {"unknown"}, "receipt status"),
            "current": version is not None and declared_version == version,
            "version": declared_version, "evidence_refs": refs(raw.get("evidence_refs", []))}


def passed(value, statuses):
    return value["status"] in statuses and value["current"] and bool(value["evidence_refs"])


def timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        fail("timestamp must be an ISO-8601 string with a timezone")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail("invalid ISO-8601 timestamp")
    if result.tzinfo is None:
        fail("timestamp must include a timezone")
    return result


def risk_is_current(raw, observed_at):
    required = ("accountable_owner_ref", "decision_ref", "rationale_ref")
    for key in required:
        if raw.get(key) is not None:
            identifier(raw[key], key)
    controls = refs(raw.get("control_refs", []))
    expiry = timestamp(raw["expires_at"]) if raw.get("expires_at") is not None else None
    return bool(all(raw.get(key) for key in required) and controls and expiry and expiry > observed_at)


def program_row(raw, process_ids, observed_at):
    program_id = identifier(raw.get("program_id"), "program_id")
    progress = obj(raw.get("progress", {}), "progress")
    version = progress.get("current_version")
    if version is not None:
        identifier(version, "current_version")
    lifecycle = choice(progress.get("lifecycle", "active"), {"active", "retired"}, "program lifecycle")
    conversion = receipt(progress.get("conversion", {}), version, {"converted", "pending", "failed"})
    catalog = receipt(progress.get("rule_catalog", {}), version, {"complete", "partial", "pending"})
    retirement = receipt(progress.get("retirement", {}), version, {"accepted", "pending"})
    gates_raw = obj(progress.get("gates", {}), "gates")
    if set(gates_raw) - set(REQUIRED_GATES):
        fail("unknown program gate ID")
    gates = [{"gate_id": gate, **receipt(gates_raw.get(gate, {}), version,
              GATE_STATES | ({"approved_difference"} if gate == "legacy_comparison" else set()))}
             for gate in REQUIRED_GATES]
    blockers = [{"blocker_id": key, "category": choice(item.get("category", "other"), BLOCKER_CATEGORIES, "blocker category")}
                for key, item in unique(progress.get("blockers", []), "blocker_id", "blockers").items()]
    memberships, consumers = set(), []
    for consumer in rows(raw.get("consumers", []), "consumers"):
        consumer = obj(consumer, "consumer")
        process_id = identifier(consumer.get("process_id"), "process_id")
        memberships.add(process_id)
        consumer_version = consumer.get("version")
        if consumer_version is not None:
            identifier(consumer_version, "consumer version")
        consumers.append({"process_id": process_id, "step_id": identifier(consumer.get("step_id"), "step_id"),
                          "provider": choice(consumer.get("provider", "unknown"), {"python", "sparkflow", "mainframe", "unknown"}, "consumer provider"),
                          "version": consumer_version, "current": version is not None and consumer_version == version})
        if process_id not in process_ids:
            blockers.append({"blocker_id": process_id, "category": "unknown_process_reference"})
    rules = []
    categories = {"business": 0, "technical": 0, "mixed": 0}
    receipts = [conversion, catalog, *gates]
    for rule_id, rule in unique(progress.get("rules", []), "rule_id", "rules").items():
        category = choice(rule.get("category"), set(categories), "rule category")
        categories[category] += 1
        disposition = choice(rule.get("lifecycle", "retained"), {"retained", "retired"}, "rule lifecycle")
        rule_version = rule.get("version")
        if rule_version is not None:
            identifier(rule_version, "rule version")
        evidence = refs(rule.get("evidence_refs", []))
        positive = count(rule.get("positive_passed"), "positive_passed")
        negative = count(rule.get("negative_passed"), "negative_passed")
        current = version is not None and rule_version == version
        retired = False
        if disposition == "retired":
            retired = passed(receipt(rule.get("retirement", {}), version, {"accepted", "pending"}), {"accepted"})
            if not retired:
                blockers.append({"blocker_id": rule_id, "category": "unaccepted_rule_retirement"})
        quota = bool(current and evidence and positive is not None and negative is not None and positive >= 100 and negative >= 100)
        rules.append({"rule_id": rule_id, "category": category, "lifecycle": "retired" if retired else "retained",
                      "positive_passed": positive, "negative_passed": negative, "quota_met": quota,
                      "current": current, "evidence_refs": evidence})
        if rule_version is not None and not current and not retired:
            receipts.append({"version": rule_version, "current": False})
    findings = []
    for finding_id, finding in unique(progress.get("findings", []), "finding_id", "findings").items():
        finding_state = choice(finding.get("status", "open"), FINDING_STATES, "finding status")
        finding_state = {"remediated": "closed_verified", "accepted": "accepted_risk"}.get(finding_state, finding_state)
        severity = choice(finding.get("severity"), {"critical", "high", "medium", "low", "info"}, "finding severity")
        resolution_raw = obj(finding.get("resolution", {}), "finding resolution")
        resolution = receipt(resolution_raw, version, {"verified", "accepted", "pending"})
        resolved = False
        if finding_state in {"closed_verified", "false_positive_with_evidence"}:
            resolved = passed(resolution, {"verified"})
        elif finding_state == "accepted_risk":
            decision_current = risk_is_current(resolution_raw, observed_at)
            resolved = severity not in {"high", "critical"} and passed(resolution, {"accepted"}) and decision_current
        status = "remediated" if finding_state == "closed_verified" else "accepted" if finding_state in {"false_positive_with_evidence", "accepted_risk"} else "open"
        findings.append({"finding_id": finding_id, "severity": severity, "status": status, "finding_state": finding_state,
                         "resolved": bool(resolved), "evidence_refs": resolution["evidence_refs"]})
        if not resolved:
            blockers.append({"blocker_id": finding_id, "category": "unresolved_finding"})
    retired = lifecycle == "retired" and passed(retirement, {"accepted"}) and not consumers
    if lifecycle == "retired" and consumers:
        blockers.append({"blocker_id": program_id, "category": "active_consumer_bindings"})
    if lifecycle == "retired" and not retired:
        blockers.append({"blocker_id": program_id, "category": "unaccepted_program_retirement"})
    converted = passed(conversion, {"converted"})
    catalog_complete = "rules" in progress and passed(catalog, {"complete"})
    retained_rules = [rule for rule in rules if rule["lifecycle"] == "retained"]
    if lifecycle == "active" and catalog_complete and not retained_rules:
        blockers.append({"blocker_id": program_id, "category": "no_retained_rules"})
    blocked = bool(blockers) or any(gate["status"] in {"failed", "blocked"} for gate in gates) or conversion["status"] == "failed"
    stale = any(item["version"] is not None and not item["current"] for item in receipts)
    complete = bool(not retired and lifecycle == "active" and not blocked and not stale and converted and catalog_complete
                    and retained_rules and all(rule["quota_met"] for rule in retained_rules)
                    and all(passed(gate, {"passed", "approved_difference"}) for gate in gates))
    state = ("retired" if retired else "blocked" if blocked else "stale" if stale else "completed" if complete
             else "converted" if converted else "in_progress" if progress else "unknown")
    if not catalog_complete and state in {"converted", "in_progress"}:
        state = "unverified"
    migrations = []
    for migration_id, migration in unique(raw.get("migrations", []), "migration_id", "migrations").items():
        dependencies = refs(migration.get("depends_on", []))
        stage = choice(migration.get("stage", "unknown"), {"identified", "design", "python_active", "ready", "flow_validated", "sparkflow_active", "retired", "blocked", "stale", "unknown"}, "migration stage")
        artifact_states = [choice(obj(artifact, "artifact").get("state", "unknown"),
                                 {"provided", "missing", "stale", "access-restricted", "deferred", "unknown"}, "artifact state")
                           for artifact in rows(migration.get("artifacts", []), "artifacts")]
        migrations.append({"migration_id": migration_id, "label": label(migration.get("display_label"), migration_id),
                           "stage": stage, "depends_on": dependencies,
                           "blocked": bool(migration.get("blocker")) or stage in {"blocked", "stale"}
                           or any(state in {"missing", "stale", "access-restricted", "unknown"} for state in artifact_states)})
    return {"program_id": program_id, "label": label(progress.get("display_label"), program_id), "current_version": version,
            "state": state, "converted": bool(converted and not retired), "completed": complete, "process_ids": sorted(memberships),
            "conversion": conversion, "rule_catalog": catalog, "retirement": retirement,
            "consumers": sorted(consumers, key=lambda row: (row["process_id"], row["step_id"])),
            "catalog_complete": catalog_complete, "rule_counts": {**categories, "total": len(rules),
            "retained": sum(rule["lifecycle"] == "retained" for rule in rules), "retired": sum(rule["lifecycle"] == "retired" for rule in rules),
            "quota_met": sum(rule["quota_met"] for rule in rules if rule["lifecycle"] == "retained")},
            "rules": sorted(rules, key=lambda row: row["rule_id"]), "gates": gates,
            "findings": sorted(findings, key=lambda row: row["finding_id"]), "blockers": blockers,
            "migrations": sorted(migrations, key=lambda row: row["migration_id"])}


def snapshot(inventory, digest, observed_at):
    inventory = obj(inventory, "inventory")
    if type(inventory.get("schema_version")) is not int or inventory["schema_version"] != 1:
        fail("inventory schema_version must be 1")
    status = choice(inventory.get("status", "unverified"), {"unverified", "partial", "complete"}, "inventory status")
    observed = timestamp(observed_at)
    processes_raw = unique(inventory.get("processes", []), "process_id", "processes")
    programs = [program_row(raw, set(processes_raw), observed) for _, raw in sorted(unique(inventory.get("programs"), "program_id", "programs").items())]
    all_migrations = [migration for program in programs for migration in program["migrations"]]
    migration_ids = {migration["migration_id"] for migration in all_migrations}
    if len(all_migrations) != len(migration_ids):
        fail("duplicate migration_id across programs")
    migrations = {migration["migration_id"]: migration for migration in all_migrations}
    indegrees, dependents = {}, {key: [] for key in migrations}
    for key, migration in migrations.items():
        indegrees[key] = len(migration["depends_on"])
        for dependency in migration["depends_on"]:
            if dependency in migrations:
                dependents[dependency].append(key)
    ready = [key for key, degree in indegrees.items() if degree == 0]
    visited = set()
    while ready:
        key = ready.pop()
        visited.add(key)
        for dependent in dependents[key]:
            indegrees[dependent] -= 1
            if migrations[key]["blocked"]:
                migrations[dependent]["blocked"] = True
            if indegrees[dependent] == 0:
                ready.append(dependent)
    for key in migration_ids - visited:
        migrations[key]["blocked"] = True
    processes = []
    for process_id, raw in sorted(processes_raw.items()):
        members = [program for program in programs if process_id in program["process_ids"]]
        progress = obj(raw.get("progress", {}), "process progress")
        version = progress.get("current_version")
        if version is not None:
            identifier(version, "process current_version")
        integration = receipt(progress.get("integration", {}), version)
        bindings = [consumer for program in members for consumer in program["consumers"] if consumer["process_id"] == process_id]
        bindings_current = bool(bindings and all(consumer["current"] and consumer["provider"] in {"python", "sparkflow"} for consumer in bindings))
        complete = bool(members and all(program["completed"] for program in members) and bindings_current and passed(integration, {"passed"}))
        state = "completed" if complete else "blocked" if any(program["state"] == "blocked" for program in members) or integration["status"] in {"failed", "blocked"} else "stale" if (integration["version"] is not None and not integration["current"]) or any(consumer["version"] is not None and not consumer["current"] for consumer in bindings) else "in_progress" if members else "unknown"
        processes.append({"process_id": process_id, "label": label(progress.get("display_label"), process_id),
                          "program_ids": [program["program_id"] for program in members], "total_programs": len(members),
                          "completed_programs": sum(program["completed"] for program in members), "state": state,
                          "integration": integration, "bindings_current": bindings_current})
    retired = sum(program["state"] == "retired" for program in programs)
    active = len(programs) - retired
    complete = sum(program["completed"] for program in programs)
    counters = {"total_programs": len(programs), "active_programs": active,
                "converted_programs": sum(program["converted"] for program in programs), "completed_programs": complete,
                "blocked_programs": sum(program["state"] == "blocked" for program in programs),
                "stale_programs": sum(program["state"] == "stale" for program in programs),
                "unknown_programs": sum(program["state"] in {"unknown", "unverified"} for program in programs),
                "retired_programs": retired, "completion_percent": round(100 * complete / active, 2) if active else None}
    return {"schema_version": 1, "kind": "conversion_progress", "fictional": False, "observed_at": observed_at,
            "inventory_sha256": digest, "inventory_status": status, "completeness": "declared_not_verified",
            "counters": counters, "programs": programs, "processes": processes}


def duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("duplicate JSON key")
        if key.lower() in {"__proto__", "constructor", "prototype"}:
            fail("reserved JSON key")
        result[key] = value
    return result


def safe_path(path):
    path = Path(os.path.abspath(path))
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            fail("symlink paths are not allowed")
    return path


def export(inventory_path, output_path):
    source, output = safe_path(inventory_path), safe_path(output_path)
    if output.exists() or output == source:
        fail("output must be a new path distinct from inventory")
    if not output.parent.is_dir():
        fail("output parent must be an existing directory")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(source, flags)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_BYTES:
            fail("inventory must be a single-link regular file of at most 8 MiB")
        content = stream.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        fail("inventory exceeds 8 MiB")
    try:
        inventory = json.loads(content, object_pairs_hook=duplicate_keys,
                               parse_constant=lambda _: fail("nonfinite JSON number"),
                               parse_float=lambda _: fail("floating-point input is not supported"))
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, InvalidInput):
            raise
        fail("invalid or excessively nested inventory JSON")
    result = snapshot(inventory, hashlib.sha256(content).hexdigest(), datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    encoded = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if len(encoded) > MAX_BYTES:
        fail("progress export exceeds 8 MiB; reduce display inventory size")
    handle, temporary = tempfile.mkstemp(prefix=".progress-", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        safe_path(output)
        try:
            os.link(temporary, output)
        except FileExistsError:
            fail("output already exists; use a new filename")
    finally:
        os.unlink(temporary)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = export(args.inventory, args.output)
    except (InvalidInput, OSError) as exc:
        parser.exit(2, f"Progress export failed: {exc}\n")
    print(json.dumps({"output": str(args.output), "inventory_sha256": result["inventory_sha256"], "counters": result["counters"]}, sort_keys=True))


if __name__ == "__main__":
    main()
