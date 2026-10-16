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
