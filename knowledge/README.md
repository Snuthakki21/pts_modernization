# Mainframe knowledge you can inspect and extend

The workbench uses [mainframe-catalog.json](mainframe-catalog.json) to recognize
mainframe source and explain platform behavior. This is a versioned reference
catalog, not a list of supported converters. Recognition, human-confirmed
interpretation, implemented replacement and verified behavior are separate facts.
A recognized utility still blocks completion until its invocation has a tested
adapter and complete evidence.

## Where to put application knowledge

After setup, edit **`WORKSPACE/knowledge/application-knowledge.json`**. Setup copies
the empty [template](../examples/application-knowledge.json) only if that file does
not exist. This local file belongs to your application and remains private. Add
Markdown knowledge articles under **`WORKSPACE/knowledge/inbox/`**. The current
intake indexes up to 20 `.md` documents and 1 MiB combined, with bounded excerpt
retrieval. Original process notes are included in this shared limit. Keep
related material together instead of creating a file for each rule.

The standard catalog contains 17 classification categories, 17 utility families
and 11 topics covering source provenance, encoding, COBOL, JCL, datasets,
utilities, Db2, CICS, interfaces, synthetic data and assurance. It includes links
to IBM documentation. Those documents describe specific products/releases;
confirm the installed release, options and local modifications for each process.

The application file has this structure. The utility below is a **fictional
example**; replace it with your actual wrapper before using it:

```json
{
  "schema_version": 1,
  "application": "Referral application",
  "notes": [
    "Business date is supplied by the scheduler; do not substitute today's date."
  ],
  "utilities": [
    {
      "id": "APP_REFERRAL_MATCH",
      "name": "REFMATCH",
      "aliases": ["REFRUN"],
      "category": "application_wrapper",
      "behavior": "Matches referral records to eligibility records using an application key.",
      "required_evidence": [
        "Complete source and control cards",
        "Both file layouts and duplicate/unmatched-record rules"
      ],
      "risks": ["The same person can have more than one product record."],
      "references": ["Application operations guide section 4; supplied by owner"],
      "owner": "Referral application team",
      "version": "State the actual exported version or write Not yet confirmed",
      "record_formats": ["State RECFM/LRECL/CCSID for each input and output"],
      "return_codes": ["State success, warning and failure codes"],
      "side_effects": ["State each output, database change and external call"],
      "dependencies": ["List layouts, lookup files, tables and called programs"]
    }
  ]
}
```

All shown utility fields are required. Use `"Not yet confirmed"` for a fact you
cannot establish; it remains unresolved context. Names, aliases and IDs use
uppercase identifiers, with national characters `@`, `#` and `$` allowed.
Recognition of such names does not extend the target converter's identifier support. Duplicate names, duplicate JSON keys, aliases
that shadow a standard utility, unknown fields, symlinks and oversized files
are rejected. Do not add code, shell commands, executable adapters or fields
claiming a utility is converted. Free-text facts are review context and are never
executed or accepted as approval.

For a locally customized **standard** utility, retain its standard entry and put
the version/options/exit differences in `notes`, with a source reference. For a
separately named wrapper, add a utility entry. Record both the wrapper and the
underlying utility; the wrapper's behavior must be traced from its actual source.
For another vendor's `SORT`, document the actual product and dialect in `notes`;
the generic `SORT` alias is not proof that DFSORT is installed.

## How the information is used

At intake, the coordinator freezes the standard and application knowledge,
including content/source hashes, into the process evidence. Classification and
utility findings use that frozen snapshot. SME review includes the application
facts as **unverified context**. A later edit affects newly started processes;
it cannot change the interpretation, questions or evidence of an existing run.
Correct a process by starting a new process ID with corrected inputs.

Classification uses structural content, filename hints and dependencies. It can
recognize extensionless COBOL programs, referenced copybooks, JCL jobs,
procedures and includes. It also identifies BMS, DCLGEN/SQL, utility cards, REXX,
CLIST, PL/I, assembler, CICS resources and some scheduler signatures. Filenames
alone are insufficient. Conflicting types and unknown files remain visible and
block automatic completion. Classification is intentionally conservative and is
not a full compiler or vendor-independent parser.

