---
updated: 2026-07-29
---

# ADR-030: Dual-Track Assessment Pattern (BaseAnalyticsService Extension)

**Status:** Accepted
**Date:** 2026-01-18
**Author:** Claude (with Mike)
**Category:** Pattern/Practice

## Context

SKUEL's core philosophy states: **"The user's vision is understood via the words they use to communicate, the UserContext is determined via user's actions."**

This insight was first implemented in LifePath's `WordActionAlignment` and recently extended to Principles via `assess_with_user_input()`. The pattern is generalizable across all Activity Domains.

### The Pattern

| Track | Source | Data |
|-------|--------|------|
| **Vision** | User self-assessment | "I feel aligned with integrity" |
| **Action** | System measurement | Goals/habits/choices expressing the principle |
| **Insight** | Gap analysis | Perception vs reality comparison |

### Current Implementations

1. **LifePath** - `WordActionAlignment` (existing)
2. **Principles** - `assess_with_user_input()` in PrinciplesAlignmentService
3. **All 6 Activity Domains** - Dual-track via `_dual_track_assessment()` template

### Activity Domain Implementations (January 2026)

| Domain | Method | Level Enum | System Metrics |
|--------|--------|------------|----------------|
| **Principles** | `assess_alignment_dual_track()` | `AlignmentLevel` | Expression count, goal alignment, behavioral consistency |
| **Tasks** | `assess_productivity_dual_track()` | `ProductivityLevel` | Completion throughput, on-time rate, overdue backlog |
| **Goals** | `assess_progress_dual_track()` | `ProgressLevel` | Progress %, milestone completion, status factor |
| **Habits** | `assess_consistency_dual_track()` | `ConsistencyLevel` | Success rate, current streak, best streak |
| **Events** | `assess_engagement_dual_track()` | `EngagementLevel` | Attendance rate, goal support, habit reinforcement |
| **Choices** | `assess_decision_quality_dual_track()` | `DecisionQualityLevel` | Outcome quality, principle alignment, confidence calibration |

**User-level vs per-entity (and the `require_entity` flag).** Three dimensions assess the
USER across all their entities, not a single one: **Tasks** (productivity), **Events**
(engagement), **Choices** (decision quality). They pass `uid=user_uid`. Because a User node
is `:User`, not `:Entity`, the template's `backend.get(uid)` returns nothing — so these callers
pass `require_entity=False` (added June 2026), and the template proceeds with `entity=None`
(the insight/recommendation generators are None-safe and fall back to `entity_type` for the
label). The other three — **Goals** (per `goal_uid`), **Habits** (per `habit_uid`), **Principles**
(per `principle_uid`) — are per-entity and keep the default `require_entity=True`.

**Where check-ins persist follows the same split.** Per-entity check-ins append to the entity's
own `dual_track_checkins` field (via the domain backend); user-level check-ins append to
`User.dual_track_checkins` — a `dict[str, list[dict]]` keyed by `DualTrackDimension` value — since
there is no `:Entity` row to attach them to. See "Surfacing (v3)" below.

Tasks' implementation lives in `core/services/tasks/_dual_track_mixin.py` (mixed into
`TasksIntelligenceService`), accessed via `tasks_service.intelligence.assess_productivity_dual_track(...)`.
It uses the shared template — there is no separate `TasksProductivityService`.

### Surfacing (v1, June 2026)

Until June 2026 the dual-track engine was **dormant** — implemented but consumed by no route or
UI, and the user-level callers (Events/Choices) had a latent `not_found` bug at the entity-fetch
step that was never hit because nothing called them. The **Self Check-In** page
(`GET /self-checkin`, `adapters/inbound/self_checkin_routes.py` + `ui/self_checkin.py`) is the
first consumer: it surfaces the three **user-level** dimensions (Productivity / Engagement /
Decision Quality) as a self-rate-then-see-the-gap fragment.

### Surfacing (v2, June 2026) — per-entity + persistence + aggregator

The remaining pieces shipped:

