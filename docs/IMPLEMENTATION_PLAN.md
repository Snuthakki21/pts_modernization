# Implementation roadmap

> Execute this plan task by task using the foreground lead and its specialist
> agents. This is the future workstation/pilot plan, not a claim that a conversion
> has run. Use the existing skills and test stack; do not build a new engine.

**Goal:** accept one representative process end to end, prove compatible shared
program reuse, then expand across the discovered inventory with current evidence.

**Architecture:** nine role definitions, three core skills, at most two active
workers; existing Zowe CLI, Db2 MCP and Sparkflows; small Python/SQL components and
database-backed evidence. Opus 4.7 only. The technical reference is the acceptance
contract. Paths below are relative to the repository root.

**Delivery boundary:** this branch supplies instructions, configuration, source
reference, review workbook and offline kit checks. Actual connection binding,
source analysis, target code, synthetic fixtures, runtime trace capture and
mainframe parity must be executed in the approved environment.

## Task 1 — Bind the existing workstation once

Owner: DevOps; independent check: audit. Skill: `consult-modernization`.

- Read `START_HERE.md`, `config/project.json` and technical-reference Section 4.
- Record the installed Claude extension/runtime, effective model/delegation,
  Zowe version and non-secret profile reference, actual Db2 MCP server/tool names,
  platform, permitted resource patterns and one installed Sparkflows flow.
- Keep receipts in `.implementation/workstation.json` and
  `.implementation/readiness.md`; do not commit credentials, raw source or rows.
- Bind exact tools to role and host permissions through the environment owner's
  approved process. Preserve explicit denials. Do not treat a configured server
  or successful metadata query as permission for data reads, writes or jobs.
- Bind the trace store, retention/access, local test commands and numeric budgets.
  Record states `user-reported`, `verified`, `denied`, `unavailable` or `unverified`
  with timestamp, resource, tool/version and receipt for each capability.

Checks: `python tools/check_kit.py`; permitted synthetic model/worker smoke test;
allowed read-only catalog/metadata probes; receipt review. Kit checks must pass
independently of unavailable remote capabilities. Batch blockers into one owner
handoff. No live probe is implied by this document.

## Task 2 — Inventory and map every program

Owners in parallel: gap analysis for mainframe/source dependencies; analytics for
approved Db2 metadata and lineage. Lead owns the merged inventory. Skill:
`modernize-process`.

- Enumerate the full verified `TSTSN.#RW477*` catalog and all relevant members;
  preserve pagination/completeness and migrated-member acquisition gaps.
- Acquire immutable protected snapshots and approved model-visible views. Resolve
  JCL/PROC expansion, COPY/includes, calls, DD bindings, SQL and dependencies.
- Populate `inventory.json`, `programs/<id>/` and `processes/<id>/` according to
  technical-reference Section 6. Every discovered program gets a status, even if
  not used by the first process. Never silently discard unreachable source units.
- Classify each source span as business, technical, mixed, non-executable or an
  explicit unresolved gap. Populate the mainframe-left/target-right mapping.
- Use the supplied workbook for attributed SME behavior decisions. SMEs own
  preserve/remove/clarify choices. Engineers own classification, naming, technical
  treatment, conversion and reuse status.

Checks: source fingerprints match; no unclassified spans without a gap; call/data
dependencies resolve or block; all source units accounted for; metadata is pinned.

## Task 3 — Prove the full-trace path before broad conversion

Owners in parallel: design/backend for the smallest existing-runtime capture
approach; QA for independent acceptance and fault cases. Audit reviews results.
Skills: `consult-modernization`, `validate-program`.

- Pick a representative shared program with a business rule, Db2 access and an
  applicable installed Sparkflows transformation; record why it is representative.
- Define stable occurrence/version, rule, invocation, attempt, event and lineage
  identities. Use the logical entities in technical-reference Section 9.
- Add only the minimal versioned contracts and validators needed by the existing
  test stack. Validate source maps, cases, manifests and trace references.
- Capture actual Python/SQL/flow outcomes and complete contributors; never claim a
  later expression rerun observed the original execution. Check available legacy
  instrumentation separately from output parity.
