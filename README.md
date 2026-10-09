# PTS Modernization Workbench

Modernize evidenced mainframe behavior with **Claude Code** and the existing local
Workbench. Windows 11 is the required workstation; Python and SQLite are the
implemented non-production target.

Start with [START_HERE.md](START_HERE.md) and its
[illustrated job aid](examples/mainframe-modernization-job-aid.html). Claude Code
uses [CLAUDE.md](CLAUDE.md) and the shared
[execution prompt](prompts/START_MODERNIZATION.md); the
[context index](prompts/CONTEXT.md) routes questions to the maintained contract.

1. Start in text: answer one bundle of approved nonsecret connection facts, fill
   one private workspace `.env` locally, place the approved CA files and run the
   Zowe/Db2 helpers. Claude owns local Db2 stdio; no MCP token is needed. Zowe
   Explorer still needs its secure-store login. Then save source defaults in the UI.
2. Add a process manifest and its separate process notes. Claude retrieves source
   through read-only Zowe CLI and Db2 evidence through the approved MCP connection.
3. Explicitly save the logic to convert. Claude builds and tests against validated
   local evidence; protected source and customer records stay outside model context.
4. Have the actual SME complete the single review packet, then import their return.
5. Open **Program comparison** for aggregate legacy/replacement totals. Select a
   program, use **Gaps only**, and open a logical unit to inspect original code,
   target code, satisfaction evidence and the exact missing verification.

The [local skill pack](.claude/skill-pack.json) supplies bounded coding, design,
context and review guidance from the requested projects. It installs no MCP,
proxy, hooks or background service. The existing approved Db2 connection remains
separate. Read only relevant skills; they cannot override source fidelity,
privacy, the Coordinator or human approval. Validate the pack with
`python tools/check_skill_pack.py` and the guide with `python tools/check_handoff.py`.

The [technical reference](docs/TECHNICAL_REFERENCE.md) owns the operating contract.
The [executive report](docs/executive-report.html) and
[engineering evidence](docs/evidence.json) distinguish source-derived verification,
observed parity, exclusions and unresolved gates. Future target adapters remain
explicitly unimplemented until qualified. Configuration is not connectivity;
finite tests do not prove every scenario. No credentials or real operational
source are included in this repository.
