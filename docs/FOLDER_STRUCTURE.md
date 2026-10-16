# Delivered files and local workspace

The branch contains the reusable operating kit and empty starter templates.
Private application source, actual conversions, runtime state and connection
credentials are populated in the approved workstation. No completed conversion or
model-quality result is implied by the presence of these files.

## Tracked operating kit

| Path | Delivered purpose |
|---|---|
| `CLAUDE.md`, `AGENTS.md` | Main Claude instructions and shared operating contract |
| `knowledge/MEMORY.md` | Compact stable memory index; points to canonical state without duplicating it |
| `README.md`, `START_HERE.md` | Entry points and workstation startup |
| `prompts/START_MODERNIZATION.md` | Start/resume prompt |
| `docs/CLAUDE_CODE_WORKFLOW.md`, `prompts/GOAL_WORKFLOW.md`, `.claude/loop.md` | Verified native feature guidance, bounded goal prompts and read-only loop default |
| `docs/GRAPHIFY_INDEX_EVIDENCE.json` | Dated source-hash and parser receipt for the refreshed public Python navigation index |
| `.claude/agents/` | Nine definitions: orchestrator, design, frontend, backend, QA, DevOps, analytics, audit and gap analysis |
| `.claude/skills/modernize-process/` | Application/process modernization procedure |
| `.claude/skills/validate-program/` | Program validation procedure and mainframe reference |
| `.claude/skills/consult-modernization/` | Evidence-based clarification and technical decision procedure |
| `.claude/skill-pack.json`, other `.claude/skills/` | Fifteen retained optional instruction packages with provenance and applicable licenses; not installed runtimes |
| `.claude/settings.json` | Approved model/delegation binding and preserved permission policy |
| `config/project.json`, `config/source-reference.json` | Non-secret shared bindings, explicit unavailable capabilities and screenshot transcription |
| `config/preservation-baseline.json` | Pinned historical permission and license baseline for full and shallow/archive checkouts |
| `knowledge/mainframe-catalog.json` | Existing source discovery reference |
| `.vscode/extensions.json` | Claude Code extension recommendation; no installation or authentication |
| `.github/copilot-instructions.md` | Repository metadata directing work to the approved Claude workflow |
| `.env.example`, `.gitignore`, `.gitattributes` | Non-secret local-binding example, private-state exclusions and file handling |
| `docs/TECHNICAL_REFERENCE.md` | Full implementation and acceptance contract |
| `docs/APP_MODERNIZATION_GUIDE.md`, `docs/IMPLEMENTATION_PLAN.md` | Concrete commands, assignments, stages and gates |
| `docs/OPUS_QUALITY.md` | Workstation verification and held-out quality evaluation; no unmeasured model-equivalence claim |
| `docs/RULE_REMOVAL.md` | Narrow reversible removal of selected converted behavior, with dependency checks and evidence |
| `docs/PROGRESS_UI.md`, `ui/` | Sanitized inventory snapshot contract and read-only progress interface |
| `PRODUCT.md`, `docs/PROGRESS_DESIGN.md` | User requirements and the dashboard's development-only design direction |
| `DESIGN.md`, `.impeccable/design.json`, `ui/design-qa.md` | Extracted implementation tokens and explicit blocked browser QA continuation |
| `docs/design/wells-fargo-reference-20261016.jpg` | Dated public-page visual reference, separate from tracker verification |
| `docs/SECURITY_REVIEW.md` | Version-bound remediation, independent QA and adversarial audit gates |
| `docs/SECURITY_EVIDENCE.json` | Dated scoped findings, fixes, independent checks and reviewed file hashes |
| `docs/TOKEN_EFFICIENCY.md`, `config/token-tools*` | Reviewed optional lookup integration and hash-locked dependencies |
| `docs/PUBLIC_SITE_DESIGN.md` | Sourced public visual references; temporary research tooling removed |
| `docs/licenses/` | New optional tool licenses, provenance and available dependency audit receipts |
| `docs/SPARKFLOWS_MIGRATION.md` | Single migration document with generated facts and preserved commentary |
| `docs/WORKBOOK_GUIDE.md`, `examples/PTS_Modernization_Review_Template.xlsx` | SME/evidence workbook instructions and clearly fictional example template |
| `docs/evidence.json` | Recorded kit verification and explicit execution limits |
| `tools/init_workspace.py` | Missing-file creation from templates, without overwriting ongoing state |
| `tools/compatibility_profile.py`, `tools/rule_cases.py` | Compatibility receipts and all-rule case generation/execution |
| `tools/replay_record.py`, `tools/render_migration.py` | Captured-record replay and factual migration document generation |
| `tools/check_instruction_responses.py`, `tools/check_kit.py` | Instruction rubric scoring and offline kit integrity |
| `tools/progress_snapshot.py`, `tools/graphify_lookup.py` | Sanitized progress export and optional source-linked Python symbol navigation |
| `tests/`, `examples/rule_validation/` | Synthetic regression suite, public instruction scenarios and runnable rule example |
| `templates/state/` | Empty inventory, decisions, handoff and retrieval-index templates |
| `templates/program/`, `templates/process/` | Empty program metadata/analysis and process templates |

