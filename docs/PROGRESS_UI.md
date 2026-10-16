# Conversion progress and evidence dashboard

The dashboard is a local, read-only view of the canonical inventory. It separates
**converted** from **completed (recorded)**, counts each program once across shared
consumers, and exposes rules, evidence gates, findings, dependencies and Sparkflow
candidates. An empty installation has unknown inventory completeness and no
completion percentage. It never starts with fictional work marked complete.

Start the UI from `ui/` with `npm ci --ignore-scripts`, then `npm run dev`.
Open the local address printed by Vite and use the file picker to load a snapshot.
`npm run build` creates the static production build; no deployment is performed.
The preview serves the UI directory, not the repository or private evidence.
Use the
separate demonstration action only to explore the layout. The fixture in
`examples/progress-demo.json` is conspicuously fictional: seven example programs,
one recorded completion, one retirement, and mixed incomplete states. Its counts
are not project results. No mainframe, model, conversion or security work was
performed to create the fixture.

## Refresh progress

The team lead updates the existing `inventory.json` after evidence-producing work.
Keep progress metadata beside each canonical program row; do not create another
inventory or infer completion from folder names. Export a new timestamped file:

```bash
python tools/progress_snapshot.py \
  --inventory inventory.json \
  --output ui/progress-20261016-120000.json
```

The output directory must exist and the filename must be new. Existing files,
source inventory, symlinks and hardlink aliases are never overwritten. The writer
publishes a fully written file atomically. Refresh by choosing the newly exported
file in the dashboard. Generated `ui/progress*.json` snapshots are local artifacts
and should remain ignored by Git. A pre-generated `ui/progress.json` is optional;
the file picker works without one. The exporter makes no network calls, opens no
evidence references, and writes no inventory updates.

## Additive inventory contract

Keep `schema_version: 1`, `programs`, `processes`, existing program `consumers` and
`migrations`. `status` is `unverified`, `partial` or `complete` and describes the
**declared enumeration** of the inventory. A status of `complete` does not prove
that every mainframe artifact was enumerated. The empty initializer template works
unchanged. Missing progress metadata stays unknown.

Add `progress` to a program row. The following is a shape example, not real
acceptance evidence; replace all example IDs with actual non-sensitive registry
IDs before use:

```json
{
  "program_id": "PROGRAM-ID",
  "consumers": [{"process_id": "PROCESS-ID", "step_id": "STEP-ID", "provider": "python", "version": "BUILD-ID"}],
  "migrations": [],
  "progress": {
    "display_label": "Approved program label",
    "current_version": "BUILD-ID",
    "lifecycle": "active",
    "conversion": {"status": "converted", "version": "BUILD-ID", "evidence_refs": ["CONVERSION-RECEIPT"]},
    "rule_catalog": {"status": "complete", "version": "BUILD-ID", "evidence_refs": ["CATALOG-RECEIPT"]},
    "rules": [{
      "rule_id": "RULE-ID", "category": "business", "lifecycle": "retained",
      "version": "BUILD-ID", "positive_passed": 100, "negative_passed": 100,
      "evidence_refs": ["CASES-RECEIPT"]
    }],
    "gates": {
      "unit_cases": {"status": "passed", "version": "BUILD-ID", "evidence_refs": ["UNIT-RECEIPT"]},
      "legacy_comparison": {"status": "pending"},
      "record_trace": {"status": "pending"},
      "code_quality": {"status": "pending"},
      "security": {"status": "pending"},
      "independent_audit": {"status": "pending"}
    },
    "blockers": [],
    "findings": []
  }
}
```

| Field | Contract |
|---|---|
| `current_version` | Immutable recorded build/source-context identity; missing means unknown. The exporter compares supplied identities; it does not verify the underlying bytes. |
| Receipt | `status`, `version`, `evidence_refs`; a current successful receipt requires matching version and at least one opaque evidence ID. |
| `conversion.status` | `converted`, `pending`, `failed` or `unknown`. Converted does not imply accepted. |
| `rule_catalog.status` | `complete`, `partial`, `pending` or `unknown`; the catalog and `rules` array must both be present for completion. |
| Rule category | `business`, `technical` or `mixed`; every retained executable rule needs the same 100 positive and 100 negative gate. |
| Rule counters | Actual passing unique cases from the case receipt; nonnegative integers or `null`. Missing counts remain `null`, never fabricated zeroes. Totals alone do not verify distinctness, oracle independence or coverage. |
| Rule retirement | Set `lifecycle: retired` and add `retirement: {status: accepted, version, evidence_refs}` after the [removal workflow](RULE_REMOVAL.md). Otherwise the rule remains retained and blocks completion. |
| Gate status | `passed`, `failed`, `pending`, `blocked`, `unknown`. Only `legacy_comparison` also allows `approved_difference`, with current decision and comparison evidence. |
| Blocker | `{blocker_id, category}`; category is `dependency`, `evidence`, `clarification`, `security`, `quality`, `validation`, `access` or `other`. Keep narrative in the referenced work item. |
| Finding | `{finding_id, severity, status}`; severity is `critical`, `high`, `medium`, `low` or `info`. Canonical states: `open`, `fixed_pending_verification`, `closed_verified`, `false_positive_with_evidence`, `accepted_risk`. Compatibility aliases `remediated` and `accepted` map to the corresponding closed/risk state. |
| Finding resolution | Verified closure and evidenced false positives require `resolution: {status: verified, version, evidence_refs}`. Risk disposition requires `status: accepted`, current evidence, opaque `accountable_owner_ref`, `decision_ref`, `rationale_ref`, nonempty `control_refs`, and a future timezone-qualified ISO-8601 `expires_at`. These refer to an actual accountable decision; an agent cannot grant itself one. |
| Security findings | Every unresolved finding blocks completion. Critical/high accepted-risk findings always remain blockers. Medium/low/info risk dispositions expire and require the full current decision. Output keeps the canonical `finding_state` and a normalized display status (`open`, `remediated`, `accepted`). |
| Program retirement | `lifecycle: retired`, a current `retirement` receipt with status `accepted`, and zero remaining consumer bindings. Otherwise retirement remains blocked and the program stays in the active denominator. |

