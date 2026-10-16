# Run the agent workflow

This branch is a clean Claude Code operating kit. It retains optional instruction
packages from `modernization-factory`; it does not start the old Python workbench.

## First workstation setup

1. Check out `modernization/clean-agent-kit` and open the folder in the approved Claude
   Code VS Code extension. A branch does not install extensions, credentials or
   machine-level plugins. Inspect the workstation's existing configuration.
2. Run `python tools/check_kit.py` (or `py tools/check_kit.py` on Windows). This
   checks the kit only. It never connects to the mainframe or invokes a model.
   The checker covers required files and the pinned permission/license baseline;
   it also checks historical Git bytes when that history is available. Then run
   `python tools/init_workspace.py --root .` through the approved local binding.
   This creates missing local inventory/memory files and preserves existing state.
   See [the folder guide](docs/FOLDER_STRUCTURE.md) before supplying program IDs.
3. Check `/model`: use the approved Opus 4.7 ID. For Anthropic naming it is
   `claude-opus-4-7`; a managed gateway may require a different verified ID. If so,
   update the explicit model fields together without adding a fallback. Inspect
   effective settings and `/tasks` during a worker smoke test. The force setting
   requires Claude Code 2.1.257 or later; if unsupported, stay in the pinned
   foreground session until the host can guarantee the same model for delegates.
   Project and agent effort is explicitly `xhigh`. Follow
   [the quality guide](docs/OPUS_QUALITY.md) to verify effective effort/routing,
   memory imports and held-out results. These settings do not establish 5.5 parity.
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

To remove converted behavior, use
`/modernize-process remove-rule <PROGRAM_ID> <RULE_ID> reason="<NEW_BEHAVIOR>"`.
Add `process=<PROCESS_ID>` for one consumer or `plan-only` to preview. The
[removal guide](docs/RULE_REMOVAL.md) covers shared dependencies, a reversible
patch, absence-of-effect tests, retained-rule validation and evidence updates.

## Mainframe comparison

DevOps prepares a concrete isolated test packet using
[the mainframe playbook](.claude/skills/validate-program/references/mainframe.md).
It specifies exact datasets, JCL changes, fixtures, Db2 state, expected effects,
capture, reset and recovery. Current repository denials prevent direct execution.
An authorized environment owner must resolve that policy before execution is
enabled; the lead records the resulting permission and review envelope once.
Existing verified baselines may be reused only when their fingerprints match.

## Included and not yet verified

For progress tracking, follow [PROGRESS_UI.md](docs/PROGRESS_UI.md). The lead exports
one sanitized inventory snapshot; the local UI shows totals, completed versus
converted work, rule counts, gates, blockers and Sparkflows dependencies. Its
demonstration is explicitly fictional. Use [SECURITY_REVIEW.md](docs/SECURITY_REVIEW.md)
for separate remediation, QA and independent adversarial review before promotion.

Optional tool installation is pinned in [TOKEN_EFFICIENCY.md](docs/TOKEN_EFFICIENCY.md)
and [REA_DESIGN_RESEARCH.md](docs/REA_DESIGN_RESEARCH.md). Graphify's scoped parser
and REA were installed and exercised in the build workspace. Activate only their
reviewed paths through the workstation's existing permission process; no global
hooks, extra model routing or credentials are installed by the kit. The optional
Graphify adapter requires a verified POSIX/WSL binding on Windows.

- Included: lead plus eight specialist definitions, three core skills, fifteen
  retained optional instruction packages/licenses, single-model settings,
  source-reference transcription, workbook and compact operating specification.
  Five standard-library evidence utilities and their synthetic regression tests
  are executable locally. Run `python -m unittest discover -s tests -v`.
- Not established here: plugin activation in your VS Code host, REA browser capture,
  live mainframe/Db2/Sparkflows connectivity, real source conversion, Claude-host
  execution, provider-token savings or model equivalence. Record each after observation.
