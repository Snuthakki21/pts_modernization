---
name: ecc
description: Design meaningful Python, API and database tests. Use for runtime logic, invalid data, transaction behavior, fixtures and modernization assurance.
---

Follow [AGENTS.md](../../../AGENTS.md) and the
[technical contract](../../../docs/TECHNICAL_REFERENCE.md) first. The foreground
Coordinator agent owns integration through `modernize-process`,
`validate-program` and `consult-modernization`; load this optional skill only
when relevant. This adapted
instruction-only skill grants no tools or permissions. Keep raw source/PII
protected; use synthetic or explicitly approved sanitized views. Preserve legacy
behavior, immutable evidence and authentic human business-review decisions.
Keep discovery read-only and obey the configured access and review policy. Do
not install or invoke upstream runtimes, MCP servers, hooks, proxies or
background services.

Use the test frameworks selected by the current repository contract; this adaptation adds no framework dependency. For a defect, demonstrate a failing regression before fixing it. For a feature, assert the intended observable behavior independently of implementation structure.

Build synthetic fixtures with explicit setup and cleanup, isolated databases and deterministic reproducibility receipts. Randomized cases are generated at runtime; retain the seed, unique source-state count, source expectation and actual target result. Preserve identifiers as strings where leading zeros matter.

Test positive, negative and boundary outcomes, NULL/blank distinctions, precision, duplicates, empty inputs, sequential effects, rollbacks, stale revisions and malformed interfaces as applicable. Mock an external boundary only when the test is about that boundary; execute the actual exported target for conversion assertions.

For each executable business, technical or mixed rule, create at least 100 distinct positive and 100 distinct negative unit data cases derived from the COBOL behavior. Negative cases pass when the expected alternate behavior or rejection is verified. Repeated runs or irrelevant data changes do not add cases. Technical rules have the same quota plus appropriate semantic and performance checks. Preserve historical receipts; unsupported behavior or infeasible case obligations remain explicit gaps, not invented credit.

Run focused regressions, then the complete mandatory release checks. Coverage percentages alone do not establish business correctness or observed mainframe parity.

Adapted scope: Python testing principles. ECC hooks, memory, telemetry, auto-installation and blanket pytest/coverage requirements are excluded.

Pinned inspiration: [upstream source](https://github.com/affaan-m/ECC/blob/ef648e01899ba3e8dc6371642deaaf64b4477775/skills/python-testing/SKILL.md). Installation scope and
license provenance are recorded in [skill-pack.json](../../skill-pack.json).
