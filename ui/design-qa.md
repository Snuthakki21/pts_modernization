# Conversion workspace design QA

final result: blocked

Recorded 16 October 2026. Source-reference inspection and code extraction are
available. No browser-rendered implementation capture is available, so this is a
blocked QA record, not a completed visual comparison or an accepted UI handoff.

## Findings

- **[P1 — QA blocker] The implementation could not be opened in the available browser.**
  Location: local preview/browser connection. Evidence: the preview attempts below
  did not provide a reachable rendered app. Impact: typography, layout, responsive
  behavior, interaction states and console health cannot be judged against the
  reference. Required resolution: capture and exercise the existing app in the
  user's approved VS Code host, then perform the comparison and continuation checks.
  This severity describes the acceptance blocker; it is not a fabricated visual defect.

Visual comparison findings remain **unassessed**. No P0/P1/P2 visual mismatch is
invented from source code, and absence of comparison findings is not a pass.

## Evidence and comparison conditions

| Field | Observed status |
|---|---|
| Source visual truth | [docs/design/wells-fargo-reference-20261016.jpg](../docs/design/wells-fargo-reference-20261016.jpg); opened and inspected |
| Source pixels | **1348 × 926**, JPEG; measured from the image file |
| Source SHA-256 | `07a317474eda5d8ad96e99077e52c2c2c88891a0a5ecc1cbd3a4f5d192743dab` |
| Source CSS viewport / device scale | Not independently recorded; pixel dimensions are not a claimed CSS viewport |
| Source state | Public Wells Fargo marketing/home page with a red masthead, gold divider and navigation; no authenticated banking state inspected |
| Implementation | `ui/src/App.jsx`, `ui/src/ProgramDetail.jsx`, `ui/src/styles.css`; code inspected, rendered app unavailable |
| Implementation screenshot path | **Unavailable — no successful browser capture** |
| Implementation viewport / pixel dimensions / CSS size / density | **Unverified** |
| Implementation states | Empty, fictional demo, import, filters, table/detail and responsive states exist in source; none browser-verified here |
| Density normalization | Not performed; no implementation image exists to normalize |
| Full-view comparison | Not performed; no combined source/implementation comparison input exists |
| Focused-region comparison | Not performed; masthead/navigation, text/controls and inventory/detail require matched rendered captures |
| Primary interactions tested in browser | None |
| Console errors checked on rendered app | Not checked; navigation failures are preview evidence, not an app-console result |

The source is a style reference for an independent operations workspace, not a
pixel-identical banking screen. Its logo, sign-on form, marketing copy and imagery
are intentionally outside this product's scope. This intention does not establish
the quality of the unrendered implementation. The reference capture is preserved
at the portable repository path above; the hash identifies the inspected bytes.

## Preview blocker history

The implementation session recorded these attempts. None is a design-QA iteration:

| Attempt | Recorded result |
|---|---|
| Sites preview start | Failed because `/tmp/sites-previewd/requests` was absent |
| Documented preview-daemon start | Could not create `/tmp/sites-previewd` in this environment |
| Direct Vite, `0.0.0.0` | Failed with `uv_interface_addresses` |
| Direct Vite, `127.0.0.1` | Server started, but browser access through `cloudterminal.local` returned `ERR_CONNECTION_REFUSED` |
| Python static server, `0.0.0.0` | Server started, but the cloud-browser route was also refused; the server was stopped |

No further detector run or style-polishing pass was performed for this record.
Build or terminal success cannot supply the missing browser capture.

## Required fidelity surfaces

| Surface | Status and evidence still needed |
|---|---|
| Fonts and typography | **Unassessed visually.** Confirm Arial/Helvetica fallback, Georgia display role, weights, line heights, small data text, wrapping and zoom in the actual browser |
| Spacing and layout rhythm | **Unassessed visually.** Compare masthead, navigation, gutters, ledger, filters, table/detail proportions and scrolling; check all breakpoints |
| Colors and visual tokens | **Unassessed visually.** CSS values are documented in `DESIGN.md`; rendered balance, disabled states, selection and focus require capture |
| Image quality and asset fidelity | **Unassessed for the implementation.** Source JPEG inspected; this app intentionally uses no copied bank logo, photo or marketing artwork. Confirm the rendered app respects that scope |
| Copy and content | **Unassessed in rendered context.** Confirm labels, demo notice, errors, counts and evidence limitations fit and read coherently in every state |

