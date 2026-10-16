# Opus quality and runtime verification

This kit stays on the approved **Opus 4.7** deployment. Its quality target is
source-faithful, independently tested modernization. A setting or instruction cannot
turn that model into Opus 5.5 or establish equivalent performance. No live Opus
evaluation has been performed in this authoring environment: the Claude executable
and the user's VS Code session are unavailable here.

## Configured controls

| Control | Delivered binding | Verification |
|---|---|---|
| Foreground model | `.claude/settings.json`: explicit `claude-opus-4-7` | Check actual host/provider model, not just this file |
| Worker models | All nine definitions pin the same model; subagent model plus force environment settings | Observe an active worker in `/tasks`; retain a sanitized routing receipt |
| Auxiliary/evaluator model | `ANTHROPIC_DEFAULT_HAIKU_MODEL: claude-opus-4-7` | Verify actual small-fast route before `/goal`; foreground/subagent pins alone do not cover it |
| Goal continuation | `CLAUDE_CODE_GOAL_CHECKIN_MINUTES: 0` | No automatic idle check-ins/retries; direct turn continuation remains, bounded by persisted original limits |
| Reasoning effort | Project `effortLevel: xhigh`; each agent `effort: xhigh` | Check effective effort and organization/environment overrides |
| Concurrency | Project maximum two workers; runtime subagent cap `2`; `ultracode: false` | Lead also counts active/resumed work; avoid alternative spawning routes |
| Fallback | Project policy prohibits other models | Inspect effective settings, launch configuration and observed routing; policy text is not host enforcement |
| Instructions | `CLAUDE.md` explicitly imports `AGENTS.md` and `knowledge/MEMORY.md` | Inspect loaded memory/context in a new session |
| Repair | One initial validation and at most two repair cycles | Persist the original counter in the handoff; never reset it on resume |

