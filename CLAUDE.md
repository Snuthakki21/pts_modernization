# PTS modernization

@AGENTS.md
@knowledge/MEMORY.md

Act as the foreground lead; do not spawn another lead. Start with
`config/project.json`, applicable inventory rows and `knowledge/handoff.json`.
Load only relevant source spans, decisions and sections of the guides below.

| Task | Entry point |
|---|---|
| Process/portfolio conversion | `/modernize-process`; [start prompt](prompts/START_MODERNIZATION.md) |
| Existing-program validation | `/validate-program` with program ID and pinned source/target versions |
| Architecture, delivery or cost decision | `/consult-modernization` |
| Phase inputs, commands and handoffs | [Application guide](docs/APP_MODERNIZATION_GUIDE.md) |
| Workstation setup or missing local state | [START_HERE](START_HERE.md); [folder guide](docs/FOLDER_STRUCTURE.md) |
| Acceptance details | [Technical reference](docs/TECHNICAL_REFERENCE.md), especially Sections 7 (ETL), 8 (tests) and 9 (record trace) |
| Goals, resume and monitoring | [Claude Code workflow](docs/CLAUDE_CODE_WORKFLOW.md); [goal prompts](prompts/GOAL_WORKFLOW.md); `.claude/loop.md` |
| Mainframe traversal or missing objects | [Endevor navigation](docs/ENDEVOR_NAVIGATION.md); route technical discovery to gap analysis/DevOps |
| Context, optional lookup tools and fresh indexes | [Token efficiency](docs/TOKEN_EFFICIENCY.md) |
| Safe behavior removal | [Rule removal](docs/RULE_REMOVAL.md) |

Load specialists only when needed. The lead owns the single current process review
workbook, inventory, durable memory and [Sparkflows register](docs/SPARKFLOWS_MIGRATION.md).
Workers return scoped artifacts and concise findings. Render only the register's
marked factual block; preserve authored cards/commentary. Use
[progress export](docs/PROGRESS_UI.md) after evidenced inventory updates.
