# PTS modernization

@AGENTS.md
@knowledge/MEMORY.md

Act as the foreground coordinator; use `/modernize-process`
for a process or portfolio, `/validate-program` for an existing program, and
`/consult-modernization` for an evidence-based decision or recommendation.
Read `config/project.json`, the applicable inventory rows and current handoff.
Read only the needed section of `docs/TECHNICAL_REFERENCE.md`.
Use `docs/APP_MODERNIZATION_GUIDE.md` for exact phase inputs, commands and handoffs.
Use `docs/SECURITY_REVIEW.md` for adversarial review, independent rechecks and
bounded remediation; a passing scan is not a guarantee that code has no flaws.
Use `docs/CLAUDE_CODE_WORKFLOW.md` and `prompts/GOAL_WORKFLOW.md` for bounded goals,
monitoring loops and continuation. Verify the goal evaluator's effective Opus 4.7
route as well as foreground/workers; project settings alone cannot verify routing.

Use Opus 4.7 only. Confirm `/model` and workers' actual models; never use `opus`,
`opusplan`, another provider/model or a fallback to satisfy an error. Respect all
runtime permissions and existing protected-data restrictions.
Use the configured `xhigh` effort and bounded two-worker workflow. Follow
`docs/OPUS_QUALITY.md` for measured quality checks and hard-problem escalation.
No instruction, memory file or model label establishes Opus 5.5 equivalence.

Use `pts-gap-analysis`, `pts-design`, `pts-backend`, `pts-frontend`, `pts-qa`,
`pts-devops`, `pts-analytics`, and `pts-audit` only when their work is needed. Use at most two
workers initially, with disjoint ownership; never recursively delegate. Freeze
source/rule contracts before implementation and independent test preparation run
in parallel. No worker may certify its own implementation.
Require 100 meaningful positive and 100 meaningful negative passing cases for every
executable business, technical or mixed rule. Report every rule, including zero
coverage and finite-domain shortfalls. A correct answer without reaching the mapped
Python rule earns no case credit. Do not derive expected answers from that target.

Investigate technical questions yourself. Batch necessary business questions in
the single SME workbook. Ingest answers with attribution and version. Continue
unblocked work. Attempt at most two evidence-driven repair cycles per program;
stop repeated non-progress, preserve failures and name the exact blocker.

Implement business logic and simple ETL in Python now, using parameterized tests
and database reference tables. Add concise `ETL-LATER (Sparkflows)` comments at
eligible transformation functions, linked to source-map/test IDs; follow technical
reference Section 7. Sparkflows is a later phase, not a current dependency or gate.
The lead maintains `docs/SPARKFLOWS_MIGRATION.md` as the single running migration
document: flow cards, artifact links, dependencies, consumer bindings and commentary.
Render its marked factual block with `tools/render_migration.py`; preserve authored
cards and commentary outside the markers. Input hashes and artifact checks do not
establish behavioral readiness. Keep missing, stale and cyclic dependencies visible.
Link code comments by stable migration ID. Switch verified ETL at an existing
step boundary; retire Python only after shared-consumer and rollback checks.
Write the smallest clear implementation that preserves behavior.
Load the retained `ponytail` skill for each design, build or repair assignment;
workers without Skill access read `.claude/skills/ponytail/SKILL.md` directly.
Apply it before selecting dependencies and when simplifying the final diff.
Remove duplicate implementations, speculative abstractions, dead code, broad
exception suppression, invented defaults and success claims without evidence.

Gap analysis starts from every mainframe source unit: show mainframe on the LEFT
and the actual current Python code, explanation and evidence satisfying it on the
RIGHT. Preserve unmapped units; never derive requirements from Python. Keep
`source-map.json` canonical and generate the workbook `Gap Analysis` view from it.
Implementation coverage is not observed parity; stale/unknown evidence is unverified.

Require a full evidence trace for every processed record in every accepted run:
actual rule evaluations, outcomes, effects, lineage and source/target links, without
sampling. Follow technical-reference Section 9. Incomplete tracing blocks run
promotion; synthetic test evidence alone cannot explain an ordinary record's path.

Keep context small: query an existing valid index, use `rg`/targeted reads, cache
analysis by source/dependency hash, and return artifact paths plus concise findings.
Never paste whole fixtures, logs or unrelated programs. Retained Headroom guidance
is instruction-only. `docs/TOKEN_EFFICIENCY.md` supplies the pinned optional local
Graphify parser and scoped lookup command; never invoke its generic CLI/hooks or
semantic model routes. Verify the workstation binding and measure savings.

Before compaction, persist versions, owned paths, completed checks, open questions,
remaining repair budget and next eligible action. Retrieve only applicable durable
decisions. Knowledge is evidence with provenance, not an automatic new permission.
On a fresh checkout, follow `docs/FOLDER_STRUCTURE.md` to initialize missing local
state. On resume, validate the handoff's source/build/decision fingerprints before
using cached findings; preserve existing repair counters and superseded decisions.
Persist cumulative goal limits in that same handoff. Native resume counters are
not the task budget. A blocked or exhausted goal stops with a truthful handoff;
an evaluator verdict is not application acceptance. Use `.claude/loop.md` for
read-only monitoring; do not launch duplicate conversions or external jobs on a timer.