Utility findings keep the job/step identity and source line when available.
Actual JCL `EXEC PGM=` invocations are checked even when omitted from the intake
manifest. The system does not execute a utility to find out what it does.

## What agents must account for

| Area | Required interpretation |
| --- | --- |
| COBOL | Complete source/COPY closure, compiler options, numeric representation, all branches, storage lifetime and error behavior. Unsupported constructs remain blocked. |
| JCL and procedures | Symbol/override expansion, DD bindings, step order, skipped steps, return codes, abends and restart. A true `COND` test commonly means bypass, so it must not be treated as an ordinary execute-if test. |
| Datasets | RECFM/LRECL/CCSID, record boundaries, significant spaces, packed/binary fields, VSAM keys, GDG generations, temporary datasets, concatenation and DISP effects. |
| IEFBR14 | Its program returns zero, but allocation/disposition around it may create or delete datasets. It is not automatically removable. |
| DFSORT/ICETOOL | Full sort/filter/join/reformat/control logic, record positions/types, duplicates, collation, exits and installed defaults. A sort step may implement business rules. |
| IDCAMS | Full command stream, catalog/VSAM attributes, REPRO semantics and MAXCC/LASTCC handling. DEFINE/DELETE or other writes are never run during discovery. |
| Copy utilities | IEBGENER/ICEGENER record editing and padding; IEBCOPY member selection, aliases and library/unload formats. They are not all ordinary file copies. |
| Command drivers | IKJEFT01 variants, Db2 DSN/RUN commands, BPXBATCH modes and IMS drivers require the nested program, parameters and environment. Driver recognition does not reveal the whole process. |
| Db2 | DDL, NULL indicators, exact decimals, CCSIDs, constraints, triggers, SQL error handling and transactions. SQLite tests establish only the implemented POC behavior. |
| CICS/BMS | Transaction/program/map bindings, validation, navigation, state and side effects. A screen definition alone cannot establish a replacement UI/API. |
| Custom utilities | Owner/version, complete source/control cards, layouts, dependencies, outputs, side effects, return codes and restart behavior. Unknown facts enter the one SME packet. |
| Verification | Source-derived expectations stay distinct from observed mainframe results. Source coverage, rule tests and exclusions use explicit denominators and evidence. |

Use the existing process workflow and its coverage gates. A knowledge entry never
turns missing source, unsupported semantics, unanswered review or failed tests
into a successful conversion. Mainframe access remains read-only, including when
investigating utilities whose normal purpose is to change data.

## Application routing and source-derived fixtures

WEBELX is a local/mounted input-availability location. Source-system files arrive
at Tran Repository for WEBELX/downstream steps. Put exact folder/file bindings in
`knowledge/input-locations.json` using [the template](../examples/input-locations.json).
Do not invent datasets from location names. Availability does not establish
layout, cutoff, completeness or business readiness.

Terminal routing hints supplied by the user are `TS0 DB2 2` for copybook/Db2
access, `SCHEDD` for development CA7 and UAT for CICS (exact location unconfirmed).
`SYSPL` is a JCL search hint. Actual Zowe service/profile/library mappings or
original exports are required; TPX session IDs are not API hosts. Record confirmed
application details together in the existing catalog notes/utilities with
provenance. Batch COBOL comes from Endeavor; JCL/PROCs may also be in actual
mainframe libraries.

Every applicable business/technical source logic item needs explicit validation.
New v5 process fixtures require at least 64 distinct randomized valid source logic states,
or 128 for recorded compound predicates, cross-layout compared keys and prior effects
that change predicate inputs. Frozen historical policies retain their original floors.
modeled outcomes/boundaries, invalid layouts and linked-group matching/mismatching
keys. Freeze expectations from source before target execution. Unsupported
numeric/file/Db2/CICS/utility semantics need reviewed adapters. Sample rows or
generic mock data cannot certify them; surviving mutations and unreachable or
undersampled obligations remain gaps.
