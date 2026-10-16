# PTS modernization: technical specification

Version 4.2 · 15 October 2026 · Agent-first branch

This contract replaces the legacy engine workflow on `modernization/agents-only`.
The existing branches and their historical evidence remain in Git. The deliverable
is a Claude Code operating kit, not a claim that real mainframe programs have been
converted. Internal Wells Fargo standards and workstation capabilities remain
environment inputs. The user confirmed **Opus 4.7** after the later 4.5 mention.

## 1. Outcome and constraints

Modernize each canonical program once, preserve verified behavior, and reuse its
version across compatible processes. Support the stated planning scale of roughly
300 processes through incremental analysis and bounded parallel work. Use the
existing Claude Code VS Code extension, Python, SQL, Sparkflows and approved
mainframe tools. Build no orchestration engine, agent framework or scheduling service.

Requirements are: all-program inventory; business/technical classification per
program; one SME-readable review workbook per process; original-to-target-to-test
traceability; 100 positive and 100 negative passing data cases per business rule;
local and observed legacy comparison; readable efficient code; database-backed
maintained values; process integration; running converted-code inventory; durable
knowledge; and actual record-level trace views. Configuration is not execution evidence.

## 2. Team, skills and ownership

An **agent** owns a role and a bounded task. A **skill** supplies a repeatable
procedure, inputs, outputs and completion conditions. One foreground orchestrator
coordinates eight specialist definitions. Definitions are not eight continuously
running workers. Default concurrency is two workers; change it only from observed
throughput, token cost and environment capacity.

| Agent | Work assigned | Required outputs |
|---|---|---|
| `pts-orchestrator` | Team lead; work allocation, SME coordination, state, reuse acceptance | Task/handoff records, single review workbook, inventory, final evidence index |
| `pts-gap-analysis` | Discover every program; analyze source, dependencies and missing behavior | Artifact inventory, source ledger, classified rules, dependency graph, questions |
| `pts-design` | Architecture, contracts, naming, reuse decisions and consulting trade-offs | Source-linked design, component/DB/ETL boundaries, acceptance measures |
| `pts-backend` | Minimal Python/SQL/Sparkflows implementation and repairs | Versioned code/flow, schemas, source mappings and emitted trace events |
| `pts-frontend` | SME/report navigation and requested database/record explorer | Minimal accessible views, diagrams, actual-record trace navigation |
| `pts-qa` | Independent expected data, cases, local and process tests | Case catalog, synthetic fixtures, actual results, regression findings |
| `pts-devops` | Runtime/model checks, environment bindings, test isolation, mainframe packets | Capability findings, reproducible run packet, authorized execution receipts |
| `pts-analytics` | File/DB reconciliation, coverage, performance and token measurements | Mismatch groups, counts with denominators, benchmarks and trace reports |
| `pts-audit` | Independent classification, code simplicity, evidence and completion review | Supported defects, acceptance findings, stale/missing-evidence report |

The lead alone updates canonical inventory. Each worker owns disjoint files and
returns paths/hashes, facts, assumptions, checks, blockers and next action. Workers
do not spawn more workers. Audit cannot self-certify implementation it authored.
QA derives expectations from original source and accepted decisions before reading
the target implementation. No separate agent is needed for each rule or program.

| Core skill | Caller and result |
|---|---|
| `modernize-process` | Lead; discover → analyze → clarify → implement → validate → integrate → publish evidence |
| `validate-program` | QA/lead with DevOps and analytics; cases, execution, reconciliation and bounded repair |
| `consult-modernization` | Lead/design/gap analysis; evidence, options, trade-offs, recommendation and decision record |

The 15 inherited optional instruction packages remain available on demand with
licenses and provenance in `.claude/skill-pack.json`. They are not upstream runtime
installations. Headroom is a context-selection adapter; Graphify was not found in
the tracked configuration. Inspect any workstation-installed tools before use.
Preserve actual existing configuration; do not claim an absent plugin is installed.

## 3. Parallel execution and automatic repair

