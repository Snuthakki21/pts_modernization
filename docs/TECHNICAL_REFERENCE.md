# Workbench technical reference

Start with [START_HERE.md](../START_HERE.md). The current solution summary is
[executive-report.html](executive-report.html); inspect [evidence.json](evidence.json)
only when detailed engineering evidence is needed. This file is the single
operating, implementation and extension reference. Update it in place.

## Operating promise

After initial setup: provide the process manifest and complete Endeavor export,
click Start, return the one authentic SME checklist, then receive one primary
executive report. Copilot Chat operates through the local workspace MCP bridge;
no LLM endpoint/token is required. Local analysis, supported Python conversion, deterministic
synthetic generation, comparison, adversarial mutation checks, knowledge updates
and the six-slide management PowerPoint run automatically. Blockers stay visible.
The Python/SQLite target is non-production. Full COBOL/CICS/SQL semantics require
source-supported adapters; recognizing syntax or submitting a plan gives no credit.

Copilot-mode intake maps job-led transitive object lineage first. Missing,
ambiguous, dynamic or unsupported bindings stop at `WAITING_DISCOVERY`, before
conversion or SME questions. The retained export is indexed in full; unrelated
members remain explicitly outside the selected closure. Configured typed Zowe
and Db2 reads resolve local misses; fetched source is frozen through a
ledger-pinned recovery journal before conversion. Closure COMPLETE describes
the bounded static graph, not all runtime paths or the entire estate.
`WAITING_COPILOT` exposes content-addressed frozen analysis/task evidence.
Copilot can implement/test adapters then call `workbench_refresh_analysis`
before the one SME packet; prior evidence remains preserved. Only the current
hash-matching return is accepted. The service never invokes Copilot Chat itself
or fabricates a model result. Deterministic/historical mode preserves earlier
contracts; the new UI/Start prompt selects Copilot mode.

Read-only Zowe/Db2 discovery does not require prelisting schemas or tables.
No source-system writes, mainframe execution or synthetic uploads are permitted.
Do not use an agent's answer as SME approval. Source-derived comparisons are
not observed mainframe results. No claim of perfect software is supported.

## Guided setup and credentials

The UI asks six questions: where the export is, whether the manifest is ready,
whether Zowe and Db2 are needed/configured, whether Copilot Chat is
wanted, and whether a reviewer is available. Answers are saved locally as typed
choices. The guide performs zero network/model calls. Configuration, successful
connection, supported conversion and verified business acceptance are separate.

## What you provide once

| Input | Put it here / action | Why it is needed |
|---|---|---|
| Workstation | CPython 3.12, local writable disk, setup script; use the committed UI bundle | Installs locked dependencies and avoids a Node requirement for operators. Native Windows execution still needs a workstation smoke test. |
| Application export | `WORKSPACE/Endeavor/` | Complete, readable UTF-8 source export with original relative member names. Include called programs, COPY dependencies, JCL, PROCs, INCLUDEs, control cards, BMS and SQL/DDL where applicable. A manifest alone cannot replace missing source. |
| Initial process | Markdown following `examples/process-input.md`, or the UI Excel template | Ordered jobs, steps, program/utility names, input/output groups and conditions. A new source version uses a new process ID. |
| Custom knowledge | `WORKSPACE/knowledge/application-knowledge.json`; start with `examples/application-knowledge.json` | Application/vendor utilities, aliases, semantics, evidence, record layouts, control-card behavior and known dependencies. The standard catalog is visible in `knowledge/mainframe-catalog.json`. |
| Background articles | `WORKSPACE/knowledge/inbox/context.md`, up to 16 KB | Devin/application notes. Treated as unverified evidence, never executable instructions or approval. |
| Zowe, when used | Authenticated CLI profile; `WB_ZOWE_PROFILE` | Account-visible read-only catalog/source operations. Profile presence is not successful authentication or complete discovery. |
| Db2, when used | Authenticated typed MCP URL/token; IBM ODBC driver and `pyodbc` for the bundled gateway | Schema/table descriptions without a prior schema allowlist. Discovery and sample access are distinct; no arbitrary SQL or automatic row sampling. |
| Copilot Chat | Normal VS Code Copilot access; copy `examples/mcp.json` to `.vscode/mcp.json`; running local UI | Frozen-task/source tools and structured analysis return. No LLM endpoint/token; normal host trust/tool consent applies. Tokens/billing Unknown without a receipt. |
| Actual SME return | One issued checklist, completed by the real reviewer; import once with attribution | Confirms or corrects interpretations. Unanswered/No/corrected items remain unresolved; no second questionnaire is generated. |

