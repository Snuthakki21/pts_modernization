# Synthetic rule-validation example

This small example exercises the [rule-case utility](../../tools/rule_cases.py)
with two invented rules and 400 data cases. It contains no real application,
customer records or credentials. The [COBOL fixture](synthetic_rules.cob) is a
reference fragment, not a deployable program; it has not been compiled or run on
a mainframe. Local agreement does not establish COBOL parity, full application
source coverage, complete record tracing, process integration or acceptance.

| Rule | Source contract | Positive cases | Negative cases |
|---|---|---|---|
| `R-ELIGIBILITY` — business | An unsigned four-digit amount is eligible at 100 or above. | 100..198 and 9999: 100 distinct true inputs | 0..99: 100 distinct false inputs |
| `R-NAME-FORMAT` — technical | Move an ASCII input of length 0..40 into a 20-character display field, preserving spaces; flag truncation above 20. | 100 distinct fitting strings, including empty, 1, 19 and 20 characters | 100 over-width strings with distinct retained prefixes; includes lengths 21 and 40 |

Both executable rules require **100 positive and 100 negative passing cases**.
A technical negative here means the correct truncation branch, not an exception
or failed test. All cases remain within the declared input contract. The adapter's
out-of-contract guards are not counted toward the quota. Quotas do not prove that
every possible boundary, failure mode or interaction has been tested.

[demo_oracle.py](demo_oracle.py) enumerates explicit source-contract groups and
freezes expected values without importing or running
[demo_target.py](demo_target.py). The target computes actual results through
`evaluate(rule_id, inputs)` and the mapped rule functions. This demonstrates
separated oracle code, not a claim of completed independent human verification.
Real conversions require independent source/decision review and must never derive
their expected answers from the target under test.

[catalog.json](catalog.json) pins source/oracle/target hashes, declared source-unit
IDs, symbol mappings, polarity meanings, rule-relevant `distinction_fields` and
coverage tags. Name cases vary retained content that affects the result; changing
only an ignored suffix or case ID would not justify the quota. Finite-domain gaps
in other rules must remain explicit instead of being padded.

## Run the actual example

Run from the repository root using Python 3.11 or later. Inspect the three source
files first: the utility executes trusted local Python with the caller's
permissions. The execution flag does not create a sandbox.

```bash
mkdir -p .implementation
pts_demo_run=$(mktemp -d .implementation/demo-rule-validation.XXXXXX)

python tools/rule_cases.py generate --root examples/rule_validation \
  --catalog examples/rule_validation/catalog.json \
  --output "$pts_demo_run/cases.json" --max-candidates 1000 \
  --allow-local-execution

python tools/rule_cases.py run --root examples/rule_validation \
  --catalog examples/rule_validation/catalog.json \
  --cases "$pts_demo_run/cases.json" --output "$pts_demo_run/results.json" \
  --allow-local-execution
```

`mktemp` gives each attempt a fresh output directory. Preserve both receipts;
never overwrite the failed run when investigating a change. Catalog artifact
paths are relative to `examples/rule_validation`; output paths are ordinary shell
paths. Exit 0 means the respective generation or unit data gate passed; exit 2
means a blocked/failed gate or invalid input. Read each receipt's per-rule counts,
coverage and per-case observations, not just the exit code.

When deliberately changing the fixture, oracle or target, review the changed
contract and update its SHA-256 in the catalog. Then generate a new case file and
execute into a new directory. Old cases pin the old catalog and must be rejected
against the changed one. Never modify expected values merely to hide a target bug.

For the complete workflow, see the [application guide](../../docs/APP_MODERNIZATION_GUIDE.md).

## Observed local example check

On 16 October 2026, the commands above generated and executed all 400 synthetic
cases locally. Both rules recorded 100 passing positives and 100 passing negatives,
with no missing declared coverage categories. The run receipt explicitly retained
`program_acceptance_established: false`. This is an observed check of this example
and utility; no actual application, mainframe or model evaluation was performed.
