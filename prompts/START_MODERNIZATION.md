# Start modernization with the existing workbench

This is the single execution prompt for GitHub Copilot, Claude Code and other
agents. Repository entrypoints: [AGENTS.md](../AGENTS.md) and
[CLAUDE.md](../CLAUDE.md), with automatic Copilot repository instructions in
[.github/copilot-instructions.md](../.github/copilot-instructions.md). Folder contract:
[docs/TECHNICAL_REFERENCE.md](../docs/TECHNICAL_REFERENCE.md).

You are operating the existing service-backed modernization workbench. Execute
the workflow using its Coordinator CLI and deliver its concrete artifacts.
Do not stop at proposing commands. Do not implement a separate conversion
engine. Preserve the read-only mainframe boundary, frozen evidence and one
human SME round. Never generate answers, mark unanswered questions Yes, or
substitute agent reasoning for reviewer approval.

1. Use the configured Python environment from `START_HERE.md`. Identify the
   user-supplied manifest and workspace. The manifest names the stable process
   ID and ordered jobs/steps. The workspace must contain the selected local,
   read-only `Endeavor/` export. User-authorized configured typed read operations
   may retrieve source and bounded read-only Zowe/Db2 discovery. Conversion
   requires the complete local export snapshot. Do not execute legacy programs,
   submit jobs, upload source, perform mainframe writes, or add unrestricted
   connectors/tools to bypass the read-only boundary.
   Run `python -m workbench.layout --workspace WORKSPACE`. Keep transient scratch
   under `.implementation/tmp/`, not a root directory beginning with `tmp`.
   Correct newly created
   misplaced files without moving or editing frozen source/evidence. Stop on
   missing intake facts, unsafe paths, failed preflight or another writer;
   diagnose the named cause rather than bypassing a gate.
   Read `knowledge/README.md`, `knowledge/mainframe-catalog.json`, the workspace's
   `knowledge/application-knowledge.json` when supplied, and `docs/TECHNICAL_REFERENCE.md`.
   Run `python -m workbench.preflight --workspace WORKSPACE --manifest MANIFEST --json`.
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
   python -m workbench.runner run --manifest MANIFEST --workspace WORKSPACE --assistant copilot_chat
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
   transitive evidence. Resolve locally first, then use configured typed
   read-only Zowe/Db2 lookup. `WAITING_DISCOVERY` means a missing, ambiguous or
   dynamic binding must be resolved before conversion or questions. Never invent
   dataset names or turn an unknown count into zero. WEDELX/Tran Repository folder
   bindings belong in `knowledge/input-locations.json`. TPX session names are
   routing hints and require actual service/profile mappings.
   With the UI running, use the workspace MCP bridge rather than a second writer.
   `workbench_next_task`, `workbench_lineage` and `workbench_source_excerpt` provide
   frozen tasks and bounded evidence. No LLM endpoint/token is required. Address
   adapter obligations using normal repository coding tools and meaningful tests.
   Submit structured context with `workbench_submit_analysis`; it validates
   structure/lineage, not conversion correctness. Preserve unsupported semantics.
   Adapter changes require evidence-consistent new analysis; never rewrite frozen
   artifacts or clear blockers by changing flags. Copilot tokens/billing remain
   Unknown without an actual usage receipt.
   The single packet is then issued at `WAITING_SME`. Deliver its paths, including
   `sme-checklist.xlsx`, to the user. Explain any source blockers and the
   source-derived evidence boundary. Preserve the packet's Context, IDs,
   questions, version and hash. New v3 packets group technical assumptions by construct
   across programs, retaining exact raw gaps and individual business rules.
   A Yes answer confirms the description only. Retain historical v1/v2 packet
   hashes; never rebuild an issued packet using a newer format. WEDELX and its
   legacy alias WEDLX identify one location; preserve frozen original spellings.
   Ask the human to complete that one workbook and
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
   Validate every business and technical source logic obligation. Require 10–20
   distinct source-valid records per applicable supported logic item, every
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
   The HTTP UI and CLI share a single-writer lock: stop the other writer before
   switching transports, or use the currently running UI/API.
8. Deliver one primary `executive-report.html` with simple counts and next actions.
   Keep the management PPT and evidence bundle available on request. Do not
   produce another narrative Markdown report. Historical reports lacking the
   new executive report remain unchanged. Include a precise result. Distinguish
   `COMPLETED`, `COMPLETED_WITH_BLOCKERS`, cancelled, failed and timed-out work.
   Name unresolved behavior and coverage gaps. Never assert zero bugs,
   production readiness, full mainframe parity or verification unsupported by
   actual evidence. Keep future outputs in the documented folders.
