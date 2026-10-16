---
name: Conversion workspace
description: Professional, restrained styling for a local read-only conversion inventory.
colors:
  red: "#d71e28"
  red-dark: "#a5151e"
  gold: "#ffcd41"
  ink: "#3b3331"
  muted: "#625854"
  line: "#d7cfca"
  surface: "#fff"
  page: "#f9f7f6"
  warm: "#f4f0ed"
  focus: "#005a8b"
  selection: "#ffe59b"
  selected-row: "#fff7de"
  row-hover: "#fcfaf9"
  input-border: "#9a8d86"
  program-link: "#8f1720"
  error-surface: "#fff0ef"
  error-border: "#ca7775"
  status-neutral-text: "#514842"
  status-neutral-bg: "#ede8e4"
  status-positive-text: "#215c3c"
  status-positive-bg: "#e7f3eb"
  status-blocked-text: "#922029"
  status-blocked-bg: "#fbe9e8"
  status-pending-text: "#715008"
  status-pending-bg: "#fff2d0"
  status-progress-text: "#24536c"
  status-progress-bg: "#e6f0f6"
typography:
  display:
    fontFamily: "Georgia, serif"
    fontSize: "clamp(2rem, 3vw, 2.7rem)"
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: "-.02em"
  heading:
    fontFamily: "Arial, Helvetica, sans-serif"
    fontSize: "1.25rem"
    lineHeight: 1.35
  body:
    fontFamily: "Arial, Helvetica, sans-serif"
    fontSize: "14px"
    lineHeight: 1.5
  control:
    fontFamily: "Arial, Helvetica, sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.5
  label:
    fontFamily: "Arial, Helvetica, sans-serif"
    fontSize: ".85rem"
    fontWeight: 600
    lineHeight: 1.5
  status:
    fontFamily: "Arial, Helvetica, sans-serif"
    fontSize: ".78rem"
    fontWeight: 600
    lineHeight: 1.5
  metric:
    fontFamily: "Arial, Helvetica, sans-serif"
    fontSize: "1.85rem"
    lineHeight: 1.4
  code:
    fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: ".86em"
  wordmark:
    fontFamily: "Georgia, serif"
    fontSize: "1.55rem"
    fontWeight: 700
rounded:
  none: "0"
  status: "3px"
  control: "4px"
spacing:
  compact: "4px"
  small: "8px"
  control-gap: "12px"
  medium: "16px"
  section-small: "20px"
  section: "24px"
  heading-gap: "28px"
  section-large: "32px"
  desktop-gutter: "40px"
  page-bottom: "48px"
components:
  button-primary:
    backgroundColor: "{colors.red}"
    textColor: "{colors.surface}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "10px 18px"
  button-primary-hover:
    backgroundColor: "{colors.red-dark}"
    textColor: "{colors.surface}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "10px 18px"
  button-secondary-hover:
    backgroundColor: "{colors.warm}"
  button-text:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "8px"
  filter-field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
  workspace-navigation:
    backgroundColor: "{colors.warm}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
  status-positive:
    backgroundColor: "{colors.status-positive-bg}"
    textColor: "{colors.status-positive-text}"
    typography: "{typography.status}"
    rounded: "{rounded.status}"
    padding: "3px 8px"
  summary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "24px 28px"
  detail-content:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "22px"
---

# Design System: Conversion workspace

## Overview

The user-selected direction is a professional, restrained interpretation of the
Wells Fargo public-page reference. A red masthead, thin gold divider, warm neutral
surfaces and clear navigation support an independent conversion workspace. No
bank affiliation, proprietary font, logo or new brand metaphor is asserted.

The frontmatter is the normative token record extracted from
`ui/src/styles.css`, `ui/src/App.jsx` and `ui/src/ProgramDetail.jsx` on
16 October 2026. It describes implemented declarations, not browser-computed or
visually accepted results. Keep the CSS and this record synchronized. The current
browser QA result is **blocked**; see [the QA record](ui/design-qa.md).

**Key Characteristics:**

- Warm neutral surfaces with restrained red and gold accents.
- Readable tables, written statuses and adjacent evidence details.
- Native controls and small, direct components.
- Empty and fictional states clearly distinguished from application evidence.

## Colors

The primary palette follows the pinned public reference; state colors distinguish
recorded outcomes without replacing their written labels. Exact values live in
the frontmatter, not in a second palette.

| Role | Tokens and use |
|---|---|
| Primary | `red` for the masthead, import action, caret and current-navigation underline; `red-dark` for primary-action hover |
| Accent | `gold` for the masthead divider; `selection` for browser text selection |
| Neutral | `ink` for primary copy, `muted` for supporting copy, `surface` for content, `page` for the canvas and `warm` for navigation/table headers/footer |
| Boundaries | `line` for section and table dividers; `input-border` for field outlines |
| Interaction | `focus` for the visible focus outline; `program-link` for program buttons; `row-hover` and `selected-row` for inventory states |
| Notices | `selected-row` also fills the fictional-demo notice; `error-surface` and `error-border` distinguish import errors |
| Recorded status | Neutral for the fallback state; positive for completed/passed; blocked for blocked/failed; pending for stale/pending/unknown/unverified; progress for converted/in-progress/approved difference |