- **Per-entity dimensions on detail pages.** Goals/Habits/Principles detail pages each carry a
  self-assessment section (`ui/dual_track_card.py::DualTrackSection`) — a self-rate form keyed by
  the entity UID that POSTs to `/{domain}/dual-track/results` (registered by the activity UI
  factory when `ActivityUIConfig.dual_track_assess` is set) — POST + `@csrf_protected` because it
  mutates (persists a check-in); it computes the gap, persists, and swaps in the gap card +
  refreshed trend. These keep `require_entity=True`. The shared gap-card
  primitives were lifted out of `ui/self_checkin.py` into `ui/dual_track_card.py` (one path).

- **Persistence + gap-trending (storage shape).** Each per-entity check-in is appended to an
  **inline `dual_track_checkins` field** on the entity — a uniform `tuple[dict]` log on Goal,
  Habit, and Principle (mirrors `Goal.progress_history`; round-trips as a JSON property via
  `neo4j_mapper`, no typed-record rehydration). The canonical store callback is
  `BaseAnalyticsService._store_dual_track_checkin` (appends the full snapshot — built by
  `DualTrackResult.to_checkin_snapshot`, incl. the computed system level/score + gap — capped at
  `DualTrackCheckin.HISTORY_LIMIT`, partial-update write). This **replaces** the former
  per-domain `_store_alignment_assessment` (Principles), which was dual-track-only glue; the
  separate single-track `assess_with_user_input` keeps its own `alignment_history` writer. The
  simple trend (`render_checkin_trend`) shows the last `DualTrackCheckin.TREND_WINDOW` snapshots
  with date + direction + gap.

  *Why a per-entity field over a graph edge:* the user-level dims aside, every per-entity check-in
  has an entity endpoint, and `create_relationship` MERGEs (one edge per pair → can't append a
  history); the inline field reuses the existing matured `progress_history`/`alignment_history`
  pattern with zero new relationship types, backend methods, or schema, and the cross-domain
  aggregator reads it uniformly via `find_by(user_uid=…)`.

- **Cross-domain aggregator.** `UserContextIntelligence.get_cross_domain_perception_analysis()`
  (new `PerceptionIntelligenceMixin`) loads the user's Goals/Habits/Principles, reads each
  entity's latest check-in, buckets `gap_direction` per domain, and synthesizes natural-language
  insights ("You tend to rate yourself higher than your tracked actions on Goals and Habits").
  Analytics-tier (no AI) — available at `INTELLIGENCE_TIER=core`.

### Surfacing (v3, June 2026) — user-level persistence + aggregator fold-in

The three **user-level** dimensions (Productivity / Engagement / Decision Quality) now persist
and feed the aggregator, closing the v2 deferral:

- **Storage shape — inline `dual_track_checkins` field on the `:User` node**, keyed by
  `DualTrackDimension` value (`productivity`/`engagement`/`decision_quality`); each value is an
  append-only log of snapshots, capped at `DualTrackCheckin.HISTORY_LIMIT`. This is the user-level
  analog of the per-entity `dual_track_checkins: tuple[dict]` field — the per-entity dims attach to
  an `:Entity` row, but user-level dims assess the user across *all* their entities of a kind and
  have no entity endpoint, so they live on the `:User` node (`User.dual_track_checkins`). It
  round-trips as a JSON property via `neo4j_mapper` (`dict[str, list[dict]]` ↔ JSON), so no new
  relationship types, backends, or schema. *(Chosen over option (b), a separate per-user store
  keyed by `(user_uid, dimension)`, for the same One-Path reasons the per-entity field beat a graph
  edge: it reuses the matured inline-log pattern and the existing User read/write path.)*

- **Persistence callback — `UserService.append_dual_track_checkin(user_uid, result, *, dimension)`.**
  The user-level analog of `BaseAnalyticsService._store_dual_track_checkin`: that callback uses the
  *domain* backend (`self.backend`) to write an entity, but the three user-level intelligence
  services' backends are the Task/Event/Choice backends — they can't write the `:User` node. So the
  callback lives on `UserService` (which owns the User node) and is **bound into the
  `store_callback(uid, result)` shape via `functools.partial(..., dimension=…)`** by the Self
  Check-In route. Safe-by-design (returns `None`, never raises). The three user-level assess methods
  (`assess_productivity_dual_track`, `assess_engagement_dual_track`,
  `assess_decision_quality_dual_track`) gained an optional `store_callback` param, forwarded to the
  template — so persistence is a property of the assessment, not the route.

