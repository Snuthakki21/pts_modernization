# Whole-application modernization guide

Use this guide to operate the kit from source discovery through acceptance of every
program and consuming process. The current implementation target is Python for
business logic and simple ETL. Sparkflows is an optional later migration phase.
Local utility tests do not verify an actual application, Claude/Opus session,
mainframe, Db2 connection, or production deployment.
The local utilities require Python 3.11 or later and no third-party packages.

The governing details are in [AGENTS.md](../AGENTS.md),
[CLAUDE.md](../CLAUDE.md), [project configuration](../config/project.json), and the
[technical reference](TECHNICAL_REFERENCE.md). The latest requirement is **at least
100 meaningful distinct positive and 100 meaningful distinct negative passing
data cases for every executable rule**, including business, technical, and mixed
rules. Technical classification does not waive this requirement.

## 1. Start the foreground lead and establish ownership

In the actual Claude Code environment, verify the configured explicit Opus 4.7
model for the foreground and every worker, with no fallback. A configured model
name or user attestation is not a verified provider-routing receipt. Stop affected
model work if the approved routing cannot be established.

For a fresh checkout, use the approved local Python binding to run
`python tools/init_workspace.py --root .`. Follow the
[folder guide](FOLDER_STRUCTURE.md) to initialize selected programs/processes.
On resume, retain the existing decisions, versions and remaining repair allowance.
`CLAUDE.md` imports the shared operating contract and tracked memory index; verify
their loading and effective model/effort through [OPUS_QUALITY.md](OPUS_QUALITY.md).

Use the three core skills with supplied identities and artifact paths. The values
in angle brackets below are **placeholders**, not supplied programs or files:

```text
/modernize-process Inventory the complete application from <APPROVED_SOURCE_MANIFEST>;
include every program and process, resolve dependency closure, and resume from
<CURRENT_HANDOFF>. Convert eligible programs in dependency order.

/validate-program Validate <PROGRAM_ID> at <PINNED_VERSION> using
<SOURCE_MAP>, <RULE_CATALOG>, and <CURRENT_HANDOFF>; preserve failed records.

/consult-modernization Assess <SPECIFIC_DECISION> for <AFFECTED_PROGRAMS> using
<SOURCE_AND_DECISION_REFERENCES>; record alternatives, evidence, and blockers.
```

The [modernization skill](../.claude/skills/modernize-process/SKILL.md) owns the
whole workflow; [validation](../.claude/skills/validate-program/SKILL.md) owns
execution and reconciliation; [consulting](../.claude/skills/consult-modernization/SKILL.md)
supports specific evidence-based decisions. These are procedures, not services.

| Agent | Responsibility and concrete return |
|---|---|
| `pts-orchestrator` | Foreground lead; bounded assignments, SME decisions, handoff, canonical inventory and migration document |
| `pts-gap-analysis` | Every-program source ledger, dependency closure, source map, rule classification and unresolved gaps |
| `pts-design` | Compatibility profile, interfaces, state/effect contracts, reuse and replacement design |
| `pts-backend` | Minimal Python implementation, database access, trace instrumentation and scoped repairs |
| `pts-frontend` | Requested record/gap navigation using stable evidence contracts |
| `pts-qa` | Independent oracle, cases, execution results, replay bundles and integration tests |
| `pts-devops` | Actual model/tool capability receipts, approved bindings and immutable mainframe packets |
| `pts-analytics` | Record/file/Db2 reconciliation, counts with denominators, measured performance and trace completeness |
| `pts-audit` | Independent source completeness, semantic distinctness, oracle provenance and acceptance review |

Use at most **two workers by default**, with disjoint files, schemas and datasets.
Workers do not recursively delegate. Freeze the source/rule contract before
implementation and independent expected-result preparation proceed in parallel.
No author certifies their own implementation. Only the foreground promotes inventory.
During workstation setup, bind the exact utility invocations below to the approved
local test environment and effective permissions. The supplied `dontAsk` policy
blocks commands that are not allowed; an execution flag does not override it.
Keep existing denials and batch missing command/profile bindings into the setup
handoff. Do not invoke a blocked utility through an alternative command.

## 2. Inventory the entire application and close source dependencies

