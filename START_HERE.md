# Mainframe Modernization Workbench

A local modernization workbench: provide a process, discover its object lineage,
choose conversion requirements, use approved Claude Code retrieval, analysis,
build and testing, review one checklist, and receive one
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

1. **Prepare local connections in text**. Answer one bundle of approved nonsecret
   setup facts, then fill one private `WORKSPACE/.env` locally and place the two CA
   files. Run the Zowe and Db2 helpers and launch Claude as described below.
   In the Workbench, **Save setup** saves source defaults and shows **Add a process**.
   Client trust, authentication and actual read access remain separate checks.
2. **Add a process**. Paste/upload the ordered manifest Markdown or intake workbook.
   Add prose process notes separately under **Add optional analysis context**.
   Choose **No exports yet** if files have not been collected, then **Prepare process guide**.
   The fictional template keeps an explicit fictional flag and is excluded from real
   inventory and forecasts. Clear it only when supplying an actual process.
3. **Copy Claude retrieval prompt**. Paste the exact generated prompt into
   Claude Code. It uses read-only Zowe CLI and approved Db2 MCP to collect
   requested safe source/metadata into that request's inbox. Click
   **Continue after Claude saves evidence**.
   Missing or wrong identities stop here and remain named gaps.
4. **Choose logic**. Everything defaults to Yes. Uncheck unwanted units and
   **Save requirements and continue**. The immutable requirements Markdown is
   conversion input; No retains its exact exclusion reason and source evidence.
5. **Copy Claude prompt**. Paste the current analysis, development and test prompt
   into Claude Code. It reads the pinned process guide, safe task/context and
   requirements plus approved sanitized source views. After its current task-bound return, click
   **Continue after Claude returns analysis**.
   Missing evidence becomes a specific approved Claude retrieval request; source
   privacy, authorization and completeness remain gates.
6. **SME review**. Share the one issued review file. The actual SME answers,
   comments and clicks **Save review file**. Import the downloaded file with their
   real reviewer name.
   An unanswered/default choice is never approval; no second questionnaire is issued.
7. **Validate and compare**. The Coordinator executes supported targets and
   creates the accepted report. Open **Program comparison** for aggregate legacy and modernized totals.
   Select a program, use **Gaps only**, and open **View source, replacement and evidence**
   on a logical unit to inspect original code, target code, satisfaction and precise
   closure needs. Inspect saved No reasons and download **management.pptx**.
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

## Context files and consistent folders

[Repository context](prompts/CONTEXT.md) gives people and assistants one compact
map of roles, folder ownership and authoritative references. For each new
process, copy the [process context template](examples/process-specific.md) into
its external authoring folder as `process-specific.md`, beside `manifest.md`
and `Endeavor/`. Fill only cited facts; leave missing facts `Unknown`. Supply that
notes file separately in Intake. The Coordinator indexes and freezes it as
`analysis/process-context.json`; do not create another context Markdown inside
the process. All processes use the same seven categories, created as needed.

## 1. Start with one text setup bundle

Use **Windows 11**, CPython **3.12** and writable local NTFS folders. Before
opening a setup UI or starting services, Claude asks for this one bundle of
approved **nonsecret** facts. Leave an unknown value `Unknown`; do not guess.
Passwords, usernames used as credentials, tokens and private `.env` contents
are entered locally, never returned in chat.

| Needed fact | What to supply safely |
| --- | --- |
| Repository and workspace | Exact installed repository and selected local evidence workspace paths |
| Zowe environment | `dev` or `prod`; the protocol is fixed **HTTPS** |
| z/OSMF endpoints | Approved dev host/port and prod host/port; the selected pair is required, an unused pair may stay blank |
| TSO metadata | Approved account code, code page and logon procedure; these configure a profile, not a TSO session |
| Db2 service | Approved z/OS DDF location, host and service port; database equals the DDF location |
| Certificate files | Approved CA filenames and current local paths for both Db2 and Zowe |
| Db2 driver | Approved installed registered IBM Db2 ODBC driver name; the default is `IBM DB2 ODBC DRIVER` |
| Retrieval boundaries | Read-only authorization, approved sanitized source/metadata route and exact WEBELX/Tran Repository folders when supplied |

For offline fictional practice, say **offline** and leave remote connection
facts unused. No mainframe connection is needed for the embedded sample.
No existing Zowe profiles are required for the text setup below.

