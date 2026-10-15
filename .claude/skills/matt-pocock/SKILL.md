---
name: matt-pocock
description: Review implementation against both the requested behavior and repository standards. Use for feature review, architecture review and requirement traceability.
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

Review two independent questions: does the change satisfy the requested specification, and does it follow the documented repository contract? Neither answer substitutes for the other.

Pin the comparison baseline and working-tree scope. Read the actual user requirements, AGENTS.md and technical reference. If the specification is unavailable, report that axis as unverified rather than inventing one.

For specification findings, name a missing, partial or incorrect observable behavior and its exact requirement. For standards findings, cite the contract, changed public file/function and likely failure. Treat naming, duplication and abstraction concerns as judgment calls unless the contract requires them.

Evaluate whether the code has a small cohesive interface, predictable ownership and meaningful trust-boundary validation. Refactoring must preserve verified source behavior, including evidenced legacy defects.

Keep findings bounded and actionable: severity, requirement, evidence span, consequence and reproducing check. Record both axes in existing structured evidence; do not add another public report. Delegate bounded work under the current role contract; the foreground Coordinator agent integrates the findings.

Adapted scope: two-axis review. Issue-tracker setup, unbounded agent spawning and duplicate specification/report files are excluded.

Pinned inspiration: [upstream source](https://github.com/mattpocock/skills/blob/b0618bc436ad893b3c5e84e55fba86586d34a404/skills/engineering/code-review/SKILL.md). Installation scope and
license provenance are recorded in [skill-pack.json](../../skill-pack.json).