**The Recorded State Rule.** Every status keeps its text label. Accent color never
establishes acceptance, freshness or completeness by itself.

## Typography

Use the existing Arial/Helvetica body fallback and Georgia display accent. These
system stacks deliberately avoid downloading the reference site's proprietary
fonts. Keep readable sans-serif data text and the separate monospace reference
style; do not replace this pinned direction solely to satisfy a generic font warning.

The frontmatter records the page display, section heading, body, control, label,
status, summary metric, code and wordmark roles. Filter controls inherit the
label's smaller size and weight in the current CSS. Table headings use small
supporting text; numeric cells and summary values use tabular figures. Opaque
reference strings may wrap anywhere. Empty-state headings use Georgia at
`1.6rem`; detail headings use `1.3rem` sans serif. These are local component
variations rather than a separate type family.

Heading balance and browser font fallback are implemented declarations. Wrapping,
optical weight, text scaling and actual fallback rendering remain unverified.

## Layout

The desktop content and masthead share a maximum width of `1560px`. Main content
uses `32px 40px 48px` padding. The masthead inner region has a `75px` minimum
height plus its separate `4px` gold lower border; workspace navigation has a
`54px` minimum height. The six-column summary is a ledger separated by thin rules.

Filters use a wider search column and three selection columns. With a program
selected, the work area uses `minmax(0, 1.05fr) minmax(420px, 1fr)` with a `24px`
gap. Inventory and detail are flat, separately scrollable content regions. The
inventory table has a `560px` minimum width and a `760px` scroll-region maximum
height; the rule table has a `420px` minimum width. Detail content has a `720px`
maximum height on wide screens. Pagination shows up to 50 program rows per page.

| CSS breakpoint | Implemented behavior; browser verification pending |
|---|---|
| At or below `1150px` | Detail follows inventory in one column; detail height is no longer capped |
| At or below `800px` | Main gutters narrow, heading/actions stack, summary uses three columns and filters use two columns |
| At or below `480px` | Main gutters become `16px`, filters form one column, actions share available width and detail padding narrows |
| Minimum body width `320px` | Narrow-view target; table regions retain their own horizontal scrolling |

These rules describe source behavior. They do not establish absence of clipping,
page overflow, collisions or hidden controls at any viewport.

## Elevation & Depth

The implemented interface has no box shadows. Warm surfaces, white content,
one-pixel dividers and written headings establish grouping. The sticky table
header uses `z-index: 1`; the focus-revealed skip link uses `z-index: 10`.

The detail panel reveals through a short clip-path animation (`.18s ease-out`).
The reduced-motion query removes animation and sets automatic scrolling. Motion,
breakpoints and complete focus treatments are recorded in the schema-2 sidecar,
since the frontmatter component schema cannot represent them.

## Shapes

Content panels remain square. Controls have the small `control` radius and status
labels use the slightly smaller `status` radius. Detail-view buttons explicitly
use the `none` radius with a three-pixel current-view underline. This underline
is a navigation state, not an accent border attached to a rounded card.

The reference's pill-shaped marketing buttons are not copied into the working
table interface. The current small-radius controls are an intentional implemented
adaptation; visual fitness still requires the blocked browser review.

## Components

| Component | Implemented treatment and states |
|---|---|
| Primary action | Solid red Import snapshot button; darker hover; `44px` minimum height |
| Secondary action | White outlined button; warm hover; used for the fictional demo, filter recovery and pagination |
| Text action | Underlined text with a `44px` minimum height; closes detail or clears the demo |
| Filter fields | Native search/select controls, visible labels, outlined white fields; disabled before data loads |
| Navigation | Two workspace anchors with an explicit current-page underline; four detail-view buttons with `aria-pressed` state |
| Status label | Compact written status on a pale contextual fill; no icon-only status |
| Inventory table | Sticky heading, textual counts, row-hover fill and selected-row fill; a program button carries selected state |
| Detail panel | Overview, Rules, Evidence and Dependencies views; opaque evidence IDs rendered as text, not arbitrary links |
| Empty/error/demo | Distinct messages with recovery controls; imported errors retain the last valid view |

The shared focus treatment is a `3px` outline with `3px` offset; masthead links
use a white outline against red. Disabled controls use opacity `.6`. Program
buttons have a smaller `34px` minimum height, so the `44px` primary-control rule
must not be described as a verified universal touch-target guarantee. Detail-view
buttons use `46px` minimum height. These declarations and native keyboard controls
need interaction, zoom and accessibility checks in a rendered browser.

## Do's and Don'ts

### Do

- Do keep the user-selected red, gold and warm-neutral direction.
- Do keep status labels, denominators and evidence limits visible.
- Do use the existing system-font stacks, native controls and flat working surfaces.
- Do preserve distinct empty, fictional-demo, import-error and selected states.
- Do complete browser comparison and interaction checks before UI acceptance.

### Don't

- Don't copy bank logos, proprietary fonts, sign-on forms or affiliation claims.
- Don't add a decorative brand metaphor, marketing imagery or a component framework without a product need.
- Don't use color, a build result or a token extraction as proof of acceptance or accessibility.
- Don't describe an uncaptured desktop or mobile implementation as visually verified.
