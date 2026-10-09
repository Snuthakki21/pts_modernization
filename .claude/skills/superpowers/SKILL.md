---
name: superpowers
description: Reproduce defects and verify complete fixes. Use for debugging, failing tests, unexpected behavior and evidence-backed completion.
---

Apply [the shared Start workflow](../../../prompts/START_MODERNIZATION.md) and
[technical contract](../../../docs/TECHNICAL_REFERENCE.md) first. This is an
adapted instruction-only skill, not the full upstream plugin. It grants no tools
or permissions. Keep raw source/PII protected; use synthetic or explicitly
approved sanitized views. Preserve legacy behavior, immutable evidence, one
Coordinator writer and actual human approval. Do not install or invoke upstream
runtimes, MCP servers, hooks, proxies or background services.

1. Reproduce the defect with a minimal synthetic regression before changing implementation. If reproduction is unavailable, record the exact uncertainty rather than guessing a cause.
2. Trace the failure across the existing caller, API, Coordinator and artifact boundaries. Inspect only relevant public code or approved sanitized spans; diagnostics return counts, hashes and categories without private values.
3. State one falsifiable cause. Compare a working path, change the smallest shared implementation and run the reproduction again. Avoid layering unrelated fixes.
4. Add boundary, invalid-input, recovery and mutation assertions where the change warrants them. Run focused regressions, the complete repository suite, required named checks and independent scoped review.
5. Summarize actual evidence and remaining gates. A green unit test is not native mainframe parity, enterprise acceptance or proof of every scenario.

Adapted scope: systematic debugging and verification. Upstream worktree automation, broad log dumping, autonomous publishing and separate workflow orchestration are excluded.

Pinned inspiration: [upstream source](https://github.com/obra/superpowers/blob/8ca22dba9a94f28898bbce59f2537ff4d87c747d/skills/systematic-debugging/SKILL.md). Installation scope and
license provenance are recorded in [skill-pack.json](../../skill-pack.json).