All six gates are required. The security gate refers to an actual scan and
adversarial review; the independent audit gate refers to a separate reviewer.
An agent must not manufacture either receipt. The [security workflow](SECURITY_REVIEW.md)
defines remediation and independent acceptance. A report of zero findings does
not prove that code is 100% secure.

Process rows use `{process_id, progress: {display_label, current_version,
integration: {status, version, evidence_refs}}}`. Membership comes from canonical
program consumers, deduplicated by process ID. Multiple steps using one program
do not inflate either program or process totals. Consumer provider is `python`,
`sparkflow`, `mainframe` or `unknown`; a process is completed only when all member
programs are completed, every binding uses the current version through Python or
Sparkflow, and the process integration receipt passes for its current version.
Old version pins make the process stale while preserving the reusable program's
own completion status. Unknown process references block the affected program.

Migration fields remain compatible with the [single migration register](APP_MODERNIZATION_GUIDE.md):
`migration_id`, optional `display_label`, `stage`, `depends_on`, and optional
`blocker`. Stages are `identified`, `design`, `python_active`, `ready`,
`flow_validated`, `sparkflow_active`, `retired`, `blocked`, `stale` or `unknown`. The view
exports blocker presence only, not its raw narrative, source code or artifact
paths. Declared missing, stale, restricted or unknown artifacts block the candidate;
artifact paths are never opened. Cycles, missing dependencies and downstream blocked candidates remain
blocked. Future ETL work does not incorrectly block a currently accepted Python
implementation; its cutover is a separate dependency-aware decision.

## Reading the totals

| Metric | Meaning |
|---|---|
| Total inventory | Unique inventoried program IDs, including accepted retirements. |
| Active programs | Total inventory minus accepted retired programs. |
| Converted | Current conversion receipt exists; other gates may still be blocked or stale. |
| Completed (recorded) | Current conversion and complete rule catalog with at least one retained executable rule; all retained rule quotas; all six gates; no unresolved blocker or finding. Empty/all-retired catalogs cannot complete an active program: use the explicit retirement workflow without dummy rules. This is a projection of recorded evidence. |
| Completion percentage | Recorded completed / active programs. With no active programs, the result is `null`, not 100%. It does not measure unknown, unenumerated programs. |
| State | Precedence: accepted retirement, blocked, stale, completed, converted, in progress, unknown. An incomplete catalog is explicitly unverified. |
| Process completion | Separate integration and current consumer-binding gates; program completion alone does not imply process completion. |

Converted, blocked and stale counters can overlap because they answer different
questions. Program state is a single display category. Report both the inventory
enumeration status and completion fraction; never present a partial inventory as
the entire application.

## Export and trust boundary

The snapshot has `kind: conversion_progress`, `schema_version: 1`, UTC
`observed_at`, SHA-256 of the exact supplied inventory bytes, `inventory_status`,
and `completeness: declared_not_verified`. It includes derived `counters`,
`programs` and `processes`; program rows expose only safe IDs, reviewed display
labels, counts, gate summaries, findings, consumer bindings and migration metadata.
The UI should label timestamps as snapshot observations, not audit times.

No record payload, source line, DB connection, SQL, credentials, runtime logs,
arbitrary artifact path or raw finding description is exported. Display labels
must be reviewed non-sensitive catalog labels, not customer or employee names;
character validation cannot prove absence of PII. Evidence IDs are opaque
references, not clickable URLs. Review the canonical evidence in the authorized
workspace. Keep the dashboard offline and do not treat arbitrary imported JSON as
trusted acceptance evidence. UI rendering must use text nodes, never HTML from
the file, and must independently validate imported snapshots.

Input and output are bounded to 8 MiB; each list is bounded to 20,000 items.
Duplicate IDs or JSON keys, reserved prototype keys, unsupported enum values,
floating-point counters, nonfinite numbers and malformed data fail closed. IDs
are 1-128 ASCII letters/digits/dot/underscore/hyphen beginning with a letter or
digit; labels are at most 80 plain ASCII characters. Protect the working directory
from concurrent untrusted filesystem mutation; this local exporter is not a
multi-user security boundary or an evidence-signing service.

Run the focused regression suite with:

```bash
python -m unittest discover -s tests -p test_progress_snapshot.py -v
```
