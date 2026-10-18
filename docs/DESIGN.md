# Design

LocalPDF Hub should feel like a small native utility, not a web page:
closer to macOS Preview or Things 3 than to a landing page. Tools live in a
sidebar, the work area is wide and quiet, and colour is spent only on what
the user can act on. The colours stay those of 3.x, so existing users still
recognise the app.

## Layout

- **Sidebar** (240 px): app name, then the tools as a list, each with its icon.
  The selected tool has the accent background tint and a 3 px accent bar.
- **Work area**: tool title, the drop zone (or the file list once files are
  added), the tool's options, and one primary button at the bottom right.
- **Below 768 px** the sidebar becomes a tool picker above the work area.
- No hero section, no cards grid, no footer. Settings and About open in a
  dialog from the bottom of the sidebar.

## Type

IBM Plex Sans (SIL OFL 1.1), bundled from `@fontsource/ibm-plex-sans` so the
app works offline. Weights 400, 500 and 600 only.

| Use | Size / line height | Weight |
|---|---|---|
| Tool title | 24 / 32 | 600 |
| Section label | 14 / 20 | 600 |
| Body, controls | 14 / 20 | 400 |
| Secondary text | 13 / 18 | 400 |
| File sizes, page counts | 13 / 18, tabular figures | 400 |

## Colour

The palette of 3.x, kept: the same blue `#2B6CEE`, the same backgrounds and
the same slate greys. Where a 3.x colour failed WCAG 2.2 AA as text, the
nearest darker shade of the same hue replaces it.

| Token | Light | Dark | Use |
|---|---|---|---|
| `bg` | `#F6F6F8` | `#101622` | window |
| `surface` | `#FFFFFF` | `#1A2235` | work area, dialogs |
| `sidebar` | `#EEEFF3` | `#141B2B` | sidebar |
| `divider` | `#E2E8F0` | `#334155` | decorative lines only |
| `control-border` | `#7A8598` | `#64748B` | inputs, checkboxes, drop zone |
| `text` | `#0F172A` | `#F1F5F9` | text |
| `text-muted` | `#475569` | `#94A3B8` | secondary text |
| `accent` | `#2B6CEE` | `#2B6CEE` | primary button, selection bar, active icon |
| `accent-text` | `#2160DA` | `#7EA6F7` | links and accent-coloured text |
| `accent-hover` | `#2259CC` | `#2259CC` | primary button on hover |
| `on-accent` | `#FFFFFF` | `#FFFFFF` | text on the accent |
| `danger` | `#DC2626` | `#F87171` | errors |
| `success` | `#047857` | `#34D399` | success messages |

Every text pair passes AA (4.5:1). The tightest are white on the accent
(4.69:1) and `accent-text` on `sidebar` (4.87:1). Hover darkens the
button (6.23:1): a lighter blue would drop below 4.5:1. `control-border`
passes the 3:1 non-text minimum on all three backgrounds. The 3.x green
(`#10B981`, 2.54:1 on white) and red (`#EF4444`, 3.76:1) were too light
for text. `divider` is below 3:1 on purpose and must never be the only edge
of a control.

## Space, shape, depth, motion

- Spacing scale: 4, 8, 12, 16, 24, 32, 48 px. Nothing in between.
- Radius: 6 px on controls and the drop zone, 10 px on dialogs. Lists and
  the sidebar are square.
- Shadows only on dialogs and menus (one soft shadow); everything else is
  separated by background colour.
- Motion only shows a change of state: something arrives, moves, finishes
  or is working. Hover, selection and dialogs ease over 150 ms; a new file
  row or thumbnail fades in over 200 ms; the result card and its check
  draw in over 250 ms, the longest anything takes. Rows and the sidebar
  bar slide to their new place (FLIP); switching tools fades the work area
  in over 150 ms. Curve `--ease-out` (`cubic-bezier(0.2, 0, 0, 1)`), and
  only `opacity` and `transform` move.
- Nothing animates on page load, and with `prefers-reduced-motion` nothing
  moves at all: the progress bar becomes a still strip.
- Animations are named `lpdf-*`. The CSP forbids inline styles, so script
  animates with `element.animate()` or `element.style`, never with
  `setAttribute("style")` or `style.cssText`.

## Icons

- Phosphor (`@phosphor-icons/core`, MIT), *regular* weight, 20 px in the
  sidebar and 16 px inline, coloured with `currentColor`.
- Tool icons with no good Phosphor match are drawn for this app on
  Phosphor's 256-unit grid with its 16-unit round-capped stroke, so they sit
  next to the others without standing out.
- Only the icons in use are copied into one SVG sprite at build time.

## What we avoid

- Gradients, glass blur, glow and coloured shadows.
- A different colour per tool.
- Inter as a stand-in for a font decision, emoji in the UI, and copy that
  sells ("powerful", "seamless", "blazing fast").
- Animations that only decorate.

## Accessibility

- Visible focus ring: 2 px `accent` outline with a 2 px offset.
- Targets at least 24 x 24 px; sidebar rows 36 px tall.
- Everything works from the keyboard, including reordering files.
- Progress and errors are announced (`aria-live`); dialogs use `<dialog>`.
