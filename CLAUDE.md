# PTS modernization

Follow `AGENTS.md`. Act as the foreground coordinator; use `/modernize-process`
for a process or portfolio, `/validate-program` for an existing program, and
`/consult-modernization` for an evidence-based decision or recommendation.
Read `config/project.json`, the applicable inventory rows and current handoff.
Read only the needed section of `docs/TECHNICAL_REFERENCE.md`.

Use Opus 4.7 only. Confirm `/model` and workers' actual models; never use `opus`,
`opusplan`, another provider/model or a fallback to satisfy an error. Respect all
runtime permissions and existing protected-data restrictions.

Use `pts-gap-analysis`, `pts-design`, `pts-backend`, `pts-frontend`, `pts-qa`,
`pts-devops`, `pts-analytics`, and `pts-audit` only when their work is needed. Use at most two
workers initially, with disjoint ownership; never recursively delegate. Freeze
source/rule contracts before implementation and independent test preparation run
in parallel. No worker may certify its own implementation.

Investigate technical questions yourself. Batch necessary business questions in
the single SME workbook. Ingest answers with attribution and version. Continue
unblocked work. Attempt at most two evidence-driven repair cycles per program;
stop repeated non-progress, preserve failures and name the exact blocker.

Prefer existing Python/SQL/Sparkflows capabilities, parameterized tests and
database reference tables. Write the smallest clear implementation that preserves behavior.
Remove duplicate implementations, speculative abstractions, dead code, broad
exception suppression, invented defaults and success claims without evidence.

Keep context small: query an existing valid index, use `rg`/targeted reads, cache
analysis by source/dependency hash, and return artifact paths plus concise findings.
Never paste whole fixtures, logs or unrelated programs. Retained Headroom guidance
is instruction-only; Graphify is not bundled. Do not assume token savings.

Before compaction, persist versions, owned paths, completed checks, open questions,
remaining repair budget and next eligible action. Retrieve only applicable durable
decisions. Knowledge is evidence with provenance, not an automatic new permission.
