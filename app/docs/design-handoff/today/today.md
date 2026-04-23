# Today — surface spec

> One-page spec for engineering.  Pairs with `today.html`.
> Route: `GET /today` → `ui/today.py::render_today(ctx)`

---

## 1. Purpose

The Today surface is the user's daily anchor.  It answers one question:
**"Given my life commitments, what am I doing in the next 16 hours?"**

It presents one ribbon per LifePath, with a *Triage* bar above for overdue /
blocked items and a *Day spine* on the right for time-anchored rituals.
Dormant LifePaths collapse to a single-line nudge.  An empty day intentionally
encourages the user to stop — SKUEL does not manufacture work.

This surface is **read-dominant** but supports a small number of mutations
(complete, defer, wake) inline.  Deeper edits happen in their own surfaces
(task editor, LifePath editor) reached via the detail drawer.

---

## 2. Data shape

The server resolves `UserContext` → `context.today`:

```python
@dataclass
class TodayContext:
    date_label:    str                  # "Saturday · March 22"
    now_hhmm:      str                  # "10:15" — server clock, user tz
    stats:         TodayStats
    triage:        list[TriageItem]
    lifepaths:     list[LifePathRibbon] # include dormant=True entries
    principles:    list[Principle]
    goals:         list[Goal]
    tasks:         list[Task]           # only today's
    rituals:       list[Ritual]
    kinds:         dict[str, KindMeta]  # icon + label per kind
```

```python
@dataclass
class TodayStats:
    nodes:         int
    committed_min: int                  # sum of est_min across today's tasks
    done:          int

@dataclass
class LifePathRibbon:
    id:            str                  # "lp-craft"
    label:         str
    blurb:         str | None
    color:         str                  # oklch(...) — token-derived
    dormant:       bool = False
    last_touched:  str | None = None    # human label, e.g. "7 days ago"

@dataclass
class Principle:
    id:            str
    lifepath_id:   str
    label:         str
    strength:      Literal["core", "strong", "developing"]
    streak:        int

@dataclass
class Goal:
    id:            str
    principle_id:  str
    label:         str
    progress:      float                # 0..1

@dataclass
class Task:
    id:            str
    lifepath_id:   str
    goal_id:       str | None
    kind:          Literal["submission", "path-step", "askesis", "journal", "ku", "resource"]
    label:         str
    meta:          str                  # short gloss: "draft · needs your decision"
    priority:      Literal["high", "medium", "low"]
    est_min:       int
    due_label:     str                  # "Today", "Tonight", "Overdue · 2d"

@dataclass
class TriageItem(Task):
    reason:        str                  # "Overdue · 2 days" / "Blocked · @mentor"
    severity:      Literal["overdue", "blocked"]

@dataclass
class Ritual:
    id:            str
    time:          str                  # "HH:MM" 24h
    label:         str
    est_min:       int
    principle_id:  str | None

@dataclass
class KindMeta:
    icon:          str                  # lucide name
    label:         str
```

Server MUST sort `lifepaths` with active-first, dormant-last.
Server MUST provide `now_hhmm` (not the client) so SSR and optimistic UI agree.

---

## 3. Alpine state

Component root: `x-data="today()"` on `<main>`.

```js
{
  seed:          TodayContext,          // hydrated from <script>window.SEED = ...</script>
  selectedId:    string | null,         // keyboard / click focus
  openTaskId:    string | null,         // drawer target
  flash:         { msg, action } | null,
  flashTimer:    number | null,
  deferred:      { [taskId]: '1d' | '1w' },   // optimistic, hidden until server confirms
  completed:     Set<string>,                 // optimistic
  _lastAction:   { type: 'complete' | 'defer', id, span? } | null,
}
```

**Derived:**
- `fTasks`, `fTriage` — seed tasks/triage minus deferred & completed
- `allEmpty` — no triage, no tasks
- `committedMin`, `fmtCommitted`, `statList`
- `nowPct` — 0..100 position on the 06:00–22:00 day spine
- `openTask` — resolved task/triage object for `openTaskId`

**Helpers:** `principlesFor(lpId)`, `tasksFor(lpId)`, `goalFor(t)`,
`principleFor(t)`, `lifepathFor(t)`, `strengthClass(s)`,
`ritualPct(hhmm)`, `ritualPast(hhmm)`.

---

## 4. Keyboard map

Bound on `window` via `@keydown.window="onKey"`.  Disabled while the drawer
is open (the drawer owns `Escape`).

