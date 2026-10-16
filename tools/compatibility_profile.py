"""Initialize/check a per-program compatibility evidence contract; never run tests.

Only caller-selected approved sanitized source paths and synthetic artifacts may
be supplied. This tool does not discover sources, infer COBOL semantics, certify
receipt authenticity, or replace independent source/runtime review.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile


DOMAINS = ("numeric", "characters", "layouts", "initialization", "dates",
           "database", "ordering", "errors")
SEMANTIC_FIELDS = ("applicability", "behavior", "source_refs", "runtime_settings",
                   "fixture_refs")
SCOPE = ("Artifact structure, hashes and linked test receipts only; "
         "tests not executed and receipt authenticity not assessed.")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def semantic_digest(entry):
    """Hash the complete semantic contract, excluding its proof reference."""
    payload = {key: entry.get(key) for key in SEMANTIC_FIELDS}
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("utf-8"))


def relative_file(root, value, must_exist=True):
    if (not isinstance(value, str) or not value or "\\" in value
            or ":" in value or PurePosixPath(value).is_absolute()
            or any(part in (".", "..", "") for part in value.split("/"))):
        raise ValueError("paths must be explicit relative paths inside --root")
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"path escapes --root: {value}")
    if must_exist and not path.is_file():
        raise ValueError(f"not a file: {value}")
    return path


def parse_json(content):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"non-JSON number: {value}")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("JSON numbers must be finite")
        return number

    return json.loads(content, object_pairs_hook=unique_object,
                      parse_constant=invalid_constant, parse_float=finite_float)


def load_json(path):
    return parse_json(path.read_text(encoding="utf-8"))


def object_value(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def check_program(design, program):
    if not program.strip():
        raise ValueError("--program must be nonempty")
    object_value(design, "design")
    if "program_id" in design and design["program_id"] != program:
        raise ValueError("design program_id mismatch")


def profile_value(design, program):
    check_program(design, program)
    profile = object_value(design.get("compatibility"), "compatibility")
    if type(profile.get("schema_version")) is not int or profile["schema_version"] != 1:
        raise ValueError("compatibility schema_version must be 1")
    if profile.get("program_id") != program:
        raise ValueError("compatibility program_id mismatch")
    return profile


def hashed_file(root, ref, label):
    object_value(ref, label)
    expected = ref.get("sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError(f"{label} needs a lowercase SHA-256")
    path = relative_file(root, ref.get("path"))
    data = path.read_bytes()
    if sha256(data) != expected:
        raise ValueError(f"sha256 mismatch: {ref['path']}")
    return data


def initialize(root, design_path, program, sources):
    original = design_path.read_bytes() if design_path.exists() else None
    design = parse_json(original) if original is not None else {}
    check_program(design, program)
    if "compatibility" in design:
        raise ValueError("compatibility already exists; refusing to overwrite it")
    fingerprints = []
    for source in sources:
        path = relative_file(root, source)
        if source in {ref["path"] for ref in fingerprints}:
            raise ValueError(f"duplicate source path: {source}")
        if path == design_path or (design_path.exists() and path.samefile(design_path)):
            raise ValueError("design cannot also be a source")
        fingerprints.append({"path": source, "sha256": sha256(path.read_bytes())})
    design["compatibility"] = {
        "schema_version": 1,
        "program_id": program,
        "source_fingerprints": fingerprints,
        "semantics": {domain: {
            "applicability": "unknown", "behavior": "", "source_refs": [],
            "runtime_settings": {}, "fixture_refs": [], "proof": None,
        } for domain in DOMAINS},
    }
    updated = (json.dumps(design, indent=2, allow_nan=False) + "\n").encode("utf-8")
    design_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=design_path.parent, prefix=f".{design_path.name}.", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        if original is not None and design_path.exists():
            os.chmod(temporary, stat.S_IMODE(design_path.stat().st_mode))
        current = design_path.read_bytes() if design_path.exists() else None
        if current != original:
            raise ValueError("design changed during initialization; retry against current decisions")
        os.replace(temporary, design_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def check_profile(root, design, program):
    """Return evidence-contract errors; a clean receipt is not runtime acceptance."""
    profile = profile_value(design, program)
    errors = []
    sources = {}
    fingerprints = profile.get("source_fingerprints")
    if not isinstance(fingerprints, list) or not fingerprints:
        errors.append("source_fingerprints must be a nonempty list")
        fingerprints = []
    for ref in fingerprints:
        try:
            data = hashed_file(root, ref, "source_fingerprints entry")
            if ref["path"] in sources:
                raise ValueError(f"duplicate source path: {ref['path']}")
            sources[ref["path"]] = (ref["sha256"], len(data.splitlines()))
        except (ValueError, OSError) as exc:
            errors.append(str(exc))
    semantics = object_value(profile.get("semantics"), "semantics")
    if set(semantics) != set(DOMAINS):
        errors.append("semantics must contain exactly: " + ", ".join(DOMAINS))
    for domain in DOMAINS:
        try:
            entry = object_value(semantics.get(domain), domain)
            check_entry(root, entry, domain, sources, fingerprints, program)
        except (ValueError, OSError) as exc:
            errors.append(f"{domain}: {exc}")
    return errors


def check_entry(root, entry, domain, sources, fingerprints, program):
    applicability = entry.get("applicability")
    if applicability not in ("applicable", "not_applicable"):
        raise ValueError("applicability is unknown or invalid; semantics are unresolved")
    behavior = entry.get("behavior")
    if not isinstance(behavior, str) or not behavior.strip():
        raise ValueError("behavior must state resolved behavior or a not-applicable reason")
    if behavior.strip().lower() in {"unknown", "unverified", "todo", "tbd", "n/a", "none"}:
        raise ValueError("behavior is an unresolved placeholder")
    object_value(entry.get("runtime_settings"), "runtime_settings")
    source_refs = entry.get("source_refs")
    if not isinstance(source_refs, list) or not source_refs:
        raise ValueError("source_refs must ground the behavior/reason in source evidence")
    for ref in source_refs:
        object_value(ref, "source_ref")
        source = ref.get("path")
        if not isinstance(source, str) or source not in sources:
            raise ValueError("source_ref path must match current source_fingerprints")
        start, end = ref.get("start_line"), ref.get("end_line")
        if (type(start) is not int or type(end) is not int
                or not 1 <= start <= end <= sources[source][1]):
            raise ValueError(f"invalid source line span: {source}")
    fixtures = entry.get("fixture_refs")
    if not isinstance(fixtures, list):
        raise ValueError("fixture_refs must be a list")
    if applicability == "not_applicable":
        if fixtures or entry.get("proof") is not None:
            raise ValueError("not_applicable requires empty fixture_refs and null proof")
        return
    if not fixtures:
        raise ValueError("applicable semantics need hashed fixture_refs")
    fixture_paths = set()
    source_hashes = {fingerprint for fingerprint, _ in sources.values()}
    for ref in fixtures:
        hashed_file(root, ref, "fixture_ref")
        if ref["path"] in fixture_paths:
            raise ValueError(f"duplicate fixture path: {ref['path']}")
        if ref["path"] in sources or ref["sha256"] in source_hashes:
            raise ValueError("source bytes cannot serve as a test fixture")
        fixture_paths.add(ref["path"])
    proof_ref = entry.get("proof")
    proof_bytes = hashed_file(root, proof_ref, "proof")
    proof = object_value(parse_json(proof_bytes), "proof content")
    if type(proof.get("schema_version")) is not int or proof["schema_version"] != 1:
        raise ValueError("proof schema_version must be 1")
    if proof.get("program_id") != program or proof.get("domain") != domain:
        raise ValueError("proof program_id/domain mismatch")
    expected_digest = semantic_digest(entry)
    if proof.get("semantic_sha256") != expected_digest:
        raise ValueError(f"proof semantic_sha256 mismatch; expected {expected_digest}")
    if proof.get("source_fingerprints") != fingerprints:
        raise ValueError("proof source_fingerprints mismatch")
    tests = proof.get("tests")
    if not isinstance(tests, list) or not tests:
        raise ValueError("proof needs nonempty executed test receipts")
    ids, covered = set(), set()
    for test in tests:
        object_value(test, "test receipt")
        test_id = test.get("id")
        if not isinstance(test_id, str) or not test_id.strip() or test_id in ids:
            raise ValueError("test receipt IDs must be nonempty and unique")
        if test.get("status") != "passed":
            raise ValueError(f"test receipt must be passed: {test_id}")
        fixture = test.get("fixture_path")
        if not isinstance(fixture, str) or fixture not in fixture_paths:
            raise ValueError(f"test receipt has an unbound fixture: {test_id}")
        ids.add(test_id)
        covered.add(fixture)
    if covered != fixture_paths:
        raise ValueError("proof must cover every fixture_ref")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "check", "digest"):
        sub = commands.add_parser(command)
        sub.add_argument("--root", type=Path, required=True,
                         help="project root; every artifact path is relative to it")
        sub.add_argument("--design", required=True, help="relative design.json path")
        sub.add_argument("--program", required=True)
        if command == "init":
            sub.add_argument("--source", action="append", required=True,
                             help="explicit approved sanitized source path; repeatable")
        elif command == "digest":
            sub.add_argument("--domain", choices=DOMAINS, required=True)
    args = parser.parse_args(argv)
    result = {"compatibility": "unverified", "errors": [], "validation_scope": SCOPE}
    try:
        root = args.root.resolve()
        if not root.is_dir():
            raise ValueError("--root must be an existing directory")
        path = relative_file(root, args.design, must_exist=args.command != "init")
        if args.command == "init":
            initialize(root, path, args.program, args.source)
            result["initialized"] = True
        else:
            design = load_json(path)
            if args.command == "digest":
                profile = profile_value(design, args.program)
                semantics = object_value(profile.get("semantics"), "semantics")
                entry = object_value(semantics.get(args.domain), args.domain)
                result.update({"domain": args.domain, "semantic_sha256": semantic_digest(entry)})
            else:
                result["errors"] = check_profile(root, design, args.program)
                if not result["errors"]:
                    result["compatibility"] = "verified"
    except (OSError, ValueError) as exc:
        result["errors"] = [str(exc)]
    print(json.dumps(result, indent=2))
    return int(bool(result["errors"]))


if __name__ == "__main__":
    sys.exit(main())
