# Sparkflows migration register

One running document for **what to build, its dependencies, the supporting
artifacts, how to switch it on, and which Python ETL can then be retired**.
Current implementation remains Python. Sparkflows execution is a later phase.

**Current inventory:** not populated. Approved program source, Python conversions
and flow exports have not been supplied to this kit. No actual flow, dependency
graph, switch command or removable Python function is asserted below. Zero listed
candidates does not mean discovery is complete. The tables and flow card are the
required working format, not conversion evidence.

## 1. How this document stays current

The foreground lead owns this single cross-program register. Workers return small
updates for their assigned migration IDs; they do not edit it concurrently. Update
it after source analysis, Python implementation, dependency changes, validation,
flow creation, consumer cutover and retirement. Preserve prior decisions in Git
and add concise dated commentary below; no transcript dumps or duplicate registers.

Use stable internal `MIG-...` IDs in Python comments, source maps and this document.
These are planning IDs, **not installed Sparkflows flow/node IDs**. One candidate
may replace several cohesive Python functions; one shared candidate may serve
several processes. Group by data contract, dependency and transaction boundary,
not mechanically one flow per function or COBOL paragraph.

Canonical source/code/test links remain in `programs/<id>/analysis/source-map.json`;
versions, consumers and acceptance remain in `inventory.json` and process manifests.
This document is their readable migration view plus the running engineering notes.
Record source/inventory/manifest fingerprints and last refresh for each card. A
changed input invalidates affected readiness and descendants; mark the view stale
until reconciled. Missing or dynamic dependencies remain explicit blockers for
migration/deletion, not reasons to guess. Deferred Sparkflows does not block Python.

Publish only approved sanitized summaries and safe artifact references here. Keep
raw code/data, credentials and protected evidence in their permitted locations.
An inaccessible or expired reference is shown as such, never claimed reviewed.

## 2. Artifacts already provided

| Artifact | What it provides | Current limit |
|---|---|---|
| [Technical specification](TECHNICAL_REFERENCE.md) | Source mapping, Python behavior, validation and every-record evidence contracts | Specification, not runtime proof |
| [Implementation plan](IMPLEMENTATION_PLAN.md) | Owners, sequence and later migration phase | Not an executed conversion |
| [Project configuration](../config/project.json) | Python now, Sparkflows deferred; link to this register | Runtime bindings remain unverified |
| [Source reference](../config/source-reference.json) | Screenshot-based `TSTSN.#RW477*` listing reference | Partial visual reference, not a complete live catalog |
| [Review workbook](../examples/PTS_Modernization_Review_Template.xlsx) | SME decisions, mainframe/Python gaps and record-evidence review | Template with fictional demonstrations |
| [Workbook guide](WORKBOOK_GUIDE.md) | Import and review instructions | No runtime importer or capture service |

Actual Python modules, schemas, fixtures, results and later flow exports are linked
under their flow cards when available. Do not create empty artifact files or
fabricated links simply to fill the register.

## 3. Flow catalog — what needs to be created

| Migration ID / proposed name | Programs and consumers | Python ETL / source-map IDs | Flow to create and retained Python | Predecessors / cutover group | Stage / blocker | Card / next action |
|---|---|---|---|---|---|---|
| — | Not yet discovered | Not yet provided | Not yet determined | Unresolved | Inventory not populated | Acquire approved artifacts; identify real candidates |

For every real candidate, add one card using Section 5. Proposed flow names are
engineering decisions. Record actual installed flow ID, export hash and node IDs
only after they exist. Separate these milestones: `identified`, `python-verified`,
`flow-built`, `flow-verified`, `cutover-ready`, `active-for-listed-consumers`,
`python-retired`. Also show `blocked` or `stale` and the prior milestone. Flow-built
is not flow-verified; one accepted consumer does not accept all consumers.

## 4. Dependencies and migration order

| From → to | Type | Required version / contract | Evidence | Migration consequence |
|---|---|---|---|---|
| Not yet inventoried | — | — | — | No order asserted |

For real edges, identify **data**, **invocation/control**, **schema/reference**,
**shared helper**, **transaction/state**, and **trace/identity** dependencies.
Record hard prerequisites separately from compatible alternatives. Include file
layouts, DB tables/views, reference snapshots, clock/parameters, commit boundaries,
external effects, consumers and dynamic call/configuration entry points.

