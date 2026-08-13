# Handoff: Calendar Month View Redesign

## Overview
A redesign of the SKUEL calendar **Month** view (route `GET /events/month/{year}/{month}`).
It keeps every existing feature — the Day/Week/Month view switcher, the Prev/Today/Next
navigation, the Monthly-note link, the ISO week-number rail, daily/weekly/monthly note
links, and the click-to-open item details modal — while reworking the layout, event
rendering, and header chrome for clarity and scannability.

The Week and Day views are shown in lighter form in the prototype; this handoff focuses
on the **Month** view (the surface that was redesigned). Week/Day chrome changes (toolbar,
event chips, legend) should be applied consistently, but their grids are out of scope
unless noted.

## About the Design Files
`Calendar Month.dc.html` in this bundle is a **design reference created in HTML** — a
prototype showing the intended look and behavior. It is **not** production code to copy
directly. It was authored in a React-based prototyping runtime (streaming "Design
Component"), so its markup uses inline `style` objects and a small JS class.

**Your task is to recreate this design in the existing SKUEL stack** —
**FastHTML + HTMX + Alpine.js + MonsterUI (FrankenUI + Tailwind)** — by editing the
existing calendar modules, using SKUEL tokens and Tailwind utility classes (exactly as
`app/ui/today` / the `today.html` mock do). Do **not** introduce React, JSX, or a bundler,
and do **not** ship the prototype's inline styles. Translate the inline styles below into
Tailwind classes bound to the existing `hsl(var(--token))` CSS variables.

## Fidelity
**High-fidelity.** Colors, typography, spacing, radii, and interactions are final. Recreate
the Month view pixel-accurately using MonsterUI components + Tailwind utilities and the
SKUEL tokens in `app/static/css/input.css`. No new hex values, no new tokens — see the
Design Tokens section for how the prototype's hex chips map back to the token system.

## Files to change in the codebase
This redesign maps onto existing modules — modify these, do not create parallel ones:

- **`app/adapters/inbound/calendar_ui.py`**
  - `calendar_month()` — the month **shell** route. Replace the header block (`PageHeader`
    + `create_view_switcher` + the centered `Div` of `ButtonLink`s including the `📝`
    button) with the new **toolbar** described below. The legend also lives here.
- **`app/ui/calendar/components.py`**
  - `create_month_grid()` — grid container, weekday header row, week rows, week-number rail.
  - `create_day_cell()` — day cell styling, date-number / Today treatment, event chips,
    `+more` indicator.
  - `create_view_switcher()` — restyle as a segmented control (see below).
  - `create_item_details_modal()` — unchanged in structure; only restyle if desired to
    match the prototype modal. Existing HTMX wiring (`hx_get=/events/calendar/item-details/{uid}`,
    `hx_target="body"`, `hx_swap="beforeend"`) stays.
- **`app/static/css/calendar.css`** — add the chip hover transition (see Interactions).

The data layer is unchanged: `calendar_month_content()` and `calendar_service.get_calendar_view(...)`
still return `CalendarData`, and cells still group `CalendarItem`s by `start_time.date()`.

---

## Screen: Month View

### Layout
Fluid width (keep `content_max_width="max-w-none"`). Top-to-bottom:

1. **Header row** — flex, `items-end justify-between`, wraps, `mb-5`.
   - Left: an uppercase eyebrow `Calendar` + the period title (`{Month} {Year}`).
   - Right: the **legend** (5 item-type swatches), bottom-aligned.
2. **Toolbar row** — flex, `items-center justify-between`, wraps, `mb-4/5`.
   - Left: segmented Day/Week/Month switcher.
   - Right: nav cluster — `[‹ Prev] [Today] [Next ›]`, a 1px divider, then `[Monthly note]`.
3. **Grid** — bordered, `rounded-xl`, `overflow-hidden`, card background, subtle shadow.
   - 8 columns: a **46px** week-number rail + `repeat(7, minmax(0,1fr))` day columns.
   - Weekday header row, then one grid row per calendar week.

### Components

**Eyebrow**
- Text: `Calendar`
- `text-[11px] font-bold uppercase tracking-[0.1em] text-muted-foreground`

**Title**
- Text: `{Month} {Year}` (e.g. `July 2026`)
- `text-[40px] font-bold tracking-[-0.02em] leading-none`, `mt-1.5`

**Legend** (5 swatches, one per `CalendarItemType`; horizontal, `gap-3.5`, wraps)
- Each: a 9×9px `rounded-[3px]` color square + `text-[11px] font-medium text-muted-foreground` label.
- Labels + colors: Event / Task / Deadline / Habit / Milestone — see Design Tokens.

**View switcher (segmented control)** — replaces the current 3-button `inline-flex`.
- Track: `inline-flex p-[3px] bg-muted border border-border rounded-[9px]`.
- Each segment: `h-7 px-4 rounded-md text-[13px] font-semibold`.
  - Active: `bg-card text-foreground shadow-[0_1px_2px_rgba(0,0,0,0.08)]` (still rendered as
    a non-navigating current item, matching today's `disabled` active span).
  - Inactive: `bg-transparent text-muted-foreground`, links to
    `/events/day/{iso}`, `/events/week/{iso}`, `/events/month/{y}/{m}` (unchanged targets).

**Nav buttons** (`Prev`, `Next`)
- `h-[34px] px-3 border border-border bg-card rounded-lg text-[13px] font-medium text-foreground`,
  inline-flex, `gap-1.5`; hover `bg-muted`.
- Leading (Prev) / trailing (Next) Lucide chevron: `<i data-lucide="chevron-left">` /
  `chevron-right`, `w-[15px] h-[15px]`, 2px stroke.
- `href` unchanged: `/events/month/{prev_y}/{prev_m}` and `/events/month/{next_y}/{next_m}`.

**Today button**
- `h-[34px] px-4 bg-primary text-primary-foreground border border-primary rounded-lg text-[13px] font-semibold`.
- `href="/events/calendar"` (unchanged).

**Divider**
- `w-px h-[22px] bg-border mx-1`.

**Monthly-note button** — replaces the bare `📝` `ButtonLink`.
- `h-[34px] px-[13px] border border-border bg-card rounded-lg text-[13px] font-medium text-foreground`,
  inline-flex, `gap-[7px]`, `whitespace-nowrap`; hover `bg-muted`.
- Lucide `square-pen` (or `pencil`) icon `w-[15px] h-[15px]` + label `Monthly note`.
- `href="/journals/monthly/{year}/{month}"`, `title="Open monthly note"` (unchanged target).

**Weekday header**
- Grid `[46px_repeat(7,minmax(0,1fr))]`, background `bg-muted/50`.
- Rail header cell: centered `Wk`, `text-[10px] font-bold uppercase tracking-[0.06em]
  text-muted-foreground`, `border-b border-r border-border`, `py-[11px]`.
- Day labels `Mon…Sun`: centered `text-[12px] font-semibold`, `py-[11px]`, `border-b border-border`.
  Weekend labels (Sat, Sun) use `text-muted-foreground`; weekdays use `text-foreground`.

**Week-number rail cell** (first column of each week row) — keep the existing `A(...)` link.
- Centered, `font-mono text-[11px] text-muted-foreground`, `bg-muted/25`,
  `border-r border-b border-border`; hover `text-primary bg-muted/60`.
- `href="/journals/weekly/{iso_year}/{iso_week}"`, `title="Weekly note — W{iso_week}, {iso_year}"` (unchanged).

**Day cell** (`create_day_cell`)
- Base: `border-r border-b border-border min-h-[120px] px-[7px] pt-1.5 pb-2.5 relative overflow-hidden`.
- Background by state (mutually exclusive, in priority order):
  - **Today**: `bg-primary/[0.07]` **plus** an inset ring `shadow-[inset_0_0_0_2px_hsl(var(--primary))]`.
  - **Out-of-month**: `bg-muted/50`.
  - **Weekend (in month)**: `bg-muted/30`.
  - **Normal**: `bg-background`.
- **Date number** (top-left, `min-h-[24px]` row, `mb-[5px]`), links to
  `/journals/daily/{iso}` with `hx-boost="false"` (unchanged):
  - **Today**: rendered as a filled pill — inline-flex, `min-w-[24px] h-6 px-1.5 rounded-full
    bg-primary text-primary-foreground text-[12px] font-bold`. (Replaces the current
    separate number + "Today" `Badge`; the pill *is* the today indicator.)
  - **Normal (in month)**: `text-[13px] font-semibold text-foreground`.
  - **Out-of-month**: `text-[13px] font-semibold text-muted-foreground/60`.
- **Event chips** — max 3 (unchanged `date_items[:3]`), stacked, `gap-[3px]`:
  - Chip: flex, `items-center gap-1.5 px-[7px] py-0.5 rounded-md text-[11.5px] font-medium
    leading-[1.5] text-foreground`, `cursor-pointer`.
  - Fill + accent from the item's type color `C`: `background: {C}/10` (10% alpha),
    `border-left: 3px solid {C}`.
  - Leading dot: 8×8px `rounded-full` filled with `C`.
  - Title span: `flex-1 min-w-0 truncate` (CSS ellipsis — **remove** the current
    `title[:15] + "..."` Python truncation; let `truncate` handle it).
  - Keeps existing HTMX: `data_item_id`, `hx_get=/events/calendar/item-details/{uid}`,
    `hx_target="body"`, `hx_swap="beforeend"`.
- **`+more`** — when `has_more`: `text-[11px] font-medium text-muted-foreground px-1.5 pt-px`.
  Prefer the count form `+{n} more` (compute `len(items) - 3`) over the bare `+more`.
- **Occurrences** — the habit-occurrence emoji row can remain, or fold into chips; not central to this redesign.

---

## Interactions & Behavior
- **View switch** — links (full navigation), unchanged routes. Active segment is non-clickable.
- **Prev / Today / Next** — links, unchanged routes; HTMX-boosted page nav as today.
- **Day number → daily note**, **week number → weekly note**, **Monthly note → monthly note** —
  links to `/journals/...` with `hx-boost="false"` where already present (full navigation
  so the 302 resolves in the browser).
- **Event chip click** — opens the item-details modal via the existing HTMX endpoint
  (`hx_get` to `/events/calendar/item-details/{uid}`, swap `beforeend` on `body`). Modal
  close/Escape handled by the existing Alpine `x-data="{ open: true }"` + `close_expr`.
- **Chip hover** — `transform: translateY(-1px)` + `box-shadow: 0 2px 5px rgba(0,0,0,0.12)`,
  transition ≤ 200ms ease-out. (Extend the existing `.calendar-item` rule in `calendar.css`.)
- **Reduced motion** — disable the hover transform under `prefers-reduced-motion` (per SKUEL rule 4).
- No gradients, no backdrop-filter, no press-scale (SKUEL motion rules).

## State Management
Server-rendered; **no client state added**. All navigation is via links/HTMX as today.
The only ephemeral state is the details modal's Alpine `open` flag, which already exists.
Grid data comes from `calendar_service.get_calendar_view(user_uid, first_day, last_day,
CalendarView.MONTH)` → `CalendarData`, grouped by `item.start_time.date()`.

## Design Tokens
Use existing SKUEL tokens only (from `app/static/css/input.css`). Reference via
`hsl(var(--…))` / Tailwind classes; do **not** hardcode hex.

**Semantic tokens used**
- `--background`, `--foreground`, `--muted`, `--muted-foreground`, `--border`, `--card`,
  `--primary`, `--primary-foreground`.

**Item-type colors (legend + chips).** The prototype uses concrete hex per
`CalendarItemType`; each `CalendarItem` already carries its own `.color` (default
`#3B82F6`), so **the chip fill/accent/dot should keep reading `item.color`** — the values
below are the intended per-type palette to assign when items are generated (converters),
not new UI tokens:
- Event — `#2563eb`  (maps to the strength-strong blue family)
- Task (`task_work`) — `#6366f1`
- Deadline (`task_deadline`) — `#e11d48`  (destructive family)
- Habit — `#16a34a`
- Milestone — `#9333ea`  (strength-core purple family)
- Chip fill = type color @ 10% alpha; accent bar + dot = type color @ 100%.

**Typography** — Inter (UI), JetBrains Mono (week numbers, time labels). Sizes used:
title 40 / eyebrow & labels 10–12 / day number 12–13 / chip 11.5 / weekday header 12.
**Radius** — grid `rounded-xl` (12px), buttons/segments `rounded-lg`/`rounded-md`,
chips `rounded-md`, dots `rounded-full`. **Shadows** — grid `0 1px 3px rgba(0,0,0,0.04)`,
active segment `0 1px 2px rgba(0,0,0,0.08)`, chip hover `0 2px 5px rgba(0,0,0,0.12)`.

## Assets
- **Icons: Lucide only**, 2px stroke (SKUEL rule 3) — `chevron-left`, `chevron-right`,
  `square-pen` (monthly note), and in the modal `x`, `map-pin`. **This replaces the emoji
  icons** (`📅`, `📝`) currently rendered in cells and the note button — a deliberate
  improvement to bring the calendar in line with the no-emoji rule.
- No images.

## Files in this bundle
- `Calendar Month.dc.html` — the interactive design reference (open in a browser to explore
  the Month view, view switching, Prev/Today/Next, and the click-to-detail modal). Sample
  events are illustrative only.