- **Self Check-In is now `POST /self-checkin/results` + `@csrf_protected`** (was a non-persisting
  GET) — it mutates, exactly the v2 per-entity fix. The page surfaces a per-dimension trend
  (`render_checkin_trend`) on load and after each submit.

- **Aggregator fold-in.** `get_cross_domain_perception_analysis()` reads the latest check-in per
  user-level dimension off `context.dual_track_checkins` (copied onto `UserContext` by
  `UserContextBuilder` straight from the `:User` node — no second read) and merges them into the
  same `per_domain` rollup as the per-entity domains, so the synthesis spans all six.

### Atomic check-in append (v3.1, June 2026) — concurrency race closed

Both persistence paths append to a **single JSON-string property** (`dual_track_checkins`) — a flat
`list[dict]` on per-entity subjects, a `dict[dimension -> list[dict]]` on the `:User` node. The
append is a read-modify-write of that JSON, which two near-simultaneous appends on the *same subject*
could otherwise race (last-writer-wins, one snapshot lost). Cypher can't append inside a JSON string,
so the append/cap stays in Python — but the whole read-modify-write now runs **under a Neo4j node
write-lock**, serializing concurrent same-subject appends so none is lost.

- **Shared mechanism — `adapters/persistence/neo4j/_dual_track_checkin_store.py::atomic_append_checkin`.**
  An **explicit** write transaction whose first statement writes a sentinel property (`_dtc_lock`) to
  acquire the node's write-lock *before* the read; a concurrent appender blocks on that lock until
  this transaction commits, then reads the just-written value. The sentinel is removed in the same
  transaction (never lingers). `dimension=None` → flat per-entity list; a dimension key → the
  user-level dict-keyed log. Explicit (not managed `execute_write`) **on purpose**: the append isn't
  idempotent, so a managed auto-retry after an unknown commit outcome could duplicate a check-in. An
  explicit transaction is at-most-once — a rare transient failure surfaces as an error the
  safe-by-design store callback swallows (one check-in lost, never duplicated), which is already
  within the persistence contract.

- **Both paths route through it (One Path Forward).** Per-entity:
  `UniversalNeo4jBackend.atomic_append_dual_track_checkin` (`_CrudMixin`), called by
  `BaseAnalyticsService._store_dual_track_checkin`. User-level:
  `UserBackend.atomic_append_dual_track_checkin` (dimension-keyed), called by
  `UserService.append_dual_track_checkin`. The interim `update_user_fields` field-only writer (v3)
  is removed — the atomic method supersedes it. The `_APPEND_ONLY_FIELDS` exclusion stays: whole-model
  `User` writes still never touch the append-only log.

- **Storage shape is unchanged** (still one JSON-string property), so the model fields, DTO/mapper
  round-trip, trend rendering, and the cross-domain aggregator are all untouched.

- **Verified on live Neo4j** with a real concurrency test: 12 overlapping appends on the same subject
  retain all 12 (per-entity, user-level same-dimension, and user-level across 3 dimensions); a
  no-lock negative control retains only 1/12, confirming the lock is what closes the race.

### Surfacing (v3.2, June 2026) — Knowledge dimension (per-Ku mastery)

The final deferred row — the **Knowledge** dimension — shipped: "I've mastered this Ku"
(`MasteryLevel`) vs the system-measured **substance score**
(`KuIntelligenceService.calculate_user_substance` — how much the user has actually applied the Ku
across their life, per the Knowledge Substance Philosophy). The gap is the perception of mastery
against the lived evidence.

- **Per-(user, Ku), not per-entity.** A Ku is SHARED/public curriculum (not user-owned, unlike
  Goals/Habits/Principles), so a mastery check-in is per-(user, Ku) and **cannot** live on the shared
  `:Ku` node — it would collide across users. The per-entity inline-field pattern does not transfer.
  Instead, check-ins persist on the **`:User` node** in a **separate `knowledge_checkins:
  dict[ku_uid, list[dict]]` field** (chosen over namespacing inside `dual_track_checkins` so the open-ended
  per-Ku keys stay distinct from the three fixed `DualTrackDimension` values). Append-only, capped at
  `DualTrackCheckin.HISTORY_LIMIT` per Ku; round-trips as a JSON property via `neo4j_mapper`.

