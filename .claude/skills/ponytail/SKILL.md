---
name: ponytail
description: Solve the complete task with the least necessary code. Use for simplification, dependency choices, maintenance and avoiding duplicate infrastructure.
---

Apply [the shared Start workflow](../../../prompts/START_MODERNIZATION.md) and
[technical contract](../../../docs/TECHNICAL_REFERENCE.md) first. This is an
adapted instruction-only skill, not the full upstream plugin. It grants no tools
or permissions. Keep raw source/PII protected; use synthetic or explicitly
approved sanitized views. Preserve legacy behavior, immutable evidence, one
Coordinator writer and actual human approval. Do not install or invoke upstream
runtimes, MCP servers, hooks, proxies or background services.

Inspect the affected callers, tests, fixtures, exports and UI contracts before selecting a smaller design. Simplicity means the complete requested behavior remains understandable and verified.

Prefer, in order: an existing Workbench helper or component; the standard library; an installed dependency; a small explicit new function. Do not add a package, wrapper, service or configuration layer for a few ordinary operations.

A shared sort function may replace several source programs only when their ordering, collation, duplicate handling, return behavior and invocation context are verified. Preserve every original source obligation and map it to the consolidated target. A smaller implementation does not reduce the original rule denominator.

Keep trust-boundary validation, data-loss protection, error handling, immutable artifacts, privacy and accessibility. Do not remove behavior because it looks old, redundant or incorrect; retain evidenced behavior unless a distinct authorized change requests otherwise.

Measure relevant performance before optimization. Prefer a readable small diff over compressed code. Test nontrivial logic against meaningful failure cases and call the real target.

Adapted scope: minimal complete implementation. No Ponytail runtime, MCP server, session hook, global mode or automatic shortcut is installed. Required job-aid detail and safety gates outrank brevity.

Pinned inspiration: [upstream source](https://github.com/DietrichGebert/ponytail/blob/9cc65d03aa2da1db7121b912d03596409ee340b8/skills/ponytail/SKILL.md). Installation scope and
license provenance are recorded in [skill-pack.json](../../skill-pack.json).
