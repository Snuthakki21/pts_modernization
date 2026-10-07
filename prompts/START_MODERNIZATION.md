# Start modernization with the existing workbench

This is the single execution prompt for GitHub Copilot, Claude Code and other
agents. Repository entrypoints: [AGENTS.md](../AGENTS.md) and
[CLAUDE.md](../CLAUDE.md), with automatic Copilot repository instructions in
[.github/copilot-instructions.md](../.github/copilot-instructions.md). Folder contract:
[docs/TECHNICAL_REFERENCE.md](../docs/TECHNICAL_REFERENCE.md).

### Host roles and local-file handoff

**GitHub Copilot in VS Code retrieves information only.** It uses the organization's
already approved MCP connections for read-only discovery and source/catalog pulls.
Use exact request identities, environment, original member names and return paths.
Write source and metadata into the designated local folder with provenance and
hashes, report missing/ambiguous/denied results, then stop. Do not assign business
analysis, development, integration, testing or review to Copilot.

**Claude Code owns local analysis and implementation.** The organization-approved
VS Code extension is allowed; Claude has **no MCP servers**. Read approved local
source exports, process notes and evidence. Do the lineage interpretation,
requirements analysis, coding, test generation, unit/scenario tests, independent
adversarial review and reporting. Never install or invoke a Claude MCP server,
route Claude through Copilot, or tunnel remote/MCP access through shell or HTTP.
`examples/claude-mcp.json` deliberately contains only an empty `mcpServers` object.

Inspect the current local task with:

```sh
python -m workbench.runner agent PROCESS_ID --workspace WORKSPACE
```

When information is absent, create a bounded request using
`agent PROCESS_ID --workspace WORKSPACE --request-file REQUEST_JSON` and deliver
the generated prompt for the user to paste into Copilot. The immutable request is
`processes/PROCESS_ID/analysis/retrieval/REQUEST_ID/request.json`; collected files
belong in that request's `inbox/files/` and the return manifest in
`inbox/response.json`. Use the advertised request/response schema and exact paths;
do not guess a return folder, accept a different request's return, or treat a
partial/ambiguous result as complete. `REQUEST_JSON` contains only a `needs` array
of objects with `kind`, `name`, `reason` and any supported evidence fields. Keep
the original source identity in response `path`; when staging requires a `.txt`
name (for example a `.md` source), use optional `staged_path` for that inbox
filename. Follow the packet schema; never execute returned source. Retrieval
requests are not SME questionnaires. Default requests batch at most 128 needs
with total/remaining counts while retaining complete lineage. A FOUND receipt
must still match a unique parsed kind/name and source path/hash before resolving
the need. Unknown metadata remains an obligation. NOT_FOUND or AMBIGUOUS returns
stop at a checkpoint; do not issue the same request automatically again.

When the user says **Continue**, run
`agent PROCESS_ID --workspace WORKSPACE --continue`. The Coordinator validates
identities, paths and file hashes, preserves accepted evidence, and resumes only
eligible work. Read the resulting task/evidence paths, continue independent local
work, and request only the remaining missing information. After tested adapter
changes use `--refresh`; submit current hash-bound analysis with
`--analysis-file ANALYSIS_JSON`. Actual usage receipts use `--measurement-file FILE`.

These commands use the existing Coordinator. If its UI is running, the runner
writes a bounded local command to `.migration/agent-commands/COMMAND_ID.json`
and waits for `.migration/agent-results/COMMAND_ID.json`; it does not connect to
an MCP server or HTTP service. The running Coordinator is the only writer. If an
older service cannot consume the command, restart the existing launcher instead
of starting another writer. PENDING (exit 3) may be retried with the same command
ID and identical payload. INDETERMINATE (exit 2) preserves a durable start marker
and never reexecutes that ID: inspect current state using a fresh agent command
before deciding any new mutation. Never delete markers or silently replay.
Atomic publication requires a local filesystem supporting hard links; unsupported
filesystems fail closed. These commands never give Claude MCP or remote access.

Claude executes the lifecycle below using this local workflow. Preserve read-only
mainframe access, frozen evidence and one authentic human SME round. Never
fabricate review answers, mark unanswered questions Yes, or use a model assertion
to clear a gate. The agent does not establish a second conversion engine.

