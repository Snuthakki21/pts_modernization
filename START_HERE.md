# Run the agent workflow

Open `modernization/clean-agent-kit` in the approved Claude Code VS Code extension.
This kit does not start the old workbench or install workstation credentials,
extensions or upstream plugin runtimes.

## Bind the workstation once

1. Run `python tools/check_kit.py` (`py` on Windows). It checks kit files and the
   pinned permission/notice baseline, not connectivity or model execution.
   Through the approved local binding, run `python tools/init_workspace.py --root .`.
   It creates missing state without overwriting decisions or budgets. Use the
   [folder guide](docs/FOLDER_STRUCTURE.md) before supplying program/process IDs.
2. Follow [OPUS_QUALITY](docs/OPUS_QUALITY.md) to verify actual foreground, worker
   and evaluator Opus 4.7 routing, `xhigh` effort and loaded memory. The delivered
   ID is `claude-opus-4-7`; verified gateway mappings must update all pins together.
   No fallback. Confirm the lead, eight specialists and three core skills load;
   restart an existing session if necessary. Run a synthetic worker smoke test
   and inspect `/tasks`. If worker routing is unsupported, stay in the verified
   same-model foreground until resolved.
3. Review `/permissions` with the environment owner. `dontAsk` runs allowed
   actions and blocks others; preserve denials, with no bypass. Reuse your Zowe
   CLI and Db2 MCP. Verify versions, profiles, actual tool names and resources;
   bind exact local test commands and connector permissions through the approved
   process. Never guess tools or grant wildcard SQL access. A Db2 MCP binding is
   not a Zowe Db2 profile. Follow [technical-reference Sections 4.1–4.3](docs/TECHNICAL_REFERENCE.md)
   and keep non-secret receipts in `.implementation/workstation.json`.
4. Bind approved source access in `config/project.json` or protected local
   configuration. The photo confirms `TSTSN.#RW477*`; live enumeration is pending.
   Populate approved sanitized `Endevor/` views and use
   [the navigation runbook](docs/ENDEVOR_NAVIGATION.md) for OKF build/check and
   permitted Db2 MCP/Zowe fallback. Keep private inputs/outputs ignored. A denied,
   partial or failed query is not object absence.
5. Bind the indexed trace store, retention/access policy, numeric task/token/time/
   query/storage limits and `execution.budget_binding`. Missing bindings block
   dependent work; unset limits are not unlimited. Every accepted run needs
   unsampled record traces under technical-reference Section 9. Sparkflows
   bindings are deferred. Run the readiness and representative pilot in
   [the implementation plan](docs/IMPLEMENTATION_PLAN.md) before scaling. Batch
   setup blockers into one owner handoff; continue unrelated permitted work.

## Start and continue

Use the foreground `pts-orchestrator`, with at most two specialists:

```text
/modernize-process Inventory every program under the configured source reference.
Classify business and technical rules per program. Use the supplied process
manifest for conversion order. Preserve compatible conversions, collect SME
questions in one review workbook, and continue all unblocked work.
```

Use `/validate-program` with an existing program ID and pinned versions, or
`/consult-modernization` for architecture/delivery/cost decisions. The
[application guide](docs/APP_MODERNIZATION_GUIDE.md) gives phase inputs, commands
and handoffs: compatibility profiles, independent 100-positive/100-negative
cases per executable rule, Python results and reproducible failures. Local case
results alone do not establish whole-program or mainframe acceptance.

| Activity | Procedure |
|---|---|
| SME review | Issue one versioned process workbook; SMEs edit business decisions and agents fill technical fields/evidence. Ingest attributed revisions and rerun affected work. [WORKBOOK_GUIDE](docs/WORKBOOK_GUIDE.md) explains **Review home**, **Record Trace** and replacing fictional examples with authorized exports. |
| Python ETL now | Use Section 7's `ETL-LATER (Sparkflows)` comments and stable migration IDs. Maintain [one register](docs/SPARKFLOWS_MIGRATION.md) of flow cards, artifacts, dependencies, callers, switch/rollback and retirement conditions. Planned flows are not execution evidence. |
| Goals/monitoring | Use [CLAUDE_CODE_WORKFLOW](docs/CLAUDE_CODE_WORKFLOW.md) and [paste-ready prompts](prompts/GOAL_WORKFLOW.md); verify the separate evaluator route first. Loops monitor existing work only. |
| Resume | Save `knowledge/handoff.json` before compaction/closure. Verify fingerprints, remaining budgets, unresolved effects and next action. Preserve zero budgets. The kit has no background daemon or guarantee of running after IDE closure. |
| Remove logic | Use `/modernize-process remove-rule <PROGRAM_ID> <RULE_ID> reason="<NEW_BEHAVIOR>"`, optionally `process=<PROCESS_ID>` or `plan-only`. Follow [RULE_REMOVAL](docs/RULE_REMOVAL.md) for reversible changes and dependency/retained-rule checks. |
| Progress/review | Export sanitized inventory via [PROGRESS_UI](docs/PROGRESS_UI.md); apply separate remediation, QA and independent audit under [SECURITY_REVIEW](docs/SECURITY_REVIEW.md). The UI cannot approve work. |

Load Ponytail for design/build/repair. Follow [TOKEN_EFFICIENCY](docs/TOKEN_EFFICIENCY.md)
for the five context techniques and optional pinned Graphify setup, including its
approved POSIX/WSL binding. Do not activate generic hooks or other-model routes.
Keep evidence, business ambiguities, access blockers and the original two-cycle
repair allowance intact.

## Compare against the mainframe

DevOps prepares the [isolated test packet](.claude/skills/validate-program/references/mainframe.md):
exact datasets, JCL changes, synthetic fixtures, Db2 state, effects, capture, reset
and recovery. Existing denials prevent direct execution; the environment owner
must resolve policy before enabling it. Record that envelope once. Reuse verified
baselines only when fingerprints match.

[Kit evidence](docs/evidence.json) records observed checks and limitations.
Workstation/model operation, live connectivity, real conversion, rendered UI
checks, token savings and model-quality claims require their own execution receipts.
