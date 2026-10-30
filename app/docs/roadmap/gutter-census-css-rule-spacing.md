---
title: "Gutter Census Reads No Spacing From Hand-Written CSS"
updated: 2026-10-30
status: "open — registered, not built; no live double today"
registered: 2026-10-30
trigger: "a hand-written stylesheet rule (static/css/*.css, not output.css) gives padding or margin to a class a shelled body places at its edge — none of today's nine does"
check: "for each bare-class rule in static/css/*.css (not output.css) that sets padding or margin, git grep the class in ui/ and adapters/inbound/, and find where each use sits in its body — nine today (seven in search.css, two in main.css), none at a body edge"
---

# Gutter Census Reads No Spacing From Hand-Written CSS

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

The page-gutter census (`tests/unit/ui/_gutter_census.py`, held by `test_page_gutters.py`) holds
every shelled body to "the shell owns the gutter": no padding at a body's sides, top or bottom, and
no margin at its top or bottom edge. It reads that spacing from **class tokens** — `px-4`, `py-8`,
`mb-8` — and nowhere else.

A hand-written stylesheet can space an element too. The census already reads those sheets for one
fact: `css_boxes()` finds the bare-class rules that paint a box (background, border, shadow), so
the walk stops at a panel drawn in CSS. It does not read their **padding or margin**. A class
whose rule pads or margins an element at a body's edge would double the shell's gutter, and the
census would pass.

## Today

Nine classes in use get padding or margin from a bare-class rule. None spaces a shelled body's edge:

| Class | Sheet | Spacing | Where it lands |
|-------|-------|---------|----------------|
| `search-input-container` | `search.css` | `margin-bottom` | the search box panel — first child of `search-main`, followed by the filters |
| `search-filters` | `search.css` | `padding`, and from `lg` `margin-bottom` | the filter drawer (fixed below `lg`), an inline bar from `lg`, followed by the results |
| `search-filters-header` / `-footer` | `search.css` | `padding-bottom` / `padding-top`, `margin-top: auto` | the drawer's own rows, below `lg` only |
| `filter-advanced` | `search.css` | `padding-top`, `margin-top` | a group inside the filter panel |
| `active-filters` | `search.css` | `padding` | the active-filter chip row, between the filters and the results |
| `more-filters-toggle` | `search.css` | `margin-left: auto` | a button in the filter row |
| `skip-link` | `main.css` | `padding` | the shell's skip link, positioned off-screen until focused |
| `sr-only` | `main.css` | `padding: 0`, `margin: -1px` | visually hidden text, out of flow |

That is a fact about where nine classes land now, not a guarantee.

## What closing it takes

A `css_spacing()` beside `css_boxes()` — the same parse of the same sheets — returning, for each
bare class, the sides its rule pads and margins (shorthands resolved to sides, rules inside an
`@media` counted as spacing at that breakpoint). The walk then reads those sides wherever it reads
a class token's, with a control that fails when the read is switched off.