Load only the relevant shared skills from `.claude/skills/`: mainframe-discovery,
mainframe-semantics, mainframe-target and mainframe-assurance. Claude Code and
VS Code Copilot use these same skill files. No separate workflow is installed.

1. Use the configured Python environment from `START_HERE.md`. Identify the
   user-supplied manifest and workspace. The manifest names the stable process
   ID and ordered jobs/steps, or online transaction/program/map bindings. The workspace must contain the selected local,
   read-only `Endeavor/` export. Only Copilot uses already approved MCP connections
   to retrieve missing source and bounded read-only Zowe/Db2 metadata. Conversion
   requires the complete local export snapshot. Do not execute legacy programs,
   submit jobs, upload source, perform mainframe writes, or add unrestricted
   connectors/tools to bypass the read-only boundary.
   A supplied folder can be snapshotted with `--source-folder SOURCE_FOLDER`;
   it is copied into immutable process input without altering the original.
   Preserve supplied process Markdown with `--process-notes PROCESS_MD`.
   For ordinary prose, derive the canonical manifest from cited document/JCL facts
   under `.implementation/tmp/`; do not ask the operator to reformat known facts.
   Missing or conflicting job identities remain discovery prerequisites.
   Run `python -m workbench.layout --workspace WORKSPACE`. Keep transient scratch
   under `.implementation/tmp/`, not a root directory beginning with `tmp`.
   Correct newly created
   misplaced files without moving or editing frozen source/evidence. Stop on
   missing intake facts, unsafe paths, failed preflight or another writer;
   diagnose the named cause rather than bypassing a gate.
   Read `knowledge/README.md`, `knowledge/mainframe-catalog.json`, the workspace's
   `knowledge/application-knowledge.json` when supplied, and `docs/TECHNICAL_REFERENCE.md`.
   Run `python -m workbench.preflight --workspace WORKSPACE --manifest MANIFEST --json`;
   include the same `--source-folder` and `--process-notes` options when supplied.
   Resolve local setup/intake blockers before Start. A blocked conversion profile
   may still be analyzed and reported, but cannot be declared converted. Keep
   configuration, reachability, classification and verified support distinct.
   Classify from source structure and dependency evidence; names/suffixes alone
   are insufficient. Check the native-semantic topics and every utility's
   required evidence, including wrappers and control cards. Use the visible
   application catalog for custom facts, preserving unknowns and provenance.
   A catalog entry never authorizes an adapter or execution. Every new process
   freezes its exact knowledge; Resume must use that original snapshot.
2. Execute:

   ```sh
   python -m workbench.runner run --manifest MANIFEST --workspace WORKSPACE --assistant claude_files --select-requirements
   ```

   `start` is an alias of `run`. Intake reads `WORKSPACE/Endeavor/` automatically.
   An existing process ID is reused only with the recorded immutable manifest
   SHA-256 (both supplied bytes and pinned snapshot must match) and an
   intact source snapshot. Repeated Start preserves the original packet/hash.
   Historical runs without a recorded baseline fail closed; never derive a new
   baseline from mutable files during Resume.
   Changed input requires an explicitly selected new process ID. Start does
   not resume a paused or failed process; inspect and use `resume` explicitly.
