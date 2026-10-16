# Token efficiency without losing evidence

The selected runtime is **Graphify 0.9.91 for local Python symbol lookup**. It is
installed in an isolated environment in the build workspace; its reproducible
dependency lock and a narrow adapter are included on this branch. It does not
replace Claude Code, run another model, install hooks, or change permissions.
Claude Code / VS Code activation on the user's workstation is not verified here.

The existing 15 optional instruction packages remain preserved. In particular,
the retained Headroom instructions are not the Headroom compression runtime.
Installing more packages does not itself save tokens. Use one applicable tool
at a time and measure complete tasks, including retries and review.

## Selection and actual evidence

Research used GitHub repository/file/commit lookup, Context7 and primary vendor
documentation on 2026-10-16. Exact revisions and licenses are in
[`config/token-tools.json`](../config/token-tools.json).

| Candidate | Decision | Reason and boundary |
|---|---|---|
| Graphify local Python parser | Installed locally; scoped adapter shipped | Parse approved converted Python without a model call; return a small source-linked symbol/call lookup. This adapter uses only per-file static extraction. |
| Claude native MCP tool search | Use existing host capability when supported | Defers tool definitions. Check the actual provider/enterprise setting; a proxy or managed deployment may disable support. No plugin installation is needed. |
| RTK OSS command filters | Pinned candidate; not installed | Can shorten shell output. Rust is absent here. The current default edition includes an additional engine; its optional proxy can route to cheaper models. That routing is incompatible with the Opus-only requirement. |
| Headroom runtime | Not activated | Its broader proxy/compression/model and effort-changing surface is unnecessary for the first integration. Its retained local guidance remains usable. |
| Context Mode | Not activated | Adds broad execution/retrieval tools, hooks and a second session store. Those need a separate permission/evidence review; they would duplicate the existing durable state. |

The live synthetic example returned `eligibility()` at line 4 and its caller
`evaluate()` at line 20. The original file was **1,188 bytes**; the complete lookup
response was **406 bytes**: **65.82% fewer output bytes for that one navigation
question**. This is not a provider token measurement, an end-to-end cost saving,
or a forecast for another program. The smaller answer deliberately omits rule
bodies, so agents must still read relevant lines before implementing or auditing.
See [`TOKEN_TOOLS_EVIDENCE.json`](TOKEN_TOOLS_EVIDENCE.json).

## Reproduce the installed dependency

Use a project-local Python 3.12 environment. This lock was installed and exercised
with CPython 3.12.14 on Linux. The adapter requires no-follow directory opens on
Linux/WSL or macOS; it refuses to run on native Windows rather than weaken that
file-access boundary. In VS Code on Windows, bind this optional command to an
approved WSL workspace. That workstation binding still requires verification. No global install,
startup script, automatic update, background service or provider credentials are
needed. These commands do not expand Claude's permission allowlist.

```bash
python -m venv .implementation/token-tools/venv
.implementation/token-tools/venv/bin/python -m pip install --require-hashes --only-binary=:all: -r config/token-tools.requirements.txt
.implementation/token-tools/venv/bin/python tools/graphify_lookup.py --file examples/rule_validation/demo_target.py --symbol eligibility
```

Use the approved package mirror if required by the workstation. The wheels-only
and hash requirements fail
closed if a compatible artifact is unavailable. Do not remove hashes to make an
install pass. The environment contains 30 pinned distributions; no binary or
grammar packages are vendored into Git.

The build installation used the equivalent `uv venv` and `uv pip install` commands.
Installed Graphify package files that have counterparts in the pinned checkout
were compared byte for byte, with no differences. The lock fixes downloaded
artifact hashes; pinning is not a vulnerability audit or proof of provenance by
itself. Independent `pip-audit` 2.10.1 checking found no known vulnerabilities
in the 30 locked packages on 2026-10-16. Independent review also reproduced and
closed a mutable-source provenance defect after the snapshot fix. These scoped
checks are recorded in the evidence file; they do not guarantee complete security.

Do **not** run upstream `graphify install`, its hook registration commands,
`graphify extract`, or even its general CLI for this integration. At this revision
the general CLI can refresh previously installed skills; generic extraction can
select a semantic backend. The adapter imports only `extract_python` and invokes
no semantic backend, provider SDK, cloud service or model. The original source is
parsed, never imported or executed.

## Agent operating instructions

1. The lead supplies an explicit approved Python file and a symbol question. Use
   a known source map first. Use lookup when it avoids reading an entire file.
