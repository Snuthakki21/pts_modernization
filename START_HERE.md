# Mainframe Modernization Workbench

A local modernization workbench: provide a process, discover its object lineage,
use GitHub Copilot Chat, review one checklist, and receive one executive report.
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
Copilot Chat, and give it the shared Start prompt. Use standard VS Code workspace
chat; input prompts are not supported by every agent harness.
[Technical reference](docs/TECHNICAL_REFERENCE.md)
contains the exact connection prerequisites and recovery actions.

For Zowe, import your exact files with
`python tools/setup_zowe.py --workspace WORKSPACE --import-config CONFIG --import-schema SCHEMA`.
For guided profile preparation, use `python tools/setup_zowe.py --workspace WORKSPACE --interactive`.
It declares `user` and `password` as secure fields. Enter values only at the local
`zowe config secure` prompts. Use the returned base/service profile variables.
Profile configuration is distinct from verified connectivity.

For Db2, run `python tools/setup_db2.py --workspace WORKSPACE` and fill the
nonsecret settings in `.migration/db2-config.json`. Replace the generated
**`certificates/DB2-CA.cert`** with your approved certificate. SSL stays enabled;
the placeholder cannot authenticate. Supply credentials privately through
`WB_DB2_USER`/`WB_DB2_PASSWORD`; set `WB_DB2_CONFIG` to the config path before
starting `python tools/db2_mcp_server.py`. Configure the private gateway URL/token
for the workbench. Discovery uses all account-visible schemas without an
allowlist. Explicit exports default to 1,000 rows and permit up to 500,000.

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

Put background/Devin articles in **`knowledge/inbox/context.md`** (up to 16 KB).
Add custom utility facts to **`knowledge/application-knowledge.json`**, created
by setup. The **Knowledge** screen and [knowledge guide](knowledge/README.md)
explain file classification, utilities, required evidence and editable facts.

## 4. Click Start

The workbench retains the full export, maps the job's transitive objects, checks
local definitions, and tries configured typed Zowe/Db2 reads for missing objects.
**Waiting for discovery** stops before conversion or questions when identities
are missing/ambiguous. Correct the named configuration/evidence and retry.
**Waiting for Copilot** provides frozen source evidence and an analysis task.
Copilot reads evidence, implements/tests needed adapters, and returns structured
analysis through MCP. Plans cannot clear blockers. The coordinator then emits
supported targets and one SME checklist.
The screen shows the current stage and next action. Pause, Resume and Cancel
retain evidence. Mainframe connections remain read-only; no jobs or synthetic
records are run or uploaded there.

## 5. Return the one SME checklist

Download `sme-checklist.xlsx`. The actual reviewer selects **Yes**, **No** or
**Not sure**, adds corrections and returns it. Import the workbook with their
name. Agents must never fill these answers. The workbench automatically runs
source-derived synthetic tests, comparisons, adversarial checks and reporting.
Copilot-mode runs require **10 distinct valid source logic states per applicable
supported logic item** (the generator supports 10–20), plus boundaries, invalid
inputs and source-evidenced linked-record matches/mismatches. Unsupported,
unreachable, undersampled or failing obligations stay explicit gaps. Expectations
are frozen before Python execution; no synthetic records go to the mainframe.
Unresolved answers remain blockers; it does not issue another questionnaire.

## 6. Open the executive report

One primary report shows before/after counts, verified coverage, gaps and next
actions. The six-slide PowerPoint and detailed source/target/test evidence are
available when requested. **Completed with blockers** means unresolved work.
Passing local tests does not establish observed mainframe parity.

For the current software's results, open [executive-report.html](docs/executive-report.html).

## Use Copilot or Claude Code

Give the agent **[prompts/START_MODERNIZATION.md](prompts/START_MODERNIZATION.md)**,
your manifest path and workspace path, then say Start. Repository instructions
point to that one workflow. The agent uses the same engine as the UI and waits
for the actual human checklist return. Stop the UI before running the CLI on
the same workspace. Folder checks keep output under each process.

For a safe trial, use **Run fictional example** in the UI. Its results are
excluded from real portfolio totals. No real process has been converted in the
software validation supplied with this repository.
