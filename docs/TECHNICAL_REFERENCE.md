# Workbench technical reference

Start with [START_HERE.md](../START_HERE.md). The current solution summary is
[executive-report.html](executive-report.html); inspect [evidence.json](evidence.json)
only when detailed engineering evidence is needed. This file is the single
operating, implementation and extension reference. Update it in place.

## Operating promise

After initial setup: provide the process manifest and complete Endeavor export,
click Start, save the selected requirements, return the one authentic SME checklist,
then receive one primary executive report. GitHub Copilot in VS Code only
retrieves source and metadata through already approved MCP connections. Claude
Code, including its approved VS Code extension, reads approved local files and
owns analysis, development, tests and review with no MCP servers. No model
endpoint/token is required by the workbench. Local analysis, supported Python
conversion, runtime-randomized synthetic generation with frozen replay seeds,
comparison, adversarial mutation checks, knowledge updates
and the six-slide management PowerPoint run automatically. Blockers stay visible.
The Python/SQLite target is non-production. Full COBOL/CICS/SQL semantics require
source-supported adapters; recognizing syntax or submitting a plan gives no credit.

Local-file agent intake maps job-led transitive object lineage first. Missing,
ambiguous, dynamic or unsupported bindings stop at `WAITING_DISCOVERY`, before
conversion or SME questions. The retained export is indexed in full; unrelated
members remain explicitly outside the selected closure. Missing objects become
request-bound Copilot retrievals; the local Coordinator validates returned files
and preserves immutable accepted evidence before conversion. Claude does not
call Zowe, Db2 or other remote/MCP connectors. Closure COMPLETE describes
the bounded static graph, not all runtime paths or the entire estate.
`WAITING_COPILOT` remains the historical ledger key for frozen agent analysis
and is presented as waiting for Claude analysis in the active workflow. Claude
implements adapters, runs tests and independent review, refreshes analysis through
the local runner and submits a current hash-bound result before the one SME
packet. Prior evidence is preserved. The service never launches an agent or
fabricates model results. New intake uses `claude_files`; deterministic and legacy
assistant modes retain their replay contracts.

Read-only Zowe/Db2 discovery does not require prelisting schemas or tables.
No source-system writes, mainframe execution or synthetic uploads are permitted.
Do not use an agent's answer as SME approval. Source-derived comparisons are
not observed mainframe results. No claim of perfect software is supported.

### Legacy behavior fidelity

Migration preserves evidenced source behavior, including suspected or confirmed
legacy design defects. Do not correct a wrong-looking condition, remove a dated
rule, normalize meaningful values or change error handling because a different
design appears better. Record the source issue and its consequences in the
existing analysis and comparison commentary; remediation is outside this
migration. Neither an SME Yes nor target best practices authorize a behavior
change.

One-for-one means equivalent observable behavior for the selected scope: outputs,
data effects, ordering, duplicates, NULL/numeric semantics, return/error codes and
source-supported state/transaction effects. It does not require identical file,
program or line counts. Refactoring or consolidation is allowed only with
source-grounded equivalence and actual target tests. A preserved source issue
needs source version/span, corresponding target version/span, expected behavior
and test evidence. Source-derived expectations remain distinct from observed
mainframe results; missing interpretation or evidence stays unresolved.

A functionality-specific Db2 utility, program or other mainframe operation without
a verified equivalent remains a named gap. Identify the job/step or transaction,
object/version, source/control-card spans, expected effects and exact missing
replacement/evidence. Do not hide it as mainframe-only, unnecessary or replaced
by a generic library. Non-executable structure requires its existing evidenced
disposition; explicit selected No remains an omission with its saved reason and
earns no parity credit.

Tests must preserve counterintuitive legacy cases and, where source-supported,
boundaries, duplicate/missing/empty records, NULLs, significant formatting, numeric
precision/overflow, errors, sequential effects and platform-specific behavior.
Adversarial review must reject silent correction as a mismatch. Finite randomized
and boundary tests establish only their stated scope, never all potential cases.

## Workspace setup and credentials

The first UI visit opens one settings form for source folders/upload mode,
process Markdown and optional exact WEDLX/Tran Repository locations. One Save
can also prepare the approved Copilot MCP bridge and selected project Zowe
profiles. The existing Coordinator owns configuration writes under its lock;
there is no additional engine, worker or ledger. Existing snapshots and accepted
evidence remain immutable. New intake uses saved defaults after restart;
explicit source uploads override the saved folder.

`GET /api/setup/workstation` returns settings plus `connection_setup`: selected
choices, local CLI availability, prepared file paths, commands and remaining
client actions. CSRF-protected `POST` accepts `settings` and optional
`connections={copilot:boolean,zowe:{mode,host,port,config_file,schema_file},db2?:{mode,host,port,database,location,driver,certificate_file,mcp_port,row_limit}}`.
Legacy requests/stored choices without `db2` remain accepted. Zowe modes are
`off`, `existing`, `create` and `import`. Inactive options are null;
create requires actual host/port and existing settings' two profile aliases.
Import accepts exact local supplied config/schema paths and preserves bytes;
a different existing destination is refused. A declared local schema pointer
selects its approved root filename (`zowe.schema.json`,
`zowe.config.schema.json` or `zowe.config.user.schema.json`); missing or unsupported
bindings stop preparation. Config and schema paths are both shown in the result. Nested selected aliases use safe
Zowe dotted names; literal dotted node keys cannot impersonate that traversal. Profile inheritance, host/port, HTTPS, certificate validation,
default type bindings and self-contained supplied schemas are checked before
writing. External `$ref`, `$dynamicRef` and `$recursiveRef` are never fetched.

Settings remain in ignored `.migration/workstation.json`; choices and managed
MCP hashes use ignored `.migration/connections.json`. The request is bounded to
32 KiB and local config/schema files to 1 MiB. All output paths reject symlinks
and Windows junctions. Invalid input/conflicts leave prior files unchanged;
ordinary write failures restore changed configuration, while concurrent external
edits fail closed and stay visible. A crash can leave valid newly prepared
connector files beside earlier preferences; Save reconciles those local files
without altering process evidence. This is configuration preparation, not an
atomic transaction spanning external clients or their secure stores.

Copilot preparation merges ignored `.vscode/mcp.json`, accepting VS Code JSONC
comments/trailing commas while preserving other server/input values. Managed
keys are `workbench-retrieval`, optional `workbench-db2` and
`workbenchDb2Token`. Existing different bindings are preserved and rejected;
only unchanged previously managed hashes authorize updates/removal. Shared
credential-input references are retained. The stdio retrieval server uses the
current Python executable, repository server path, running loopback origin and
`--role retrieval`; VS Code starts it without another dependency install.
Db2 uses the approved endpoint and VS Code password input, never a saved token.

Live mainframe source/dataset metadata access uses the typed read-only Zowe CLI;
Db2 catalog/data retrieval uses negotiated MCP tools. Driver access is confined
to the approved MCP server, not an alternate Workbench Db2 client. Copilot owns
approved retrieval; Claude remains local with zero MCP servers.