- Exercise duplicate input keys, rejection, no-output, short circuits, joins,
  splits, aggregates, retry, rollback and evidence-write failure. Measure overhead,
  throughput and retained size. Stop an unsupported implementation choice early.

Checks: every input occurrence has intake and terminal evidence; every effect has
complete lineage; observed events match required capture sites; missing evidence
fails the gate. Count agreement alone is insufficient. No per-record model calls.

## Task 4 — Convert and validate the canonical pilot

Owners in parallel: backend implements approved behavior; QA derives independent
expectations and fixtures. Design resolves contracts; frontend improves only the
existing review interface when needed. Skills: `modernize-process`,
`validate-program`.

- Pin accepted SME decisions and source/DB/reference/runtime fingerprints.
- Keep business logic small; isolate codecs, I/O, transactions and capture. Use
  actual Sparkflows processors where applicable and version the executed flow.
- Generate at least 100 meaningful distinct positive and 100 negative unit data
  cases per business rule. Record expected-result provenance and outcome classes.
  Use appropriate technical tests without an artificial 200-case quota.
- Execute tests on actual target units, SQL and flows. Add interaction, restart,
  idempotency, rollback and selected mutation/fault tests.
- Record commands, inputs, assertions, results and immutable receipts under the
  program's tests/runs/evidence structure. Keep real data outside model context.

Checks: every required rule's separate quotas are met; negative cases assert the
correct negative behavior; independent oracle; no hidden defaults, duplicated
logic, speculative wrappers or swallowed errors; measured resource behavior.

## Task 5 — Reconcile with the mainframe and prove reuse

Owners: DevOps prepares the exact packet; QA compares results; analytics verifies
trace completeness; gap analysis updates the side-by-side evidence; audit signs
off independently. Skill: `validate-program`.

- Build `programs/<id>/runs/<run-id>/mainframe/packet.json` using Section 4.4 and
  the validation skill's mainframe reference. Bind cloned test JCL, synthetic
  input/Db2 state, reset, effects isolation, capture, budgets and recovery.
- Use a compatible immutable observed baseline or execute only in the permitted
  test envelope. Current upload/submit denials require owner resolution first.
- Compare full duplicate-sensitive records/files and DB effects, return behavior
  and required traces. Document every normalization and intentional difference.
- On discrepancy, classify implementation, fixture, baseline, environment or
  business-decision cause. Repair only within the bound; preserve failed evidence,
  invalidate affected results and rerun from reproducible state.
- Validate a second consumer against the pinned canonical program, including
  parameter/transaction/context differences. Do not claim all consumers accepted.

Checks: no unexplained parity differences; complete every-record evidence;
source-to-executable correspondence; uncertainty reconciled before resubmission;
two independent accepted process integrations where reuse is claimed.

## Task 6 — Scale, retain knowledge and prepare release

Owner: lead; assign specialists only when needed. Skill: `modernize-process`.

- Expand eligible independent programs two workers at a time. Avoid concurrent
  writes to the same paths or mutable test schema; isolate state or serialize.
- Keep `inventory.json` current with exact accepted versions, consumer coverage,
  gaps, evidence and invalidation. Update `knowledge/decisions.json` and
  `knowledge/handoff.json` with concise facts, receipts, ownership and next action.
- Reuse hash-matched analysis/baselines, not stale success. Measure tokens per
  accepted program and runtime/storage cost. Tune only from observed results.
- Audit all acceptance gates before release. Production coexistence, rollback/data
  repair, access, retention and operating SLOs require their own approval.

Checks: no stale evidence or orphan programs; denied/unknown remains visible;
handoff survives session restart; permissions and model pin preserved; every
accepted run satisfies full trace and every claimed consumer has integration proof.

## Parallelism and stop rules

The lead is the sole writer of shared inventory/decision state. Workers own
disjoint program/task paths and return hashes and compact receipts. Independent
analysis/metadata and implementation/test design can proceed in parallel; evidence
publication waits for review. Mutable shared Db2 state is never assumed isolated.

Stop only affected work on a business ambiguity, explicit access denial, missing
required evidence, stale source/state, uncertain remote effects, exhausted numeric
budget or two failed repair cycles. Continue unrelated permitted tasks. Ask SMEs
for behavior decisions and environment owners for capability/policy decisions;
neither is a substitute for engineering verification.
