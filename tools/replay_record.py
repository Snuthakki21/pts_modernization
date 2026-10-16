#!/usr/bin/env python3
"""Materialize a pinned, synthetic/authorized record replay; execute only on request.

Bundle v1 is JSON with bundle_id, schema_version=1, artifacts, dependencies,
clock, environment and expectations. Required artifacts are records,
reference_data, state (JSON), target and adapter (UTF-8 Python). Each descriptor
is {"path": "relative/file", "sha256": "<64 lowercase hex>"} under the manifest
directory. All bytes are read once, checked and copied; the manifest itself is
hashed into report.json. Hashes identify a snapshot, not authenticity/approval.

records.json: {"records": [{"record_id":"r1","parents":[],"data":{...}}]}.
dependencies: {"complete":true,"context_record_ids":[],
               "full_partition":{"required":false}}.
If full_partition.required is true, complete:true and record_ids containing the
entire records artifact inventory are mandatory. Every record's parents must be
known, even outside the selected closure. Completeness is a producer attestation;
this utility cannot discover an omitted external dependency or missing snapshot.

clock: {"utc":"2026-01-02T03:04:05Z","business_date":"2026-01-02"}.
environment: {"contract_version":1,"python":"3.12",
              "implementation":"cpython","variables":{}}.
Python major.minor, implementation and declared environment variables must match
before execution; the utility never changes the global clock or environment.

expectations: {"r1":{
  "expected":{"value":{...},"provenance":{"source_id":"case-1","version":"1"}},
  "failed_observed":{"value":{...},"provenance":{"source_id":"run-1","version":"1"}}
}}. Approval/authenticity of these supplied references is not established here.

The separately pinned adapter defines replay(context) -> JSON. context contains
schema_version, bundle_id, selected_record_id, ordered records, reference_data,
state, clock, environment, and target:{source,sha256}. It must be trusted, pure,
standard-library-only code, relying exclusively on that snapshot. It can compile
the supplied target source explicitly. This is a contract, NOT a sandbox: trusted
Python runs locally with this process's permissions, including network/filesystem
access. Do not execute untrusted adapters or targets. No shell command is invoked
by this utility. Ordinary Python print output from the adapter is discarded.

Output is a new directory containing fixture.json, a portable bundle.json,
source_bundle.json (original manifest bytes), artifacts/ and report.json.
No existing output is overwritten. A matching expected value is a
comparison only, never acceptance/parity evidence; replay of a known failure is
reported separately. Exit 0: fixture created or expected comparison matched
without reproducing the failed reference; 1: mismatch/reproduced failure;
2: invalid input, incompatible environment, or execution error;
130: interrupted adapter load/replay, with a sanitized interrupted report.
"""

import argparse
import contextlib
import copy
from datetime import date, datetime, timedelta
import hashlib
import heapq
import io
import json
import os
from pathlib import Path
import platform
import re
import sys
import types


class ReplayError(ValueError):
    """Safe diagnostic containing no record contents."""


def require(condition, message):
    if not condition:
        raise ReplayError(message)


def object_value(value, label):
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON object key")
        result[key] = value
    return result


def reject_constant(_value):
    raise ReplayError("non-finite JSON number")


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"


def validate_json_result(value):
    """Reject Python values that the JSON encoder would silently coerce."""
    if type(value) is dict:
        require(all(type(key) is str for key in value), "adapter result keys must be strings")
        for child in value.values():
            validate_json_result(child)
    elif type(value) is list:
        for child in value:
            validate_json_result(child)
    else:
        require(type(value) in (str, int, float, bool, type(None)), "adapter result must be JSON")


def parse_json(raw):
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object, parse_constant=reject_constant)
        # A legal numeric token such as 1e999 can also overflow Python's float.
        json_bytes(value)
        return value
    except (UnicodeError, ValueError, TypeError, RecursionError) as error:
        raise ReplayError("invalid JSON; require finite values and unique object keys") from error


def id_list(value, label):
    require(isinstance(value, list) and all(nonempty(item) for item in value), f"{label} must be an ID list")
    require(len(set(value)) == len(value), f"{label} contains duplicate IDs")
    return value


def load_artifacts(bundle, root):
    descriptors = object_value(bundle.get("artifacts"), "artifacts")
    required = {"records", "reference_data", "state", "target", "adapter"}
    require(set(descriptors) == required, "artifacts must declare exactly records, reference_data, state, target, adapter")
    artifacts, paths = {}, set()
    for name in sorted(required):
        descriptor = object_value(descriptors[name], "artifact descriptor")
        relative, digest = descriptor.get("path"), descriptor.get("sha256")
        require(nonempty(relative), "artifact path is required")
        require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), "artifact sha256 is invalid")
        relative = Path(relative)
        require(not relative.is_absolute() and ".." not in relative.parts, "artifact path escapes bundle")
        try:
            path = (root / relative).resolve(strict=True)
            require(path.is_relative_to(root) and path.is_file(), "artifact escapes bundle or is not a file")
            require(path not in paths, "artifacts must have distinct paths")
            paths.add(path)
            raw = path.read_bytes()
        except (OSError, RuntimeError) as error:
            raise ReplayError("artifact is missing or unreadable") from error
        require(hashlib.sha256(raw).hexdigest() == digest, "artifact hash mismatch")
        if name in {"target", "adapter"}:
            require(relative.suffix == ".py", "target and adapter must be Python source files")
            try:
                raw.decode("utf-8")
            except UnicodeError as error:
                raise ReplayError("Python source must be UTF-8") from error
        artifacts[name] = raw
    return artifacts