Follow the existing [mainframe discovery and validation runbook](../.claude/skills/validate-program/references/mainframe.md)
and technical-reference Sections 4.1–4.4 for exact Zowe/Db2 readiness and commands.
Reuse the existing tools and their verified bindings; this guide introduces no
alternative connector or database command. Dataset reads, Db2 metadata reads,
synthetic row access, test writes and job submission have separate permissions.
A denied operation stays stopped; do not route around it through another tool.

Enumerate complete dataset/member listings, including continuation pages,
inaccessible objects, unrecognized artifacts and programs unreachable from the
first process. Qualify identities by library/member/version; two same-named members
are not automatically one program. Preserve original snapshots and hashes outside
model context; use only approved sanitized source views with original-span links.

Resolve ordered COPY/includes, JCL/PROC expansion, calls and dynamic references,
SQL declarations and database objects, bind/runtime settings, scheduler and transfer
controls, reference data, and dependencies outside the starting prefix. Unresolved
dependencies remain visible blockers. Independently review the complete source
ledger; a tool accepting a declared list cannot prove that all COBOL was supplied.

Create one canonical `programs/<id>/` for each program and one
`processes/<id>/process.json` for each ordered/conditional process. Preserve
unreferenced programs in `inventory.json` with empty consumer memberships. Expected
outputs are the source manifest/ledger, dependency graph, source fingerprints,
process-to-program bindings, and explicit acquisition or meaning gaps.

## 3. Resolve compatibility before translating behavior

Record each program's source-based compatibility contract in
`programs/<id>/analysis/design.json`. Cover all eight domains: numeric, characters,
layouts, initialization, dates, database, ordering, and errors. Resolve details
such as decimal scale/rounding/overflow, encoding and padding, record layouts,
initial state, clock rules, null/transaction behavior, duplicate/order policy,
and return/error behavior from evidence rather than Python defaults.

Run all commands from the repository root. The following assignments are an
**operator-filled template**: replace every angle-bracket value with an existing
approved input or a fresh run identifier before executing. All artifact paths in
the compatibility profile and rule catalog are repository-relative with `--root .`.
CLI catalog/cases/output paths are ordinary paths relative to the current shell.

```bash
pts_program='<CANONICAL_PROGRAM_ID>'
pts_source='<APPROVED_REPOSITORY_RELATIVE_SOURCE_VIEW>'
pts_catalog='<REVIEWED_REPOSITORY_RELATIVE_RULE_CATALOG_JSON>'
pts_design="programs/$pts_program/analysis/design.json"
pts_run='.implementation/validation-<NEW_RUN_ID>'
set -o noclobber
mkdir -p .implementation
mkdir "$pts_run"

python tools/compatibility_profile.py init --root . \
  --design "$pts_design" --program "$pts_program" --source "$pts_source" \
  > "$pts_run/compatibility-init.json"
```

Repeat `--source` for every approved source/dependency view in this program's
closure. `init` adds an unresolved profile and refuses to replace an existing one;
initialization is not compatibility acceptance. Preserve previous revisions when
updating an established profile.

Resolve every domain as `applicable` or `not_applicable`, with behavior or a reason,
source paths/line spans, and explicit runtime settings. Applicable domains require
hashed fixtures and a hashed proof document containing linked passing test
receipts. Run the real focused tests before creating those receipts. A justified
non-applicable domain has empty fixtures and a null proof; it still needs evidence.

After the semantic fields and fixture references are final, obtain their digest;
this example selects `numeric`, and must be repeated for other applicable domains:

```bash
python tools/compatibility_profile.py digest --root . \
  --design "$pts_design" --program "$pts_program" --domain numeric \
  > "$pts_run/compatibility-numeric-digest.json"
```

Bind each proof's `semantic_sha256`, program/domain and `source_fingerprints` to
the current contract; hash the completed proof back into the profile. Then check:

```json
{
  "schema_version": 1,
  "program_id": "<PROGRAM_ID>",
  "domain": "numeric",
  "semantic_sha256": "<DIGEST_FROM_COMMAND>",
  "source_fingerprints": [{"path": "<SOURCE_PATH>", "sha256": "<SOURCE_HASH>"}],
  "tests": [{"id": "<ACTUALLY_PASSED_TEST_ID>", "fixture_path": "<FIXTURE_PATH>", "status": "passed"}]
}
```

