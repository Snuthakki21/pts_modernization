# Public-site design reference

Observed 16 October 2026. This is the source-backed design brief for the conversion
tracking interface. Public CSS and page structure inform the design; they do not
establish an approved Wells Fargo corporate design system or affiliation.

## Evidence and retained deliverable

Public HTML and CSS were retrieved from Wells Fargo and Wells Fargo Advisors with
HTTP 200. The findings below are source declarations, not browser-computed values.
The newsroom homepage returned HTTP 403 and was not bypassed.

A separate cloud-browser visit captured the public Wells Fargo homepage. The
[reference screenshot](design/wells-fargo-reference-20261016.jpg) is a 1348 × 926
JPEG captured on 16 October 2026, SHA-256
`07a317474eda5d8ad96e99077e52c2c2c88891a0a5ecc1cbd3a4f5d192743dab`.
It confirms the visible reference layout; it is not a rendered test of the new
tracker. No sign-in or form submission was performed.

[REA](https://github.com/morluto/rea) was used only as a temporary research tool.
Version 6.5.0 installed and its version/help commands ran; a site-capture attempt
failed because no Chrome-family browser was available and the official Chromium
download returned invalid/truncated ZIP data. No successful REA capture is claimed.
The reviewed repository commit was `1b97b0f3707b1cf78ac98bd4ae81638b33cc286f`.
The temporary runtime, source checkout, browser-download files, package manifests
and redistributed notices have since been removed. REA is not a dependency,
plugin, installation step or validation gate for this kit. Earlier install
receipts describe historical research, not the current branch contents.

The retained deliverable is this brief, its dated source references and the public
reference image. Raw research receipts remain local diagnostics, excluded from
commits. Agents should use this document and [the implemented design contract](../DESIGN.md)
without installing research tooling or loading full downloaded pages into context.

## Primary source register

| ID | Source | Retrieval | SHA-256 of retrieved bytes |
|---|---|---|---|
| WF-HTML | [Wells Fargo homepage](https://www.wellsfargo.com/) | HTTP 200; 124,156 bytes | `47321bbc87a69a1396dce868c56855e7f6917f5ca19f4a44fd48cde7b0bc8f2e` |
| WF-CSS | [Homepage stylesheet](https://www.wellsfargo.com/ui/css/homepage-ui/ps-homepage.64e2080ce97f4cefb1b5.css) | HTTP 200; 222,526 bytes | `428654e483b47116d113de6c7a24d1709f5387d3cde0d046142612e41086eb34` |
| WFA-HTML | [Wells Fargo Advisors homepage](https://www.wellsfargoadvisors.com/) | HTTP 200; 127,226 bytes | `5599b9b6bc8b115d17fb60424050b40f815eee0eadd7fb5e93cb1d527fd766a1` |
| WFA-CSS | [Advisors shared stylesheet](https://www.wellsfargoadvisors.com/css/shared.min.css?v=07.17.26) | HTTP 200; 194,178 bytes | `7c8e81ed7c0016963d66afb9a6f8056ab2137765af423592a16b331799d74fdb` |
| WFA-FONT | [Advisors font declarations](https://www.wellsfargoadvisors.com/font/fonts.css?v=1) | HTTP 200; 1,405 bytes | `1747df9f6efe8bc404baea4ad6ee9a1266b9041f84ae8289a386ec4a85afbff1` |

Sources are a dated representative sample, not exhaustive coverage of affiliated
sites. Dynamic HTML can change without a stylesheet filename changing. Preserve
new capture hashes when the references are refreshed.

## Observed design vocabulary

| Element | Source observation | Tracking UI application |
|---|---|---|
| Masthead | WF-CSS `.ps-masthead`: red `#d71e28`, 75px height, 4px gold `#ffcd41` bottom border | Compact red identity band with a thin gold separator; use the app's own name |
| Primary action | WF-CSS `.ps-actionbtn-primary`: red background, white text, 24px radius, 9px 16px padding | One clear rounded primary action per context; no red success state |
| Secondary action | WF-CSS `.ps-btn-secondary`: white background, 1px dark border, dark text | Quiet outlined controls for filtering, export and navigation |
| Text and surfaces | WF-CSS `.ps-message`: `#f9f7f6` surface, `#e2dede` border; common dark text `#3b3331` and `#141414` | Warm neutral workspace, dark readable text and subtle table dividers |
| Advisors surfaces | WFA-CSS `.background--offWhite`: `#f4f0ed`; `.background--darkBrown`: `#3b3331` | Restrained warm background and clear section contrast |
| Body type | WF-CSS custom Wells Fargo Sans with Arial/Helvetica fallback; WFA-CSS `html` uses WF Sans/Arial | Use system Arial/Helvetica; do not download or redistribute proprietary fonts |
| Editorial type | WFA-CSS headings use WF Serif/Georgia; `h1` 2.25em with heading line-height 1.3 | Georgia may distinguish the page title; data tables remain sans serif |
| Navigation | WF-HTML has header, utility navigation, product navigation, main and footer; WFA-HTML includes desktop/mobile navigation variants | Clear top-level overview, programs, evidence and ETL destinations; responsive navigation |
| Content hierarchy | Both pages separate a principal message from grouped actions and supporting sections | Lead with inventory/completion, then searchable program rows and evidence details |

These applications are design decisions for an engineering tool. They are not
statements that the public marketing sites contain a migration dashboard.
Do not copy banking sign-on forms, customer imagery, logos or product claims.

## Handoff to design and frontend agents

Use this table as the reference brief, alongside the product-design, Impeccable
and Taste guidance already available in the branch. Load only the relevant
guidance; the downloaded website source does not belong in every agent prompt.

1. Put **completed / total inventoried programs** in the first view, with an
   explicit timestamp, inventory completeness and denominator definition. Zero
   discovered programs is an empty state, not 100% completion.
2. Keep separate counts for implementation, validation, independent audit and
   acceptance. A code file existing must not imply a completed conversion.
3. Provide a dense, sortable program table with process, rule counts, stage,
   blockers, last evidence and next action. Show why a gate is blocked.
4. In the selected program, show mainframe rule/source references on the left
   and Python satisfaction/evidence on the right. Make record-trace and replay
   evidence reachable without exposing raw protected records.
5. Provide a read-only rule-removal planning entry point with the precise
   program/rule identifier. Follow `RULE_REMOVAL.md`; an interface must not
   silently delete shared logic or grant new execution permissions.
6. Show the single Sparkflows migration register and dependency readiness.
   Distinguish implemented Python ETL from a verified Sparkflows replacement.
7. Statuses need text labels and accessible contrast, keyboard focus, meaningful
   empty/error states and a responsive layout. Color alone is insufficient.
8. Render untrusted inventory/source strings as text. No remote tracking assets,
   external font calls, arbitrary HTML rendering or automatic credential access.
