# PTS agent workflow

This branch implements the user's agent-first rebuild. Read `CLAUDE.md`, then
`prompts/START_MODERNIZATION.md`. The foreground Claude Code conversation is the
coordinator. There is no Python Coordinator service, workflow engine, UI server,
or legacy campaign dependency on this branch.

The operating contract is `docs/TECHNICAL_REFERENCE.md`. Eight specialist definitions, one lead definition
and three core skills own the workflow. The retained third-party skill pack is
optional instruction content, not installed runtime plugins. Load only guidance
needed for the current task. Preserve its licenses and provenance.

Use only the approved Opus 4.7 configuration. Verify the actual session and worker
model before work; no fallback or cross-model routing. Stop affected model work
if the installed host cannot honor this restriction.

Preserve original sources, accepted decisions and historical evidence. Work from
explicitly approved sanitized source views and synthetic data. Raw customer rows,
credentials and protected source must not enter model context, logs or commits.
Never bypass a denied path or command through shell, copying, scripts or MCP.
Existing mainframe write/submit/delete denials remain effective. A configuration
flag or general request for autonomy does not override a runtime denial.

SMEs resolve business meaning and intended changes. Agents determine technical
classification, reuse, replacement names and target design. Never manufacture
SME answers. Use one versioned review workbook per process; ingest genuine replies
and batch only unresolved questions. No out-of-scope disposition.

Every business rule requires 100 distinct positive and 100 distinct negative
passing data cases. Technical operations receive appropriate contract tests.
Never relabel a rule, duplicate cases or weaken expectations to pass a gate.

Keep sources, rules, target mappings, cases and observed results linked by IDs,
versions and hashes. An unavailable result remains unverified. Reuse only compatible
versions and fresh evidence. The foreground coordinator alone publishes inventory.

Use disjoint program paths and at most the configured workers. Repair locally
within the configured budget; preserve failures and continue other independent
programs when a program is blocked. Do not add another orchestration layer.

Before publishing kit changes, run `python tools/check_kit.py` and independent
scoped review. Business-program changes also require their real focused and
affected integration tests. Configuration checks are not Claude-host or mainframe
acceptance. Keep private working files under ignored program/process directories
or `.implementation/`; do not publish them with the operating kit.