Db2 modes are `off`, `existing` and `gateway`. Off clears the selected endpoint;
existing requires the approved HTTP(S) MCP endpoint and creates no driver config.
Gateway requires actual host, Db2 service port, database, DDF location, registered
ODBC driver, loopback MCP port and row limit (1..500000); an optional local CA
file supplies exact validated PEM/DER bytes. Save derives
`http://127.0.0.1:MCP_PORT/mcp`, requires Copilot preparation and refuses the
Workbench's current port. The Db2 service port and MCP port are independent.
The pure `db2_setup.prepare_db2` helper is shared with existing CLI setup.
Config, CA and imported CA-source bytes join the same pre-planning baselines,
concurrent-edit checks and ordinary failure rollback as Zowe/MCP preferences.
No credentials are stored in these JSON settings. A missing CA produces an
explicit prerequisite, never verified access; symlinks, junctions, invalid
certificates and attached private keys are rejected.
Certificate encoding support follows the [IBM CLI/ODBC keyword contract](https://www.ibm.com/docs/en/db2/11.5.x?topic=cck-sslservercertificate);
certificate bundles require the installed driver's documented support.

The returned local server command uses the existing `tools/db2_mcp_server.py`
with `--transport http --config CONFIG --port MCP_PORT --interactive`. Interactive
startup requires a real local terminal, validates nonsecret fields, CA bytes and
registered driver before credentials, and restores temporary environment changes
when it exits. Password/token prompts do not echo or enter the UI/ledger. The
same FastMCP server retains typed SELECT-only tools, loopback binding, bearer
authentication and host/origin protections. Its search journal uses the selected
config's directory. No Db2 connection/query occurs during preparation or server
startup. Canonical fixed `.env` and existing `WB_DB2_CONFIG` modes remain supported.
Python-module presence is distinct from installed native-driver readiness; live
TLS/auth/read access still needs an approved read through Copilot.
Changed loopback ports or managed bindings require fresh Save.

Zowe preparation reuses `zowe_setup.prepare_profile`/`prepare_import` and the
existing CLI wrappers. Availability checks resolve installed launchers without
running them. The screen emits native PowerShell or POSIX secure commands;
Windows uses the native Node argv for an installed npm Zowe package and
`npm.cmd` for the optional installation command. The published v3 LTS channel
is a convenience command for an organization-approved installation, not an
automatic package download or permission to bypass enterprise deployment.
Missing CLI/runtime, secure credential entry, VS Code review/start and Db2
authentication remain explicit actions. No configuration implies successful
host access; setup makes no network, model or mainframe call.

The default workflow remains Claude local files and Copilot approved retrieval.
No model token, manifest declaration or reviewer answer is needed for local
intake readiness. Claude gets zero MCP servers. Copilot receives saved retrieval
context beside its immutable request; changes never rewrite request hashes or
frozen prompts. Source validation, connectivity, supported conversion and the
actual human return remain separate gates. Historical `/api/setup` enum clients
and `.migration/setup.json` remain supported without driving the active screen.

## What you provide once

| Input | Put it here / action | Why it is needed |
|---|---|---|
| Workstation | CPython 3.12, local writable disk, setup script; use the committed UI bundle | Installs locked dependencies and avoids a Node requirement for operators. Native Windows execution still needs a workstation smoke test. |
| Application export | Source folder chosen in Workspace setup, `WORKSPACE/Endeavor/`, or files uploaded at intake | Complete, readable UTF-8 source export with original relative member names. Include called programs, COPY dependencies, JCL, PROCs, INCLUDEs, control cards, BMS and SQL/DDL where applicable. A manifest alone cannot replace missing source. |
| Initial process | Markdown following `examples/process-input.md`, or the UI Excel template | Ordered jobs, steps, program/utility names, input/output groups and conditions. A new source version uses a new process ID. |
| Custom knowledge | `WORKSPACE/knowledge/application-knowledge.json`; start with `examples/application-knowledge.json` | Application/vendor utilities, aliases, semantics, evidence, record layouts, control-card behavior and known dependencies. The standard catalog is visible in `knowledge/mainframe-catalog.json`. |
| Background articles | `WORKSPACE/knowledge/inbox/`, up to 20 Markdown documents, 1 MiB combined | Devin/application notes. Treated as unverified evidence, never executable instructions or approval. |
| Zowe, when used | Authenticated CLI profile; `WB_ZOWE_PROFILE` | Account-visible read-only catalog/source operations. Profile presence is not successful authentication or complete discovery. |
| Db2, when used | Authenticated typed MCP URL/token; IBM ODBC driver and `pyodbc` for the bundled gateway | Schema/table descriptions without a prior schema allowlist. Discovery and sample access are distinct; no arbitrary SQL or automatic row sampling. |
| GitHub Copilot | Normal VS Code access and already approved MCP connections; optional `examples/mcp.json` selects `--role retrieval` | Read-only discovery and file/metadata retrieval into exact request-bound local inboxes. No coding, analysis, tests, review or conversion submission. Credits Unknown without a receipt. |
| Claude Code | Organization-approved VS Code extension or other approved host; local framework and approved exports | Local analysis, rules, development, testing and review. No MCP servers. `examples/claude-mcp.json` is empty; no setup or connection required. Local runner commands preserve the single Coordinator. |
| Actual SME return | One issued checklist, completed by the real reviewer; import once with attribution | Confirms or corrects interpretations. Unanswered/No/corrected items remain unresolved; no second questionnaire is generated. |

Nonsecret workstation defaults are saved through the UI. Authentication
variables, when needed by approved tools, stay private in the launch shell.
`.env.example` is an example, not an auto-loaded credential file. Do not paste credentials into
source, knowledge, intake or review files. The `runner agent` command uses a
local command inbox when the UI owns the workspace. Other direct-writer CLI
commands require stopping the UI first.

### Connection configuration

Save optional nonsecret retrieval values in Workspace setup. Private credentials
remain in approved secure tools or the launch shell. Root `.env.example` is not
auto-loaded; the Db2 server reads only its fixed `tools/dq3g_mcp/.env`.
The UI never asks you to paste credentials into a form or source file.

| Connection | Variables / prerequisite | Actual implemented behavior |
|---|---|---|
| Zowe | `WB_ZOWE_PROFILE`, optional paired `WB_ZOWE_ZOSMF_PROFILE`; actual service access | `tools/setup_zowe.py --interactive` prepares secure declarations; exact config/schema import is supported. Typed bounded lists/reads resolve missing sources. TPX aliases cannot substitute for z/OSMF/API host/profile mappings. |
| Db2 MCP | `WB_DB2_MCP_URL`, `WB_DB2_MCP_TOKEN` | Schema/table/describe tools, bounded sampling, explicit `db2_read_table_rows`, and resumable literal content-search tools. Supported revisions 2025-06-18 / 2025-03-26. Every account-visible schema/table is eligible; no allowlist or caller-supplied SQL. Automatic lineage does not export business rows. |
| Local Db2 FastMCP | Fixed `tools/dq3g_mcp/.env`, IBM ODBC driver and `pyodbc`; HTTP additionally needs `WB_DB2_MCP_TOKEN` | Python FastMCP provides stdio or authenticated loopback HTTP. TLS and approved PEM/DER certificate required. Query cap defaults to 500,000 and cannot exceed it; pages remain bounded. Private credentials never enter tool output. Existing JSON/ODBC modes remain explicit compatibility options. |
| GitHub Copilot | Already approved workspace MCP connections; optional `examples/mcp.json`, `--role retrieval`, existing local UI origin | The workbench retrieval profile exposes only `workbench_retrieval_task(process_id)`. Copilot writes requested files/response using approved file tools. No code, tests, analysis submission or second Coordinator. |
| Claude Code | Approved local files, configured Python; empty `examples/claude-mcp.json` | No MCP or remote connector connection. Local `runner agent` commands use the existing Coordinator or its filesystem command queue; this is not an MCP/HTTP proxy. |


Db2 `.env` recognizes exactly `DB2_LOCATION_NAME`, `DB2_HOSTNAME`, `DB2_PORT`,
`DB2_DATABASE`, `DB2_USERNAME`, `DB2_PASSWORD`, `DB2_SSL_CONNECTION`,
`DB2_SSL_CERT_LOCATION`, and `DB2_QUERY_ROW_LIMIT`. The matching launch-shell
values override file fields even when empty. Parsing never executes or expands
values. Keep the username commented in the file and supply it privately in the
shell. Certificate paths stay below the `.env` directory; symlinks/traversal and
SSL false are rejected. Blank row limit means 500,000; permitted values are
1–500,000. Settings status is separate from successful authentication.
Explicit legacy `WB_DB2_CONFIG` takes precedence, then an explicit
`WB_DB2_ODBC_CONNECTION`, otherwise the fixed `.env`. The JSON mode retains
`WB_DB2_USER`/`WB_DB2_PASSWORD` and `certificates/DB2-CA.cert`; external ODBC mode
retains externally managed TLS responsibility. No environment-file selector is
required. All modes enforce the query budget and read-only ODBC access mode.

A search begins with `db2_search_start(query)` and advances via
`db2_search_continue(search_id, row_budget=1000)`. It follows `SYSIBM.LOCATIONS`
recursively through configured three-part DDF names, deduplicates location/object
identities, enumerates `SYSIBM.SYSTABLES` without schema/type allowlists, then
attempts a fixed SELECT against every discovered object. Table descriptions,
including empty-table column names, and all supported cell contents are searched
as literal case-insensitive substrings. Numeric/date values use driver text
representations and binary values use hex; unsupported types are explicit gaps.
No procedures, jobs, bind operations, arbitrary SQL, network scans or source
writes are exposed. A configured read-only Db2 account remains required.

`db2_search_status` returns counts and `db2_search_results` pages matches or
per-object outcomes (`kind="matches"` or `"objects"`; at most 100 records,
`after=next_after`). Match excerpts are bounded and include location/schema/
table/column and cursor row ordinal. An ordinal is not a stable business key.
`db2_search_cancel` closes live cursors and retains results. Calls process at
most 1,000 fetched rows or roughly two seconds of work between driver calls;
ODBC login/query timeouts are 10/15 seconds. A row may be materialized by the
driver before its 1 MiB application byte check; this does not certify native
memory use at every database type/size. Query caps apply across continuations;
even an exact cap remains PARTIAL without proof of cursor exhaustion.

Private search state/results live under `.migration/db2-search/`, with one
server writer, eight active searches, a 256 MiB SQLite page cap and reserve.
Storage exhaustion records partial coverage and closes remaining search cursors.
SQLite transaction journals may temporarily require additional disk. Live
cursors expire after five idle minutes. Server restart/expiry cannot restore an
unordered table cursor: that object stays partial, while continuation visits
remaining objects. Use a new search to retry interrupted objects. These local
search records never replace frozen process evidence. The UI and CLI keep the
existing Coordinator/ledger and one-packet gates.

Coverage is account-visible and uses uncommitted reads, not a consistent
snapshot. Denied objects, unreachable/unadvertised locations, malformed catalogs,
row/storage/byte limits, and unsupported driver values cannot establish absence.
COMPLETE describes only an exhausted traversal of available catalogs/selectable
objects; it is not complete enterprise inventory or observed mainframe parity.
`discover_catalog(..., continuation=...)` also accepts the previous catalog
cursor so callers can continue beyond a single metadata page budget.

Zowe's “no secure properties found” means the selected configuration has no
secure declarations. The guided helper adds field names `user`/`password` to
the base profile's `secure` array. Run the emitted `zowe config secure` command
from that workspace (or its matching user-config variant), enter credentials
only at local prompts, then perform an actual permitted read. Existing defaults
and unrelated profiles are preserved. Import never searches home configurations.

Application routing facts: the supplied TPX session `TS0 DB2 2` is a source/Db2
hint, `SCHEDD` is the development CA7 hint, CICS is in UAT with the exact location
unconfirmed, and `SYSPL` is a JCL search hint. These facts do not establish an
API endpoint, dataset library, permission, CICS map or CA7 export facility.
Provide actual Zowe-visible libraries/services or original exported definitions.
WEDLX receives available files from Tran Repository/source systems; configure
exact local/mounted folder bindings in `knowledge/input-locations.json` using
`examples/input-locations.json`. Only an observed exact file binding resolves
availability. Layout, cutoff/completeness and business readiness remain unknown.

### Runtime and recovery

Use CPython 3.12 and the SHA256-locked wheels. `scripts/Start.ps1` and
`scripts/start.sh` reuse the existing installer when the environment is missing
or its locked dependencies are incomplete. They stop on install/preflight
failure and open the browser after service startup. `-NoBrowser` /
`--no-browser` suppress browser opening. The launch path owns one Coordinator.
Operators use the committed React bundle; Node 22+ is needed only to develop the UI. Keep the workspace on
local disk, back up the whole workspace, and run one Coordinator at a time.
Stop the UI before direct-writer CLI commands on the same workspace. The
`runner agent` local command inbox uses the running Coordinator and is the
explicit exception. Never delete a lock or
recalculate frozen hashes to get past a blocker. Restart/Resume preserves stage,
review quota and evidence. Transient stage retries are limited to three.

Preflight: `python -m workbench.preflight --workspace WORKSPACE --manifest MANIFEST --json`.
Folder validation: `python -m workbench.layout --workspace WORKSPACE`.
The executable agent workflow and continuation commands are in
[prompts/START_MODERNIZATION.md](../prompts/START_MODERNIZATION.md).

### Explicit resource limits

10,000 source files; 16 MiB UTF-8 bytes/file; 512 MiB and 2 million physical lines
combined; 40,000 source traversal entries; 100,000 workspace entries. Browser
source uploads are separately 32 MiB combined, HTTP/JSON documents 128 MiB,
workbooks 8 MiB. These are protective ceilings, not memory/stress certification;
per-line analysis/model expansion can reach the state or memory bound earlier.
The 822-file export and 700,570-byte source regression retain every input byte.
No dependent file is removed to fit the old POC limit.
SME v2 compacts technical blockers by program/type while preserving all raw gaps
in Context/coverage; business rules remain individual. At most 2,000 mandatory
review items; no silent truncation. Historical packet v1 is replayed unchanged.
New processes use fixture contract 4: a 4,096-case budget/program (up to 10,000),
at least 20 distinct randomized valid source-predicate input states per supported
logic item, and a runtime-generated unsigned 63-bit seed pinned at Start. Resume
replays that seed. Historical fixture contracts and minima remain unchanged. There are 192 atomic condition
comparisons and JSON depth 256. Coverage XLSX splits sheets at Excel's row limit.
Limits reject excess rather than silently truncating it. Required witnesses
that cannot fit the fixture budget remain coverage gaps. Do not omit dependent
files to fit a budget. The separate 200,000/600,000-scenario engineering campaigns do
not change these process limits.

## Implemented behavior and remaining adapters

| Area | Implemented | Boundary / next adapter |
|---|---|---|
| Source | Complete original line-order accounting, hashes, supported copybook field layouts, program inventory | Flat IF/ELSE/END-IF; comparisons and AND/OR; literal MOVE, CONTINUE, GOBACK/STOP RUN. No nested IF, PERFORM, READ/WRITE, arithmetic, SQL, CICS, REDEFINES, OCCURS, signed/packed decimals or continuation. |
| Layouts | Unsigned PIC 9 and fixed-width PIC X, simple named 01/05 declarations, LINKAGE groups named once each in PROCEDURE USING, group-correlated fixtures | JSON record transport; not EBCDIC, packed binary, COMP-3, VSAM or native datasets. Standalone level-77 items, FILLER, WORKING-STORAGE/FILE lifetime and initialization require adapters and remain blocked. |
| Conversion | Audited generated Python for fully supported programs, immutable shared versions | Source-order rule behavior is preserved; syntactic line-for-line Python correspondence is not claimed. Unsupported programs receive no full executable translation. No code is silently retired as mainframe-only. |
| Jobs | Named method per job, ordered steps and RC comparisons; actual record-adapter job comparison | Same field-name sets required between programs. New runs require at least 20 distinct randomized executed states per step, with full source/target comparisons. Never-executed steps and budget/state deficits remain gaps; historical single baselines remain replayable. DSN reads/writes, external scheduler, procedure expansion and restart semantics require adapters. |
| Agent handoff | Copilot retrieves requested source/metadata; Claude analyzes approved local files, implements and tests through the existing Coordinator | Missing/ambiguous returns remain gates. Retrieval is not validation, model claims are not test receipts, and no Claude MCP connection is allowed. Legacy source-free development evidence remains historical. |
| Synthetic data | Source-derived boundaries, invalid layouts, sequential effects, distinct logic states and linked-group match/mismatch witnesses | New contracts require at least 20 distinct valid states per supported logic item, with explicit budget/domain/reachability gaps. Native missing/duplicate/empty file/table behavior needs its own adapter. No exhaustive or observed legacy claim. |
| Source oracle | Independent source IR interpreter freezes expected results before generated Python execution | Both depend on the parser; parser errors remain a shared risk. No observed mainframe oracle or mainframe execution. |
| Verification | Full output/trace/RC comparisons, independent source-order job interpretation, per-rule decision/boundary/effect mutation, denied capability checks; new target contracts include directly tested input guards | Historical targets used the separate JSON adapter. No native mainframe malformed-record semantics are claimed. Unit suite and mutation checks do not substitute for actual legacy execution evidence. |
| SME | One frozen packet / one valid return per process, immutable question identity/Context/Metadata, Yes/No/Not sure, corrections retained | Corrections requiring new semantics remain blockers. A Yes on an unsupported-item description does not make its conversion supported. |
| Knowledge | Standard mainframe catalog, editable application/vendor JSON catalog, content-based classification, per-process immutable snapshot, bounded indexed Markdown and confirmed-fact JSON/index pair | Recognition never grants conversion support. No semantic cross-process auto-approval or autonomous interpretation of corrected prose. |
| Connectors | Local-first typed transitive discovery, Zowe source/metadata reads, Db2 catalog lookup and explicit row exports | Account/service visibility and parser limits remain explicit. No schema allowlist; missing libraries/dynamic bindings/TPX-only facilities need exports or actual service mappings. |
| UI | Local React intake/prompt/file workflow, real stage events, rule lineage, source coverage filters, review import, Pause/Resume/Cancel and downloads | New CICS intakes support source-bound literal BMS character layouts and FastAPI rendering; native controller, symbolic buffers, AID, state, security and data semantics remain named gaps. Workbench controls are not business replacements. |
| Reporting | One primary executive HTML report, six editable PPT slides, metric XLSX/CSV/JSON/history, complete source coverage JSON/CSV/XLSX/HTML, unique/membership counts, LOC and blockers | CICS/VSAM/interfaces unknown until evidenced. Db2 metric is distinct references in supplied SQL, not a confirmed estate table count. Physical/code LOC convention differs by source kind and is not equivalent complexity. |
| Inspection | PPT reopened, editable table count and canvas bounds checked, hashes recorded | Six sample slides rendered and visually inspected through Artifact Tool. Local browser and hosted Windows/POSIX setup/launch checks are scoped software evidence. Native PowerPoint, Windows 11 desktop and complete manual accessibility remain unverified. |


New agent-mode processes issue SME packet version 4; other modes retain version 3. Technical obligations group across
programs by source-evidenced construct family, with explicit ASSUMPTION and
unverified-obligation wording. Compound lines retain all observed families;
missing/unknown/mixed evidence remains visible. Full original blockers, source
spans, hashes and memberships remain bound to the packet; only display lists
truncate at whole program names. Historical v1/v2 generation/fingerprints and
issued packets remain unchanged. These family labels do not implement adapters
or let human Yes answers clear unsupported semantics. The pictured 19-entry
implementation was unavailable; current conservative classification is tested
against actual referenced source evidence.

## Metric rules

Source assets deduplicate by kind, name and SHA256. Process memberships count references separately. Production portfolio totals exclude processes created with the UI demo flag. Revisions with changed hashes count as distinct versions, not necessarily distinct logical programs; titles use **versions** accordingly. Snapshot history in SQLite is retained, and the report workbook includes previous non-demo snapshots. Report metrics project the eligible current process outcome; inspected artifacts, accepted snapshot, terminal state and completion event are committed together. Failed, cancelled and blocked work receives no completion credit.

A known rule is credited only when its SME answer is Yes, its whole supported program has no source blockers or output differences, and both decision outcomes have witnesses. `known_rule_verification_percent` divides those rules by all **extracted known rules**. It is never called total modernization percentage. Unsupported lines, unknown rules, uncertainty, omitted behavior and coverage gaps are shown separately and prevent `COMPLETED`. Non-executable and explicit out-of-scope lines are separated from applicable lines. Every supplied file/line retains its disposition/reason. Mainframe-specific credit requires a concrete verified replacement; native DD/dataset/scheduler behavior is not inferred away.

`COMPLETED` means the stated source-derived target profile finished its tests and report gates without recorded blockers. It does not prove all possible legacy inputs equivalent. `COMPLETED_WITH_BLOCKERS` records finished reporting with unresolved work. Waiting for retrieval/Claude analysis are prerequisites, not conversion status; historical ledger keys stay stable. Report failure leaves `REPORTING_FAILED`; Resume preserves the SME quota.

The frozen declared estate is 166 batch COBOL, 599 JCL jobs, 174 PROCs, 245
copybooks/layouts, 80 CICS screens, 108 Db2 tables, 450 CA7 schedules and 4 MQ
interfaces. These sum to **1,826**; the declared **1,829** has **3 unreconciled**.
The baseline remains user-reported/unverified in `knowledge/inventory-baseline.json`
(template `examples/inventory-baseline.json`). Executive report, PowerPoint and
workbook separate baseline, observed/unknown scope, verified converted versions,
unique logical assets, memberships and cumulative progress. Shared assets are
deduplicated. CICS screens and transactions are distinct; workbench controls/UI
are never counted as business replacements.

## Adversarial review

Every supported rule decision, atomic boundary comparison and literal effect receives deterministic mutation checks. Surviving masked/unobservable mutations are gaps; no detected witness is fabricated. Denied-capability checks remain. The workbench receives independent scoped code review before publication. A configurable independent model review for each future process is still an implementation gap; the runtime report explicitly describes its deterministic review method.

## Complete source accountability and organization

Coverage has one source-order row per original exported physical line: file/kind/hash, exact original text, stable semantic unit, source/target span and version, test witnesses, evidence, disposition, reason and replacement. File scope is explicit, including unused/unknown exports. Dispositions separate mapped verified/unverified, platform replaced verified/unverified, blocked, non-executable and out of scope. Unsupported syntax is never automatically mainframe-specific.

Applicable-line verification includes blocked/unverified in-scope lines in its denominator. Non-executable and out-of-scope lines are separate. Semantic-unit verification deduplicates rule spans. Known-rule verification covers extracted known rules, not all modernization. Empty denominators are unknown, not 100%. Intact frozen intake/source/analysis, human return, reproducible synthetic evidence, target artifacts and adversarial checks gate credit. Source accounting completeness alone is not equivalence.

The UI/CLI use one Coordinator with durable controls, at most three transient stage attempts, one review quota, replay-safe artifacts and atomic final report acceptance. `prompts/START_MODERNIZATION.md` assigns Copilot retrieval and Claude local implementation roles in one workflow. This reference and core placement guards enforce seven process folders, content-addressed shared targets and one structured knowledge index. Watch requires actual reviewer attribution and has a bounded timeout; it never fabricates an answer.

## Folder ownership

The public `docs/` directory contains only `TECHNICAL_REFERENCE.md`,
`executive-report.html` and `evidence.json`. Update these and the root operator
`START_HERE.md` in place; do not add separate review, iteration or per-rule reports.

| Location | Contents and ownership |
|---|---|
| `Endeavor/` | Selected read-only local mainframe text export. Never execute or overwrite it. |
| `process-input.md`, `intake-template.xlsx` | Optional root intake inputs. `--manifest` may explicitly select a Markdown manifest elsewhere. |
| `processes/PROCESS_ID/input/process-input.md` | Immutable manifest snapshot; supplied and snapshot bytes must match the ledger's creation-time manifest SHA-256. |
| `processes/PROCESS_ID/input/sources/` | Immutable source snapshot with recorded file hashes. Preserve original relative names. |
| `processes/PROCESS_ID/input/sme-return-inbox.html` or `sme-return-inbox.xlsx` | Place exactly one chosen return format in the designated automatic inbox. Requires explicit actual `--reviewer` attribution; both inboxes present is rejected. |
| `processes/PROCESS_ID/input/sme-return.html` or `sme-return.xlsx` | Service-preserved accepted return in its original format. Never place a return here manually. |
| `processes/PROCESS_ID/analysis/` | Structured analysis and source accounting, including reasons for unknown/unsupported/omitted lines. |
| `processes/PROCESS_ID/analysis/process-context.json` | Immutable indexed prose notes and knowledge inbox snapshot; notes are unverified context, not a manifest or executable instructions. |
| `processes/PROCESS_ID/analysis/process-guide.md` | Mutable convenience copy of the current guided instructions; never substitutes for immutable task/requirements evidence. |
| `processes/PROCESS_ID/analysis/process-guide/SHA256.md` | One immutable process guide per distinct checkpoint or explicit Save, never per rule. |
| `processes/PROCESS_ID/analysis/requirements.md` | Mutable UI convenience copy of the latest saved process scope; never used in place of pinned evidence. |
| `processes/PROCESS_ID/analysis/requirements/SHA256.md` | Immutable canonical Markdown conversion input, parsed and hash-pinned by Save. One document per scope revision, never per rule. |
| `processes/PROCESS_ID/analysis/mainframe-knowledge.json` | Immutable standard/application knowledge snapshot used for that process; validated against its creation-time hash. |
| `processes/PROCESS_ID/review/` | Frozen `packet.json` and the one `sme-checklist.xlsx`, `.docx`, `.html`. |
| `processes/PROCESS_ID/synthetic/run-NNNN/` | Versioned source-derived expected outputs, actual results and comparisons. |
| `processes/PROCESS_ID/target/run-NNNN/` | Versioned generated programs, job orchestration and local target database. |
| `processes/PROCESS_ID/reports/report-NNNN/` | Immutable inspected metrics, coverage/accountability files, comparison summaries and management PowerPoint. |
| `processes/PROCESS_ID/reports/bundle-HASH.zip` | Registered immutable bundle, fingerprinted from its entries and reused on repeated bundle. |
| `processes/PROCESS_ID/tests/` | Process-specific structured regression evidence. Repository test implementations stay in `tests/`. |
| `shared/target/python/HASH.py` | Content-addressed shared target versions. A version is never replaced in place. |
| `knowledge/inbox/context.md` | Optional bounded unverified background; never approval or verification. |
| `knowledge/mainframe-catalog.json`, `knowledge/README.md` | Versioned standard classifications, utilities, native-semantic checklist and official references. |
| `knowledge/application-knowledge.json` | Editable private application/vendor utility knowledge, initialized from `examples/application-knowledge.json`; future intakes freeze edits. |
| `knowledge/records.json`, `knowledge/INDEX.md` | Canonical provenance-bound SME-confirmed interpretations and one compact index; target verification is separate. |
| `prompts/OPERATOR_GUIDE.json` | Compact checked navigation/FAQ cache with source hashes and relevant spans; never process state, rules, approvals or a second workflow. |
| `workbench/`, `frontend/`, `tests/`, `tools/`, `scripts/`, `docs/`, `prompts/`, `examples/`, `.github/` | Repository implementation, verification, entrypoints, instructions, synthetic examples and GitHub/Copilot metadata. |

Process IDs are stable, validated identifiers beginning with a letter. Process
roots may contain only `input`, `analysis`, `review`, `synthetic`, `target`,
`reports`, `tests`. Root-level process files, miscellaneous process folders,
path traversal and symlinks are refused. Generated Python/database artifacts
belong in `target` or `tests`, not analysis/review/input. Input allows only the
manifest, source snapshot and two designated return paths. Use structured
coverage records; never create a Markdown file per rule or per source line.
Process Markdown is limited to the input manifest, original source exports under
`input/sources`, and the explicitly requested process-guide/requirements copy and
version paths above. Editable `process-specific.md` notes stay in the external
authoring package; their indexed content is frozen as structured process context.
Do not add another Markdown file in process input.


## Failure and recovery matrix

| What can go wrong | Detection / treatment | Required action or remaining boundary |
|---|---|---|
| Excel declares a smaller range than its actual job rows, has duplicate/out-of-bounds cells or malformed XML | Intake checks actual worksheet cell locations against declared dimensions before reading job rows; malformed structure produces a named validation error | Repair the workbook using the supplied template. No hidden rows are silently discarded. XML entity/declaration checks also cover UTF-16/32. |
| Wrong Python, missing package/wheel, broken UI bundle | Setup exits on failure; preflight checks runtime, dependencies and assets | Use the supported environment and locked installation. Do not ignore install errors. |
| Full/read-only disk, unsuitable shared filesystem | Preflight checks access/capacity; writes fail explicitly and retain state | Use local disk with headroom and backups. Filesystem behavior, antivirus interference and sudden hardware failure cannot be certified by a permission check. |
| Two workers, occupied port, browser opens early | Single-writer OS lock; optional port diagnostic; launch scripts check failures | Stop the other owner, then restart. Never delete the lock or ledger to bypass the check. |
| Missing/partial/truncated source export | File/byte bounds, manifest resolution, classification and full-line accounting | Supply complete exports and dependency lists. Account-visible discovery cannot prove that inaccessible libraries do not exist. |
| Binary/EBCDIC data mistaken for UTF-8 source | Text decoding/intake bounds; unrecognized content stays blocked | Export source as text without changing program columns. Keep business data formats in the custom knowledge; native record conversion needs an adapter. |
| Member has no suffix, misleading suffix or multiple plausible types | Content evidence plus names, COPY references and manifest context; conflicts recorded | Inspect classification evidence. Unknown/conflicting files remain in scope and are not excused as comments. |
| Case-only, Unicode-normalized, file/directory or reserved-name collision | Intake rejects ambiguous source paths before writing a process | Preserve unique portable relative names and explicit library provenance. Do not let Windows overwrite a member silently. |
| Duplicate member/program across libraries | Ambiguous dependency or program identity rejected | Supply the actual search order/version provenance; current converter does not infer STEPLIB/COPY resolution across libraries. |
| Malformed/partly blank intake row or colliding job method | Strict Markdown/Excel row, identity and ordering validation | Fix the named row before Start. No populated row is silently dropped. |
| JCL PROCs, symbols, INCLUDEs, conditions, GDGs, DD concatenation or DISP | Recognized/accounted; unsupported native semantics block credit | Add a source-supported adapter with expansion, lifecycle and error/restart tests. Never delete allocation behavior merely because IEFBR14 does no program work. |
| Standard utility name recognized but semantics differ by site/version | Catalog captures evidence, risks and needed inputs; no utility adapter inferred | Supply utility version, options, control cards, exits, return codes and side effects. SORT may be a site-selected product. |
| Custom utility/wrapper hides calls, filters or side effects | Editable application catalog and unresolved utility findings enter the one review | Document underlying programs, files, controls, RCs and failures. A catalog entry does not execute code or turn support on. |
| COBOL compiler or storage semantics differ | Unsupported constructs explicitly blocked | Record compiler/options, decimals, signs, truncation, rounding, overflow, padding, collating sequence, REDEFINES/OCCURS, working storage and run-unit lifetime. Implement and test each needed adapter. |
| SQL/Db2 and SQLite differ | SQL behavior remains unsupported; discovered references are not converted tables | Resolve nulls, decimals, CCSID/collation, timestamps, isolation, commits/rollback, cursors, SQLCODE, constraints and concurrency before claiming parity. |
| VSAM/IMS/MQ/files are not ordinary SQLite rows | File families/utility risks retained; native I/O not credited | Preserve access mode, record/key layout, duplicate keys, status codes, locks and transaction/message semantics. |
| CICS screen appears mapped but actions differ | BMS/source inventory retained; no business UI/API credit without implementation | Capture map fields/attributes, AID keys, validation, state, navigation, COMMAREA/channels and transaction/security behavior. Workbench UI screens are not replacements. |
| Scheduler/external interface unavailable | Scope questions and source blockers; job adapter covers only the declared bounded profile | Include calendars, triggers, time zones, cutoffs, dependencies, endpoints, acknowledgments and retries. Python step order alone is not CA7 parity. |
| Connection denied, token expired, TLS/proxy/driver mismatch | Configuration separated from live/partial discovery evidence; bounded retries/timeouts | Repair the actual account/driver/certificate. Never disable read-only enforcement or infer empty catalog means no assets. |
| Discovery pagination ends at a limit or data changes mid-scan | Cursors, counts and partial/complete account-visible evidence | Preserve the cursor and timestamps. Current discovery is not a transactional estate snapshot or automatic dependency fetcher. |
| Source/target/catalog/SME/report bytes changed | Recorded immutable hashes, source/analysis replay, return identity and artifact checks | Restore an intact backup or start a separately identified process from the original evidence. Never recalculate hashes to certify modified history. |
| Stale knowledge or hostile instructions in source/notes | Data-only bounded catalog; frozen provenance; no executable catalog fields or automatic approval | Review evidence for this source/version. Prior confirmations are interpretations, not permission to execute commands or approve changed rules. |
| Too few or unrealistic synthetic records | Source-derived mandatory branches/boundaries/matches, deterministic interactions and witness counts | Record missing obligations explicitly. Four sample rows cannot certify 85 rules. New processes use a 4,096-case budget and requires at least 20 distinct valid states per supported logic; unreachable or unsupported obligations stay gaps. A budget is not exhaustive coverage. |
| Expected results copied from target | Expectations frozen from independent source IR before target execution | Shared parser remains a common-mode risk; SME/source review and mutation checks help but cannot establish observed legacy parity. |
| Invalid data accepted by exported Python | New target contract embeds input validation; direct target rejection is tested | Distinguish malformed input rejection from business-rule failure. JSON validation is not proof of native malformed EBCDIC-record behavior. |
| Good tests miss a rule, overwritten effect or incorrect boundary | Per-rule mutation checks and explicit surviving/missing witness gaps | Treat masked or surviving mutations as unresolved; do not invent passing evidence. |
| Crash, pause, cancellation, duplicate Start/return or expired wait | Durable stage state, bounded retries, idempotent matching return, quota and cancellation checks | Resume the recorded stage after resolving the cause. Do not rewrite outputs or reissue a checklist. |
| Partial SME response or a correction requires new semantics | Actual answer/correction retained; no automatic Yes or second round | Deliver the blocked report with exact unresolved items. One review cannot guarantee all unknown business facts will be resolved. |
| Misleading completion percentages or double counts | Full-line, semantic-unit and known-rule denominators separated; unique versions vs memberships | Use counts with scope/evidence labels. Unknown is not zero and lines of code are not equivalent complexity. |
| Report generated but missing/damaged | Inspection, metric consistency, report hashes and terminal acceptance gate | `REPORTING_FAILED` is not completed. Preserve evidence, repair the named cause and Resume. |
| OS/native application behavior differs from test host | Published validation identifies tested and untested environments | Run the real workstation/Zowe/Db2/provider smoke checks. Browser rendering and native PowerPoint need local confirmation. |


## Extension priorities — preserve these requirements

The original requested destination includes full process conversion and React
business screens/REST APIs. These are not implemented merely because the
workbench has its own UI/API. Extend the existing engine incrementally:

| Required extension | Evidence required before enabling it |
|---|---|
| Native data / numeric behavior | Compiler/options, EBCDIC/CCSID, record widths, signs, COMP/COMP-3, rounding/overflow/truncation, OCCURS/REDEFINES, status/error cases, independent expected bytes. |
| Full COBOL and other source languages | Complete source-order control/data flow, paragraph/call/lifetime behavior, dependencies, exceptions and explicit per-unit target lineage; no bundled unexamined logic. |
| JCL / CA7 / utilities | Resolved PROCs/symbols/INCLUDEs, DD concatenation/DISP/GDG, control cards, return codes, calendars/triggers/restarts and verified side effects. Recognizing utility names never implements them. |
| Db2 / VSAM / IMS / MQ / interfaces | Keys/joins/referential consistency, null/decimal/collation/time semantics, transaction boundaries, locking, idempotency, protocol errors, generated coherent positive/negative multi-file records. SQLite limitations must remain explicit. |
| CICS / BMS to business React / REST | Before/after maps, AID keys, navigation, validation, transaction/session/security behavior, API contracts and executable tests. Count real replacements only. |
| Broader synthetic generation / diagnosis | Source-derived independent expectations; boundary, invalid, missing-match, sequence and interaction cases; label data-contract, parser/oracle, code and environment faults with evidence. Do not tune data to make the target pass. |
| Automatic source closure | Read-only cross-library dependency search with provenance, duplicate resolution and complete/partial discovery evidence; no invented search order. |
| Independent model review | Approved provider, bounded excerpts/budget, structured findings, no authority to change answers or bypass gates; deterministic checks first. |

Keep one method per job and ordered step calls, content-addressed shared program
versions, before/after scope/history metrics, genuine single-round SME review,
versioned knowledge, exact omission reasons and a final PPT gate. Broadening
support requires implementation, negative tests and independent review. Until
then report the unmet requirement as blocked. The full earlier design and
research remain in Git history at published commit
`f9f500bc9abc4e4f82070b521ea339c5eab3b348`; they are not duplicate live prompts.

## Interface and accessibility contract

One primary next action; an eight-step Coordinator-backed progress guide; one workstation settings form;
plain-language statuses; evidence behind disclosure controls; one executive
report link. Workbench actions are not fabricated modernization progress.
Use semantic controls, persistent labels, keyboard focus, status/alert regions,
text alongside colors, reduced-motion support and responsive layouts. Test
small viewports, zoom, keyboard and screen-reader behavior on the actual browser.

Public Wells Fargo homepage CSS supplies red `#d71e28`, yellow `#ffcd41`, charcoal
`#3b3331` and neutral `#f4f0ed`. Use system fonts, not unlicensed brand fonts or
invented corporate marks. This is public-style alignment; internal Wells Fargo
design-system approval is not available. WCAG 2.2 AA is the accessibility target,
not a claim that automated checks constitute certification. Local Chrome checks
cover setup, intake defaults, work windows and exact 18-digit record transport at
320px, 390px and 1280px. Lost-response retries retain their original work-window
choice or serialized record bytes; feedback follows the server's saved outcome.
Failed measurement reads clear loading and expose recovery. Long recovery IDs
remain fully available with narrow-screen wrapping. The current exercised matrix,
including checks not exercised at each viewport, lives in `docs/evidence.json`.
Complete keyboard/popup, zoom and screen-reader acceptance remains separate.
Windows 11 desktop, native PowerPoint and live source connections require
acceptance on the target workstation.

## Efficient engineering and evidence

Use the durable Coordinator rather than an open-ended agent conversation to
run a process. Parsing, input validation, fixture generation, comparisons,
mutation review, report metrics and hashes are deterministic. Generated programs
are compiled once per suite, with validation/checkpoints per record. UI polling
is serial and pauses when hidden. Model calls are optional, bounded and cached;
report actual provider usage, not guessed savings or model-independent token
costs. Retrieve only the relevant source spans and structured evidence records
when an agent must reason. Never repeatedly load the entire evidence ledger.

Development checks in the locked environment:

```sh
python -m unittest discover -s tests
python tools/review500.py
python tools/review_expanded.py
python tools/scenario_campaign.py --seed 20261003 --total-scenarios 200000 --output .implementation/tmp/campaign-200000.json
python -m workbench.layout --workspace .
python tools/check_handoff.py
```

The standalone `tools/synthetic_cases.py` generator uses the same V4 fixture
contract and current record adapter: a fresh runtime seed, 20 distinct randomized
states per supported logic, and frozen source/copybook byte hashes. Supply
`--seed` with an unsigned 63-bit integer for exact replay. Insufficient budgets
and finite domains remain coverage gaps; generation alone grants no conversion
credit. Historical suites retain their original contract.

On macOS, set `TMPDIR` to the absolute nonsymlink workspace `.implementation/tmp`
path before tests; the system `/var` symlink is intentionally rejected by fixture
workspace validation.

Install frontend development dependencies with `npm ci` in `frontend/`, then
`npm run typecheck`, `npm run build`; from the repository root run
`npm --prefix frontend test` for the component, accessibility and layout checks.
The same test script runs in the hosted platform-smoke workflow. Engineering tests use fictional fixtures only and clear
all source/provider environment settings. The real HTTP tests bind loopback.
The 1,000 named checks comprise R001–R500 and 500 new R501–R1000 checks. They are
not 1,000 independent reviewers. The required campaign selects 200,000 unique
program/input scenarios (200 programs × 1,000 records). An optional expanded run
uses `--total-scenarios 600000` and a fresh private output path; historical receipts
are preserved. The campaign compares executed Python and reference
behavior against independently coded family expectations, records
its seed, implementation hashes and replay indices, and uses zero LLM calls.
Finite combinations do not establish exhaustive legacy parity.

Keep only the current solution executive report and one `docs/evidence.json`
index, with full scenario descriptions and reproducible receipts. Private raw
logs belong under `.implementation/tmp/`; retain them while diagnosing failures.
Do not create new review/validation/iteration Markdown files. Per-process frozen
reports and bundles are legitimate audit evidence and are never overwritten to
make the current repository look cleaner. A historical report without the new
executive HTML remains historical; do not backfill evidence retroactively.

## Primary references

- [Wells Fargo homepage](https://www.wellsfargo.com/) and [public stylesheet](https://www.wellsfargo.com/ui/css/homepage-ui/ps-homepage.64e2080ce97f4cefb1b5.css)
- [Wells Fargo accessibility](https://www.wellsfargo.com/about/inclusion/accessibility/) and [WCAG 2.2](https://www.w3.org/TR/WCAG22/)
- [IBM COBOL](https://www.ibm.com/docs/en/cobol-zos/6.4.0), [DFSORT](https://www.ibm.com/support/pages/dfsort), [Db2 catalog](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-catalog)
- [Zowe CLI](https://docs.zowe.org/stable/web_help/index.html), [MCP transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
- [SQLite transactions](https://www.sqlite.org/lang_transaction.html), [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/), [React effects](https://react.dev/reference/react/useEffect)
- [GitHub repository instructions](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/add-custom-instructions/add-repository-instructions)

File/utility-specific primary IBM references remain in the visible
[mainframe catalog](../knowledge/mainframe-catalog.json) and its
[editable-knowledge guide](../knowledge/README.md).

- [FastMCP server transports](https://gofastmcp.com/deployment/running-server), [Db2 DDF three-part names](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=widdip-three-part-names-aliases-in-distributed-data-applications)

## Agent-mode intake, grouped decisions and rule reporting

`--assistant claude_files` is the active local-file entrypoint over the existing
Coordinator states and packet-v4 analysis contract. `--assistant agent` and older
modes remain compatibility interfaces; immutable v1–v3 evidence retains its
fingerprints. Both hosts use `.claude/skills/`; the single Start prompt assigns
roles. Copilot retrieves files through approved MCP; Claude interprets local
source and performs all implementation, tests and review without MCP.

### Retrieval and local analysis handoff

`python -m workbench.runner agent PROCESS_ID --workspace WORKSPACE` reads the
current task and pinned local evidence paths. Missing source/metadata is described
in a bounded `--request-file REQUEST_JSON`, not an SME question. The Coordinator
creates a stable, immutable request and a copyable Copilot prompt. Requests bind
the process and current evidence; missing, ambiguous, denied or partial responses
cannot imply source closure or conversion support. Continue uses the exact recorded
inbox, never a broad filesystem search or guessed latest folder.

| Local interface | Contract |
|---|---|
| `agent PROCESS_ID --workspace WORKSPACE` | Read the current analysis task, required local artifacts and continuation state. |
| `agent ... --request-file REQUEST_JSON` | Validate a bounded retrieval request and preserve its immutable packet plus generated Copilot prompt. |
| `agent ... --continue` | Inspect the recorded request inbox, validate response identities/paths/hashes, preserve accepted evidence and resume eligible work. Absent or invalid responses retain named gaps. |
| `agent ... --refresh` | Recompute analysis after actual tested semantic changes; preserve earlier artifacts and require a fresh task-bound result. Changed loaded adapters require restarting the existing service first. |
| `agent ... --analysis-file ANALYSIS_JSON` | Submit bounded structured Claude analysis against current task/lineage hashes. No test, parity or SME credit is granted by accepting a model assertion. |
| `agent ... --measurement-file RECEIPT_JSON` | Import an actual attributed usage/effort receipt through the existing ledger; unknown charges remain Unknown. |
| Copilot `workbench_retrieval_task(process_id)` | Read the pending retrieval packet only. Copilot's approved source/file tools perform the pull and write its exact local return folder. |

Per-request placement below `processes/PROCESS_ID/analysis/retrieval/REQUEST_ID/`:

- `request.json`: immutable requested identities, bounds, return schema and prompt.
- `inbox/files/`: original files and requested metadata written by Copilot.
- `inbox/response.json`: the completed response manifest, written after its files.
- Accepted returns: frozen and registered by the existing Coordinator; later
  responses never rewrite previously accepted snapshots or source evidence.

Default discovery requests batch at most 128 needs without truncating the frozen
lineage. The local view's `retrieval_state.total_need_count` and
`remaining_need_count` expose the total and needs outside the current packet.
Complete imports can advance to the next batch; explicit NOT_FOUND or AMBIGUOUS
results stop at a visible checkpoint rather than issuing repeated automatic
prompts. Inspect the unresolved reason before making a new request.

The CLI `--request-file` input is exactly an object containing `needs`; analysis,
request and measurement input files must be regular non-symlink JSON of at most
128,000 bytes. The `needs` array contains 1–128 items with required `kind`, `name`, `reason` and
optional `source`, `relationship`, `status`. The packet derives stable `need_id`
values, a SHA-256 request ID, the source-generation/iteration/lineage bindings and
a complete copyable prompt. `request.json` and `response.json` are each bounded
at 512 KiB. The response has exactly `request_id` and `items`, with one item per
need. A `FOUND` item has `need_id`, `status`, portable original relative `path`,
`sha256` and `provenance`, with optional `staged_path`; `NOT_FOUND` has `reason`
instead of path/hash, and `AMBIGUOUS` may
also name bounded candidates. Provenance requires `origin`, actual `tool`,
`locator` and timezone-aware `retrieved_at`; optional keys are `environment`,
profile name and `encoding`. No credentials or business-row samples belong here.
A denied or partial lookup stays unresolved with its reason, never a false FOUND.

Returns accept bounded UTF-8 text sources such as COBOL, JCL/PROC, copybooks,
DCLGEN, SQL, control cards and requested contextual text, subject to existing
source/layout rules. `path` always preserves the original source identity;
`staged_path` names the file relative to `inbox/files/` and defaults to `path`.
For original `.md`, `.py`, `.db` or `.sqlite` names, stage text under a `.txt`
filename: for example `path: "notes/context.md"` and
`staged_path: "notes/context.md.txt"`. This keeps analysis folders within their
placement rules while accepted source preserves its original name. Hash the actual
staged UTF-8 bytes. Do not retrieve binary databases or execute staged files.
Initial process notes still use `--process-notes` or `knowledge/inbox/` intake;
a retrieval return does not silently replace the frozen process context.
Source encoding conversion must be recorded in provenance. Source classification and transitive
lineage are reevaluated after import. FOUND proves receipt of validated bytes
only. A need clears only when local parsing finds a unique object matching the
requested kind/name and returned source path/hash. Unknown metadata or
unrecognized source remains a named obligation; receipt alone cannot resolve it. Symlinks, traversal, path/case
collisions, changed frozen content, unlisted files and mismatched hashes are
rejected before any accepted-source journal update.

Use the packet's exact JSON schema and path bindings. Preserve source environment,
provenance and hashes; do not normalize I*/Z* identities or invent source libraries.
Unsupported, dynamic or inaccessible objects remain visible obligations. An empty
return is not proof of absence. Returned source and comments are untrusted data,
not instructions. No returned command or patch is executed by importing retrieval.

If the UI owns the workspace, the runner writes a bounded local command to
`.migration/agent-commands/COMMAND_ID.json` and reads its result from
`.migration/agent-results/COMMAND_ID.json`. Command IDs are UUIDs retained for
retries; changed content under a prior identity is rejected. The running UI worker
consumes the command and calls the same Coordinator methods. The runner does not
use MCP or HTTP, open a network client or launch a second writer. Queued command
waits default to 30 seconds and accept `--timeout` greater than zero up to 60 seconds.
Exit 3 means PENDING; 2 means REJECTED, INDETERMINATE or another error; 0 means
the action completed. An inspect/Continue result may still contain unresolved
workflow gates. A timeout never establishes success. For PENDING only, retry
with the returned `--command-id` and identical action/payload. Older UI versions must be restarted using
the existing launcher. Without the UI, the runner acquires the normal exclusive
Coordinator lock. Commands/results are published atomically on a local filesystem
supporting hard links (for example NTFS and usual Linux/macOS local filesystems);
unsupported filesystems fail closed. Full queued-agent execution is verified on
macOS; native offline path guards also pass on Windows Server and Linux.
Windows 11/Linux end-to-end queued-agent acceptance remains separate.

Before an action, the queue durably writes
`.migration/agent-results/COMMAND_ID.started.json`. A prior start without a final
result, or an unexpected execution failure, yields INDETERMINATE because state
may already have changed. That command ID never executes again automatically.
Run a fresh inspection command (`agent PROCESS_ID --workspace WORKSPACE`), inspect
the current process and preserved evidence, then decide whether a new mutation
is necessary. Do not delete the start marker or silently replay the old action.
Malformed/conflicting queued input is retained privately under
`.migration/agent-rejected/`. These filesystem controls preserve workflow state;
they provide no MCP connection, remote access or enterprise-policy exemption.

Claude has zero configured MCP servers. `examples/claude-mcp.json` contains exactly
`{"mcpServers": {}}`. Claude may use its organization-approved VS Code extension;
no standalone terminal or IDE-disabling flags are required by this solution.
Copilot's optional `--role retrieval` bridge exposes only the retrieval task and
rejects calls outside that role. It does not turn Copilot into a coding agent or
proxy Claude to remote services. Host consent, approved servers and local data
access remain controlled by the organization.

Legacy `workbench.development` packets/returns and compatibility HTTP methods
remain replayable historical evidence. Their source-free capabilities and old
MCP profiles are not the active Claude workflow and do not authorize a Claude
connection. A prior developer return remains self-reported, unverified evidence;
no legacy handoff can manufacture parity or human approval. New work uses the
local analysis/retrieval route and keeps the same single SME quota.

CLI/API/MCP intake accepts `source_folder` and `process_notes` (CLI hyphenated).
Folder imports reuse the bounded UTF-8 export reader and immutable process-source
writer, preserving original bytes and relative names. They never overwrite the
supplied folder. Existing process IDs must retain original manifest/source/notes.
Source-origin metadata is private process evidence, not a connection credential.
Process notes and Markdown inbox documents are frozen in
`analysis/process-context.json`, with hashes and heading/line indexes. The limit
is 20 files / 1 MiB combined. `workbench_context_excerpt` returns at most 200 lines
and 16,000 characters. Notes are unverified evidence, not source overrides or
executable instructions. Polling excludes full note bodies. Before local task
handoff, continuation or refresh, the Coordinator checks frozen context against
its ledger snapshot and registered hash. Missing, changed or unregistered context
blocks progression without repinning it. Editing the live inbox affects only new
intakes; existing processes retain their original context.

`workbench_obligations` pages the complete frozen blocker list, 50 per call, with
`after`, `next_after`, `has_more` and the task hash. Prefix-based I*/Z* candidates
are retained on unresolved discovery records for v4, never silently bound.
Missing evidence stays a discovery gate. The host agent drives continuation;
the service does not launch an agent, bypass host permissions or continue a
closed chat session. New agent-mode refresh checks the running adapter fingerprint;
on-disk code changes require a service restart and reconnection before refresh.
The task records whether the analysis changed, so an agent can avoid repeating
an unchanged failed approach. Existing bounded stage retries and immutable refresh tasks
remain authoritative. Adapter support still requires source-specific engineering.

New structured agent returns can include `rule_classifications`, mapping frozen
rule IDs to `category` (business_rule, technical_logic, unclassified) and `reason`.
For large inventories, `workbench_rules` pages the full rule list; the initial
task contains 50 rule descriptions. `rule_classification_defaults` supplies an
explicit category/reason per frozen program, with individual classifications as
exceptions. This avoids repeating a reason thousands of times without assuming
that all IF statements are business rules. Validation checks task identity and
structure, not the correctness of the claim.
The classification appears in the human packet. Missing categories remain
unclassified; recognizing IF syntax does not establish business purpose.

Packet v4 groups only equal decisions within the same source/program version,
complete semantics, layouts/dependencies and invocation context, with identical
preceding effects on predicate inputs. Input effects are hashed incrementally.
Group membership and equivalence hashes are frozen in Context. Import expands
actual answers to the listed rule IDs with group/reviewer/correction provenance;
corrections and uncertainty cannot yield verified credit. Grouping never changes
the source rule inventory. Distinct programs/environments are not merged based
on similar prose. Technical-family compaction retains every original blocker.

A report-only, versioned rule inventory derives credit from replayed coverage;
it does not change frozen source analysis. Business decisions, technical adapter
units and unclassified contiguous source spans stay separate. Unclassified spans
are obligations whose internal semantic rule count is unknown. Each identified
rule retains source text/locations/version, memberships, target spans/version/text,
verification evidence and status. Statuses are identified, implemented_unverified,
converted_verified and blocked. Credit retains the existing whole-program gate;
new classifications do not create finer proof than the underlying tests provide.

Job totals deduplicate repeated invocations. Process totals count unique
source-version occurrences; memberships across jobs are separate. Program views
include owned copybook dependencies; their overlapping totals are not summed as
unique process totals. Unassigned obligations remain listed. Denominators include
all identified in-scope rules in that category; empty totals are N/A. V4 unknown
classifications prevent an unblocked completion claim.

The primary executive report presents the same rollups as Excel and PowerPoint.
Its `rules.html` detail, `rules.json` and `rules.csv` preserve original/modernized
mappings. These are immutable per-process report artifacts, not new public
narrative documents. Spreadsheet text is escaped and large excerpts use numbered
chunks. Existing accepted executive models remain replayable. The Coordinator
passes its already verified coverage model into reporting to avoid a second
expensive target replay during the same report stage.

`Coordinator.program_comparison` and read-only `GET /api/process/{id}/comparison`
project only the accepted report generation, validating artifact/report hashes,
exact parsed bytes, frozen executive context, identities, statuses, ownership and
recomputed totals. Program keys bind name/path/source version; job-only and other
unowned source stay selectable. Pages default to 25, maximum 50; every clipped
excerpt, mapping, test, reason or gate preview exposes its count/completeness.
Filters are all, gaps (identified/candidate/blocked), verified and selected No.
They do not invoke source/target execution or change the ledger. Unique inventory,
selected-program, matching-filter and page totals remain separate.

Comparison diagnostic contract 2 freezes process integrity gates, exact SME
item/answer/correction/reviewer and packet/return references, per-rule witness
shortfalls, named branch gaps, differing case IDs and program review/test failures.
Own-rule gates lead bounded previews, including shared copybook owners. Scope
labels distinguish the affected source span from rule, whole-program and process
causes. Successful local line reasons are never displayed as the failure cause
of a process integrity gate. Process-only SME obligations remain in UI/HTML even
when no individual rule gaps exist; guidance preserves the consumed single packet.
Closure guidance is separate from evidence and cannot grant verification credit.
Only registered receipts with hash baselines become artifact download links;
preserved SME returns remain local references with their frozen return hash.
Historical reports remain immutable: absent diagnostics stay Unknown; historical
process details may be read only from accepted frozen coverage/context. The new
`rules.html` renderer adds local filters without changing historical executive
rendering or the inline executive report's script restrictions. Specific rule
deficits remain on their cards; complete program gates appear once with local
links, and shared process gates appear once. Gate details are indexed by rule to
avoid quadratic duplication in large reports; the full inventory retains all facts.

`workbench.backends` defines the versioned target boundary; only python-sqlite is
registered. Future backends need generation/comparison implementations and the
same coverage gates. SQLite currently stores comparison results; this is not
proof of native Db2 transaction semantics or a converted application database.
The factory UI/report adds an evidence-grounded Python/SQLite versus Python/Oracle
assessment. Oracle is a future, unregistered target: qualification covers exact
numeric/NULL/empty-string behavior, SQL dialect/errors/cursors, constraints,
transaction/DDL boundaries, concurrency/recovery and operations. Only cited
structural SQL/DCLGEN or selected Db2 lineage evidence can trigger the database
assessment; filenames and generic utility names cannot. The backend registry
continues to reject unimplemented targets. Service extraction requires independent
business responsibility, data ownership and a verified transaction boundary.

V4 synthetic coverage counts source predicate values **after** preceding source
writes, not irrelevant input padding. Input layout and terminal units separately
require 20 distinct randomized valid records. Finite domains, overwritten values,
unreachable outcomes, mandatory boundaries and exhausted budgets remain explicit
gaps; repeated runs cannot manufacture distinct states. Jobs compare complete
ordered traces, skip decisions, records and return codes across randomized and
boundary witnesses. Native scheduler/dataset I/O remains outside that adapter.

Each supported program exports `tests/run-NNNN/PROGRAM/test_generated.py` plus
`unit-results.json`. Run the Python file directly with Python 3, preserving the
process folder hierarchy; it has only standard-library dependencies. It checks
frozen suite and target byte hashes, invokes the real generated entry point for
valid and invalid inputs, and compares canonical JSON types, full results and
caller-input immutability. No oracle is recalculated from the target. Coverage
regenerates the canonical test module, executes it and matches the receipt before
crediting it. Missing/modified evidence revokes credit. Unit tests complement the
independent source interpreter and adversarial mutation checks. The live factory
view labels prior success **Recorded pass · not freshly verified**; reports derive
current validation status from replayed coverage. These tests do not establish
observed mainframe parity or exhaustive scenario coverage.


Zowe `--check` inspects the selected project config/schema without network calls
or credential access. `--normalize` only deduplicates secure declarations when
structural/schema checks pass, preserving a hash-named private backup. External
schema references are not fetched. No profile roles/defaults are deleted and
credentials/connectivity remain UNVERIFIED until a permitted live read succeeds.
Native Windows/Linux and both agent-host smoke evidence are required separately
from local Python and frontend checks.

Windows 11 is the workstation target with CPython 3.12 and a writable local,
hard-link-capable disk. The shipping Windows PowerShell launcher prepares the
locked environment, restores missing pip through ensurepip, starts the one
Coordinator and opens the browser after the local service binds. PowerShell 7
native-error preferences are also exercised. POSIX uses the same Python engine.
Workspace/source paths reject junctions and symlinks before access; layout
traversal prunes redirects. Source and copybook UTF-8 bytes retain LF/CRLF/mixed
line endings and hashes. Implementation-module packaging normalizes checkout
line endings independently of immutable mainframe exports.

For an approved Windows npm Zowe install, `connectors.zowe_command` resolves the
existing package's declared JavaScript bin and invokes native Node with argument
boundaries intact. Native executable installs remain supported. Package/bin/Node
absence is a named preflight gate; no batch-command fallback or source-system
write is permitted. Secure configuration uses the same resolver. This validates
the local launch configuration without asserting authentication or connectivity.

The native platform smoke workflow executes shipping setup and offline
intake/ledger/report/CLI, junction, encoding, adapter and launcher tests on Windows
and Ubuntu using the locked dependencies. Current execution receipts are indexed
in `docs/evidence.json`; a configured workflow alone is not evidence. Windows
Server CI is separate from Windows 11 desktop, Excel/PowerPoint, enterprise
agent-host and live read-only connector acceptance.

### Consolidated program knowledge

`workbench.program_insights` projects existing frozen analysis, requirements and
replayed coverage. It does not add a parser authority, workflow or source mutation.
The factory view's `program_insights` object includes an inventory over 17 frozen
file classifications, separate file/selected-file/observed-definition counts,
conservative unquoted Db2 `CREATE PROCEDURE` observations, and COBOL program pages.
Statement literals, comments and CALL references do not become procedure definitions.
Source-hash/line evidence and unresolved classifications remain visible. DCL means
DCL/DCLGEN descriptors here; CICS BMS counts describe retained sources, not installed
screens or verified replacements. Whole-estate totals remain Unknown.

Each program has technical job/transaction entry mappings, parsed fields and
dependencies, source-derived functionality observations, categorized/unclassified
rules, default or saved Yes/No selections, validation obligations, risks and persona
guidance. These are starting technical/functional documentation, not invented
business requirements. A No rule retains the exact requirements exclusion reason;
Yes is not conversion credit. Verified counts are Unknown until coverage replay.

Factory pagination uses `program_after`, separately from obligation `after`, with
20 programs per page. Detail lists cap at 30 and expose completeness flags; the
existing source/coverage/rules artifacts retain complete accounting. New final
reports freeze `program-insights.json` and `program-insights.html` alongside
`factory.html` under `reports/report-NNNN/`. The HTML has a program index and source,
technical, rule, validation and persona sections. Both artifacts are registered
and pinned by report inspection. Historical reports are unchanged; no per-program
Markdown, duplicate requirements document or additional SME checklist is created.

## Factory contract and bounded online delivery

New agent-mode intakes and online intakes carry factory contract version 1.
`workbench_factory` and `GET /api/process/{id}/factory?after=0` expose the same
assessment, discovery, target-design, implementation, human-review, verification
and delivery projection. Obligations page in groups of 50 with stable evidence
identities, investigation steps and recorded stage attempts. These are views over
the existing Coordinator, not a second scheduler or ledger. The UI Evidence →
Factory view and CLI status use the same projection. Capability recognition across
14 domains never establishes blanket support for a language or subsystem.

Online Markdown intake uses this table instead of the batch table:

```text
| Transaction | Program | Mapset | Map |
|---|---|---|---|
| ELIG | ELIGIBLE | | |
```

Blank map bindings mean unknown, not absent. If supplied, both Mapset and Map are
required and the map must resolve within its named mapset. Transaction IDs are
case-insensitive 1–4 alphanumeric characters. Intake freezes transactions and
workload along with identity and source. Online roots resolve programs and maps
transitively; no synthetic batch job is invented. Batch dependencies still need
source-supported linkage and retain their existing accountability gates.

A successfully tested flat-record program can be packaged under
`target/RUN/online/` as a **local online candidate**: Python service, React form,
OpenAPI description, source/target contract, Windows/POSIX launchers and HTTP
comparison receipt. Business module filenames are content hashes under `modules/`
to avoid Windows collisions with runtime files. The service invokes the existing
generated program; it is not another COBOL converter. Expected cases come from
the frozen source oracle and are compared through the actual HTTP interface.
Unsupported record programs receive no record candidate. A separately verified BMS character layout may produce a rendering-only candidate with transaction execution disabled. Generated candidates remain distinct
from verified native CICS replacements in JSON, Excel, HTML and PowerPoint.

New online intakes carry `cics_contract_version=1`; marker-absent historical
source analyses, requirement catalogs and retrieval prompts keep their prior
contracts. The new discovery graph resolves bounded multiline `EXEC CICS` map,
program, file/dataset, queue, transaction, channel/container and remote-system
references. Dynamic or ambiguous identities remain gaps. Supplied CSD transaction
bindings must agree with the manifest; source commands or supplied map bindings
require actual transaction resource evidence before closure. Resource definitions
are evidence of identity, not executable behavior or permission to access systems.

Typed Db2 descriptions are non-executable `DB2_TABLE_DESCRIPTION` JSON assets
with schema/table, columns, observation provenance (canonical locator must equal
exact `SCHEMA.TABLE`) and nullable DDL/constraints/
indexes/triggers. Missing metadata and native SQL/type/transaction/auth semantics
remain explicit obligations; a column description does not prove full DDL.
New CICS retrieval requests use schema 2 and require Zowe CLI for mainframe exports
and typed read-only Db2 MCP for catalog/DDL. The exact inbox and immutable source
journal remain authoritative. The existing approved MCP tools may not expose every
requested DDL component; do not invent it or conceal its absence.

`workbench.cics` implements `BMS_CHARACTER_LAYOUT_V1`: literal DFHMSD/DFHMDI/
DFHMDF, complete FINAL/END, bounded dimensions, positions, nonoverlapping character
fields, supported protection/intensity/cursor attributes and printable ASCII
INITIAL values. Explicit ATTRB defaults use UNPROT/NORM; absent ATTRB uses
ASKIP/NORM. Unsupported operands, symbolic layout, encoding and native effects
remain named gaps. The DFHMDF attribute byte precedes displayed data. IBM source
references: [DFHMDI](https://www.ibm.com/docs/en/cics-ts/5.6.0?topic=macros-dfhmdi)
and [DFHMDF](https://www.ibm.com/docs/en/cics-ts/5.5.0?topic=macros-dfhmdf).

Requirements GET filters (`program`, `screen=MAPSET/MAP`, `kind`, `path`) apply
before the existing 50-item pagination; duplicate/unknown parameters fail closed.
Safe unnamed constant fields alone can be omitted without a dependency redesign.
Save retains every hidden page/filter No in one pinned Markdown. Map definitions,
editable/named fields and controller actions cannot be silently waived.

The same Coordinator verification issues `synthetic/RUN/SCREEN_ID/` source
expectations/comparisons, `tests/RUN/SCREEN_ID/` executable unit module and receipt,
`target/RUN/SCREEN_ID.py`, shared content-hash Python code and the online package.
At least 20 distinct runtime-randomized valid states per input/layout are required;
finite domains never receive duplicate padding. Constant display fields have one
source value and are compared across distinct randomized input contexts, without
claiming 20 distinct display values. Mutation candidates stream and stop at the
first actual differing witness; receipts record the checked cases, and cancellation
is checked throughout source planning, target/unit/HTTP execution and review.
Independent source interpretation,
actual target execution, mutation witnesses and authenticated FastAPI comparisons
cover layout/field behavior only. The linked map/controller witness pins source
identity and lineage; it does not execute a native controller.

`POST /api/screens/{transaction}/{screen_id}` accepts exactly `values`, validates
source-owned fixed-width character inputs and returns the complete rendered layout
or rejection. Protected outputs cannot be supplied as inputs. It shares bounded
JSON, duplicate-key, bearer and origin checks, and has no native session/data side
effects. A layout-only transaction returns 409 from session creation and transaction
execution. Coverage replays source/requirements, units, mutations, target copies and
HTTP package receipts before layout-only credit; tampering, cancellation or an
unresolved human return withholds it. Program ownership associates only the bound
map units even when multiple maps share one file. Native command gaps stay visible.

The local runtime uses an explicitly supplied private `ONLINE_TOKEN` of at least
32 characters, binds to loopback port 8766 by default and supports isolated,
expiring sessions, revision checks, request idempotency and SQLite rollback.
Requests are bounded at 64 KiB, active sessions at 1,000, and committed requests
at 100 per session. Reusing a key with changed input fails. The browser retains a
pending request across transport failure. Native CICS session state, BMS/AID
behavior, RACF identity, Db2/VSAM/IMS transactions and distributed commits remain
unverified obligations. SQLite stores local session/retry state, not a migrated
enterprise database. No production authorization or automatic deployment is implied.

Launch a reviewed candidate with the repository's locked Python environment and
`python application.py` (or the supplied launcher). Keep the token in the launch
environment. Mutable runtime state defaults outside the immutable package under
`~/.pts-online-state/CONTRACT_HASH`; `ONLINE_STATE` can select an operator-owned
local directory. `ONLINE_PORT` can choose another local port; choose a free port
separate from Workbench and the Db2 MCP listener. When the Db2 gateway uses 8766,
8767 is an example candidate port if free. The operator guide gives native
PowerShell and POSIX launch syntax. Do not edit issued
packages or run this service inside the workbench's control API.

Consistency checks run at factory stage boundaries; violations record named
findings and stop advancement. Existing source/hash, review and report replay
checks remain authoritative. `python tools/check_factory.py` verifies shared
MCP/HTTP exposure, skill presence and documentation bounds. Run it after changes,
with focused regressions, then the full suite and required review/campaign checks
at release gates. CI runs native Windows/Ubuntu smoke checks on pushes and pull
requests; configured CI is not evidence of an executed native run. No periodic
background audit or independent agent launcher is installed.

## Pilot economics and forecast contract

`workbench.economics` is a deterministic projection of the existing ledger,
not another workflow engine. SQLite adds append-only status transitions, stage
attempt timing, attributed measurement receipts and resumable work-session
identities. Existing ledgers acquire these tables without rewriting history.
Service attempt durations use monotonic clocks, including I/O; wall status time
separates queue, agent/SME/discovery waits, pause and service stages. A crashed
attempt has unknown duration. Historical partial timing cannot calibrate a whole
process. Service, work effort and elapsed time can overlap and are never summed.

The running UI owns all writes. Open **Effort & scale** from workspace navigation
or **Evidence & reports → Effort & scale** for a selected process. Its work-window
controls start, stop or close unmeasured windows through POST
`/api/economics/work/start` and `/api/economics/work/stop`. Start accepts `id`,
`process_id`, `actor` and `stage`; stop accepts `id` and optional `abandon`.
Stages are discovery, analysis, mainframe, conversion, sql, validation, review,
reporting, rework and framework. Framework uses null process_id. Use a unique
stable session ID and actor/session identity; stop before human waits. Retry
returns the existing receipt. A restart loses the monotonic session clock:
close the session as unmeasured rather than charging downtime. Work windows
measure agent session time, not human attendance or total project completeness.
Internal work-clock receipts retain the measured monotonic duration even when
coarse UTC audit timestamps fall on the same tick. Only the protected internal
observation with its reserved session ID and exact clock attribution uses this
rule; timestamps still must be ordered and in the past, and durations finite and
nonnegative. Imported detail work remains bounded by its stated UTC interval.

Active Claude sessions append a bounded 64 KiB receipt through
`python -m workbench.runner agent PROCESS_ID --workspace WORKSPACE --measurement-file RECEIPT`,
including the local queue when the UI is running. GET `/api/economics?process_id=ID`
reads live metrics. POST `/api/economics/receipts` records an attributed receipt;
POST `/api/economics/forecast` previews a plan. Mutation routes retain the
same-origin/token guards; preview is read-only but uses the same authenticated
POST transport. With the UI stopped,
`python -m workbench.runner measure --workspace WORKSPACE --file RECEIPT`
uses the existing exclusive writer. Do not launch it beside the UI. Copilot's
retrieval-only MCP surface does not expose development or economics operations.

Every receipt requires `id`, `kind`, `process_id` (nullable), `evidence` (a bounded
source description/reference, never credentials), and `recorded_by`. IDs are
idempotent; changed content under an old ID is rejected. Optional `supersedes`
corrects a same-kind/scope receipt without deleting it. Process receipts freeze
under `processes/ID/analysis/measurements/SHA256.json`; workspace/account receipts
remain in the private ledger. Integrity failures withhold forecasts/conditional
balances. Session/provider prefixes are reserved for internal observations.

| Kind | Additional fields and meaning |
|---|---|
| `work` | `actor`, `stage`, decimal `hours`, timezone-aware `started_at`, `ended_at`; intervals must be in the past. Imported detail work cannot exceed its actor interval; internal work windows use the protected monotonic clock described above. `stage: pilot_total` with `complete: true` explicitly attests total repeatable process effort across all stages/actors, including rework. Stage detail is contained in this total, never added again. Framework investment is workspace-wide. |
| `usage` | `provider`, `account`, `model`, timestamps and `quantities`, such as `{"credits":"5.25"}`. Default `coverage: partial`. `coverage: complete_process` requires a process and a whole-pilot credits-only total for that provider/account. Its detail receipts are not added again. Imported overlapping intervals, duplicate totals and conflicting attribution withhold affected totals/calibration. |
| `budget` | `provider`, `account`, `unit: credits`, `allowance`, `consumed`, `period_start`, `period_end`, `snapshot_at`; process_id null. Show the dated actual balance and tracked subsequent usage separately. Conditional remaining assumes no untracked charges and becomes Unknown for expired or straddled periods. An allowance is not a live account connection. |
| `plan` | process_id null and `plan` as below. This is an attributed scenario, never conversion credit. |

Example scenario (assumptions, not measured pilot data):

```json
{"cohorts":[{"id":"batch-processes","unit":"process","total":100,
"hours_per_unit":{"low":"15","base":"20","high":"30"}}],
"capacity_hours_per_week":"40"}
```

Units are `process` plus the eight estate category keys. `sample_process_ids`
selects calibration only; optional `process_ids` defines actual cohort membership.
Repeated process cohorts require disjoint membership and `allocation_note`.
Asset rates require separately allocated assumptions; whole-process and asset
work cannot be added together. Different asset categories require a disjoint-work
allocation explanation. Optional `usage_per_unit` entries carry provider, account,
unit and low/base/high assumptions. Explicit rates retain ASSUMPTION provenance.
Without rates, complete attributed effort and whole-pilot credit receipts from
intact accepted COMPLETED non-demo/non-fixture processes calibrate min/mean/max.
A one-pilot rate is provisional, not a statistical confidence interval. Provider,
account and unit stay separate; raw tokens never become credits. Legacy provider
counters are captured even on failed structured responses; cache reuse adds no
new token charge. Claude/Copilot host charges require actual receipts.

The model exposes sample IDs, completed/remaining units, estimated subset, unknown
units, full remaining effort only when all cohorts have rates, capacity weeks,
separate observed service/sequential elapsed projections and billing provenance.
Declared estate totals remain unverified; the existing 1,829 versus 1,826 mismatch
remains visible. Completed scope, comparable complexity, dependencies, waits,
reuse and future framework work limit extrapolation. Optional stale plans produce
an explicit forecast error and Unknown estimate without blocking modernization.
No forecast certifies a finish date, observed mainframe parity or 100% conversion.

Each new report freezes economics JSON/HTML/CSV and an Excel effort sheet beside
its existing evidence; the primary executive report links the same snapshot.
Reporting duration is still open at that snapshot and completes in the live
ledger afterwards. Accepted report bytes are never refreshed in place. Learning
summarizes scope, artifact types, tests, gaps and timing; its response displays
up to 50 recent pilots while calculations use all eligible cohort members.


## Operator requirements and selected conversion scope

UI/local-file intake enables `requirements_selection`; job-led discovery must finish
before `WAITING_REQUIREMENTS`. The shared Start command opts in with
`--select-requirements`. Existing SDK callers and historical processes keep their
original workflow unless explicitly opted in. Nothing is converted or issued for
SME review until an operator Save. Default Yes selects scope; it never supplies
SME approval. The pinned local requirements artifact is readable by Claude; the
legacy MCP requirements endpoint is read-only, not a scope-answer tool.

GET `/api/process/ID/requirements?after=0&path=FILE` pages 50 stable source units
and returns the retained file inventory. Unit IDs bind path, source hash, physical
span, kind and parsed rule identity. Rules remain individually selectable;
contiguous technical/context spans are grouped. POST to the same route supplies
`catalog_hash`, `revision`, `excluded_ids`, `saved_by`. It uses same-origin/session
protection and compare-and-swap revisions. The UI attribution means the local
operator clicked Save; it is not an authenticated named SME identity. An identical
retry of the last request returns the saved revision; changed stale requests fail.
Sources and selections are checked before use. The UI retains an
in-memory draft per process across route/process switches, tied to its original
catalog hash and revision. A changed live binding blocks Save until explicit
**Reload saved choices**; no draft becomes evidence before Save. Browser unload
warns about unsaved scope, but does not persist it across reloads. The complete frozen UTF-8 source
is downloadable through GET `/requirements/source?path=FILE`, with a verified hash
and attachment disposition, including portable Unicode filenames.

Save writes canonical UTF-8 Markdown (32 MiB maximum) containing an exact JSON
selection and readable source/choice/replacement table. It freezes
`analysis/requirements/SHA256.md`, parses those exact bytes as conversion input,
commits the ledger revision, then updates `analysis/requirements.md`. A lost
response/copy failure can be retried without duplicating the revision. The pinned
snapshot is authoritative; manual draft edits cannot silently change conversion.
Previous versions stay immutable. Save invalidates old agent tasks and queues
analysis through the existing Coordinator. Changed adapter catalog identities
preserve prior evidence and stable No choices but require a new operator Save.
Packet issue locks scope; subsequent changes need a new process.

The selected IR omits No rules, preserves original rules as `omitted_rules`, and
binds target semantics to the requirements hash. An omitted writer consumed by
retained logic blocks generation, including later conditional job steps, repeated
program invocations and successive jobs sharing records. Excluded required
layouts, COPY/platform dependencies and job behavior require a verified
behavior-preserving replacement;
unknown semantics are never cleared by a No flag. Generated supported modules
retain record validation, ordered effects, rule trace and source/requirements
hashes. Real source-derived comparisons and adversarial mutation evidence remain
mandatory; new selected-mode fixtures require at least 20 distinct valid randomized states
per applicable logic item plus the existing dependency/invalid/boundary witnesses.
Historical fixture contracts remain frozen. This is bounded
semantic verification, not native mainframe parity or exhaustive proof.

Coverage keeps every original line and marks explicit No rows with the exact
reason “Not converted because selected No in requirements.” and the saved
Markdown hash/path. `rules.json`/HTML include the entire source-unit comparison:
source identity/span, choice, omission or replacement commentary, candidate versus
evidenced replacement status, target versions/spans and test/evidence references.
Non-runtime source structure has an explicit rationale, not executable credit.
Rule JSON/CSV/Excel and job/program rollups separate original total, selected,
verified, unverified/blocked and `excluded_by_requirements` counts. Percentages
cover requested Yes scope; they do not claim complete original-source conversion.
Executable omissions prevent whole-source asset credit and partial scopes cannot
calibrate full-estate process effort/credits. Unknown business/technical categories
remain visible; excluded unknowns do not masquerade as classified rules.

The economics UI exposes GitHub Copilot credits used per provider/account from
actual `usage` receipts (`quantities.credits`). Known zero and Unknown differ;
conflicting/overlapping billing is withheld. No token-to-credit conversion or live
GitHub billing connection is inferred. Optional budgets remain available in
collapsed detail. Process polling keeps requirements/rule detail bounded; full
selection, source and evidence load on demand.


## Guided preparation, handoffs and database observations

Explicit fictional intent uses the existing ledger `demo` flag, is pinned in the guide and must match on Prepare retry. Walkthroughs are excluded from production inventory and pilot forecasts; names never infer this flag.

`POST /api/intake/prepare` explicitly creates a new `guided_contract_version=1`
local-file process before exports exist. It freezes the actual canonical manifest,
context, knowledge and original source membership, with `source_intake_pending=true`
until compatible static closure and outstanding receipt identities are resolved.
Empty input never creates a placeholder program, starts conversion or issues SME
questions. Legacy `/api/intake` retains its one-or-more source requirement. Same
manifest/initial source/context/prompt retries reuse the existing prepared process.
Prepared analysis context must be text of at most 16,000 characters; overbound
requests are rejected before process creation rather than silently truncated.
Changed input needs a new stable ID. The existing Start/advance/Continue lifecycle,
ledger and single writer own all transitions.

`GET /api/process/ID/guide` is read-only. It presents eight steps and the actual
next action, source closure, pinned requirements and registered outputs. Explicit
`POST /guide/save {}` freezes a canonical process instruction Markdown and updates
its convenience copy. Stable guided checkpoints pin the new guide automatically.
A stale or modified pinned guide cannot supply a current copyable prompt. Setup
Save also writes the one ignored `.migration/workstation.md` with validated
nonsecret configuration. A missing/stale companion needs Save; GET never repairs
it or echoes altered content. A process freezes the setup context it consumes as
structured `analysis/workstation-SHA256.json`; later global edits cannot rewrite it.

Guided schema-2 retrieval adds a hash-bound absolute workspace and exact inbox.
Found mainframe source requires read-only Zowe CLI command provenance; typed Db2
catalogs/DDL and record exports require approved Db2 MCP provenance. Strict guided
version 1 recognizes typed catalogs for batch and online processes; CICS action
and resource gates still require CICS version 1. JSON kind/key escapes and a
single leading UTF-8 byte-order mark do not change typed receipt identity; the
original export bytes/hash remain immutable. Record snapshots require an explicit
guided row request even when their JSON spelling differs. Catalog recognition supplies static table facts,
not verified SQL, keys, constraints or native database equivalence. No Claude
MCP, driver, HTTP proxy or second writer is introduced. Historic request bytes and
replay contracts remain unchanged. Copilot only retrieves. The current Claude
prompt references actual process, context, source, task, requirements and guide
paths/hashes and instructs local analysis, implementation, randomized tests,
adversarial review, adapter refresh and fresh analysis return. The primary Copilot
prompt appends configured Zowe aliases and the Db2 endpoint from the registered
frozen process setup context, when present, as configuration-only data with its
path/hash. Later global settings do not substitute another environment. Original
request bytes, identity and exact return inbox remain unchanged; unavailable or
conflicting approved connections require an explicit retrieval gap. No code plan clears
a gap. Requirements Save and authentic review remain separate human gates.

The Database view uses only registered, hash-checked process SQLite artifacts.
Schema candidates retain source lines and specific unsupported features. Explicit
pre-SME schema preparation requires saved Yes scope, complete closure and accepted
Db2 MCP catalog/DDL provenance. Any No touching a schema source blocks its build;
manual self-claimed provenance is insufficient. The local schema-only database is
separate from immutable verification `target.sqlite` and does not run native
business SQL. Only validated emitted DDL and parameterized inserts execute locally.
Tables and paged records are read-only; arbitrary SQL, WAL sidecars, unknown tables,
coerced filters and unsafe paths are refused. Integer display strings preserve
large exact values; decimal storage preserves fixed scale without claiming arithmetic.

Record comparison uses immutable before/after exports with exact keys, input/run,
environment, scope, completeness and consistency facts. It distinguishes insert,
update, delete, unchanged, initial-state and final-state differences. Equal five-row
run deltas cannot hide twenty source-only historical rows or prove whole-table
parity. The approved Db2 row tool uses uncommitted read; absent a qualified consistent
observation, equality/native parity is withheld. No agent executes mainframe jobs.
Unsupported controllers, business SQL and types remain named obligations.

The management deck remains six editable slides. Its first slide relates source,
Copilot, frozen process evidence, Claude, Coordinator verification and target/report
components; legacy/target size and known original/selected-No/verified rule counts
use the same report model. Python AST statement counts include generated validation
and scaffolding and are not equivalent to COBOL rule counts. Old dates are context,
not deletion authority. Future Python/Oracle, Python/BigQuery, Java and .NET adapters
must implement `TargetBackend` generation/comparison and pass the same source,
selected-scope, actual execution, linked-state, adversarial and report gates before
joining the executable allowlist. BigQuery requires workload/transaction redesign
qualification, not automatic transactional Db2 substitution.

The single issued SME packet also exports a self-contained local HTML review.
Explicit Yes/No/Not sure answers, bounded commentary and the actual reviewer are
saved with **Save review file**, downloading `PROCESS_ID-sme-return.html`; browser files cannot silently
overwrite the original. No network, extensions, Python or MCP are required for the
SME. The operator imports exactly one base64 `html` or `xlsx` return with reviewer
attribution. The parser never executes returned HTML; it validates the canonical
shell, original immutable packet/hash, process/source, complete unique IDs and
explicit answer values. HTML consumes the same ledger quota and preserves exact
raw bytes as `input/sme-return.html`; XLSX retains its historical receipt contract.
Runner watch accepts either designated `input/sme-return-inbox.html` or `.xlsx` and
refuses simultaneous files. Coverage, integrity, reports and bundles revalidate the
accepted format. Modified, unanswered or mismatched returns cannot create approval. Any nonempty
correction/commentary remains unresolved even with Yes; preserve the actual concern
rather than deleting it to obtain a green result.

### Compact operator reference

`prompts/OPERATOR_GUIDE.json` is a source-bound index for assistants answering
operator questions. It records portable paths/SHA-256 bindings, bounded relevant
line spans, exact UI labels, FAQ answers and all 46 numbered review-job-aid steps.
The authoritative owners remain this reference, `START_HERE.md`, the shared Start
prompt and implementation. `tools/check_handoff.py` rejects stale or unsafe bound
sources/ranges. After an owner changes, inspect its affected facts, revise the
cache and rebind hashes; never merely rehash contradictory text. The separately
offline HTML review draft is tracked at
`examples/mainframe-modernization-job-aid.html`, with embedded fictional inputs
and screenshots. Its portable path and hash are bound in the cache; it is the
illustrated companion to `START_HERE.md`, not another workflow or process receipt.

Read this cache first for static how-to questions, then only the relevant cited
spans if detail is needed. It has no mutable process status, current prompt,
counts, credentials or billing. For current-task inspection use existing
`runner agent PROCESS_ID --workspace WORKSPACE`; an inspection can enable the
local-file workflow on historical processes, advance queued work or prepare a
missing retrieval request, so it is not universally read-only. For status only,
use `runner status` after stopping the UI, or the running UI's read-only guide.
Do not query raw SQLite/ledger files or create a new HTTP/MCP status proxy.
Unknown gates stay Unknown; no cached screenshot or green label clears them.


## Interface ownership and accessibility

This reference is the maintained design and interaction contract. The local tool
uses the public Wells Fargo red/yellow direction, system typography including
Segoe UI on Windows, semantic text states and visible keyboard focus. Internal
Wells Fargo design-system compliance requires its approved standards.

Canonical UI Map:

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
| --- | --- | --- | --- | --- |
| Navigation and saved place | `frontend/src/main.tsx` | Existing Coordinator and selected process | Overview, Setup, Intake, Evidence; Setup drafts remain mounted across navigation | Frontend navigation regression and local Chrome keyboard walkthrough |
| Setup fields, errors and commands | `frontend/src/WorkspaceSetup.tsx` | Validated workstation API settings | Existing/create/import Zowe and approved Db2 modes; app-owned Setup errors and first-invalid focus | Setup regressions, field/error associations and browser failure/recovery |
| Next step and exact prompts | `frontend/src/GuidedProcess.tsx`, `workbench/guide.py` | Hash-bound process guide and current request | Eight workflow steps; stale or missing evidence blocks actions | Guided API/local-file regressions |
| Source comparison and gaps | `frontend/src/ProgramComparison.tsx` | Accepted immutable report evidence | Per-program, gap and selected-No filters | Source/target report and frontend filter tests |
| Database records | `frontend/src/DatabasePanel.tsx` | Registered SQLite artifacts and typed snapshot comparison | Paged read-only tables and exact key filters | Composite-key, identifier/decimal, delta/history and byte-limit checks |
| Colors, focus and scrollbars | `frontend/src/style.css` | Shared application stylesheet | Native controls; visible scrollbar and forced-colors fallback | Frontend tests plus scoped contrast, keyboard, narrow-screen and zoom observations |
| Table Selection | `frontend/src/RequirementsPanel.tsx` | Hash-bound requirements catalog and explicit Save | Native Yes/No checkboxes per source unit; filtered selections retain all IDs | Requirements selection, CICS selection and frontend tests |
| Select/Listbox | Native HTML select in its owning panel | Current filter/mode state and validated API options | Operating-system popup is intentional; no authored listbox | Frontend labels/filter tests; full popup matrix remains pending |
| Form | `frontend/src/WorkspaceSetup.tsx` and each owning panel | Server validation and form state | Setup, estate scenario and database filters own persistent field errors and first-invalid focus; other operations focus their error summary | Field association/focus regressions and scoped browser checks; all-form assistive-technology qualification pending |
| Scrollbar | `frontend/src/style.css` | Global scrollbar tokens and forced-colors CSS | Document/panel overflow keeps visible operable scrollbars | Frontend style tests and scoped Chrome media observations |
| Toast | `frontend/src/main.tsx` and owning panel inline feedback | Actual operation result or persistent error | Persistent status/alert feedback; critical content does not depend on an ephemeral toast | Frontend status tests and operator save/error walkthrough |
| CRUD | Existing Coordinator through `frontend/src/main.tsx` | Ledger lifecycle, immutable artifacts and explicit saved scope | Prepare/update scope/cancel preserve evidence; no hard-delete variant | Guided API, requirements, cancellation and named workflow checks |

Setup owns its validation messages instead of browser validation bubbles, links
the invalid field to the persistent error and preserves the draft after failures.
Leaving Setup inside the app preserves its values; actual page unload uses the
browser's unsaved-change warning. Setup collects no passwords or tokens. Route titles
identify the current screen. These safeguards do not establish full screen-reader,
all-route accessibility or Windows 11 browser acceptance. A third-party static
auditor that requires separate `DESIGN.md`/`UX-CONTRACT.md` cannot certify this
repository's consolidated contract; record that tool result separately from
executed runtime checks rather than converting it into a passing receipt.


The shared stylesheet is copied to `workbench/static/style.css` by the frontend
build. The bounded online pilot stylesheet is an adapter checked against the same
font and control tokens. Input borders use `--field-border: #827c71` and keyboard
focus uses `--focus: #1763aa`; body fonts prefer Segoe UI on Windows. The skip link
is clipped while idle and occupies normal document flow when focused. Table and
lineage regions have a name and keyboard focus so wide evidence can scroll within
the panel. Scope drafts remain local and unsaved until the actual operator Save. Native textareas intentionally allow vertical resizing so long instructions remain expandable; horizontal width stays contained. The generic design auditor's resize-none and separate ownership-manifest requirements remain recorded policy findings, not a conformance waiver.

Verification uses [WCAG reflow guidance](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html),
[non-text contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html)
and [focus visibility guidance](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html).
Scoped browser geometry and finite contrast tests do not certify complete WCAG
conformance. Windows 11, screen-reader, native popup, actual browser zoom and
organization-specific design-system acceptance remain separately qualified.
