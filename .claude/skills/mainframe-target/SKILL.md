---
name: mainframe-target
description: Implement and verify source-supported mainframe semantic adapters in the existing workbench, initially targeting Python and SQLite. Use for a frozen missing-adapter task, not for speculative conversion claims.
---

Follow the host roles in [the shared workflow](../../../prompts/START_MODERNIZATION.md).
Claude Code owns analysis, implementation, testing, review and local integration.
Read the current task and approved frozen source paths with
`python -m workbench.runner agent PROCESS_ID --workspace WORKSPACE`.
Preserve task hashes and evidence. Claude has no MCP servers. Missing source or
metadata requires a generated Copilot retrieval request and exact local inbox;
Copilot only retrieves files, then Claude validates/imports them on Continue.

Implement actual parser/IR, reference semantics, target generator and relevant
runtime adapters together. Extend the existing backend boundary; do not create a
second conversion engine or execute arbitrary model-generated source through MCP.
Keep source rules separate from target emission so expected results cannot be
copied from the target. Preserve rule IDs, versions and many-to-many source/target
mappings. Native data, SQL and external-system gaps require executable replacements.

Reproduce an observed defect before fixing it. For every newly supported logic
item use at least 20 distinct source-valid states, branch outcomes, boundaries, errors,
sequence interactions, and consistent linked-file keys where applicable. Compare
full outputs, traces and return codes by actually executing the exported target.
Test malformed inputs at the target interface, not only in the test harness.

After integration tests pass, reload changed adapter code: if the running service
reports a stale adapter fingerprint, restart it through the existing launcher
when idle and retain its ledger. Never start a second writer. Use
`agent --refresh`, then read the new task before submitting with
`agent --analysis-file ANALYSIS_JSON`. With the UI running, the local command
inbox routes mutations to its Coordinator without a Claude MCP or HTTP client.
A submission is review context, not proof of support. Classify frozen rule IDs
with source-grounded reasons. Preserve unverified obligations and do not silently
replace SQLite limitations with mocks.

Continue independent work without routine operator questions. If an unchanged
approach repeats the same failure, record the attempt and missing prerequisite
in the task return rather than looping. Resume from Coordinator state after a
session interruption. Host permissions and authentication cannot be assumed.

Implement online behavior as business modules with API contracts and replacement
screens only when supported by source evidence. Default to one modular deployment.
Service extraction requires independent responsibility, data ownership and verified
transaction boundaries; never split each COBOL paragraph into a service. Keep
SQLite incompatibilities explicit. The current local record API/form package is
only a candidate and earns no native CICS/BMS replacement credit. Preserve replay
keys across uncertain responses and test the actual packaged launcher and APIs.
