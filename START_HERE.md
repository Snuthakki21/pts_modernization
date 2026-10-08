# Mainframe Modernization Workbench

A local modernization workbench: provide a process, discover its object lineage,
choose conversion requirements, use GitHub Copilot to retrieve information and
Claude Code to analyze, build and test, review one checklist, and receive one
executive report.
Python/SQLite is the non-production target. Unsupported semantics require tested
adapters; a plan cannot be marked converted.
Conversion preserves the mainframe's evidenced behavior, even when its design
appears incorrect. Source issues are reported rather than fixed. The comparison
shows the corresponding target code and tests; a Db2/mainframe function without
a verified replacement remains a specific gap.

## The analyst job aid

Follow the **Your next step** panel for the selected process. It shows the current
prompt, exact return folder and saved instructions; use **Refresh guide** after
an assistant finishes. The normal sequence is:

1. **Save setup**. Enter nonsecret Zowe and approved Db2 MCP choices. Save writes
   `.migration/workstation.md` and shows **Add a process**. Complete the displayed
   native secure credential/client steps; configuration alone does not prove access.
2. **Add a process**. Paste/upload the ordered manifest Markdown or intake workbook.
   Add prose process notes separately under **Add optional analysis context**.
   Choose **No exports yet** if files have not been collected, then **Prepare process guide**.
   The fictional template keeps an explicit fictional flag and is excluded from real
   inventory and forecasts. Clear it only when supplying an actual process.
3. **Copy Copilot prompt**. Paste the exact generated prompt into GitHub Copilot
   in VS Code. It retrieves source with Zowe CLI and Db2 facts with approved MCP
   into that request's inbox. Click **Continue after Copilot saves files**.
   Missing or wrong identities stop here and remain named gaps.
4. **Choose logic**. Everything defaults to Yes. Uncheck unwanted units and
   **Save requirements and continue**. The immutable requirements Markdown is
   conversion input; No retains its exact exclusion reason and source evidence.
5. **Copy Claude prompt**. Paste the current analysis, development and test prompt
   into Claude Code. It reads the pinned process guide, source, context and
   requirements locally. After its current task-bound return, click
   **Continue after Claude returns analysis**.
   Missing evidence leads back to a specific Copilot request; Claude has no MCP.
6. **SME review**. Share the one issued review file. The actual SME answers,
   comments and clicks **Save review file**. Import the downloaded file with their
   real reviewer name.
   An unanswered/default choice is never approval; no second questionnaire is issued.
7. **Validate and compare**. The Coordinator executes supported targets and
   creates the accepted report. Filter **Program comparison → Gaps only**, inspect
   saved No reasons and source/Python evidence, and download **management.pptx**.
   The read-only Database view exposes registered SQLite schema candidates and
   tables; schema creation does not convert business SQL or establish Db2 parity.

The process guide is `processes/PROCESS_ID/analysis/process-guide.md`; each saved
version is pinned under `analysis/process-guide/SHA256.md`. Prompts reference the
immutable version and exact task/requirements hashes. Setup changes affect future
intake; existing frozen process evidence stays intact. Same-input Prepare retries
reuse the existing process and its saved choices. Changed inputs require a new ID.

For questions about these steps, assistants first read the compact
[operator reference](prompts/OPERATOR_GUIDE.json). It routes questions to exact
labels, guide steps and relevant source spans. It is a checked navigation cache,
not process evidence: changing a bound file invalidates it. Current status,
prompts, counts and return paths must come from the selected process's current
guide or existing runner, never from cached examples or a direct database scan.

For the detailed walkthrough, open the [offline screenshot job aid](examples/mainframe-modernization-job-aid.html)
in your browser. Its 46 steps, screenshots and fictional sample ZIP are embedded
in one file. It remains a review draft; screenshot paths are illustrative.

## 1. Install and open

Use CPython **3.12** and a writable folder on your local disk.

- **Windows:** run `./scripts/Start.ps1` in PowerShell.
- **Linux/macOS:** run `bash scripts/start.sh`.