| Wave | Independent work | Required convergence |
|---|---|---|
| Discover | Gap analysis inventories source; DevOps verifies host/access/ETL bindings | Frozen source identities, model/capability findings |
| Understand | Analyze separate programs; design assesses reuse; QA drafts expected outcomes | Stable rule IDs, data contracts and necessary SME answers |
| Build | Backend implements; QA builds independent cases; frontend works only on stable view contracts | Compatible source, decision, target, flow and test versions |
| Validate | QA runs tests; audit reviews code; DevOps prepares legacy packet | Local readiness and permitted, comparable legacy evidence |
| Reconcile | Analytics compares independent partitions; QA checks integration; audit checks findings | Explained differences and required passing cases |
| Publish | Lead updates inventory; relevant workers record reusable lessons | Navigable evidence pack and explicit remaining blockers |

Do not parallelize writes to the same file, mutable schema or test dataset. Deduplicate
shared programs before dispatch. While one program waits for SME clarification,
continue other independent programs. Never invent an answer to advance the queue.

Automatic repair uses one initial validation and at most two repair cycles per
program invocation. Group failures by cause; send the smallest reproducer to the
responsible owner; fix; rerun affected tests; then run required integration/regression
checks. Retain original failures. Add meaningful cases when diagnosis reveals a
new scenario. Correct an expected result only with source or SME evidence.

Stop the affected task on repeated failure without progress, exhausted budget,
ambiguous business meaning, missing contracts, unavailable approved model, denied
action, or unbound external resource. Return one concise blocker record. A stopped
task is not success. A normal foreground IDE session is not a durable unattended
service; persist handoffs so it can resume after closure or context compaction.

## 4. Mainframe source discovery

The supplied photo shows listing pattern **`TSTSN.#RW477*`**, at **Row 39 of 75**.
`config/source-reference.json` records visible dataset examples and provenance.
The prefix is visually confirmed; existence, access, member contents and complete
coverage have not been checked against the live system. The terminal URL is not
evidence of a Zowe API endpoint. Do not encode the visible suffix as the only snapshot.

Use approved read-only catalog tools to enumerate the complete matching dataset
list and every member of applicable libraries. Record exact dataset/member names,
encoding, record format/length, acquisition time, original bytes/hash, source
version and approved sanitized view. Resolve ordered COPY/include libraries,
JCL/PROC expansion, CALLs, SQL declarations, link/bind controls, scheduler references,
NDM controls and dynamic references. Dependencies outside the prefix remain visible
and must be resolved through authorized locations.

Inventory **every program**, including programs not reached from the first process.
Do not mistake a dataset for a program or collapse two same-named members from
different libraries. Qualify identity with library/member/version. Preserve every
unrecognized artifact and source span with its finding; no silent omissions.

## 5. Classification, SME review and source mapping

Classify logical units using effects and dependencies, not keywords alone:

| Class | Meaning | Validation |
|---|---|---|
| Business | Eligibility, calculation, routing, limits, business data validation or outcomes | 100 positive + 100 negative meaningful data cases per rule |
| Technical | Encoding, I/O, allocation, mechanical sorting, connection or transport behavior | Contract, boundary, failure, recovery and performance cases |
| Mixed | Technical operation determines business outcome, such as tie order selecting a winner | Separate the business decision and technical contract; test both |
| Unknown | Evidence is incomplete or semantics cannot yet be established | Named gap; no conversion or verification credit |

Attach source file/member, immutable hash, original line range, effective expanded
source mapping, paragraph/statement, dependencies, explanation, classification
rationale, desired behavior, technical treatment and target references. Support
many-to-many mappings across Python symbols, SQL statements, schema objects and
Sparkflows nodes. Preserve old line maps when source changes; never rely on line
numbers alone. Audit reviews any change from business to technical.

### Mainframe-left, Python-right gap comparison

Start with the mainframe source inventory for **every program**, including
unreferenced programs. Each original logical unit anchors a row in
`programs/<id>/analysis/source-map.json`; preserve its stable source ID even when
no Python exists. Do not derive original requirements from Python, match only
implemented code, or infer satisfaction from similar descriptions.