3. First map job/PROC/program/COPY/include/dataset/Db2/CICS/scheduler/interface
   dependencies. Retain and index the entire export; select conversion scope by
   transitive evidence. Resolve locally first, then generate a specific Copilot
   retrieval request for missing files or metadata. `WAITING_DISCOVERY` means a missing, ambiguous or
   dynamic binding must be resolved before conversion or questions. Never invent
   dataset names or turn an unknown count into zero. WEDLX/Tran Repository folder
   bindings belong in `knowledge/input-locations.json`. TPX session names are
   routing hints and require actual service/profile mappings.
   With the UI running, use the local agent command inbox, never a second writer.
   `WAITING_REQUIREMENTS` exposes the full source breakdown with default Yes.
   Direct the operator to the UI requirements screen for an explicit Save. Do not
   impersonate that Save or treat default scope as SME approval. Read the resulting
   pinned local requirements Markdown and its immutable artifact reference.
   Convert only selected Yes units; retain No units with the exact reason
   "Not converted because selected No in requirements." and source evidence.
   Preserve required-dependency gaps; no exclusion proves unknown semantics safe.
   After adapter refresh changes the catalog, a new scope Save is required before
   conversion. Prior scope/analysis evidence and the single SME quota stay intact.
   Use `python -m workbench.runner agent PROCESS_ID --workspace WORKSPACE` to
   read the frozen task and local source, context, rule and obligation evidence.
   No Claude MCP server or model endpoint/token is required. Claude implements
   missing adapters, integrates changes and runs meaningful tests and independent
   review. Submit structured context with `--analysis-file ANALYSIS_JSON`;
   validation binds structure and lineage, not conversion correctness. Preserve
   unsupported semantics. Adapter changes require `--refresh` and a fresh task;
   never rewrite frozen artifacts or clear blockers by changing flags.
   Credits remain Unknown without actual provider/account usage receipts.
   Read the complete pinned obligations and relevant indexed process Markdown.
   Submit `rule_classifications` with a source-grounded reason for each classified
   rule; uncertain rules remain unclassified. Never classify business versus
   technical behavior from IF syntax alone. Use I*/Z* names only as
   environment-scoped candidate matches, not automatic substitutions.
   Continue independent tasks through implementation/test/refresh. Do not repeat
   identical failed approaches; preserve attempts and exact missing prerequisites.
   The single packet is then issued at `WAITING_SME`. Deliver its paths, including
   `sme-checklist.xlsx`, to the user. Explain any source blockers and the
   source-derived evidence boundary. Preserve the packet's Context, IDs,
   questions and fingerprint. Ask the human to complete that one workbook and
   provide the actual reviewer name. Then wait. Do not edit any answers yourself.
4. The returned workbook goes in exactly:

   ```text
   WORKSPACE/processes/PROCESS_ID/input/sme-return-inbox.xlsx
   ```

   Resume after the actual return with attribution:

   ```sh
   python -m workbench.runner resume PROCESS_ID --workspace WORKSPACE --reviewer "ACTUAL REVIEWER"
   ```

   Or import an explicitly supplied workbook:

   ```sh
   python -m workbench.runner import PROCESS_ID --workspace WORKSPACE --file RETURNED_WORKBOOK --reviewer "ACTUAL REVIEWER"
   ```

   For a local operator who already knows the reviewer, `run`/`resume` may use
   `--watch --reviewer "ACTUAL REVIEWER" --timeout 3600`. Watch waits at the
   designated inbox and automatically queues verification/reporting when the
   authentic return arrives. It never fabricates a return. All waits are
   bounded: default 120 seconds, maximum 3600. Exit code 3 means the bound was
   reached; inspect status and rerun resume. Non-watch agents exit at
   `WAITING_SME` and can continue after the user supplies the workbook.
   Have the user finish writing the workbook before placing it in the inbox;
   use an atomic rename when possible.
5. Import checks the frozen packet, hashes the return and consumes the one
   review quota atomically. The service preserves the accepted file as
   `input/sme-return.xlsx`. An identical return with the same attribution is an
   idempotent import; a different second return is refused. No/Not sure,
   missing answers or corrections remain unresolved. Do not create another
   SME round to turn blockers into success.
6. Inspect generated coverage, tests, target comparisons, adversarial evidence
   and reports. Account for every selected exported file and line, including
   copybooks, JCL, BMS, SQL and unrecognized text. Every omission needs a
   disposition and reason. Do not call unsupported syntax a mainframe-only
   feature by default. Mainframe-specific/platform behavior needs a concrete
   replacement and verification evidence before it can be credited.
   Source-derived oracles do not establish observed mainframe parity.
   Include classification conflicts, custom utility details, record formats and
   runtime assumptions in the existing single checklist before its issue. The
   service includes these in Context. SME approval cannot turn an unsupported
   construct into supported code. Preserve corrections as unresolved facts;
   do not silently convert prose into executable semantics. New generated target
   contracts validate their own inputs; regression tests must call the exported
   target on malformed inputs rather than pre-rejecting them in a test harness.
   Run real regression tests for any engine changes and perform an adversarial
   review before claiming completion. Inspect unmet gates rather than relying
   on a green label alone. Preserve failed and blocked evidence.
   Validate every business and technical source logic obligation. Require at least 20
   distinct runtime-randomized source-valid records per applicable supported logic item, every
   decision outcome, boundaries, sequential effects, errors and invalid layouts.
   Related files/tables use consistent referral/product/key values and explicit
   unmatched/duplicate/missing/empty cases where source-supported adapters exist.
   Generate expectations from source rules before executing Python; compare full
   outputs, traces and return codes, then perform adversarial review. Unsupported
   logic gets no fabricated expectations or verification credit. Keep complete
   source/target/test/reason mappings in coverage artifacts, not per-rule Markdown.