The launcher installs the locked environment when needed, starts the existing
workbench and opens **http://127.0.0.1:8765** after startup. Keep the terminal
open. Use `-NoBrowser` on Windows or `--no-browser` on Linux/macOS when needed.
The UI is included; running it does not require Node. Follow any named setup error
before continuing. CPython 3.12 must already be installed. Native installation
and offline checks pass on Windows Server and Linux; Windows 11 desktop and
organization-specific driver/client/host acceptance remain separate.

Commands shown as `python` below use the repository's locked environment:
`.\.venv\Scripts\python.exe` on Windows PowerShell, or `.venv/bin/python` on
Linux/macOS. Use that executable directly for agent and maintenance commands;
no separate global dependency installation is needed.

To keep evidence outside the installed repository, create an empty local
workspace folder first. In the repository's PowerShell terminal, run:

```powershell
.\scripts\Setup.ps1
.\.venv\Scripts\python.exe -m workbench.preflight --workspace "C:\MainframeFactory\JobAidWorkspace" --initialize-knowledge
.\.venv\Scripts\python.exe -m workbench.launch --root "C:\MainframeFactory\JobAidWorkspace" --port 8765
```

`C:\MainframeFactory\JobAidWorkspace` is an example; use your actual folder.
`Start.ps1` launches the repository root and has no `-Root` option. The explicit
`--root` command selects a separate workspace; it serves the installed assets and
standard catalog without copying implementation files into that workspace.

## 2. Enter your settings and save once

The first visit opens **Workspace setup**. Choose your local source export folder,
or upload files when adding a process. Optionally enter your process Markdown
and exact WEDLX/Tran Repository folders. These defaults survive a restart.

The same screen prepares your approved retrieval connections:

- **Copilot MCP:** select the retrieval bridge. Save writes the ignored
  `.vscode/mcp.json` with the current Python interpreter and running Workbench
  address. Existing approved servers and inputs are preserved. Db2 access
  always uses an approved MCP server with a secure VS Code token prompt.
- **Zowe:** select existing project profiles, create profiles using the actual
  z/OSMF host/port and two aliases, or import your exact supplied config/schema
  paths. Import preserves file bytes. New profiles declare secure credentials
  and require HTTPS with certificate validation.
- **Db2 MCP:** select an existing approved server address, or prepare the
  supplied local server. Enter the actual Db2 host, service port, database, DDF
  location, registered IBM ODBC driver name, approved CA file, local MCP port
  and read limit. Save prepares ignored `.migration/db2-config.json`, the CA
  certificate and the Copilot binding. The local MCP port is separate from the
  mainframe Db2 service port. Missing certificates or drivers remain visible.

Mainframe source and dataset metadata use **Zowe CLI**. Db2 catalogs and data use
**MCP**. There is no alternate direct Db2 retrieval route in the Workbench.

Click **Save setup** once to prepare the selected files and save intake defaults.
Unsaved Setup entries survive navigation within the app. Save before closing
or reloading the browser; the browser warns while changes remain unsaved.
The result shows the files, local CLI availability and any remaining client steps.
Copy the displayed command to install your approved Zowe CLI when needed, then
recheck. Zowe requires its approved Node/npm runtime; the Workbench UI itself
needs no Node installation. Enter credentials only at the displayed local
`zowe config secure` command or VS Code's secure prompt. Open this workspace in
VS Code and use **MCP: List Servers** to review/start the approved retrieval
servers. Keep the Workbench running for its retrieval bridge.

For the local Db2 server, copy its displayed command into your terminal. It
checks the selected registered driver and certificate before prompting privately
for credentials and the approved MCP token. Enter that same token at the VS Code
secure prompt, and keep the server terminal open. The command runs the existing
read-only FastMCP server; it does not execute a Db2 query during setup. Install the
organization-approved IBM driver and `pyodbc` in the displayed Python environment
if the local check reports them missing.