Copy the complete profile source-fingerprint list, not just one source, into that
proof. Fixture paths/hashes belong in the domain's `fixture_refs`; the proof's
path/hash belongs in its `proof` field. Unknown or stale receipts remain blockers.

```bash
python tools/compatibility_profile.py check --root . \
  --design "$pts_design" --program "$pts_program" \
  > "$pts_run/compatibility-check.json"
```

The [profile utility](../tools/compatibility_profile.py) verifies artifact structure,
hashes and receipt linkage. Its `compatibility: verified` means that limited check
passed: it neither executes those tests nor authenticates their claimed outcomes.

## 4. Map every executable source rule and freeze independent expectations

Maintain canonical `analysis/source-map.json` and `analysis/rules.json`. Start each
gap row on the mainframe side with exact approved source spans, conditions and
effects; link the actual current Python code and evidence on the right. Explain
every non-executable unit. Removed behavior needs an accepted decision reference.
Do not remove difficult source spans, derive requirements from the target, or
reclassify a rule to evade testing.

Generate the process workbook's gap view from the canonical source map. Use one
current workbook per process, preserving issued versions and attributed replies;
see the [workbook guide](WORKBOOK_GUIDE.md). SMEs decide business meaning and
intended changes. Agents own technical classification, implementation and reuse.
Unanswered questions block affected behavior while independent work continues.

Prepare the rule catalog consumed by [rule_cases.py](../tools/rule_cases.py) from
those reviewed IDs and mappings. Its required contract is:

| Catalog element | Required content |
|---|---|
| Identity | `schema_version: 1`, `program_id`, deterministic `seed` |
| `source_files` | Approved source path/SHA-256 descriptors |
| `source_units` | Unique `source_id`; `kind` is `executable`, `non_executable`, or `removed`; non-executable/removed reasons, and removal `decision_ref` |
| `target` | Pinned Python path/hash, declared dependencies, default entrypoint `evaluate` |
| `oracle` | Separate pinned Python path/hash/dependencies and `provenance.kind` plus `provenance.reference` |
| `rules` | Unique `rule_id`, business/technical/mixed `kind`, executable `source_ids`, pinned `python_path`, top-level `python_symbol`, positive/negative meanings, `distinction_fields`, `required_coverage` |

Every declared executable source unit must map to a rule. That structural check
does not establish complete COBOL discovery or faithful classification: audit both
against the original ledger. Declare and pin all target/oracle dependencies;
source changes invalidate affected maps, profiles, cases and prior results.

The reviewed independent oracle implements `generate_cases(rule, seed)` and yields
JSON-compatible cases with `case_id`, `category` (`positive` or `negative`),
`inputs`, frozen `expected`, and `coverage_tags`. Supported provenance kinds are
`source_derived`, `approved_specification`, and `verified_python_reference`.
Derive the oracle from COBOL/accepted decisions independently of the target. A
separate, frozen Python reference is eligible only when prior independent
verification and current compatibility are evidenced. Merely copying today's
target into another file is circular, regardless of different file hashes.

Define `distinction_fields` as rule-relevant dotted input paths, including relevant
state where needed. IDs, random noise and irrelevant fields do not create distinct
cases. Define required coverage from actual outcomes, boundaries, errors and
interactions. Positive cases exercise the rule's satisfied condition; negative
cases exercise its correct alternative or defined rejection. Failure in a parser
before reaching the mapped rule does not count as a passing negative.

Require 100 passing distinct cases of **each** polarity for every executable rule,
plus applicable coverage. When a real finite domain cannot supply them, preserve
exhaustive cases and the domain proof, report the unmet quota and obtain an explicit
requirement resolution. Never pad inputs, duplicate cases or silently exempt a
technical rule. Labels and declared distinction fields themselves need source review.

## 5. Execute Python and preserve full record evidence

Implement the actual target adapter `evaluate(rule_id, inputs)`, returning
`{"actual": <JSON result>, "rule_events": [{"rule_id": <ID>, "category": <polarity>}]}`.
The mapped Python symbol must actually execute. Include required values/effects in
the comparison contract and separately reconcile database/external effects; an
adapter's asserted event is not proof of every internal decision.