Use the exact role assignments in the [application guide](APP_MODERNIZATION_GUIDE.md).
Native per-agent memory folders are not needed: the lead owns one canonical
decision/handoff store, and workers return scoped updates.

## First-use initialization

Run from the checkout root after the local Python command has been bound in the
approved workstation. Commands remain subject to effective host permissions;
include a missing binding in the one setup handoff instead of using an alternate
route around a denial.

```bash
python tools/init_workspace.py --root .
```

This creates only `inventory.json` and the three canonical `knowledge/*.json`
state files. They are ignored by Git. It creates no programs or processes,
populates no model/tool capabilities and assigns no acceptance or repair budget.
The lead records verified bindings and the configured task allowance when real
work is assigned. The tracked [memory entry point](../knowledge/MEMORY.md)
explains how to save and resume.

After qualified program/process identities are known, replace both placeholders
below with supplied identifiers and run:

```bash
python tools/init_workspace.py --root . --program '<PROGRAM_ID>' --process '<PROCESS_ID>'
```

Either option is optional and repeatable. Identifiers contain 1–64 ASCII letters,
digits, underscores or hyphens, begin with a letter/digit, and cannot be reserved
Windows names or differ only by case within a batch. A short ID is not proof of
source identity: populate `program.json` with the qualified library/member/version
and approved source-manifest reference. Only the lead adds evidenced program rows
and actual consumer relationships to the inventory/process manifest.

The program scaffold contains `program.json`, plus `analysis/source-map.json`,
`rules.json`, `questions.json` and `design.json`. The process scaffold contains
`process.json`. Every list starts empty, every unknown binding remains null and
all analysis remains unpopulated. These are starter containers, not a complete
rule catalog, fixture set, compatibility proof or executable process. The
compatibility utility adds its unresolved profile to the existing design file.

Repeated invocation preserves existing file bytes, decisions and remaining repair
allowances. It skips compatible existing files and creates only missing ones.
Malformed/incompatible existing state, different identities, symlinks, hardlinks
or path collisions block preflight; review them rather than replacing them with
empty templates. This structural check does not validate application correctness.
All planned paths are checked before any write. An I/O interruption can still
leave partial creation: exit code 2 and the JSON report identify created files and
the path requiring review. Inspect that path before resuming; never delete live
state merely to make initialization pass.

## Local application layout

| Path | Owner and contents |
|---|---|
| `inventory.json` | Lead; canonical component/version registry, actual consumers and separate acceptance dimensions |
| `knowledge/decisions.json` | Lead; accepted attributed decisions with provenance/applicability/supersession |
| `knowledge/handoff.json` | Lead; current work, versions, checks, blockers, pending tasks, remaining budgets and next action |
| `knowledge/local-index.json` | Lead; rebuildable retrieval pointers and hash matches, never independent acceptance |
| `programs/<id>/program.json` | Qualified program identity and source-manifest reference |
| `programs/<id>/source/` | Protected original snapshots or references; existing read protections remain |
| `programs/<id>/analysis/` | Approved sanitized views, source ledger/map, classified rules, questions, design and compact compatibility profile |
| `programs/<id>/target/` | Minimal Python, SQL and eligible ETL comments |
| `programs/<id>/tests/` | Independent oracle, generators, cases, fixtures and actual executable tests |
| `programs/<id>/runs/<run-id>/` | Immutable results, reconciliation, trace/effect evidence, replay bundles and run handoff |
| `processes/<id>/process.json` | Actual ordered/conditional steps, pinned program versions, parameters and dependencies |
| `processes/<id>/review.xlsx` | One current SME workbook generated from approved analysis; preserve issued revisions |
| `processes/<id>/integration/runs/<run-id>/` | Process-level integration, recovery and affected-consumer evidence |
| `.implementation/` | Private workstation receipts and local kit/instruction test runs |

Program and process containers are created only for explicitly supplied IDs.
Their functional directories start empty until useful artifacts are produced.
One canonical program serves all consuming processes; the initializer does not
copy implementations or infer dependencies. It does not copy the fictional
workbook into a real process: the lead/frontend produces that process's approved
projection when analysis exists. Source maps, rules, cases, results and record
events must retain versioned links back to the original mainframe evidence.

Existing Db2 MCP and Zowe configuration stay in their approved workstation
locations. This kit intentionally does not populate `.mcp.json`, Zowe credentials,
`.claude/settings.local.json`, customer data or raw mainframe artifacts. The
extension recommendation and retained instruction packages do not install plugins.
Follow [START_HERE.md](../START_HERE.md) for one-time capability verification.
