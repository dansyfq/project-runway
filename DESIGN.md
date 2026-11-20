# Runway — DESIGN.md

Locked design direction for every Runway page. Do not invent per-page colours, fonts or spacing; change this file instead.

## Direction
- **Style:** warm editorial real-estate, built the Apple way. Real HDB photography, one hunter-green accent, the system font, surfaces separated by fill and soft elevation rather than outlines, dense content blocks.
- **References:** LVIM Bank (section rhythm, raised middle card), Real Estate Property app (steppers, chips, square icon buttons), Trade Estate / VillaVox boards (photo-led cards, bento product demo).
- **One idea per section.** Hero = Ask Runway. Nothing else competes in the hero.
- **One layout idea per page, one style per site.**

## Colour (one accent)
| Token | Light | Dark | Use |
|---|---|---|---|
| `--page` | `#FDFEFD` | `#0E1714` | page background (body, nav, app bar, composer bar) |
| `--snow` | `#FDFEFD` | `#1A2722` | raised cards, sheets, floating map controls; text on the green accent |
| `--beige` | `#E7DBC5` | `#3A3327` | beige buttons, tags, rule and source boxes inside a beige-2 bubble, "23 more towns", flowchart questions |
| `--beige-2` | `#F4EDE0` | `#222F2A` | grouped fills: bands, rows, lists, tiles, notices, the assistant's chat bubble, the upload card, empty states |
| `--beige-deep` | `#C9B892` | `#5E5442` | switch tracks, the empty-state mark, hand-drawn marks |
| `--field` / `--field-alt` | `#F4EDE0` / `#FDFEFD` | `#2B3833` / `#2B3833` | text fields and selects; `-alt` for a field that sits on a beige-2 fill |
| `--tint` / `--tint-2` | green at 10% / 16% | green at 12% / 18% | secondary buttons, chips, quick picks (`-2` on hover and press); translucent, so they work on any fill |
| `--fill-press` | `#EDE3D1` | `#2F3128` | hover and press on beige-2 rows and lists |
| `--green` | `#023933` | `#8DD0B3` | **the accent**: buttons, links, headings, selected states |
| `--green-deep` | `#012A26` | `#ADE0C9` | hover and pressed state of the accent |
| `--green-mid` | `#0F6B4F` | `#86D1A9` | full-CPF chip text only |
| `--ink` | `#14201C` | `#ECE6DA` | body text |
| `--ink-2` | `#4D5A55` | `#B3ADA1` | secondary text (≥4.5:1 on every surface above) |
| `--line` | `#E2D9C8` | `#2C3833` | hairlines, only where nothing else separates (see Shape) |
| `--ok` / `--ok-soft` | `#0F6B4F` / `#DCEBE3` | `#86D1A9` / `#173A2C` | CPF verdict semantics only, never decoration |
| `--part` / `--part-soft` | `#8F5509` / `#F8EAD4` | `#E6B26A` / `#3B2D17` | 〃 |
| `--no` / `--no-soft` | `#4D5A55` / `#EDE6D8` | `#B3ADA1` / `#2A332E` | 〃 |

**Brand surfaces** keep one look in both themes (they are already dark): the hero, the grainy green surfaces, the map hint and toasts.

| Token | Both themes | Use |
|---|---|---|
| `--brand` / `--brand-deep` | `#023933` / `#012A26` | large green surfaces, photo-credit chips, the runway strip |
| `--on-brand` | `#FDFEFD` | text on brand surfaces and photos (lighter tints are mixes of it, never alpha over a photo) |
| `--brand-hi` | `#E7DBC5` | beige accents on brand surfaces: the second half of the hero headline, scribbles, focus ring, current footer link |
| `--sign` | `#F2C230` | runway markings, the plane and lit windows in the building drawing only |

**Map colours** (`--land`, `--land-edge`, `--pa-line`, `--road`, `--road-edge`, `--block`, `--block-edge`, `--water`, `--mrt-case`) are defined per theme in the stylesheet; the map reads them when it draws and redraws when the theme changes. MRT line, amenity and chart series colours are data colours and stay the same in both themes: in dark mode MRT lines get a light `--mrt-case` casing, because several line colours fall under 3:1 against any dark ground.

Rules: no second accent, no purple, no glowing buttons. Gradients appear in two places: the hero's legibility scrim over the photo (no grain there), and the grainy gradient on green surfaces (footer, question band, green cards): a soft sage glow (25% at its brightest) around a dark disc with still film grain, kept dark enough for snow and beige text at 4.5:1 at the glow's brightest point.

## Dark theme
- Light is the default and the brand's theme. "Dark mode" is a button in the nav (sidebar and drawer) with `aria-pressed`; the choice is kept in the browser under one key, `runway-theme`, and nothing else is ever stored. The attribute `data-theme` is set on `<html>` before the first paint.
- Dark mode only redefines tokens (`:root[data-theme="dark"]`), never component rules. Deep green-black page, slightly lighter cards, warm off-white text, the same single green accent lightened, beige darkened as the secondary fill. On the accent, text uses `--snow`, so a green button is light sage with dark text in dark mode.
- Contrast bars are the same as light: 4.5:1 body and small text, 3:1 large text and essential graphics.

