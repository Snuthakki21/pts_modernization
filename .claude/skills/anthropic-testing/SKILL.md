---
name: anthropic-testing
description: Inspect and test local web flows with synthetic data. Use for rendered UI behavior, accessibility, responsive layouts and screenshot evidence.
---

Apply [the shared Start workflow](../../../prompts/START_MODERNIZATION.md) and
[technical contract](../../../docs/TECHNICAL_REFERENCE.md) first. This is an
adapted instruction-only skill, not the full upstream plugin. It grants no tools
or permissions. Keep raw source/PII protected; use synthetic or explicitly
approved sanitized views. Preserve legacy behavior, immutable evidence, one
Coordinator writer and actual human approval. Do not install or invoke upstream
runtimes, MCP servers, hooks, proxies or background services.

Use the organization-approved browser automation capability already available in the host. This text-only adaptation does not install Playwright, helper scripts or another server manager.

Identify the exact operator task and current rendered state before interacting. Locate controls through visible labels and accessible roles. Observe the result after each state-changing action instead of assuming a click succeeded.

Cover setup Save, the visible next action, process selection, requirements Save, gap filters, detail expansion and return validation with fictional data. Do not enter SME answers or bypass the one-packet gate. Keep one Coordinator writer; use its existing UI and local runner inbox.

Inspect normal and narrow widths, 200% zoom, keyboard order, visible focus, dialog dismissal, status announcements, long labels, empty/error/loading states and reduced motion. Reject unintended overlaps or global page overflow; allow bounded code-table scrolling when labelled.

Capture only synthetic or explicitly approved sanitized screens. Verify screenshots against current build/hash/host context. A macOS browser screenshot is not Windows 11 acceptance, and a geometry scan alone is not full accessibility conformance.

Report successful steps, failures and host limitations separately. Close only test surfaces created for this task.

Adapted scope: observe-before-act browser testing. Upstream scripts, black-box execution, arbitrary screenshot uploads and raw DOM/data capture are excluded.

Pinned inspiration: [upstream source](https://github.com/anthropics/skills/blob/683bc88e56f3e09ba94f7055977f3d3aa499f202/skills/webapp-testing/SKILL.md). Installation scope and
license provenance are recorded in [skill-pack.json](../../skill-pack.json).
