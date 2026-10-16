# Mainframe discovery and validation preparation

Use this reference only when the task needs discovery, legacy evidence or a run
packet. It grants no permissions. Read `config/project.json` and
`config/source-reference.json`; retain every existing deny. Do not use Bash,
PowerShell, scripts, MCP or copied paths to bypass them. Source/PII remains private;
only approved sanitized views and synthetic examples may enter model context.

## Read-only discovery and OKF fallback

Start with the checked [Endevor navigation](../../../../docs/ENDEVOR_NAVIGATION.md)
snapshot and the exact qualified source/object identity. A missing or stale index
is not a remote absence: reconcile approved local files and rebuild/check first
when the generated state is intact. If the question remains unanswered, missing
sources, unresolved/dynamic references, SQL dependencies or a fresh graph with no
relevant edges trigger the appropriate bounded discovery below. Do not query
remotely for every already-understood leaf. The lead owns reconciliation; gap analysis/DevOps use
existing tools, not a new resolver service.

The user screenshot visually confirms `TSTSN.#RW477*`, including the highlighted
`TSTSN.#RW477.P.ELE01.JCL.D260923`. It shows Row 39 of 75, not a complete catalog.
Do not treat the date suffix as the only valid version, infer program identity
from a library name, or infer a z/OSMF endpoint from the terminal URL.

Before Zowe dataset reads, require the environment owner's confirmed read profile,
`capabilities.mainframe_read`, an explicit approved command binding and applicable
host permission. Shipped null bindings/false capability and dontAsk policy do not
permit Zowe dataset discovery. Report that gap; do not alter settings to escape it.
For Db2 MCP metadata discovery, use the independently verified exact MCP tool,
approved resource binding and `capabilities.db2_metadata_read`, with role, host
and database-account permission. The Zowe dataset gate does not apply to that
MCP-only operation. Follow technical-reference Sections 4.1–4.3 for its readiness
receipt. Do not infer synthetic row-read or test-write authority from metadata access.
Once independently verified, reuse each binding within its recorded scope without
repeated confirmation. Neither connector may bypass a denial on the same object or
action. One route's unavailability need not block unrelated permitted metadata work.

At authoring on 16 October 2026, this workspace exposes no Db2 MCP tool and no
`zowe` executable; the user reports both configured on their workstation. No live
lookup was performed. Resolve actual server/tool schemas and CLI version there;
never invent an MCP tool name or treat these templates as a successful lookup.

The official Zowe command forms below are **templates, not executed commands**.
Confirm them against the installed version and replace every placeholder before
adding exact commands to the reviewed binding. Quote names containing `#` or `*`.
Use profile-managed secrets; never embed passwords/tokens or disable TLS checks.

```bash
zowe zos-files list data-set 'TSTSN.#RW477*' --attributes --zosmf-profile '<READ_PROFILE>'
zowe zos-files list all-members '<VERIFIED_PARTITIONED_DATASET>' --pattern '<EXACT_MEMBER>' --attributes --zosmf-profile '<READ_PROFILE>'
```

Try a known exact dataset before the prefix; search evidenced library concatenations
in their actual order. Broaden a missing member to an approved member pattern only
within the remaining request/row/byte/time budget. For full inventory, enumerate
every applicable library/member in resumable batches, including unreachable programs,
sequential datasets and unknown types. Outside-prefix dependencies require an
already approved location, not an automatic global search.

Record each page and continuation boundary. Official dataset listing supports
`--start` as the first name to return; do not assume an exclusive cursor. Current
stable member help documents `--pattern` and `--max-length`, not `--start`; use
continuation only if the installed help and binding support it. Otherwise use
complete bounded patterns or retain `partial`. `--max-length` caps results, and
omitting it requests all items; neither is evidence that a service/transport result
was complete. Inspect supported completion metadata, deduplicate page boundaries,
and stop non-progress. Unknown truncation, changed catalog versions or exhausted
budgets remain explicit gaps. Never declare a complete inventory from a first page.

For database discovery, verify Db2 for z/OS versus LUW and server release first.
Use the existing MCP server's advertised metadata operation where available; if it
offers an approved read-only SQL operation, bind values through its actual schema.
The following are **z/OS catalog query shapes**, not invented MCP calls or proof of
access. Restrict predicates to the approved identity, use explicit columns and the
verified tool's paging/timeout limits; do not concatenate untrusted identifiers.