7. Use the diagnostic/continuation commands as needed:

   ```sh
   python -m workbench.runner status PROCESS_ID --workspace WORKSPACE
   python -m workbench.runner resume PROCESS_ID --workspace WORKSPACE
   python -m workbench.runner report PROCESS_ID --workspace WORKSPACE
   python -m workbench.runner bundle PROCESS_ID --workspace WORKSPACE
   python -m workbench.layout --workspace WORKSPACE
   ```

   Status returns blockers, packet/report paths and a continuation command.
   Resume retries only eligible service states and keeps the SME quota.
   Report exposes preserved report paths and can resume a failed report stage;
   it does not silently replace terminal evidence. Bundle creates/reuses an
   immutable, registered ZIP containing intake/source snapshots, the review
   packet/accepted return, coverage reports, target artifacts, synthetic
   comparisons and the management PowerPoint where generated.
   The UI and CLI share a single-writer lock. The `agent` command uses its local
   command inbox when the UI is running. Other direct-writer CLI commands require
   stopping the UI first; never create an MCP/HTTP workaround for Claude.
8. Deliver job/program rule totals, separately for business rules and technical
   logic, with original source versus modernized implementation and test evidence.
   Successfully converted means verified, not merely generated. Unknown spans
   remain visible; grouping questions never changes the rule inventory. Deduplicate
   repeated invocations within job totals and preserve cross-job memberships.
   Deliver one primary `executive-report.html` with simple counts and next actions.
   Keep the management PPT and evidence bundle available on request. Do not
   produce another narrative Markdown report. Historical reports lacking the
   new executive report remain unchanged. Include a precise result. Distinguish
   `COMPLETED`, `COMPLETED_WITH_BLOCKERS`, cancelled, failed and timed-out work.
   Name unresolved behavior and coverage gaps. Never assert zero bugs,
   production readiness, full mainframe parity or verification unsupported by
   actual evidence. Keep future outputs in the documented folders.

For an online-first process, use the transaction manifest table documented in the
technical reference; do not fabricate jobs. Read the local factory projection,
all obligations and transaction/program/map bindings. Select the smallest
complete transaction chain if the supplied process identifies multiple candidates
without priority, recording the rationale in the existing structured analysis.
Investigate source-version documentation, existing adapters, tested equivalents
and explicit target design alternatives before recording an unresolved obligation.
Prefer a modular Python business application with APIs and SQLite. Extract a
service only with evidenced responsibility, data ownership and transaction
boundaries. Local record-API/form candidates do not replace unimplemented CICS,
BMS, native persistence, identity or recovery behavior. Continue those adapter
obligations rather than interpreting candidate generation as completed migration.
Run `python tools/check_factory.py` after implementation changes, focused boundary
regressions and the mandated release checks. Native platform CI and real agent-host
acceptance must actually run before claiming those environments verified.

### Observe effort and learn the remaining estate

Use the existing effort panel for real work windows (discovery, mainframe reads,
conversion, SQL, validation and rework). Record framework investment separately.
Close clocks before waiting on a human or restarting; an interrupted clock is
Unknown, never guessed downtime. Claude imports actual available host credit
receipts through `agent --measurement-file FILE`; the existing UI can also import
them. Copilot may retrieve an available credit receipt as a file, but does not
perform implementation work or own its measurements. Credits are the budget unit.
Never estimate credits from tokens or infer a quota from configuration.
Whole-pilot effort/billing coverage requires complete attributed evidence, not
merely a successful import or elapsed clock.
After each migration, inspect the existing Effort & scale projection: accepted source scope,
dependencies, generated artifacts, rules, validation, waits and measured effort
inform the remaining same-unit cohort. Retain provider/account identity, explicit
rate assumptions, excluded samples and missing measurements. Calibration sample
selection is separate from completed estate scope. Update an existing scenario
only with evidence; frozen reports retain their original numbers. Use the
technical reference for bounded receipt contracts and conditional forecasts.
