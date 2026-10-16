# PTS agent workflow

This branch implements the user's agent-first rebuild. Read `CLAUDE.md`, then
`prompts/START_MODERNIZATION.md`. The foreground Claude Code conversation is the
coordinator. There is no Python Coordinator service, workflow engine or legacy
campaign dependency. The requested progress UI is a read-only view of exported
inventory; its local preview does not orchestrate conversions.

The operating contract is `docs/TECHNICAL_REFERENCE.md`. Eight specialist definitions, one lead definition
and three core skills own the workflow. The retained third-party skill pack is
instruction content, not installed runtime plugins. Ponytail is required for
design, implementation and repair; load other guidance only when needed.
Preserve its licenses and provenance.
The curated `knowledge/MEMORY.md` indexes durable state. Initialize missing state
from tracked templates with `tools/init_workspace.py`; preserve existing decisions,
handoffs and exhausted budgets. Use `docs/FOLDER_STRUCTURE.md` for exact paths.

Use only the approved Opus 4.7 configuration. Verify the actual session and worker
model before work; no fallback or cross-model routing. Stop affected model work
if the installed host cannot honor this restriction.
Use the explicit `xhigh` quality profile and observed evaluation procedure in
`docs/OPUS_QUALITY.md`. Configuration alone cannot establish 5.5-level performance.

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

Every retained or replaced executable rule requires 100 distinct positive and
100 distinct negative passing data cases, including business, technical and mixed
rules. A finite domain with insufficient meaningful cases remains an explicit gap.
Never relabel a rule, duplicate cases or weaken expectations to pass a gate.

Use `docs/APP_MODERNIZATION_GUIDE.md` for the application-wide sequence and local
evidence utilities. Keep compatibility inside each program's design, derive cases
from an independent oracle, capture portable failed-record bundles, and generate
only the factual block of the single migration document. Regression-check changed
instructions with the pinned scenario suite; synthetic checks are not an Opus run.

Keep sources, rules, target mappings, cases and observed results linked by IDs,
versions and hashes. An unavailable result remains unverified. Reuse only compatible
versions and fresh evidence. The foreground coordinator alone publishes inventory.

When OKF cannot answer an object question, follow `docs/ENDEVOR_NAVIGATION.md`:
refresh stale local views first, then use the existing permitted Zowe/Db2 MCP
route appropriate to the object. Preserve denial, partial, error and scoped-miss
outcomes separately. Do not invent tool bindings or repeat an answered search.
Apply all five context techniques in `docs/TOKEN_EFFICIENCY.md` at handoff and
compaction. Trim conversation, not canonical evidence, active constraints,
unresolved failures, authentic decisions or remaining budgets.

Follow `docs/SECURITY_REVIEW.md`: backend remediates, QA challenges the fix, and
an independent audit rechecks the exact version. Keep quality and security gates
separate; missing checks and unresolved critical/high findings block promotion.
Never claim 100% security from scanner results or review. The progress UI reports
recorded evidence; it cannot grant acceptance or execute a removal.

Use disjoint program paths and at most the configured workers. Repair locally
within the configured budget; preserve failures and continue other independent
programs when a program is blocked. Do not add another orchestration layer.

Before publishing kit changes, run `python tools/check_kit.py`,
`python -m unittest discover -s tests -v`, and independent scoped review.
Business-program changes also require their real focused and
affected integration tests. Configuration checks are not Claude-host or mainframe
acceptance. Keep private working files under ignored program/process directories
or `.implementation/`; do not publish them with the operating kit.
