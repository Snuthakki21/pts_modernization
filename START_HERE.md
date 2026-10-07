# Mainframe Modernization Workbench

A local modernization workbench: provide a process, discover its object lineage,
choose conversion requirements, use GitHub Copilot to retrieve information and
Claude Code to analyze, build and test, review one checklist, and receive one
executive report.
Python/SQLite is the non-production target. Unsupported semantics require tested
adapters; a plan cannot be marked converted.

## 1. Install and open

Use CPython **3.12** and a writable folder on your local disk.

- **Windows:** run `./scripts/Setup.ps1`, then `./scripts/Start.ps1` in PowerShell.
- **Linux/macOS:** run `bash scripts/setup.sh`, then `.venv/bin/python -m workbench`.

Open **http://127.0.0.1:8765**. Setup installs the locked dependencies. The UI
is included; operators do not need Node. Follow any named setup error before
continuing. Native Windows execution still needs a workstation smoke test.

## 2. Answer six setup questions

The UI guides you through source location, manifest, Zowe, Db2, Copilot Chat
and reviewer availability. Choose “needs setup” when unsure; it gives the next
action. No passwords are entered in this questionnaire. Configuration does not
mean a live connection has been verified. The guide uses no LLM tokens.

For connections, set private shell variables from `.env.example` **before**
launch. That file is a template, not automatically loaded. You can begin with
local source and deterministic analysis. Copilot Chat needs your normal VS Code
Copilot access, not an LLM endpoint/token. Copy [examples/mcp.json](examples/mcp.json)
to `.vscode/mcp.json`, start the UI, enable the workbench tools in workspace
Copilot Chat with the retrieval prompt below. Preserve already approved server
bindings; the workbench template selects retrieval-only tools. Claude Code has no
MCP setup: its approved VS Code extension reads the retrieved local files.
Use standard VS Code workspace chat for Copilot; input prompts are not supported
by every agent harness.
[Technical reference](docs/TECHNICAL_REFERENCE.md)
contains the exact connection prerequisites and recovery actions.

For Zowe, import your exact files with
`python tools/setup_zowe.py --workspace WORKSPACE --import-config CONFIG --import-schema SCHEMA`.
For guided profile preparation, use `python tools/setup_zowe.py --workspace WORKSPACE --interactive`.
It declares `user` and `password` as secure fields. Enter values only at the local
`zowe config secure` prompts. Use the returned base/service profile variables.
Profile configuration is distinct from verified connectivity.

For Db2, keep **`tools/dq3g_mcp/.env`** (template:
[tools/dq3g_mcp/.env.example](tools/dq3g_mcp/.env.example)). The supplied connection
settings remain local; `DB2_USERNAME` stays commented out. Set `DB2_USERNAME`
and `DB2_PASSWORD` privately in the launch shell, or supply the password locally
in `.env`. Place the approved certificate at the file's `DB2_SSL_CERT_LOCATION`,
relative to the `.env` directory. SSL is required; PEM and DER certificates are
accepted. Install the approved IBM Db2 ODBC driver and `pyodbc` locally.

Start the Python FastMCP server with
`python tools/db2_mcp_server.py --transport http` after setting a private
`WB_DB2_MCP_TOKEN`. It listens only on `127.0.0.1:8766/mcp`.
Set `WB_DB2_MCP_URL` and the same token for the workbench; the `db2` entry in
[examples/mcp.json](examples/mcp.json) connects Copilot to that same server.
For a direct private subprocess client, use `--transport stdio` instead; run
only one Db2 server for the workspace's search journal. The existing UI bridge
continues to use the running Coordinator.

