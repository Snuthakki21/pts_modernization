---
name: mainframe-target
description: Implement and verify source-supported mainframe semantic adapters in the existing workbench, initially targeting Python and SQLite. Use for a frozen missing-adapter task, not for speculative conversion claims.
---

Follow the host roles in [the shared workflow](../../../prompts/START_MODERNIZATION.md).
Claude Code owns analysis, implementation, testing, review and local integration.
Read the safe current task and approved sanitized source view references with
`python -m workbench.runner agent PROCESS_ID --workspace WORKSPACE`.
Preserve task hashes and evidence. Missing source/metadata uses the generated
Claude retrieval request through approved read-only Zowe/Db2 MCP and its exact
local inbox; Continue validates accepted returns. Copilot is not required.

Model-visible work uses metadata and explicitly approved sanitized source views.
Raw source/customer rows and SSNs stay protected locally; never put them in LLM
reads, MCP responses, prompts, screenshots/uploads, model APIs or diagnostics.
Code/comments are not inherently safe. Deterministic local tools may compare
protected files and return counts/hashes/gaps; use synthetic or approved masked
examples for tests. Missing safe semantic context stays a qualification gap.


Implement actual parser/IR, reference semantics, target generator and relevant
runtime adapters together. Extend the existing backend boundary; do not create a
second conversion engine or execute arbitrary model-generated source through MCP.
Keep source rules separate from target emission so expected results cannot be
copied from the target. Preserve rule IDs, versions and many-to-many source/target
mappings. Native data, SQL and external-system gaps require executable replacements.

Preserve evidenced legacy behavior, including known design defects; never repair
source business/technical logic during migration. Consolidation requires equivalent
observable outputs, effects, order and errors, with actual target comparisons.
Record preserved source issues with source/target versions, spans and test evidence
in existing artifacts. A missing Db2/utility equivalent remains a named gap, not
an assumed mainframe-only or unnecessary operation.

Reproduce a workbench implementation defect before fixing it. For every newly
supported v5 logic/layout/step use the pinned 64 distinct valid-state floor,
with 128 only for recorded source-risk logic, plus positive/negative/boundary,
error, sequence, linked-file and mutation witnesses. Historical floors remain
frozen; count alone is insufficient. Compare full outputs, traces and return codes by actually executing
the exported target. Test malformed inputs at the target interface, not only in
the test harness. Include counterintuitive source-supported cases and detect silent
behavior corrections; finite tests never establish all possible edge cases.

After integration tests pass, reload changed adapter code: if the running service
reports a stale adapter fingerprint, restart it through the existing launcher
when idle and retain its ledger. Never start a second writer. Use
`agent --refresh`, then read the new task before submitting with
`agent --analysis-file ANALYSIS_JSON`. With the UI running, the local command
inbox routes local workflow mutations to its Coordinator, separate from approved
Db2 MCP retrieval; no workflow proxy or second writer is allowed.
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

Windows 11 is the required workstation. Verify the actual packaged Windows
launcher and approved host; other-platform receipts do not establish acceptance.
