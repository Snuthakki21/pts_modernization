"""Offline integrity checks for the Claude Code kit; no model or remote calls."""
import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "c6834d9b49c3524bf7d987e66d465b964d2805bb"
BASELINE_SHA256 = "be76b12acc7fe058622f6047dfd784e49e7d81eb5fe489023f3ee7354282c0c9"
RETAINED_PACKAGES = {
    "superpowers", "matt-pocock", "ecc", "karpathy-guidelines", "anthropic-testing",
    "ponytail", "ui-ux-pro-max", "caveman", "agent-engineering", "taste",
    "understand-anything", "impeccable", "headroom", "i-have-adhd", "oh-my-claudecode",
}
REQUIRED_FILES = (
    "AGENTS.md", "CLAUDE.md", "README.md", "START_HERE.md", "PRODUCT.md", "DESIGN.md", ".env.example",
    ".impeccable/design.json",
    ".gitignore", ".gitattributes", ".vscode/extensions.json",
    ".github/copilot-instructions.md", ".claude/settings.json", ".claude/skill-pack.json", ".claude/loop.md",
    "config/project.json", "config/source-reference.json", "config/preservation-baseline.json",
    "config/token-tools.json", "config/token-tools.requirements.in", "config/token-tools.requirements.txt",
    "docs/TECHNICAL_REFERENCE.md", "docs/APP_MODERNIZATION_GUIDE.md",
    "docs/SPARKFLOWS_MIGRATION.md", "docs/IMPLEMENTATION_PLAN.md", "docs/WORKBOOK_GUIDE.md",
    "docs/FOLDER_STRUCTURE.md", "docs/OPUS_QUALITY.md", "docs/RULE_REMOVAL.md", "docs/evidence.json",
    "docs/CLAUDE_CODE_WORKFLOW.md", "docs/GRAPHIFY_INDEX_EVIDENCE.json",
    "docs/PROGRESS_UI.md", "docs/PROGRESS_DESIGN.md", "docs/PUBLIC_SITE_DESIGN.md",
    "docs/SECURITY_REVIEW.md", "docs/SECURITY_EVIDENCE.json", "docs/TOKEN_EFFICIENCY.md", "docs/TOKEN_TOOLS_EVIDENCE.json",
    "docs/design/wells-fargo-reference-20261016.jpg",
    "docs/licenses/graphify/LICENSE", "docs/licenses/graphify/LICENSE-MIT", "docs/licenses/graphify/NOTICE",
    "knowledge/MEMORY.md", "knowledge/mainframe-catalog.json", "prompts/START_MODERNIZATION.md",
    "prompts/GOAL_WORKFLOW.md",
    "examples/PTS_Modernization_Review_Template.xlsx", "examples/rule_validation/README.md",
    "examples/rule_validation/catalog.json", "examples/rule_validation/demo_oracle.py",
    "examples/rule_validation/demo_target.py", "examples/rule_validation/synthetic_rules.cob",
    "examples/progress-demo.json",
    "tools/check_kit.py", "tools/check_instruction_responses.py", "tools/compatibility_profile.py",
    "tools/init_workspace.py", "tools/render_migration.py", "tools/replay_record.py", "tools/rule_cases.py",
    "tools/progress_snapshot.py", "tools/graphify_lookup.py",
    "tests/instruction_cases.json", "tests/test_kit_integrity.py", "tests/test_init_workspace.py",
    "tests/test_compatibility_profile.py", "tests/test_instruction_responses.py",
    "tests/test_render_migration.py", "tests/test_replay_record.py", "tests/test_rule_cases.py",
    "tests/test_progress_snapshot.py", "tests/test_graphify_lookup.py",
    "templates/state/inventory.json", "templates/state/decisions.json",
    "templates/state/handoff.json", "templates/state/local-index.json",
    "templates/program/program.json", "templates/program/source-map.json", "templates/program/rules.json",
    "templates/program/questions.json", "templates/program/design.json", "templates/process/process.json",
    ".claude/skills/validate-program/references/mainframe.md",
    "ui/AGENTS.md", "ui/README.md", "ui/design-qa.md", "ui/index.html", "ui/package.json", "ui/package-lock.json",
    "ui/vite.config.mjs", "ui/src/App.jsx", "ui/src/main.jsx", "ui/src/ProgramDetail.jsx",
    "ui/src/styles.css", "ui/src/snapshot.mjs", "ui/src/demo-progress.json",
    "ui/scripts/prepare-sites-build.mjs", "ui/worker/index.js",
    "ui/tests/sites-worker.test.mjs", "ui/tests/snapshot.test.mjs", "ui/.openai/hosting.json",
)
TEMPORARY_RESEARCH_PATHS = (
    "tools/rea", "docs/licenses/rea", ".implementation/rea-runtime",
    ".implementation/rea-source", ".implementation/rea-browsers", ".implementation/rea-tmp",
)