| Need | Catalog and narrow projection | Exact predicates / resolution |
|---|---|---|
| Table, view or alias | `SYSIBM.SYSTABLES`: `CREATOR, NAME, TYPE, LOCATION, TBCREATOR, TBNAME` | `CREATOR = ? AND NAME = ?`; for aliases, retain location and target identity rather than assuming a local table. |
| Column contract | `SYSIBM.SYSCOLUMNS`: `TBCREATOR, TBNAME, NAME, COLNO, COLTYPE, LENGTH, SCALE, NULLS` | `TBCREATOR = ? AND TBNAME = ?`, ordered by `COLNO`; request further required constraints/CCSID/default metadata separately. |
| Bound package identity | `SYSIBM.SYSPACKAGE`: `COLLID, NAME, VERSION, HEX(CONTOKEN)` | `COLLID = ? AND NAME = ?`, narrowed by evidenced version/token; preserve multiple candidates. |
| Package-to-object or object-to-package links | `SYSIBM.SYSPACKDEP`: `DCOLLID, DNAME, HEX(DCONTOKEN), DTYPE, COPYID, BQUALIFIER, BNAME, BTYPE` | Package: `DCOLLID = ? AND DNAME = ?`; reverse: `BQUALIFIER = ? AND BNAME = ?`. Reconcile token/copy/type before asserting the active binding. |

If qualification is unknown, consult approved DCLGEN/bind/JCL context first, then
search only the authorized schema/collection set; do not assume an uppercase default
or wildcard every schema. Metadata visibility does not grant data-read permission.
Package dependencies may include objects unused by the selected access path and
do not prove executed SQL, complete dynamic dependencies or source/load equivalence.
Missing catalog support remains a gap; do not execute routines, EXPLAIN writes,
DDL, business-row reads or jobs to obtain metadata.

For every lookup, save a protected receipt in the existing program analysis area
and link it from the handoff/catalog: qualified request and reason; source snapshot;
tool/server version and approved binding; account/profile reference without secrets;
exact query/command and safe parameters; authorized scope; start/end UTC; pages,
bounds and completion flags; response/exit or SQL status; immutable result path and
hash; unresolved identities and next action. Redact before model ingestion; preserve
the exact permitted request/result in its protected store when a summary must omit
details. A hash alone does not establish completeness or permission.

Use `found`, `not_found_in_scope`, `partial`, `denied`, `unavailable` or `error` for
lookup outcomes, alongside the original OKF reason. Only a successful, complete
search earns `not_found_in_scope`; denial, timeout and zero visible rows with unknown
paging do not. Resume from the receipt within the original budget, not from zero.

For approved acquisition into a protected new local snapshot, the official form is:

```bash
zowe zos-files download data-set '<VERIFIED_DATASET(MEMBER)>' --binary --file '<NEW_PROTECTED_SNAPSHOT_FILE>' --zosmf-profile '<READ_PROFILE>'
```

Select transfer mode from the actual contract: binary preserves untranslated
content; record mode preserves record lengths; encoding mode converts text.
Record RECFM/LRECL/CCSID and raw/decoded hashes. Do not decode mixed packed/binary
records as plain text, overwrite a historical snapshot, or print protected file
contents. An approved deterministic local process may prepare a reviewed sanitized
view with original-span mapping. Db2 metadata/row extraction requires its separately
approved tool/resource path and corresponding capability; file access does not
establish Db2 access. Reuse the existing Db2 MCP server where bound. A Zowe Db2
profile is needed only for an explicitly selected Zowe Db2 route, not for MCP.

After approved acquisition, reconcile identity/version, source-span mapping and
hashes into canonical source maps and `knowledge/mainframe-catalog.json`. Add only
approved sanitized source views to `Endevor/` and its explicit navigation manifest;
the lead rebuilds/checks OKF and invalidates affected analysis before reuse. Keep
Db2 metadata receipts in canonical analysis, not fabricated COBOL source concepts.
Preserve historical evidence, ambiguous matches and unresolved dynamic references.
Only business meaning or intended changes go to SMEs; technical access gaps go to
the environment owner once, while independent work continues.

## Reviewable validation packet

Create `programs/<id>/runs/<run-id>/mainframe/packet.json` and `commands.md`.
When an actual reviewed JCL adaptation exists, include `jcl-diff.patch`; do not
invent a diff or resource to fill a template. Record unresolved fields explicitly.

1. Identify legacy executable/source correspondence, JCL/PROC expansion, symbols,
   DD concatenations, parameters, tables/files and external effects.
2. Obtain designated test datasets/schemas, allocation/encoding contracts, reset
   procedure and test endpoints from the environment owner. Do not guess them.
3. Propose a copied test JCL with only reviewed environment-binding changes.
   Preserve original code and business logic; resolve generation references,
   dispositions, return-code conditions, restart and downstream triggers.
