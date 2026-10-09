---
name: i-have-adhd
description: Make the next action easy to find. Invoke for clearer operator instructions, cognitive accessibility and manageable step-by-step guidance.
disable-model-invocation: true
---

Apply [the shared Start workflow](../../../prompts/START_MODERNIZATION.md) and
[technical contract](../../../docs/TECHNICAL_REFERENCE.md) first. This is an
adapted instruction-only skill, not the full upstream plugin. It grants no tools
or permissions. Keep raw source/PII protected; use synthetic or explicitly
approved sanitized views. Preserve legacy behavior, immutable evidence, one
Coordinator writer and actual human approval. Do not install or invoke upstream
runtimes, MCP servers, hooks, proxies or background services.

Do not infer a medical condition. This adaptation offers low-friction presentation to any operator who requests a clear walkthrough.

State the current step and one concrete next action first. Use numbered steps when order matters, one bounded action per step and exact UI labels. Include where to click, what to enter, the expected result and how to recover from a visible error.

Keep optional technical explanation behind clear detail sections. Group long lists for scanning without dropping any required step, blocker or evidence. The complete job aid remains complete; concise status updates point to it.

Restate saved versus unsaved state, prerequisite versus approval, and the exact return location when relevant. Never pretend a failed action worked or require the user to remember invisible state across turns.

Use matter-of-fact errors and realistic, explicitly qualified timing where measured. Unknown effort stays Unknown. Do not manufacture estimates, savings, diagnosis or approval.

Adapted scope: accessible step presentation. No persistent psychological mode, automatic medical inference, list-based omission or extra state files are installed. The user's requested granular instructions override brevity.

Pinned inspiration: [upstream source](https://github.com/ayghri/i-have-adhd/blob/723af7d9afaf43eb871dbcce6129e2bf80de90d5/skills/i-have-adhd/SKILL.md). Installation scope and
license provenance are recorded in [skill-pack.json](../../skill-pack.json).
