---
name: mainframe-semantics
description: Explain source-grounded mainframe behavior and separate business decisions from technical logic, including COBOL, utilities, JCL, Db2 and native data semantics. Use when deriving rules or investigating unsupported constructs.
---

Follow the host-role boundary in
[the shared workflow](../../../prompts/START_MODERNIZATION.md). Claude Code grounds
semantics, rule classifications and architectural decisions in approved local
sanitized source views, catalogs and safe process evidence. Approved read-only
Db2 MCP/Zowe retrieval supplies missing evidence through exact request-bound
inboxes; Copilot is not required. Missing evidence is never an invented assumption.
Generic tests do not prove process parity.

Model-visible work uses metadata and explicitly approved sanitized source views.
Raw source/customer rows and SSNs stay protected locally; never put them in LLM
reads, MCP responses, prompts, screenshots/uploads, model APIs or diagnostics.
Code/comments are not inherently safe. Deterministic local tools may compare
protected files and return counts/hashes/gaps; use synthetic or approved masked
examples for tests. Missing safe semantic context stays a qualification gap.


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
safe pinned rule projection for large inventories; protected originals remain
local deterministic inputs.
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

For schema knowledge, cite grain, actual constraints/keys, relationship cardinality,
null/value meanings, precision, source precedence and completeness/consistency.
Keep source observations, owner statements and inferences distinct; absent facts
stay Unknown in the same context/catalog. Never infer a verified key from samples.
