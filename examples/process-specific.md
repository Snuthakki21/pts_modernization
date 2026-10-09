# Process-specific context template

Copy this file into one process's external authoring folder as
`process-specific.md`, beside its `manifest.md` and original `Endeavor/` export.
Replace bracketed fields with cited facts or `Unknown`. Delete inapplicable
sections only with a reason. This is background data, not an executable prompt,
a canonical manifest, saved scope, an SME return or evidence of conversion.
Keep secrets and all raw customer records/identifiers out of this file. Use only
synthetic or explicitly approved masked examples. Code/comments may contain PII;
identify approved sanitized source views and protected local original locations
without copying their values. Raw files are for deterministic local comparison,
not LLM reading, tool responses, screenshots/uploads or model APIs.

## Identity and applicability

- Process ID: [exact stable ID matching manifest.md]
- Process name and purpose: [actual owner/source-backed description]
- Environment: [actual system/subsystem, non-production or production; Unknown if absent]
- Source version and export time: [actual references, not an inferred date]
- Process owner and document provenance: [actual attribution and document/version references]
- Applicability: [products, partners, job/transaction scope; do not generalize one partner's rule]

## Entry points, order and dependencies

Record every known job/PROC/step/program or transaction/program/mapset/map in the
actual order. Include conditional execution, called programs, COPY/INCLUDE,
resources, scheduler triggers and external interfaces. Cite member paths and
line ranges or owner documents. Dynamic or ambiguous bindings stay Unknown.

| Order / branch | Entry / step / transaction | Program / object | Dependency or condition | Evidence |
| --- | --- | --- | --- | --- |
| [actual] | [actual] | [actual] | [actual or Unknown] | [source/version/span] |

## Inputs, outputs and data contracts

| Dataset / table / file | Input or output | Layout / keys / order | Null, decimal, encoding and identifier requirements | Evidence |
| --- | --- | --- | --- | --- |
| [actual] | [actual] | [RECFM/LRECL/CCSID, COPY/DDL, keys or Unknown] | [leading zeros, spaces, boundaries or Unknown] | [source/version/span] |

Record DD concatenation, GDG/DISP, duplicate/missing records and output routing
where applicable. Preserve original names and significant identifier formatting.
I* and Z* are separate environment identities until the actual binding is proven.

## Data meaning, quality and reliability

For each relevant table/file, document the grain (what one record represents),
actual keys and uniqueness, relationships/cardinality, units, valid values,
NULL/blank/zero meanings, source precedence and applicable time window. Cite
DDL/source spans or attributed owner definitions. Mark assumptions and missing
facts Unknown; an inferred key is not a verified constraint.

Record duplicate/missing/orphan rows, truncation/capped reads, stale snapshots,
encoding/precision concerns and what the evidence can reliably establish.
Distinguish observed values from inferred business meaning. Keep these facts in
this single document and the existing structured catalog; no per-table Markdown.

## Business and technical behavior

Describe source behavior with its exact product/partner/program applicability and
evidence. Separate business qualification from technical movement, sorting,
error handling and persistence. For referral matching, distinguish referral and
sale inputs; record the actual identity precedence, product mappings, employee
condition, dates/window boundaries, multiple-match policy and routing. Leave
unspecified rules Unknown; do not add policies because they seem reasonable.

| Behavior | Applicability | Source / document evidence | Known fact or unresolved question |
| --- | --- | --- | --- |
| [actual behavior] | [actual scope] | [source/version/span] | [fact or Unknown and exact missing evidence] |

## Platform-specific effects

Record applicable utilities/control cards, Db2 SQLCODE/transactions/isolation,
CICS/BMS fields/AID keys/navigation/state/security, VSAM/IMS/MQ/file operations,
return codes, abends, restart/recovery and external effects. Cite installed
version/options and linked objects. Recognition is not a verified replacement;
missing semantics remain specific gaps, not automatically unnecessary behavior.

## Preserved source issues and comparison basis

Record counterintuitive or defective legacy behavior with source evidence.
Preserve it during migration; proposed business changes need separate authority.
For database/output comparison, record input/run identity, before/after scope,
historical baseline, keys, completeness and consistency. Distinguish run deltas
from whole-table equality and observed mainframe parity. Reference protected local
comparison artifacts by path/hash, scope and aggregate counts only; never paste
raw rows here. State the masking/redaction limitations and exact unavailable
semantics rather than claiming a simple identifier regex protects every field.

## Local retrieval bindings

List only actual approved export/library/profile/location references and exact
WEDLX/Tran folder bindings when known. A TPX session hint is not a host or physical
path. Source retrieval uses read-only Zowe; Db2 evidence uses approved MCP through
Claude Code. It consumes accepted local returns for local implementation. Do not
put credentials here.

## Unknowns and evidence needed

| Affected object / behavior | Missing or conflicting fact | Relevant source / owner | Evidence needed |
| --- | --- | --- | --- |
| [actual] | [exact Unknown] | [reference or Unknown] | [specific export/definition/document] |

Context does not answer the human checklist or save conversion checkboxes. The
Coordinator preserves these notes as unverified indexed context; the original
source, explicit scope, actual human return and executed comparisons own their
respective facts. Changes affect a new intake, not an existing frozen process.