Current [model documentation](https://code.claude.com/docs/en/model-config)
supports `xhigh` for Opus 4.7 and describes it as that model's default. `max` is
available for difficult work but can have diminishing returns. Opus 4.7 uses
adaptive reasoning. Do not add a fixed thinking-token budget or a moving model
alias to simulate another model. An explicit effort environment variable or
organization cap can override the intended level; check effective behavior.

The [subagent documentation](https://code.claude.com/docs/en/sub-agents) requires
Claude Code **2.1.257 or later** for the combined subagent-model/force mechanism.
It documents the runtime concurrency cap from 2.1.217, but resumes, forks and other
execution mechanisms have exceptions. The lead's two-worker rule remains required.
Per-invocation effort overrides require 2.1.292; the delivered agents use static
frontmatter instead. Do not use Ultracode or a separate team mechanism to bypass
this kit's role, concurrency or model constraints.

The [memory documentation](https://code.claude.com/docs/en/memory) distinguishes
explicit imports from prose asking an agent to open another file. The imports here
make the shared instructions and curated memory explicit. Large guides, prior
results and source excerpts remain targeted reads. Imports still consume context.

## One workstation verification pass

DevOps records non-secret facts in `.implementation/workstation.json`. Reuse the
existing configured extension, Zowe CLI and Db2 MCP; do not reinstall them blindly.

1. Record the extension and actual Claude runtime versions. Check supported
   settings against those versions. Do not infer runtime support from VS Code's
   presence or the repository's extension recommendation.
2. Inspect effective model/effort settings and the launch environment locally.
   Check for fallback chains and advisor/alternate-model settings. Do not print
   credentials or copy complete environment/settings files into model context.
3. Use `/status` and the installed model/effort controls for the foreground;
   observe a permitted synthetic worker in `/tasks`. Record actual provider/model
   evidence and effective effort. A display label alone may not prove gateway
   routing; use an authorized provider receipt when that routing is indirect.
4. Inspect loaded context to confirm the imports. Start a harmless task, save a
   handoff, reopen the session, and confirm it resumes from the same versions,
   open questions and remaining repair allowance.
5. If the host cannot honor the approved model for delegates, remain in a verified
   same-model foreground session. If that cannot be verified either, keep model
   execution blocked while preparing inputs. No cross-model fallback.

The [VS Code documentation](https://code.claude.com/docs/en/vs-code) describes the
extension's model/effort controls and shared Claude settings. Their presence and
behavior must be checked in the user's installed version. This kit does not install
extensions or alter machine credentials.

For a verified managed deployment ID, update `config/project.json` model `id` and
`provider`, keep `approved_family: opus-4.7` and `no_fallback: true`, record
`provider_binding_confirmed: true` plus a non-secret `deployment_mapping_reference`,
and update settings/worker model pins together. The instruction evaluator reads
that binding. Its acceptance of the declaration does **not** authenticate the
mapping; the environment owner must retain the actual mapping evidence. Canonical
other-model IDs and moving aliases are not valid replacements.

Include the auxiliary `ANTHROPIC_DEFAULT_HAIKU_MODEL` mapping when changing a
managed deployment ID. It affects goal evaluation and other small-fast work;
do not test the evaluator by first allowing a call to another model. Read the
[goal/loop guide](CLAUDE_CODE_WORKFLOW.md) and verify effective provider settings
before execution. Native evaluator approval does not replace independent audit.

## Improve measured work, not a model label

Use `xhigh` for the baseline. Consider a session-scoped `max` experiment only for
a specific unresolved semantic problem after the normal evidence review. Stay on
the same Opus 4.7 deployment and within the original time/token/repair budget.
Record effective effort and the result; do not permanently increase effort because
one response sounds more confident. Revert to the baseline if quality does not
improve enough to justify cost. Do not weaken acceptance criteria to save tokens.

QA and audit select a small representative **held-out** set from approved source
that was not used to tune the instructions. Freeze source, dependencies, expected
behaviors, environment and review rubric before the run. Include decimal/encoding
edge cases, shared callers, conditional JCL, database state, a failed-record replay
and removal of one rule that shares code with a retained rule. Keep expected
answers away from the implementation session. Public instructional scenarios are
training/contract checks, not this held-out evaluation.

Run the prior and revised Opus 4.7 configurations on the same frozen tasks and
resources, with separate fresh state. Compare actual artifacts rather than prose:

| Measure | Required evidence |
|---|---|
| Source and rule completeness | Independent source ledger; omissions, misclassifications and unresolved units |
| Behavior | Independent expected data; actual Python assertions; 100 positive and 100 negative passing cases per executable rule; declared coverage gaps |
| Fault detection | Deliberately introduced semantic defects caught by the independent tests; restore the unmodified candidate afterward |
| Record evidence | Complete occurrence-level rule/effect lineage and reproducible failure context |
| Reuse and removal | Every affected consumer tested; retained behavior intact; unwanted behavior/effects absent; rollback evidence |
| Engineering quality | Independent review of semantic defects, duplication, hidden defaults, unnecessary code and database behavior |
| Cost and persistence | Observed tokens, elapsed time, calls, repair attempts and correct resume after interruption |

Do not use an averaged score to hide a failed required gate. An unknown or missing
measurement is unverified, not zero defects. Record unresolved findings separately
from accepted intentional changes. Without an authorized comparable Opus 5.5 run,
there is no empirical basis for claiming parity with it; this comparison measures
improvement within the allowed Opus 4.7 workflow.

## Retain an auditable result

Keep the quality receipt with the existing ignored run evidence. Record evaluation
ID, task/source/decision hashes, instruction/suite fingerprint, actual runtime/model
and effort receipts, case/test result references, defects and reviewer, cost
measurements, remaining gaps and next action. No receipt is pre-filled as passing.

Run `tools/check_instruction_responses.py` after changing agent, skill, memory or
template instructions. It checks pinned structured responses and now includes
safe rule removal. Human review of explanations and observed tool behavior remains
required. Its synthetic fixture mode never counts as an actual Opus evaluation.

The full [application guide](APP_MODERNIZATION_GUIDE.md) defines acceptance;
[folder and memory guidance](FOLDER_STRUCTURE.md) defines durable state;
[rule removal](RULE_REMOVAL.md) defines reversible deletion of converted behavior.
