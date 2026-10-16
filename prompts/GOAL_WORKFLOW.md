# Goals and bounded loops: paste-ready prompts

Use [Claude Code workflow](../docs/CLAUDE_CODE_WORKFLOW.md) first. Replace angle
brackets with real approved IDs/paths and an original UTC deadline. These prompts
do not grant permissions or claim workstation bindings are verified. Load only
the current program's context. Every prompt inherits `AGENTS.md`, `CLAUDE.md` and
the existing handoff; do not paste all guides into every worker.

## Host check — once per changed host/configuration

```text
Establish this checkout's effective Claude Code capability receipt. Read the
operating instructions and existing handoff. Confirm the actual foreground,
worker and auxiliary/evaluator routes are Opus 4.7 with no fallback. Report the
installed version, /goal and /loop availability, effective policy, permitted
Zowe/DB2 bindings and any missing evidence. Do not expose credentials or bypass
denials. Native /goal is unavailable for this effort until its separate evaluator
route is verified as Opus 4.7. Preserve all existing budgets and state. Load the
local Ponytail skill for minimal complete design. Give the next eligible action.
```

## Pilot — ordinary goal prompt works without native /goal

```text
Use /modernize-process for process <PROCESS>, starting with program <PROGRAM>
and approved sanitized manifest <MANIFEST>. Goal <GOAL-ID>: produce the smallest
reusable Python implementation with source-to-target mapping, a compatibility
profile and evidence for every rule and processed record. Load local Ponytail
and perform its simplification pass without removing required behavior.

You are the foreground lead. Use at most two specialists with disjoint paths.
Freeze rules/decisions before backend implementation and independent QA case
design run in parallel. Require 100 distinct positive and 100 distinct negative
passing cases per executable retained/replaced rule; use source/SME-derived
expected results, not the target as its own oracle. Require full traces, replay,
observed mainframe parity or authorized differences, affected process integration
and independent quality/security audit of the final version. Keep unknowns open.

Implement ETL in Python now; update the single Sparkflows migration document with
flow IDs, artifacts, dependency/consumer order and later replacement boundaries.
Refresh affected Graphify lookups after edits before reusing navigation results.

Persist this goal's contract and cumulative usage in knowledge/handoff.json.
Stop this attempt at completed, a genuine blocker, original deadline
<UTC-DEADLINE>, 12 cumulative lead turns, or the existing tighter budget—whichever
comes first. Never reset budgets; allow at most the remaining two repair cycles.
Preserve an unknown external-job outcome and reconcile before retry. Batch SME
questions and continue independent work within this same bounded attempt.
Return outcome, passed/required rule counts, artifact references and next action.
Only the lead updates inventory; blocked or budget-exhausted is not completed.
```

Choose one startup path. For an ordinary session, submit the pilot prompt above.
For **verified native `/goal`**, first prefix that pilot prompt with:

```text
Record this pilot contract and its original limits only; do not start conversion.
I will start the recorded task with /goal after the capability checks pass.
```

Then submit the command below once. It immediately starts work. Do not start a
second goal for an already running or terminal attempt. The terminal condition
ends the attempt; the handoff preserves whether conversion actually completed.

```text
/goal Goal <GOAL-ID> in knowledge/handoff.json has an evidenced terminal outcome: completed with every recorded acceptance gate satisfied, or blocked/budget-exhausted with exact missing evidence and next action preserved. Follow that contract using Opus 4.7 only, at most two specialists and required Ponytail simplification. Stop at its original deadline, 12 cumulative lead turns or tighter remaining budget. Never reset counters, duplicate uncertain external jobs, weaken tests or mark an incomplete conversion completed. Surface check commands, actual exit/results, current hashes and receipt references so the outcome can be assessed.
```

The `/goal` evaluator's judgment does not replace the independent audit. Check
status with `/goal`; cancel an active goal with `/goal clear` when needed.

## Portfolio — one dependency-ready wave