| Keys                  | Action                                     |
|-----------------------|--------------------------------------------|
| `j` / `↓`             | Focus next task (triage → ribbons top-down)|
| `k` / `↑`             | Focus previous                             |
| `Enter` / `Space`     | Open drawer for focused task               |
| `x`                   | Complete focused task (optimistic + POST)  |
| `d`                   | Defer focused 1 day                        |
| `⇧D`                  | Defer focused 1 week                       |
| `Escape`              | Close drawer; return focus to origin row   |

Focus is moved by `selectedId` + `.focus()` on the matched row's `role="button"`.
Rows are themselves `role="button"` + `tabindex="0"`, so native Tab also works.

---

## 5. HTMX endpoints (proposal)

All endpoints are POST unless noted.  Engineering is free to rename; the
HTML has `hx-post` / `hx-get` bindings colocated with each trigger.

| Trigger                                   | Method · URL                                       | Request       | Response             |
|-------------------------------------------|----------------------------------------------------|---------------|----------------------|
| Complete task (drawer button, `x`, drag)  | `POST /today/tasks/{id}/complete`                  | —             | `204` or new ribbon fragment |
| Defer task (drawer button, `d`/`⇧D`, drag)| `POST /today/tasks/{id}/defer`                     | `span=1d\|1w` | `204` or new fragment |
| Wake dormant LifePath                     | `POST /today/lifepaths/{id}/wake`                  | —             | `outerHTML` swap → active ribbon |
| Star / pin task (drawer)                  | `POST /today/tasks/{id}/star`                      | —             | `204`                |
| Server-rendered drawer body               | `GET  /today/tasks/{id}/drawer`                    | —             | HTML fragment into `#drawer-body` |
| Full surface SSR                          | `GET  /today`                                      | —             | full page            |

**Optimistic UI contract:** the client mutates `deferred` / `completed` and
shows a flash toast with Undo *immediately*.  HTMX fires the POST in the
background; on error the server should return `422` + a fragment that replaces
the toast with an error state.  On success, the fragment either `204`s
(keeping the optimistic state) or swaps a fresh ribbon to reconcile.

**Swap targets used in the HTML:**
- `hx-swap="outerHTML"` on the dormant-ribbon wake button
- `hx-swap="none"` on complete/defer (client handles UI)
- `hx-target="#drawer-body"` for the drawer body fragment

---

## 6. Accessibility

- Ribbon sections: `role="region"` with `aria-labelledby="ribbon-<id>"`.
- Triage section: `role="region"` with `aria-labelledby="triage-heading"`.
- Each task row: `role="button" tabindex="0"` with a composed `aria-label`
  of the form `"{label} · {due or reason} · {est_min}m"`.
- Drawer: `role="dialog" aria-modal="true" aria-labelledby="drawer-title"`,
  `Escape` closes, focus returns to the originating row.
- Flash toast: `role="status" aria-live="polite"`.
- Focus ring: `focus:shadow-focus` using `0 0 0 2px hsl(var(--ring) / 0.2)`.
- All transitions `≤ 300ms ease-out`; `prefers-reduced-motion: reduce` zeroes
  transitions and disables the drag transform so defer is keyboard-only.
- Color is never the sole carrier of priority or strength — each pairs with
  a text label (e.g. the priority word in the drawer, the strength pill text).
- Drag-to-defer is a *progressive enhancement*; the same actions are always
  reachable via keyboard (`d` / `⇧D`) and the drawer's Defer buttons, so
  pointer-only users are not required.

---

## 7. Rendering notes

- Task rows are hand-rendered via a template-literal `renderRow(t, opts)`
  helper.  Alpine's reactive re-render re-runs it when `fTasks` / `fTriage`
  change, and we call `lucide.createIcons()` in `$watch` hooks to repaint
  icons.  If engineering prefers, each row can become a partial template
  rendered by the server on every optimistic change.
- The day-spine is absolute-positioned inside a fixed-height `<aside>`;
  positions are a linear map from `06:00–22:00` to `top: 52px .. bottom:18px`.
- No gradients except the Triage bar's single downward red wash (inside the
  one-exception allowance).  No backdrop-filter.  No scale/press animations.
- Token references are all `hsl(var(--token))` or `oklch(...)` — nothing
  hardcoded.  A single `:root` block mirrors `static/css/input.css` for
  preview only; production pulls the real stylesheet.
