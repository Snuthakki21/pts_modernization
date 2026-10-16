# REA license and dependency provenance

- Upstream: https://github.com/morluto/rea
- Reviewed source commit: `1b97b0f3707b1cf78ac98bd4ae81638b33cc286f`.
- Installed release: npm `rea-agents@6.5.0` from the official registry.
- Package integrity: `sha512-C6BG7LyrAdR74mSjertM6PrxJkcNZ2bfQNOJornPo9erDEp2tyPRVYPnV5Yodr+1RqewCQla68WulXlVnveD+A==`.
- REA-authored license: MIT; exact published `LICENSE` preserved here.
- Published `THIRD_PARTY_NOTICES.md` preserved unchanged. Referenced dependency
  licenses are included in the installed package and its dependencies; they are
  not replaced by REA's MIT license.
- Tracked install: `tools/rea/package.json` and `tools/rea/package-lock.json`.
- Lock SHA-256: `2aa8deaa749593ad20096d088c583079e7e0dbe4298d883836e57029692ba2da`.
- Root manifest is private and contains only exact `rea-agents: 6.5.0`.
  Transitive package entries and integrity fields are copied unchanged from the
  actual isolated installation. Only local root package naming differs.
- No upstream application source, node_modules, binaries or proprietary browser
  assets are vendored into this branch.

`LICENSE` SHA-256: `798f9e4d18e49b30bf2f12696c8ced73dc4e1413da375a333d01281543a1ea8b`.
`THIRD_PARTY_NOTICES.md` SHA-256: `43e579cc53ead3b9ebe1ca78b594bf8acabd341eab8065194e4226bc11d0ac12`.

On 16 October 2026, `npm audit --omit=dev --omit=optional --json` against the
installed production dependency graph exited 0 and reported zero known
vulnerabilities. Optional dependencies were omitted from execution. This is a
dated registry advisory check, not proof of complete security or coverage of
all possible vulnerabilities. Preserve review gates before updating the pin;
never use a forced audit fix to silently change approved versions.

See ../../REA_DESIGN_RESEARCH.md for execution receipts and the browser-capture
limitation. REA CLI execution does not imply installation into the user's VS Code
MCP configuration.