- **Assessment — `KuIntelligenceService.assess_mastery_dual_track(user_uid, ku_uid, user_level,
  user_evidence, user_context, ...)`** via the shared `_dual_track_assessment()` template
  (`require_entity=True` — the Ku IS an `:Entity`). `level_scorer = MasteryLevel.to_score`; the
  `system_calculator` wraps the existing `calculate_user_substance` → `(MasteryLevel, score, evidence)`.
  Because substance is computed from the user's activity→Ku channels, the caller passes the **rich**
  `UserContext` (`get_rich_unified_context` — those maps are rich-only); the route builds it.

- **Atomic persistence — `UserService.append_knowledge_checkin(ku_uid, result, *, user_uid)`**,
  routing through `UserBackend.atomic_append_knowledge_checkin` → the shared
  `_dual_track_checkin_store.atomic_append_checkin` (now parameterized with `property_name`, keyed by
  `ku_uid`). Same node-write-lock guarantee as v3.1 (One Path Forward — no new mechanism). Added to
  `_APPEND_ONLY_FIELDS` so whole-model `User` writes never clobber the log.

- **Surface — Ku detail page (`/explore/ku/{uid}`).** A "Mastery Self-Check" section
  (`ui/explore/ku_mastery.py`, reusing the `ui/dual_track_card.py` primitives) POSTs to
  `POST /explore/ku/{uid}/mastery-checkin` (`@csrf_protected` — it mutates). Wired **manually** in
  `learning_loop_routes.py` (the Ku detail page is not the activity UI factory). Authenticated users
  only.

- **Aggregator fold-in.** `get_cross_domain_perception_analysis()` reads `context.knowledge_checkins`
  (copied off the `:User` node by `UserContextBuilder`), aggregates the latest check-in per Ku into a
  single **"Knowledge"** bucket, and folds it into the same `per_domain` rollup — so the synthesis now
  spans **all assessable dimensions**.

- **Verified on live Neo4j**: seed `(Task)-[:APPLIES_KNOWLEDGE]->(Ku)` → substance moves off 0 → rate
  MASTERED → gap 95% `user_higher` → atomic persist → round-trip → builder populates
  `context.knowledge_checkins` → aggregator surfaces "Knowledge" in `over_rated_domains`; a real
  concurrency test (12 overlapping same-(user, Ku) appends) retains all 12.

**All dual-track dimensions are now shipped.** No deferred rows remain.

### Future Extensions

_(All shipped — retained for the historical record.)_

| Domain | User Self-Assessment | System Measurement | Status |
|--------|---------------------|-------------------|--------|
| **Knowledge** | "I've mastered this" (`MasteryLevel`) | Substance score | ✅ Shipped (v3.2, June 2026) |

## Decision

**Extend `BaseAnalyticsService` with a `_dual_track_assessment()` template method.**

### Rejected Alternative: DualTrackAssessmentMixin

| Concern | Mixin | BaseAnalyticsService |
|---------|-------|------------------------|
| Scope | Too broad (any service) | Correct scope (intelligence) |
| Dependencies | Must re-specify | Already available |
| Philosophy | "Bolted on" | "Fundamental" |
| One Path Forward | Creates alternative | Extends single path |
| Inheritance | Composition required | Automatic for 10 services |

### Rationale

1. **Dual-track IS intelligence work** - Comparing user perception with measured behavior is core intelligence, not a utility.

