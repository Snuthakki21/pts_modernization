---
name: modernize-process
description: Modernize or resume a supplied mainframe process through a foreground team lead and bounded specialists. Use for complete program inventory, analysis, SME clarification, conversion, reuse, integration and evidence publication without an orchestration engine.
---

# Modernize process

Execute in the foreground `pts-orchestrator` role. Do not launch a second lead.
Read `CLAUDE.md`, `config/project.json`, the supplied process definition and
applicable accepted decisions/handoff. Load `consult-modernization` only for
interpretation or design trade-offs. Use `validate-program` for actual validation.
Preserve all permission denies; never use Bash, scripts, MCP or copied paths to
bypass protected source/PII. Work from approved sanitized source and synthetic data.

## Prerequisites and intake

Confirm the selected model and actual provider/worker routing; use no fallback.
Read configured concurrency/repair limits: at most two workers and two repair
cycles per program invocation. Null command/profile bindings are unavailable,
not instructions to guess. Preparation may proceed while execution is blocked.

Read `config/source-reference.json`. `TSTSN.#RW477` and the listing pattern
`TSTSN.#RW477*` are visually confirmed from the screenshot; live access and full
coverage are not. Do not infer an endpoint from the terminal URL or treat the
visible snapshot as the entire application. Use the mainframe reference linked
from `validate-program` for permitted discovery preparation.

Preserve supplied source as immutable versioned snapshots or existing protected
snapshot references. Record qualified library/member identities and original
hashes; link approved sanitized views back to original spans. Do not read raw
protected contents into model context. Validate the process's jobs, steps, order,
conditions, parameters, inputs and outputs without inventing missing bindings.

## Dispatch and convergence

| Phase | Assign only needed specialists | Required output/gate |
|---|---|---|
| Discover | `pts-gap-analysis`; `pts-devops` for runtime/access findings | Every supplied program inventoried, including unreferenced programs; immutable identities and explicit missing inputs |
| Understand | Gap analysis; `pts-design` or `pts-qa` on independent contracts | Source spans accounted for; classified rules; compatible reuse assessment; focused business questions |
| Decide | Foreground ingests SMEs; design uses consulting skill as needed | Accepted decision revision, required behavior and target/data/ETL contracts |
| Build | `pts-backend` and QA; `pts-frontend` only for assigned stable view contracts | Minimal target assets and independent case definitions; actual trace instrumentation |
| Validate | QA; DevOps for packets; `pts-audit` for independent review | Current local results and explicit legacy-comparison availability |
| Converge | `pts-analytics`, QA integration and audit as capacity permits | Reconciled evidence, process results and audit findings before inventory promotion |

Queue excess tasks; do not run all eight specialists at once. Give each worker
specific input hashes, output paths and stop conditions. No nested delegation.
Deduplicate shared programs before dispatch. Never assign concurrent writers to
the same file, schema or dataset. Keep implementations canonical; pin each
consumer's version in `processes/<id>/process.json`.

## Required artifacts and SME handling

- Gap analysis writes `programs/<id>/analysis/rules.json`, `source-map.json`, and
  `questions.json`. Include business/technical/mixed/unknown classifications,
  justified declarative/inert treatment, source spans, effects, dependencies and
  unresolved gaps. Include repository/process/program graph views from one model.
- Design writes `programs/<id>/analysis/design.json`; backend owns `target/`;
  QA owns `tests/` and assigned new run evidence. Merge target mapping proposals
  after owners finish; maintain source-to-target-to-test links in `source-map.json`.
- Build every gap row from the mainframe source inventory: LEFT shows original
  dataset/member/hash/lines, exact approved excerpt, preconditions, requirement
  and effects; RIGHT shows current Python file/hash/symbol/lines, actual code
  excerpt, how it satisfies that behavior, delegated SQL/ETL, tests/results and
  observed legacy evidence. Preserve unmapped source, stable IDs and many-to-many
  links across all programs. Never derive requirements from Python or count prose
  similarity as evidence. Use technical-reference Section 5 statuses; include
  each gap and next action. Keep implementation coverage and parity separate.
- Keep one current `processes/<id>/review.xlsx`. Show exact approved source
  excerpts, explanation, generated technical treatment, target/evidence links and
  SME choices: preserve behavior, remove behavior, clarify behavior. SMEs do not
  select reuse or technologies. Preserve issued versions and attributed replies.
  Generate its `Gap Analysis` sheet directly from canonical `source-map.json`,
  with mainframe on the LEFT and Python satisfaction/evidence on the RIGHT.
- Ingest each answer against its question/source version into
  `knowledge/decisions.json`. Detect conflicts, revise rules and invalidate affected
  results. Never infer approval from silence. Continue independent unblocked work.
- Run `validate-program`; QA also runs configured process integration and records
  `processes/<id>/integration/runs/<run-id>/results.json`. Test ordering, bindings,
  state, failure/restart and downstream effects as applicable.
- Only the foreground updates `inventory.json`: all programs, source/target
  versions, rules, consumers, compatibility, evidence, status dimensions and gaps.
  Keep implementation, unit validation, observed parity, process acceptance and
  evidence freshness separate. Unreferenced programs retain empty memberships.

Reuse requires compatible behavior, invocation conditions and current fingerprints
of source/includes, target, decisions, schemas, runtime, reference data and tests.
Do not re-convert a compatible accepted program. Do not reuse stale evidence or
skip consumer-specific integration. Preserve intentionally changed behavior as an
approved difference, never as exact legacy equivalence.

## Completion, repair and memory

Route grouped defects through the two-cycle procedure in `validate-program`.
Stop affected work on repeated failure without progress, missing safe evidence,
unresolved meaning, denied actions, unbound execution or exhausted budget. Do not
reset a budget on resume or rename failures into new tasks. Never weaken tests,
fabricate receipts or overwrite historical evidence.

Persist `knowledge/handoff.json` before interruption: versions, owners, outputs,
checks, blockers, questions, remaining repair budget and next eligible action.
Capture reusable decisions with evidence/applicability/supersession; do not save
whole transcripts. Return one evidence index and concise remaining blockers.
Declare each gate only from actual evidence; a runnable kit is not a conversion.