Private environment variables are set in your shell before launch. `.env.example`
is an example, not an auto-loaded credential file. Do not paste credentials into
source, knowledge, intake or review files. Stop the running UI before starting a
CLI Coordinator against the same workspace.

### Connection configuration

Set private variables in the launch shell. `.env.example` is not auto-loaded.
The UI never asks you to paste credentials into a form or source file.

| Connection | Variables / prerequisite | Actual implemented behavior |
|---|---|---|
| Zowe | `WB_ZOWE_PROFILE`, optional paired `WB_ZOWE_ZOSMF_PROFILE`; actual service access | `tools/setup_zowe.py --interactive` prepares secure declarations; exact config/schema import is supported. Typed bounded lists/reads resolve missing sources. TPX aliases cannot substitute for z/OSMF/API host/profile mappings. |
| Db2 MCP | `WB_DB2_MCP_URL`, `WB_DB2_MCP_TOKEN` | Schema/table/describe tools plus bounded sampling and explicit `db2_read_table_rows`. Supported revisions 2025-06-18 / 2025-03-26. Every account-visible schema/table is eligible; no allowlist or caller-supplied SQL. Automatic lineage does not export business rows. |
| Local Db2 gateway | IBM ODBC/pyodbc; `WB_DB2_CONFIG`; private `WB_DB2_USER`/`WB_DB2_PASSWORD` | `tools/setup_db2.py` prepares server/location/database/host/port, SSL true, fixed `certificates/DB2-CA.cert` and max_rows up to 500,000. Replace the invalid placeholder. Explicit row exports default to 1,000, pages at most 1,000, short-lived cursors and byte/time limits. Reaching a cap is PARTIAL. Legacy external `WB_DB2_ODBC_CONNECTION` retains externally managed TLS responsibility. |
| Copilot Chat | Workspace stdio MCP configuration from `examples/mcp.json` and existing local UI origin | Uses normal workspace chat/agent tools. Bridge never creates a second Coordinator, runs arbitrary shell or asks for a model endpoint. Legacy explicit opt-in provider remains available, with its own endpoint/source-egress configuration. |

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
WEDELX receives available files from Tran Repository/source systems; configure
exact local/mounted folder bindings in `knowledge/input-locations.json` using
`examples/input-locations.json`. Only an observed exact file binding resolves
availability. Layout, cutoff/completeness and business readiness remain unknown.
New configuration uses `WEDELX`; `WEDLX` remains an accepted legacy alias.
Both spellings resolve to one lineage node. Do not configure both as separate
locations. Historical frozen manifests, packets and receipts retain their bytes.

### Runtime and recovery

