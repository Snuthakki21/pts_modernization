# Conversion workspace

Local read-only inventory viewer. From this directory:

```sh
npm ci --ignore-scripts
npm run build
npm test
npm run dev
```

The development server binds to loopback. Open its displayed local URL. Import
the sanitized JSON produced by `tools/progress_snapshot.py` from the repository
root. The viewer does not accept original inventory or customer-record files.
It keeps data only in memory; reload clears it. **Load fictional demo** explicitly
loads illustrative data. Displayed status is recorded, not independently verified.

The built static site is in `dist/client`. Template Sites handoff files remain
present, but this task does not deploy the site. Do not publish imported snapshots
or source data. Shared hosting needs access control, restrictive response headers,
and a separately reviewed deployment. Hot reload is disabled so the CSP can keep
scripts restricted to the same origin without an inline React refresh preamble.
Refresh the page after local edits. The application itself makes no data requests.

No runtime plugin, model, mainframe or database credential belongs in this UI.
Evidence references remain text; the viewer cannot open arbitrary file paths or
URLs. File size is capped at 8 MiB. Import schema checks bound collections, validate
identifiers and reject additional fields. Invalid input leaves the previous
snapshot intact.
