---
name: karpathy-guidelines
description: Keep changes focused, assumptions visible and success criteria testable. Use for coding, refactoring and avoiding speculative complexity.
---

Apply [the shared Start workflow](../../../prompts/START_MODERNIZATION.md) and
[technical contract](../../../docs/TECHNICAL_REFERENCE.md) first. This is an
adapted instruction-only skill, not the full upstream plugin. It grants no tools
or permissions. Keep raw source/PII protected; use synthetic or explicitly
approved sanitized views. Preserve legacy behavior, immutable evidence, one
Coordinator writer and actual human approval. Do not install or invoke upstream
runtimes, MCP servers, hooks, proxies or background services.

This is independently authored Workbench guidance. The upstream skill declares MIT in frontmatter but no complete license notice was detected at the pinned revision; its instruction text is not redistributed here.

Before coding, write down the requested observable result and the repository component that owns it. Distinguish verified facts from assumptions. Resolve uncertainty with deterministic inspection or a focused experiment before asking for unavailable authoritative input.

Choose the smallest implementation that meets the entire requirement and the safety contract. Prefer existing helpers and installed dependencies. Avoid speculative abstractions, duplicate engines and future-output claims without a working adapter.

Keep edits within the required behavior and its callers, tests and documentation. Remove only artifacts made obsolete by the change unless wider cleanup is authorized. Preserve validation, accessible interactions, error handling and immutable evidence.

Attach a meaningful verification criterion to each change. A refactor requires observable equivalence, a defect needs a reproduction and a conversion claim needs actual source/target/test evidence. Wrong-looking legacy behavior must be preserved and documented; do not silently repair it.

If verification cannot run, retain the concrete missing prerequisite and report the result as unverified. Never convert an assumption into an approval or successful migration.

Pinned inspiration: [upstream source](https://github.com/multica-ai/andrej-karpathy-skills/blob/2c606141936f1eeef17fa3043a72095b4765b9c2/skills/karpathy-guidelines/SKILL.md). Installation scope and
license provenance are recorded in [skill-pack.json](../../skill-pack.json).