4. Serialize the same logical synthetic inputs/reference data used locally. Pin
   logical and byte hashes, initial database state and expected outputs/effects.
5. List exact supplied commands, prerequisites, resources read/written, capture,
   limits, cleanup/recovery and environment-owner review/notification requirements. Bind review
   to the finalized pre-run packet hash in a separate approval receipt; keep the
   packet immutable and retain source/decision versions and permitted repeat limits.
6. Keep execution blocked while write/submission denies apply. A config flag,
   approval comment or executable script does not override host/account policy.
   Return the specific policy/resource gap for the authorized owner to resolve.
7. For any subsequently permitted operator run, retain job ID/status and receipts,
   business output files and Db2 effects separately from spool. Reconcile unknown
   submission status before retrying; never infer that a timeout means no job ran.
   Write post-run receipts separately, linked to the approved packet hash; do not
   require future job IDs/output evidence as pre-run fields or mutate the packet.

Speed comes from matching baseline reuse, coherent prebuilt fixtures, batched
compatible cases, isolated test resources and targeted reruns. Never modify the
original program or comparison tolerance merely to make validation pass.

## Commands for a subsequently permitted test run

These templates belong in the packet; they have not been executed and cannot run
under the current upload/submission denials. The environment owner supplies actual
test resources and permitted bindings. Do not issue them with placeholders.

Upload a text fixture to an **existing** isolated test dataset/member:

```bash
zowe zos-files upload file-to-data-set '<LOCAL_FIXTURE_FILE>' '<TEST_DATASET_OR_MEMBER>' --encoding '<APPROVED_DATASET_ENCODING>' --zosmf-profile '<TEST_PROFILE>'
```

Confirm allocation, RECFM and LRECL separately. For a prepared binary/mixed packed
payload, use `--binary` instead of `--encoding`; use `--record` only for a compatible
record-mode payload. These are alternative transfer contracts.

Submit the reviewed cloned test JCL and retain its response/job ID:

```bash
zowe zos-jobs submit local-file '<APPROVED_TEST_JCL_FILE>' --job-encoding '<APPROVED_JCL_CODEPAGE>' --job-record-length <JCL_LRECL> --job-record-format <F_OR_V> --zosmf-profile '<TEST_PROFILE>'
```

The JCL record options describe submission, not business input allocation. Check
the returned job rather than submitting again when its state is uncertain:

```bash
zowe zos-jobs view job-status-by-jobid '<RETURNED_JOB_ID>' --zosmf-profile '<TEST_PROFILE>'
```

After completion, retain spool evidence:

```bash
zowe zos-jobs download output '<RETURNED_JOB_ID>' --directory '<RUN_EVIDENCE_DIRECTORY>' --encoding '<APPROVED_SPOOL_ENCODING>' --zosmf-profile '<TEST_PROFILE>'
```

Spool is not the complete business output. Capture output datasets and Db2 effects
through their separately verified bindings, then run the specified comparisons.
Job completion and a successful return code do not establish business equivalence.

Official command references checked 15 October 2026:
- [Dataset listing](https://docs.zowe.org/stable/web_help/docs/zowe_zos-files_list_data-set)
- [Member listing](https://docs.zowe.org/stable/web_help/docs/zowe_zos-files_list_all-members)
- [Dataset download and transfer modes](https://docs.zowe.org/stable/web_help/docs/zowe_zos-files_download_data-set)
- [Fixture upload](https://docs.zowe.org/stable/web_help/docs/zowe_zos-files_upload_file-to-data-set.html)
- [JCL submission](https://docs.zowe.org/stable/web_help/docs/zowe_zos-jobs_submit_local-file)
- [Job status](https://docs.zowe.org/stable/web_help/docs/zowe_zos-jobs_view_job-status-by-jobid)
- [Spool download](https://docs.zowe.org/stable/web_help/docs/zowe_zos-jobs_download_output.html)

Fallback references checked 16 October 2026 (match the installed versions before use):
- [Zowe dataset listing and start/limit semantics](https://docs.zowe.org/stable/web_help/docs/zowe_zos-files_list_data-set)
- [Zowe member patterns and limits](https://docs.zowe.org/stable/web_help/docs/zowe_zos-files_list_all-members)
- [Db2 13 z/OS SYSTABLES](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=spaces-systables) and [alias metadata](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=design-retrieving-catalog-information-about-aliases)
- [Db2 13 z/OS SYSCOLUMNS](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-syscolumns)
- [Db2 13 z/OS SYSPACKAGE](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=spaces-syspackage) and [SYSPACKDEP](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-syspackdep)