| LEFT: original mainframe behavior | RIGHT: exactly how Python satisfies it |
|---|---|
| Dataset/library, member, source version/hash, original lines and expanded-source mapping | Current Python file, build/hash, symbol and lines; actual relevant code excerpt |
| Exact approved source excerpt; retain original-span mapping and identify any redaction/unavailable excerpt | Explanation linking the actual code to each original precondition, requirement, outcome and effect |
| Preconditions, business/technical classification and requirement, inputs, state and effects | Actual delegated SQL/schema/Sparkflows asset/hash/node and Python caller where applicable; never fabricate a Python implementation for delegated behavior |
| Stable source/rule IDs, dependencies and accepted business-decision reference | Case IDs, actual results/run references, verification level, observed legacy evidence when available, status, specific gap and next action |

Support many-to-many relationships: one source unit may need multiple target
assets, and one target component may satisfy several source units. Retain the
original IDs and count distinct source units for coverage; repeated display rows
must not inflate totals. Keep exact excerpts within approved data-handling rules;
missing safe content remains unavailable, never invented.

Use these explicit row statuses:

| Status | Meaning |
|---|---|
| `missing` | Known required behavior has no target implementation; name the next action. |
| `partial` | Target covers only part of the original requirement/effects; identify the remainder. |
| `implemented-unverified` | Target mapping exists, but current required verification is absent or stale. |
| `verified-with-evidence` | Current referenced results substantiate the explicitly named verification claim; record its level and limits. |
| `approved-change/removal` | An attributed decision intentionally changes/removes behavior; link the decision and affected consumers. |
| `unknown` | Original meaning or target correspondence is unresolved; identify the missing evidence. |
| `non-executable` | Source material has no executable behavior, with an evidenced reason; count it as source accounted for, never as implemented or behaviorally verified. |

Use `non-executable` only for justified inert material such as comments. Declarations
that affect layouts, defaults, precision, state or other behavior still require
target mappings and appropriate verification.

Track implementation coverage, local behavioral verification and observed legacy
parity separately. A locally tested row does not establish mainframe parity.
Unknown or stale evidence cannot support `verified-with-evidence`; preserve its
historical references while marking current verification unmet. Approved changes
remain visible and cannot count as exact legacy equivalence.

Generate the process workbook's **Gap Analysis** sheet from this canonical map,
with mainframe columns on the LEFT and Python satisfaction/evidence on the RIGHT.
Use six visible columns: **Mainframe unit / source reference**; **Mainframe behavior
/ source code**; **Python code / source reference**; **How Python satisfies the
behavior**; **Coverage status**; **Evidence, gap and next action**. The first two
form the LEFT baseline; the last four form the RIGHT comparison. Display statuses
as `Missing`, `Partial`, `Implemented but unverified`, `Verified with evidence`,
`Approved change/removal`, `Unknown`, and `Non-executable source`, mapped to the canonical values above. Keep the
separate legacy-parity basis explicit in the evidence cell; retain full metadata
and multi-span links in `source-map.json`.
Do not create a second mapping store or runtime engine. Backend supplies exact
target mappings; gap analysis preserves source completeness; QA/analytics attach
results; independent audit checks the comparison before the lead promotes status.

SMEs choose **preserve behavior**, **remove behavior**, or **clarify behavior**.
They confirm meaning and intended changes. Agents determine reuse, target names,
replacement technology and implementation. There is no out-of-scope choice. A
removal needs its rationale, affected consumers and tests showing remaining behavior
still works. Keep technical treatment separate from the SME decision.

Use `processes/<id>/review.xlsx` as the single current review file. Include exact
source excerpts, plain language, questions, generated treatment, target locations,
case counts and evidence links. Preserve previous issued versions and original SME
replies; incorporate corrections with attribution and invalidate affected results.
Ask one batch of necessary questions; do not repeatedly ask resolved questions.

## 6. Files, state and inventory

Create directories only when they contain useful artifacts. One canonical program
folder serves all consuming processes; process folders link to pinned versions.

