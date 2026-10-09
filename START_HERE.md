# Mainframe Modernization Workbench

Use **Windows 11** and Claude Code. The factory keeps each process in its own
folder and preserves the mainframe’s evidenced behavior. Python/SQLite is the
implemented non-production target; unsupported behavior stays a specific gap.

## Four phases

1. **Prepare once.** In the installed repository, run the foreground setup below.
   It creates `Process.md`, `Endeavor/`, `certificates/` and empty supplemental
   folders. Fill one private `.env` locally and place your approved CA files.
   Claude asks once for missing nonsecret connection facts. Credentials stay local.
2. **Provide your process.** Fill `Process.md` with its stable ID, name, job names
   in run order and what you know in your own words. Put the complete export in
   `Endeavor/`. Click **New process → Download Process.md template** if needed,
   select your completed file, then click **Map this process**. No separate
   manifest, notes file or source-mode choice is required.
3. **Choose rules and build.** Follow **Source & mapping**, **Choose rules**,
   **Build & test**, then **Review & compare**. Local Endeavor is always checked
   first. The configured read-only Zowe resolver maps known missing source
   references. Remaining or Db2 evidence uses the current Claude retrieval prompt
   and approved Db2 MCP. Clear unwanted checkboxes and click **Save
   requirements and continue**. Claude develops/tests using approved safe evidence.
   Deliver the one issued file to the actual SME and import their saved return.
4. **Compare.** Select a program, click **Gaps only**, then expand its source unit.
   The comparison shows legacy logic, Python/database replacement, satisfaction,
   tests and exact unresolved needs. Selected No says why it was not converted.
   Open the accepted executive report and management deck when reporting finishes.

Use the stage buttons and **Back** to revisit details; **Return to current stage**
returns to the eligible action. This navigation never rewrites frozen input or
resets approval. **Refresh checkpoint** reads current progress. A failed input or
action shows its error beside that step. If the workspace connection is lost,
click **Reconnect to this workspace**; saved details remain visible and mutations
wait for the current read.

Paste this initial prompt into the approved Claude Code host from the repository:

```text
Start. Follow prompts/START_MODERNIZATION.md. Use this repository as the workspace
and prepare its Process.md template, Endeavor folder and certificates folder.
Walk me through the shared .env once; ask missing nonsecret connection facts
together and keep credentials local. Use Process.md to map the jobs from Endeavor
first, retrieve only missing mainframe evidence with read-only Zowe CLI and Db2
MCP, then guide me through saved rule choices, build/tests, the single human review
and the source-versus-target comparison. Ask only for unresolved facts.
```

## Prepare the fixed folders

Open PowerShell in the installed repository. Run each command in the foreground
and wait for its result before the next command:

```powershell
.\scripts\Setup.ps1
.\.venv\Scripts\python.exe -m workbench.workspace_inputs --workspace .
.\.venv\Scripts\python.exe -m workbench.preflight --workspace . --initialize-knowledge
```

The helper preserves existing files and never opens exports or credentials:

```text
WORKSPACE/                     repository by default
  Process.md                   fill-in template; one file per current intake
  .env                         private shared Db2/Zowe values
  certificates/
    DB2-CA.cert                 approved Db2 CA (PEM or DER)
    ZOWE-CA.pem                 approved Zowe PEM CA
  Endeavor/                    put the complete unchanged text export here
  supplemental/                leave empty until an exact missing-object request
    JCL/
    JCLPlus/
    PROCConverted/
    Copybooks/
    ControlCards/
  processes/PROCESS_ID/        Coordinator-owned immutable process evidence
```

Copy [.env.example](.env.example) to `.env` only if that private file is absent.
Fill credentials in an approved local editor; never paste or screenshot the file.
Open `Process.md` in Notepad, replace its two identity values and job placeholder,
write any known process details, and **File → Save** using UTF-8. `Unknown` is
accepted for background knowledge; entry identities must be real. For online-only
CICS intake, use the actual transaction/program table in the template’s comment.
One known job is enough to start discovery; its steps/programs come from source.
Use [the template](examples/process-specific.md) or the UI download, whichever is
convenient. Both are the same maintained template.

Mapping uses the existing lazy read-only resolver for known exact missing
mainframe references when configured. A complete local closure never opens the
private connection file. If dependencies remain missing, use the current Claude
retrieval prompt; Db2 metadata always uses approved typed MCP and its exact inbox.
There is no Zowe MCP or workflow proxy.

Leave supplemental folders empty initially. If approved retrieval still cannot
find an object, Claude names the exact missing object and destination; then place
only the requested approved export in its named supplemental folder and click
**Continue**. This fallback requires an accepted read-only Zowe `NOT_FOUND` for
that exact member; the original receipt stays in evidence. Supplemental folders
are not scanned as default inputs. Db2 evidence still requires approved Db2 MCP;
ambiguous or dynamic objects are not resolved by guessing.

<details>
<summary>Connection setup: exact fields and commands</summary>

### Required connection facts

Use **Windows 11**, CPython **3.12** and writable local NTFS folders. Before
starting native clients, Claude asks for this one bundle of
approved **nonsecret** facts. Leave an unknown value `Unknown`; do not guess.
Passwords, usernames used as credentials, tokens and private `.env` contents
are entered locally, never returned in chat.

