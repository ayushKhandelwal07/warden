# Warden design system (locked)

The single source of truth for every screen. Chosen Fri Oct 16 and **locked until the end of the hackathon**. Every module's UI is built in this style from the start. We don't refactor the design after each module; there is one polish pass (Sat 23:00–01:30) that stays inside these tokens.

## Direction

Clean, type-led product UI: white page, near-black type, grey secondary text, hairline borders, pill buttons, and exactly one warm accent. Calm text at the top of a screen, dense real data below it.

References:
- kage.design "incredible-landing-page" for the design language (hierarchy, rhythm, colour discipline).
- minimal.gallery/tag/startup for whitespace and restraint.
- vibeprompts.dev patterns: agent run trace, approvals queue, command palette, empty states.

We adapt a landing-page language to an app; we never copy the reference product's name, copy, logo, screenshots, or badges.

Brief answers (the questions the Kage prompt asks first):
- **Product:** Warden, an agent that finds which vulnerabilities and changes actually put your system at risk, proves it with the path through a FalkorDB graph, and fixes them behind your approval.
- **Audience:** security and platform engineers, plus hackathon judges watching a 3-minute demo.
- **Brand:** name "Warden"; a simple geometric glyph (a shield cut by a path line) in the accent colour; Inter.
- **Primary action:** in the app, "Ask" (the question box) and "Sync"; in the README/video, "Watch the demo".

## Tokens

Defined once as CSS variables in `src/styles/tokens.css` and mapped into the Tailwind theme. **No other colours anywhere.**

| Token | Value | Use |
|---|---|---|
| `--bg` | `#ffffff` | Page |
| `--ink` | `#111111` | Text, primary buttons, status bar, headline |
| `--muted` | `#757575` | Secondary text, captions, axis labels |
| `--line` | `#d6d6d6` | 1px hairline borders, dividers, inactive graph edges |
| `--code` | `#f5f5f5` | Background of Cypher/code blocks only |
| `--tint` | `#faf6f2` | Faint warm wash behind the evidence stage only |
| `--accent` | `#ff4a00` | Logo glyph, evidence-path edges, "exploited in the wild" marker, focus ring. Never a large fill. |
| `--ok` | `#1a7f4b` | "Verified fixed" / "approved" status dot and text only |

Severity is monochrome, always with a text label (no red/amber/green traffic lights):

| Severity | Style |
|---|---|
| CRITICAL | Solid `--ink` pill, white text |
| HIGH | 1px `--ink` outline pill, ink text |
| MEDIUM | 1px `--line` outline pill, ink text |
| LOW / UNKNOWN | No border, muted text |
| KEV | Accent dot + "Exploited in the wild" in accent text (the only accent text) |

## Type

One grotesque sans: **Inter** (`@fontsource-variable/inter`). Mono: **JetBrains Mono** (`@fontsource/jetbrains-mono`) for Cypher, IDs, versions, and package keys. Self-hosted via npm, no font CDN.

| Role | Size / line-height | Tracking | Weight |
|---|---|---|---|
| Display (screen hero) | 56px / 1.04 | -0.03em | 600 |
| H1 | 32px / 1.15 | -0.02em | 600 |
| H2 | 20px / 1.3 | -0.01em | 600 |
| Body | 15px / 1.55 | 0 | 400 |
| Small | 13px / 1.45 | 0 | 400 |
| Mono | 13px / 1.5 | 0 | 400 |

Subcopy under a display headline: 18px muted, with the key sentence in ink, weight 600.

## Shape, space, motion

- 4px spacing base. Screen hero: ~96px top padding, 640px text column. App content max width 1200px.
- Pills (buttons, inputs, badges, chips): radius 999px. Buttons 44px tall (hero CTA 52px).
- Cards: radius 12px. Evidence window: radius 16px.
- Borders: 1px `--line`. No drop shadows, except one soft ambient shadow on the evidence window: `0 24px 60px -24px rgba(17,17,17,.18)`.
- Buttons step down in weight:
  - primary: solid ink pill, white text, icon
  - secondary: white pill, hairline border, icon
  - tertiary: text link
  - **At most one solid button per view.**
- Motion stays quiet: hover = opacity .85 or a slight darken; cards fade/scale in over 150ms. One allowed flourish: the evidence path draws itself once (stroke animation, ~600ms) when a Thread opens.

## Layout (app adaptation of the reference)

