# Workbook operating guide

The [review workbook](../examples/PTS_Modernization_Review_Template.xlsx) brings
SME decisions, mainframe-to-Python comparisons and record evidence into one file.
Use Excel 365 or Excel 2021 or later for the dynamic record timeline. The workbook
is a review projection of approved evidence. It does not instrument programs,
collect runtime events, execute jobs or automatically import evidence.

## Start with the review question

| Question | Open |
|---|---|
| Where do I start, and which cells may I edit? | Home |
| Which rules did this particular record encounter? | Record Trace |
| What did the mainframe require, and how does Python satisfy it? | Gap Analysis |
| Which business behavior should remain or change? | SME Review |
| What proves the rule's positive and negative cases? | Rule Evidence and Case Catalog |
| What has already been converted and can be reused? | Converted Inventory |
| Where did the selected evidence come from? | Run Manifest, Record Index and Trace Events |

Process Intake, Workflow, Agent Map and Illustrative Review retain their supporting
content. SMEs supply business decisions and genuine clarifications. Engineering
supplies classification, implementation mappings, reuse decisions and evidence.
Do not use an implementation status as proof of successful execution.
Rule Evidence and Case Catalog now cover every executable business, technical and
mixed rule: 100 meaningful distinct passing positive cases and 100 negative cases
for each. Import actual per-rule results from the application guide's validation
process, including zero coverage and finite-domain gaps. The workbook does not
generate or execute these cases and its fictional examples establish no acceptance.
The original nine tabs retain their order. Use **Review home** and **Record trace**
links on those tabs to open the added views.

## Follow one record

1. In Record Trace, type or paste the run ID and the opaque record-occurrence ID
   from Record Index. The view checks that they identify exactly one run and
   record. A business key alone cannot distinguish duplicate input records.
2. Read the three separate evidence states before interpreting the timeline:
   run capture, the selected record's capture attestation and workbook import
   completeness. A complete record export does not establish a complete run.
3. Review every displayed event membership. The view shows event ID, rule ID,
   outcome, attempt, operands, effect, evidence, mainframe source and Python/flow
   source. Scroll right to columns J–T for run, record, version, invocation,
   ordinal, causal parent, lineage, gap, engine, snapshot and event-kind metadata;
   the same fields are available in Trace Events. Repeated evaluations and retries remain separate.
   The display preserves imported row order; it does not establish a global
   execution order across distributed workers.
4. Open the rule's mainframe and Python references, its decision operands and its
   effect evidence. Preserve the distinction between an evaluation, a true
   condition and a committed action.
5. Follow the full trace and lineage references for all ancestors, descendants,
   join or aggregate contributors, field changes and transaction outcomes. A
   rejected or no-output record still requires a terminal reason and evidence.

The timeline uses one `FILTER` over `TraceEvents[#Data]`, including all detail and
metadata columns, with its calculated `Selected` column as the inclusion mask.
Keep its spill area
empty and unmerged. A spill error means the view cannot display its results;
it must not be interpreted as zero rule evaluations. An empty selection, an
unknown record, a declared zero-event record and missing event rows are different
states. Zero events are explainable only when the authoritative evidence supports
that result. Missing events never establish that a rule was not reached.

## Prepare and refresh evidence

Populate the named Excel Tables on Run Manifest, Record Index and Trace Events
from an approved, versioned export. The tables expand when rows are added within
their table boundaries; confirm the table range includes every imported row.
Manual refresh is required in this version. Keep a copy of the previous workbook
and its export manifest when replacing evidence.

Preserve both helper formula columns during imports; they are not imported
evidence. Fill their formulas through every new table row and verify recalculation:

| Sheet and column | Formula responsibility |
|---|---|
| Record Index, P — `Lookup key` | Combine the run ID's length, a colon, the run ID and record ID into an unambiguous lookup key. Empty identities produce an empty key. |
| Trace Events, U — `Selected` | Return 1 only when this row's run and record IDs match the nonblank Record Trace selectors and the selection identifies exactly one run and one index entry; otherwise return 0. |

Do not paste exported values over either helper column. Reapply the existing
formulas with row references adjusted when extending the tables. A difference
between the sum of `Selected` and the imported event count produces **Viewer
incomplete**. A missing `Lookup key` formula can instead produce a lookup error;
restore the formula before interpreting the view. Column U also appears at the
right of the spilled view as a diagnostic.

- **Run Manifest / `TraceRuns`** identifies the run, process, pinned fingerprints, independent
  input inventory, capture assessment, export coverage, closure report and full
  evidence location.
