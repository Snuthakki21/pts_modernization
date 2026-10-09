---
name: ecc
description: Design meaningful Python, API and database tests. Use for runtime logic, invalid data, transaction behavior, fixtures and modernization assurance.
---

Apply [the shared Start workflow](../../../prompts/START_MODERNIZATION.md) and
[technical contract](../../../docs/TECHNICAL_REFERENCE.md) first. This is an
adapted instruction-only skill, not the full upstream plugin. It grants no tools
or permissions. Keep raw source/PII protected; use synthetic or explicitly
approved sanitized views. Preserve legacy behavior, immutable evidence, one
Coordinator writer and actual human approval. Do not install or invoke upstream
runtimes, MCP servers, hooks, proxies or background services.

Use the existing unittest and frontend test frameworks; this adaptation does not require pytest or a new dependency. For a defect, demonstrate a failing regression before fixing it. For a feature, assert the intended observable behavior independently of implementation structure.

Build synthetic fixtures with explicit setup and cleanup, isolated databases and deterministic reproducibility receipts. Randomized cases are generated at runtime; retain the seed, unique source-state count, source expectation and actual target result. Preserve identifiers as strings where leading zeros matter.

Test positive, negative and boundary outcomes, NULL/blank distinctions, precision, duplicates, empty inputs, sequential effects, rollbacks, stale revisions and malformed interfaces as applicable. Mock an external boundary only when the test is about that boundary; execute the actual exported target for conversion assertions.

New fixture-v5 processes require 64 distinct valid states per applicable logic/layout/step and 128 for recorded source-risk logic, plus linked-file and mutation obligations. Historical floors remain frozen. Unsupported or unreachable states remain exact gaps, not count-based credit.

Run focused regressions, then the complete mandatory release checks. Coverage percentages alone do not establish business correctness or observed mainframe parity.

Adapted scope: Python testing principles. ECC hooks, memory, telemetry, auto-installation and blanket pytest/coverage requirements are excluded.

Pinned inspiration: [upstream source](https://github.com/affaan-m/ECC/blob/ef648e01899ba3e8dc6371642deaaf64b4477775/skills/python-testing/SKILL.md). Installation scope and
license provenance are recorded in [skill-pack.json](../../skill-pack.json).
