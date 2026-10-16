# Run the agent workflow

This branch is a clean Claude Code operating kit. It retains optional instruction
packages from `modernization-factory`; it does not start the old Python workbench.

## First workstation setup

1. Check out `modernization/clean-agent-kit` and open the folder in the approved Claude
   Code VS Code extension. A branch does not install extensions, credentials or
   machine-level plugins. Inspect the workstation's existing configuration.
2. Run `python tools/check_kit.py` (or `py tools/check_kit.py` on Windows). This
   checks the kit only. It never connects to the mainframe or invokes a model.
3. Check `/model`: use the approved Opus 4.7 ID. For Anthropic naming it is
   `claude-opus-4-7`; a managed gateway may require a different verified ID. If so,
   update the explicit model fields together without adding a fallback. Inspect
   effective settings and `/tasks` during a worker smoke test. The force setting
   requires Claude Code 2.1.257 or later; if unsupported, stay in the pinned
   foreground session until the host can guarantee the same model for delegates.
4. Confirm that the lead and eight specialists load and that the three core skills
   are discoverable. If `.claude/agents` was new to an already-open session, restart
   the session. Use the configured foreground `pts-orchestrator`; do not spawn a
   second lead. Have the lead call one worker on a small synthetic source fixture
   and inspect its actual model. This repository has not run that host smoke test.
5. Review effective `/permissions` once with the environment owner. The supplied
   `dontAsk` policy runs allowed actions without routine prompts and blocks other
   actions. Existing mainframe upload/submit/delete denials remain. Do not use
   bypass mode or alternate tools to evade them. Configure exact local Python test
   commands through approved settings; null bindings are deliberate blockers.
6. Reuse your configured Zowe CLI and Db2 MCP server. Do not install another
   connector by default. With the environment owner, verify the actual MCP tool
   catalog, Zowe version/profile, account permissions and approved resources. Bind
   exact allowed MCP tools to the relevant agent tool lists and host permissions;
   do not guess tool names or grant wildcard SQL access. Existing denies remain.
   Follow technical-reference Sections 4.1–4.3 and record non-secret receipts in
   `.implementation/workstation.json`. A Db2 MCP binding is not a Zowe Db2 profile.
   Bind source access in `config/project.json` or protected local configuration.
   Sparkflows examples, profiles and `commands.etl` are deferred; missing bindings
   do not block current Python implementation or its unit/integration tests.
   The photo confirms `TSTSN.#RW477*`; live
   enumeration is still required. Model-visible source must be approved sanitized
   content. Keep private inputs and outputs in the ignored working folders.
7. Bind the approved indexed trace/evidence store and retention policy in
   `config/project.json`. Every processed record needs complete rule-event,
   lineage and effect evidence under technical-reference Section 9. No sampling;
   missing trace evidence blocks acceptance. These bindings are not configured here.
8. Set numeric task/token/time/query/storage limits once and record their protected
   binding in `execution.budget_binding`. Unset is not unlimited. Run the readiness
   and representative-pilot tasks in [the implementation plan](docs/IMPLEMENTATION_PLAN.md)
   before scaling to the program inventory. Batch unresolved setup items into one
   owner handoff; continue unrelated allowed work.

## Start, review and resume

In Claude Code, invoke:

```text
/modernize-process Inventory every program under the configured source reference.
Classify business and technical rules per program. Use the supplied process
manifest for conversion order. Preserve compatible conversions, collect SME
questions in one review workbook, and continue all unblocked work.
```

The lead assigns only needed specialists, at most two simultaneously by default.
For an existing program use `/validate-program` with its ID and pinned source/target
versions. For an architecture, delivery or cost decision use `/consult-modernization`.
All work follows [the technical specification](docs/TECHNICAL_REFERENCE.md).
Follow [the application operating guide](docs/APP_MODERNIZATION_GUIDE.md) for the
complete sequence, exact commands and required artifacts per phase. Each program
gets a compact compatibility profile, all-rule data cases, current Python results
and reproducible bundles for failures. The local rule runner requires 100 passing
positive and 100 passing negative cases per executable business, technical or mixed
rule; it does not establish whole-program or mainframe acceptance by itself.

Implement business logic and simple ETL in Python now. Put short
`ETL-LATER (Sparkflows)` comments beside eligible ETL functions using the Section 7
convention. Keep actual Python source, tests and every-record evidence current;
future migration annotations are plans, not completed flow evidence.
The lead maintains [one running migration document](docs/SPARKFLOWS_MIGRATION.md).
Ask it to show flow cards, available/missing artifacts, dependency order and which
Python functions/callers each flow will replace. Each code comment links to its
card. Later, switch a validated step through its documented binding; retire shared
Python only after every consumer and in-flight version is accounted for.

SMEs edit the business-decision cells in the process review workbook. Engineering
fills classification, technical treatment, reuse, replacement names and evidence.
Use the workbook's **Review home** link for navigation and **Record Trace** to
inspect a run and record occurrence. Follow the [workbook guide](docs/WORKBOOK_GUIDE.md)
to replace the fictional demonstration with an authorized evidence export.
Return real answers with attribution. The lead ingests revisions and reruns affected
work. Technical repair proceeds within the configured two-cycle budget without
repeated confirmation. Business ambiguity and blocked access remain explicit.

Before closing the extension, save the handoff. To resume, ask the lead to read
`knowledge/handoff.json`, verify recorded versions and continue the next eligible
task. The kit has no background daemon and makes no guarantee of running after the
IDE session closes.

## Mainframe comparison

DevOps prepares a concrete isolated test packet using
[the mainframe playbook](.claude/skills/validate-program/references/mainframe.md).
It specifies exact datasets, JCL changes, fixtures, Db2 state, expected effects,
capture, reset and recovery. Current repository denials prevent direct execution.
An authorized environment owner must resolve that policy before execution is
enabled; the lead records the resulting permission and review envelope once.
Existing verified baselines may be reused only when their fingerprints match.

## Included and not yet verified

- Included: lead plus eight specialist definitions, three core skills, fifteen
  retained optional instruction packages/licenses, single-model settings,
  source-reference transcription, workbook and compact operating specification.
  Five standard-library evidence utilities and their synthetic regression tests
  are executable locally. Run `python -m unittest discover -s tests -v`.
- Not established by this kit: installed runtime plugins, Graphify availability,
  live mainframe/Db2/Sparkflows connectivity, real source conversion, Claude-host
  execution, performance improvements or parity. Record each only after observation.