def record_closure(records_document, dependencies, selected):
    rows = object_value(records_document, "records artifact").get("records")
    require(isinstance(rows, list), "records artifact must contain a records list")
    records = {}
    for row in rows:
        object_value(row, "record")
        record_id = row.get("record_id")
        require(nonempty(record_id), "record ID is required")
        require(record_id not in records, "duplicate record ID")
        id_list(row.get("parents"), "parents")
        object_value(row.get("data"), "record data")
        records[record_id] = row
    require(selected in records, "selected record is absent")

    # Validate the entire graph with a stable, iterative topological sort.
    children = {record_id: [] for record_id in records}
    degrees = {}
    for record_id, row in records.items():
        degrees[record_id] = len(row["parents"])
        for parent in row["parents"]:
            require(parent in records, "dangling parent record")
            children[parent].append(record_id)
    ready = [record_id for record_id, degree in degrees.items() if degree == 0]
    heapq.heapify(ready)
    ordered = []
    while ready:
        record_id = heapq.heappop(ready)
        ordered.append(record_id)
        for child in children[record_id]:
            degrees[child] -= 1
            if degrees[child] == 0:
                heapq.heappush(ready, child)
    require(len(ordered) == len(records), "cyclic record dependencies")

    object_value(dependencies, "dependencies")
    require(dependencies.get("complete") is True, "dependency closure is unknown or incomplete")
    context_ids = id_list(dependencies.get("context_record_ids"), "context_record_ids")
    require(all(record_id in records for record_id in context_ids), "context record is absent")
    partition = object_value(dependencies.get("full_partition"), "full_partition")
    require(type(partition.get("required")) is bool, "full_partition.required must be explicit")
    pending = [selected, *context_ids]
    if partition["required"]:
        require(partition.get("complete") is True, "full partition state is unknown or incomplete")
        membership = id_list(partition.get("record_ids"), "full partition record_ids")
        require(set(membership) == set(records), "full partition membership must equal the captured inventory")
        pending.extend(membership)
    included = set()
    while pending:
        record_id = pending.pop()
        if record_id not in included:
            included.add(record_id)
            pending.extend(records[record_id]["parents"])
    return [records[record_id] for record_id in ordered if record_id in included]


def validate_clock_environment(bundle, execute):
    clock = object_value(bundle.get("clock"), "clock")
    try:
        instant = datetime.fromisoformat(clock["utc"].replace("Z", "+00:00"))
        require(instant.utcoffset() == timedelta(0), "clock.utc must be an explicit UTC timestamp")
        business_date = clock["business_date"]
        require(date.fromisoformat(business_date).isoformat() == business_date, "business_date must be YYYY-MM-DD")
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ReplayError("clock must provide an explicit UTC timestamp and business date") from error
    environment = object_value(bundle.get("environment"), "environment")
    require(type(environment.get("contract_version")) is int and environment["contract_version"] == 1, "unsupported environment contract")
    version = environment.get("python")
    require(isinstance(version, str) and re.fullmatch(r"\d+\.\d+", version), "environment.python must be major.minor")
    require(nonempty(environment.get("implementation")), "Python implementation is required")
    variables = object_value(environment.get("variables"), "environment.variables")
    require(all(nonempty(key) and isinstance(value, str) for key, value in variables.items()), "environment variables must be explicit strings")
    if execute:
        current = f"{sys.version_info.major}.{sys.version_info.minor}"
        require(version == current, "incompatible Python version")
        require(environment["implementation"] == platform.python_implementation().lower(), "incompatible Python implementation")
        require(all(os.environ.get(key) == value for key, value in variables.items()), "environment contract mismatch")


def expectation_for(bundle, selected):
    expectations = object_value(bundle.get("expectations"), "expectations")
    expectation = object_value(expectations.get(selected), "selected record expectation")
    for name in ("expected", "failed_observed"):
        reference = object_value(expectation.get(name), name)
        require("value" in reference, "expected and failed_observed values are required")
        provenance = object_value(reference.get("provenance"), "expectation provenance")
        require(all(nonempty(provenance.get(key)) for key in ("source_id", "version")), "expectation provenance requires source_id and version")
    return expectation


def write_exclusive(path, raw, readonly=False):
    with path.open("xb") as stream:
        stream.write(raw)
    path.chmod(0o400 if readonly else 0o600)


