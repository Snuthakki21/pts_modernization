---
name: validate-program
description: Validate a converted program using independent source-derived data cases, actual local and ETL execution, permitted legacy reconciliation and bounded repairs. Use after implementation changes, new SME decisions, changed fixtures or reuse checks.
---

# Validate program

Let `pts-qa` own cases/results; the foreground owns dispatch and acceptance.
Workers do not delegate. Use DevOps for bindings/packets, analytics for comparison,
backend for repairs and audit for independent findings. Keep at most two workers.
Read `CLAUDE.md`, `config/project.json`, approved original-source views, rule IDs,
accepted decision revisions and the assigned target/flow versions. Never bypass
protected data or permission denies through shell, scripts, MCP or alternate paths.

## 1. Establish an independent oracle

Derive expectations from original semantics and accepted business changes before
reading target code. Record source/hash/span, rule preconditions/outcomes, data
contracts, declared precision, reference snapshot, clock context and side effects.
The tested function must not calculate its own expected answer. Mark expectation
basis as source-derived, accepted specification, observed legacy or unresolved.
Unresolved proposals cannot count as passing evidence.

Create `programs/<id>/tests/cases.json`, executable parameterized tests and coherent
fixtures under `tests/fixtures/`. Store case/rule IDs, category, meaningful input
vector, initial state, expected values/effects, prohibited effects, basis, seed,
and boundary/outcome rationale. Keep exact data in fixture files rather than
expanding hundreds of cases into model prompts.

Require at least **100 positive and 100 negative meaningful distinct data cases
per retained or replaced business rule**. Positive means its condition is met and
required behavior occurs; negative means the correct alternative/no action occurs.
Count invalid input only where that rule defines rejection; a parser failure before
reaching the rule is not a business-rule negative. A passing negative is a passing
assertion, not a failed test. Repeats or irrelevant-field changes do not count.

Cover every applicable outcome, boundary and important interaction; counts alone
are insufficient. If a finite domain cannot justify the quota, report the unmet
requirement and evidence; do not pad it or silently waive it. Mechanical sorting,
codecs, file/DB access and other technical units receive appropriate contract,
boundary, failure and performance tests without a 200-case quota.

## 2. Execute and preserve evidence

Validate configured `commands.unit`, `commands.integration` and `commands.etl`
bindings before their relevant execution. A null binding blocks that execution;
report the exact missing binding and do useful preparation. Do not guess commands,
install tooling or change permissions to proceed. Use isolated local run databases
and outputs; preserve baseline inputs. Run the actual target and the exact deployed
SQL/Sparkflows artifact, not a surrogate Python version of a flow.

Write new `programs/<id>/runs/<run-id>/results.json`, actual outputs and emitted
`trace.jsonl` where supported. Record command binding, runner/model when relevant,
source/build/flow/test/reference hashes, actual assertion results and per-rule
positive/negative counts derived from distinct cases. Keep failures and unavailable
trace evidence. Measure elapsed time, memory/database calls when instruments exist;
never invent performance receipts.

QA runs process integration against pinned program versions when assigned, saving
`processes/<id>/integration/runs/<run-id>/results.json`. Include multi-rule/state
interactions, job order, I/O bindings, rollback/restart and repeated execution where
applicable. Unit counts cannot substitute for these results.

## 3. Reconcile legacy and target

Read [mainframe preparation](references/mainframe.md) for read-only discovery,
baseline collection or a reviewable run packet. Existing mainframe write/submission
denials remain effective; preparing a packet does not authorize its execution.
Reuse a matching immutable observed baseline or identify the missing permitted
reference run. Never label source-derived expectations as observed legacy parity.

Analytics writes `runs/<run-id>/reconciliation.json`: compared initial state,
versions, keys, duplicate/order policy, field-specific normalization, population
or labeled sample coverage, actual record/file/DB differences and accepted change
references. Compare inserts, updates, deletes, values, return/error behavior and
relevant effects. Totals alone are insufficient. Preserve protected originals
locally and expose only allowed synthetic/sanitized examples and summaries.

## 4. Bounded repair and acceptance

Allow one initial validation plus at most two repair cycles per program invocation,
using the configured lower limit if present. Record the counter in the foreground
handoff so resuming does not reset it. Group failures by root cause; send a minimal
reproducer, rule/source reference, expected-result basis and actual difference to
the responsible owner. Preserve the failing receipt. Add a meaningful regression
case for a new scenario; rerun affected checks, then required regressions.

Stop on the same failure without progress, exhausted budget, new business ambiguity,
missing expected-result evidence, denied actions or unbound resources. Correct an
oracle only through evidenced source/SME revision; never relax assertions merely
to obtain green results. New cases without matching legacy results require a new
permitted reference run before claiming their observed parity.

Audit writes `runs/<run-id>/audit.json`; QA returns `runs/<run-id>/handoff.json`
with input/output hashes, checks/results, remaining gaps, repair count and next
step. The foreground alone promotes inventory status. Report unit validation,
legacy comparison, technical checks and process acceptance separately. Approval,
model confidence, test counts or a zero job return code alone are not completion.
