# Remove converted logic safely

Use this workflow when an accepted decision removes behavior from a converted
program. It uses the existing agents and three core skills; there is no deletion
engine, new service or requirement to manually find every Python line. No actual
program has been removed by supplying this guide.

## One request

In the approved Claude Code session, use:

```text
/modernize-process remove-rule A1 R-017 reason="Stop rejecting records for the retired eligibility condition. Continue all other validation."
```

For one consuming process only:

```text
/modernize-process remove-rule A1 R-017 process=PROCESS-A reason="PROCESS-A no longer applies this rejection; PROCESS-B must keep it."
```

Append `plan-only` to inspect the concrete impact plan without changing behavior.
These are natural-language instructions to the skill, not shell commands or a
custom argument parser. You can instead identify the workbook row, source lines
or unwanted behavior in plain language. The agent resolves the rule ID and target
mapping; SMEs are not asked to supply replacement names or implementation choices.

An explicit program-wide request applies to all identified consumers of that
program version. A process-qualified request applies only to that process. If the
request does not establish whether other consumers should change, the lead asks
one focused question after preparing the impact analysis. It does not silently
interpret an ambiguous request as permission to change every consumer.

A clear request authorizes the reversible repository edit and its local tests.
The lead records the attributed decision, prepares a reviewable plan, then applies
and verifies the change without another approval question. Unknown behavior,
unknown consumers, unavailable execution bindings or an existing tool denial are
explicit blockers for the affected operation. Deployment, external database
changes and mainframe operations retain their existing authorization boundaries.

## Responsibilities and existing artifacts

| Owner | Work | Durable output |
|---|---|---|
| Foreground lead | Resolve intended behavior and affected processes; retain decision attribution, work ownership and repair budget | `knowledge/decisions.json`; `knowledge/handoff.json`; removal entry in the program's `analysis/design.json` |
| Gap analysis and design, when needed | Verify original rule boundaries, every target mapping, dependencies and consumer compatibility | Current `analysis/rules.json`, `source-map.json`, compatibility section and impact plan |
| Backend | Apply the smallest change that removes the selected behavior while retaining other behavior | Reviewed patch to program `target/` and the necessary existing invocation/configuration boundary |
| QA | Derive changed expectations from the accepted decision; test absence of removed effects and preservation of other rules | Versioned cases, reproducible records, traces and actual program/process results |
| Audit | Check impact completeness, patch boundaries, independent expectations and evidence | Findings and verification limits in the new run evidence |
| Foreground lead | Reconcile results and publish current state | Inventory, review workbook, migration facts and dated commentary |

Use at most the configured two workers. Backend and QA can work in parallel only
after the decision, source and test contracts are pinned, with disjoint paths.
Audit reviews the completed patch independently. Do not create another agent or
dispatch a second team lead.

## 1. Build a precise, hash-bound impact plan

Before editing target behavior, read the current accepted decision, source map,
program compatibility profile, rule catalog and actual target code. Check the
current test results and the exact versions bound by every consuming process.
Old passing results establish a baseline only for the versions they actually ran.

Store the plan as a `pending_changes` entry in
`programs/<PROGRAM_ID>/analysis/design.json`; retain other design fields. The entry
contains:

- Change ID, program and selected rule IDs, intended new behavior, reason,
  requested process IDs or an explicit program-wide selection, and `decision_ref`.
- Hashes of source/includes, target files, rule/source maps, compatibility profile,
  decision revision, process bindings, independent expectations and relevant
  schemas/reference snapshots; the base commit and pre-existing working changes.
- Exact files, symbols and spans proposed for change; all rules implemented by
  those symbols; all callers, consumers, dependencies and resulting effects.
- Affected tests, trace and replay expectations, process integration runs,
  migration cards, proof requirements, unresolved dependencies and next action.
- A version-pinned rollback target, data-recovery implications, status and evidence
  links. `plan-only` remains `planned`; an unresolved dependency remains `blocked`.

The handoff references this plan, its input fingerprint, owners, blockers and the
remaining repair budget. The accepted decision stays in
`knowledge/decisions.json`; do not duplicate competing decisions in a second
registry. Recheck the pinned inputs immediately before applying the patch. If
they changed, rebuild the affected plan; do not apply a stale line-number patch.

| Check | What must be accounted for |
|---|---|
| Rule-to-code mapping | One rule may span functions, SQL and ETL. One function may implement several rules. Identify all behavior and preserve retained branches. |
| Invocation and consumers | Direct and dynamic calls, batch steps, restart paths, shared versions, process conditions and downstream readers. An unresolved possible consumer prevents deleting the shared implementation. |
| Data and dependencies | Database writes, transaction boundaries, reference lookups, schemas, defaults, output fields, rejected records, totals, ordering and downstream preconditions. A value produced by the removed rule may still be required. |
| Evidence and operations | Rule events, every-record lineage, replay context, case expectations, monitoring, restart/idempotency behavior and failure handling. Remove neither evidence infrastructure nor unrelated guards. |
| Future migration | Python ETL annotations, existing migration IDs, required Sparkflows artifacts, flow prerequisites and consumers. A removed producer can invalidate a planned flow. |

Unknown dependencies block the affected deletion. Continue independent work while
the lead resolves the specific missing fact through approved source views or a
batched SME question. Lack of a search hit does not prove that a dynamic caller or
database consumer is absent.

## 2. Remove only the intended behavior