| Path | Contents and owner |
|---|---|
| `config/project.json` | Shared non-secret bindings and limits; DevOps/lead |
| `programs/<id>/source/` | Protected immutable source or snapshot references |
| `programs/<id>/analysis/` | Approved views, rules, source ledger/maps, graph, questions and design |
| `programs/<id>/target/` | Python, SQL and versioned ETL definitions |
| `programs/<id>/tests/` | Case manifest, generators, fixtures and independent expectations |
| `programs/<id>/runs/<run-id>/` | Results, traces, reconciliation, findings and handoff |
| `processes/<id>/process.json` | Ordered/conditional jobs and steps, parameters and pinned programs |
| `processes/<id>/integration/runs/<run-id>/` | End-to-end process evidence and failure/restart results |
| `inventory.json` | Lead-owned current component/version registry and evidence links |
| `knowledge/decisions.json` | Accepted reusable findings with applicability, provenance and supersession |
| `knowledge/handoff.json` | Current task, versions, owned paths, blockers, budget and next action |

The initial registry may be compact JSON; migrate to a small SQLite metadata index
only if measured volume requires it. Keep application data, metadata and large
evidence payloads separate. The workbook is a projection, not a second competing
state store. Maintain status separately for implementation, unit tests, observed
legacy parity, process acceptance and freshness.

Each inventory row identifies source/version, rules, target/build, database and
flow assets, consumers, dependencies/configuration/reference-data fingerprints,
per-rule positive/negative results, evidence locations, owner, blockers and time.
An A1 conversion is reusable only for compatible required behavior and invocation
conditions. New consumers still require process integration. Changed source,
decisions, target, fixtures, expected results, schema, runtime or relevant reference
data invalidate affected evidence. Preserve history and pin consumer versions.

## 7. Implementation, databases and Sparkflows

Prefer small functions, explicit contracts and existing libraries/processors. Keep
business behavior separate from database access, record codecs, job sequencing and
trace capture. Use set-based SQL, batched reads/writes, bounded memory and suitable
algorithms. Compare representative batch duration, statement count, throughput and
memory; do not optimize from intuition alone.

Keep maintained thresholds, dates, mappings, categories and reference data in
versioned database tables. Keep environment paths and tunable settings in config.
Code may contain intrinsic algorithm constants and explicit rule logic; it must
not embed maintained business data or credentials. Avoid a database query per record
when a correctly versioned batch lookup suffices.

Start with SQLite and isolate backend-specific SQL, migrations and transaction
behavior for possible Oracle or BigQuery adoption. Do not promise zero-change
portability. SQLite NUMERIC affinity alone does not guarantee exact decimals [S4].
Use checked scaled integers where ranges permit, or exact decimal representations
with deliberate arithmetic/comparison. Reproduce COBOL precision, intermediate
rounding, signs, overflow and error behavior. Test schema constraints, rollback,
null/blank handling, duplicates, key order and concurrency on each actual backend.

Use the existing Sparkflows framework for applicable extraction, joins, mappings,
lookups, transformations and loads. First inspect a working approved flow, installed
processors/connectors, data types, versions and execution interface. The product
may be public Sparkflows or an internal Spark framework. Public capabilities are
not proof of installed support [S5]. Version flow exports, parameters, field maps
and source-to-node/SQL mappings. Test the **executed flow artifact**, not a separate
Python imitation. Avoid concurrent Spark writes to one local SQLite file; use an
approved staging/load path if direct connectivity is unsuitable.

Audit generated code for redundant wrappers, duplicate logic, speculative frameworks,
dead code, broad exception suppression, hidden defaults, row-by-row SQL and assertions
that reproduce the implementation. Remove unjustified code while preserving behavior.

## 8. Data validation and reconciliation

For each retained or replaced business rule, derive at least **100 distinct positive
and 100 distinct negative unit data cases from COBOL and accepted decisions**.
Negative cases pass by asserting the correct negative outcome. Repeated runs,
irrelevant-field variations and a parser rejection before the rule is reached do
not create meaningful business cases. Record category definitions, boundary and
outcome classes, meaningful distinctness and expected-result provenance.

