"""Generate frozen source-derived cases and check every declared Python rule.

Standard-library local test utility, not a conversion engine or sandbox. Only load
reviewed, permitted Python artifacts. A passing unit data gate is not source
completeness, oracle authenticity, full trace, mainframe parity or app acceptance.
"""
import argparse
import ast
from collections import Counter
import hashlib
import importlib.abc
import importlib.util
import json
from pathlib import Path
import sys
import types


QUOTA = 100


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    def duplicate_safe(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("duplicate JSON key: " + key)
            out[key] = value
        return out
    value = json.loads(Path(path).read_text(), object_pairs_hook=duplicate_safe)
    canonical(value)
    return value


def resolve(root, value):
    path = (root / value).resolve()
    if Path(value).is_absolute() or not path.is_relative_to(root):
        raise ValueError("artifact path escape")
    return path


def artifact(root, ref):
    path = resolve(root, ref["path"])
    if digest(path.read_bytes()) != ref["sha256"]:
        raise ValueError("artifact hash mismatch: " + ref["path"])
    return path


class PinnedModules(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Scoped fresh imports of explicit sibling .py files; not a sandbox.

    Standard-library imports are supported. Relative/package and undeclared
    third-party imports require a separate reviewed adapter, not guessed paths.
    Existing modules with these names are restored even if loading fails.
    """
    def __init__(self, root, entry):
        self.entry_path = resolve(root, entry["path"])
        self.paths, self.code, trees = {}, {}, {}
        refs = [entry] + entry.get("dependencies", [])
        for ref in refs:
            path = resolve(root, ref["path"])
            data = path.read_bytes()
            if digest(data) != ref["sha256"]:
                raise ValueError("artifact hash mismatch: " + ref["path"])
            name = path.stem
            if (path.suffix != ".py" or path.parent != self.entry_path.parent
                    or not name.isidentifier() or name == "__init__"
                    or name in sys.stdlib_module_names or name in self.code):
                raise ValueError("unsupported Python import layout; use uniquely named sibling .py modules")
            self.paths[path] = name
            self.code[name] = compile(data, str(path), "exec")
            trees[path] = ast.parse(data)
        for path, tree in trees.items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        raise ValueError("unsupported relative import in " + path.name)
                    imports = [node.module]
                else:
                    continue
                for name in imports:
                    if name not in self.code and name.split(".", 1)[0] not in sys.stdlib_module_names:
                        raise ValueError("unsupported undeclared/package import: " + name)

    def find_spec(self, fullname, path=None, target=None):
        if fullname in self.code:
            return importlib.util.spec_from_loader(fullname, self)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        code = self.code[module.__name__]
        module.__file__ = code.co_filename
        exec(code, module.__dict__)

    def __enter__(self):
        self.previous = {name: sys.modules[name] for name in self.code if name in sys.modules}
        for name in self.code:
            sys.modules.pop(name, None)
        sys.meta_path.insert(0, self)
        try:
            self.entry = importlib.import_module(self.paths[self.entry_path])
            return self
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def __exit__(self, *exc):
        if self in sys.meta_path:
            sys.meta_path.remove(self)
        for name in self.code:
            sys.modules.pop(name, None)
        sys.modules.update(self.previous)

    def rule_code(self, root, rule):
        code = self.code[self.paths[resolve(root, rule["python_path"])]]
        matches = [value for value in code.co_consts if isinstance(value, types.CodeType)
                   and value.co_name == rule["python_symbol"]
                   and value.co_qualname == rule["python_symbol"]]
        if len(matches) != 1:
            raise ValueError("mapped Python symbol must have one top-level code definition")
        return matches[0]


def catalog(path, root=None):
    path = Path(path).resolve()
    root = Path(root).resolve() if root is not None else path.parent
    if not root.is_dir() or not path.is_relative_to(root):
        raise ValueError("catalog must be inside the existing artifact root")
    data = read_json(path)
    if data.get("schema_version") != 1 or not data.get("program_id"):
        raise ValueError("invalid catalog identity/version")
    source_refs = data.get("source_files", [])
    if not source_refs:
        raise ValueError("source fingerprints required")
    for ref in source_refs:
        artifact(root, ref)
    target = data["target"]
    oracle = data["oracle"]
    target_refs = [target] + target.get("dependencies", [])
    oracle_refs = [oracle] + oracle.get("dependencies", [])
    target_paths = {artifact(root, ref) for ref in target_refs}
    oracle_paths = {artifact(root, ref) for ref in oracle_refs}
    target_hashes = {ref["sha256"] for ref in target_refs}
    oracle_hashes = {ref["sha256"] for ref in oracle_refs}
    if target_paths & oracle_paths or target_hashes & oracle_hashes:
        raise ValueError("oracle must be independent of target artifacts")
    provenance = oracle.get("provenance", {})
    if provenance.get("kind") not in {"source_derived", "approved_specification", "verified_python_reference"} or not provenance.get("reference"):
        raise ValueError("independent expected-result provenance required")
    units = {}
    for unit in data.get("source_units", []):
        sid = unit["source_id"]
        if sid in units:
            raise ValueError("duplicate source ID")
        if unit["kind"] not in {"executable", "non_executable", "removed"}:
            raise ValueError("unresolved source kind")
        if unit["kind"] != "executable" and not unit.get("reason"):
            raise ValueError("source disposition reason required")
        if unit["kind"] == "removed" and not unit.get("decision_ref"):
            raise ValueError("removed behavior requires accepted decision reference")
        units[sid] = unit
    if not units:
        raise ValueError("source-unit inventory required")
    identifiers, covered = set(), set()
    for rule in data.get("rules", []):
        rid = rule["rule_id"]
        if rid in identifiers:
            raise ValueError("duplicate rule ID")
        identifiers.add(rid)
        if rule["kind"] not in {"business", "technical", "mixed"}:
            raise ValueError("unresolved rule classification")
        if not rule.get("positive_meaning") or not rule.get("negative_meaning"):
            raise ValueError("positive/negative meanings required")
        if not rule.get("distinction_fields") or not rule.get("required_coverage"):
            raise ValueError("meaningful fields and coverage classes required")
        refs = rule.get("source_ids", [])
        if not refs or any(s not in units or units[s]["kind"] != "executable" for s in refs):
            raise ValueError("rule source mapping invalid")
        covered.update(refs)
        code_path = resolve(root, rule["python_path"])
        if code_path not in target_paths:
            raise ValueError("mapped Python file is not pinned")
        tree = ast.parse(code_path.read_bytes())
        mapped = [node for node in tree.body
                  if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and node.name == rule["python_symbol"]]
        if not mapped:
            raise ValueError("mapped Python symbol missing")
        if len(mapped) != 1 or isinstance(mapped[0], ast.AsyncFunctionDef):
            raise ValueError("duplicate or async mapped Python symbols are unsupported")
    unmapped = {sid for sid, unit in units.items() if unit["kind"] == "executable"} - covered
    if unmapped:
        raise ValueError("unmapped executable source units: " + ", ".join(sorted(unmapped)))
    if not identifiers:
        raise ValueError("no executable rules; no unit data acceptance can be claimed")
    return root, data, digest(path.read_bytes())


def distinction(rule, inputs):
    values = []
    for field in rule["distinction_fields"]:
        value = inputs
        for part in field.split("."):
            if not isinstance(value, dict) or part not in value:
                raise ValueError("missing meaningful input field: " + field)
            value = value[part]
        values.append(value)
    return canonical(values)


def validate_case(rule, case):
    canonical(case)
    if not isinstance(case.get("case_id"), str) or not case["case_id"]:
        raise ValueError("case ID required")
    if case.get("category") not in {"positive", "negative"}:
        raise ValueError("invalid case category")
    if not isinstance(case.get("inputs"), dict) or "expected" not in case:
        raise ValueError("case inputs and frozen expected result required")
    if not isinstance(case.get("coverage_tags"), list) or any(not isinstance(tag, str) for tag in case["coverage_tags"]):
        raise ValueError("coverage tags required")
    return distinction(rule, case["inputs"])


def generate(path, max_candidates=10000, root=None):
    root, data, fingerprint = catalog(path, root)
    if max_candidates < 1:
        raise ValueError("positive candidate budget required")
    cases, summaries, global_ids = [], [], set()
    with PinnedModules(root, data["oracle"]) as modules:
        oracle = modules.entry
        for rule in data["rules"]:
            seen, tags, counts = set(), set(), Counter()
            duplicates, exhausted_budget = 0, False
            candidates = iter(oracle.generate_cases(rule, data.get("seed", 0)))
            for index, supplied in enumerate(candidates):
                if index >= max_candidates:
                    exhausted_budget = True
                    break
                case = dict(supplied)
                case["rule_id"] = rule["rule_id"]
                key = validate_case(rule, case)
                if key in seen:
                    duplicates += 1
                    continue
                if case["case_id"] in global_ids:
                    raise ValueError("duplicate case ID")
                seen.add(key); global_ids.add(case["case_id"])
                counts[case["category"]] += 1
                tags.update(case["coverage_tags"])
                cases.append(case)
            missing = sorted(set(rule["required_coverage"]) - tags)
            summaries.append({"rule_id": rule["rule_id"], "generated": {c: counts[c] for c in ("positive", "negative")},
                              "discarded_duplicates": duplicates, "missing_coverage": missing,
                              "candidate_budget_exhausted": exhausted_budget,
                              "meets_quota": all(counts[c] >= QUOTA for c in ("positive", "negative")) and not missing})
    # Detect changed artifacts even if trusted generator inadvertently edits them.
    _, _, after = catalog(path, root)
    if after != fingerprint:
        raise ValueError("catalog changed during generation")
    return {"schema_version": 1, "program_id": data["program_id"], "catalog_sha256": fingerprint,
            "oracle_provenance": data["oracle"]["provenance"], "cases": cases, "rules": summaries,
            "generation_gate_passed": all(row["meets_quota"] for row in summaries),
            "semantic_distinctness_independently_verified": False}


def run(path, frozen, root=None):
    root, data, fingerprint = catalog(path, root)
    canonical(frozen)
    if frozen.get("schema_version") != 1 or frozen.get("program_id") != data["program_id"] or frozen.get("catalog_sha256") != fingerprint:
        raise ValueError("case catalog fingerprint mismatch")
    rule_by_id = {r["rule_id"]: r for r in data["rules"]}
    ids, seen = set(), {rid: set() for rid in rule_by_id}
    for case in frozen["cases"]:
        rid = case.get("rule_id")
        if rid not in rule_by_id:
            raise ValueError("unknown rule in cases")
        key = validate_case(rule_by_id[rid], case)
        if case["case_id"] in ids:
            raise ValueError("duplicate case ID")
        if key in seen[rid]:
            raise ValueError("duplicate meaningful case inputs")
        seen[rid].add(key); ids.add(case["case_id"])
    counts = {rid: Counter() for rid in rule_by_id}
    tags = {rid: set() for rid in rule_by_id}
    results = []
    with PinnedModules(root, data["target"]) as modules:
        evaluate = getattr(modules.entry, data["target"].get("entrypoint", "evaluate"))
        for case in frozen["cases"]:
            rid, failures = case["rule_id"], []
            rule, calls = rule_by_id[rid], []
            expected_code = modules.rule_code(root, rule)

            def observe(frame, event, arg):
                if event == "call" and frame.f_code is expected_code:
                    calls.append(True)

            previous = sys.getprofile()
            observed = None
            try:
                sys.setprofile(observe)
                # Keep target mutation from corrupting frozen fixture/expected objects.
                returned = evaluate(rid, json.loads(canonical(case["inputs"])))
                observed = json.loads(canonical(returned))
                if not isinstance(observed, dict) or "actual" not in observed:
                    raise ValueError("target must return actual and rule_events")
                if canonical(observed["actual"]) != canonical(case["expected"]):
                    failures.append("actual differs from independent expectation")
                events = observed.get("rule_events", [])
                if not isinstance(events, list) or not any(isinstance(e, dict) and e.get("rule_id") == rid and e.get("category") == case["category"] for e in events):
                    failures.append("expected rule outcome not observed")
            except Exception as exc:
                failures.append("execution error: " + type(exc).__name__)
            finally:
                sys.setprofile(previous)
            if not calls:
                failures.append("mapped symbol not executed")
            passed = not failures
            if passed:
                counts[rid][case["category"]] += 1
                tags[rid].update(case["coverage_tags"])
            results.append({"case_id": case["case_id"], "rule_id": rid, "category": case["category"],
                            "passed": passed, "mapped_symbol_calls": len(calls), "observed": observed,
                            "failures": failures})
    summaries = []
    for rid, rule in rule_by_id.items():
        missing = sorted(set(rule["required_coverage"]) - tags[rid])
        passing = {c: counts[rid][c] for c in ("positive", "negative")}
        summaries.append({"rule_id": rid, "kind": rule["kind"], "passing": passing,
                          "missing_coverage": missing, "meets_quota": all(n >= QUOTA for n in passing.values()) and not missing})
    _, _, after = catalog(path, root)
    if after != fingerprint:
        raise ValueError("catalog changed during execution")
    return {"schema_version": 1, "program_id": data["program_id"], "catalog_sha256": fingerprint,
            "cases_sha256": digest(canonical(frozen).encode()), "rules": summaries, "cases": results,
            "unit_data_gate_passed": all(row["meets_quota"] for row in summaries) and all(row["passed"] for row in results),
            "program_acceptance_established": False,
            "limitations": ["Declared source inventory completeness and oracle provenance require independent review.",
                            "Meaningful fields/coverage tags and adapter event truth require source-based audit.",
                            "This unit check does not establish mainframe parity, full-record tracing or integration."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["generate", "run"])
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--root", type=Path,
                        help="artifact root; defaults to the catalog's parent directory")
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-candidates", type=int, default=10000)
    parser.add_argument("--allow-local-execution", action="store_true", help="Reviewed local Python only; this is not a sandbox or permission override")
    args = parser.parse_args()
    try:
        if not args.allow_local_execution:
            raise ValueError("reviewed local execution must be explicitly enabled")
        if args.output.exists():
            raise ValueError("output already exists; preserve previous evidence")
        if args.action == "run" and args.cases is None:
            raise ValueError("run requires --cases")
        result = generate(args.catalog, args.max_candidates, args.root) if args.action == "generate" else run(args.catalog, read_json(args.cases), args.root)
        serialized = json.dumps(result, indent=2, allow_nan=False) + "\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as stream:
            stream.write(serialized)
        key = "generation_gate_passed" if args.action == "generate" else "unit_data_gate_passed"
        print(json.dumps({key: result[key], "rules": len(result["rules"]), "cases": len(result["cases"])}))
        return 0 if result[key] else 2
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ImportError, SyntaxError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
