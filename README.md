# PTS modernization agents

An agent-and-skill operating kit for Claude Code in VS Code. The foreground
conversation coordinates eight specialist roles and three core skills; no conversion
engine or orchestration service is included. Current business logic and simple ETL
run in Python. Source/test-linked code comments identify simple ETL for later
Sparkflows migration; Sparkflows setup and execution are deferred.
Use [the single Sparkflows migration register](docs/SPARKFLOWS_MIGRATION.md) for
flows to create, artifact links, dependencies, running commentary and the exact
per-consumer switch/rollback/Python-retirement plan as real programs are analyzed.

Start with [START_HERE.md](START_HERE.md). The full contract is
[docs/TECHNICAL_REFERENCE.md](docs/TECHNICAL_REFERENCE.md). The editable SME and
evidence workbook is [examples/PTS_Modernization_Review_Template.xlsx](examples/PTS_Modernization_Review_Template.xlsx).
Recorded kit checks and execution limits are in [docs/evidence.json](docs/evidence.json).
Use [the Claude Code workflow](docs/CLAUDE_CODE_WORKFLOW.md) and
[goal/loop prompts](prompts/GOAL_WORKFLOW.md) for bounded autonomous work and
read-only monitoring. Ponytail is required for minimal complete design and code.
Use [Endevor navigation](docs/ENDEVOR_NAVIGATION.md) for source dependency/caller
traversal in Open Knowledge Format. Mainframe views live in `Endevor/`; the local
Markdown bundle is generated from an explicit approved-source manifest.
Unanswered OKF questions use the documented permitted Db2 MCP/Zowe fallback.
The agents apply [five context techniques](docs/TOKEN_EFFICIENCY.md#five-context-techniques-in-the-existing-workflow)
while retaining complete evidence and unresolved outcomes.

This clean branch retains the existing 15 optional instruction packages and their
licenses from `modernization-factory`. It does not install their upstream runtimes.
The branch is `modernization/clean-agent-kit`; earlier branches and history are
preserved. Your existing Db2 MCP server and Zowe CLI are the intended access layer,
not a request to build another connector. They are user-reported configured and
still require workstation capability verification here. Model, source, Python,
evidence-store and permission bindings are current readiness gates. Sparkflows
bindings become gates only for the later migration phase.
The supplied photo confirms listing prefix `TSTSN.#RW477*`; live discovery is pending.
Use [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) for the staged execution
roadmap, ownership, parallel work and acceptance checks.

Use [APP_MODERNIZATION_GUIDE.md](docs/APP_MODERNIZATION_GUIDE.md) for the full
application workflow, exact agent/skill prompts and executable local commands.
Five small Python utilities check compatibility receipts, generate and execute
100 positive plus 100 negative cases per executable rule, replay captured failures,
render factual migration tables, and regression-score instruction scenarios.
They use the standard library and require reviewed program-specific inputs.
Run `python -m unittest discover -s tests -v` for their synthetic regression suite.
The [rule-validation example](examples/rule_validation/README.md) is runnable locally.

A fresh checkout includes [the memory index](knowledge/MEMORY.md) and ten tracked
starter templates. Run `python tools/init_workspace.py --root .` for missing local
state; it preserves existing decisions and repair budgets. See
[FOLDER_STRUCTURE.md](docs/FOLDER_STRUCTURE.md) for every delivered and generated path.
[OPUS_QUALITY.md](docs/OPUS_QUALITY.md) defines effective model/effort checks and
measured quality gates. [RULE_REMOVAL.md](docs/RULE_REMOVAL.md) gives the one-request
workflow for safely removing converted logic without damaging other consumers.

The requested [progress UI](docs/PROGRESS_UI.md) shows unique inventory totals,
converted versus completed programs, current evidence gates and blocked work.
It imports sanitized snapshots and includes an explicitly fictional demo.
[SECURITY_REVIEW.md](docs/SECURITY_REVIEW.md) separates remediation, QA and
independent adversarial audit. [TOKEN_EFFICIENCY.md](docs/TOKEN_EFFICIENCY.md)
documents the installed optional Graphify parser, pinned dependency lock and
measured navigation-output reduction. [PUBLIC_SITE_DESIGN.md](docs/PUBLIC_SITE_DESIGN.md)
retains the sourced visual reference; the temporary REA research tool has been removed.