Use deterministic fixture generators and parameterized tests. Freeze seed, logical
inputs, initial DB/reference state and clock context. Do not ask a model to write
hundreds of redundant test functions. Assert outputs, return/error behavior, DB
effects and forbidden side effects. Cover all material outcomes, interactions and
multi-record state, not merely the two category totals. If a true domain cannot
support the quota, report the evidence and unmet requirement; do not pad it.

Technical sorting, codec, I/O and database tests have no blanket 200-case quota.
Add linked-file, program integration, job ordering, restart, rollback, idempotency
and performance tests as applicable. Test actual converted units and flow nodes.
Expected values must not come from the target function being tested.

Compare local and mainframe runs from equivalent logical inputs and initial state.
Capture executable identity, source correspondence, JCL parameters, encoding,
reference-data and schema versions. A legacy return code alone proves no business
equivalence. Compare full records, files, return/error behavior and DB inserts,
updates/deletes, with duplicate-sensitive and ordering-aware contracts. Totals
alone can hide offsetting errors. Use explicit field-specific normalization and
tolerances; preserve raw protected evidence for deterministic comparison and expose
only permitted summaries. Every intentional difference needs a decision reference.

Use matching immutable legacy baselines when valid. Otherwise prepare the exact
mainframe packet described in the validation skill. Existing runtime denials block
uploads/submission in this branch. DevOps reports the precise policy/resource gap;
it must not route around it. After an authorized environment owner supplies permitted
bindings, the workflow can execute reviewed test work without asking again within
the agreed authorization envelope. This setup has not executed such a run.

## 9. Full evidence trace for every processed record

Every processed record requires a complete, queryable evidence trace in every
accepted execution, including ordinary processing runs, not only synthetic tests.
Sampling, aggregate rule counters and error-only logging do not satisfy this
requirement. Capture business rules and relevant technical transformations from
the actual Python, SQL and Sparkflows execution. Unsupported capture is an explicit
delivery blocker. Do not infer a path afterward and label it observed.

### Record identity and lineage

Assign an opaque record-occurrence ID at intake, before decoding or business-rule
evaluation. Bind it to the run, source snapshot and exact file offset/ordinal or
database row occurrence. Business keys alone are insufficient: duplicates remain
distinct records. Preserve identity across program calls with separate invocation,
attempt and record-version IDs. Pin the input inventory before processing; if a
source cannot be fully enumerated, mark acquisition and run completeness unknown.

Track every input occurrence and derived record version, including malformed,
rejected, filtered, deleted, deduplicated and no-output records. Keep explicit
parent/child edges for joins, splits and aggregations; preserve all contributors
with indexed membership edges rather than a truncated list. Link lookup/reference
rows and their immutable versions when they determine a decision. A final output
must trace backward to its inputs; an input must trace forward to every effect or
its explicit no-output reason.

### Required evidence contract

Use the approved database and existing instrumentation facilities. These are
logical entities, not a request to build a new tracing service or engine.

| Entity | Required evidence |
|---|---|
| Run manifest | Run/process/job/step IDs; input inventory; source/build/rule-map/flow/config/reference-data hashes; capture version; start/end; trace completeness; observed coverage and missing evidence. |
| Record occurrence/version | Opaque ID; source locator and snapshot; parent identity; invocation/attempt; initial state reference; terminal outcome and reason; resulting versions and output/effect references. |
| Rule evaluation | Event ID; record IDs or complete membership reference; invocation/attempt and evaluation ordinal; stable rule ID/version; source and target locations; evaluated condition and typed operands or protected immutable references; outcome; reason and action/effect links. |
| Effect | Event/record/rule links; output location or table/key reference; changed fields with protected before/after evidence; transaction identity; attempted, committed or rolled-back status; errors and rejection reasons. |
| Lineage edge | Parent and child record-version IDs, generating event, relationship type and contributor membership; cross-program links retain the same process-run identity. |

