"""Offline, public structured-decision rubric; never calls or verifies a model.

Examples (run from the repository root):
    python tools/check_instruction_responses.py --fingerprint
    python tools/check_instruction_responses.py --template response-template.json
    python tools/check_instruction_responses.py responses.json --receipt receipt.json
    python tools/check_instruction_responses.py --synthetic-fixture synthetic.json
    python tools/check_instruction_responses.py synthetic.json

Give the template, tests/instruction_cases.json, and the exact pinned instruction
files to the approved real Opus session manually. Ask for its own decisions and
rationales. A human records the user-reported model attestation and preserves the
pre-run fingerprint. Do not regenerate metadata on old responses. A receipt only
scores declared fields; a human must audit the narrative and observed behavior.
The synthetic-fixture command copies the public answer key to test this utility.
It is not a model run or evidence that any model follows these instructions.
Template, synthetic-fixture and receipt destinations must be new files. Existing
files, including hardlink or symlink aliases, are never overwritten.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SUITE_PATH = "tests/instruction_cases.json"
REQUIRED_INSTRUCTIONS = (
    "AGENTS.md", "CLAUDE.md", "README.md", "START_HERE.md",
    "docs/TECHNICAL_REFERENCE.md", "docs/SPARKFLOWS_MIGRATION.md",
    "docs/WORKBOOK_GUIDE.md", "docs/IMPLEMENTATION_PLAN.md",
    "prompts/START_MODERNIZATION.md", ".github/copilot-instructions.md",
    "config/project.json", "config/source-reference.json",
    "knowledge/MEMORY.md",
    ".claude/settings.json", ".claude/skill-pack.json",
    ".claude/skills/modernize-process/SKILL.md",
    ".claude/skills/validate-program/SKILL.md",
    ".claude/skills/consult-modernization/SKILL.md",
    ".claude/skills/validate-program/references/mainframe.md",
)
APPROVED_MODEL = "claude-opus-4-7"


def model_binding(root):
    """Use the explicit project deployment; declarations do not verify routing."""
    model = read_json(root / "config/project.json")["model"]
    identity, provider = model.get("id"), model.get("provider")
    if (model.get("approved_family") != "opus-4.7" or model.get("no_fallback") is not True
            or not isinstance(identity, str) or not identity.strip()
            or not isinstance(provider, str) or not provider.strip()):
        raise ValueError("Explicit Opus 4.7 model/provider and no-fallback policy required")
    if identity != APPROVED_MODEL:
        reference = model.get("deployment_mapping_reference")
        if (identity in {"opus", "opusplan", "default", "best", "fable", "sonnet", "haiku"}
                or identity.startswith("claude-")
                or provider == "anthropic"
                or model.get("provider_binding_confirmed") is not True
                or not isinstance(reference, str) or not reference.strip()):
            raise ValueError("Nonstandard deployment needs an explicit confirmed Opus 4.7 mapping reference")
    return identity, provider


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=_unique_object)


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _string_list(value):
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def load_suite(root=ROOT):
    """Validate the public rubric itself, so malformed expected data fails closed."""
    suite = read_json(root / SUITE_PATH)
    if not isinstance(suite, dict) or not all(
            isinstance(suite.get(key), str) and suite[key].strip()
            for key in ("suite_id", "suite_version", "response_contract")):
        raise ValueError("Invalid suite metadata")
    cases = suite.get("cases")
    if not isinstance(cases, list) or not 6 <= len(cases) <= 12:
        raise ValueError("Expected 6 to 12 public synthetic scenarios")
    case_ids = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Case must be an object")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in case_ids:
            raise ValueError("Missing or duplicate rubric case ID")
        case_ids.add(case_id)
        if not isinstance(case.get("prompt"), str) or not case["prompt"].strip():
            raise ValueError(f"{case_id}: missing prompt")
        fields = case.get("decision_fields")
        if not isinstance(fields, list) or not fields:
            raise ValueError(f"{case_id}: missing decision fields")
        field_ids = set()
        for field in fields:
            if not isinstance(field, dict):
                raise ValueError(f"{case_id}: invalid decision field")
            field_id, choices = field.get("id"), field.get("choices")
            if (not isinstance(field_id, str) or not field_id or field_id in field_ids
                    or not _string_list(choices) or len(set(choices)) != len(choices)
                    or len(choices) < 2 or field.get("expected") not in choices):
                raise ValueError(f"{case_id}: invalid field, choices or expected value")
            field_ids.add(field_id)
        options, expected = case.get("action_options"), case.get("expected_actions")
        if (not _string_list(options) or not _string_list(expected) or not expected
                or len(set(options)) != len(options)
                or len(set(expected)) != len(expected)
                or not set(expected) <= set(options)):
            raise ValueError(f"{case_id}: invalid action rubric")
    return suite


def instruction_snapshot(root=ROOT):
    """Hash actual instruction bytes, paths, and all discovered role/skill guidance.

    Mandatory paths cannot disappear silently. Discovery also detects new role,
    skill, prompt or documentation files. License texts are not instructions.
    The ordered path/hash map is included in every evaluation receipt.
    """
    paths = set(REQUIRED_INSTRUCTIONS)
    for pattern in (".claude/**/*.md", ".github/*instructions*.md",
                    "docs/**/*.md", "prompts/**/*.md", "knowledge/**/*.md",
                    "templates/**/*.md", "templates/**/*.json"):
        paths.update(path.relative_to(root).as_posix() for path in root.glob(pattern)
                     if path.name != "LICENSE.md" and path.is_file())
    files = {name: _digest((root / name).read_bytes()) for name in sorted(paths)}
    reference = (root / "docs/TECHNICAL_REFERENCE.md").read_text(encoding="utf-8")
    match = re.search(r"(?m)^Version\s+([^\s·]+)", reference)
    if not match:
        raise ValueError("Technical reference must declare a Version")
    return {
        "instruction_version": match.group(1),
        "instruction_fingerprint": _digest(_canonical(files)),
        "instruction_files": files,
    }


def response_metadata(root=ROOT, synthetic=False):
    suite = load_suite(root)
    snapshot = instruction_snapshot(root)
    model, provider = model_binding(root)
    return {
        "suite_id": suite["suite_id"],
        "suite_version": suite["suite_version"],
        "suite_fingerprint": _digest((root / SUITE_PATH).read_bytes()),
        "instruction_version": snapshot["instruction_version"],
        "instruction_fingerprint": snapshot["instruction_fingerprint"],
        "response_kind": "synthetic_fixture" if synthetic else "model_response",
        "model_attestation": {
            "status": "not_applicable_synthetic" if synthetic else "user_reported",
            "provider": "none" if synthetic else provider,
            "foreground_model": "none" if synthetic else model,
            "worker_models": [],
            "fallback_used": False,
            "attested_by": "synthetic_fixture_generator" if synthetic else "REQUIRED: human run recorder",
            "attested_at": (datetime.now(timezone.utc).isoformat() if synthetic
                            else "REQUIRED: ISO-8601 run attestation time with timezone"),
        },
    }


def make_response(root=ROOT, synthetic=False):
    suite = load_suite(root)
    responses = []
    for case in suite["cases"]:
        responses.append({
            "case_id": case["case_id"],
            "decisions": {field["id"]: field["expected"] if synthetic else None
                          for field in case["decision_fields"]},
            "actions": case["expected_actions"] if synthetic else [],
            "rationale": ("SYNTHETIC FIXTURE: copied from the public rubric; no model was invoked."
                          if synthetic else "REQUIRED: independent explanation and evidence needs"),
        })
    return {"metadata": response_metadata(root, synthetic), "responses": responses}


def _validate_attestation(metadata, errors, root):
    model, provider = model_binding(root)
    kind = metadata.get("response_kind")
    if kind not in ("model_response", "synthetic_fixture"):
        errors.append("metadata.response_kind must be model_response or synthetic_fixture")
    attestation = metadata.get("model_attestation")
    if not isinstance(attestation, dict):
        errors.append("metadata.model_attestation must be an object")
        return
    synthetic = kind == "synthetic_fixture"
    expected = {
        "status": "not_applicable_synthetic" if synthetic else "user_reported",
        "provider": "none" if synthetic else provider,
        "foreground_model": "none" if synthetic else model,
        "fallback_used": False,
    }
    for key, value in expected.items():
        if attestation.get(key) != value or (key == "fallback_used"
                                           and attestation.get(key) is not False):
            errors.append(f"metadata.model_attestation.{key} must be {value!r}")
    workers = attestation.get("worker_models")
    if (not _string_list(workers)
            or any(worker != model for worker in workers)
            or (synthetic and workers)):
        errors.append("Worker attestation must list only the approved model; synthetic fixtures have none")
    recorder = attestation.get("attested_by")
    if not isinstance(recorder, str) or not recorder.strip() or recorder.startswith("REQUIRED:"):
        errors.append("metadata.model_attestation.attested_by must identify the human run recorder")
    try:
        timestamp = attestation["attested_at"]
        if not isinstance(timestamp, str):
            raise ValueError("not text")
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone missing")
    except (KeyError, ValueError):
        errors.append("metadata.model_attestation.attested_at must be an ISO-8601 timestamp with timezone")


def evaluate(response, root=ROOT):
    """Return a receipt; exact declared-field matching is not semantic verification."""
    suite = load_suite(root)
    snapshot = instruction_snapshot(root)
    suite_hash = _digest((root / SUITE_PATH).read_bytes())
    errors = []
    if not isinstance(response, dict):
        errors.append("Response document must be an object")
        response = {}
    metadata = response.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("metadata must be an object")
        metadata = {}
    required_metadata = {
        "suite_id": suite["suite_id"], "suite_version": suite["suite_version"],
        "suite_fingerprint": suite_hash,
        "instruction_version": snapshot["instruction_version"],
        "instruction_fingerprint": snapshot["instruction_fingerprint"],
    }
    for key, expected in required_metadata.items():
        if metadata.get(key) != expected:
            errors.append(f"metadata.{key} is missing or stale; do not relabel old responses with a new fingerprint")
    _validate_attestation(metadata, errors, root)

    supplied = response.get("responses")
    if not isinstance(supplied, list):
        errors.append("responses must be an array")
        supplied = []
    expected_ids = {case["case_id"] for case in suite["cases"]}
    by_id = {}
    for index, item in enumerate(supplied):
        if not isinstance(item, dict) or not isinstance(item.get("case_id"), str):
            errors.append(f"responses[{index}] requires a case_id string")
            continue
        case_id = item["case_id"]
        if case_id in by_id:
            errors.append(f"Duplicate response case: {case_id}")
            continue
        by_id[case_id] = item
        if case_id not in expected_ids:
            errors.append(f"Extra response case: {case_id}")

    total = sum(len(case["decision_fields"]) + 1 for case in suite["cases"])
    matched = 0
    case_results = []
    for case in suite["cases"]:
        case_id = case["case_id"]
        case_errors = []
        item = by_id.get(case_id)
        if item is None:
            case_errors.append("Missing response case")
            item = {}
        decisions = item.get("decisions")
        if not isinstance(decisions, dict):
            case_errors.append("decisions must be an object")
            decisions = {}
        required_fields = {field["id"] for field in case["decision_fields"]}
        for extra in sorted(set(decisions) - required_fields):
            case_errors.append(f"Extra decision field: {extra}")
        for field in case["decision_fields"]:
            field_id = field["id"]
            actual = decisions.get(field_id)
            if field_id not in decisions:
                case_errors.append(f"Missing decision field: {field_id}")
            elif not isinstance(actual, str) or actual not in field["choices"]:
                case_errors.append(f"Invalid decision enum for {field_id}: {actual!r}")
            elif actual != field["expected"]:
                case_errors.append(f"Wrong decision for {field_id}: expected {field['expected']!r}, received {actual!r}")
            else:
                matched += 1
        actions = item.get("actions")
        if not _string_list(actions):
            case_errors.append("actions must be an array of action ID strings")
        else:
            if len(actions) != len(set(actions)):
                case_errors.append("Duplicate action IDs")
            invalid = set(actions) - set(case["action_options"])
            if invalid:
                case_errors.append(f"Unknown action IDs: {', '.join(sorted(invalid))}")
            if set(actions) != set(case["expected_actions"]):
                case_errors.append("Selected action IDs differ from the required public rubric")
            elif len(actions) == len(set(actions)):
                matched += 1
        rationale = item.get("rationale")
        if (not isinstance(rationale, str) or not rationale.strip()
                or rationale.startswith("REQUIRED:")):
            case_errors.append("rationale must contain an explanation for human audit")
        if (metadata.get("response_kind") == "model_response"
                and isinstance(rationale, str) and rationale.startswith("SYNTHETIC FIXTURE:")):
            case_errors.append("Synthetic fixture marker cannot be submitted as a model response")
        case_results.append({"case_id": case_id,
                             "structured_check": "failed" if case_errors else "passed",
                             "errors": case_errors})
        errors.extend(f"{case_id}: {message}" for message in case_errors)

    passed = not errors
    synthetic = metadata.get("response_kind") == "synthetic_fixture"
    return {
        "receipt_schema_version": 1,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        **required_metadata,
        "instruction_files": snapshot["instruction_files"],
        "submitted_metadata": metadata,
        "response_fingerprint": _digest(_canonical(response)),
        "structured_rubric": "passed" if passed else "failed",
        "score": {"matched_checks": matched, "total_checks": total,
                  "fraction": round(matched / total, 6),
                  "scope": "exact decision enums plus one exact action-set check per case"},
        "synthetic_fixture_check": ("passed" if passed else "failed") if synthetic else "not_performed",
        "model_response_check": ("not_performed" if synthetic else
                                 "structured_fields_passed_human_audit_required" if passed else
                                 "structured_fields_failed"),
        "model_attestation_verified": False,
        "runtime_model_evaluation": "not_performed_by_this_utility",
        "semantic_instruction_compliance": "not_verified",
        "human_narrative_and_behavior_audit": "required",
        "limitations": [
            "Public expected fields can be copied; this is not a hidden benchmark.",
            "No model/API is invoked, and model identity/origin attestation is user-reported only.",
            "Rationales are checked only for presence, never keyword-scored or semantically certified.",
            "A structured pass is not runtime, mainframe, or program acceptance.",
        ],
        "cases": case_results,
        "errors": errors,
    }


def _write_json(path, value):
    # Serialize before creating anything; exclusive creation also rejects aliases
    # and a destination created by another process after an existence check.
    serialized = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(serialized)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("responses", nargs="?", type=Path, help="supplied JSON responses")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--fingerprint", action="store_true", help="print current instruction and suite pins")
    modes.add_argument("--template", type=Path, help="create a new unfilled manual-run response template")
    modes.add_argument("--synthetic-fixture", type=Path, help="create a new explicit evaluator-only answer-key fixture")
    parser.add_argument("--receipt", type=Path, help="also create a new evaluation receipt file")
    args = parser.parse_args(argv)
    generating = args.fingerprint or args.template or args.synthetic_fixture
    if (generating and args.responses) or (generating and args.receipt):
        parser.error("generation modes cannot also evaluate responses or write a receipt")
    if not generating and not args.responses:
        parser.error("provide responses, --fingerprint, --template or --synthetic-fixture")
    try:
        if args.fingerprint:
            suite = load_suite()
            result = {"suite_id": suite["suite_id"], "suite_version": suite["suite_version"],
                      "suite_fingerprint": _digest((ROOT / SUITE_PATH).read_bytes()),
                      **instruction_snapshot()}
        elif args.template or args.synthetic_fixture:
            destination = args.template or args.synthetic_fixture
            fixture = bool(args.synthetic_fixture)
            _write_json(destination, make_response(synthetic=fixture))
            result = {"written": str(destination),
                      "response_kind": "synthetic_fixture" if fixture else "unfilled_model_response_template",
                      "model_invoked": False}
        else:
            if args.receipt and args.receipt.resolve() == args.responses.resolve():
                raise ValueError("Receipt path must not overwrite supplied responses")
            result = evaluate(read_json(args.responses))
            if args.receipt:
                _write_json(args.receipt, result)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"structured_rubric": "failed", "errors": [str(exc)],
                          "runtime_model_evaluation": "not_performed_by_this_utility"}, indent=2))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return int(result.get("structured_rubric") == "failed")


if __name__ == "__main__":
    sys.exit(main())