- **Record Index / `TraceRecords`** has one row per run and occurrence. It identifies intake,
  disposition, expected event memberships, the record capture attestation,
  closure and lineage receipts, and the full trace location.
- **Trace Events / `TraceEvents`** contains every exported event-to-record-version membership.
  It links the rule, outcome, operands, effects, source and target code, evidence,
  invocation, attempt, ordinal, causal parent and lineage.

| Table | Fields that bind the review |
|---|---|
| `TraceRuns` | `Run ID`, `Snapshot ID`, `Data origin`, `Fingerprints ref`, `Input inventory ref`, `Run capture`, `Export coverage`, `Closure report`, `Full evidence` |
| `TraceRecords` | `Run ID`, `Record ID`, `Snapshot ID`, `Capture assessment`, `Expected memberships`, `Membership receipt`, `Intake ref`, `Closure ref`, `Lineage ref`, `Record versions ref`, `Full trace ref` |
| `TraceEvents` | `Run ID`, `Record ID`, `Version ID`, `Event ID`, `Snapshot ID`, `Invocation ID`, `Attempt`, `Ordinal`, `Parent event`, `Lineage ref`, `Gap ref` |

`Record ID` means the opaque occurrence ID. Generate normalized UUID or ASCII
identifiers with consistent casing and no `*`, `?` or `~` characters: Excel
`MATCH` uses case-insensitive wildcard-aware comparisons. Require identifiers to
be unique after normalization. For example, `REC-A` and `rec-a` cannot represent
different records in this workbook. Do not use IDs that differ only by surrounding
whitespace. Apply the same convention to run and snapshot IDs.

The membership identity is run + occurrence + record version + event. An event
may belong to multiple contributing records; preserve every membership. Repeated
evaluations have distinct event identities. Do not collapse these relationships
into a comma-separated or truncated contributor list.

Refresh the tables as one consistent export. Match run IDs, occurrence IDs and
pinned source/build/rule-map/configuration versions across tables and references.
Check duplicate index keys, duplicate memberships, unmatched records, missing
receipts and unresolved links. Compare the actual membership set with the
authoritative export, not just its row count. The expected membership count must
come from the evidence producer, not from counting the same imported rows.

## Interpret completeness honestly

**Run capture** is the authoritative assessment against the independent input
inventory and required capture sites. **Record attestation** covers a specific
record's intake, invocation closure, evaluations, terminal state, effects and
lineage. **Workbook import completeness** describes which of those memberships
are present in this export. Spreadsheet formulas can identify inconsistencies;
they cannot certify the capture system or manufacture an attestation.
The view detects missing or ambiguous selections, absent expected counts, count
differences, missing required record-reference fields and inconsistent snapshot
IDs. A reference being present does not establish that it resolves or that its
receipt is valid. Duplicate event memberships, complete membership-set equality,
source fingerprints and causal relationships still require the linked evidence
checks. The message **Imported count matches** deliberately does not say complete.

A selected subset is acceptable for review only when its coverage is explicit and
every selected record's full evidence remains accessible. Do not silently cap
rows, omit records, sample events or label a partial export complete. If evidence
exceeds spreadsheet capacity, keep the canonical event and lineage tables in the
approved store and provide an explicit bounded export with a full-evidence link.
The runtime requirement remains a full trace for every processed record.
The prepared result formatting covers rows 23–1022, or 1,000 event rows; the
`FILTER` calculation is not capped to those rows. Extend formatting when needed
without placing values in the spill area. Any spreadsheet-capacity limit must be
disclosed before export.

Actual mainframe rule hits require actual legacy instrumentation. Mainframe output
parity and synthetic test results remain separate evidence; neither proves an
ordinary record's internal execution path.

## Demonstration and protected information

Rows labelled `DEMO` are fictional fixtures showing the review mechanics,
including partial or missing evidence. They are not PTS execution results or
proof of conversion. Replace them with an approved export before an actual review;
never mix demonstration assessments into acceptance totals.

Use opaque identifiers, authorized masked values and immutable evidence references.
Keep raw PII, credentials and protected source outside workbook exports and Git.
Links must resolve for the authorized reviewer to the exact retained evidence;
expired or inaccessible evidence remains visible as a gap. A hash identifies a
snapshot but cannot replace the evidence needed to explain a decision.

Workbook generation checks and rendered previews do not establish behavior in
native Excel. Native Excel execution was not available for verification; confirm
recalculation, the dynamic result area and evidence links in the supported Excel
version before using imported evidence for an acceptance decision.

The complete runtime contract is in
[Technical Reference, Section 9](TECHNICAL_REFERENCE.md#9-full-evidence-trace-for-every-processed-record).