Open PowerShell in the installed repository. If its locked environment is not
ready, run `./scripts/Setup.ps1` **synchronously** and wait for **Environment ready**
or its concrete error. Setup tries `py -3.12`, then `python`, then `python3`,
accepting CPython 3.12 at any patch version, including an approved installation
on PATH when the Python launcher has no registered 3.12. It reuses a compatible
`.venv`, installs the hash-locked dependencies and temporarily prevents inherited
`PIP_USER=1` from redirecting that install while retaining approved package-index
and CA settings. It restores the caller's `PIP_USER` afterward.
Do not run parallel installers, manual pip retries or background setup. Preserve
an incompatible `.venv` for the technical owner before replacing it after setup
stops. Private `.env` is a connection file; Python `.venv` is a runtime folder.

Commands shown as `python` below mean the repository's locked executable
`.\.venv\Scripts\python.exe`. The committed UI needs no operator Node install;
Zowe CLI and the approved native Claude Code client need their approved runtimes.

Create your empty workspace first. Initialize its one knowledge catalog:

```powershell
.\.venv\Scripts\python.exe -m workbench.preflight --workspace "C:\MainframeFactory\JobAidWorkspace" --initialize-knowledge
```

Replace every example path with the same actual workspace. Keep the external
manifest, notes and source authoring package outside it.

## 2. Prepare one private `.env`, then the native clients

Copy the repository's [.env.example](.env.example) to **`WORKSPACE/.env`** only
when that private file does not already exist. In File Explorer enable file
extensions and keep the exact filename `.env`, never `.env.txt`. Open it only in
your approved local editor inside the approved network. Preserve an existing
file and correct named prerequisites locally; never overwrite it to hide a
conflict. Neither Claude nor a diagnostic command should print its contents.

The single file contains these **19 keys**. The owner fills the four credential
values locally; Claude can prepare only nonsecret values and empty placeholders.
Quote literal values containing spaces, `#` or `$`; values are never executed.

| Key | Local value or rule |
| --- | --- |
| `DB2_LOCATION_NAME` | Actual z/OS DDF location |
| `DB2_DATABASE` | Exactly the same DDF location |
| `DB2_HOSTNAME` | Actual Db2 service host, without a URL |
| `DB2_PORT` | Actual Db2 service port |
| `DB2_USERNAME` | Read-only account, entered only locally |
| `DB2_PASSWORD` | Password, entered only locally |
| `DB2_SSL_CONNECTION` | `true`; SSL stays enabled |
| `DB2_SSL_SERVER_CERTIFICATE` | `certificates/DB2-CA.cert` |
| `ZOWE_ENVIRONMENT` | `dev` or `prod` |
| `ZOWE_DEV_HOST` | Approved dev z/OSMF host, or blank when unused |
| `ZOWE_DEV_PORT` | Matching dev service port; never a partial host/port pair |
| `ZOWE_PROD_HOST` | Approved prod z/OSMF host, or blank when unused |
| `ZOWE_PROD_PORT` | Matching prod service port; never a partial host/port pair |
| `ZOWE_TSO_ACCOUNT` | Supplied account code |
| `ZOWE_TSO_CODE_PAGE` | Supplied code page |
| `ZOWE_TSO_LOGON_PROCEDURE` | Supplied logon procedure |
| `ZOWE_CA_CERTIFICATE` | `certificates/ZOWE-CA.pem` |
| `ZOWE_USERNAME` | Read-only account, entered only locally or at the secure client prompt |
| `ZOWE_PASSWORD` | Password, entered only locally or at the secure client prompt |

Create **`WORKSPACE/certificates/`**. Copy the approved Db2 CA bytes to
**`DB2-CA.cert`** (approved PEM or DER) and the approved Zowe PEM CA bytes to
**`ZOWE-CA.pem`**. A filename or a placeholder is not a valid certificate.
Relative certificate paths above resolve from the workspace's `.env` folder.
Do not disable TLS or certificate validation. If company certificate policy
blocks an Endevor/Zowe connection, retain the named gate and have the authorized
owner supply the complete approved source export locally through
`WORKSPACE/Endeavor/` or Intake's **Copy from a folder on this workstation**.
Do not invent an Endevor connection or treat TPX session names as API hosts.

From the repository, prepare a clean Zowe project config/schema programmatically:

```powershell
.\.venv\Scripts\python.exe tools\setup_zowe.py --workspace "C:\MainframeFactory\JobAidWorkspace" --from-env --env-file "C:\MainframeFactory\JobAidWorkspace\.env"
```

