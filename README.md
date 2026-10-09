# PTS Modernization Workbench

Modernize evidenced mainframe behavior with **Claude Code** and the existing local
Workbench. Windows 11 is the required workstation; Python and SQLite are the
implemented non-production target.

Start with [START_HERE.md](START_HERE.md) and its
[illustrated job aid](examples/mainframe-modernization-job-aid.html). Claude Code
uses [CLAUDE.md](CLAUDE.md) and the shared
[execution prompt](prompts/START_MODERNIZATION.md); the
[context index](prompts/CONTEXT.md) routes questions to the maintained contract.

1. **Prepare once:** one private `.env`, two approved CA files and the native
   Zowe/Db2 helpers. `python -m workbench.workspace_inputs --workspace .` creates
   the fixed input folders and preserves any existing files. The repository is
   the default workspace; no source-folder choice is needed.
2. **Provide Process.md and Endeavor:** fill the template in your own words,
   add job names and place the complete export in `Endeavor/`. Click **New process**,
   select your file and **Map this process**. Local evidence is checked first;
   the configured read-only Zowe resolver maps known missing references. Remaining
   source or Db2 needs use the current Claude retrieval prompt and approved typed
   Db2 MCP, preserving exact local inboxes.
3. **Choose rules and build:** save the checked Yes/No scope, then use Claude for
   safe analysis, code and tests. The actual SME completes the single issued
   review file. Setup Save, a separate notes file and eight-column manifests are
   not prerequisites for the normal flow.
4. **Compare:** open source-versus-target results by program, use **Gaps only**,
   inspect the exact replacement/evidence, and download the executive report/deck.

Stage buttons and **Back** revisit saved details without resetting the process.
New HTML review packets accept supported returns up to 128 MiB; frozen older
packets and XLSX retain their original limits. Large source exports use the local
folder rather than browser upload. Protected originals/customer data stay outside
model context; only approved sanitized views and safe metadata inform Claude.

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