```text
Use /modernize-process to reconcile total canonical inventory against the approved
source manifests for <PORTFOLIO>. Preserve unmapped programs and stale evidence.
Select the next dependency-ready wave with at most two active program owners;
reuse compatible validated programs by version rather than copying them.
Record exact wave IDs, owned paths and the original limits in the existing
handoff. Apply the pilot acceptance contract and required Ponytail pass to each
program. Stop at <UTC-DEADLINE>, 12 cumulative lead turns, an exhausted budget,
or when this wave is completed or blocked. Do not automatically create a new
wave or reset counters. Export progress showing total, converted, completed,
blocked and stale programs separately; return the next eligible wave.
```

## Resume — do not restart the analysis or the budget

```text
Resume goal <GOAL-ID> from knowledge/handoff.json. Verify source, decision, target,
dependency and index fingerprints before using prior findings. Reconcile recorded
external-job IDs and actual worker/task state before creating any new work.
Preserve original elapsed/turn/usage limits and remaining repair counters even
if the native session displays reset counters. Reuse current artifacts, load
Ponytail only if its relevant guidance is absent, and perform the next eligible
action with at most two workers. If the original limit is exhausted, persist
budget-exhausted and stop. Do not recreate loops or goals merely to obtain a new
budget. Report missing bindings or changed assumptions precisely.
```

## QA repair — implementation and audit stay independent

```text
Use /validate-program for <PROGRAM>, run <RUN-ID>, preserving the failed receipts
and portable reproducer. Group failures by evidenced root cause. Backend makes
the smallest corrective change; QA reproduces the failure and tests the fix;
a fresh pts-audit independently challenges the exact target/dependency version.
Use the remaining repair budget in the handoff. Apply Ponytail to avoid duplicate
logic while preserving all source obligations. Rerun affected cases and required
regressions, retaining 100 positive and 100 negative passing cases per executable
rule, full traces and valid oracle/parity evidence. Do not edit expectations to
match the target. Stop repeated non-progress or an exhausted budget. Missing
checks, stale evidence and open critical/high findings prevent completion.
```

## Monitoring — optional fixed loop, one task only

First ask Claude to list scheduled tasks and reuse/cancel any existing task for
this same goal. Use this explicit prompt only when native scheduling and the
model routes are verified; record the confirmed task ID in the handoff. The
deadline is absolute and is not extended by retries, resume or task recreation.

```text
/loop 15m Monitor goal <GOAL-ID> using knowledge/handoff.json and permitted existing task/evidence status only. Do not start conversions, repair code, rerun tests, submit mainframe/DB2 jobs, change acceptance or launch another owner. Report only changed counts/blockers and receipt references; keep all underlying evidence. Persist cumulative monitoring usage and this confirmed task ID. Cancel this exact scheduled task and verify its absence when the goal reaches any terminal outcome, at <UTC-DEADLINE>, after four scheduled checks, or at its tighter remaining budget. Preserve a cancellation failure as a blocker; never silently recreate the task. Other tasks are outside this instruction.
```

No native loop? Ask for the same status once and explicitly repeat when needed.
Do not invent a scheduler. To stop, ask: `Cancel monitoring task <TASK-ID> and list
the remaining tasks to verify it is gone.` Do not rely on `/goal clear` to cancel
a separate scheduled task.

## Safe removal — one rule or one consumer's use

```text
Use /modernize-process remove-rule <PROGRAM> <RULE-ID> process=<PROCESS>
reason="<INTENDED BEHAVIOR CHANGE>". Follow docs/RULE_REMOVAL.md. Verify actual
consumers and dependent rules first; load Ponytail for the smallest safe patch.
Preserve shared behavior needed by other consumers, original sources and old
evidence. Produce the reversible patch, new absence/effect checks and affected
regressions within the existing budget. Regenerate current source/dependency
lookups, update the rule disposition, migration cards and inventory only from
fresh checks. Record intentional legacy differences and separately identify any
data-repair action. Stop only affected work if the intended consumer/behavior is
ambiguous; do not delete a shared function just because it contains this rule.
```
