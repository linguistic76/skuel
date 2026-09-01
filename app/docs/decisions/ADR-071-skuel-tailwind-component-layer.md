---
title: "ADR-071: SKUEL-Owned Tailwind Component Layer"
updated: 2026-09-01
status: implemented
category: decisions
tags: [adr, decisions, ui, tailwind, alpine, components]
related: [ADR-043, ADR-050]
related_skills: [skuel-ui, ui-browser, ui-css]
---

# ADR-071: SKUEL-Owned Tailwind Component Layer

**Status:** Implemented (M10 2026-06-29; DaisyUI removal completed in follow-up 2026-06-30)

**Date:** 2026-06-29

**Decision Type:** ⬜ Pattern/Practice  ⬜ Infrastructure  ✅ Architecture

**Related ADRs:**
- Supersedes: MonsterUI/FrankenUI as the UI component library (no separate ADR — was an undocumented default)
- Depends on: ADR-050 (PWA / static serving)

---

## Context

SKUEL uses MonsterUI (a FastHTML wrapper around FrankenUI, which wraps UIkit) as its UI
component library. Two converging problems make this foundation untenable.

### Problem 1 — Architectural conflict: UIkit vs Alpine.js

UIkit ships its own JavaScript state machine (`data-uk-modal`, `data-uk-toggle`,
`data-uk-dropdown`, etc.) that directly conflicts with Alpine.js. Both systems try to own
DOM state. The collision is not theoretical — it has already forced a workaround:
`ui/patterns/modal.py` (`AlpineModal`) was built from scratch precisely because UIkit modals
cannot be driven by Alpine state. UIkit intercepts the same DOM events Alpine handles, causing
unpredictable behavior whenever the two systems touch the same element.

The consequence: every new interactive component is a bet on which JS framework wins
a given DOM subtree. SKUEL's intended interactivity model is **Alpine.js + HTMX**. UIkit is
an uninvited third party that the project must route around.

### Problem 2 — Upstream momentum

FrankenUI has evolved into `0build.dev`, which has one GitHub follower as of 2026-06-29.
MonsterUI depends on this upstream. Committing to deeper MonsterUI adoption means committing
to a library with no visible community, maintenance trajectory, or compatibility guarantees.

### Problem 3 — Hidden payload cost

MonsterUI loads five vendor files totalling ~4.1MB per page:

| File | Size | Purpose |
|------|------|---------|
| `franken_css.css` | 174KB | FrankenUI component CSS (`uk-*` class names) |
| `daisyui.css` | 2.9MB | DaisyUI 4.x (used only for CSS variables + Alert/Loading) |
| `tailwind.js` | 407KB | **Tailwind Play CDN JIT running in the browser** |
| `franken_js_core.js` | 220KB | UIkit JS (the Alpine.js conflict source) |
| `franken_icons.js` | 366KB | Lucide icons via UIkit's custom element system |

The critical discovery: `static/css/output.css` exists (from Tailwind CLI builds) but is
**never loaded**. The app relies entirely on `tailwind.js` browser JIT for all Tailwind
compilation. This is a development convenience that is not production-appropriate.

---

## Decision

Replace MonsterUI/FrankenUI with a **SKUEL-owned thin Python FT component layer** built
directly on Tailwind class strings. The result is a coherent three-part stack with no
inter-system conflict:

```
Appearance:     Tailwind CSS (CLI-compiled output.css, no runtime JIT)
Icons:          Lucide JS (vendored, ~32KB, data-lucide attribute pattern)
Interactivity:  Alpine.js (unchanged)
Server comms:   HTMX (unchanged)
Components:     ui/components/ — Python FT functions encoding Tailwind class strings
```

### Decision 1 — Python FT components encoding Tailwind strings

SKUEL components use the exact same FT protocol FrankenUI uses — Python functions returning
FT objects. The difference is that Tailwind class strings replace `uk-*` class names, and
UIkit is not involved.

```python
# The FT protocol: callable → FT object, cls + kwargs pass through
def Card(*c: Any, cls: str | tuple = "", **kwargs: Any) -> FT:
    return Div(*c, cls=_cls("rounded-lg border bg-card shadow-sm", cls), **kwargs)
```

`**kwargs` passthrough is the essential contract — it lets any component accept HTMX
attributes (`hx_post`, `hx_target`), Alpine attributes (`x_data`, `x_on:click`), and
arbitrary HTML attributes without the component needing to know about them.

All components live in a new `ui/components/` package:

