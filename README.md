# PTS modernization agents

A Claude Code operating kit for VS Code: one foreground lead, eight specialists
and three core skills. Python implements logic and ETL now; a single migration
register tracks later Sparkflows replacement. Start with [START_HERE](START_HERE.md).

| Need | Reference |
|---|---|
| Full specification and execution stages | [Technical reference](docs/TECHNICAL_REFERENCE.md); [implementation plan](docs/IMPLEMENTATION_PLAN.md) |
| Agent/skill prompts and executable commands | [Application guide](docs/APP_MODERNIZATION_GUIDE.md); [goals and loops](prompts/GOAL_WORKFLOW.md) |
| SME decisions and record evidence | [Review workbook](examples/PTS_Modernization_Review_Template.xlsx); [workbook guide](docs/WORKBOOK_GUIDE.md) |
| Folder structure, initialization and memory | [Folder guide](docs/FOLDER_STRUCTURE.md); [memory index](knowledge/MEMORY.md) |
| Mainframe dependency/caller traversal | [Endevor OKF navigation and Db2 MCP/Zowe fallback](docs/ENDEVOR_NAVIGATION.md) |
| Future ETL flows, dependencies and commentary | [Single Sparkflows register](docs/SPARKFLOWS_MIGRATION.md) |
| Converted-logic deletion | [Safe rule removal](docs/RULE_REMOVAL.md) |
| Total inventory versus evidenced completion | [Read-only progress UI](docs/PROGRESS_UI.md) |
| Quality, independent audit and recorded checks | [Opus quality](docs/OPUS_QUALITY.md); [security review](docs/SECURITY_REVIEW.md); [kit evidence](docs/evidence.json) |
| Context reduction and optional Graphify | [Token efficiency](docs/TOKEN_EFFICIENCY.md) |
| UI research and standards | [Public-site design reference](docs/PUBLIC_SITE_DESIGN.md) |

This branch, `modernization/clean-agent-kit`, preserves the fifteen retained
instruction packages and licenses from `modernization-factory`; their upstream
runtimes are not installed. Ponytail is required for design/build/repair. The
previous branch/history remains intact; temporary REA research tooling is removed.

The supplied photo confirms `TSTSN.#RW477*`. Your existing Db2 MCP and Zowe CLI are
the intended access layer; live enumeration and workstation capability verification
remain necessary. The kit supplies configuration, templates, a fictional workbook/UI
demo and local evidence utilities; it does not establish real conversion, mainframe
parity, Claude-host operation, model equivalence or provider-token savings.
Sparkflows bindings are needed only for the later migration phase.

Run the synthetic regression suite with `python -m unittest discover -s tests -v`.
The [rule-validation example](examples/rule_validation/README.md) is runnable locally.