1. **Status bar** (top, 36px, ink background, 13px white text, centered): live graph status, e.g. `org_demo · 2,698 nodes · KEV feed 2026-10-16 · FalkorDB connected`, plus an inline "Open FalkorDB Browser →" link. Replaces the announcement bar.
2. **Header** (64px, no border): accent glyph + "Warden" wordmark at left. Centered nav: Ask · PR impact · Approvals (count badge) · Tools. One solid pill at right: "Sync".
3. **Screen hero** (Ask screen): centered 640px column.
   - Display headline built from live data, e.g. "256 vulnerabilities. One is exploited in the wild."
   - Two lines of subcopy, the second in ink and bold.
   - The ask input as a large pill, then a row of 3 suggested-question chips.
4. **Evidence stage** (the "product proof" area): a full-width window card on the `--tint` wash.
   - Window chrome: three small neutral `--line` dots, then the Thread title, then a "Cypher" toggle.
   - Inside: the path graph on the left; the Thread on the right (answer, claims, tool trace with ms, Cypher in mono, sources, policies applied).
   - Airy top, dense bottom.
5. **Tables:** hairline row dividers, 44px rows, no zebra stripes, mono for IDs and versions, right-aligned numbers.
6. **Empty / error states:** one muted sentence + one action. Never a blank panel.

## v3 shell (Oct 17): replaces the status bar and header above

- **Public pages** (`/`, `/login`, `/signup`): the dark announcement bar (36px, ink, white 12.5px) and a slim header with one solid "Get started" pill. The landing page shows the live demo graph inside window chrome.
- **App** (`/app/:project/...`): a claude.ai-style left sidebar, 272px with a 1px `--line` right border. From top to bottom it holds the logo and collapse button, the project switcher, a "New chat" secondary pill, the section links (Home, Ask, PR impact, Approvals with count, Tools, Sync), the recent list (chats, or PR analyses on PR impact) grouped Today / Previous 7 days / Older, then the graph status dot and the user menu. Below 1024px it's a drawer behind a 56px top bar.
- **Borders** are `--line` #d6d6d6 (strengthened from #e8e8e8 on Oct 17 so cards read on light screens).
- **List + detail** pages (Approvals) put a 340px list on the left and the detail on the right; on phones they become two pages with a back link.
- **Side panels** (evidence, tool runs) are right drawers on desktop and bottom sheets on phones.
- **Landing page** (Oct 17, modelled on the incredible.one layout, our content only): 75px/600 hero at -0.035em, 21px semibold muted subline with the key sentence in ink, 48px pills, a nav that morphs from full-width to a floating white pill on scroll, a pinned product window that grows as you scroll, a source marquee, scroll-lit paragraphs, a scroll-driven step story, a use-case carousel with count-ups, a live stats band, an auto-rotating feature panel, and a footer with a faded wordmark. Glows use only `--tint` and the accent at ≤16% alpha. All motion uses `cubic-bezier(0.32, 0.72, 0, 1)` and switches off under `prefers-reduced-motion`. No customer logos, testimonials or invented numbers: every figure is live from the demo graph or measured by the planner.

## Path graph (cytoscape)

- Layout: left to right, Internet → Ingress → services → package → vulnerability → KEV catalog.
- Nodes: white rounded rectangles with a 12px Inter label and a tiny mono type prefix (`NET`, `ING`, `SVC`, `PKG`, `CVE`, `KEV`, `DATA`, `TEAM`). Type is shown by prefix, not colour.
- Nodes on the evidence path get a 1px ink border; other nodes get a `--line` border. The KEV catalog node gets an accent border.
- Edges on the evidence path are `--accent`, 2px, with arrows. Other edges are `--line`, 1px. Edge label (`CALLS`, `DEPENDS_ON`, …) is 11px muted.
- Never render the whole graph: only evidence subgraphs and neighbourhoods.

## Never

- Colours outside the token table; gradients; neon "hacker" dark dashboards; red/green severity lights.
- More than one solid button per view.
- Drop shadows (except the evidence window).
- Mock or placeholder data on any screen (Rule 2: real FalkorDB data only).
- Copying the reference product's name, copy, logo, screenshots, or third-party badges.
- Redesigning outside the polish pass. New UI reuses the shared components (`Button`, `Pill`, `Card`, `Window`, `Table`, `SeverityBadge`, `KevBadge`, `PathGraph`, `CypherBlock`, `StatusBar`).
