# Deprecated Copilot entrypoint metadata

The active modernization workflow uses Claude Code for approved read-only
retrieval, analysis, development, testing and review. GitHub Copilot is not a
required host or handoff step. This file remains as compatibility entrypoint
metadata for people opening an older checkout.

Read [AGENTS.md](../AGENTS.md), [repository context](../prompts/CONTEXT.md) and the
single [Start workflow](../prompts/START_MODERNIZATION.md). Do not start a second
workflow, proxy Claude through Copilot, or reuse historical prompts as current
instructions. Current requests, paths and gates come from the existing
Coordinator and selected process guide. Immutable historical evidence stays intact.

Mainframe access remains read-only: Db2 uses approved typed MCP; source and
dataset metadata use Zowe CLI. Never execute legacy programs, submit jobs, write
source/Db2 data, answer SME questions or infer approval. Keep credentials and
private exports out of repository commits. Follow
[the folder contract](../docs/TECHNICAL_REFERENCE.md); scratch belongs under
`.implementation/tmp/`, and the required workstation is Windows 11.

Raw customer/dataset records, including SSNs, must stay in protected local storage
inside the approved network. Never read them into an LLM, MCP tool response,
prompt, model API, screenshot/upload or diagnostic output. Use synthetic data or
explicitly approved masked examples for model-visible work. Source comments and
control cards can also contain private values: use approved sanitized views, not
an assumption that code is safe. Original source is protected by default;
LLM access requires an approved sanitized view and absent safe semantic context
remains a qualification gap. Local deterministic comparison may read protected
files and return counts, hashes and exact gaps without row values. The operator-only
localhost database inspector is distinct from model-visible content. A masking
regex is not comprehensive privacy assurance; enterprise approval and least-privilege
server enforcement remain required.