Use CPython 3.12 and the SHA256-locked wheels. `scripts/Setup.ps1` and
`scripts/setup.sh` stop on install/preflight failure. Operators use the committed
React bundle; Node 22+ is needed only to develop the UI. Keep the workspace on
local disk, back up the whole workspace, and run one Coordinator at a time.
Stop the UI before using the CLI on the same workspace. Never delete a lock or
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
New SME v3 packets compact technical blockers across programs by construct
family, even for small inventories. The 19-family `CONSTRUCT_ASSUMPTIONS` catalog
in `workbench/review.py` covers loops, SQL, CICS, file/VSAM I/O, sort/merge,
arithmetic, decisions, assignments, calls, control flow, layouts, text, tables,
JCL execution/data, scheduling, MQ, unclassified source and missing evidence.
Classification uses source tokens outside comments/literals and exact physical
references. Multiple operations on one physical line retain each detected
family. Multiline SQL/CICS bodies stay with their enclosing construct; SQL line
and block comments and continued quoted literals cannot open or close a block.
Each family lists its own object references and spans. These lexical labels help
the reviewer navigate evidence; they do not enumerate or prove all semantics.
Whole-file gaps without precise references remain unclassified unless an
evidenced source type identifies the family. Recognition is not conversion.
Each question starts `ASSUMPTION - family`, lists whole program names with a
bounded `+N more` summary, and explicitly describes an unverified obligation.
Context retains every object, source span, blocker index and digest against the
frozen complete source analysis. A blocker containing several constructs appears
in each relevant family; unique totals come from `source_analysis`, not the sum
of group memberships. Confirming the statement never clears its adapter gap.
Business rules and other human questions remain individual. At most 2,000
mandatory review items; no silent truncation. Historical v1 and v2 packets replay
unchanged, including the old v2 program/type compaction and original hashes.
Copilot-mode fixtures default to 4,096 cases/program, support budgets to 10,000,
and require 10 distinct source-predicate input states per supported logic item
(configurable 10–20). Legacy fixtures retain 256. There are 192 atomic condition
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
| Jobs | Named method per job, ordered steps and RC comparisons; actual record-adapter job comparison | Same field-name sets required between programs. One integration baseline, not exhaustive path testing. DSN reads/writes, external scheduler, procedure expansion and restart semantics require adapters. |
| Copilot | Frozen tasks, bounded source excerpts, MCP return and adapter reassessment before SME issue | IDE host initiates model work. Returned plans/context cannot clear semantic blockers; actual adapters and tests are required. |
| Synthetic data | Source-derived boundaries, invalid layouts, sequential effects, distinct logic states and linked-group match/mismatch witnesses | New contracts require 10–20 distinct valid states per supported logic item, with explicit budget/domain/reachability gaps. Native missing/duplicate/empty file/table behavior needs its own adapter. No exhaustive or observed legacy claim. |
| Oracle | Independent source IR interpreter freezes expected results before generated Python execution | Both depend on the parser; parser errors remain a shared risk. No observed mainframe oracle or mainframe execution. |
| Verification | Full output/trace/RC comparisons, independent source-order job interpretation, per-rule decision/boundary/effect mutation, denied capability checks; new target contracts include directly tested input guards | Historical targets used the separate JSON adapter. No native mainframe malformed-record semantics are claimed. Unit suite and mutation checks do not substitute for actual legacy execution evidence. |
| SME | One frozen packet / one valid return per process, immutable question identity/Context/Metadata, Yes/No/Not sure, corrections retained | Corrections requiring new semantics remain blockers. A Yes on an unsupported-item description does not make its conversion supported. |
| Knowledge | Standard mainframe catalog, editable application/vendor JSON catalog, content-based classification, per-process immutable snapshot, one background Markdown and confirmed-fact JSON/index pair | Recognition never grants conversion support. No semantic cross-process auto-approval or autonomous interpretation of corrected prose. |
| Connectors | Local-first typed transitive discovery, Zowe source/metadata reads, Db2 catalog lookup and explicit row exports | Account/service visibility and parser limits remain explicit. No schema allowlist; missing libraries/dynamic bindings/TPX-only facilities need exports or actual service mappings. |
| UI | Local React intake/prompt/file workflow, real stage events, rule lineage, source coverage filters, review import, Pause/Resume/Cancel and downloads | No target business CICS screen modernization in this subset. Workbench screens and control APIs are not counted as business replacements. |
| Reporting | One primary executive HTML report, six editable PPT slides, metric XLSX/CSV/JSON/history, complete source coverage JSON/CSV/XLSX/HTML, unique/membership counts, LOC and blockers | CICS/VSAM/interfaces unknown until evidenced. Db2 metric is distinct references in supplied SQL, not a confirmed estate table count. Physical/code LOC convention differs by source kind and is not equivalent complexity. |
| Inspection | PPT reopened, editable table count and canvas bounds checked, hashes recorded | Six sample slides rendered and visually inspected through Artifact Tool. Native PowerPoint/LibreOffice, browser rendering and Windows launch remain unverified. |

## Metric rules

Source assets deduplicate by kind, name and SHA256. Process memberships count references separately. Production portfolio totals exclude processes created with the UI demo flag. Revisions with changed hashes count as distinct versions, not necessarily distinct logical programs; titles use **versions** accordingly. Snapshot history in SQLite is retained, and the report workbook includes previous non-demo snapshots. Report metrics project the eligible current process outcome; inspected artifacts, accepted snapshot, terminal state and completion event are committed together. Failed, cancelled and blocked work receives no completion credit.

A known rule is credited only when its SME answer is Yes, its whole supported program has no source blockers or output differences, and both decision outcomes have witnesses. `known_rule_verification_percent` divides those rules by all **extracted known rules**. It is never called total modernization percentage. Unsupported lines, unknown rules, uncertainty, omitted behavior and coverage gaps are shown separately and prevent `COMPLETED`. Non-executable and explicit out-of-scope lines are separated from applicable lines. Every supplied file/line retains its disposition/reason. Mainframe-specific credit requires a concrete verified replacement; native DD/dataset/scheduler behavior is not inferred away.

`COMPLETED` means the stated source-derived target profile finished its tests and report gates without recorded blockers. It does not prove all possible legacy inputs equivalent. `COMPLETED_WITH_BLOCKERS` records finished reporting with unresolved work. Waiting for discovery/Copilot are prerequisites, not conversion status. Report failure leaves `REPORTING_FAILED`; Resume preserves the SME quota.

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

The UI/CLI use one Coordinator with durable controls, at most three transient stage attempts, one review quota, replay-safe artifacts and atomic final report acceptance. `prompts/START_MODERNIZATION.md` is the execution prompt for Copilot/Claude. this reference and core placement guards enforce seven process folders, content-addressed shared targets and one structured knowledge index. Watch requires actual reviewer attribution and has a bounded timeout; it never fabricates an answer.

