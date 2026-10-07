# Workbench retrieval instructions

Read [AGENTS.md](../AGENTS.md) and the retrieval role in the single shared
[prompts/START_MODERNIZATION.md](../prompts/START_MODERNIZATION.md). Claude Code's
[CLAUDE.md](../CLAUDE.md) references the same workflow.

**GitHub Copilot in VS Code retrieves files and metadata only.** Use the
organization's already approved MCP servers for read-only mainframe discovery,
source/member pulls and requested dependency or catalog metadata. The optional
[workbench configuration](../examples/mcp.json) selects `--role retrieval`;
retain the user's approved bindings and credentials. Do not add a server merely
to evade policy. Claude Code has no MCP access.

Follow the generated retrieval request exactly: preserve the process/request ID,
requested identities, environment and supplied WEDLX/Tran Repository bindings.
Write retrieved original files under the exact `inbox/files/` directory and the
bounded response manifest to `inbox/response.json`, as specified in the packet.
Keep original source identity in response `path`. If its extension is restricted
under analysis (such as `.md` or `.py`), stage UTF-8 text with a `.txt` filename
and set `staged_path`; hash the saved bytes and follow the packet schema. Do not
retrieve binary databases or execute returned files.
Record provenance, hashes and missing/ambiguous/denied/partial results honestly.
Finish files before writing the response manifest. Never overwrite frozen source
or prior accepted returns. I* and Z* names are evidence-dependent candidates,
not automatic substitutions; TPX aliases are not physical/API locations.

Stop after retrieval and tell the user to return to Claude Code and say Continue.
Do not analyze business logic, classify rules, implement code, integrate patches,
run conversion tests, perform review or submit final analysis. Claude performs
that work using the approved local files. Do not invoke Claude through Copilot.

Mainframe access remains read-only: never submit jobs, execute legacy programs,
write datasets/Db2 data or upload synthetic records. Preserve original export
bytes and supplied notes; do not fabricate a successful lookup. Missing evidence
remains a named prerequisite. Never fill SME answers or infer human approval.
Keep credentials and private exports out of repository commits and public reports.

The Python service is `workbench.coordinator.Coordinator`. Preserve its ledger,
one SME quota, immutable artifacts and single-writer lock. Follow
[docs/TECHNICAL_REFERENCE.md](../docs/TECHNICAL_REFERENCE.md) for folder placement;
use `.implementation/tmp/` for temporary repository scratch, not new root folders.