For unknown data, Copilot can call `db2_search_start` with a literal phrase, then
`db2_search_continue` while status is `RUNNING`. Every search includes table
contents across discovered schemas, tables, views, aliases and catalog-listed
DDF locations. Page `db2_search_results` with `kind="matches"` for hits and
`kind="objects"` for coverage; pass `next_after` as `after` until `has_more=false`.
Use `db2_search_status` or `db2_search_cancel` as needed.
**`DB2_QUERY_ROW_LIMIT=500000`** caps each query across continuation calls.
Unreadable locations, denied objects, capped rows and interrupted cursors remain
explicit partial results. This searches what the account and configured DDF
routes expose; it cannot discover unadvertised servers. Configuration alone
does not verify connectivity.

Existing explicit `WB_DB2_CONFIG` JSON installations remain supported with their
original private credential variables and certificate path. See the technical
reference for precedence and recovery details.

## 3. Provide your process

Put the complete UTF-8 export in **`Endeavor/`**, or choose source files in the
UI. Keep original relative names. Supply Markdown following
[examples/process-input.md](examples/process-input.md), or download the Excel
intake template in the UI. It names the process, ordered jobs/steps, programs
and input/output groups. Use a new process ID for changed source.

The local export permits **10,000 files**, **16 MiB per file**, **512 MiB combined**,
and **2 million physical lines**. Browser uploads permit 32 MiB combined; larger
repositories use local Endeavor. The 822-file/700,570-byte regression is verified;
full ceilings are protective limits, not memory or analysis certification.

For WEDLX/Tran Repository, copy [examples/input-locations.json](examples/input-locations.json)
to `knowledge/input-locations.json`. Set the actual mounted folders and exact
`{"logical_id":"REFERRAL","file":"referral.dat"}` bindings. These are application
staging locations. File availability is distinct from business readiness.

Put background/Devin articles in **`knowledge/inbox/`** (up to 20 Markdown documents, 1 MiB combined).
Keep related business knowledge together with its source, applicability and open details.
New processes freeze these articles for local Claude analysis; inbox edits do not
change existing processes or count as requirements selection or SME approval.
Add custom utility facts to **`knowledge/application-knowledge.json`**, created
by setup. The **Knowledge** screen and [knowledge guide](knowledge/README.md)
explain file classification, utilities, required evidence and editable facts.

## 4. Click Start

The workbench retains the full export, maps the job's transitive objects, checks
local definitions, and tries configured typed Zowe/Db2 reads for missing objects.
**Waiting for discovery** stops before conversion or questions when identities
are missing/ambiguous. Correct the named configuration/evidence and retry.
**Select requirements** shows every retained file and a paged source breakdown.
All in-scope items start at **Yes**. Set unwanted rules/behavior to **No**, then
click **Save requirements and continue**. Save updates
`processes/PROCESS_ID/analysis/requirements.md` and pins an immutable Markdown
revision as the conversion input. Related source statements share a unit; each
parsed rule remains selectable. Source excerpts include hashes and full-source
downloads. Choices persist across pages; Save detects conflicting edits.

No means **“Not converted because selected No in requirements.”** That reason
remains in the original-versus-modernized report with the saved requirements
and source evidence. Yes requires implementation and verification; excluding a
required layout or a writer consumed by later logic creates a visible dependency
gap. Requirements are separate from SME answers and lock at packet issue.
Changed adapter analysis requires a new scope Save; issued evidence never changes.

**Waiting for Claude analysis** provides frozen evidence and a local task.
Claude reads the approved files, develops and tests needed adapters, performs
independent review, refreshes analysis and submits a current task-bound result.
If information is missing, the handoff gives you a copyable Copilot retrieval
prompt and an exact return folder. Paste it into Copilot; after retrieval, return
to Claude and say **Continue**. Missing or mismatched returns keep the gate open.
The coordinator then emits supported targets and one SME checklist. Historical
ledgers retain the internal `WAITING_COPILOT` key; it does not assign coding to Copilot.
The screen shows the current stage and next action. Pause, Resume and Cancel
retain evidence. Mainframe connections remain read-only; no jobs or synthetic
records are run or uploaded there.

## 5. Return the one SME checklist