## Folder ownership

| Location | Contents and ownership |
|---|---|
| `Endeavor/` | Selected read-only local mainframe text export. Never execute or overwrite it. |
| `process-input.md`, `intake-template.xlsx` | Optional root intake inputs. `--manifest` may explicitly select a Markdown manifest elsewhere. |
| `logs/`, `plugins/`, `settings/`, `.events/`, `.gradle/`, `extenders.json` | Private existing workstation content is accepted by layout, ignored for publication and left untouched. Layout acceptance does not load plugins or execute configuration. |
| `.npmrc`, `pip.conf`, `pip.ini`, `NuGet.Config`, `tools/dq3g_mcp/.env` | Local package/server configuration may contain credentials; ignored for git, never gathered as modernization source. |
| `processes/PROCESS_ID/input/process-input.md` | Immutable manifest snapshot; supplied and snapshot bytes must match the ledger's creation-time manifest SHA-256. |
| `processes/PROCESS_ID/input/sources/` | Immutable source snapshot with recorded file hashes. Preserve original relative names. |
| `processes/PROCESS_ID/input/sme-return-inbox.xlsx` | The single designated automatic return inbox. Requires explicit actual `--reviewer` attribution. |
| `processes/PROCESS_ID/input/sme-return.xlsx` | Service-preserved accepted return. Never place a workbook here manually. |
| `processes/PROCESS_ID/analysis/` | Structured analysis and source accounting, including reasons for unknown/unsupported/omitted lines. |
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
| `workbench/`, `frontend/`, `tests/`, `tools/`, `scripts/`, `docs/`, `prompts/`, `examples/`, `.github/` | Repository implementation, verification, entrypoints, instructions, synthetic examples and GitHub/Copilot metadata. |

Process IDs are stable, validated identifiers beginning with a letter. Process
roots may contain only `input`, `analysis`, `review`, `synthetic`, `target`,
`reports`, `tests`. Root-level process files, miscellaneous process folders,
path traversal and symlinks are refused. Generated Python/database artifacts
belong in `target` or `tests`, not analysis/review/input. Input allows only the
manifest, source snapshot and two designated return paths. Use structured
coverage records; never create a Markdown file per rule or per source line.
The only process Markdown is the input manifest or an original source-export
Markdown file preserved under `input/sources`.


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
| Too few or unrealistic synthetic records | Source-derived mandatory branches/boundaries/matches, deterministic interactions and witness counts | Record missing obligations explicitly. Four sample rows cannot certify 85 rules. Copilot mode uses a 4,096-case budget and requires 10–20 distinct valid states per supported logic; unreachable or unsupported obligations stay gaps. A budget is not exhaustive coverage. |
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

One primary next action; a five-stage progress guide; six setup questions;
plain-language statuses; evidence behind disclosure controls; one executive
report link. Workbench actions are not fabricated modernization progress.
Use semantic controls, persistent labels, keyboard focus, status/alert regions,
text alongside colors, reduced-motion support and responsive layouts. Test
small viewports, zoom, keyboard and screen-reader behavior on the actual browser.

Public Wells Fargo homepage CSS supplies red `#d71e28`, yellow `#ffcd41`, charcoal
`#3b3331` and neutral `#f4f0ed`. Use system fonts, not unlicensed brand fonts or
invented corporate marks. This is public-style alignment; internal Wells Fargo
design-system approval is not available. WCAG 2.2 AA is the accessibility target,
not a claim that automated checks constitute certification. The cloud browser
could not reach this release's local preview, so full visual/manual accessibility
verification is pending. Native Windows, native PowerPoint and live source
connections also require the target-workstation acceptance check.

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
PYTHONPATH=. python tools/review500.py
PYTHONPATH=. python tools/review_expanded.py
PYTHONPATH=. python tools/scenario_campaign.py --seed 20261003 --total-scenarios 600000
python -m workbench.layout --workspace .
python tools/check_handoff.py
```

Install frontend development dependencies with `npm ci` in `frontend/`, then
`npm run typecheck`, `npm run build`; from the repository root run
`node frontend/test-ui.mjs` for the component/behavior checks. Engineering tests use fictional fixtures only and clear
all source/provider environment settings. The real HTTP tests bind loopback.
The 1,000 named checks comprise R001–R500 and 500 new R501–R1000 checks. They are
not 1,000 independent reviewers. The generated campaign explicitly selects 600,000 unique
program/input scenarios (200 programs × 3,000 records); the historical default
200,000 recipe remains reproducible. It compares executed Python and reference
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
