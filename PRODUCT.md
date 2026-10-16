# Conversion progress workspace

## Product intent

Give modernization leads and SMEs one readable place to compare the complete
program inventory with recorded completion, inspect blockers, and locate the
rule, dependency, test and evidence gaps behind each program.

The operating kit remains agent first. This interface is a read-only view of a
sanitized progress snapshot. It does not start agents, run code, modify records,
approve conversions, or connect to a mainframe or database.

## Users and decisions

- A lead sees total programs, completed programs and work requiring attention.
- An engineer identifies an incomplete gate, dependency or validation quota.
- An SME reads recorded business questions without deciding technical conversion.
- An auditor sees evidence identifiers and the limits of recorded status.

Completion comes from the snapshot generator's defined gates. A status shown in
the interface is recorded evidence, not an independent certification. The
initial state is empty. A separate, clearly identified fictional demo explains
the interface without pretending any application has been converted.

## Required experience

Import a sanitized JSON snapshot, search programs, filter by process and status,
sort the inventory, and open a program detail pane. Show positive and negative
test counts per rule, gates, findings, dependencies and evidence references.
Keep total inventory distinct from filtered results. Invalid or oversized files
show a recovery message and preserve the last valid snapshot.

## Delivery assumptions

The minimal implementation uses the Product Design React and Vite prototype
template with native browser controls and CSS. Data stays in browser memory and
is cleared on reload. There is no authentication or backend because this build
is a local read-only viewer. Shared hosting or live data access requires its own
access-control and deployment review.

## Visual direction

Use the supplied Wells Fargo reference and separately captured public site
observations as visual research: a red masthead, thin gold rule, warm neutral
surfaces, clear navigation, understated typography and strong table hierarchy.
Do not copy logos, proprietary fonts, marketing content or imply bank ownership.
The product name is Conversion workspace. Details are in
[the design brief](docs/PROGRESS_DESIGN.md).
