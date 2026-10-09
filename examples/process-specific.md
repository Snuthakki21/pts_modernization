# Process

Process ID: replace-with-a-stable-id
Process name: Replace with the name people use for this process

## Jobs (in run order)

1. REPLACEJOB

## What this process does

Write in your own words. What starts it, what goes in, and what should come out?
Use `Unknown` when you do not know. Add more job names above in their run order.
The factory reads their JCL to discover steps, programs, copybooks, control cards,
CICS interfaces and database dependencies; you do not need to list them all here.

## What we should know

Add any known dependencies, conditions, product or partner rules, screens,
input/output names, source versions, owner references and expected results.
Distinguish facts from assumptions and cite evidence where you have it.
Keep identifiers as written, including leading zeros and I*/Z* prefixes.
Preserve existing behavior even if it appears wrong; describe the concern here.

## Missing details or questions

List anything you cannot answer. Missing facts are resolved from the supplied
Endeavor export first, read-only Zowe next, and approved Db2 MCP for Db2 evidence.
The factory asks you only for information it still cannot find.

<!-- Copy this template to WORKSPACE/Process.md and replace the two identity
values and REPLACEJOB. Put the full source export in WORKSPACE/Endeavor/ and the
approved certificates in WORKSPACE/certificates/. No separate manifest or notes
file is required. A single known entry job is enough to start discovery. For an
online-only process, replace the Jobs section with this table, using actual
transaction and program names; leave Mapset/Map empty if unknown:
| Transaction | Program | Mapset | Map |
| --- | --- | --- | --- |
| XXXX | PROGRAM | | |
Do not paste passwords, credentials, raw customer records, SSNs or private
values here. Source/comments are protected by default; model interpretation
requires an explicitly approved sanitized view. These notes are unverified
context, not instructions that override source, policy, selected scope or the
single actual human review. Original Process.md bytes are frozen on intake;
changes belong to a new process ID, never an existing process snapshot. -->