## Type (one face)
- **The system font everywhere** (San Francisco on Apple devices): `--font-ui` = `system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`. `--font-display` points at the same stack, so headings stand out by size, weight, tracking and colour, never by a second face. `font-optical-sizing: auto`. No italics as a device: the hero's "what buyers need to know." is set apart by its beige colour.
- **Scale** (size / leading / tracking): hero h1 42–78px / 1.04 / −0.03em; section h2 32–48px / 1.08 / −0.03em; big numbers 52px / 1 / −0.03em; inner h1 34px / 1.1 / −0.02em; h2 and 24–32px numbers / 1.2 / −0.02em; h3 and 18–23px sentences / 1.3 / −0.01em at 600; body 17px / 1.5 / 0; small 14px / 1.45 / +0.01em; labels 12px / 700 / +0.01em in sentence case. Leading tightens as size grows; hierarchy comes from weight + size + leading together. Tokens: `--track-display`, `--track-title`, `--track-heading`, `--track-small`.
- Two text tiers, in rem so Text size scales them: normal text 17px (`.944rem`, 400) for paragraphs, nav items, inputs, breadcrumbs and messages on every page; small 14px (`.778rem`) for notes, captions and credits. Buttons and big numbers keep their own sizes. Weights 400 to 700; nothing heavier.
- **Wordmark only:** Anton (RUNWAY), the one font loaded from Google Fonts.
- Numbers: `font-variant-numeric: tabular-nums` everywhere a number can change.
- Sentence case for labels and buttons. Caps only for the wordmark. Inner pages size type in rem so Text size scales them: its slider sets normal text from 14 to 24px (root size = px ÷ .944), for the visit only.

## Spacing & shape
- 8px grid. Section padding 80px (desktop) / 48px (phone). Content max-width 1240px, 32px gutters.
- **Background, not outline.** Things that float are snow with a shadow: the chat card, the calculator, the featured town, Trends cards, the town card and controls over the map, the login and loading cards, search results, Back to top. Things that sit in the page are a beige-2 fill with no border: rows (towns, sales, layers, shortlist cards), the More lists, tiles, notices, the upload card, empty states, the flowchart, the verdict card (its tiles are `--field-alt` inside it). Rule and source boxes inside a beige-2 bubble are beige. In dark mode the surfaces step up in lightness (page < snow < beige-2 < field) so fills separate without a line.
- **No dashed or dotted lines** anywhere in the interface. The two exceptions: the dashed line that bridges a gap in a Trends chart (and the sentence that explains it), and the vendored Leaflet stylesheet.
- **Hairlines (`--line`) stay only where a surface meets the same colour and nothing else separates it:** the phone app bar's bottom edge, the desktop sidebar's right edge, the Ask composer's top edge, row separators inside a More list and in tables, the divider between the calculator's two halves, the line above "More numbers" in a sheet, under the chat card's header, the footer divider, the Trends tooltip and the small labels on the map.
- Cards: 20px radius (24px for the calculator, bands and phone sheets), `corner-shape: squircle` where supported. Inner boxes, tiles and bubbles 12–16px.
- **Buttons:** one radius scale: 14px for 46–56px buttons, 12px (`--radius-chip`) for 44px compact ones. Green filled primary (`--green-deep` on hover and press), tinted secondary (`--tint`, green text, no border), beige secondary, plain text tertiary (links, crumbs, "Show as a table"). Heights: 44px minimum; 50px for primary actions.
- **Number pickers:** every number the user picks (ages, lease, text size) is a slider (`sliderHtml`/`bindSlider`): the value large above a native range input, with its lowest and highest values labelled at the two ends. One control per number: no wheels, steppers or suggested-value chips beside it. Arrows, Page Up/Down and Home/End move it. Map zoom stays + and −.
- **Chips and quick picks:** 44px, 12px radius, tinted; a selected single choice is green with snow text. Pills (999px) only for count badges.
- **Fields** (inputs, search, selects, the composer): 50px, `--field` fill, no border, 14px radius; selects keep Home's chevron; placeholders `--ink-2` (≥4.5:1). Focus is the global ring (below). The range slider is the native control in `accent-color` green.
- Shadows: `--shadow-soft` (`0 1px 2px rgba(1,42,38,.06), 0 4px 14px rgba(1,42,38,.07)`) on cards that sit in the page; `--shadow-card` (`0 1px 2px rgba(1,42,38,.06), 0 16px 40px rgba(1,42,38,.14)`) on things that float over the map or the photo. Both black in dark mode. No coloured glows.
- **Materials, sparingly:** only the phone app bar is translucent (`--page` at 80%, `backdrop-filter: blur(20px) saturate(180%)`), with the page scrolling under it (each screen keeps the top 56px clear, `scroll-padding-top` 56px). Solid under `prefers-reduced-transparency: reduce`. Never on the desktop sidebar or on text-heavy cards.
- Density over whitespace: group related controls inside one card; no floating elements.
- **More** groups its rows under four small headings (`.label` as an `<h2>`): Your settings, Guides, About Runway, Legal. One list card per group.

