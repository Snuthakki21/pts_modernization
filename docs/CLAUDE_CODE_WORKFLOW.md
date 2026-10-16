# Claude Code operating workflow

Use one foreground lead, at most two specialists, and one bounded objective per
program or dependency wave. Keep VS Code for source, diffs and the dashboard.
Use the integrated terminal for native automation commands when the extension
does not expose them. This uses the existing agents, skills and durable handoff;
it adds no coordinator service or scheduler.

Official documentation and the Claude Code GitHub changelog were checked on
**2026-10-16**. These are documented capabilities, not a receipt that this user's
VS Code installation, provider or mainframe has been exercised.

## 1. Establish the actual host

1. Open this repository's branch in VS Code. Follow
   [START_HERE](../START_HERE.md) to initialize missing local state; preserve
   existing inventory, handoff and repair counters.
2. Record the extension version. If using a terminal, check `claude --version`
   and `claude --help`; the extension's bundled CLI does not put `claude` on PATH.
   The extension exposes a subset of commands; inspect its `/` menu. In the CLI,
   use `/help`. [VS Code documentation](https://code.claude.com/docs/en/vs-code)
3. Confirm `/model`, worker models and the effective provider mapping are Opus
   4.7. Keep `xhigh`, the two-worker limit and all existing denials. Test required
   read/execute bindings through the approved workstation setup. Record blocked
   bindings rather than trying alternative commands to bypass them.
4. Before native `/goal`, verify its evaluator route separately. It uses the
   configured small-fast model. `ANTHROPIC_DEFAULT_HAIKU_MODEL` controls that route
   and other auxiliary model work; the foreground model setting alone is
   insufficient. This kit pins that auxiliary setting to `claude-opus-4-7`;
   require an approved, observed binding for every model call. Otherwise use
   the ordinary goal prompt and manual resume below.
   [Goal evaluation](https://code.claude.com/docs/en/goal#evaluation-model-and-cost)
5. Check `/goal` and `/loop` availability on this host and effective managed
   policy before invoking them. Do not change permissions or hooks to make a
   missing feature appear. The fallback is the same bounded task in an ordinary
   conversation, followed by an explicit resume when necessary.

An evaluator verdict is a progress signal, never independent application audit.
Only actual source-linked checks and fresh receipts satisfy this kit's gates.

The foreground agent explicitly exposes `CronCreate`, `CronList`, `CronDelete`
and `ScheduleWakeup`; specialists do not schedule work. These documented built-ins
do not require separate permission prompts. The narrow `Skill(loop)` approvals
let the lead load the bundled skill when requested. Confirm actual availability
and list/cancel one bounded monitor on the workstation; no schedule was created
in this authoring environment. [Tool reference](https://code.claude.com/docs/en/tools-reference)

## 2. Choose the right continuation mechanism

| Mechanism | Verified behavior | Use here |
|---|---|---|
| `/goal CONDITION` | Starts immediately; one active goal. `/goal` reports status; `/goal clear` cancels. Completion, impossibility or unrecoverable error can clear it. It needs trusted hooks and compatible managed settings. | One bounded implementation/validation objective, only after evaluator routing is verified. |
| `/loop 15m PROMPT` | Repeats a prompt on a schedule; explicit interval gives fixed scheduling. This can execute work, not just monitor it. | Restrict our prompt to monitoring existing receipts and running tasks. Do not start another conversion owner. |
| Ordinary prompt | Uses the existing conversation and tools. | Default when native feature/model routing is unavailable; persist and explicitly resume. |

Sources: [goals](https://code.claude.com/docs/en/goal),
[scheduled tasks](https://code.claude.com/docs/en/scheduled-tasks).

Active goals restore on resume, but their displayed timer, turn count and token
baseline reset. Background tasks defer evaluation. This kit sets
`CLAUDE_CODE_GOAL_CHECKIN_MINUTES=0`: automatic idle check-ins and retries are off;
ordinary turn-to-turn continuation remains. Resume explicitly after a pause.
Preserve cumulative limits in the handoff and reconcile uncertain external jobs
before any retry. [Goal lifecycle](https://code.claude.com/docs/en/goal)

Fixed scheduled tasks resume with exceptions: expired recurring tasks and past
one-shot tasks are not restored. Self-paced loops and background shell/monitor
tasks are not restored. Recurring tasks expire after seven days. Tasks require a
running session; missed intervals do not all replay. Timing can be delayed or
jittered. List/cancel tasks by their recorded IDs; verify cancellation. Do not
treat closing a window as proof a background session stopped.
[Scheduling limitations](https://code.claude.com/docs/en/scheduled-tasks#limitations)

This kit's [.claude/loop.md](../.claude/loop.md) limits bare `/loop` to status
monitoring. Prefer the explicit, bounded prompt below so the intended goal and
deadline are unambiguous. Do not add a Stop hook or another session store. Built-in
commands and skills marked `disable-model-invocation: true` cannot be scheduled
as executable skills. [Loop prompts](https://code.claude.com/docs/en/scheduled-tasks)

The upstream changelog introduced `/loop` in 2.1.71 and `/goal` in 2.1.139.
Later fixes matter: 2.1.274 preserves goals after compaction/resume; 2.1.290 fixes
scheduled-task restoration after new compactions; 2.1.295 fixes pending-loop
cancellation in background sessions. Use the organization's approved current
version and verify capabilities rather than relying on the introduction version.
[Pinned changelog](https://github.com/anthropics/claude-code/blob/03b5892ee77de289bcd5dfa39f541525ade74aff/CHANGELOG.md)

## 3. Define completion before spending tokens

The lead writes the objective into the existing `knowledge/handoff.json`.
Use the existing fields rather than introducing a new state file:

| Handoff field | Required content |
|---|---|
| `current_task` | Goal ID, program/wave IDs, exact intended outcome and acceptance checks. |
| `versions`, `owned_paths` | Source, decisions, dependency and target fingerprints; each worker's disjoint ownership. |
| `execution_limits` | Original start/deadline, cumulative turn/usage limits and observed usage; model/capability receipt reference; monitoring task IDs and original expiry if used. |
| `repair_budget` | Original configured allowance and remaining cycles per program; never replenish on resume. |
| `completed_checks`, `blockers` | Actual check receipts; terminal outcome: completed, blocked or budget-exhausted. A paused attempt is not a completed conversion. |
| `pending_tasks`, `next_action` | Dependencies, unresolved external-job IDs and the next eligible action. |

Prompt limits are agent instructions, not a hard billing or runtime barrier. If a
hard spend control is required, bind the organization's actual control before
unattended work. CLI `--max-budget-usd` and `--max-turns` are print-mode controls;
the estimated spend cap can overshoot and excludes spend restored on resume.
Do not assume they cap a graphical session or cumulative project spend.
[CLI reference](https://code.claude.com/docs/en/cli-reference)

Completion requires every executable rule accounted for, 100 distinct positive
and 100 distinct negative passing cases per retained/replaced rule, independent
expected results, observed legacy comparison or an evidenced authorized difference,
full record traces, reproducible failures and fresh quality/security/audit gates.
Keep technical, business and mixed rules visible. A finite-domain shortfall is a
gap, not permission to duplicate cases. Process completion also requires its own
integration evidence and compatible shared-program bindings.

## 4. Run a small wave, then expand

1. **Lead + gap analysis/design:** inventory all source obligations, classify
   rules, freeze source/decision hashes and the compatibility profile. Batch only
   genuine business ambiguities for SMEs. Reuse a validated shared program only
   after checking the consuming process and current evidence.
2. **Backend + QA in parallel:** backend implements Python in its owned target
   paths; QA develops source/SME-derived expectations and synthetic cases in
   separate test paths. QA must not copy expected answers from the Python target.
3. **Required Ponytail pass:** read the retained local
   [Ponytail skill](../.claude/skills/ponytail/SKILL.md) once for the applicable
   task. Simplify the design and implementation using existing helpers or small
   explicit functions. Preserve dependencies, behavior, protections and evidence.
   Record the concrete simplification or why no safe reduction was justified.
4. **QA/analytics, then independent audit:** validate exact versions, record
   complete traces and parity, remediate by root cause within the remaining
   two-cycle allowance, and let a fresh audit inspect the fix. Authors cannot
   certify their own changes. Do not weaken assertions to obtain green results.
5. **Lead publishes evidence:** update canonical inventory, the single Sparkflows
   migration document and an exported progress snapshot. Stop at the first
   terminal outcome or the original budget, then persist the next action.

Keep the source map and stable migration IDs alongside Python ETL comments.
Future Sparkflows replacement must preserve dependency ordering, shared consumers,
lineage, single-writer effects and rollback. Use
[safe rule removal](RULE_REMOVAL.md) for authorized behavioral deletion.

For navigation, use a current hash-bound Graphify result and read the actual
affected code. Refresh after changes; a graph cannot prove complete dependencies.
Use Caveman only for concise status prose. If an approved RTK filter is available,
use it for selected terminal summaries while retaining the original output,
exit status, failures and every-record evidence. Do not add a proxy, model route
or broad command-rewriting hook to save tokens. See
[token efficiency](TOKEN_EFFICIENCY.md).

Use the [paste-ready prompts](../prompts/GOAL_WORKFLOW.md). Start with one pilot,
then one dependency-ready wave. Do not run a portfolio-wide endless loop or
schedule repeated instructions that can submit duplicate external jobs.