Download `sme-checklist.xlsx`. The actual reviewer selects **Yes**, **No** or
**Not sure**, adds corrections and returns it. Import the workbook with their
name. Agents must never fill these answers. The workbench automatically runs
source-derived synthetic tests, comparisons, adversarial checks and reporting.
Every new run requires **at least 20 distinct randomized valid source logic states per applicable
supported logic item**, generated at runtime with a recorded random seed, plus boundaries, invalid
inputs and source-evidenced linked-record matches/mismatches. Unsupported,
unreachable, undersampled or failing obligations stay explicit gaps. Expectations
are frozen before Python execution; no synthetic records go to the mainframe.
Unresolved answers remain blockers; it does not issue another questionnaire.
In **Evidence & reports → Factory**, inspect the minimum, executed unit tests,
job cases, recorded seed and target architecture assessment. Each program includes
runnable `tests/run-NNNN/PROGRAM/test_generated.py`; keep the process folder intact
and run the file with Python 3 to replay its frozen comparisons. The architecture
view explains SQLite's current scope and Oracle qualification requirements.
Oracle conversion/execution is not yet implemented.

## 6. Open the executive report

One primary report shows before/after counts, verified coverage, gaps and next
actions. The six-slide PowerPoint and detailed source/target/test evidence are
available when requested. **Completed with blockers** means unresolved work.
Passing local tests does not establish observed mainframe parity.

For the current software's results, open [executive-report.html](docs/executive-report.html).

## Use Copilot for retrieval and Claude Code for implementation

**Copilot in VS Code only retrieves files and metadata.** It may use your already
approved MCP connections for mainframe discovery, catalog lookups and source
pulls. The optional [Copilot template](examples/mcp.json) selects
`--role retrieval`; its workbench tool reads the current retrieval task. Keep your
approved Zowe/Db2 bindings. Do not assign analysis, coding, testing or review to
Copilot.

**Claude Code does the local work**, including in your organization-approved VS
Code extension: source and lineage analysis, inventory, rules, development,
unit/scenario testing, independent adversarial review and reports. It reads the
approved local exports and process notes. **Claude has no MCP servers.**
[examples/claude-mcp.json](examples/claude-mcp.json) is empty by design; nothing
needs registering or connecting. Do not substitute an MCP/HTTP shell wrapper or
route Claude through a Copilot tool.

1. Put the initial approved export in `WORKSPACE/Endeavor/`, or provide its local
   path and process notes. Give Claude the initial prompt below. It uses the
   existing Coordinator and presents the default-Yes requirements for your Save.
2. Claude reads the current task with
   `python -m workbench.runner agent PROCESS_ID --workspace WORKSPACE`.
   When evidence is missing, it writes a bounded request using `--request-file`
   and returns the generated **Copy Copilot retrieval prompt** text.
3. Paste that prompt into Copilot. Copilot writes original files into
   `processes/PROCESS_ID/analysis/retrieval/REQUEST_ID/inbox/files/` and finishes
   with that request's `inbox/response.json`. The prompt contains the exact paths,
   identities and response schema. Partial, missing, denied or ambiguous results
   must remain explicit. `FOUND` carries an original portable member path, hash
   and provenance. When a name cannot be staged in an analysis folder (for example
   a `.md` source), preserve it in `path` and use `staged_path` for its `.txt`
   inbox filename. `NOT_FOUND`/`AMBIGUOUS` carry the reason instead. A denied or
   partial lookup must not be returned as a complete found file. Copilot stops
   when retrieval is finished.
4. Return to Claude and say **Continue**. It runs the local command below,
   validates the request-bound files and resumes analysis. Subsequent requests
   identify only the remaining information; prior accepted evidence is retained.
   Default requests batch up to 128 needs and show remaining counts. A found file
   still needs a matching parsed object before its gap clears. NOT_FOUND or
   AMBIGUOUS results stop at a visible checkpoint; Claude does not repeat the same
   retrieval automatically.