| Needed fact | What to supply safely |
| --- | --- |
| Workspace | The installed repository is the default; give another path only when explicitly requested |
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

Prepare the fixed empty input folders and Process.md template. The installed repository is the default workspace:

```powershell
.\.venv\Scripts\python.exe -m workbench.workspace_inputs --workspace .
.\.venv\Scripts\python.exe -m workbench.preflight --workspace . --initialize-knowledge
```

Use this same workspace throughout. Place Process.md and your Endeavor export in its prepared folders; the Coordinator creates immutable per-process evidence separately.

### Shared `.env` and native clients

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
`WORKSPACE/Endeavor/`. Explicit alternate local-folder import remains an advanced option.
Do not invent an Endevor connection or treat TPX session names as API hosts.

From the repository, prepare a clean Zowe project config/schema programmatically:

```powershell
.\.venv\Scripts\python.exe tools\setup_zowe.py --workspace "." --from-env --env-file ".env"
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
actual workspace and run:

```powershell
$workspace = (Get-Location).Path
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
.\.venv\Scripts\python.exe -m workbench.db2_setup --workspace "." --env-file ".env"
.\scripts\Start-Claude.ps1 -Workspace "."
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

Open the Workbench with `.\scripts\Start.ps1` from the repository and keep its
terminal open. It uses the repository as workspace. `-NoBrowser` suppresses only
browser opening. For a deliberately different workspace use the documented
locked-Python `workbench.launch --root WORKSPACE` command. Keep one Coordinator.
Click **New process**; source-setting Save is not a prerequisite. Optional
**Setup** settings can retain exact WEBELX/Tran Repository bindings for missing
input data; they do not relocate the default Endeavor folder. Historical WEDLX
bindings remain compatible and frozen identities are not renamed.

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


</details>

<details>
<summary>Process input, large files and legacy compatibility</summary>

`Process.md` accepts the template’s labels, ordinary surrounding Markdown,
numbered job names and freeform knowledge. Markdown is limited to **1 MiB UTF-8**.
Indexed process context accepts at most 20 Markdown documents and 1 MiB
combined, counting Process.md knowledge and any optional notes.
The Coordinator preserves its original bytes and derives job/step/program bindings
from validated source. Unknown, ambiguous or dynamic bindings stop discovery;
operator prose cannot prove a source identity or authorize a conversion.
Existing structured batch/CICS Markdown and Excel intake remain supported under
**Other input options**. Separate process notes and alternate export paths are
advanced compatibility inputs; they are not required for the normal flow.

Local source intake supports up to **10,000 files**, **16 MiB per file**,
**512 MiB combined** and **2,000,000 physical lines**. There is no 800 KB source
ceiling. Use the local Endeavor folder for a large export; browser source upload
remains **32 MiB combined**. Limits are finite resource guards, not promises about
all file encodings, available memory or performance. Preserve UTF-8 text, record
endings, column positions and original relative names; binary/EBCDIC data needs
an approved adapter/export, not silent decoding.

New version-2 HTML SME packets support saved returns up to **128 MiB**. Existing
version-1 HTML packets keep their frozen **8 MiB** contract, and legacy XLSX
returns remain **8 MiB** with archive protections. A returned file never authorizes
a second packet or reviewer impersonation. UI import is convenient; the existing
attributed local runner/inbox route is available for a large supported HTML file.
Stop the existing UI Coordinator first with Ctrl+C before this direct CLI import:

```powershell
.\.venv\Scripts\python.exe -m workbench.runner import PROCESS_ID --workspace . --file RETURNED.html --reviewer "Actual reviewer"
```

Use only the real human’s saved file and attribution. The technical reference
owns the exact frozen-packet/size/identity validation contract. Do not edit issued
metadata or split one packet into competing returns.

</details>

## Results and safeguards

Each stable process ID owns `input`, `analysis`, `review`, `synthetic`, `target`,
`reports` and `tests`. The same folders are used every time. Saved scope and
process instructions have immutable hash-bound versions. Same-input retries reuse
the process; changed inputs need a new explicit ID. **Continue** validates the
current request inbox and resumes the existing Coordinator; it does not start a
second writer or repeat a denied/missing request blindly.

Source-derived tests compare actual target output with evidenced expectations.
Observed mainframe parity additionally needs matched inputs, environment, run,
keys and baseline scope. Historical database rows remain separate differences.
Credentials, original source/comments/control cards and customer records remain
protected locally. Models see approved sanitized semantic views, safe metadata and
synthetic data; missing safe context remains a qualification gap. Preserve legacy
behavior even when it appears wrong; a suspected source issue is evidence to
report, not permission to fix the business rule during migration.

For concise how-to answers use [OPERATOR_GUIDE.json](prompts/OPERATOR_GUIDE.json),
then only its relevant checked spans. For more detailed clicks open the [offline
illustrated job aid](examples/mainframe-modernization-job-aid.html). Its optional
46 atomic steps support the four-phase path. Figures 34–37 show actual current
local synthetic intake, source navigation, rules and build handoff; all 33 earlier
captures are marked historical. Illustrative capture paths are not operator
commands. No screenshot establishes Windows 11/live-connection acceptance.
The [technical reference](docs/TECHNICAL_REFERENCE.md) owns the full contract.
The [executive report](docs/executive-report.html) distinguishes validated progress,
exclusions and unresolved acceptance. Finite tests do not prove every scenario.
