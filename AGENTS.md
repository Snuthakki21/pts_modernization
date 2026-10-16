# PTS operating contract

One foreground lead, eight specialists and three core skills own this workflow.
The progress UI reads exported inventory; do not add an engine or orchestration
service. [TECHNICAL_REFERENCE](docs/TECHNICAL_REFERENCE.md) defines acceptance.

- **Model.** Verify approved Opus 4.7 for foreground, workers and auxiliary
  evaluators, with configured `xhigh` effort. No moving aliases, other-model
  routing or fallback. Stop affected model work if the host cannot honor this.
  Follow [OPUS_QUALITY](docs/OPUS_QUALITY.md); settings cannot establish 5.5 parity.
- **Source safety.** Preserve originals, authentic decisions and historical
  evidence. Use only approved sanitized source views and synthetic data in
  context, logs and commits; never protected source, customer rows or credentials.
  Runtime denials bind shell, scripts, copying and MCP alike. Autonomy or flags
  cannot override them; existing mainframe write/submit/delete denials remain.
- **Ownership.** Read `config/project.json` and the handoff. Use only needed
  specialists, at most two workers with disjoint paths; specialists never delegate.
  Freeze source/rule contracts before parallel implementation and independent test
  preparation. Only the lead merges canonical state and publishes inventory.
  No author certifies their own work.
- **SMEs and mappings.** SMEs own business meaning and intended changes in one
  versioned process workbook; agents own classification, treatment, reuse, names
  and design. Ingest attributed real answers, batch business questions and
  continue unblocked work. Never invent answers or use an out-of-scope disposition.
  Map every mainframe source unit on the LEFT to actual Python, explanation and
  evidence on the RIGHT. Keep unmapped units; `source-map.json` is canonical.
- **Minimal implementation.** Load retained Ponytail for design/build/repair;
  workers without Skill access read its local `SKILL.md`. Prefer existing helpers
  and small clear code; remove duplication, dead code, speculative abstractions,
  invented defaults and broad exception suppression. Preserve required notices
  and provenance in the existing skill-pack manifest.
  Implement logic and ETL in Python now, with database reference tables. Follow
  technical-reference Section 7 for `ETL-LATER (Sparkflows)` comments and the
  single [migration register](docs/SPARKFLOWS_MIGRATION.md). Sparkflows is deferred.
  Retire Python only after dependency, shared-consumer, in-flight and rollback
  checks; use [RULE_REMOVAL](docs/RULE_REMOVAL.md) for authorized behavior deletion.
- **Validation.** Every retained/replaced executable business, technical or mixed
  rule needs 100 distinct meaningful positive and 100 distinct meaningful negative
  passing cases from an independent oracle. Credit requires reaching the mapped
  Python rule. Report zero coverage and finite-domain shortfalls; never relabel
  rules, duplicate cases or weaken expectations. Every record in every accepted
  run needs observed evaluations, outcomes, effects, lineage and source/target
  links, without sampling. Missing trace blocks promotion; synthetic tests alone
  cannot explain ordinary records. Link sources, rules, code, cases and results
  by IDs, versions and hashes. Unknown/stale results stay unverified; reuse needs
  compatible versions and fresh evidence.
- **Evidence and review.** Use [APP_MODERNIZATION_GUIDE](docs/APP_MODERNIZATION_GUIDE.md)
  for compatibility profiles, reproducible failures, factual migration generation
  and instruction regression. Under [SECURITY_REVIEW](docs/SECURITY_REVIEW.md),
  backend remediates, QA challenges and independent audit rechecks the exact
  version. Separate quality/security gates; missing checks or unresolved critical/high
  findings block promotion. Scans cannot prove 100% security. A goal verdict,
  navigation graph or UI cannot grant acceptance or removal.
- **Retrieval.** Follow [ENDEVOR_NAVIGATION](docs/ENDEVOR_NAVIGATION.md): check
  approved `Endevor/` views, rebuild stale OKF, then use permitted Zowe/Db2 MCP
  when the object question remains unanswered. Distinguish scoped misses, partial
  results, errors and denials; never invent bindings or repeat answered searches.
  Graphify is a separate optional Python lookup. Apply the five
  [context techniques](docs/TOKEN_EFFICIENCY.md#five-context-techniques-in-the-existing-workflow)
  at handoff/compaction. Trim conversation, never evidence, active constraints,
  decisions, unresolved failures or budgets; avoid whole-log/fixture context.
- **Continuation.** Follow [CLAUDE_CODE_WORKFLOW](docs/CLAUDE_CODE_WORKFLOW.md) for
  bounded goals and read-only monitoring; timers must not duplicate work.
  [Initialize only missing state](docs/FOLDER_STRUCTURE.md). Persist fingerprints,
  owned paths, checks, questions, blockers, remaining budgets and next action
  before compaction/closure; verify them on resume. Memory grants no permission.
  Allow at most two evidence-driven repair cycles per program. Stop non-progress,
  preserve failures and continue independent work. Resume/task renaming never
  replenishes cumulative limits.

Before publishing kit changes, run `python tools/check_kit.py`,
`python -m unittest discover -s tests -v` and independent scoped review. Changed
instructions need the pinned scenario check; synthetic checks are not an Opus run.
Program changes need real focused and affected integration tests. Configuration
checks are not host/mainframe acceptance. Keep private work in ignored
program/process paths or `.implementation/`.