After reviewing the oracle, target and their dependencies as trusted local code:

```bash
python tools/rule_cases.py generate --root . --catalog "$pts_catalog" \
  --output "$pts_run/cases.json" --max-candidates 10000 --allow-local-execution

python tools/rule_cases.py run --root . --catalog "$pts_catalog" \
  --cases "$pts_run/cases.json" --output "$pts_run/results.json" \
  --allow-local-execution
```

The generation receipt records counts, discarded duplicates and missing coverage.
The execution receipt records actual results, mapped-symbol calls, failures and
passing counts per rule. A generation pass is not an execution pass. A unit data
pass is not program or application acceptance. Preserve every output; choose a
new run directory for the next attempt rather than overwriting cases or receipts.

These utilities execute permitted Python with the calling process's permissions;
`--allow-local-execution` is an explicit local execution choice, **not a sandbox or
permission override**. Review code and use the authorized isolated environment.
Hash/provenance declarations and structured receipts are evidence references,
not automatically true statements about semantics or origin.
The compact runner supports uniquely named sibling `.py` modules, pinned declared
dependencies and standard-library imports. It observes top-level synchronous Python
functions. Package/relative/unpinned third-party imports need the existing approved
program test runner and equivalent rule evidence; do not substitute a copied target
to fit this adapter. Production database/codec integration remains a separate gate.
Start with the [runnable synthetic example](../examples/rule_validation/README.md)
to see the complete source, oracle, catalog and actual target contracts together.

Instrument ordinary and validation runs for every input/derived record, actual
rule evaluation, outcome, effect, retry and terminal disposition, without sampling.
Preserve occurrence/version identities, split/merge parents, all join/aggregate
contributors, source/target links and immutable reference/state snapshots. Compare
trace completeness to an independent record inventory, including rejected/no-output
records. The rule utility does not supply this complete application tracing.
Missing trace or unresolved effects block run promotion.

## 6. Reproduce each failed record and repair within the budget

For every failed record, QA prepares a captured replay bundle from the failing run,
not a reconstruction using today's reference data. The
[replay utility contract](../tools/replay_record.py) specifies:

- `schema_version: 1`, `bundle_id`, and exactly five hashed artifacts: `records`,
  `reference_data`, `state`, `target`, and `adapter`. Paths are relative to the
  bundle manifest directory. The linked run provenance also pins source, rule,
  decision, build and test versions.
- Record occurrence IDs, data and every parent; explicit context records; and
  `dependencies.complete: true` only with evidence of complete closure. For
  stateful/aggregate/window behavior requiring a full partition, set
  `full_partition.required: true`, `complete: true`, and list the entire captured
  inventory in `record_ids`. An isolated child row is insufficient.
- Pinned UTC/business date, Python major/minor and implementation, declared
  environment variables, initial state, reference data, expected result and the
  original failed observation, each expectation carrying source/version provenance.
- A separately pinned trusted adapter `replay(context)` that uses only the supplied
  snapshot. It may explicitly compile the pinned target source; it must preserve
  relevant ordering and avoid uncontrolled external side effects.

After capturing an actual bundle, fill these placeholders. The fresh output must
be **outside the input bundle directory**; its parent must already exist:

```bash
pts_bundle='<CAPTURED_REPLAY_BUNDLE_JSON>'
pts_record='<FAILED_RECORD_OCCURRENCE_ID>'

python tools/replay_record.py --bundle "$pts_bundle" --record "$pts_record" \
  --output "$pts_run/replay-materialized"

python tools/replay_record.py --bundle "$pts_bundle" --record "$pts_record" \
  --output "$pts_run/replay-executed" --execute
```

The first command materializes only; the second runs reviewed local Python. Outputs
are `fixture.json`, portable `bundle.json`, original `source_bundle.json`, pinned
`artifacts/`, and `report.json`. Exit 0 means materialization or expected comparison
without reproducing the failed reference; 1 means mismatch/reproduced failure;
2 means invalid input, environment mismatch or execution error. Reproducing the
original failure is useful diagnosis, never acceptance. Exit 130 records an
interrupted adapter without its potentially sensitive exception message. Closure
completeness and
expectation authenticity remain independent-review obligations. The adapter is
trusted local code, not sandboxed code.