2. **Infrastructure exists** - `BaseAnalyticsService` already has `backend`, `relationships`, `event_bus`, and the analysis template (`_analyze_entity_with_typed_context()`, renamed from the original `_analyze_entity_with_context()` during the intent-traversal ↔ registry convergence, #253).

3. **Template pattern matches** - The existing analysis template is 80% of what we need. Extending it maintains consistency.

4. **One Path Forward** - All 10 domain intelligence services inherit from `BaseAnalyticsService`. Adding the method there means automatic availability without additional composition.

5. **Grounded design** - This "roots it deepest into the codebase" rather than existing as an add-on.

## Implementation

### Phase 1: Generic Result Model

Created `core/models/shared/dual_track.py` with `DualTrackResult[T]`:

```python
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

L = TypeVar("L")  # Level enum type


@dataclass(frozen=True)
class DualTrackResult(Generic[L]):
    """
    Generic dual-track assessment result.

    Captures both user self-assessment and system measurement,
    enabling gap analysis between perception and reality.
    """
    entity_uid: str
    entity_type: str  # EntityType.value

    # USER-DECLARED (Vision)
    user_level: L
    user_score: float  # 0.0-1.0 normalized
    user_evidence: str
    user_reflection: str | None

    # SYSTEM-CALCULATED (Action)
    system_level: L
    system_score: float  # 0.0-1.0 normalized
    system_evidence: tuple[str, ...]

    # GAP ANALYSIS (Insight)
    perception_gap: float  # Absolute difference (0.0-1.0)
    gap_direction: str  # "user_higher" | "system_higher" | "aligned"

    # GENERATED INSIGHTS
    insights: tuple[str, ...]
    recommendations: tuple[str, ...]

    def has_perception_gap(self, threshold: float = 0.15) -> bool:
        """Check if gap exceeds threshold."""
        return self.perception_gap >= threshold

    def is_self_aware(self) -> bool:
        """Check if user perception matches system measurement."""
        return self.gap_direction == "aligned"
```

### Phase 2-3: BaseAnalyticsService Extension

Added to `core/services/base_analytics_service.py`:

```python
async def _dual_track_assessment(
    self,
    uid: str,
    user_uid: str,
    # USER-DECLARED (Vision)
    user_level: L,
    user_evidence: str,
    user_reflection: str | None,
    # SYSTEM CALCULATION
    system_calculator: Callable[
        [Any, str], Awaitable[tuple[L, float, list[str]]]
    ],
    # LEVEL SCORING (domain-specific enum → float)
    level_scorer: Callable[[L], float],
    # OPTIONAL CUSTOMIZATION
    entity_type: str = "",
    insight_generator: Callable[[str, float, str], list[str]] | None = None,
    recommendation_generator: Callable[[str, float, Any, list[str]], list[str]] | None = None,
    store_callback: Callable[[str, Any], Awaitable[None]] | None = None,
) -> Result[DualTrackResult[L]]:
    """Template method for dual-track assessment."""
```

Also added:
- `_calculate_perception_gap()` - Gap calculation
- `_default_gap_insights()` - Default insight generation
- `_default_gap_recommendations()` - Default recommendation generation

### Phase 4: Domain Implementation Example

In `PrinciplesIntelligenceService`:

```python
async def assess_alignment_dual_track(
    self,
    principle_uid: str,
    user_uid: str,
    user_alignment_level: AlignmentLevel,
    user_evidence: str,
    user_reflection: str | None = None,
) -> Result[DualTrackResult[AlignmentLevel]]:
    """Dual-track alignment assessment for principles."""
    return await self._dual_track_assessment(
        uid=principle_uid,
        user_uid=user_uid,
        user_level=user_alignment_level,
        user_evidence=user_evidence,
        user_reflection=user_reflection,
        system_calculator=self._calculate_system_alignment_for_dual_track,
        level_scorer=self._alignment_level_to_score,  # delegates to AlignmentLevel.to_score()
        entity_type="principle",
        insight_generator=self._generate_principle_gap_insights,
        recommendation_generator=self._generate_principle_gap_recommendations,
        store_callback=self._store_alignment_assessment,
    )
```

## Files Modified

| File | Change |
|------|--------|
| `core/models/shared/__init__.py` | NEW: Package init |
| `core/models/shared/dual_track.py` | NEW: Generic `DualTrackResult[T]` model |
| `core/models/enums/activity_enums.py` | Add 5 level enums: ProductivityLevel, ProgressLevel, ConsistencyLevel, EngagementLevel, DecisionQualityLevel |
| `core/services/base_analytics_service.py` | Add `_dual_track_assessment()` template and helpers |
| `core/services/principles/principles_intelligence_service.py` | Add `assess_alignment_dual_track()` implementation |
| `core/services/tasks/_dual_track_mixin.py` | `assess_productivity_dual_track()` (June 2026, shared template + `require_entity=False`) |
| `adapters/inbound/self_checkin_routes.py` / `ui/self_checkin.py` | Self Check-In surface — first consumer (v1 June 2026); v3 → POST + CSRF + persistence + per-dimension trend |
| `core/models/enums/activity_enums.py` | v3: `DualTrackDimension` StrEnum (productivity/engagement/decision_quality) |
| `core/models/user/user.py` | v3: `User.dual_track_checkins: dict[str, list[dict]]` (user-level check-in log) |
| `core/services/user/user_core_service.py` + `core/services/user_service.py` | v3: `append_dual_track_checkin()` store callback |
| `core/services/{tasks/_dual_track_mixin,events/_behavioral_signals_mixin,choices/_behavioral_signals_mixin}.py` | v3: optional `store_callback` param on the 3 user-level assess methods |
| `core/services/user/unified_user_context.py` + `user_context_builder.py` | v3: `UserContext.dual_track_checkins` populated from the `:User` node |
| `core/services/user/intelligence/perception_intelligence.py` | v3: aggregator folds in user-level dims |
| `core/services/goals/goals_intelligence_service.py` | Add `assess_progress_dual_track()` implementation |
| `core/services/habits/habits_intelligence_service.py` | Add `assess_consistency_dual_track()` implementation |
| `core/services/events/events_intelligence_service.py` | Add `assess_engagement_dual_track()` implementation |
| `core/services/choices/choices_intelligence_service.py` | Add `assess_decision_quality_dual_track()` implementation |
| `docs/decisions/ADR-030-dual-track-assessment-pattern.md` | NEW: This ADR |

## Migration Path

1. **Phase 1** (January 2026): Add generic model and template to BaseAnalyticsService ✅
2. **Phase 2**: Implement for Principles (demonstrate pattern) ✅
3. **Phase 3**: Implement for Tasks (productivity self-assessment) ✅
4. **Phase 4**: Implement for Goals (progress self-assessment) ✅
5. **Phase 5**: Implement for Habits (consistency self-assessment) ✅
6. **Phase 6**: Implement for Events (engagement self-assessment) ✅
7. **Phase 7**: Implement for Choices (decision quality self-assessment) ✅
8. **Phase 8**: Implement for Knowledge (per-Ku mastery vs substance score, v3.2 June 2026) ✅

## Verification

1. **Unit tests**: Test `_dual_track_assessment()` with mock calculators
2. **Integration**: Verify Principles endpoint returns dual-track response
3. **MyPy**: Ensure generic `DualTrackResult[L]` type-checks correctly
4. **Linter**: Run `uv run python scripts/lint_skuel.py`

## Consequences

### Positive
- Unified pattern across all intelligence services
- No additional mixins or composition required
- Automatic inheritance for all 10 domain intelligence services
- Consistent API response structure
- Enables cross-domain perception gap synthesis in UserContextIntelligence

### Negative
- Adds complexity to BaseAnalyticsService (~200 lines)
- Domain-specific calculators must be provided by each service
- Existing `assess_with_user_input()` in PrinciplesAlignmentService can coexist

### Neutral
- Each domain can choose to implement or not
- Existing implementations continue to work

## Future Extensions

The cross-domain aggregator below **shipped** (June 2026, v2) as
`UserContextIntelligence.get_cross_domain_perception_analysis()` — see "Surfacing (v2)" above. It
reads from `self.context` (no `user_uid` param needed). As of v3.2 (June 2026) it covers **all
assessable dimensions** — the three per-entity domains (Goals/Habits/Principles), the three
user-level dimensions (Productivity/Engagement/Decision Quality, read off
`context.dual_track_checkins`), and the per-Ku **Knowledge** dimension (read off
`context.knowledge_checkins`):

```python
# core/services/user/intelligence/perception_intelligence.py
async def get_cross_domain_perception_analysis(self) -> Result[dict[str, Any]]:
    """
    Synthesize perception gaps across all six assessable domains/dimensions.

    Returns insights like:
    - "You tend to rate yourself higher than your tracked actions on Goals, Habits, and Productivity"
    - "You're doing better than you think on Principles and Engagement"
    """
```

No remaining future work — the Knowledge-domain dimension shipped in v3.2 (see "Surfacing (v3.2)").

## References

- LifePath `WordActionAlignment`: `core/models/lifepath/`
- Principles alignment service: `core/services/principles/principles_alignment_service.py`
- Principles intelligence service: `core/services/principles/principles_intelligence_service.py`
- BaseAnalyticsService: `core/services/base_analytics_service.py`
- ADR-024: BaseAnalyticsService Migration