def run(bundle_path, selected, output, execute=False):
    require(not output.exists() and not output.is_symlink(), "output already exists")
    manifest = bundle_path.resolve(strict=True)
    root = manifest.parent
    require(not output.resolve().is_relative_to(root), "output must be outside the bundle directory")
    manifest_raw = manifest.read_bytes()
    bundle = object_value(parse_json(manifest_raw), "bundle")
    require(type(bundle.get("schema_version")) is int and bundle["schema_version"] == 1, "unsupported bundle schema")
    require(nonempty(bundle.get("bundle_id")), "bundle_id is required")
    artifacts = load_artifacts(bundle, root)
    rows = record_closure(parse_json(artifacts["records"]), bundle.get("dependencies"), selected)
    validate_clock_environment(bundle, execute)
    expectation = expectation_for(bundle, selected)
    fixture = {
        "schema_version": 1,
        "bundle_id": bundle["bundle_id"],
        "selected_record_id": selected,
        "records": rows,
        "reference_data": parse_json(artifacts["reference_data"]),
        "state": parse_json(artifacts["state"]),
        "clock": bundle["clock"],
        "environment": bundle["environment"],
        "target": {"source": artifacts["target"].decode("utf-8"), "sha256": bundle["artifacts"]["target"]["sha256"]},
    }
    fixture_raw = json_bytes(fixture)
    portable_bundle = copy.deepcopy(bundle)
    for name, descriptor in portable_bundle["artifacts"].items():
        suffix = ".py" if name in {"adapter", "target"} else ".json"
        descriptor["path"] = "artifacts/" + name + suffix
    portable_raw = json_bytes(portable_bundle)
    report = {
        "schema_version": 1,
        "bundle_id": bundle["bundle_id"],
        "selected_record_id": selected,
        "bundle_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "materialized_bundle_sha256": hashlib.sha256(portable_raw).hexdigest(),
        "fixture_sha256": hashlib.sha256(fixture_raw).hexdigest(),
        "artifact_sha256": {name: descriptor["sha256"] for name, descriptor in bundle["artifacts"].items()},
        "closure_record_ids": [row["record_id"] for row in rows],
        "closure_basis": "bundle_attestation_not_independently_proven",
        "execution": "not_requested",
        "validation_status": "not_established",
        "expectation_authenticity": "not_independently_verified",
        "expected": expectation["expected"],
        "failed_observed": expectation["failed_observed"],
        "comparison": "not_run",
        "reproduced_failed_observation": None,
    }
    output.mkdir(mode=0o700)
    (output / "artifacts").mkdir(mode=0o700)
    write_exclusive(output / "source_bundle.json", manifest_raw, readonly=True)
    write_exclusive(output / "bundle.json", portable_raw, readonly=True)
    write_exclusive(output / "fixture.json", fixture_raw, readonly=True)
    for name, raw in artifacts.items():
        suffix = ".py" if name in {"adapter", "target"} else ".json"
        write_exclusive(output / "artifacts" / (name + suffix), raw, readonly=True)

    exit_code = 0
    if execute:
        try:
            adapter = types.ModuleType("_pinned_replay_adapter")
            adapter.__file__ = str(output.resolve() / "artifacts" / "adapter.py")
            # Compiling the already verified bytes avoids rereading mutable paths.
            # Redirect ordinary prints; no adapter exception message is logged.
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                exec(compile(artifacts["adapter"], adapter.__file__, "exec"), adapter.__dict__)
                require(callable(getattr(adapter, "replay", None)), "adapter must define replay(context)")
                result = adapter.replay(copy.deepcopy(fixture))
                validate_json_result(result)
                result_raw = json_bytes(result)
                result = parse_json(result_raw)
            report["execution"] = "completed"
            report["result"] = result
            matches = result_raw == json_bytes(expectation["expected"]["value"])
            reproduced = result_raw == json_bytes(expectation["failed_observed"]["value"])
            report["comparison"] = "matches_expected" if matches else "differs_from_expected"
            report["reproduced_failed_observation"] = reproduced
            exit_code = 0 if matches and not reproduced else 1
        except (KeyboardInterrupt, GeneratorExit) as error:
            # Preserve the interrupted attempt without exposing traceback text
            # or an exception message that may contain record values.
            report["execution"] = "interrupted"
            report["error_type"] = type(error).__name__
            exit_code = 130
        except (Exception, SystemExit) as error:
            report["execution"] = "error"
            report["error_type"] = type(error).__name__
            exit_code = 2
    write_exclusive(output / "report.json", json_bytes(report))
    return exit_code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bundle", required=True, type=Path, help="Pinned bundle JSON manifest")
    parser.add_argument("--record", required=True, help="Opaque record occurrence/version ID")
    parser.add_argument("--output", required=True, type=Path, help="New fixture directory outside the bundle")
    parser.add_argument("--execute", action="store_true", help="Run trusted pinned Python adapter locally; NOT a sandbox")
    args = parser.parse_args(argv)
    try:
        code = run(args.bundle, args.record, args.output, args.execute)
    except ReplayError as error:
        print(f"Replay rejected: {error}", file=sys.stderr)
        return 2
    except (OSError, RuntimeError, RecursionError):
        print("Replay failed: filesystem access or input structure error", file=sys.stderr)
        return 2
    print("Replay artifacts created; consult report.json for comparison and limitations.")
    return code


if __name__ == "__main__":
    sys.exit(main())
