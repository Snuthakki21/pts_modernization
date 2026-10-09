---
name: matt-pocock
description: Review implementation against both the requested behavior and repository standards. Use for feature review, architecture review and requirement traceability.
---

Apply [the shared Start workflow](../../../prompts/START_MODERNIZATION.md) and
[technical contract](../../../docs/TECHNICAL_REFERENCE.md) first. This is an
adapted instruction-only skill, not the full upstream plugin. It grants no tools
or permissions. Keep raw source/PII protected; use synthetic or explicitly
approved sanitized views. Preserve legacy behavior, immutable evidence, one
Coordinator writer and actual human approval. Do not install or invoke upstream
runtimes, MCP servers, hooks, proxies or background services.

Review two independent questions: does the change satisfy the requested specification, and does it follow the documented repository contract? Neither answer substitutes for the other.

Pin the comparison baseline and working-tree scope. Read the actual user requirements, shared Start prompt and technical reference. If the specification is unavailable, report that axis as unverified rather than inventing one.

For specification findings, name a missing, partial or incorrect observable behavior and its exact requirement. For standards findings, cite the contract, changed public file/function and likely failure. Treat naming, duplication and abstraction concerns as judgment calls unless the contract requires them.

Evaluate whether the code has a small cohesive interface, predictable ownership and meaningful trust-boundary validation. Refactoring must preserve verified source behavior, including evidenced legacy defects.

Keep findings bounded and actionable: severity, requirement, evidence span, consequence and reproducing check. Record both axes in existing structured evidence; do not add another public report. Delegate only when expressly authorized, with disjoint scopes; never create a second Coordinator writer.

Adapted scope: two-axis review. Issue-tracker setup, automatic parallel agents and additional specification/report files are excluded.

Pinned inspiration: [upstream source](https://github.com/mattpocock/skills/blob/b0618bc436ad893b3c5e84e55fba86586d34a404/skills/engineering/code-review/SKILL.md). Installation scope and
license provenance are recorded in [skill-pack.json](../../skill-pack.json).