Distinguish **evaluated true**, **evaluated false**, **not reached**, **error** and
**unavailable**. A "rule hit" means a recorded evaluation; show true matches and
actions separately. Record every loop/repeated evaluation and each retry attempt.
For short-circuit conditions, identify unevaluated operands rather than inventing
their values. Show not-reached only with captured branch/exit evidence against the
pinned rule/control-flow map. An absent event alone means unavailable.

Record event sequence and causal parent links. Across distributed partitions use
causal order; do not invent a global execution order from timestamps. Capture SQL
and ETL per-record outcomes from the executed transformation, including predicates
and rejected rows. A later rerun of an expression or a Python imitation is not an
observation of the original flow.

Keep sensitive values and replay material in approved access-controlled evidence
storage, with masked authorized views and immutable pointers. Do not put raw PII in
general logs, model context, Git or workbook exports. Hashes identify snapshots;
hashes alone cannot explain operands or reproduce a decision. Preserve authorized
access to the referenced values for the agreed evidence-retention period. Bind
retention/access and replay resources before accepting a run; expiry must be visible.

### Record explorer and gap-analysis connection

Reuse an approved record/database browser where sufficient. Search by process/run,
program, record occurrence, permitted business key, rule or outcome. Selecting a
record shows its intake, causal timeline of evaluations, why each rule matched or
did not match, field changes, transaction outcome, final disposition, ancestors,
descendants, and available test/mainframe comparison evidence. Every evaluation
opens the mainframe-LEFT/Python-RIGHT comparison for that rule and pinned versions.
From a rule, list all affected record occurrences with pagination and export.
Pagination must not sample, truncate or discard the underlying evidence.

Label legacy comparisons separately. Target tracing does not prove the mainframe's
internal path. Display a legacy rule hit only when actual legacy instrumentation
supports it; output parity alone cannot supply that evidence. Synthetic case results
are not proof of the path taken by an ordinary processing record.

### Completeness and acceptance

QA verifies record-level set membership against the independent input inventory,
not just matching totals: every input has an intake and terminal outcome, every
generated record/effect has valid lineage, every evaluated rule has its event, and
all evidence references resolve to the pinned versions. Check invocation closure,
evaluation ordinals, trace-write acknowledgments and declared expected capture
sites; unexplained gaps, duplicate event IDs or dangling edges block completeness.
Report separate counts and IDs for inputs, outputs, rejected/no-output records,
attempts, and incomplete traces. Do not count retries as additional business inputs.

Exercise positive/negative outcomes, short circuits, loops, duplicates, joins,
splits, aggregates, rejection, rollback, restart, worker crash and evidence-write
failure. Test that instrumentation preserves behavior and that missing evidence
is detected. Preserve failed attempts and reconcile uncertain commits before retry.
Use transactional capture/outbox or durable acknowledgment where the environment
supports it; otherwise declare the failure window. Trace loss must fail the trace
acceptance gate and prevent run promotion, never silently mark the run complete.

Index run/record/rule/event relationships; batch and compress evidence writes and
avoid per-record model calls. Measure throughput, storage and trace overhead on
representative full-volume runs. Optimize capture without sampling records or
dropping required events. Store detailed traces in the database/evidence store;
the SME workbook links to selected record traces instead of holding the event log.

## 10. Model, autonomy, tokens and durable knowledge

Pin the approved model; no fallback to other models, aliases that drift, or plugin
services using another model. Project settings select `claude-opus-4-7` and request
the same model for every subagent. The force setting requires compatible Claude Code
versions; verify actual worker models and provider routing [S1]. Project settings
alone are not organization-wide model enforcement. If unsupported, run the affected
phase in the pinned foreground conversation or stop; never silently substitute.

The supplied `dontAsk` policy permits named local actions and denies actions that
would otherwise prompt. It is not universal auto-approval. All historical deny
entries are retained and protected paths extended to the new layout. No permission
mode can be manufactured in `CLAUDE.md`; the host enforces permissions [S2]. Auto
mode uses a classifier and needs separate model-policy verification. Do not enable
it when that would violate the single-model restriction. Read/write/execute flags
never grant account privileges or defeat managed policy.