Local intake can continue with **Add a process** when its settings pass.
Connector actions remain visible until their native configuration/authentication
is established; the form never asserts connectivity or migration parity from
configuration. Save performs no CLI execution, network or model calls.
Passwords and tokens stay in their approved secure clients or private launch
environment. Claude Code builds and tests from local files with **no MCP
servers**. Source snapshots, requirements Save and the actual SME return keep
their existing gates.

Conflicting MCP bindings, different existing Zowe import destinations, unsafe
paths or invalid schemas stop the save and preserve existing files. Ordinary
failed writes restore prior configuration. Correct the named conflict and retry.
CLI alternatives remain `python tools/setup_zowe.py --workspace WORKSPACE
--import-config CONFIG --import-schema SCHEMA` and `--interactive`; the
[technical reference](docs/TECHNICAL_REFERENCE.md) describes the same helpers.
Zowe installation follows its [official CLI guide](https://docs.zowe.org/stable/user-guide/cli-installcli/);
VS Code activation follows its [MCP guide](https://code.visualstudio.com/docs/agent-customization/mcp-servers).

Existing Db2 installations can keep **`tools/dq3g_mcp/.env`** (template:
[tools/dq3g_mcp/.env.example](tools/dq3g_mcp/.env.example)). The supplied connection
settings remain local; `DB2_USERNAME` stays commented out. Set `DB2_USERNAME`
and `DB2_PASSWORD` privately in the launch shell, or supply the password locally
in `.env`. Place the approved certificate at the file's `DB2_SSL_CERT_LOCATION`,
relative to the `.env` directory. SSL is required; PEM and DER certificates are
accepted. Install the approved IBM Db2 ODBC driver and `pyodbc` locally.

Start the Python FastMCP server with
`python tools/db2_mcp_server.py --transport http` after setting a private
`WB_DB2_MCP_TOKEN`. It listens only on `127.0.0.1:8766/mcp`.
Save the endpoint in Workspace setup and supply the same token privately when
using Workbench connector commands; the `db2` entry in
[examples/mcp.json](examples/mcp.json) connects Copilot to that same server.
For an approved Copilot MCP subprocess configuration, use `--transport stdio`; run
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

Choose **No exports yet** to prepare an exact retrieval request before source exists,
or put the complete UTF-8 export in **`WORKSPACE/Endeavor/`**, select **Copy from a
folder on this workstation**, or choose source files in the UI. Keep original
relative names. Supply the canonical manifest following
[examples/process-input.md](examples/process-input.md), or download the Excel
intake template in the UI. It names the process, ordered jobs/steps, programs
and input/output groups. Use a new process ID for changed source.

Keep each process's editable intake package in its own folder outside the evidence
workspace, for example `C:\MainframeFactory\Inputs\referral-batch\`.
`manifest.md` contains the stable ID and ordered job/step or transaction table;
upload it in **Process manifest**. `process-specific.md` contains ordinary prose
about dependencies and business context; enter its full path in **Add optional
analysis context → Process Markdown path on this workstation**. A prose notes
file alone is not a valid manifest. Claude may derive a manifest from explicit
notes/JCL facts locally; missing facts stay Unknown.
The Coordinator freezes the manifest as `input/process-input.md`, the original
source under `input/sources/`, and notes inside `analysis/process-context.json`
under that process ID. Do not add `input/process-specific.md` or edit frozen copies.

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

## 4. Follow the process guide

Click **Prepare process guide** to save the process and begin discovery.
Existing ready processes show **Start discovery** in their guide.
The workbench retains the full export, maps the job's transitive objects, checks
local definitions, and prepares exact Copilot retrieval requests for missing objects.
The local Claude workflow makes no remote connector calls.
**Waiting for discovery** stops before conversion or questions when identities
are missing/ambiguous. Correct the named configuration/evidence and retry.
**Select requirements** shows every retained file and a paged source breakdown.
All in-scope items start at **Yes**. Set unwanted rules/behavior to **No**, then
click **Save requirements and continue**. Save updates
`processes/PROCESS_ID/analysis/requirements.md` and pins an immutable Markdown
revision as the conversion input. Related source statements share a unit; each
parsed rule remains selectable. Source excerpts include hashes and full-source
downloads. Unsaved choices survive pages, filters and in-app route/process
switches; they are not saved evidence. Save before closing/reloading the browser;
unsaved scope warns on unload. A live hash/revision conflict blocks Save;
**Reload saved choices** explicitly discards the draft and loads current choices.

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

Download **`sme-checklist.html`** and share that one file. The SME opens it in
their normal browser, explicitly chooses **Yes**, **No** or **Not sure**, adds
commentary, enters their name and clicks **Save review file**. That downloads
`PROCESS_ID-sme-return.html`; they send that answer-bearing file back and you import
it with their actual name. No install or server is required for the SME. The original file is not
overwritten automatically; return the downloaded file. The legacy
`sme-checklist.xlsx` remains an alternative for the same single packet. Agents must never fill these answers. The workbench automatically runs
source-derived synthetic tests, comparisons, adversarial checks and reporting.
New process fixture contracts require **at least 20 distinct randomized valid source logic states per applicable
supported logic item**, generated at runtime with a recorded random seed, plus boundaries, invalid
inputs and source-evidenced linked-record matches/mismatches. Unsupported,
unreachable, undersampled or failing obligations stay explicit gaps. Expectations
are frozen before Python execution; no synthetic records go to the mainframe.
Unresolved answers remain blockers; it does not issue another questionnaire.
Any nonempty correction/commentary also remains an unresolved review fact, even
beside Yes. Record concerns honestly; do not erase commentary to obtain approval.
In **Evidence & reports → Inspect evidence → Factory**, inspect the minimum, executed unit tests,
job cases, recorded seed and target architecture assessment. Each program includes
runnable `tests/run-NNNN/PROGRAM/test_generated.py`; keep the process folder intact
and run the file with Python 3 to replay its frozen comparisons. The architecture
view explains SQLite's current scope and Oracle qualification requirements.
Oracle, BigQuery, Java and .NET are future target candidates behind the same
versioned generation/comparison contract. They are not yet implemented or selectable;
a warehouse target requires explicit workload and transaction qualification.

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
   after adapter changes and submits the fresh result. Your actual SME HTML review or workbook
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
verified on macOS; native offline path guards also pass. Full queued-agent
execution on Windows 11/Linux still needs end-to-end acceptance.

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

For a safe trial, use **Explore a fictional example** in the UI. Its results are
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
> Python/SQLite, preserving evidenced legacy behavior including design defects.
> Refactor only with verified observable equivalence; report source issues and
> unsupported Db2/mainframe operations with source/target/test evidence or exact
> missing replacements. Do not silently correct or retire behavior. Document
> evidence for any future Oracle decision. Generate
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

Open **Evidence & reports**, choose **Factory** under **Inspect evidence**, then
open **Application inventory and program knowledge**.
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

At the end of conversion, open **Evidence & reports**, choose **Program comparison**
under **Inspect evidence**, or click **Compare COBOL and Python** in Reports. Choose a program and click **Gaps only**.
Each source unit shows the original file/lines beside the actual Python
file/lines, accepted status and evidence. Gaps name the recorded reason,
missing branch or distinct-state count, differing case IDs, and evidence needed
for resolution. Rule, whole-program and process-wide gates stay distinct;
process obligations remain visible even when a program has no conversion gaps.
**Selected No** shows “Not converted because selected No in requirements.”
Shared copybooks retain all program owners without inflating unique totals.
The downloadable comparison HTML has the same program/status filters; JSON keeps
all details when an on-screen preview is abbreviated. Filtering reads the frozen
accepted report; it does not rerun verification or establish mainframe parity.

The final factory report links one navigable **Program knowledge** HTML document
and its structured JSON under the process report folder. These consolidate useful
technical and functional documentation without a separate Markdown file per
program or a second business approval document. The pinned requirements and one
SME checklist remain authoritative.

## Online-first factory

For an online process, the agent derives a transaction table from your process
notes and source instead of inventing batch jobs. Give it transaction, entry
program and map bindings when available. Missing identities stay discovery gaps.
**Evidence & reports → Inspect evidence → Factory** shows capability coverage,
transaction/API candidates and paged obligations. The final report links the same factory detail and Excel sheets.

For CICS intake, include the transaction/program/map table in your process Markdown,
then supply that file and your export folder through the existing Start flow.
Copilot retrieves full CICS programs, BMS maps, symbolic COPY dependencies and
resource definitions with Zowe CLI; Db2 descriptions/DDL use the approved Db2 MCP
connection. Returns go into the exact process/request inbox, then Claude reads
validated local exports. Missing, dynamic or conflicting dependencies stop discovery.

In **Select requirements**, filter by program, mapset/map and component. Each field
and `EXEC CICS` action has a default-Yes checkbox and its exact original source span.
Save pins the process's requirements Markdown. Safe constant labels can be omitted;
excluding a required buffer, map or action keeps a specific dependency gap and does
not authorize a redesign. Every No retains the exact requirements omission reason.

The supported literal BMS character profile generates Python layout code and a
FastAPI rendering route in `target/RUN/online/`. Its form shows source positions,
input widths, protected defaults and the actual API layout result. Generated unit
cases, at least 20 distinct randomized valid input/layout states, malformed requests
and adversarial mutations are compared before layout credit. Static-only or small
finite domains retain their test-state deficit. **Program comparison** shows original
BMS/CICS and Python/FastAPI spans, with Gaps only and Selected No filters.

Layout conversion does not implement native `SEND`/`RECEIVE`, symbolic buffers, AID,
controller flow, sessions, security or database effects. Those remain named,
source-specific obligations. A layout-only package disables transaction execution.
Supported record modules can also expose the existing tested record API. Neither
candidate is a claim of full CICS replacement or observed mainframe parity.
The package includes OpenAPI, HTTP comparisons and Windows/POSIX launchers. Use
the existing Python environment and set a private `ONLINE_TOKEN` (32+ characters).
Choose a free candidate port separate from the Workbench and Db2 MCP server.
When the Db2 gateway uses 8766, use 8767 if available. From the package directory,
with the reviewed Python environment active:

On Windows PowerShell:

```powershell
$env:ONLINE_PORT = "8767"
python application.py
```

On Linux/macOS:

```bash
ONLINE_PORT=8767 python application.py
```

Open `http://127.0.0.1:8767`. If that port is occupied, choose another free port
and use it in both the launch environment and browser. Session data stays outside
the immutable package; see the technical reference for `ONLINE_STATE` and other
configuration. Do not edit an issued package to change its port.

Add this to the initial prompt above:

> Use the online-first factory workflow. Trace transactions, maps, programs,
> storage, security, sessions and batch dependencies before selecting adapters.
> Inspect workbench_factory and exhaust its paged obligations. Prefer one modular
> business application with APIs; extract a separate service only when evidence
> supports independent business responsibility, data ownership and transaction
> boundaries. Keep SQLite and explicitly account for incompatible semantics.
> Check consistency after each change and workflow stage. Continue independent
> work, verify actual exported interfaces, and keep native CICS/BMS gaps visible.
> Use my process Markdown and export folder. Present the program/screen/component
> checkboxes, pin my explicit Save to the process requirements Markdown, and compare
> original BMS fields and CICS actions with actual Python/FastAPI code and receipts.
> Gather missing dependencies through the exact Copilot retrieval inbox; Claude uses
> local exports only. Keep layout verification separate from controller/data parity.

## Pilot effort, AI credits and the remaining estate

Open **Evidence & reports → Inspect evidence → Effort & scale**, or the sidebar's
**Effort & scale** button. Service stages, retries, elapsed time and
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