def read_json(path, root=ROOT):
    return json.loads((root / path).read_text(encoding="utf-8"))


def audit(root=ROOT):
    """Check a clone or source archive without requiring historical Git objects."""
    root = Path(root).resolve()
    errors = []
    basis = "not_verified"

    def require(ok, message):
        if not ok:
            errors.append(message)

    for name in REQUIRED_FILES:
        require((root / name).is_file(), f"Missing required kit file: {name}")
    # REA was authorized only for temporary design research. Keep the sourced
    # brief and historical receipts, not an installation or redistributed code.
    for name in TEMPORARY_RESEARCH_PATHS:
        path = root / name
        require(not (path.exists() or path.is_symlink()),
                f"Temporary REA research distribution remains: {name}")
    try:
        config = read_json("config/project.json", root)
        settings = read_json(".claude/settings.json", root)
        pack = read_json(".claude/skill-pack.json", root)
    except (OSError, KeyError, ValueError) as exc:
        errors.append(f"Invalid kit artifact: {exc}")
        return report(errors, basis)
    model = config["model"]["id"]
    binding = config["model"]
    provider = binding.get("provider")
    require(binding.get("approved_family") == "opus-4.7" and
            isinstance(model, str) and bool(model.strip()) and
            isinstance(provider, str) and bool(provider.strip()),
            "Only the approved Opus 4.7 binding is allowed")
    if model != "claude-opus-4-7":
        reference = binding.get("deployment_mapping_reference")
        require(isinstance(model, str) and
                model not in {"opus", "opusplan", "default", "best", "fable", "sonnet", "haiku"} and
                not model.startswith("claude-") and provider != "anthropic" and
                binding.get("provider_binding_confirmed") is True and
                isinstance(reference, str) and bool(reference.strip()),
                "Only an approved Opus 4.7 deployment with a confirmed mapping reference is allowed")
    quality = config.get("quality", {})
    environment = settings.get("env", {})
    require(quality.get("effort") == "xhigh" and settings.get("effortLevel") == quality.get("effort"),
            "Foreground effort must match the approved xhigh project binding")
    require(environment.get("CLAUDE_CODE_EFFORT_LEVEL", "xhigh") == "xhigh",
            "Explicit environment effort differs from the approved xhigh binding")
    require(environment.get("ANTHROPIC_MODEL", model) == model,
            "Explicit environment model differs from project binding")
    require(environment.get("ANTHROPIC_DEFAULT_HAIKU_MODEL") == model,
            "Auxiliary small-fast model must match the approved Opus 4.7 project binding")
    require(environment.get("CLAUDE_CODE_GOAL_CHECKIN_MINUTES") == "0",
            "Automatic goal check-ins must remain disabled")
    require(not settings.get("fallbackModel"), "Explicit fallback models must remain disabled")
    require(settings.get("ultracode", False) is False,
            "Ultracode must remain disabled to preserve the worker limit")
    workers = config.get("execution", {}).get("max_workers")
    require(type(workers) is int and 1 <= workers <= 2 and
            settings.get("env", {}).get("CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS") == str(workers),
            "Worker concurrency must match the bounded project limit")
    require(settings["model"] == model, "Foreground model differs from project binding")
    require(settings["env"]["CLAUDE_CODE_SUBAGENT_MODEL"] == model,
            "Worker model differs from project binding")
    require(settings["env"]["CLAUDE_CODE_SUBAGENT_MODEL_FORCE"] == "1",
            "Worker model force setting missing")
    require(config["model"]["no_fallback"] is True, "Fallback must remain disabled")
    require(settings["permissions"]["defaultMode"] == "dontAsk",
            "Expected bounded no-prompt policy")
    require({"Read(//**/programs/*/source/**)", "Read(//**/sources/**)",
             "Read(//**/*.private.json)", "Read(//**/programs/*/runs/*/private/**)",
             "Read(//**/processes/*/integration/runs/*/private/**)",
             "Read(//**/processes/*/runs/*/private/**)"} <= set(settings["permissions"]["deny"]),
            "Program-source and private-evidence deny entries were removed")
    require(settings.get("agent") == "pts-orchestrator", "Foreground lead not selected")
    trace = config.get("trace", {})
    require(trace.get("required") is True and trace.get("coverage") == "all_records"
            and trace.get("sampling_allowed") is False
            and trace.get("incomplete_trace_blocks_acceptance") is True,
            "Full per-record tracing must be required without sampling")
    require(config["validation"]["positive_cases_per_rule"] >= 100 and
            config["validation"]["negative_cases_per_rule"] >= 100,
            "Executable-rule case minima below the acceptance requirement")
    require(config["validation"].get("rule_scope") == "all_executable",
            "Case minima must cover business, technical and mixed executable rules")

    agent_names = {"pts-orchestrator", "pts-design", "pts-frontend", "pts-backend",
                   "pts-qa", "pts-devops", "pts-analytics", "pts-audit", "pts-gap-analysis"}
    agent_files = list((root / ".claude/agents").glob("*.md"))
    require({p.stem for p in agent_files} == agent_names, "Agent role set differs from contract")
    for path in agent_files:
        content = path.read_text(encoding="utf-8")
        frontmatter = re.match(r"\A---\n(.*?)\n---[ \t]*(?:\n|\Z)", content, re.DOTALL)
        require(frontmatter is not None, f"Missing or unclosed frontmatter: {path.name}")
        head = frontmatter.group(1) if frontmatter else ""
        description = re.search(r"(?m)^description:[ \t]*([^\r\n]*)$", head)
        description_text = description.group(1).strip() if description else ""
        if description_text.startswith(("|", ">")):
            block = []
            for line in head[description.end():].splitlines():
                if line and not line[0].isspace():
                    break
                block.append(line)
            description_text = "\n".join(block).strip()
        require(description_text not in {"", '""', "''", "null", "~"} and
                not description_text.startswith("#"),
                f"Agent description must be nonempty: {path.name}")
        require(re.search(rf"(?m)^name:\s*{re.escape(path.stem)}\s*$", head),
                f"Agent name mismatch: {path.name}")
        require(re.search(rf"(?m)^model:\s*{re.escape(model)}\s*$", head),
                f"Agent model mismatch: {path.name}")
        require(re.search(r"(?m)^effort:\s*xhigh\s*$", head), f"Agent effort mismatch: {path.name}")
        tools_line = re.search(r"(?m)^tools:\s*(.+)$", head)
        tools_text = tools_line.group(1) if tools_line else ""
        if path.stem == "pts-orchestrator":
            delegation = re.search(r"Agent\(([^)]+)\)", tools_text)
            allowed = {name.strip() for name in delegation.group(1).split(",")} if delegation else set()
            require(allowed == agent_names - {"pts-orchestrator"},
                    "Lead must delegate only to the eight specialists")
            require(re.search(r"\bSkill\b", tools_text), "Lead needs the Skill tool")
            require(all(re.search(rf"\b{name}\b", tools_text) for name in
                        ("CronCreate", "CronList", "CronDelete", "ScheduleWakeup")),
                    "Lead needs the documented native monitoring tools")
        else:
            require(not re.search(r"\b(?:Agent|Task)\b", tools_text),
                    f"Specialist must not delegate: {path.name}")
            require(not re.search(r"\b(?:CronCreate|CronList|CronDelete|ScheduleWakeup)\b", tools_text),
                    f"Specialist must not schedule work: {path.name}")
            if path.stem in {"pts-qa", "pts-design", "pts-gap-analysis"}:
                require(re.search(r"\bSkill\b", tools_text),
                        f"Skill-calling specialist needs the Skill tool: {path.name}")

    core = {"modernize-process", "validate-program", "consult-modernization"}
    require(set(pack["retained_skills"]) == core, "Core skill manifest mismatch")
    for name in core:
        path = root / ".claude/skills" / name / "SKILL.md"
        require(path.is_file(), f"Missing core skill: {name}")
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            require(content.startswith(f"---\nname: {name}\n"), f"Skill metadata: {name}")
            require("[TODO" not in content, f"Unfinished skill: {name}")

    require(pack["runtime_installed"] is False and pack["permission_grants"] == [],
            "Instruction pack must not claim runtime installation or permissions")
    require({package.get("name") for package in pack["packages"]} == RETAINED_PACKAGES
            and len(pack["packages"]) == len(RETAINED_PACKAGES), "Retained package set differs from the preserved kit")
    for package in pack["packages"]:
        expected_skill = f".claude/skills/{package['name']}/SKILL.md"
        require(expected_skill in {item["path"] for item in package["files"]},
                f"Missing retained skill manifest entry: {expected_skill}")
        for item in package["files"]:
            path = root / item["path"]
            if not path.resolve().is_relative_to(root):
                errors.append(f"Retained asset escapes kit: {item['path']}")
                continue
            require(path.is_file(), f"Missing retained asset: {item['path']}")
            if path.is_file():
                data = path.read_bytes()
                require(hashlib.sha256(data).hexdigest() == item["sha256"],
                        f"Asset hash mismatch: {item['path']}")
                require(len(data) == item["bytes"], f"Asset length mismatch: {item['path']}")

    # New optional tools keep their own license inventory, separate from the
    # historical instruction-pack preservation snapshot.
    try:
        graphify_licenses = read_json("config/token-tools.json", root)["selected"]["license_files"]
        expected_license_paths = {
            "docs/licenses/graphify/LICENSE", "docs/licenses/graphify/LICENSE-MIT", "docs/licenses/graphify/NOTICE",
        }
        require(set(graphify_licenses) == expected_license_paths, "Graphify license inventory differs from contract")
        for name in expected_license_paths:
            path = root / name
            require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == graphify_licenses.get(name),
                    f"Graphify license hash mismatch or missing: {name}")
    except (OSError, KeyError, ValueError, TypeError) as exc:
        errors.append(f"Invalid Graphify license inventory: {exc}")

    # A pinned, historical snapshot keeps preservation checks valid in archives
    # and shallow clones. Available Git objects are an additional comparison.
    try:
        baseline_data = (root / "config/preservation-baseline.json").read_bytes()
        if hashlib.sha256(baseline_data).hexdigest() != BASELINE_SHA256:
            raise ValueError("preservation baseline hash mismatch")
        baseline = json.loads(baseline_data)
        if baseline.get("base_commit") != BASE_COMMIT or baseline.get("schema_version") != 1:
            raise ValueError("preservation baseline identity mismatch")
        basis = "pinned_baseline_only"
        require(set(baseline["permissions_deny"]) <= set(settings["permissions"]["deny"]),
                "Historical permission deny entries were removed")
        for name, expected_hash in baseline["licenses"].items():
            path = root / name
            require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash,
                    f"License changed or missing: {name}")
        if (root / ".git").exists():
            try:
                original = subprocess.run(["git", "show", f"{BASE_COMMIT}:.claude/settings.json"],
                                          cwd=root, capture_output=True, check=False)
            except FileNotFoundError:
                original = None
            if original is not None and original.returncode == 0:
                basis = "git_history_and_pinned_baseline"
                old = json.loads(original.stdout)
                require(old["permissions"]["deny"] == baseline["permissions_deny"],
                        "Historical Git permission entries differ from pinned baseline")
                for name, expected_hash in baseline["licenses"].items():
                    old_license = subprocess.run(["git", "show", f"{BASE_COMMIT}:{name}"],
                                                 cwd=root, capture_output=True, check=False)
                    require(old_license.returncode == 0 and
                            hashlib.sha256(old_license.stdout).hexdigest() == expected_hash,
                            f"Historical Git license differs from pinned baseline: {name}")
    except (OSError, KeyError, ValueError) as exc:
        errors.append(f"Invalid preservation baseline: {exc}")

    require(not (root / "workbench").exists(), "Retired workbench engine remains in clean tree")
    claude = root / "CLAUDE.md"
    if claude.is_file():
        content = claude.read_text(encoding="utf-8")
        require(re.search(r"(?m)^@AGENTS\.md\s*$", content), "Root CLAUDE.md requires the AGENTS import")
        require(re.search(r"(?m)^@knowledge/MEMORY\.md\s*$", content),
                "Root CLAUDE.md requires the shared memory import")
    document_paths = [root / name for name in REQUIRED_FILES if name.endswith(".md")]
    document_paths += agent_files
    document_paths += [root / ".claude/skills" / name / "SKILL.md" for name in core]
    document_paths += [root / item["path"] for package in pack["packages"]
                       for item in package["files"] if item["path"].endswith("SKILL.md")]
    for path in document_paths:
        require(path.is_file(), f"Missing kit document: {path.relative_to(root)}")
        if not path.is_file():
            continue
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            target = target.split("#", 1)[0]
            require((path.parent / target).exists(), f"Broken link in {path.relative_to(root)}: {target}")
    return report(errors, basis)


def report(errors, basis):
    return {"kit_integrity": "failed" if errors else "passed", "errors": errors,
            "preservation_basis": basis, "runtime_validation": "not performed",
            "mainframe_validation": "not performed"}


def check():
    """Keep the original error-list interface for existing local callers."""
    return audit(ROOT)["errors"]


if __name__ == "__main__":
    try:
        result = audit()
    except (OSError, KeyError, ValueError) as exc:
        result = report([f"Invalid kit artifact: {exc}"], "not_verified")
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result["errors"]))