```
ui/components/
    __init__.py      — clean import surface
    _util.py         — _cls() tuple-flattening utility
    button.py        — Button, ButtonT (StrEnum of Tailwind class strings)
    card.py          — Card, CardHeader, CardBody, CardTitle, CardFooter
    icon.py          — Icon (UkIcon replacement, data-lucide attribute)
    feedback.py      — Alert, AlertT, Loading, Progress, ProgressT
    form.py          — Input, TextArea, Select, Label, LabelInput, LabelTextArea, ...
    divider.py       — Divider
    table.py         — Table, TableFromLists, TableFromDicts, Td, Th, Tbody, TableT
    nav.py           — TabContainer
    accordion.py     — Accordion, AccordionItem (Alpine.js-driven, no UIkit)
    layout.py        — DivFullySpaced, DivCentered, Center (the 3 MonsterUI re-exports)
```

### Decision 2 — CSS variable ownership

Currently DaisyUI generates all semantic CSS variables (`--primary`, `--background`,
`--card`, `--foreground`, etc.) for the app's theme. After removing DaisyUI, SKUEL owns
these values in `static/css/input.css`. The Tailwind config maps them:

```js
colors: {
  background: 'hsl(var(--background))',
  foreground: 'hsl(var(--foreground))',
  primary: { DEFAULT: 'hsl(var(--primary))', foreground: 'hsl(var(--primary-foreground))' },
  card: { DEFAULT: 'hsl(var(--card))', foreground: 'hsl(var(--card-foreground))' },
  // muted, accent, destructive, border, input, ring, popover ...
}
```

This is the shadcn/ui pattern — proven, widely understood, and stable. Visual parity with the
current DaisyUI-generated theme is maintained by copying the exact computed values before
removing the library.

### Decision 3 — Lucide JS as the icon strategy