Token controls: short always-loaded instructions; targeted source retrieval;
hash-based analysis reuse; no full-repository broadcast; at most two active workers;
source-derived expectations independent of implementation; deterministic generation
and comparison outside model context; concise findings with artifact references;
bounded repair; and relevant skills loaded on demand. Native usage/context reports
can measure overhead [S3]. Retaining all plugins does not mean invoking all of them.
Only adopt Graphify/Headroom runtime features after inspecting the actual installation,
model/data routing and measured benefit. No invented reduction percentages.

Before compaction, persist current source/build/decision IDs, results, unresolved
questions, work ownership, remaining repair budget and next action. Keep knowledge
as versioned facts/decisions with evidence and applicability. Supersede stale guidance;
do not store whole transcripts or promote a local observation into a global rule.

Prompts and review discipline can improve reliability; they cannot guarantee Fable
or Opus 5.5 capability. Evaluate quality on a labeled representative pilot: rule
classification, trace completeness, retained behavior, defect escape, independent
test quality, reconciliation accuracy, runtime and tokens per accepted program.
Use higher reasoning effort for unresolved semantic/architecture problems only
when the approved runtime supports it; measure the trade-off.

## 11. Acceptance and additional recommendations

| Gate | Evidence required |
|---|---|
| Kit ready | Valid files, model/settings consistency, preserved licenses/hashes, no stale engine entrypoints |
| Workstation ready | Actual extension version, loaded skills/agents, approved model, local command permissions, plugin capability inventory |
| Analysis ready | All discovered programs inventoried; all source spans classified or named gaps; resolved dependencies |
| Program ready | Source/target map, accepted behavior, 100+100 cases/rule, applicable technical tests and independent audit |
| Legacy parity | Comparable observed baseline/run, full required comparisons, no unexplained differences |
| Full record trace | Every intake and derived record accounted for; complete actual rule events, lineage, effects and source/target links; no unresolved capture loss |
| Process accepted | Pinned components, real integration/recovery results, current inventory and navigable evidence |

Do not turn one gate into another. A valid kit is not a converted program; a validated
program does not accept all consumers. Missing evidence remains visible.

Recommended additions: prove exported-source/load-module correspondence; test
selected intentional faults to assess the test suite; add rule-interaction tests;
check snapshot consistency and duplicates; detect reference/schema drift; agree a
bounded repeat-run authorization envelope; measure trace failure/overhead; and plan
production coexistence, rollback/data repair and evidence retention separately.
These are engineering recommendations, not claims about NVIDIA or Google standards.

## 12. Reference documentation

Primary documentation checked 15 October 2026. Bind capabilities to the installed
versions, not merely to current public documentation.

- S1: [Claude Code subagents](https://code.claude.com/docs/en/sub-agents), [model configuration](https://code.claude.com/docs/en/model-config), [skills](https://code.claude.com/docs/en/skills).
- S2: [Permissions](https://code.claude.com/docs/en/permissions), [VS Code extension](https://code.claude.com/docs/en/vs-code).
- S3: [Cost and context management](https://code.claude.com/docs/en/costs).
- S4: [SQLite datatypes](https://www.sqlite.org/datatype3.html), [Python Decimal](https://docs.python.org/3/library/decimal.html).
- S5: [Sparkflows workflow API](https://docs.sparkflows.ai/en/latest/rest-api/rest-api-curl/workflow.html), [runtime parameters](https://docs.sparkflows.ai/en/latest/user-guide/runtime-parameters/index.html), [export/import](https://docs.sparkflows.ai/en/latest/user-guide/export-import/index.html).
- S6: [Zowe dataset download](https://docs.zowe.org/stable/web_help/docs/zowe_zos-files_download_data-set), [job submission](https://docs.zowe.org/stable/web_help/docs/zowe_zos-jobs_submit_local-file), [Db2 plugin](https://docs.zowe.org/stable/user-guide/cli-db2plugin/).