2. Invoke the adapter only through the workstation's approved command binding.
   Its accepted paths are `examples/`, `tools/`, and `programs/<id>/target/`.
   Existing raw-source, private-record and tool denials remain effective. This
   path restriction does not certify target code as suitable for model context;
   the normal sanitized-input requirement still applies.
3. Read the returned source hash, matching lines, caller links and `truncated`
   flag. A zero-result response means no static match in that file, not that the
   program has no such behavior. Dynamic calls, cross-file callers and JCL/COBOL
   dependencies remain the responsibility of source analysis and the dependency
   register. This integration is Python-only despite broader upstream support.
4. Read exact relevant source spans through the approved reader. Never infer a
   rule's semantics, safe deletion, complete caller set or security from the graph.
   Recompute a lookup after source changes; do not treat stale output as memory.
5. Return IDs, hashes, counts, blockers and artifact references in handoffs. Keep
   full test results, original outputs and every-record trace in their canonical
   evidence stores. Summaries never remove evidence or award conversion credit.

The adapter rejects traversal, symlink/hardlink inputs, unrecognized directories,
invalid Python and files over 1 MiB. It opens each path component without following
links, captures bounded bytes, then parses a private read-only snapshot. The
advertised hash and the parser consume those same captured bytes, so another agent
editing the original during extraction cannot mislabel the result. The temporary
snapshot is removed after the call. It emits at most 12 matched symbols and 12
calls, with bounded names and explicit truncation. A Python audit hook blocks
network and child-process operations during the parser call as defense in depth.
It is **not an OS sandbox** against malicious native dependencies. Run only the
pinned, reviewed environment and retain normal host isolation/access controls.

## Native context controls

Claude's current first-party default defers MCP definitions. Do not blindly set
`ENABLE_TOOL_SEARCH=true` for an enterprise gateway: unsupported providers can
reject tool-reference blocks. Verify DB2 MCP discovery and denied-tool behavior
on the actual host, then record the effective setting in the workstation receipt.
Keep tool descriptions concise and disable irrelevant servers through the
organization's normal controls, without modifying the user's other projects.

Keep the three core skills as the entry points. Load optional guidance only for
the relevant job, avoid preloading all role guidance into every worker, and retain
the two-worker and repair-budget limits. Persist decisions and hashes before a
context reset. The durable memory files remain the authority, not a second
plugin database. Do not change the approved model or reduce quality gates to save
tokens. A smaller transcript is useful only if the required task is still correct.

## Measure, then keep or remove

For the same frozen program, source hashes, task and Opus 4.7 configuration,
compare baseline against the selected tool. Record input/output/cache tokens
from provider receipts, total elapsed time, complete tool output bytes, retries,
failed gates and audit defects. Include every worker and any plugin/model call.
If provider usage is unavailable, record it as unavailable; bytes are not tokens.

Retain the tool only when the task's source coverage, 100 positive/100 negative
cases per executable rule, record trace, replay and independent audit still pass.
Do not count a filtered test summary as the test result. Never compress protected
data into an external service, conceal failed rules, drop exceptions from logs,
or suppress permission errors to improve the saving figure. There is no measured
claim here of drastic whole-project savings.

To remove this optional integration, stop invoking the adapter and remove the
isolated environment through normal workspace cleanup. No registered hooks or
provider settings require rollback. Historical evidence and lock receipts remain
available for audit.

## Primary references

- [Graphify pinned source and install documentation](https://github.com/Graphify-Labs/graphify/tree/10130e79ed9caf8f60d998073e097531eaa1a395)
- [Graphify direct local parser](https://github.com/Graphify-Labs/graphify/blob/10130e79ed9caf8f60d998073e097531eaa1a395/graphify/extract.py)
- [RTK pinned source](https://github.com/rtk-ai/rtk/tree/f16becacd2f40616839333b3e0e281e40a0bc823)
- [Headroom reviewed source](https://github.com/headroomlabs-ai/headroom/tree/df11f2749862a0090db11f7fca3e7dc42a75b612)
- [Context Mode reviewed source](https://github.com/mksglu/context-mode/tree/40813fe886798bad07c69a43d2ae00a52b4b934d)
- [Claude MCP tool search](https://code.claude.com/docs/en/mcp#scale-with-mcp-tool-search)
- [Claude skill loading](https://code.claude.com/docs/en/skills)
- [Claude usage measurement](https://code.claude.com/docs/en/costs)
