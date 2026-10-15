# PTS modernization: technical specification

Version 4.0 · 15 October 2026 · Agent-first branch

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

## 9. Frontend and actual execution traces

Reuse an approved database browser where sufficient. Add only missing SME, source,
rule and record views. A selected record must show the actual run, evaluated rules,
values permitted for display, outcomes, source and target links, changes and validation
findings. Represent true, false, not reached, error and unavailable distinctly.
An absent event is unavailable unless control-flow evidence proves not reached.

Record provenance supports joins, splits, aggregations, repeated updates, rejected
records, deletions and records with no output. Events carry stable input/output IDs,
run and sequence IDs, rule IDs and effect references. Trace observed execution;
never infer a path afterward and label it observed. Measure trace overhead and
detect incomplete traces after crashes. Read-only browsing must not imply writes.
Use accessible navigation and explicit environment/run labels; keep technical
details out of ordinary SME decisions unless needed to judge business behavior.

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
