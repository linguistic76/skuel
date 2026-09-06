---
title: "Parked Features — Memory-Only Until Now"
updated: 2026-09-06
status: "parked"
registered: 2026-08-28
trigger: "Mike schedules each — feature work, never self-scoped"
check: "the four git grep absence checks in the case file, all empty"
---

# Parked Features — Memory-Only Until Now

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

Four feature-shaped threads Mike ruled *build later, from a stated design* — parked under the
2026-08 stabilize directive. Each carries: what it is, why the deleted implementation is not the
starting point, the design already stated, the ruled constraint, and a check that it is still
absent. **Trigger for all four: Mike schedules it** — none is a data threshold, and none may be
self-scoped.

Each thread names live code as of 2026-09-05. Paths decay; the *premise* under each constraint is
what to re-verify, not the line number.

## Activity ledger (ruled 2026-06-11)

**What it is.** A cross-domain activity *ledger* — raw, event-grained, chronological ("Completed
habit: Exercise · 2h ago", "Assessed alignment as mostly_aligned"). Complementary to
`ActivityReport` (Tier D synthesis *about* activity), not competing with it. Two consumers:

1. **Profile UI sibling** — a recent-activity feed alongside the recent-reports section
   (`render_recent_reports_section`, `ui/patterns/generate_report.py`).
2. **`ActivityReport` evidence input** — the raw material report generation synthesizes from
   ("3 alignment assessments this period, trending up" beats entity counts). Rhymes with
   Knowledge Substance: substance accrues from lived activity; the ledger IS that activity,
   itemized.

**Why the deleted code is not the starting point.** `PrinciplesAlignmentService.get_recent_activity`
(deleted #286) predates ADR-030 and read only `alignment_history` — the single-track store whose
writer was staged — while missing `dual_track_checkins`, the LIVE assessment store. Expressions
used `principle.updated_at` as a proxy timestamp, so per-event times were fabricated, and each
call did a full-scan Python synthesis. Its habits sibling
(`habits.completions.get_recent_activity`) never existed at all — only phantom mocks in tests,
also deleted. Restoring it would import all four defects.

**Constraint.** Design from the LIVE stores and `{domain}.{action}` events (`dual_track_checkins`,
habit completions, choice records; `PrincipleAlignmentAssessed` already publishes) across all 6
Activity Domains **at once** — a cross-domain surface is all-or-nothing, never piecemeal. Start
from a design doc or ADR, never from git-restoring the #286 deletions.

**Check:** `git grep -n -i "activity_ledger\|ActivityLedger" -- core/ ui/ adapters/` → empty.

## Interest signal + adoption/gravity — ONE thread (ruled 2026-06-11, unified 2026-08-22)

**What it is.** An interest-aware recommendation signal derived from live stores — `VIEWED` edge
recency/frequency, tags of engaged entities, or an embedding centroid of touched content —
feeding LP/content ranking.

**Why the deleted facet surface is not the starting point.** Bloat campaign 4 (#288) deleted the
UserContext facet-personalization surface (`evaluate_against_facets`, `update_facet_affinity`,
`add_facet`, `get_facet_recommendations`, `get_top_facets`, the `facet_profile` /
`facet_affinities` / `facet_interaction_history` / `content_type_preferences` fields, and the
`learning_recommendation_engine` interest-match branch). Mike chose *delete + record forward
thread*, for three reasons that still hold:

1. **Session-local by design** — the profile lived in the cached UserContext dict, which
   `DebouncedContextInvalidator` (`core/services/user/debounced_invalidator.py`) wipes on every
   domain event. Learned affinities could not survive normal use without a persistence redesign.
2. **The graph already tracks interest durably** — `:VIEWED` edges carry `view_count` /
   `last_viewed_at` (`adapters/persistence/neo4j/_learning_state_mixin.py`), and
   `UserKnowledgeProfile` carries `interested_uids` / `bookmarked_uids`
   (`core/services/user_progress_service.py`), alongside substance.
3. **Embeddings subsume tag-overlap matching** semantically (ADR-068, shipped #278).

**Adoption/gravity is the same thread.** The ownership bundle (ADR-086 § 2) deleted the four
`HAS_*` "gravity" writers whose semantic was "user pulled this entity into their orbit" —
adoption/engagement, NOT ownership. Mike ruled that unified with this one.

**Constraint.** ONE engagement signal, never two edges. Never resurrect the #288 facet code, and
never resurrect the retired gravity edges `HAS_TASK` / `HAS_GOAL` / `HAS_HABIT` / `HAS_EVENT` /
`HAS_CHOICE` / `HAS_PRINCIPLE` / `HAS_KU` (the live `HAS_*_TEMPLATE` family is a different edge and
stays). Starting point when scheduled: `_learning_state_mixin` VIEWED data + vector search.

**Check** — three greps, all empty today. SKUEL030 makes `RelationshipName` the only door to a
Cypher edge, so the enum *member* is what to watch, not free-text mentions (two comments still
name the edges historically):

```
git grep -n -i "interest_signal\|engagement_signal\|facet_affinit" -- core/ ui/ adapters/
git grep -n -E '^\s+HAS_(TASK|GOAL|HABIT|EVENT|CHOICE|PRINCIPLE|KU)\s*=' -- core/models/relationship_names.py
git grep -n -E '^\s+HAS_(GOAL|HABIT)\s*=' -- core/models/enums/metadata_enums.py
```

The third covers the lowercase semantic vocabulary, where the same idea survived as two
reader-less `RelationshipType` members until #1179 deleted them.

## Icon provider swap (ruled 2026-06-29)

**What it is.** Make icons hexagonally provider-swappable (Lucide ↔ HeroIcons).

**Current state — the seam exists, but only half of hexagonal is built.** `Icon()`
(`ui/components/icon.py`) is a real chokepoint (good, and rare), but **the port leaks the
adapter's vocabulary**: every call site passes a lucide kebab name (`Icon("chevron-down")`)
straight through to a single `ICON_PATHS` registry. There is no provider concept and no toggle.
Lucide and HeroIcons share neither names nor coordinate systems, so even a build-time swap breaks
every call site whose name does not exist in the other set. `gen_icons.py`'s "switch source"
docstring note only changes where *lucide* geometry is harvested from — still lucide. Count the
leak with `git grep -oh -E 'Icon\("[a-z0-9-]+"' -- ui/ adapters/ | sort -u | wc -l` (62 distinct
names across 128 literals on 2026-09-05); the number moves, the leak is the premise.

**Design when wanted.**

- **Port:** an `IconName` StrEnum of *semantic* names (EXPAND, COLLAPSE, KNOWLEDGE_UNIT, NEXT…).
  Call sites pass `IconName.EXPAND`, not `"maximize-2"`.
- **Adapters:** one generated `dict[IconName, str]` registry per provider (`_icons_lucide.py`,
  `_icons_heroicons.py`), each with a `SEMANTIC_MAP` of `IconName →` that provider's source name
  (EXPAND → `maximize-2` lucide / `arrows-pointing-out` heroicons). `gen_icons.py` grows a
  `--provider` flag and a heroicons harvest path.
- **Selection:** `_ACTIVE_PROVIDER` resolved at startup from `ICON_PROVIDER=lucide|heroicons`, the
  same env-driven adapter pattern as `INTELLIGENCE_TIER`. Per-USER runtime switching is heavier
  (the provider can no longer be a module constant) — start env-level.
- Renderer and call sites otherwise change only in passing `IconName.X`.

**Validation already shipped** (#454 `329d36f6`, broadened #455 `5cf039c6`):
`gen_icons.py::icon_name_literals()` plus a build-time assertion and
`tests/unit/scripts/test_gen_icons.py` enforce that every icon-intent literal resolves to a
committed registry key, closing the silent help-circle fallback gap. `ICON_INTENT_RX` covers four
shapes: `Icon("…")`, `icon="…"`, `"icon": "…"` (the most common config shape — section/template
specs → `form_generator` → `Icon(icon_name)`), and `_icon_*("…")` wrappers. Dynamic forms
(`Icon(var)`, `icon=var`) are unvalidatable by construction. When the swap lands this generalizes
to the two port invariants: (1) every call uses a defined `IconName` — mostly a mypy error once it
is an enum; and (2) **every adapter is total**, `set(provider.paths) == set(IconName)` for *each*
provider. Invariant (2) is the one that actually makes a swap safe — it is what guarantees no
blank icon for any name the app uses.

**Constraint.** No swap machinery before a second provider is actually wanted (One Path Forward).
Do not bolt a second name vocabulary onto the single `ICON_PATHS`.

**Check:** `git grep -n "IconName\|ICON_PROVIDER" -- ui/ core/` → empty.

## Activity-templates re-homing (ruled 2026-07-06, shape undecided)

**What it is.** The 6 Activity Templates (`TASK_TEMPLATE`, `GOAL_TEMPLATE`, `HABIT_TEMPLATE`,
`EVENT_TEMPLATE`, `CHOICE_TEMPLATE`, `PRINCIPLE_TEMPLATE`) should be modelled and surfaced
**somewhere of their own**, not left living implicitly under PathStep/curriculum. Beyond that
direction Mike explicitly did not want a shape forced yet.

**Current state — what "their own home" is a move away from.**

- Templates are **PS-owned**: authored inside PathSteps and TEACHER-gated
  (`require_role=UserRole.TEACHER`, `adapters/inbound/_pathstep_template_routes_helpers.py`).
  They spawn real user-owned instances on PathStep *engagement*.
- Templates are **invisible to search**: absent from `SearchRouter._SEARCHABLE_DOMAINS`
  (`core/orchestrator/search_router.py`), and absent from the `/search` Types facet —
  `_ENTITY_TYPE_OPTIONS` (`ui/search/components.py`) now lists only the 6 activity instance types,
  Ku/PS/LP having moved to the NOUS facet.

**Adjacent question, raised in the same thread and NOT ruled.** The `/search` Types facet is an
entity-type filter over existing instances (mostly the user's own). It does the "filter what
exists" job, not the "discover curriculum by domain" job. Whether that facet — or templates —
should ever serve content-discovery-by-domain is an open, distinct design question. Do not
conflate it with the re-homing ruling.

**Constraint.** A separate arc — do not fold this into search/nous work. Entities stay orthogonal:
no coupling edges added to make templates "belong" somewhere.

**Check:** `git grep -n "_TEMPLATE" -- core/orchestrator/search_router.py` → empty (still
unsearchable); no templates hub under `ui/`.
