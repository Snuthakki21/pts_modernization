---
name: headroom
description: Keep model context bounded without losing evidence. Use for safe summaries, efficient retrieval and stale-context detection; no compression runtime is installed.
---

Apply [the shared Start workflow](../../../prompts/START_MODERNIZATION.md) and
[technical contract](../../../docs/TECHNICAL_REFERENCE.md) first. This is an
adapted instruction-only skill, not the full upstream plugin. It grants no tools
or permissions. Keep raw source/PII protected; use synthetic or explicitly
approved sanitized views. Preserve legacy behavior, immutable evidence, one
Coordinator writer and actual human approval. Do not install or invoke upstream
runtimes, MCP servers, hooks, proxies or background services.

This is a local instruction adapter inspired by Headroom's public context-management concepts. The pinned repository exposes no upstream SKILL.md. Its library, proxy, server, models, telemetry and reversible retrieval runtime are not installed.

Select the smallest approved evidence span that answers the current question. Prefer deterministic counts, categories and hashes, plus compact public context routes, over full logs or repeated repository scans.

Preserve requirement IDs, source/target/test hashes, scope denominators, excluded counts, blocker categories and uncertainty. Keep every missing obligation visible. Summarization never changes ledger state or grants conversion credit.

Retain detailed engineering evidence only in its existing owner; link or hash the bounded reference rather than creating a parallel memory store. Verify source hashes before reuse and invalidate a stale summary.

Do not compress raw PII into a model prompt. Compression is not sanitization, and storing raw originals behind a retrieval tool does not make them model-safe. Only synthetic or explicitly approved sanitized views may enter model context.

State unavailable facts explicitly. Record actual provider/account usage receipts when available; never claim a compression percentage, credit savings or lower costs from this instruction adapter.

Pinned inspiration: [upstream source](https://github.com/headroomlabs-ai/headroom/blob/17abee2721c1946bc8903d623bec91ff6e531c17/README.md). Installation scope and
license provenance are recorded in [skill-pack.json](../../skill-pack.json).