Allow one initial validation and at most **two evidence-driven repair cycles per
program invocation**, subject to a lower configured limit. Group failures by cause;
backend receives the pinned failing bundle, source/rule reference and observed
difference. Preserve failures, add meaningful regressions, rerun affected cases,
then required broader regressions in fresh directories. Version any corrected
oracle only with source/SME evidence. Stop repeated non-progress, exhausted budget,
ambiguous meaning, denied actions or missing contracts; continue independent work.
Persist the remaining budget so a resume does not reset it.

## 7. Prove mainframe parity and every consuming process

Use the [existing mainframe packet and execution runbook](../.claude/skills/validate-program/references/mainframe.md).
Prepare immutable synthetic inputs, initial Db2 state/reference snapshots,
source-to-executable correspondence, approved JCL/bindings and a reviewed packet
hash. Execute only through subsequently permitted, verified bindings. Capture
separate post-run job receipts, output datasets and Db2 effects. A denied submission
or missing output remains unverified; local source-derived expectations are not an
observed legacy run.

Dual-run the same logical inputs and state through legacy and Python. Reconcile
every relevant record/field, duplicate occurrence, ordering rule, insert/update/
delete, committed or rolled-back effect, and return/error behavior. Preserve
normalization rules and accepted intentional differences. Totals or a zero job
return code cannot substitute for this comparison. Reconcile an uncertain external
commit/submission before retry or fallback; a timeout does not prove failure.

Run every affected process's configured integration binding against pinned program
versions, recording `processes/<id>/integration/runs/<run-id>/results.json`. Cover
job/step ordering and conditions, I/O/database bindings, shared state, downstream
effects, restart/rollback and repeated execution. Shared canonical code may be
reused only with compatible source, decisions, schemas, runtime, references and
tests; each consuming process still needs its own integration evidence.

Audit the full evidence chain before the foreground records separate statuses for
implementation, unit data, compatibility, full trace, observed parity, process
integration and freshness. Whole-app completion requires every inventoried program
and every required process to have an evidenced disposition; blocked work does not
disappear from the denominator.

## 8. Publish current facts and retain one migration document

The lead updates canonical `inventory.json` and accepted decisions/handoff from
reviewed evidence. Invalidate affected acceptance after changes to sources/includes,
decisions, target/dependencies, expected cases, database schemas, runtime or relevant
reference snapshots. Preserve old evidence under its original hashes. Record
owners, blockers, remaining repair budget and the next eligible action before exit.

Keep [SPARKFLOWS_MIGRATION.md](SPARKFLOWS_MIGRATION.md) as the single migration
document. Mark eligible Python ETL with concise `ETL-LATER (Sparkflows)` comments
linked by stable migration ID to source maps/tests and that document. Sparkflows
installation or flow execution does not gate current Python acceptance.

After canonical inventory/source maps exist, refresh only the document's generated
facts section; preserve curated flow cards and dated commentary outside its markers:

```bash
python tools/render_migration.py --inventory inventory.json \
  --source-map "programs/$pts_program/analysis/source-map.json" \
  --output docs/SPARKFLOWS_MIGRATION.md
```

Repeat `--source-map` for every program containing a migration in the inventory.
The [renderer](../tools/render_migration.py) requires existing generated-section
markers, unique program/migration IDs, consumer process/step/provider/version
bindings, dependency IDs and source mappings. Artifact paths are below the inventory
directory; hashes distinguish provided, missing, stale, restricted and deferred
artifacts. Rendering facts does not create flows or prove migration readiness.

Add the following fields to existing inventory program rows and source maps.
This is a shape example with placeholders; do not add it as a fictitious migration:

```json
{
  "programs": [{
    "program_id": "<PROGRAM_ID>",
    "consumers": [{"process_id": "<PROCESS>", "step_id": "<STEP>", "provider": "python", "version": "<PINNED_BUILD>"}],
    "migrations": [{
      "migration_id": "<MIGRATION_ID>", "proposed_name": "<NAME>",
      "stage": "identified", "blocker": "<ACTUAL_BLOCKER_OR_EMPTY>",
      "depends_on": [], "python_symbols": ["<MODULE:SYMBOL>"],
      "retain_python": [],
      "artifacts": [{"path": "<RELATIVE_PATH>", "sha256": "<HASH>", "state": "provided"}]
    }]
  }]
}
```

Each corresponding source map supplies `program_id`, its existing `source_units`
with unique `source_id`, a `rules` array, and
`migrations: [{"migration_id": "<MIGRATION_ID>", "source_ids": ["<SOURCE_ID>"]}]`.
Use `[]` for actual empty memberships, not an unknown dependency. A known missing
dependency remains a blocker until mapped. Artifact states are `provided`,
`missing`, `stale`, `access-restricted` or `deferred`; restricted/deferred paths
are not read. Output hashes can verify bytes, not the declared stage. Cycles and
their dependent candidates are reported without inventing an executable order.

In the later phase, switch verified ETL at an existing step boundary. Prove all
dependencies, consumer/provider bindings, single-writer effects, lineage handoff
and rollback/data repair. Retire shared Python only after every consumer and
in-flight reference is resolved and required regressions pass. Retain components
still serving other callers. Unknown external outcomes must be reconciled first.

## 9. Check instruction changes in an actual Opus session

Use the public eleven-scenario [instruction rubric](../tests/instruction_cases.json)
and [offline evaluator](../tools/check_instruction_responses.py) after instruction
edits are complete. This tests supplied decisions about the workflow; it does not
modernize or validate an application. The fingerprint includes tracked memory and
templates, so changes to startup state also invalidate old responses. Create a new
run directory:

```bash
pts_instruction_run='.implementation/instruction-<NEW_RUN_ID>'
mkdir -p .implementation
mkdir "$pts_instruction_run"

python tools/check_instruction_responses.py --fingerprint \
  > "$pts_instruction_run/instruction-fingerprint.json"
python tools/check_instruction_responses.py \
  --template "$pts_instruction_run/response-template.json"
```

Provide the pinned instruction files, public prompts and response contract to the
actual approved Opus session. Have it supply all case IDs, decision enums, selected
action IDs and its own rationales. A human run recorder completes `attested_by`,
`attested_at` with timezone, foreground/worker model declarations and fallback
status. Attestation is explicitly **user-reported**, not verified by the utility.
Save the completed response as the new `responses.json` in this run directory,
preserving the original instruction/suite pins; never relabel an old response with
a current fingerprint.

```bash
python tools/check_instruction_responses.py \
  "$pts_instruction_run/responses.json" \
  --receipt "$pts_instruction_run/receipt.json"
```

Missing, duplicate or extra cases, wrong decisions/actions and stale fingerprints
fail the structured check. A person must audit narratives and observed behavior;
matching public answer fields cannot establish semantic compliance. The evaluator
does not call a model/API or certify routing. To test the evaluator itself,
`--synthetic-fixture <NEW_JSON_PATH>` produces an explicitly synthetic answer-key
fixture; its pass never counts as a real model evaluation.

For changes to this operating kit, run the actual local checks and independent
scoped review before publishing:

```bash
python tools/check_kit.py
python -m unittest discover -s tests -v
```

Report these as local kit checks. Keep actual model evaluation, application tests,
mainframe parity and environment acceptance tied to their own observed receipts.

Use [OPUS_QUALITY.md](OPUS_QUALITY.md) for a separate held-out evaluation against
the prior Opus 4.7 instruction set. Do not treat the public rubric as a capability
benchmark or claim equivalence to another model without a comparable actual run.

## 10. Remove an unwanted converted rule

Use `/modernize-process remove-rule <PROGRAM_ID> <RULE_ID> reason="<INTENT>"`.
Add `process=<PROCESS_ID>` to preserve other consumers' behavior, or `plan-only`
to inspect the impact before editing. The [rule-removal playbook](RULE_REMOVAL.md)
assigns the existing agents, shared dependency checks, narrow reversible patch,
independent tests, evidence updates and rollback. The agent determines exact code
locations; you can identify the unwanted behavior or workbook row instead.