The helper uses the provided template, selected environment, HTTPS and certificate
validation. It prepares `project_base`, `DevPlex`/`ProdPlex` for the complete
endpoint pairs and the TSO metadata profile. Credentials do not enter JSON,
Markdown, arguments or model output. A conflicting existing config is a named
prerequisite, not permission to delete profiles. Preparation creates no TSO
session, submits no job and proves no connection.

**Zowe Explorer has a separate secure-store login.** A populated `.env` alone
does not sign in Explorer. Before starting VS Code/Explorer, the operator or
approved launcher must set `NODE_EXTRA_CA_CERTS` to the full local
`WORKSPACE\certificates\ZOWE-CA.pem` path, then launch/restart VS Code with the
workspace containing the generated config. In a local terminal in that workspace,
run `zowe config secure` and supply requested credentials privately. Keep secure
storage enabled. Follow only approved read-only retrieval requests.

Save your work and exit **all VS Code windows** first so an older process cannot
reuse an environment without this CA. In a fresh PowerShell window, replace the
example workspace and run:

```powershell
$workspace = "C:\MainframeFactory\JobAidWorkspace"
$env:NODE_EXTRA_CA_CERTS = Join-Path $workspace "certificates\ZOWE-CA.pem"
Set-Location -LiteralPath $workspace
zowe config secure
code --new-window $workspace
```

Enter the mainframe username/password only at Zowe's local secure prompts.
The `code` command opens the approved VS Code installation with this inherited
CA environment. If `code` is unavailable, have the technical owner launch the
approved Code executable from this same PowerShell window; a desktop shortcut
or an already running Code process may not inherit the CA. Do not disable TLS.

Prepare the approved local Db2 MCP binding from the same `.env`:

```powershell
.\.venv\Scripts\python.exe -m workbench.db2_setup --workspace "C:\MainframeFactory\JobAidWorkspace" --env-file "C:\MainframeFactory\JobAidWorkspace\.env"
.\scripts\Start-Claude.ps1 -Workspace "C:\MainframeFactory\JobAidWorkspace"
```

