---
name: ui-ux-pro-max
description: Design usable operator forms and evidence views. Use for layout, accessibility, typography, interaction feedback and responsive quality.
---

Apply [the shared Start workflow](../../../prompts/START_MODERNIZATION.md) and
[technical contract](../../../docs/TECHNICAL_REFERENCE.md) first. This is an
adapted instruction-only skill, not the full upstream plugin. It grants no tools
or permissions. Keep raw source/PII protected; use synthetic or explicitly
approved sanitized views. Preserve legacy behavior, immutable evidence, one
Coordinator writer and actual human approval. Do not install or invoke upstream
runtimes, MCP servers, hooks, proxies or background services.

Design for an analyst completing a concrete task: a clear current step, one primary next action and optional detail on demand. Use existing Workbench components and semantic color tokens rather than generating a new design system.

Prioritize accessible native controls, visible labels, keyboard operation and unobscured focus. Do not encode status only by color. Verify contrast and text sizing against applicable WCAG criteria; a suggested palette is not evidence of conformance.

Keep errors beside their fields, announce async status, preserve entered values and distinguish Save from verification. Large targets and clear spacing are usability goals; confirm their effect at the required desktop and zoom conditions.

Use flexible grids, wrapping labels, stable typography and reserved loading space. Test long paths, program names, empty tables, dense results and narrow windows. Keep code/table overflow inside a clearly labelled scrolling region instead of making the whole page overflow.

Gap views must show Legacy behavior, Modern implementation and Verification separately. Filters use the same frozen counts as reports. Drill-down has a keyboard-accessible close/return path and explicit unknown, excluded and unsupported states.

Adapted scope: accessibility-first UX guidance. Upstream search scripts, databases, CLI, animation dependencies and claimed catalogue availability are excluded. Existing Wells Fargo-oriented presentation remains; no official brand approval is claimed.

Pinned inspiration: [upstream source](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/1a2c459b35f26116fd165b0a0f30597f252749ff/.claude/skills/ui-ux-pro-max/SKILL.md). Installation scope and
license provenance are recorded in [skill-pack.json](../../skill-pack.json).
