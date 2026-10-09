---
name: understand-anything
description: Explain a component and its evidence-backed dependencies. Use for onboarding, lineage interpretation and source-to-target drill-down without full rescans.
---

Apply [the shared Start workflow](../../../prompts/START_MODERNIZATION.md) and
[technical contract](../../../docs/TECHNICAL_REFERENCE.md) first. This is an
adapted instruction-only skill, not the full upstream plugin. It grants no tools
or permissions. Keep raw source/PII protected; use synthetic or explicitly
approved sanitized views. Preserve legacy behavior, immutable evidence, one
Coordinator writer and actual human approval. Do not install or invoke upstream
runtimes, MCP servers, hooks, proxies or background services.

Start with the existing compact context and operator-reference index for static guide questions. Check source-hash freshness, then read only relevant public or approved sanitized spans. Do not rescan protected exports or databases to answer navigation questions.

Describe one component through its responsibility, inputs, outputs, callers, dependencies and failure boundaries. Distinguish an observed call/reference from a inferred business meaning. Unknown or dynamic dependencies remain visible.

For a process, explain job → step/program or transaction → program/map bindings, the logical obligation, its selected scope, target location and verification receipt. Keep source IDs and cross-job memberships consistent with the Coordinator evidence.

Use the existing inventory/lineage projection as the graph owner. Avoid creating a second knowledge database, hidden graph directory, Markdown per rule or another discovery engine. A stale graph/cache is a navigation gap; it cannot authorize conversion.

A detail explanation must link exact source and target spans when available through approved views. If a safe semantic view is absent, show the hash/span and qualification gap instead of reading raw code into the model.

Adapted scope: bounded component/dependency explanation. Graph builder, dashboard server, hooks, indexer and implicit raw-source reading are excluded.

Pinned inspiration: [upstream source](https://github.com/Egonex-AI/Understand-Anything/blob/790b157028637b626c8666fa7fa28248944b900c/understand-anything-plugin/skills/understand-explain/SKILL.md). Installation scope and
license provenance are recorded in [skill-pack.json](../../skill-pack.json).
