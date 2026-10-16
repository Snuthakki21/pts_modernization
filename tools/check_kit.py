"""Offline integrity checks for the Claude Code kit; no model or remote calls."""
import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def check():
    errors = []

    def require(ok, message):
        if not ok:
            errors.append(message)

    config = read_json("config/project.json")
    settings = read_json(".claude/settings.json")
    pack = read_json(".claude/skill-pack.json")
    model = config["model"]["id"]
    require(settings["model"] == model, "Foreground model differs from project binding")
    require(settings["env"]["CLAUDE_CODE_SUBAGENT_MODEL"] == model,
            "Worker model differs from project binding")
    require(settings["env"]["CLAUDE_CODE_SUBAGENT_MODEL_FORCE"] == "1",
            "Worker model force setting missing")
    require(config["model"]["no_fallback"] is True, "Fallback must remain disabled")
    require(settings["permissions"]["defaultMode"] == "dontAsk",
            "Expected bounded no-prompt policy")
    require(settings.get("agent") == "pts-orchestrator", "Foreground lead not selected")
    trace = config.get("trace", {})
    require(trace.get("required") is True and trace.get("coverage") == "all_records"
            and trace.get("sampling_allowed") is False
            and trace.get("incomplete_trace_blocks_acceptance") is True,
            "Full per-record tracing must be required without sampling")
    require(config["validation"]["positive_cases_per_rule"] >= 100 and
            config["validation"]["negative_cases_per_rule"] >= 100,
            "Business-rule case minima below the acceptance requirement")

    agent_names = {"pts-orchestrator", "pts-design", "pts-frontend", "pts-backend",
                   "pts-qa", "pts-devops", "pts-analytics", "pts-audit", "pts-gap-analysis"}
    agent_files = list((ROOT / ".claude/agents").glob("*.md"))
    require({p.stem for p in agent_files} == agent_names, "Agent role set differs from contract")
    for path in agent_files:
        content = path.read_text(encoding="utf-8")
        require(content.startswith("---\n"), f"Missing frontmatter: {path.name}")
        head = content.split("---", 2)[1] if content.startswith("---") else ""
        require(re.search(rf"(?m)^name:\s*{re.escape(path.stem)}\s*$", head),
                f"Agent name mismatch: {path.name}")
        require(re.search(rf"(?m)^model:\s*{re.escape(model)}\s*$", head),
                f"Agent model mismatch: {path.name}")
        tools_line = re.search(r"(?m)^tools:\s*(.+)$", head)
        tools_text = tools_line.group(1) if tools_line else ""
        if path.stem == "pts-orchestrator":
            delegation = re.search(r"Agent\(([^)]+)\)", tools_text)
            allowed = {name.strip() for name in delegation.group(1).split(",")} if delegation else set()
            require(allowed == agent_names - {"pts-orchestrator"},
                    "Lead must delegate only to the eight specialists")
            require(re.search(r"\bSkill\b", tools_text), "Lead needs the Skill tool")
        else:
            require(not re.search(r"\b(?:Agent|Task)\b", tools_text),
                    f"Specialist must not delegate: {path.name}")
            if path.stem in {"pts-qa", "pts-design", "pts-gap-analysis"}:
                require(re.search(r"\bSkill\b", tools_text),
                        f"Skill-calling specialist needs the Skill tool: {path.name}")

    core = {"modernize-process", "validate-program", "consult-modernization"}
    require(set(pack["retained_skills"]) == core, "Core skill manifest mismatch")
    for name in core:
        path = ROOT / ".claude/skills" / name / "SKILL.md"
        require(path.is_file(), f"Missing core skill: {name}")
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            require(content.startswith(f"---\nname: {name}\n"), f"Skill metadata: {name}")
            require("[TODO" not in content, f"Unfinished skill: {name}")

    require(pack["runtime_installed"] is False and pack["permission_grants"] == [],
            "Instruction pack must not claim runtime installation or permissions")
    for package in pack["packages"]:
        for item in package["files"]:
            path = ROOT / item["path"]
            require(path.is_file(), f"Missing retained asset: {item['path']}")
            if path.is_file():
                data = path.read_bytes()
                require(hashlib.sha256(data).hexdigest() == item["sha256"],
                        f"Asset hash mismatch: {item['path']}")
                require(len(data) == item["bytes"], f"Asset length mismatch: {item['path']}")

    # Historical policy and license comparison is local, read-only Git inspection.
    base = "c6834d9b49c3524bf7d987e66d465b964d2805bb"
    try:
        old = json.loads(subprocess.check_output(
            ["git", "show", f"{base}:.claude/settings.json"], cwd=ROOT, text=True))
        require(set(old["permissions"]["deny"]) <= set(settings["permissions"]["deny"]),
                "Historical permission deny entries were removed")
        for package in pack["packages"]:
            for item in package["files"]:
                if item["path"].endswith("LICENSE.md"):
                    original = subprocess.check_output(
                        ["git", "show", f"{base}:{item['path']}"], cwd=ROOT)
                    require(original == (ROOT / item["path"]).read_bytes(),
                            f"License changed: {item['path']}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        errors.append("Historical commit unavailable: fetch branch history for preservation checks")

    require(not (ROOT / "workbench").exists(), "Retired workbench engine remains in clean tree")
    document_paths = [ROOT / name for name in (
        "AGENTS.md", "CLAUDE.md", "README.md", "START_HERE.md",
        "docs/TECHNICAL_REFERENCE.md", "prompts/START_MODERNIZATION.md",
        ".github/copilot-instructions.md",
        ".claude/skills/validate-program/references/mainframe.md")]
    document_paths += agent_files
    document_paths += [ROOT / ".claude/skills" / name / "SKILL.md" for name in core]
    document_paths += [ROOT / item["path"] for package in pack["packages"]
                       for item in package["files"] if item["path"].endswith("SKILL.md")]
    for path in document_paths:
        require(path.is_file(), f"Missing kit document: {path.relative_to(ROOT)}")
        if not path.is_file():
            continue
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            target = target.split("#", 1)[0]
            require((path.parent / target).exists(), f"Broken link in {path.relative_to(ROOT)}: {target}")
    return errors


if __name__ == "__main__":
    try:
        failures = check()
    except (OSError, KeyError, ValueError) as exc:
        failures = [f"Invalid kit artifact: {exc}"]
    print(json.dumps({"kit_integrity": "failed" if failures else "passed",
                      "errors": failures,
                      "runtime_validation": "not performed",
                      "mainframe_validation": "not performed"}, indent=2))
    raise SystemExit(bool(failures))
