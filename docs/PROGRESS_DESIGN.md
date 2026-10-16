# Progress interface design brief

Reading this as a conversion operations workspace for engineering leads and
SMEs, with a calm enterprise language derived from the supplied banking-site
reference. The interface prioritizes a readable inventory and adjacent evidence
detail rather than a grid of decorative cards.

## Reference and boundaries

The supplied public-page capture was inspected on 16 October 2026. Visible
observations include a red masthead, thin gold divider, warm pale navigation and
content surfaces, dark body text, and clear active-navigation indicators.
Public CSS research is documented in [REA design research](REA_DESIGN_RESEARCH.md).
This is an interpretation of observed public design, not an official Wells Fargo
design standard or affiliated product.

## Committed direction

| Element | Decision |
| --- | --- |
| Masthead | 75 px desktop height, red `#d71e28`, gold `#ffcd41` divider |
| Surfaces | White content, warm `#f9f7f6` and `#f4f0ed` supporting surfaces |
| Text | `#3b3331` primary; contrast-tested darker supporting text |
| Type | Arial/Helvetica body; Georgia page heading as an editorial accent |
| Structure | Header, compact navigation, inventory summary, filters, table and detail pane |
| State | Written labels and counts; color only reinforces state |
| Motion | Short detail reveal; reduced-motion preference removes it |
| Density | Compact working data, 44 px minimum primary control height |

The Taste landing-page skill excludes dashboards. Its landing-page patterns are
not applied here; its frontend UI engineering guidance informs semantics,
keyboard access, responsive layout and state design. Impeccable's craft floor
informs contrast, spacing, focus, empty/error states and restrained surfaces.

## Main surface

The inventory summary presents total programs and recorded completion in one
horizontal ledger, with a textual completion fraction. Search and process/status
filters sit directly above the table. The table exposes program, process,
recorded status, validated-rule counts and outstanding gates. A selected program
opens an adjacent detail pane without obscuring the inventory.

The pane has four views: Overview, Rules, Evidence and Dependencies. Textual
gates and rule counts remain readable without color. Evidence is displayed as
opaque identifiers, never opened as arbitrary external links. Details use only
the sanitized snapshot contract; raw source and processed customer records are
not accepted by the viewer.

## Responsive behavior and accessibility

At wide widths, inventory and detail share a two-column work area. At tablet
widths, detail follows the table. At 320 px, filters stack, summary wraps, and
the table has its own labeled horizontal scroll region without page overflow.
Buttons, selects, file input and search retain native keyboard behavior. Focus
is visibly outlined, selected rows have explicit state, headings are ordered,
and errors/status changes are announced. Color contrast must be checked on the
built page, not assumed from the palette.

## Functional boundaries

Import requires a bounded versioned JSON object and validates expected types.
React text rendering escapes imported strings. There is no HTML injection,
remote data fetch, browser storage, executable record control or arbitrary-link
navigation. The dev server defaults to loopback and exposes only the UI root.
The app displays recorded status honestly and never manufactures verification.

## Verification record

Build, import-contract tests, browser interactions and responsive checks are
recorded with the implementation evidence. Claims of a full accessibility audit
or absolute security require separate evidence and are not implied here.
