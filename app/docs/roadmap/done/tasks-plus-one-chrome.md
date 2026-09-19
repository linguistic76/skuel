---
title: "Tasks+ on Phones, the /profile Hub, and One Chrome for the App — Arc Record"
updated: 2026-09-19
status: "done"
registered: 2026-09-18
ruled: 2026-09-19
---

# Tasks+ on phones, the /profile hub, and one chrome for the app — arc record

*The review outcome and build brief (v2) that the six Tasks+ / one-chrome PRs executed, with every PR's amendment
block folded in at the top. Cited by `docs/design-principles/HUB_PAGES.md`, `docs/patterns/HUB_PAGE_PATTERN.md`,
`docs/patterns/UI_COMPONENT_PATTERNS.md`, `docs/ui/ROUTE_MAP.md` and `scripts/chrome_gate.py`. What the app IS lives
in those docs; this file holds the measurements, the rulings overturned and the argument.*

**Status:** DONE 2026-09-19 — all six PRs merged the day after the review (#1373–#1378). This is the review's outcome (v2, 2026-09-18) with every PR's amendment block folded in; the v1 brief and the review's raw artifacts (reader maps, lensed proposals, judge/refuter/critic JSON, 320/375/1440 snapshots) are gitignored scratch and are not cited here.
**Owner:** Mike. **Rulings (2026-09-19):** Mike accepted every recommendation in §4, D1 included — the Calendar icon goes, "Tasks+" is the centre link and the bottom tab. Each PR runs in a fresh context.
**Ledger:** PR 1 — MERGED #1373 (2026-09-19). PR 2 — MERGED #1374 (2026-09-19). PR 3 — MERGED #1375 (2026-09-19). PR 4 — MERGED #1376 (2026-09-19). PR 5 — MERGED #1377 (2026-09-19). PR 6 — MERGED #1378 (2026-09-19). Arc CLOSED.
**Amendments from PR 6 (docs closure):** the chrome gate graduated with this record — it is `scripts/chrome_gate.py`
(paths derived from `__file__`; 65 checks + the `GET /profile` 404 probe; GREEN before and after, no `static/` change,
`CACHE_VERSION` stays v15). `HUB_PAGES.md` rewritten around the section/chrome rule (§3.5's last line); the
navbar's 28-entry "Evolution" changelog in `UI_COMPONENT_PATTERNS.md` and its "Legacy Pattern Removal" section
deleted in favour of one present-tense chrome description that points here; `ROUTE_MAP.md`'s `/home`, `/profile`
and `/ku` sections replaced by "The Tasks+ section" (there is no `/ku` route — the `ku_ui.py` log line that claimed
one was fiction, fixed; `hub_cards_from_organizers`' default `href_template` pointed at it too, now
`/explore/ku/{uid}` with its test). The accessibility-guide's Example 1 now shows the real section nav (it showed a
`ProfileDomainItem` renderer that never existed in `sidebar.py`); the skuel-ui reference's sidebar patterns lose
their emoji `icon` values (an emoji renders `help-circle` — §5 PR 1's own finding). Verification greps
(`/profile\b` outside `/profile/shared`; the dead-name list) return only `done/`, `migrations/`, `.claude/completed/`,
ADR bodies and third-party `llms.txt` — plus the three case files that record the re-rulings by name.
Deferred items registered in `deferred-work.md`: Explore's phone form + the MOC-roots ruling (D5), the doorless
surfaces census (D8) and the `enum_helpers` census in ONE case file (`tasks-plus-follow-ons.md`, with the
`ui/patterns/tabs.py` extraction, `SidebarItem.group` dividers, the D7 "Transcribe" rename and PWA first-run).
**Amendments from PR 5:** `/profile` is a real 404 (no redirect); `/profile/shared` + list fragment call
`services.sharing.get_shared_with_me` directly. The delete set's closure reached further than §3.4 listed: the
entry-reports preview was the ONLY consumer of the whole `AssessmentService` stack (service, `AssessmentOperations`,
`get_assessments_for_student_raw`, the orchestrator method, wiring, test) — deleted; `StatTile` (only `_shared.py`
drew it) and `InsightMiniCard` (zero consumers, navigated by `hx-get` on a div) went with it. The insight-card
repoint is NOT `/{domain}/detail?uid=` verbatim: the `PersistedInsight(` writer census found SEVEN domains — the six
Activity slugs plus `user_entry` (→ `/gradebook/{uid}`) — and one writer (the teacher turnaround anomaly) stamped a
*report* uid under `user_entry`; it now carries no entity (a pattern, not a page). Links go through
`entity_detail_href`. The live check found `/insights` overflowing 63px at 375 — `CardGenerator`'s header badges were
`shrink-0`; they wrap now. `CACHE_VERSION` v15. The chrome gate is 65 checks + a `GET /profile` 404 probe
(`/profile/shared` rendered for the member at every width; inbox icon the only lit item). The roadmap case file was
renamed `profile-side-search.md` → `lived-output-search.md` (heading + MOC + closure record + INDEX moved with it).
Spawned, not swept: `ui/enum_helpers.py` (~20 caller-less wrappers before this PR, 3 more after) wants a census PR.
Codex: 1 P2 accepted (a module docstring narrating the retirement — the same reflex as PR 4 round 1), then clean.
**Amendments from PR 4:** the role doors (Teaching, Admin) are centre links at **lg+**, not sm+ — measured with the four
section doors and the icon cluster: a member's bar is exactly full at 640 (670px with `px-3`; centre links are now
`px-2`), a teacher's needs 758px and an admin's 829px, so §3.3's "centre links at sm+" cannot hold in any font and the
brief's fallback ("Admin as a `/settings` row") applies below lg to BOTH role doors (`hidden lg:block` ↔ `lg:hidden`;
sign-out keeps its own `sm` pair). §3.5's tablet row is therefore Tasks+ · Library · PathSteps · Submissions only.
`/settings` had 56px of phantom vertical scroll — the STANDARD `BasePage` main carried `min-h-screen` under the 3.5rem
sticky navbar (every short STANDARD page did); deleted. `IconNavItem.page_keys` is a frozenset (the Library door
`{explore, library}`). The live graph's personas are `linguistic76` = MEMBER and `mfan0110` (`user_admin`) = ADMIN —
§2's "Admin (Mike's account)" is the second, and both were verified live. `CACHE_VERSION` stays v14 (output.css
byte-identical). The chrome gate is 60 checks (3 personas × {320, 375, 640, 768, 1440}; `/admin`, `/settings`,
`/cal/month` as real routes). Codex: 3 P2s accepted (present-tense docstrings, ROUTE_MAP §Regular User Navigation, the
hamburger checklist/catalog lines), 1 rejected by ruling (a `/profile` door — retired in PR 5).
**Amendments from PR 3:** the badge loader is `SidebarPage(badges=True)` (Tasks+ only) with `hx-trigger="intersect once"`
on the fixed desktop `<nav>` — measured live: one request per desktop Tasks+ page view, zero at 375, one on a phone page
widened to lg+ without reload, none on a second narrow/widen; the `matchMedia` fallback was not needed. The "4 of 9
fragments target nothing" count was off by one: `knowledge` DID target a row — Submissions › Knowledge shares the slug,
so a KU-mastery badge sat on a submissions page (gone with the opt-in). The Library Path Steps badge was a constant 0.
`ui/profile/domain_stats_config.py` now holds ONLY the six activity extractors (the curriculum nine + two `DomainStatus`
calculators were deleted). The chrome gate renders `/events` too (24 checks). `CACHE_VERSION` stays v14 (no static change).
**Amendments from PR 2:** the navbar box is now exactly `h-14` border INCLUDED (the brief's "57px" was the inner row
plus the wrapper border — `top-14` alone would have left a 1px overlap); `PageHeader` wraps its actions under the title
(dropping `whitespace-nowrap` alone gave a three-line button at 320); the chrome gate carries three more assertions
(sidebar top == navbar bottom at lg+, no phantom scroll on the near-empty admin page, bottom-nav content box ≥ 44px
under an EMULATED 34px inset — a real device's `env()` is unmeasured). `CACHE_VERSION` is v14.
**Amendment from PR 1's review:** the custom-renderer row (`mobile_item_renderer`, teaching student page) is NOT an `<li>` list — Codex caught that a nav list owning `role="tab"` children is an invalid tabs hierarchy; that row is a `<div role="tablist">` of the renderer's tabs, no nav, no script. The `<li>` instruction in §5 PR 1 is superseded. Also: centring re-runs on resize until the row has had a width once (a page opened at lg+ and narrowed).
**Method:** 34-agent workflow (5 readers → 4 lensed proposals → 3 judges → synthesis → 2 refuters per claim → critic);
all 34 agents complete, including 2 refuters per load-bearing claim and a completeness critic — §7 records what
they corrected, and this v2 already carries the corrections. The raw artifacts (maps, proposals, judges, result.json,
rendered snapshots at 320/375/1440, the renderer script) are gitignored scratch.

**Mike's rulings during the review (authoritative):**
- The Calendar navbar icon IS the desktop door into Tasks+ (`/cal` → month view → Tasks+ sidebar). The open question
  is only whether a door labelled "Calendar", placed in the icon cluster, is the right NAME and PLACE for the section
  labelled "Tasks+". §4 D1 puts that question with a recommendation.
- Mike is considering retiring the pages associated with the `/profile` 4-tab setup as those tabs are absorbed
  elsewhere (Activities → Tasks+, Curriculum → Library, Submissions → navbar #1371, Reports → GradeBook row #1370/#1372).

---

## 1. Verdict on the v1 brief

The trigger is real and measured, but the brief under-scoped the defect class. "Scroll the lit tab into view" is one
of five things wrong with the same component, and the brief's Q2 (one navigation or two) turns out to be the actual
design question — it decides what the row should carry before it decides how the row scrolls. The answer that every
lens converged on: fix the row's semantics and centring in the shared component; make the chrome ONE navigation with
ONE rule at every width for every role; retire `/profile`; let Tasks+ learn the hub's two good habits (native
elements, lazy-on-reveal) and refuse its bad one (an unscrollable flex tab bar).

## 2. Verified facts that changed the shape (all measured on real routes @ main 1a547f401)

**Geometry at 375 / 320 (ten Tasks+ tabs, row scrollWidth 986, scrollLeft 0 on every page):**

| Tab | x-range | lit tab visible at 375? | at 320? |
|---|---|---|---|
| Today · Weekly · Monthly | 0–286 | yes | yes |
| Tasks | 290–372 | yes | cut |
| Goals · Habits · Principles · Choices · Journal · GradeBook | 376–986 | **no** (starts off-screen) | no |

- Nothing scrolls the row (no scroll/snap/fade code anywhere). ⚠ Every pixel above was measured in the host's Noto
  Sans fallback: `--font-sans: 'Inter'` is declared (`static/css/input.css:27,165`) but Inter is never shipped (no
  `@font-face`, no `static/fonts/`, no font link), so phones render SF Pro / Roboto. Font-independent facts: the row
  is ≥2.5× a 375 viewport in every font; the six tabs from Goals on start at or past the right edge; whether a Goals
  sliver shows at exactly 375 depends on the font (none in Noto; a sliver in Liberation-like metrics; the lit Tasks
  tab itself cut in DejaVu-like metrics). The gate in §5 therefore asserts invariants, not pixels.
- The row costs 61px (45 + `mb-4`); with the 57px top bar and 64px bottom nav, fixed chrome = 182px = 22% of 812.
- `/profile` at 375: `document.scrollWidth` 417 vs 360 — the WHOLE PAGE scrolls sideways; the 4-button tab bar is
  `flex border-b` with no `overflow-x-auto`/`shrink-0` (`ui/profile/hub.py:89`). At 320 the overflow is 112px.
  The profile is a model for progressive disclosure and ARIA, **not** for tab-bar geometry.
- `/gradebook` at 320 scrolls sideways too: the `whitespace-nowrap` "Request activity report" header button
  (`adapters/inbound/user_entry_ui.py:591-597`). GradeBook chips are 30px tall, the Source select 40px.
- Navbar is `h-14` (57px) but the desktop sidebar is `fixed top-16` and content uses `min-h-[calc(100vh-64px)]` →
  7px strip on desktop; 118px phantom scroll on an empty phone page (the calc ignores the row and `pb-16`).
- Bottom nav `h-16` is border-box, so `padding-bottom: env(safe-area-inset-bottom)` (~34px on notched iPhones)
  squeezes the content box to 30px — icons clip, labels remain (emulated; needs a real device after unpark).

**Semantics.** The mobile row is `<a role="tab">` inside `role="tablist"` with no `aria-selected`/`aria-controls`/
`tabpanel`/roving tabindex (`ui/patterns/sidebar.py:395-414`). Those links navigate between PAGES — an ARIA-tabs
misuse; the accessibility-guide's own sidebar example prescribes `<a aria-current="page">` inside `<nav>`. The bottom
nav (`navbar.py:384-398`) and the journal navigator already use `aria-current`. `/profile`'s tab bar IS a correct
WAI-ARIA tabs widget (buttons, aria-controls, roving tabindex, arrow keys) — right pattern for same-page panels,
wrong pattern for the Tasks+ row. `SidebarItem.children` + `_render_accordion_item` have zero consumers and are
inaccessible (`Div role=button`, no tabindex); `alpine_section_renderer`/`alpine_mobile_section_renderer` (teaching
student page only) render `Div role="tab" @click` with no keyboard path.

**Cost.** `hx_get="/api/sidebar/badges" hx_trigger="load"` sits unconditionally on the DESKTOP sidebar div
(`sidebar.py:375-378`). htmx fires `load` regardless of visibility, and OOB swaps land in `display:none` spans → every
SidebarPage at every width (Library, Teaching, Admin, Explore, Finance…) builds a `RichUserContext` (the MEGA-QUERY)
per page view; on phones it fills invisible spans. 4 of the 9 emitted fragments (events, knowledge, path-steps on
non-Library, learning-paths) target nothing.

**Chrome by role (the reader's door graph, at review time):**
- Member desktop: no link NAMED for Tasks+; the Calendar icon (→ `/cal` month) and avatar → `/profile` → "View all"
  are the doors (2 clicks from `/explore`). Tablet (rendered at 768, `shots/*_768.png`): the desktop bar plus the
  phone row showing 8 of 10 tabs (Journal, GradeBook off-screen), no bottom nav, and — since Today is
  desktop-excluded — no Today door at all.
- Phone member: Today in the bottom nav AND the row on `/today`; Calendar (bottom) + Monthly (row) both lit on
  `/cal/month`; `/journals/{uid}` lights Calendar under a lit Journal row; `/tasks` passes `active_page="activity"`
  which no chrome item matches → nothing lights.
- Admin (Mike's account) at every width: NO bottom nav, no centre links, no icon cluster — only Admin, Teaching,
  `/submissions/journal`, Sign out via a `sm:hidden` hamburger (an `<a href="#">` whose `@click` lacks `.prevent`,
  so Enter navigates to `#`). Rendered at 768 the admin bar is brand + avatar + Sign out and nothing else: every
  section is reached by typing a URL or via `/`. The only person testing on a phone never sees the member chrome.
  Also: every admin sidebar row shows a "?" — `ADMIN_SIDEBAR_ITEMS` (and `ui/teaching/detail.py:500`) pass emoji as
  `icon`, and `Icon()` falls back to `help-circle` for any unregistered name.
- Teacher on a phone: zero doors to `/teaching/*`.
- Three "homes": login → `/today` (5 sites in `auth_ui.py`); `/` typed later → 303 `/profile` (`system_ui.py:55`,
  from the initial commit, never ruled on); brand → `/explore`. The PWA `start_url` is `/` — an installed app
  launches into `/profile`, the horizontally-overflowing page.
- `/events` has NO Tasks+ row (events pages light Monthly via `sidebar_active="monthly"`, `events_ui.py:78` +
  ten hard-coded `active="monthly"` at :106–247); the profile Activities block is its only INBOUND door from outside
  the Events pages themselves (the stats bar self-links `/events?status=…`). Retiring the hub orphans `/events`
  (and `/events/create` — the calendar links only `/events/edit`).

**Rulings archaeology (`map_rulings-archaeology.md`):** #663 "Tasks+ dropped from the navbar (activity domains
reached via the Profile hub)" — premise dies with the hub, already eroded by #1334. "No drawer, no hamburger overlay"
— a description of what efc6c94 built that hardened into a rule through three doc rewrites; no reason ever recorded;
admins already have a hamburger. Bottom nav `Div()` for admins (c06f7d214) — docstring only, no reason, no test.
ADR-050 says nothing about navigation. HUB_PAGES doctrine ("no breakpoint switching between sidebar and tabs") was
written seven weeks after SidebarPage built exactly that; it survives only by its own "within-section" carve-out,
and its Enforcement section names `/home` (no such route). The founder reversal of calendar-arc ruling 6 (#1334,
"one sidebar everywhere") has no recorded reason — that reason is the constraint any row re-cut must satisfy.

**Docs stale on this topic (fix in the closing PR):** ROUTE_MAP.md:15,29,71,85,97,136; HUB_PAGES.md:24-26,50,54,96-97;
HUB_PAGE_PATTERN.md:27,29,80-86,297; UI_COMPONENT_PATTERNS.md:82,90,96,165 (claim the row uses `TabContainer`/
DaisyUI classes, that `ACTIVITY_DROPDOWN_ITEMS` is live, that admins have no bottom nav); skuel-ui reference.md:25,
323,325-333,421 + SKILL.md:30,451-452,462; ui-css SKILL.md:145,222; ui-browser patterns-reference.md:345 +
SKILL.md:249 (`profileFocusHandler` — pinned by `tests/unit/docs/test_alpine_docs_registry.py`, so it must change in
the same PR as the deletion, with `scripts/smoke_test.py:124` and `docs/user-guides/ui-development.md:847`);
COMPONENT_CATALOG.md:60; ADR-071:118; `scripts/authed_smoke.py:17,49-50` (hits `/profile`); `user_profile_ui.py:9,152`
docstrings; `sidebar.py:6` docstring; ADR-058 § Decision :87-89 (see §6).

**Dead (grep-proven):** `ACTIVITY_DROPDOWN_ITEMS`/`DropdownItem`, `IconNavItem.letter`/`has_dropdown`/
`hide_for_teacher`, `NavItem.requires_admin` (never True), `HubContainer`/`HubContainerGrid`,
`hub_cards_from_root_organizers`, `TabContainer` (tests + 6 doc citations only), `ui/profile/_shared.py` (368 lines),
`profileFocusHandler` (skuel.js), the insight-card links to `/profile/{domain}?focus=` (a route that does not exist
→ live 404 from `/insights`), `SidebarItem.children`, and `static/js/focus_trap.js` — loaded on every BasePage
(`base_page.py:112`) AND precached by the service worker with zero consumers (its Alpine half died in c06f7d214).
Same defect class elsewhere: `/groups`' tab bar is an inline `display:flex; width:100%` with no overflow rule
(`ui/groups/hub.py:25-28`) — bounded at 4 tabs, and a second consumer of the roving-tabindex widget.

## 3. The recommendation (all four lenses converged on this core)

### 3.1 Tasks+ mobile form (Q1, Q3, Q4)
Keep the scrolling row — it is the least chrome that still shows the siblings and works without JS — but rebuild it
as what it is, in `ui/patterns/sidebar.py`'s mobile block:

    <div class="section-nav lg:hidden mb-4">
      <nav aria-label="Tasks+">
        <ul role="list" class="flex overflow-x-auto gap-1 border-b border-border list-none m-0 p-0">
          <li class="shrink-0"><a href="/tasks" aria-current="page" class="…">…

- `aria-current="page"` set server-side (`item.slug == active`); `role="list"` restores list semantics that
  `list-none` strips in VoiceOver; `shrink-0` is the lesson from the hub's overflow.
- **Centring the lit link:** one small parse-time inline `<script>` after the nav that finds `[aria-current="page"]`
  and sets the `ul`'s `scrollLeft` (never `scrollIntoView`, which scrolls ancestors). Runs before Alpine's deferred
  bundle → no post-paint jump; JS off → a plain scrolling list. Every CSS-only route was tried and fails
  cross-browser (`scroll-snap mandatory` snaps back after user scroll; `scroll-initial-target` is Chromium-only).
  This needs Mike's yes (D4) because it is JS outside Alpine — argued as a one-shot layout enhancement, not UI state.
- **Overflow affordance:** keep the native scrollbar (do NOT add `scrollbar-none`), plus a right-edge fade shown only
  while the row overflows and is not at its end. My recommendation: the same 10-line script stamps `data-overflow` at
  load and toggles `data-at-end` on a passive scroll listener, and CSS masks on those attributes. The synthesis's
  alternative — a CSS scroll-driven-animation fade under `@supports (animation-timeline: scroll())` — is verified in
  Chrome 153 only; prefer the plain attribute version and skip the animation.
- Rejected and priced: "More" overflow (server cannot know N; promoting the lit item reorders per page); drawer
  (hides ten siblings behind a tap; runner-up only if a real device shows the row is still too much chrome);
  temporal lenses into the bottom nav (eight rows still span 290–986px); `<select>` (WCAG 3.2.2 change-on-input);
  wrapping chip groups (zero JS, always visible, but 150–200px of in-flow chrome on the first screen); one-DOM
  in-flow disclosure (biggest deletion, but phones have no section nav until Alpine boots — runner-up on the
  deletion axis).
- Badges (Q4): none on the phone row — eleven counts widen a 375px row and cost a MEGA-QUERY; the phone's
  cross-domain glance is `/today`. The loader becomes opt-in (`badges: bool = False`, Tasks+ passes True) with
  `hx-trigger="intersect once"` on the fixed desktop `<nav>` (a `display:none` element never intersects, so phones
  make no request); fallback if `intersect` misbehaves on a fixed element: `load[window.matchMedia('(min-width:64rem)').matches]`.
  The handler emits exactly `ACTIVITY_SIDEBAR_ITEMS ∩ DOMAIN_STATS_CONFIG`, drift-pinned by a test; the never-targeted
  knowledge/path-steps/learning-paths block goes (Library's lone path-steps badge is the one visible casualty).
- Touch/geometry (Q3): sidebar `top-16` → `top-14`; delete `min-h-[calc(100vh-64px)]`; bottom nav `h-16` →
  `min-h-16` with `pb-[calc(4rem+env(safe-area-inset-bottom))]` on main and the offline banner; GradeBook header
  action drops `whitespace-nowrap`, chips `min-h-[36px]`, select 44px. Snapshot gate on every chrome PR: 320/375/1440
  headless renders of `/today`, `/tasks`, `/gradebook`, `/cal/week` asserting `document.scrollWidth == clientWidth`
  and the lit link fully visible.
- Also in the component: delete `SidebarItem.children` + `_render_accordion_item`; delete `TabContainer` (+ its
  test class and the six doc citations, two of which falsely say the row uses it); desktop wrapper `Div
  role=navigation` → `Nav` with `aria-current` on rows; drop the doubled `aria_hidden` kwarg; render no mobile nav
  when `items` is empty (Explore draws an empty bordered strip today).

### 3.2 One navigation, one rule (Q2, D1)
**Rule:** the global chrome (bottom nav <sm, centre links ≥sm — both derived from `ICON_NAV_ITEMS`, as today) carries
exactly ONE door per SECTION, lit for the whole section by a section key; the row/sidebar carries the section's PAGES,
lit by slug. A section door's href is the section's landing, which is also the row's first page — **that landing is
the one sanctioned overlap** (on `/today` the Tasks+ door lights as the section and the Today row lights as the page:
two levels of one navigation, not a duplicate). Beyond the landing, no URL appears in both. The critic caught the
first draft of this rule contradicting its own corollary; the anti-duplication test in PR 4 encodes THIS version.
**Section keys must cover the landing:** the Library tab lands on `/explore/library`, which lights `explore`, while
`/library/*` lights `library` — under the rule as first written the Library tab would never light on its own landing
and the brand's `/explore` would light nothing. PR 4 keys the Library door on a section-key SET (`explore` +
`library`) until D5 rules whether Explore and My Library are one section.

- Bottom nav = **Tasks+** (→ `/today`, page_key `activity`) · Library (→ `/explore/library`) · PathSteps ·
  Submissions — four tabs (93px at 375, 80px at 320), identical for every authenticated role. Anonymous gets the two
  `requires_auth=False` items (today `Div()`). Deleted: `_CALENDAR_TAB`, `_calendar_button`, the Today item as such,
  `include_today`, the sr-only "Go to X" span (accessible name is "TodayGo to Today" today).
- **Desktop door — Mike's ruling honoured, its open question answered:** the door is NAMED for the section and PLACED
  with the other section links — a "Tasks+" centre link, first, from the same spec as the tab. The Calendar icon then
  duplicates the Monthly row and goes. #663 is overturned (its only premise is the hub). The 640–1023 band gains the
  door it never had. → **D1.**
- `render_activity_sidebar_page` keeps `active_page="activity"` (dead today — nothing matches it) and loses the
  parameter; the three overrides go (`today_routes.py:103`, `calendar_ui.py:101`, `journals_routes.py:1150` — only
  these; `journals_routes.py:381,1043` are BasePage discussion pages, NOT Tasks+ pages). That kills every measured
  duplicate: Today lit twice on `/today`, Calendar+Monthly on `/cal/month`, Calendar under Journal, nothing on `/tasks`.

### 3.3 Admin and teacher (Q5, D2)
One navbar for every role. Delete the admin branch of `create_navbar`, `_admin_right_section`, the hamburger, the
bottom-nav `is_admin` gate, `base_page.py:219`'s admin exclusion and the admin hub at `/`. Admin/Teaching become
role-gated doors inside the one chrome: a `NavItem("Admin", "/admin", "admin", requires_admin=True)` (the field
exists, never set; note that the early-return admin branch must be deleted FIRST or the item renders for no one) and
Teaching's `hide_for_admin` flips; on phones both are `sm:hidden` rows on `/settings`. `/` → 303 `/today` for
everyone; `auth_ui.py`'s five `"/" if admin` splits collapse. Today the admin `/` hub is the admin's ONLY desktop door
to `/teaching/students` and `/submissions/journal`, so PR 4 must ship the Teaching link for admins and the Submissions
centre link in the same change — and `avatar → /settings` with the sign-out and role rows in the SAME PR (not the
retirement PR), or an admin/teacher below 640px has no door to `/admin` or `/teaching/*` in between, and in PWA
standalone mode there is no address bar to type one. Overturns c06f7d214/c75b8b231 — neither recorded a reason beyond
"admins had no navigation on mobile", and the compensating hamburger is `sm:hidden` and navigates to `#` on Enter.

### 3.4 Retire `/profile` (D5 is the only sub-question)
Retire, no redirect. One replacement per unique job:
- landing → `/today` (matches the login redirect, ADR-058 and the PWA `start_url`; the vacuous
  `test_auth_routes.py:399-413` becomes a real 303 assertion);
- phone sign-out → `signout_row()` moves verbatim into `navbar.py` beside `_signout_button` (both halves of the
  one-door-per-width contract in one file) and renders FIRST on a new `ui/settings/page.py` shell, outside any
  HTMX fragment or `x-cloak`;
- avatar → `/settings` ("Account"; zero inbound hrefs today) — ships in PR 4; the avatar's active key changes from
  `profile` to `settings` (`settings_routes.py:64` already passes it) or it never lights on its own page;
  `ui/profile/preferences.py` → `ui/settings/`;
- `?tab=curriculum` ×3 → `/library`, `?tab=reports` → `/gradebook`;
- `/profile/shared` + list-fragment keep their URL and call `services.sharing.get_shared_with_me` directly
  (`ProfileOrchestrator` deleted; its two surviving tests at `test_profile_orchestrator.py:177-197` are re-homed
  onto the sharing service, not deleted); `adapters/inbound/user_profile_ui.py` stays for those two routes;
  `/api/sidebar/badges` moves to its own module beside the sidebar (`adapters/inbound/sidebar_badges_ui.py`) and
  `ui/profile/badges.py` + `domain_stats_config.py` → `ui/activities/` (they are Tasks+ domain stats);
  the insight-card `/profile/{domain}?focus=` 404s → `/{domain}/detail?uid=`; `scripts/authed_smoke.py` page list
  updated;
- **Events gets a Tasks+ row** (`SidebarItem("Events", "/events", "events", icon="calendar")` after Habits);
  delete `ActivityUIConfig.sidebar_active` AND repoint the ten `active="monthly"` in `events_ui.py`;
- roadmap re-rulings: `profile-side-search.md` → the search home becomes `/submissions/history`,
  `/library/exercises`, `/gradebook`; `parked-features.md` "Profile UI sibling" → GradeBook sibling;
  `done/search-facet-redesign.md:38` amendment;
- previews die with no replacement (the cross-domain top-3-by-priority glance has no other home; if missed later,
  its home is a `/today` section, not a revived hub).
- Deleted: `ui/profile/hub.py`, `_shared.py`, the five `*_BLOCKS`/panel modules, `HubAccordionBlock/List`,
  `HubContainer/Grid`, `hub_cards_from_root_organizers` (keep `hub_cards_from_organizers` — live at
  `user_entry_ui.py:800`), eight preview routes, `profileFocusHandler`, `test_profile_orchestrator.py`,
  `PROFILE_SIDEBAR_ACCESSIBILITY_TEST_GUIDE.md`, `ui/profile/README.md`.

**What Tasks+ learns from the hub:** native first (`nav`/`ul`/`a`; `<details>` if grouping is ever wanted);
lazy-on-reveal (`intersect once` — now the badge gate); real URLs beat `?tab=`; chrome never waits for Alpine (the
sign-out lesson). **Not copied:** roving tabindex on links (a tabs-widget technique); `x-cloak` around chrome;
"View all" inside `<summary>`; three doors to one page. The hub's one correct widget — the WAI-ARIA tab bar
(`hub.py:80-133`) — is worth extracting to `ui/patterns/tabs.py` WITH the `overflow-x-auto` + `shrink-0` it forgot,
for the teaching student-detail page whose same-page switch IS the tabs job (its current rows are
keyboard-inoperable). That is a follow-on, not part of this arc (see §5).

### 3.5 App shape after
| Width / role | Top bar | Global nav | Within a section |
|---|---|---|---|
| Phone <640, every role | SKUEL(→/explore) · Askesis · Inbox · Bell · Avatar(→/settings) | bottom: Tasks+ · Library · PathSteps · Submissions | the row (Tasks+: Today Weekly Monthly Tasks Goals Habits Events Principles Choices Journal GradeBook) |
| Tablet 640–1023 | same + centre links Tasks+ · Library · PathSteps · Submissions · [Teaching] · [Admin] · Sign out | (no bottom nav) | the row |
| Desktop ≥1024 | same | centre links | 256px collapsible sidebar, badges on Tasks+ only |

Homes: two — landing `/today` for all (login, `/`, PWA launch); brand `/explore`. Account = `/settings`
(preferences, devices, role rows, phone sign-out). Retired: `/profile` hub (+8 preview routes), admin hub/navbar/
hamburger, Calendar icon+tab, Today tab, the ARIA-tabs row, `TabContainer`, the per-page MEGA-QUERY on phones.
HUB_PAGES doctrine rewritten: Tasks+ IS a section; sections have chrome (bottom nav + row/sidebar); a hub page earns
its place only when it carries what the section nav cannot.

## 4. Decisions for Mike (recommendation first; D1–D3 gate PR 4 and PR 6; PR 1–3 need none)

- **D1 — Replace the Calendar icon with a "Tasks+" centre link (first among section links, → `/today`, lit on every
  Tasks+ page) and label the bottom tab "Tasks+" instead of "Today"?** Recommend YES. It deletes the icon your ruling
  named as the desktop door, so it needs your explicit yes. Alternatives: (a) keep the Calendar icon as well, lit by
  the section key so two items never light together; (b) keep the label "Today" — then the tab must not light on
  `/goals`, leaving the section with no lit global item (today's state on `/tasks`).
- **D2 — Bottom nav: four identical tabs for every role (Teaching/Admin as `sm:hidden` rows on `/settings`), or at
  most one role tab?** Recommend four identical. Your phone then shows exactly the member chrome; no
  teacher-on-phone persona is verified; a role tab is a one-field addition later.
- **D3 — Chrome breakpoint: keep `sm` (640) for the bottom-nav/centre-links split?** Recommend keep; revisit after
  real-device checks. Unifying at `lg` is a wholesale, unmeasured change for 640–1023 that no ruling asks for.
- **D4 — Accept one parse-time inline `<script>` (outside Alpine) to centre the lit link and stamp the overflow
  attributes?** Recommend YES. Alternatives: `x-init` on the `ul` (visible jump after first paint because Alpine is
  deferred); no centring (today's state).
- **D5 — Library and Explore: two names, two keys, one section?** The navbar "Library" lands on the public catalog
  (`/explore/library`, key `explore`); the sidebar "Library" is the personal MOC (`/library`, key `library`); the
  brand lands on `/explore`; and on phones the Explore sidebar (graph + Learning/Saved/Completed lists) does not
  exist at all — it is desktop-only `extra_sidebar_sections`, and `/explore/library` is the Library tab's landing.
  Recommend: keep the `/library` and `/submissions` MOC roots for now; PR 4 keys the Library door on both keys;
  rename the sidebar title "My Library"; and rule Explore's phone form (accept absence, add an
  `extra_mobile_sections` equivalent, or fold Explore into the Library section) as its own PR after the arc.
- **D6 — Re-cut the chrome into loop phases (Tasks+ · Study · Submissions · GradeBook, GradeBook out of Tasks+,
  brand → `/today`) as a later arc?** Recommend NOT now. It reverses #1372 (HEAD) and the six-day-old ADR-058
  amendment, and your reason for reversing calendar-arc ruling 6 (#1334) is unrecorded — that reason is the
  constraint any row re-cut must satisfy. PR 8's group dividers give the desktop sidebar the loop's structure cheaply.
- **D7 — Rename Submissions › Journal (`/submissions/journal`, persists no UserEntry per ADR-073) to "Transcribe" so
  "Journal" means two things instead of three?** Recommend YES, own S PR.
- **D9 — Ship Inter or drop the declaration?** `--font-sans: 'Inter'` is declared and never shipped, so every
  device renders its fallback and no row measurement is portable. Recommend drop the declaration (system-ui) in
  PR 2 unless you want the font — then it must be self-hosted and precached.
- **D8 — The ten doorless surfaces (`/groups`, `/lifepath`, `/insights`, `/self-checkin`, `/ku`, `/journals`
  discussions, `/search`, `/pathways`, `/activity-review`, `/analytics`) and the caller-less
  `ProfileHubData`/`UserStatsAggregator.get_profile_hub_data` stack: staged (door) or abandoned (delete)?**
  Recommend a follow-on census PR after PR 7; none is a hub dependency; each needs a product ruling.

## 5. PR plan (ordered, sized; every chrome PR carries the 320/375/1440 snapshot gate and `./dev css-prod`)

0. **Every chrome PR:** bump `CACHE_VERSION` in `static/service-worker.js` (cache-first serves the old `/static/`
   bundle to installed PWA clients until the version changes — the discipline CLAUDE.md names); `./dev css-prod`;
   the snapshot gate at 320/375/768/1440 asserting `document.scrollWidth == clientWidth` and the centring invariant
   (the `[aria-current]` link lies inside the row's `clientWidth`) — never a pixel position (D9).
1. **PR 1 (S) — the row is a nav list.** `sidebar.py` mobile block → `nav/ul/li/a[aria-current]` + inline centring
   script + `data-overflow`/`data-at-end`; `.section-nav` fade in `input.css`; delete `children`/accordion,
   `TabContainer` (+ its module `ui/components/nav.py`, test class, registry line, the 8–9 doc/skill citations);
   `Nav` wrapper + desktop `aria-current`; no empty mobile nav; fix `sidebar.py:6` docstring. ⚠ Cover BOTH producers:
   the `mobile_item_renderer` branch (`sidebar.py:384-386`, the teaching student page) bypasses the default block —
   it must emit `<li>` items too, and the centring script is a no-op inside that page's `x-cloak` wrapper, so scope
   the script to the default branch. Also replace the emoji `icon` strings in `ui/admin/layout.py` and
   `ui/teaching/detail.py:500` with lucide names (every admin row renders "?" today). Tests: new
   `tests/unit/ui/test_sidebar_mobile_nav.py`; re-anchor `test_gradebook_ui.py:105`. Needs D4 only if Mike rejects
   the script (then `x-init`).
2. **PR 2 (S) — phone geometry + touch targets.** `top-14`; delete the min-h calc; safe-area `min-h-16` + calc
   padding on nav, main, banner; GradeBook header/chips/select; delete `static/js/focus_trap.js` (+ its precache
   entry and the `base_page.py` script tag); D9's font ruling. Layout assertions.
3. **PR 3 (S) — badges opt-in + Events row.** `badges` param + `intersect once`; handler = `ACTIVITY_SIDEBAR_ITEMS ∩
   DOMAIN_STATS_CONFIG` + drift test; Events row; delete `sidebar_active` + the ten `active="monthly"`; rewrite
   `test_activity_ui_factory_sidebar_slug.py`; verify with a live server at 1440 (fragments present) and 375 (no
   `/api/sidebar/badges` request).
4. **PR 4 (M) — one navbar, one rule** (needs D1–D3, D5's key ruling). `nav_config` (Tasks+ item, Admin `NavItem` —
   only works once the admin early-return branch is gone, so delete that first; Library section-key set; dead
   fields), `navbar.py` (admin branch + hamburger, Calendar icon/tab, `include_today`, sr-only span, bottom nav for
   all + the anonymous pair, avatar → `/settings` with key `settings`), `base_page.py:219` (drop BOTH halves of the
   padding gate — admins AND anonymous now have a bottom nav), `system_ui.py` + `admin_hub.py`, `auth_ui.py` ×5,
   the `ui/settings/page.py` shell carrying the phone sign-out row + `sm:hidden` Admin/Teaching rows, drop the
   `active_page` param + its three overrides. Tests: rewrite `test_navbar.py`; one-spec-both-surfaces +
   anti-duplication invariant over every `*_SIDEBAR_ITEMS` (landing overlap sanctioned); a real `/` → `/today` test.
   ADR-058 amendment naming BOTH clauses (:87-88 "admins continue to /"; :89 the Today item's key/icon). Measure the
   admin tablet bar at 640 (six links + icons may crowd; fallback: Admin as a `/settings` row only). Render `/today`,
   `/cal/week`, `/admin`, `/settings` and a pure-teacher persona at 375 and 768 BEFORE merging — none has been
   rendered as a real route yet (the review's "lit" variants were class-swapped `/tasks` copies).
5. **PR 5 (L) — retire `/profile`.** Everything in §3.4 not already shipped by PR 4; roadmap re-rulings; the
   `profileFocusHandler` deletion with its three doc/script pins in the same PR (the Alpine docs registry test fails
   otherwise); `./dev bloat`, `./dev docs-links`. Largest blast radius (~25 docs/skills cite the hub; four modules
   move; SKUEL027/032 must stay clean; the post-commit docs hook will flag more than the census lists).
6. **PR 6 (S) — docs closure.** HUB_PAGES rewrite, ROUTE_MAP, HUB_PAGE_PATTERN, UI_COMPONENT_PATTERNS, skuel-ui +
   accessibility-guide Example 1, activity-domains, learning-loop, ui-development, PROMETHEUS_METRICS,
   ROUTE_AUTH_REQUIREMENTS; memory note.
7. **Follow-ons, each its own PR, after the arc:** `ui/patterns/tabs.py` extraction + adoption by BOTH live
   consumers — the teaching student-detail page (keyboard-inoperable rows) and `/groups` (non-scrolling inline tab
   bar) — Mike sees the 1440 snapshot first; `SidebarItem.group` + desktop dividers (By time / By kind / Journal ·
   GradeBook); the "Transcribe" rename (D7); Explore's phone form + the MOC-roots ruling (D5); the
   doorless-surfaces census (D8); PWA first-run — `AuthPage` renders no manifest/service-worker/offline banner, so the
   app is not installable before login and a standalone launch on an expired session lands on chrome-less login.

## 6. Rulings overturned, with the argument
| Ruling | Argument |
|---|---|
| #663 (022d54574) Tasks+ off the navbar "reached via the Profile hub" | the only premise is the hub being retired; already half-false since #1334 |
| c06f7d214 / c75b8b231 admin gets no bottom nav + a separate navbar/hamburger | the only recorded reason is "admins had no navigation on mobile", which the one chrome answers better; the hamburger is `sm:hidden` and navigates to `#` on Enter; the owner never sees the member chrome. ADR-058 :87-88 ("admins continue to /") is amended with it |
| #776 / #1323 / #1334 Events lights Monthly, no row | #776 was "not important now" (a deferral); the hub was `/events`' only door; `/events/create` exists and the calendar has no create door |
| "No drawer, no hamburger overlay" | not overturned — the row stays; the sentence is rewritten to state the reason (siblings visible, JS-free) |
| HUB_PAGES "no breakpoint switching" / "/profile is THE main hub" | rewritten: Tasks+ IS a section; a hub page earns its place only when it carries what the section nav cannot |
| Mike's in-review "the Calendar icon is the desktop door" | honoured as fact; D1 asks whether the door should carry the section's name and place |

## 7. Verification status (final — 2 refuters per claim, repo-truth + consequence, then a completeness critic)
The refuters were told a 90%-right claim is refuted, so 9 of 10 claims were "refuted" — every one a precision
correction that this v2 now carries (aria-selected exists in the two Alpine renderers; `IconNavItem` lines :46-61;
`requires_admin` is dead until the admin early-return goes; hub.py:22 is the only INBOUND `/events` door;
`journals_routes.py:381` is the journals landing, not a discussion; ADR-058 :87-89 must be amended; the hamburger
renders `href="#"`; `/profile` inbound list gains the insight cards, the inbox link and `authed_smoke.py`;
`TabContainer` has 8–9 doc citations; the pixel geometry is font-specific). C10 (CSP report-only with
`'unsafe-inline'`, an inline script already ships in `base_page.py`, which Tailwind classes already compile) survived
both lenses. Nothing structural fell.

The critic's findings, all folded in above: the "one rule" contradicted its corollary (fixed, landing overlap
sanctioned); the Library tab's key never matches its landing (D5 + PR 4 key set); PR 4 → PR 5 stranded admins and
teachers on phones (avatar/settings moved into PR 4); the anonymous half of the padding gate; `CACHE_VERSION` bumps;
where the badges endpoint lives after the hub; the avatar's active key; the unshipped Inter font (D9 + invariant
gate); Explore has no phone form at all (D5); admin emoji icons render "?"; dead `focus_trap.js`; `/groups` shares the
profile's tab-bar defect; PWA first-run is chrome-less. Still UNRENDERED as real routes: `/today`, `/cal/week`,
`/cal/month`, `/journals/{uid}` (all `max-w-none` + `calendar.css`), `/admin`, `/settings`, `/groups`, `/explore`
pages, a pure-teacher persona, and any offline state — PR 4's gate covers them before D1/D3 are acted on.
The verdict and critic JSON are gitignored scratch; this section is their record.

## 8. Constraints kept from v1
- One `SidebarPage` for every sidebar — the improvement lands in the shared component, never a Tasks+ fork.
- Alpine for UI state, HTMX for server calls, FastHTML markup (the one inline script is D4, argued above).
- New Tailwind utilities need `./dev css-prod` (deletions stale output.css too). No dark mode exists.
- Verify at 375×812, 320 AND 1440. **The gate is `scripts/chrome_gate.py`** (built in PR 1, graduated in PR 6): real
  routes (`/today`, `/tasks`, `/events`, `/gradebook`, `/cal/week`, `/settings`, `/admin`, `/profile/shared`) +
  the admin sidebar page, mocked services, rendered in headless Chrome at 320/375/768/1440 — phone widths through an
  iframe, because headless Chrome clamps its window to 500px — asserting `scrollWidth == clientWidth`, the
  `[aria-current]` link inside the row, the right half hidden/visible per breakpoint, and zero `help-circle` fallback
  icons, three personas (member, teacher, admin) at 320/375/640/768/1440, and a `GET /profile` → 404 probe.
  `uv run python scripts/chrome_gate.py <out_dir>` — exit 0 = green. Every later chrome PR runs it BEFORE and AFTER.
- Real-device unknowns until the DigitalOcean unpark: safe-area behaviour, `100vh` in standalone mode, scroll
  restoration on back, every screen-reader announcement (inferred from role semantics, not recorded).