5. Claude implements and verifies selected behavior, refreshes stale analysis
   after adapter changes and submits the fresh result. Your actual SME workbook
   remains the one human review; retrieval packets do not answer it or add a
   second questionnaire.

On **Linux/macOS**, from the repository with its configured environment:

```sh
.venv/bin/python -m workbench.runner agent PROCESS_ID --workspace WORKSPACE --continue
```

On **Windows PowerShell**:

```powershell
.\.venv\Scripts\python.exe -m workbench.runner agent PROCESS_ID --workspace WORKSPACE --continue
```

The runner uses local files, not an MCP or HTTP connection. When the UI is running,
it submits `.migration/agent-commands/COMMAND_ID.json` and receives
`.migration/agent-results/COMMAND_ID.json` from the same Coordinator. Waits are
bounded; a timeout is not an accepted return. If an older UI cannot consume these
commands, restart it using the existing launcher. Never start a second writer.
With the UI stopped, the runner acquires the existing exclusive Coordinator lock.
If a wait returns PENDING (exit 3), retry with the returned `--command-id` and
identical action. INDETERMINATE (exit 2) means the action may already have changed
state; its durable start marker prevents executing that command again. Run a fresh
inspection command first, then decide on any new action. Never delete the marker
or silently replay a mutation. REJECTED also exits 2 and names the cause.
The local queue requires hard-link support (such as NTFS and usual Linux/macOS
local filesystems); unsupported filesystems fail closed. Execution has been
verified on macOS; native Windows/Linux verification remains separate.

A `--request-file` contains only `{"needs": [...]}`; each need names its `kind`,
`name` and `reason`. The generated packet provides the complete return schema.
Use `--analysis-file ANALYSIS_JSON` to submit task-bound Claude analysis,
`--refresh` after tested adapter changes, and `--measurement-file RECEIPT_JSON`
for an actual usage receipt. If loaded adapters changed, restart the existing UI
when idle before refreshing. Neither an analysis return nor a plan clears a
semantic gap; actual supported behavior and verification evidence are required.

Both hosts use the four shared mainframe skills and one workflow. Actual credits
remain attributed to the provider/account that supplied the receipt; Claude
usage is not GitHub Copilot credits. Missing receipts stay Unknown. No agent is
automatically launched, and host policy/authentication still need workstation
verification. Existing source-free development packets are historical evidence,
not the active no-MCP Claude workflow.

For a safe trial, use **Run fictional example** in the UI. Its results are
excluded from real portfolio totals. No real process has been converted in the
software validation supplied with this repository.

## Agent start and rule conversion detail

The source selector can snapshot a supplied workstation/mounted folder directly.
CLI equivalent: add `--source-folder SOURCE_FOLDER --process-notes PROCESS_MD`
to the shared Start command, using `--assistant claude_files --select-requirements`. Originals stay unchanged.
The process Markdown is frozen as evidence; the agent derives the standard
manifest from explicit notes and JCL facts when your document is ordinary prose.
Ambiguous job identities still require evidence. Markdown in `knowledge/inbox/`
is indexed: at most 20 documents and 1 MiB combined, with bounded excerpt reads.

The executive report includes business-rule and technical-logic totals by job
and program. Its rule-detail link shows original source alongside modernized
Python/SQL mappings, versions, tests and reasons. `metrics.xlsx` includes Job
Summary, Program Summary, Business Rules, Technical Logic, Unclassified and Rule
Mapping sheets. `rules.json` and `rules.csv` preserve the same detail. Unclassified
spans are unresolved obligations, not a claimed count of all missing rules.
Repeated calls do not inflate job totals; cross-job memberships remain visible.
Only **converted and verified** counts as successful conversion. The report also
shows explicit omissions, candidate versus verified replacements, and source
structure needing no separate runtime replacement. Counts distinguish original,
selected and verified rules. A selected-scope completion is not full conversion
of an asset containing excluded executable behavior.

