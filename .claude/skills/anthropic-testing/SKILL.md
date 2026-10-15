---
name: anthropic-testing
description: Inspect and test local web flows with synthetic data. Use for rendered UI behavior, accessibility, responsive layouts and screenshot evidence.
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

Use the organization-approved browser automation capability already available in the host. This text-only adaptation does not install Playwright, helper scripts or another server manager.

Identify the exact operator task and current rendered state before interacting. Locate controls through visible labels and accessible roles. Observe the result after each state-changing action instead of assuming a click succeeded.

Test the implemented operator flows defined in the current contract using fictional data: table browsing, record trace drill-down, business review and gap evidence where available. Do not fabricate SME decisions or assume a planned interface exists. Return observed results to the foreground Coordinator agent; do not operate a second workflow writer.

Inspect normal and narrow widths, 200% zoom, keyboard order, visible focus, dialog dismissal, status announcements, long labels, empty/error/loading states and reduced motion. Reject unintended overlaps or global page overflow; allow bounded code-table scrolling when labelled.

Capture only synthetic or explicitly approved sanitized screens. Verify screenshots against current build/hash/host context. A macOS browser screenshot is not Windows 11 acceptance, and a geometry scan alone is not full accessibility conformance.

Report successful steps, failures and host limitations separately. Close only test surfaces created for this task.

Adapted scope: observe-before-act browser testing. Upstream scripts, black-box execution, arbitrary screenshot uploads and raw DOM/data capture are excluded.

Pinned inspiration: [upstream source](https://github.com/anthropics/skills/blob/683bc88e56f3e09ba94f7055977f3d3aa499f202/skills/webapp-testing/SKILL.md). Installation scope and
license provenance are recorded in [skill-pack.json](../../skill-pack.json).
