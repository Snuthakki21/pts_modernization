# Claude Code implementation entrypoint

Read [AGENTS.md](AGENTS.md), then the host roles in the single shared
[prompts/START_MODERNIZATION.md](prompts/START_MODERNIZATION.md) workflow.
Claude Code may run in the organization-approved VS Code extension. **Claude has
no MCP servers.** Do not install, register or invoke one, use a Copilot tool as a
Claude proxy, or tunnel MCP/remote access through a shell or HTTP wrapper.
[examples/claude-mcp.json](examples/claude-mcp.json) is deliberately empty; no
Claude MCP setup is required.

Claude reads approved source exports, process notes and evidence from the local
workspace. It owns local analysis, lineage interpretation, rules, development,
unit and randomized testing, independent adversarial review, and reporting.
GitHub Copilot in VS Code only discovers and retrieves requested source or
metadata through already approved MCP connections into the designated folder.

Use `python -m workbench.runner agent PROCESS_ID --workspace WORKSPACE` to read
the current task and evidence paths. For missing information, prepare a bounded
request with `agent --request-file REQUEST_JSON` and give the generated retrieval
prompt to the user to paste into Copilot. Do not guess missing objects or request
credentials. When the user says Continue, run the same process with
`agent --continue`; validate its exact request-bound inbox before resuming.
NOT_FOUND/AMBIGUOUS returns stay checkpoints, not automatic repeat prompts.
For an INDETERMINATE local command, inspect current state using a fresh command
before deciding any new mutation; never delete its marker or replay it silently.
Submit analysis using `agent --analysis-file ANALYSIS_JSON`; after tested adapter
changes use `agent --refresh` and read the fresh task before submitting.
These are local-file operations through the existing Coordinator. With the UI
running, its Coordinator consumes the local command inbox; never start a second
writer, connect Claude to an MCP server, or bypass the ledger and evidence gates.

Preserve the [technical contract](docs/TECHNICAL_REFERENCE.md), immutable source,
one human review packet and real reviewer attribution. Run
`python -m workbench.layout --workspace WORKSPACE` before and after local work.
A plan, model assertion or synthetic test cannot establish mainframe parity.