Order hard dependencies before their consumers. An upstream Python stage may stay
in place while a downstream flow is introduced if the pinned output contract is
compatible and the mixed path is validated; an upstream flow need not always be
migrated first. Independent candidates can be built/tested in parallel in isolated
state. Shared writers or resources cannot be changed concurrently without a proven
isolation contract.

Do not invent an acyclic order for cycles. Group inseparable stages into one tested
cutover unit, or keep them in Python until a real boundary is established. A
transaction spanning two functions cannot simply be split across a remote flow.
Record the affected consumer closure and shared dependencies before scheduling a
switch. Unknown consumers block retirement of shared code.

## 5. Per-flow card — complete for every actual candidate

Copy this section under a real stable migration ID; all fields are required or
explicitly marked missing, deferred or not applicable with a reason.

| Field | Content to supply |
|---|---|
| Identity and freshness | Migration ID, proposed name, owner, milestone/blocker, last update, source/decision/code/inventory/manifest fingerprints |
| What to create | Plain-language ETL sequence; inputs → operations → outputs; candidate processor types; actual supported node mapping only after installation is verified |
| Original behavior | Program/library/member/hash, source-map and rule IDs, accepted behavior decisions; preserve business/technical classification |
| Python today | Exact module path, commit/hash, symbols and diagnostic line spans; all call sites and executable/job/config entry points |
| Replace / keep | Exact ETL symbols/calls to replace; business logic, codecs, shared helpers, I/O and trace responsibilities that must remain or move explicitly |
| Input/output contract | Fields/types/scale/nulls, keys and duplicates, order/ties, encoding, schema version, occurrence IDs and complete lineage; materialized output location/format if crossing a batch boundary |
| State and effects | Reference versions, initial DB state, transaction/isolation, allowed writes, rejection/error behavior, retries/idempotency and uncertain-outcome recovery |
| Dependencies | Predecessor IDs and non-flow resources; versions/conditions; hard versus compatible alternative; cycle/atomic group; full downstream consumer closure |
| Current consumers | Every process/step/caller, pinned implementation version and active provider; distinguish confirmed from unresolved/dynamic use |
| Artifacts | Rows from the artifact checklist below, each with exact safe location, hash/version, availability, supplier/received date, owner and verification receipt |
| Planned switch | Exact existing process/job/config path and key or caller change; old → new binding; target flow/export version; completion/output handoff; prerequisites and run boundary |
| Acceptance | Python baseline, independent cases, original/mainframe comparison, actual-flow results, full trace, performance, mixed-path and every affected consumer's integration receipts |
| Rollback | Previous Python build and binding, revert command/patch, operator/owner, checkpoint, data reset/repair/compensation and recovery-test receipt |
| Retirement | Exact deletable files/symbols/imports/config/package references; zero remaining consumers/in-flight runs proof; retained components and regression evidence |
| Next action | One concrete task, owner and blocker; no unsupported completion date or success claim |

Artifact checklist for each card:

| Artifact | Required content / timing |
|---|---|
| Original/source map | Approved source references, source/rule IDs and versioned original-to-Python mapping; available during analysis |
| Python implementation | Actual functions/modules and their callers; available after implementation |
| Contract and data | Schemas, field mapping, parameters/reference-state bindings and synthetic fixtures; required for Python verification |
| Tests and baseline | Case catalog, independent expected results, Python run manifest, mainframe comparison and trace/reconciliation receipts |
| Flow build packet | Ordered operations and input/output bindings sufficient to build the flow; supported processors and node settings verified when migration starts |
| Actual flow export | Real export, installed flow/node IDs, version/hash and parameter schema; deferred until built, never a placeholder |
| Cutover artifacts | Exact integration/config diff, allowed invocation/monitoring bindings, version pin, output handoff and rollback instructions; prepared before switching |
| Migration evidence | Actual flow runs, original/Python comparisons, every-record lineage/effects and affected consumer tests; required before cutover |
| Retirement diff | Exact code/import/dependency deletion patch and regression results; prepared only after retirement prerequisites are met |

Availability is `provided`, `missing`, `stale`, `access-restricted` or `deferred`.
Availability alone is not verification. Link large/protected artifacts; do not embed
raw traces or datasets in this document. Keep planned artifacts distinct from
actual provided artifacts and preserve historical run references.

## 6. Make the Python ETL easy to replace