## Interaction
- Every target is at least 44×44px (the range slider's 24px track is the one exception). Links inside sentences grow their hit area with vertical padding.
- Focus: a 2px `--green` ring 3px outside the element on every interactive element; `--brand-hi` on brand surfaces. Never `outline: none` without a replacement.
- Motion: 300ms or less, with the easing tokens, never linear or a built-in curve: `--ease-out` `cubic-bezier(.23,1,.32,1)` for things entering, leaving and changing colour; `--ease-in-out` `cubic-bezier(.77,0,.175,1)` for things moving on screen (the lease bar filling, the plane); `--ease-drawer` `cubic-bezier(.32,.72,0,1)` for the phone drawer and the sheets. No overshoot. Nothing enters from `scale(0)`. Only `transform` and `opacity` move; no `transition: all`.
- The drawer and the sheets enter and leave along the same path (drawer from the left, phone sheets from the bottom, desktop sheets from the right), out a little faster than in. A click or tap closes a sheet with a slide; Escape and code close it at once.
- **A key press gets no motion.** The page records the last input on `html[data-input]` (`key` or `pointer`); with `key`, the drawer, sheets, dialogs, toasts and switches change at once. Typing, a slider moved by key and the calculator's bar get no animation at all: the bar follows the slider 1:1.
- Every press shows at once: anything pressable (buttons, chips, quick picks, nav items, list rows) darkens and shrinks to `scale(0.97)` over 140ms `--ease-out` (not for a keyboard press); anything that waits on the server shows a busy or loading state. Hover effects only inside `@media (hover:hover) and (pointer:fine)`.
- `prefers-reduced-motion`: movement goes (no slides, scales or bounces; the drawer and sheets fade), opacity and colour changes stay.

## Navigation
- One left nav on every page, Home included: Home, Map, Shortlist, Trends, Ask, More, then Dark mode and Log in at the foot, with the logo and wordmark on top.
- ≥1024px: a fixed left sidebar, content to its right. "Collapse menu" at its foot folds it to a 76px icon rail (labels become tooltips; a search icon reopens it with the search box focused). The fold is instant and lasts for the visit only: nothing is stored. Below 1024px: a slim top bar with a menu button (top left) that opens the same nav as a drawer from the left over a dimmed scrim. No bottom tab bar.
- The Runway logo (sidebar, rail, top bar) always opens the top of Home.
- The search box carries a magnifier icon.
- Current page: green text on a beige-2 fill with a 2px green edge. More's own pages keep More marked.
- One URL per page (page names only, never user input); Back and Forward follow it.
- Every inner page starts with a breadcrumb (`crumbs()`: Home › … › page, the last crumb plain text). On the map it sits in the town card.
- Site search lives in the nav, under the brand. Long pages (Home, How it works, FAQ, Sources, Privacy, Terms) get a Back to top button 72px above the bottom edge, clear of Streamlit Cloud's badge.
- Loading the map data shows the `.rwload` panel with only the stages the page can observe; never a percentage.

## Icons
- One set: 24px viewBox, 2px stroke, round caps, `currentColor`. No emoji. Logo mark is the diamond-runway SVG.

## Imagery
- Real photos only, from Wikimedia Commons with credit: Punggol Waterway (CC BY-SA), Toa Payoh (CC BY-SA 2.0), Woodlands Ave 4 (Slivester, CC BY-SA 2.5).
- Hero treatment: the real photo + one soft green-deep scrim for legibility (left to right, with a short bottom fade). No grain, no thermal gradient, no parallax or drift.

## Human touch
- One hand-drawn element per page: the scribbled underline under the hero headline and the sketched arrow on the chat card. Keep it to one or two, never a theme.

## Copy (from lead review, Nov 2026)
- Headline: "Less lease, less CPF: what buyers need to know."
- Subhead: "How much CPF you can use for a flat depends on the years left on its lease and your age."
- Section 01 is "The gist"; use *hinges* / *discover* / "– too late".
- Verdict format: "Remaining lease 55 years · 43 years to 95. The flat has 55 lease years left — the youngest buyer turns 95 in 43 years. With 12 years to spare, CPF can be used up to the Valuation Limit, and the HDB loan is up to 75%."
- No closing "Have more questions?" band (removed Nov 2026): its "Start asking" only jumped back up to the hero's ask box, which is where questions start.
- Replace "calculated in the ordinary way" with "The figures come from the rule itself, not from the AI."

## Pre-ship pass
1. One accent only? 2. Tabular numbers? 3. No glow / purple / emoji / shouty caps? 4. Squircles on cards and buttons? 5. Hero carries one idea? 6. Photo credits present, on a solid chip? 7. Phone width: menus stack, nothing clipped. 8. Both themes: contrast holds, no hard-coded colour outside the tokens. 9. Targets ≥44px, focus ring visible, motion ≤300ms with the easing tokens. 10. Separated by fill or elevation, not outlines; no dashed or dotted lines; system font, Anton only for the wordmark.