For a program-wide change, remove the selected logic from its mapped target
locations while preserving all remaining contracts. For a process-only change,
preserve other consumers on their compatible accepted version, or use the
smallest already-supported invocation boundary to select the required behavior.
Document the choice and pin each process binding. Do not copy the entire program
to work around a shared rule or add a general-purpose rules engine.

If rule R1 and retained rule R2 share a function, edit the R1 branch or isolate
that behavior with the smallest necessary refactor. Do not delete or blanket
comment out the function, its database adapter, or a shared helper. Remove imports
and parameters only when the impact analysis proves they are now unused by every
relevant consumer. An explicit removal is implemented as removal, not an
undocumented permanently disabled branch.

Keep a single owner for each changed file. Build and review one narrow change set,
inspect its diff, preserve unrelated user edits and promote the verified changes
together. Never use a broad reset, recursive cleanup or table drop to make the
change pass. Source deletion is not a transaction that undoes past database
writes. Historical effects require a separately authorized, tested data-recovery
plan; an uncertain commit must be reconciled before retrying an effect.

Original COBOL, immutable source snapshots, previously issued SME replies and
historical results remain untouched. Physical retirement of an old shared Python
version waits until all consumers, rollback commitments and retention obligations
permit it. A process-only removal is not permission to delete another process's
accepted version.

## 3. Prove the new behavior and preserve the rest

QA freezes new expectations from the attributed decision and source semantics,
independently of the changed target. Keep the original cases and expectations in
their historical version. Create a new case version linked to the decision rather
than overwriting old proof or merely deleting failing assertions.

1. Reuse every applicable former positive and negative case, including the former
   100 + 100 case set, to demonstrate the intended new output and absence of the
   prohibited effect. Explicitly account for cases whose input contract changed;
   do not silently discard them. Add boundary, interaction and effect checks that
   exercise the actual removed path. A check such as “module imports” is not proof
   of removal.
2. Prove absence at the right boundary: no retired rejection, no unwanted database
   write, no removed output mutation, or the specific effect named in the decision.
   Verify retained outputs, errors, ordering and state, including records that
   formerly hit R1 and also hit retained R2. Where feasible, temporarily restoring
   the old behavior should make the new checks fail; record that focused check.
3. Every retained or replacement executable rule still needs 100 distinct positive
   and 100 distinct negative passing cases. Run the actual Python against the
   independent expectations; a finite-domain shortfall remains a gap. A removed
   rule is not counted as a passing retained rule merely to preserve the totals.
4. Reproduce the original affected records from pinned replay bundles, including
   parent records, state, clock and reference snapshots. Keep the old failed
   observation separate from the new expected result. Missing replay context is
   an explicit verification gap; use safe local adapters without repeating an
   external side effect.
5. Run integration for every affected consuming process, including downstream
   contracts, restart and shared data effects. For a process-only removal, also
   prove the other consumers retain their prior behavior. Reused component
   evidence does not replace consumer-specific integration.
6. Capture complete per-record traces for the changed run. They must show the
   rules actually evaluated, outcomes, effects, record lineage and the exact
   decision/build. Do not fabricate an R1 “hit” after removing it. The versioned
   source ledger explains the intentional absence; retained rule events remain
   visible for every processed record.

Use the commands and input contracts in `APP_MODERNIZATION_GUIDE.md` and the
`validate-program` skill. The existing two-cycle repair allowance applies across
retries and resume; do not reset it for a removal or modify expected results to
conceal a defect. Preserve failing bundles and block affected promotion if the
budget or required evidence is exhausted.

If this retires the component's final executable rule, `rule_cases.py` deliberately
rejects an empty executable catalog. Do not fabricate a retained rule or report
that rejection as a pass. Preserve removed source units and decision references;
use the approved existing test runner to prove absence of retired effects and
verify all affected processes and remaining consumers. Record the unit-rule quota
as not applicable only for a truly retired component, with independent retirement,
dependency and rollback evidence. Any retained executable behavior still needs
its ordinary rule cases and acceptance gates.

Mainframe comparison now has two explicit interpretations: unchanged behavior
must satisfy its required comparison; the intentionally removed behavior is an
approved difference checked against the new decision. Do not call the changed
program exactly equivalent to the unchanged mainframe or invent live comparison
results when the mainframe is unavailable.

## 4. Reconcile the inventory and publish evidence

Retain stable source and rule IDs. Mark the rule mapping
`approved-change/removal`, with the decision, affected versions and consumers.
In the executable rule catalog, a fully removed source unit is `removed` with a
reason and `decision_ref`. If a source unit also implements retained R2, keep it
`executable` and mapped to R2; do not erase its remaining behavior by relabeling the
entire unit as removed. Preserve original spans and historical mappings.

Invalidate acceptance for affected new versions until their actual gates pass.
Update rules, source maps, target/test hashes, compatibility where behavior changed,
process bindings, per-rule counts and inventory evidence. Keep implementation,
unit validation, process acceptance, observed legacy comparison and freshness
separate. Regenerate the workbook projection and the factual block in
`docs/SPARKFLOWS_MIGRATION.md`; add one dated commentary entry explaining changed
flow prerequisites and any Python retirement that remains blocked.

The completion message names the removed rule and affected processes, preserved
consumers, patch/version, decision, real test counts, replay and trace locations,
integration results, rollback instructions and remaining gaps. It must not claim
that deletion succeeded from a plan or an unexecuted test command.

For rollback, restore the recorded accepted code and process binding with a
reviewed inverse change that preserves subsequent work. Recheck dependencies and
rerun affected validation. Restoring code alone does not reverse previously
committed data effects; follow the separately approved recovery plan if needed.