Keyboard reachability, focus return, mobile interaction, reduced motion, text
scaling, tap targets and actual screen-reader announcements remain unverified.

## Limited static checks

The existing single Impeccable detector pass produced two warnings:

| Warning | Code-based disposition; not a visual acceptance result |
|---|---|
| Arial is overused | Retain the user-pinned reference fallback. The source research and product brief deliberately use Arial/Helvetica without proprietary font downloads |
| Accent border on a rounded component | The reported `.detail-tabs button` uses a `3px` lower state border and explicitly sets `border-radius: 0`; it is a navigation underline, not a rounded card. Acceptable detector false positive on code inspection |

The following contrast ratios were calculated from the opaque CSS color pairs
using relative sRGB luminance. They were not sampled from a rendered page:

| Pair | Ratio |
|---|---|
| Main text on page | 11.54:1 |
| Supporting text on white / warm | 6.90:1 / 6.09:1 |
| White primary-action label / hover label | 5.11:1 / 7.70:1 |
| Neutral / positive status text on its fill | 7.33:1 / 6.92:1 |
| Blocked / pending / progress status text on its fill | 7.28:1 / 6.61:1 / 7.18:1 |
| Focus blue against white | 7.41:1 |

These selected pairs do not establish full accessibility. They do not test
composited disabled opacity, every foreground/background adjacency, effective
focus visibility, text size, browser rendering or keyboard behavior.

## Comparison history

**Zero visual-comparison iterations.** The source image was opened, but the
implementation could not be captured. No before/after visual fixes or post-fix
comparison evidence exist. Preview troubleshooting and static token extraction
must not be counted as completed comparison passes.

## Open questions

There is no unresolved aesthetic choice requiring another user interview. The
direction is already pinned. The remaining question is whether the implemented
interface meets that direction and its interaction contract when rendered in the
existing approved host. That requires the missing evidence below.

## Continuation checklist — existing VS Code host

1. [ ] Use the repository's existing UI run instructions in the approved VS Code
   host. Record commit, browser/version, URL, CSS viewport and device scale; do
   not introduce a new runtime or deployment just to bypass this preview failure.
2. [ ] Capture the initial empty view and the clearly labeled fictional demo.
   Confirm empty totals never imply completion and demo data remains visibly fictional.
3. [ ] Import a valid sanitized snapshot, then invalid and oversized files.
   Confirm recovery messages, busy/disabled state and preservation of the last valid view.
4. [ ] Exercise search, process/status filters, sort, no-match recovery and
   pagination. Confirm filtered counts remain distinct from the total inventory.
5. [ ] Open and close program details; inspect Overview, Rules, Evidence and
   Dependencies. Confirm recorded status and positive/negative quota counts,
   long reference wrapping, dependency gaps and close-focus return.
6. [ ] Complete a keyboard-only pass: skip link, actions, file import, filters,
   program selection, detail-view buttons, close action and scroll regions.
   Inspect focus visibility, labels, announcements and disabled-control behavior.
7. [ ] Check desktop plus widths around `1150px`, `800px`, `480px` and `320px`.
   Exercise mobile controls, touch targets, long strings, table scrolling,
   200% zoom and reduced motion; confirm persistent controls are not clipped.
8. [ ] Save implementation screenshots for the tested states and inspect browser
   console errors. Record actual outcomes and evidence paths, including failures.
9. [ ] Place the source and implementation captures in one comparison input,
   normalize viewport/density where justified, and inspect full views plus readable
   focused regions. Record each of the five fidelity surfaces. Fix actionable
   P0/P1/P2 findings, recapture and recompare before changing the final result.

## Follow-up polish

None assessed. No further style changes are proposed without rendered evidence.

final result: blocked