> **⚠️ SUPERSEDED by [ADR-072](ADR-072-server-rendered-inline-svg-icons.md) (2026-06-30).**
> The client-side Lucide runtime described below (`data-lucide` + `lucide.createIcons()`) was
> removed in #452 after it caused a MutationObserver infinite loop that froze the browser
> (#450). `Icon()` now emits server-rendered inline `<svg>` from a generated registry — no
> client-side icon JS. The rest of ADR-071 stands.

`UkIcon("name")` is replaced by `Icon("name")` from `ui/components/icon.py`. Lucide JS is
vendored at `static/vendor/lucide/` (same pattern as Alpine.js and HTMX). Icons render via
`data-lucide` attribute; `lucide.createIcons()` is called once after Alpine initializes and
again on each HTMX content swap. Icon names are identical — FrankenUI already used Lucide
under the hood.

### Decision 4 — Tailwind CLI compilation replaces browser JIT

`static/css/output.css` is compiled by the Tailwind CLI and loaded as a static file. The
407KB `tailwind.js` browser JIT is removed. `./dev css-build` generates `output.css`; the
safelist handles dynamic class strings (`gap-{n}`, `grid-cols-{n}`, etc.) that the static
scanner cannot detect.

---

## Alternatives Considered

### Alternative A — Keep MonsterUI, route around UIkit more carefully

Build every interactive component as a pure Alpine.js workaround (as `AlpineModal` did).
**Rejected.** This is the current trajectory and it has already produced one workaround. The
root cause is UIkit's presence, not insufficient workaround quality. Each new component
requires re-solving the same conflict. The architecture is wrong; the fix is removal.

### Alternative B — Switch to a different FrankenUI-derived library

e.g., find a maintained FrankenUI fork without UIkit, or a pure CSS component library.
**Rejected.** No library in this space offers what SKUEL already has: Python FT components
that integrate naturally with FastHTML. Writing the thin layer ourselves is the correct
investment — the components encode Tailwind strings, which is not complex code.

### Alternative C — Switch to shadcn/ui (React-style server components)

**Rejected.** SKUEL is a FastHTML hypermedia application. React's component model is the
wrong paradigm. The server renders FT, not JSX. Shadcn/ui's design token conventions
(CSS variable names, Tailwind token names) are adopted; the React component code is not.

### Alternative D — Keep DaisyUI, only remove FrankenUI/UIkit

Strip UIkit but keep DaisyUI for CSS components. **Rejected.** DaisyUI provides 2.9MB of CSS
and is used only for CSS variable values and two components (Alert, Loading). Writing
pure-Tailwind replacements for Alert and Loading is trivial; owning the CSS variables directly
is simpler than maintaining a 2.9MB dependency for color values.

---

## Consequences

### Positive

- ✅ **UIkit eliminated** — no more Alpine.js/UIkit DOM state conflicts. Every interactive
  component is Alpine.js, cleanly.
- ✅ **Large payload reduction** — ~4.1MB → ~130KB (`output.css` ~98KB + Lucide JS ~32KB).
  Eliminates `tailwind.js` browser JIT (production-inappropriate). (`output.css` settled at
  ~98KB once DaisyUI's ~30 baked-in themes were stripped in the 2026-06-30 follow-up — see
  Changelog; the earlier ~50KB estimate predated the final app-wide utility surface.)
- ✅ **SKUEL controls the component layer** — no upstream dependency risk. Component changes
  require editing Python, not waiting for a library release.
- ✅ **One JS model** — Alpine.js handles all client state, HTMX handles server comms.
  Accordion, tabs, modals — all Alpine, all consistent.
- ✅ **`output.css` finally loaded** — the compiled CSS file that existed but was never used
  is now the production asset. The browser JIT is a development convenience that is gone.

### Negative

- ⚠️ **One-time migration cost** — 192 MonsterUI import sites across ~60 production files.
  Heaviest: `ButtonT` (84 sites), `CardContainer` (55 sites), `Button` (54 sites),
  `UkIcon` (138 sites). Mechanical but non-trivial.
- ⚠️ **SKUEL owns component maintenance** — bugs in `Card` or `Button` are ours to fix. This
  is acceptable given the upstream risk being traded away.
- ⚠️ **Tailwind CLI must run before serving** — `./dev css-build` is a required build step.
  Missing classes in `output.css` are invisible at Python-edit time. The safelist must be
  maintained for dynamic class strings.

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Visual regression during call-site migration | Medium | Medium | Phase 2 is per-component; component gallery (`/admin/component-gallery`) validates parity before call-site migration |
| Dynamic class strings missed by Tailwind scanner | Low | Low | Explicit safelist patterns in `tailwind.config.js` cover all known dynamic patterns; `static/js/*.js` added to Tailwind content scan (see Implementation Notes) |
| JS-generated classes not visible to Python-based content scan | Medium | Medium | `static/js/today.js` builds classes like `bg-strength-strong/10` at runtime — covered by adding `static/js/*.js` to Tailwind content paths (see Implementation Notes) |
| Lucide icons in Alpine-reactive DOM nodes render as blank | Medium | Medium | `<uk-icon :icon=...>` inside `x-for`/`x-if` auto-upgrades via UIkit's custom element registry; Lucide's `createIcons()` only processes elements present at call time. See M9 prerequisite below |
| `output.css` not rebuilt after component changes | Low | Low | `./dev quality` (step 8) validates that `output.css` is up-to-date |

---

## Migration Sequence

Migration follows One Path Forward: each component is migrated completely across all call
sites in a single PR; the old import is removed at the same time.

### Phase 1 — Build the foundation (no call-site changes)

| PR | Scope |
|----|-------|
| PR-1 | ADR-071 (this document) |
| PR-2 | CSS variable ownership (`input.css`), Tailwind config extension, vendor Lucide JS, `skuel_headers()` dormant parallel to `monster_headers()` |
| PR-3 | `ui/components/` package — all replacement components + `tests/unit/ui/test_components.py` |

The app keeps working throughout Phase 1 (MonsterUI still loaded; new infrastructure is
additive only).

### Phase 2 — Migrate call sites (component by component)

Approximate sequence (re-evaluated after Phase 1):

| PR | Scope | Sites |
|----|-------|-------|
| M1 | `ui/primitives.py` — `ButtonLink`, `UkIcon` wrapper | Foundation |
| M2 | `ui/feedback.py` — Alert, Loading, Progress | Removes `monsterui.daisy` |
| M3 | `ui/layout.py` — remove 3 MonsterUI re-exports | Clean |
| M4 ✅ | All `ButtonT` + `Button` call sites | 84 sites (#440 2026-06-29) |
| M5 ✅ | All `Card*` call sites | 55 sites (#441 2026-06-29) |
| M6 ✅ | All `UkIcon` call sites | 138 sites (#442 2026-06-29) |
| M7 ✅ | Form components (`ui/forms/`) | 1 file (#443 2026-06-29) |
| M8 ✅ | Remaining components (`ui/data.py`, `ui/navigation.py`, `relationship_section.py`) | 4 files (#444 2026-06-29) | <!-- historical -->
| M9 ✅ | Wire `skuel_headers()`, remove `monster_headers()` — UIkit leaves the browser | Cutover |
| M10 ✅ | `uv remove monsterui`; delete vendor files; remove quality gate | Cleanup |
| M11 ✅ | **DaisyUI removal** (2026-06-30 follow-up): `daisyui` dropped from `package.json` + `tailwind.config.js`; daisy color utilities (`text-error`, `bg-base-200`, …) re-homed as concrete tokens in the Tailwind config; 2 remaining daisy component-class sites (`ui/ingestion/dashboard.py`, `ui/search/components.py`) migrated to pure Tailwind. `output.css` ~195KB → ~98KB (30 baked-in themes removed). | Cleanup |

M4 and M5 are large but mechanical — good candidates for fresh-context agents.
M9 is the pivotal cutover: after it lands, UIkit is no longer loaded in any browser session.

### Phase 3 — Verify and close

After M10:
- `grep -r "uk-" ui/ adapters/` returns zero results
- `grep -r "monsterui" . --include="*.py"` returns zero results
- `./dev quality` passes
- All Activity domain list + detail pages render correctly
- Form submission and Alpine.js modals work

---

## Implementation Notes

### The `_cls()` utility

FrankenUI allows `cls=(ButtonT.primary, ButtonT.sm)` tuple composition. SKUEL components
inherit this convention via a shared utility in `ui/components/_util.py`:

```python
def _cls(*parts: Any) -> str:
    """Flatten heterogeneous cls arguments to a space-separated string."""
    result = []
    for part in parts:
        if isinstance(part, (list, tuple)):
            result.extend(str(p) for p in part if p)
        elif part:
            result.append(str(part))
    return " ".join(result).strip()
```

### ButtonT as StrEnum

`ButtonT` becomes a StrEnum whose values ARE the Tailwind class strings. This preserves the
existing call signature (`Button("text", cls=ButtonT.primary)`) while eliminating the UIkit
class name layer entirely.

### Tailwind content scanning — must include `static/js/`

The Tailwind CLI scanner must cover JavaScript files that build class strings at runtime.
`static/js/today.js`'s `strengthClass()` function returns classes like
`bg-strength-strong/10` and `bg-strength-developing/10` that are invisible to Python-only
scanning. Add to `tailwind.config.js`:

```js
content: [
  "./ui/**/*.py",
  "./adapters/inbound/**/*.py",
  "./core/**/*.py",         // ← required; enum badge classes live here (EntityStatus, HabitEssentiality, etc.)
  "./ui/components/**/*.py",
  "./static/js/*.js",       // ← required; covers runtime-built Tailwind classes
  "./templates/**/*.html",
],
```

Verify during PR-2 that `output.css` contains the strength classes and enum badge utilities
(e.g. `bg-gray-100 text-gray-600`) after running `./dev css-build`. Fix the safelist if any
are missing.

### M9 prerequisite — Alpine-reactive Lucide icon contexts

UIkit's custom element system auto-upgrades `<uk-icon>` elements whenever they are
inserted into the DOM, including by Alpine `x-for`/`x-if`/`x-show`. Lucide's
`createIcons()` only processes elements present at the moment it is called.

`ui/today/page.py` uses `<uk-icon :icon=...>` inside Alpine reactive blocks (e.g. the
drawer toolbar that appears only after `openTask` becomes truthy). After M9 cutover, these
will render as blank unless the dynamic icon contexts are handled.

**Required before M9:**

Option A (preferred) — replace `<uk-icon :icon="name">` with a static `Icon()` call
inside an Alpine template that uses `x-html` or moves the icon out of the reactive block.
This is the cleanest path: static `data-lucide` attributes present on page load are always
processed.

Option B — add a MutationObserver in `static/js/skuel.js` that watches for new
`data-lucide` attribute additions and calls `lucide.createIcons()`:

```js
new MutationObserver(() => {
    if (window.lucide) lucide.createIcons();
}).observe(document.body, { subtree: true, attributeFilter: ['data-lucide'] });
```

The M6 PR (UkIcon call-site migration) is the natural point to audit every `<uk-icon
:icon=...>` Alpine binding and convert to Option A or ensure Option B is in place.

### Already pure Tailwind (no migration needed)

- `ui/layout.py` — `DivHStacked`, `DivVStacked`, `Stack`, `Row`, `Container`, `FlexItem`
  already build `Div(cls="flex ...")` directly. Only 3 MonsterUI re-exports remain.
- `ui/feedback.py` — `Badge`, `PriorityBadge`, `StatusBadge` are pure Tailwind.
- `ui/patterns/modal.py` — `AlpineModal` is pure Tailwind (built to avoid UIkit).

---

## Related Documentation

- `docs/patterns/UI_COMPONENT_PATTERNS.md` — update after Phase 1 to reference `ui/components/`
- `docs/ui/COMPONENT_CATALOG.md` — update as each Phase 2 PR lands
- `CLAUDE.md` (UI Component Pattern section) — update after M10 to remove MonsterUI references
- Skills: `skuel-ui`, `ui-browser`, `ui-css` — update after Phase 1

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2026-06-29 | Claude Code | Initial draft | 0.1 |
| 2026-06-29 | Mike | Accepted | 1.0 |
| 2026-06-30 | Claude Code | DaisyUI removal completed (M11); payload + status corrected | 1.1 |