New agent-mode packets group only proven repeated decisions. Business/technical
classification needs source-grounded reasoning and is visible in the one human
review. Unknown classifications remain explicit. Older packet versions and
issued evidence retain their original interpretation and fingerprints.

Check Zowe without connecting with `python tools/setup_zowe.py --workspace WORKSPACE --check`.
`--normalize` only removes duplicate secure-field declarations after validation,
with a private backup. It does not remove profiles, change defaults, move
credentials or certify connectivity.

Copy this initial prompt into **Claude Code**:

> Read CLAUDE.md, AGENTS.md and prompts/START_MODERNIZATION.md. Use approved local
> source at `[SOURCE_FOLDER]`, process notes `[PROCESS_MD_PATH]` and workspace
> `[WORKSPACE]`. Claude has no MCP access. Use the existing Coordinator through
> its local-file runner workflow; never create another engine or writer. Inventory
> the complete export and trace job/program/data dependencies with evidence.
> Analyze business rules separately from technical logic. Present all conversion
> choices as Yes by default and wait for my explicit UI Save; retain every No
> with its exclusion reason. Implement selected behavior in professional
> Python/SQLite and document evidence for any future Oracle decision. Generate
> at least 20 distinct runtime-randomized valid source states per supported logic,
> pin seeds, execute unit and target-comparison tests, and perform independent
> adversarial review. Own analysis, development, integration, testing and reporting.
> When information is missing, produce the exact request-bound prompt for me to
> paste into GitHub Copilot; it retrieves files/metadata only. When I say Continue,
> validate that request's local return folder and resume. Do not guess missing
> objects or count a partial return as complete. Preserve source, evidence and
> one authentic SME checklist. Report original versus converted behavior by
> job/program with evidence, replacements, omissions and unresolved obligations.
> Track actual effort and provider credits; leave unavailable usage Unknown.

For the **initial pull in GitHub Copilot**, before a process task exists:

> Follow the retrieval role in .github/copilot-instructions.md. Use only already
> approved MCP connections to discover and retrieve the source and metadata for
> `[APPLICATION / STARTING JOBS]` into `[WORKSPACE]/Endeavor/`. Preserve original
> member paths, bytes, environment and provenance; use supplied WEDLX/Tran
> Repository bindings. Resolve read-only dependencies as requested. Record missing,
> denied, partial or ambiguous objects; never invent a successful lookup or
> substitute I* and Z* identities without evidence. Do not analyze rules, code,
> test or review. Stop after writing the export and tell me to continue in Claude.

For later missing information, use Claude's **generated Copilot retrieval prompt**
unchanged. It carries the current request ID, exact inbox and response schema.
After Copilot finishes, tell Claude: **“Continue process `[PROCESS_ID]` in
`[WORKSPACE]` from its recorded retrieval inbox.”**

## Application inventory and program knowledge

Open **Evidence → Factory → Application inventory and program knowledge**.
The inventory separates retained files, selected files and observed definitions:
COBOL programs, copybooks, DCL/DCLGEN, JCL jobs/PROCs, CICS BMS sources, SQL/Db2,
control cards, scheduler definitions and other retained types. Db2 procedure
counts come from conservative `CREATE PROCEDURE` observations; calls do not count
as definitions. Missing classifications and whole-estate totals stay Unknown.

Each program page shows its source hash/lines, job or transaction entry mappings,
parsed fields/dependencies, functionality observations, business/technical rules,
Yes/No scope, validation needs, risks and business/engineering/assurance views.
It does not invent business purpose or claim that a parsed screen is converted.
Verified counts require replayed coverage. Program details page in groups of 20;
bounded lists flag omissions and point to the complete source and rule reports.

The final factory report links one navigable **Program knowledge** HTML document
and its structured JSON under the process report folder. These consolidate useful
technical and functional documentation without a separate Markdown file per
program or a second business approval document. The pinned requirements and one
SME checklist remain authoritative.

## Online-first factory