During normal Python implementation, use small named ETL functions/modules with
explicit inputs, outputs and effects. Keep unrelated business decisions outside
the replaceable unit. Do not entangle a projection/join with caller-specific global
state or hide writes in a utility. Document necessary coupling rather than forcing
an unsafe split. Existing module and process boundaries are sufficient; do not add
a plugin system, generic dispatcher, new scheduler or parallel implementations now.

Add a migration ID and register link to the existing comment convention.
Illustrative IDs only:

```python
# ETL-LATER (Sparkflows) MIG-DEMO-01: project and rename these input fields.
# Preserve nulls, duplicate occurrences and complete record lineage.
# Plan: docs/SPARKFLOWS_MIGRATION.md#flow-mig-demo-01; source: DEMO-MAP-01; tests: DEMO-ETL-01.
```

For actual code, the linked card and source/test references must exist. Its card
lists all callers and what stays in Python. Comments identify the unit; they are
not the switch and do not authorize deletion.

## 7. Quick cutover and Python retirement

The cutover unit is one identified process step or proven atomic group, with one
active implementation per consumer/version and exactly one side-effect writer.
Use the **existing** process manifest/job configuration or a small explicit caller
change. The per-flow card supplies the exact old/new binding and rollback patch.
Record provider (`python` or `sparkflows`), artifact/version, input/output contract,
parameters and receipt in the existing manifest/run metadata; these are required
fields to bind in the actual runner, not a new runtime implemented by this kit.

1. **Prepare:** freeze a verified Python build/baseline, dependency closure and
   consumer list. Build the real flow and validate actual execution, original
   semantics, mainframe comparison, all required tests, full trace and mixed-path
   integration. Prove the runner's binding and output handoff before enabling it.
2. **Switch at a run boundary:** pin the selected provider/version for the whole
   run, drain or explicitly isolate older in-flight work and change only the
   reviewed step/group binding. Keep retained Python business functions active.
   Never run both implementations against the same writable destination. Shadow
   comparisons use isolated outputs/state and cannot repeat real effects.
3. **Handoff and verify:** the existing runner waits for the actual flow completion
   and validated output/commit receipt before downstream Python consumes it. Pass
   run/occurrence/attempt identity and full lineage across the boundary. A submitted
   job ID is not completed ETL; asynchronous flows cannot simply replace a
   synchronous function's return value. Fail a missing/unknown binding or failed
   contract; do not silently fall back to Python after possible external writes.
   Capture the selected-provider receipt and complete dispatch/trace evidence that
   the disabled Python ETL was not invoked; absent events alone do not prove it.
4. **Rollback if needed:** reconcile uncertain jobs/commits first; restore the
   pinned Python build and binding with the tested checkpoint/data-repair procedure.
   A configuration flip alone cannot undo committed DB/file effects.
5. **Retire only after adoption:** confirm every consumer of each removable symbol
   is migrated or pinned to an independently retained old build; no in-flight run
   needs the files; dynamic imports/job/config references are resolved; shared
   helpers, codecs, business rules and trace capture still have an owner. Run the
   affected regressions, then delete only the documented ETL code/imports and
   genuinely unused dependencies; rerun the affected checks against the deletion
   result. Preserve independent contract tests, rollback artifacts and historical
   maps, and record the exact removal commit and post-removal receipts.

Prefer a small reviewed binding/caller change over commenting out blocks. The
ETL can be inactive immediately after a verified cutover while its old build is
retained for rollback. Physical deletion is a separate gate; one converted flow
does not prove shared Python code is unused. Keep the register's consumer matrix
current during staggered migration. This kit has no working toggle or deletion
tool until actual program/runner contracts are provided and implemented.

## 8. Running commentary

For each substantive update append: timestamp, migration ID, what changed, why,
dependency/consumer impact, exact artifact/commit/receipt references, resulting
milestone or blocker, owner and next action. Update the catalog/card in the same
handoff. Record decisions and observed results, not model confidence.

| Date | Migration ID | Update and impact | Evidence | Next action |
|---|---|---|---|---|
| 2026-10-15 America/New_York | Register | Added the single migration register and dependency-aware cutover/retirement contract. Python remains current; real candidate inventory is pending. | Provided kit artifacts in Section 2; no runtime receipts | Acquire approved source and Python artifacts, then populate actual flow cards |