For an approved driver registered under a different name, append
`--driver "Exact registered IBM Db2 driver name"` to the Db2 setup command.
For offline fictional practice use
`python -m workbench.db2_setup --workspace WORKSPACE --offline` instead; a fresh
workspace gets an empty managed MCP configuration and no Db2 server.
The Db2 helper checks local fields/certificate prerequisites and prepares private
`WORKSPACE/.mcp.json`. Install the approved IBM Db2 ODBC driver; its registered
name must match the supported configuration. Missing credentials remain an
explicit local action. Fill them before launch: **stdio does not prompt for
credentials**. Claude owns the stdio server as its child; there is no separate
Db2 server terminal, HTTP port or MCP bearer token in this primary path.
The launcher preserves saved config and activates only managed `workbench-db2`
through a bounded `--strict-mcp-config`; it retains repository instructions and
adds a separate workspace with `--add-dir`. Other saved servers are not activated.
Complete actual Claude project trust and server approval; inspect `/mcp` and an
approved typed metadata read to verify access. A saved configuration or server
startup is not connectivity evidence. The approved VS Code extension must load
the same configuration in its actual host. Start a fresh conversation after a
configuration change. See the [official MCP contract](https://code.claude.com/docs/en/mcp).

Mainframe source/dataset metadata uses read-only **Zowe CLI**; Db2 schema/DDL uses
approved **typed MCP**. Arbitrary SQL, row/sample/search tool responses and a
workflow-proxy MCP are not allowed. Protected comparison exports use the exact
request-bound `db2_export_snapshot_to_inbox(process_id, request_id, need_id)`;
only path/hash/count/scope metadata returns to Claude. Original source, comments,
control cards, raw customer records and private exports stay deterministic-local.
Only explicitly approved sanitized semantic views and approved metadata may enter
the model. Missing safe context is a qualification gap. The operator-only local
Database view does not authorize model-visible rows or screenshots.

Now open the Workbench. For the repository itself as workspace run
`.\scripts\Start.ps1` synchronously. `-NoBrowser` only suppresses automatic browser
opening; setup and the Workbench stay foreground. For the separate workspace above:

```powershell
.\.venv\Scripts\python.exe -m workbench.launch --root "C:\MainframeFactory\JobAidWorkspace" --port 8765
```

Keep that one terminal open. Open **http://127.0.0.1:8765** after its URL appears;
never start another Coordinator. `Start.ps1` has no `-Root` option. In **Setup**,
save source-export/process-note defaults and optional exact **WEBELX folder** and
**Tran Repository folder**. Text-prepared connectors need no UI onboarding.
Leave the connector selectors unchanged; do not replace text config with a UI
connection draft. Click **Save setup**, then **Add a process** and follow
**Your next step**. Save affects future intake defaults; frozen evidence stays intact.
WEBELX is the current label; historical WEDLX/internal `wedlx_folder` bindings
remain compatible and frozen identities are not renamed.

### Retained compatibility routes

Existing supplied Zowe config/schema imports, existing profile selection and
Workspace setup's connection form remain explicit compatibility routes. They
are optional, preserve existing files and still require native authentication,
approved CA policy and actual read evidence. `setup_zowe.py --check` checks local
configuration; `--normalize` is limited to duplicate secure-field declarations.
Neither establishes access. The technical reference owns their detailed contract.

Existing Db2 JSON/`WB_DB2_CONFIG`, legacy `tools/dq3g_mcp/.env` and its
`DB2_SSL_CERT_LOCATION` alias, and separately approved remote HTTP/OAuth/bearer
MCP bindings retain their documented compatibility handling. Transport tokens
are relevant only to those explicit HTTP routes and are separate from Db2
passwords. Do not use them for the recommended local stdio route. No retained
route is presumed connected, Windows 11 accepted or enterprise approved.
Historical other-platform receipts remain scoped history.

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
file alone is not a valid manifest. Claude may draft a manifest only from
explicitly approved sanitized ordered notes/JCL facts. The local owner verifies
original bindings programmatically; missing safe facts stay Unknown.
The Coordinator freezes the manifest as `input/process-input.md`, the original
source under `input/sources/`, and notes inside `analysis/process-context.json`
under that process ID. Do not add `input/process-specific.md` or edit frozen copies.

The local export permits **10,000 files**, **16 MiB per file**, **512 MiB combined**,
and **2 million physical lines**. Browser uploads permit 32 MiB combined; larger
repositories use local Endeavor. The 822-file/700,570-byte regression is verified;
full ceilings are protective limits, not memory or analysis certification.

For WEBELX/Tran Repository, copy [examples/input-locations.json](examples/input-locations.json)
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
local definitions, and prepares exact Claude retrieval requests for missing objects.
Claude uses approved read-only Zowe/Db2 tools; accepted returns remain local and hash-bound.
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
Claude reads approved sanitized source/metadata, develops and tests adapters, performs
independent review, refreshes analysis and submits a current task-bound result.
If information is missing, the guide provides a Claude retrieval prompt and exact
return folder. Claude collects only approved safe evidence, saves the complete
response and continues through the local runner. Missing or mismatched returns keep the gate open.
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
New fixture-v5 processes require **64 distinct randomized valid source states**
per applicable logic/layout/step; **128 applies only to recorded source-risk logic**.
The recorded runtime seed, positive/negative/boundary, invalid-input, linked-record
and adversarial/mutation obligations are separate requirements; count alone is
insufficient. Historical contracts retain their original floors. Unsupported,
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

## Use Claude Code from retrieval through verification

Claude Code handles approved read-only Zowe/Db2 retrieval and safe local analysis,
development, tests and independent review. Copilot is not a dependency.
After the text connection setup and **Save setup** for source defaults, use the
same-workspace Claude session and the current
**Copy Claude retrieval prompt** or **Copy Claude prompt** from **Your next step**.

1. Provide the process manifest, optional background and approved export path, or
   **No exports yet**. Claude reads the current task with
   `python -m workbench.runner agent PROCESS_ID --workspace WORKSPACE`.
2. Missing evidence becomes a bounded `--request-file` request. Claude follows its
   current prompt through approved read-only tools, writing the exact
   `analysis/retrieval/REQUEST_ID/inbox/files/` and `inbox/response.json`.
   Metadata-only responses and approved sanitized sources may be model-visible;
   protected customer snapshots and original source are deterministic-local inputs.
   Preserve original identities, bytes, provenance and hashes. A missing, partial,
   denied or ambiguous result is never a successful FOUND.
3. Claude runs `--continue` after the complete response. The existing Coordinator
   validates identities/paths/hashes and resumes eligible work. Default batches
   contain at most 128 needs and show remaining counts. A returned file must match
   a unique parsed object before clearing a need. NOT_FOUND/AMBIGUOUS stop at a
   visible checkpoint; never repeat an unchanged failed lookup automatically.
4. You explicitly **Save requirements and continue**. Claude implements/tests the
   selected safe semantics, refreshes changed adapter analysis and submits its
   fresh task-bound return. Missing approved semantic views remain named gates.
5. The real SME completes the one issued review packet. No agent may save scope
   on your behalf, answer the packet or turn silence into approval.

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
The local queue requires hard-link support, such as local NTFS; unsupported
filesystems fail closed. Historical macOS/Windows Server/Linux receipts are scoped
evidence. Windows 11 queued-agent/approved-host acceptance must actually run before
claiming it verified.

A `--request-file` contains only `{"needs": [...]}`; each need names its `kind`,
`name` and `reason`. The generated packet provides the complete return schema.
Use `--analysis-file ANALYSIS_JSON` to submit task-bound Claude analysis,
`--refresh` after tested adapter changes, and `--measurement-file RECEIPT_JSON`
for an actual usage receipt. If loaded adapters changed, restart the existing UI
when idle before refreshing. Neither an analysis return nor a plan clears a
semantic gap; actual supported behavior and verification evidence are required.

The four shared mainframe skills extend one workflow. Actual credits
remain attributed to the provider/account that supplied the receipt; Claude
usage is not GitHub Copilot credits. Missing receipts stay Unknown. No agent is
automatically launched, and host policy/authentication still need workstation
verification. Existing source-free development packets are historical evidence,
not the current approved Claude workflow.

For a safe trial, use **Explore a fictional example** in the UI. Its results are
excluded from real portfolio totals. No real process has been converted in the
software validation supplied with this repository.

## Agent start and rule conversion detail

The source selector can snapshot a supplied workstation/mounted folder directly.
CLI equivalent: add `--source-folder SOURCE_FOLDER --process-notes PROCESS_MD`
to the shared Start command, using `--assistant claude_files --select-requirements`. Originals stay unchanged.
The process Markdown is frozen as evidence and consumed programmatically.
Claude can help draft the public manifest format from explicitly approved sanitized
ordered facts; an authorized owner verifies private bindings locally. Original
notes/JCL and their paths stay out of the chat. Missing, ambiguous or unqualified
job identities still require approved evidence. Markdown in `knowledge/inbox/`
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

> Read CLAUDE.md, AGENTS.md, prompts/CONTEXT.md and prompts/START_MODERNIZATION.md.
> First ask one bundle of approved nonsecret setup facts: repository/workspace,
> selected dev/prod environment and both available HTTPS host/port pairs, TSO
> account/code page/logon procedure, Db2 DDF/host/port, approved CA filenames/local
> paths and registered IBM driver. Keep unknowns explicit. Prepare one workspace
> .env with the canonical 19 keys and empty credential placeholders; have me fill
> credentials only locally. Run the documented text Zowe/Db2 helpers and launch
> Claude-owned stdio without a token before opening the process UI. Never read or
> print .env. If certificate policy blocks retrieval, use an approved local export.
> Then follow the selected process guide's current safe task and exact opaque references.
> Use public repository context and explicitly approved sanitized views only.
> Original source, process notes, private filenames and raw customer data remain
> local intake data consumed programmatically, never chat context. Preserve
> UNAPPROVED_MODEL_METADATA until an approved sanitized lookup identity or local
> deterministic export capability exists; never infer names from hashes or open
> protected requests. Approved Db2 MCP and read-only Zowe remain the only retrieval
> routes; protected Db2 export resolves exact IDs server-side. Use the existing Coordinator through
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
> the pinned fixture-v5 floor (64 valid states; 128 for recorded risk triggers),
> positive/negative/boundary and adversarial/mutation obligations,
> pin seeds, execute unit and target-comparison tests, and perform independent
> adversarial review. Own analysis, development, integration, testing and reporting.
> When information is missing, follow the exact request-bound Claude retrieval
> prompt through approved tools, save its local response, validate and resume.
> Do not expose raw records or private source to any LLM/tool output. Do not guess missing
> objects or count a partial return as complete. Preserve source, evidence and
> one authentic SME checklist. Report original versus converted behavior by
> job/program with evidence, replacements, omissions and unresolved obligations.
> Track actual effort and provider credits; leave unavailable usage Unknown.

For later missing information, use the **generated Claude retrieval prompt**
unchanged. It carries current request/need references and the exact inbox; private
operational names may remain masked with `UNAPPROVED_MODEL_METADATA`. That gate is
not permission to guess names or read private requests. To resume, tell Claude: **“Continue process `[PROCESS_ID]` in `[WORKSPACE]` from
its recorded retrieval inbox using only approved safe evidence.”**

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

For an online process, Claude drafts a transaction table from explicitly approved
sanitized process/source facts. The local owner verifies original bindings
programmatically; do not expose protected notes/source to the model. Supply safe
transaction, entry-program and map facts when available. Missing safe identities
stay discovery gaps; never invent batch jobs.
**Evidence & reports → Inspect evidence → Factory** shows capability coverage,
transaction/API candidates and paged obligations. The final report links the same factory detail and Excel sheets.

For CICS intake, include the transaction/program/map table in your process Markdown,
then supply that file and your export folder through the existing Start flow.
Claude retrieves approved CICS programs, BMS maps, symbolic COPY dependencies and
resource definitions with Zowe CLI; Db2 descriptions/DDL use the approved Db2 MCP
connection. Returns go into the exact process/request inbox, then Claude reads
accepted metadata and explicitly approved sanitized views. Missing, dynamic or conflicting dependencies stop discovery.

In **Select requirements**, filter by program, mapset/map and component. Each field
and `EXEC CICS` action has a default-Yes checkbox and its exact original source span.
Save pins the process's requirements Markdown. Safe constant labels can be omitted;
excluding a required buffer, map or action keeps a specific dependency gap and does
not authorize a redesign. Every No retains the exact requirements omission reason.

The supported literal BMS character profile generates Python layout code and a
FastAPI rendering route in `target/RUN/online/`. Its form shows source positions,
input widths, protected defaults and the actual API layout result. Generated unit
cases, the pinned fixture-v5 64-state layout floor, malformed requests
and adversarial mutations are compared before layout credit. Static-only or small
finite domains retain their test-state deficit. **Program comparison** shows original
BMS/CICS and Python/FastAPI spans, with Gaps only and Selected No filters.

Layout conversion does not implement native `SEND`/`RECEIVE`, symbolic buffers, AID,
controller flow, sessions, security or database effects. Those remain named,
source-specific obligations. A layout-only package disables transaction execution.
Supported record modules can also expose the existing tested record API. Neither
candidate is a claim of full CICS replacement or observed mainframe parity.
The package includes OpenAPI, HTTP comparisons and a Windows launcher; historical
POSIX artifacts retain their original evidence. Use
the existing Python environment and set a private `ONLINE_TOKEN` (32+ characters).
Choose a free candidate port separate from the Workbench and Db2 MCP server.
When the Db2 gateway uses 8766, use 8767 if available. From the package directory,
with the reviewed Python environment active:

On Windows PowerShell:

```powershell
$env:ONLINE_PORT = "8767"
python application.py
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
> Gather missing dependencies through approved Claude retrieval into the exact
> local inbox. Keep raw source/records protected; read only approved safe views.
> Keep layout verification separate from controller/data parity.

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

Import actual provider/account credit receipts through the panel or Claude
`agent --measurement-file RECEIPT_JSON`. Older Copilot receipts remain attributed
to Copilot; Claude usage must not be counted as Copilot credits. Missing receipts
stay Unknown and known zero requires evidence. Tokens/requests are not converted
to credits; an Anthropic token or currency charge is not an invented credit count.

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

## Claude Code skills for development and review

The requested instruction-only additions are already in `.claude/skills/`,
indexed by [.claude/skill-pack.json](.claude/skill-pack.json). From the installed
repository, run `python tools/check_skill_pack.py` before relying on a changed
pack. Start Claude using `scripts/Start-Claude.ps1 -Workspace WORKSPACE`; the
repository entrypoint routes to the shared workflow and relevant local skills.
If a running client has cached skill discovery, reopen its repository session.
No separate plugin installer, MCP server, proxy, hook or service is required by
this pack. Existing approved Db2 MCP/Zowe setup remains separate.

Use only guidance relevant to the task: reproducible fixes, focused architecture,
meaningful tests, consistent accessible UI, bounded context and independent
review. Each entry states its upstream pin, license and adaptation scope. These
are local skill adaptations rather than the full upstream runtimes; they never
authorize access to protected source/records, human scope/SME decisions or changes
to evidenced legacy behavior. Native Windows/client invocation remains a target
acceptance check, not an automatic consequence of installing files.