For an online process, the agent derives a transaction table from your process
notes and source instead of inventing batch jobs. Give it transaction, entry
program and map bindings when available. Missing identities stay discovery gaps.
Evidence → **Factory** shows capability coverage, transaction/API candidates and
paged obligations. The final report links the same factory detail and Excel sheets.

A supported, tested business module can produce a local API and React form in
`target/RUN/online/`. This is a candidate interface, not a verified CICS/BMS
replacement. Native session, AID, security and database differences remain visible.
The package includes OpenAPI, HTTP comparisons and Windows/POSIX launchers. Use
the existing Python environment, set a private `ONLINE_TOKEN` (32+ characters),
and run `python application.py` from the package directory. Open localhost:8766.
Session data stays outside the immutable package; see the technical reference
for `ONLINE_STATE` and other configuration.

Add this to the initial prompt above:

> Use the online-first factory workflow. Trace transactions, maps, programs,
> storage, security, sessions and batch dependencies before selecting adapters.
> Inspect workbench_factory and exhaust its paged obligations. Prefer one modular
> business application with APIs; extract a separate service only when evidence
> supports independent business responsibility, data ownership and transaction
> boundaries. Keep SQLite and explicitly account for incompatible semantics.
> Check consistency after each change and workflow stage. Continue independent
> work, verify actual exported interfaces, and keep native CICS/BMS gaps visible.

## Pilot effort, AI credits and the remaining estate

Open **Evidence → Effort & scale**. Service stages, retries, elapsed time and
SME/agent waiting are recorded automatically. Use the existing effort controls to record discovery, mainframe, conversion,
SQL and validation work windows; stop clocks before human waiting.
Framework work is recorded once, separately from repeatable process work.
Interrupted clocks and older unrecorded work remain Unknown.

Set the estate quantity and counting unit once, with productive hours/week.
A business process and a JCL PROC are different units. The scenario can use
explicit low/base/high assumptions while the pilot is unfinished. For example,
20 assumed hours × 100 remaining processes = 2,000 effort hours, or 50 capacity
weeks at 40 hours/week. This example is not a measured result or promised date.

After migration, the app learns from its accepted evidence: jobs, programs,
source scope, rules, generated outputs, validation runs, open gaps, service time,
work records and credit receipts. Each forecast names its calibration pilots.
Complete attributed pilot effort and **whole-pilot credit receipts** replace
assumed rates automatically when the saved plan has no explicit rates. Blocked,
fictional, damaged, partially measured or requirements-excluded pilots do not
establish a complete-estate rate. Excluded executable source also prevents
whole-asset conversion credit.
Service and sequential elapsed projections remain separate from work effort.

**GitHub Copilot credits used** is the primary usage count, per account. Import
actual Copilot credit receipts through the panel or Claude
`agent --measurement-file RECEIPT_JSON`. Copilot may retrieve an available receipt
as a file using an approved connection. A zero is shown only when evidenced; missing receipts stay Unknown.
Token/request counts are not converted into credits. Optional allowance and
other-provider detail remain in the collapsed advanced usage section.

The AI budget uses **credits**, separated by provider/account. Import actual
credit statements and dated allowance/consumption snapshots through the panel
or import them with the local `agent --measurement-file` command. Tokens are useful
usage evidence but do not establish credit charges. No connected host billing
receipt means Unknown credits; no token-to-credit conversion is invented.
Future reports freeze their estimate and assumptions; the live view recalculates
as evidence arrives without rewriting issued reports.

Add this to the initial prompt:

> Track framework and process work through the existing effort controls; stop
> clocks before waiting for people. Capture actual provider credit receipts and
> allowance snapshots when available. Keep missing usage Unknown. After each
> migration, inspect Effort & scale and use its accepted source, generated
> artifacts, validation, timings and complete effort/credit evidence to update the
> same-unit estate forecast. Separate calibration samples from completed scope,
> expose unestimated work and never treat an estimate as verified conversion.
