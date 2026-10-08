---
name: mainframe-semantics
description: Explain source-grounded mainframe behavior and separate business decisions from technical logic, including COBOL, utilities, JCL, Db2 and native data semantics. Use when deriving rules or investigating unsupported constructs.
---

Follow the host-role boundary in
[the shared workflow](../../../prompts/START_MODERNIZATION.md). Claude Code grounds
semantics, rule classifications and architectural decisions in approved local
source, catalogs and process evidence. Copilot only retrieves requested files or
metadata using approved MCP connections. Claude has no MCP access. Missing local
evidence becomes a request-bound retrieval prompt, not an invented assumption.
Generic tests do not prove process parity.

Use [the knowledge catalog](../../../knowledge/mainframe-catalog.json) and
[technical contract](../../../docs/TECHNICAL_REFERENCE.md). Load relevant topics
and product/version primary references progressively. Catalog recognition is not
implementation support. Keep reusable application facts in the one application
catalog; preserve each process's frozen knowledge on Resume.

Trace business outcomes through the complete control/data flow, not a list of IF
statements. A business rule describes a domain decision/calculation/validation.
Technical logic describes execution mechanics. IF can express either. Submit
rule_classifications for frozen rule IDs with category business_rule,
technical_logic or unclassified and an evidence-based reason. Read the complete
pinned local rule catalog for large inventories.
Explicit rule_classification_defaults can classify a program’s extracted decisions
when the same category applies; per-rule exceptions override the default. Unparsed spans stay
unclassified; do not turn each unsupported line into a supposed business rule.

Preserve evidenced behavior even when the source design appears incorrect.
Document suspected legacy defects and their consequences in existing structured
analysis; do not substitute intended or preferred behavior for what the source
does. Record exact source versions/spans and unresolved interpretation. Apply
the technical contract's Legacy behavior fidelity section; a functionality-specific
Db2/mainframe operation without a verified equivalent remains a named gap.

Before interpreting behavior, establish applicable semantics:
- COBOL: compiler/options, paragraph fall-through, PERFORM ranges, nested decisions,
  CALL/CANCEL and storage lifetime, condition names, REDEFINES/OCCURS, reference
  modification, signs, decimals, COMP/COMP-3, rounding, truncation, overflow.
- Files: CCSID, RECFM/LRECL, record padding, collating order, VSAM access/key/status,
  duplicate/missing records, DD concatenation, temporary files, GDGs and DISP.
- JCL/utilities: PROC expansion, symbols, COND bypass, IF/RC/abend, allocation and
  restart. IEFBR14 can have allocation side effects. DFSORT/ICETOOL controls can
  encode business logic. IDCAMS MAXCC/LASTCC matters. Trace IKJEFT01/DSN/RUN,
  BPXBATCH, IMS drivers and site wrappers; confirm vendor dialects and exits.
- Db2: DDL/types, decimal/null semantics, host/null indicators, SQLCODE/SQLSTATE,
  cursors, collation/CCSID, dates, isolation, commits/rollback, locks, constraints,
  triggers and procedures. SQLite differences require explicit replacements.
- Online/interfaces: CICS AID/maps/COMMAREA/channels, session and transaction state,
  IMS/MQ delivery/retry behavior, authentication, acknowledgments and idempotency.

Investigate supported equivalents, reusable adapters and feasible replacements
before recording a blocker. Specify missing evidence and tested alternatives;
never claim universal mainframe coverage or use an SME answer to implement code.
