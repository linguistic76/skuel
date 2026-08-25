---
title: Intelligence Services - Master Index
updated: 2026-08-08
category: intelligence
status: current
related_skills:
- base-ai-service
- base-analytics-service
tracking: conceptual
last_reviewed: 2026-08-08
review_frequency: annual
---
# Intelligence Services - Master Index

**Last Updated:** March 21, 2026 · **Last Audited:** August 8, 2026

> **Code-accuracy audit — 2026-08-08.** Every service, protocol, count, and ADR reference below
> was re-verified against the codebase. Corrections made this pass:
> - **MOC removed as an intelligence domain.** `MocIntelligenceService` was deleted in the
>   January-2026 KU-based MOC refactoring (see [MOC_INTELLIGENCE.md](./MOC_INTELLIGENCE.md)); no
>   `MocIntelligenceService`/`MOCService`/`MocNavigationService` class exists. MOC is emergent
>   identity — any `Entity` with outgoing `ORGANIZES` edges (CLAUDE.md; `CURRICULUM_GROUPING_PATTERNS.md`).
> - **Counts reconciled.** The inventory now lists **16** analytics/core-side services (was internally "14" and "11" in
>   different sections). **11** extend `BaseAnalyticsService`; **9** domain services implement the
>   `IntelligenceRouteFactory` 3-method protocol (was stated as "10"), of which **8** actually have
>   routes generated — KU conforms to the protocol but `KU_CONFIG` doesn't wire the factory.
> - **Added three services the index omitted:** `KnowledgeHealthService` (corpus-level
>   `BaseAnalyticsService`, ADR-080 H1), `LifePathIntelligenceService` (lightweight
>   recommendation logic, not a `BaseAnalyticsService`), and `CrossDomainAnalyticsService`
>   (event-driven cross-domain analytics, wired every tier). Added a scope-boundary note so the
>   count excludes infrastructure/query/facade services rather than silently omitting them.
> - **`DomainIntelligenceOperations`/`IntelligenceOperations` are largely aspirational.** Of the
>   7 domain-protocol methods only `get_performance_analytics` is universal; 3 have no
>   implementation at all and a 4th (`get_learning_velocity`) only a non-conforming one outside the
>   per-domain classes. What the domain services uniformly satisfy is the separate 3-method
>   route-factory surface. The "all services implement protocol methods" claims were qualified.
> - **AI tier is wired, not "future."** The `BaseAIService` layer is constructed in FULL tier
>   (`services_bootstrap/_ai_wiring.py`, 10 subclasses) — the "for future use" language was stale.
>   The **16** total is the analytics/core-side inventory; the wired AI tier is documented and
>   counted separately.
> - Protocol method counts (Knowledge=4, Domain=7, composed=11) verified accurate.

## Overview

SKUEL's intelligence layer provides graph-based analytics and insights across all entity types. The unified architecture uses a **two-tier design** (ADR-024):

- **`BaseAnalyticsService`** - Graph analytics with NO AI dependencies (all domain intelligence services extend this)
- **`BaseAIService`** - Optional AI-powered features (LLM, embeddings), **wired in FULL tier** (ADR-043) — enhances, never required

The app functions fully without any LLM dependencies - AI services enhance but are not required.

**Total Intelligence Services:** 16 — *analytics/core-side inventory* (the `BaseAnalyticsService`, specialized-graph, cross-domain, and lightweight-recommendation services below). The parallel **wired AI tier** (`BaseAIService` subclasses, FULL tier) is counted separately — see below.
- **Activity Domains:** 6 (Tasks, Goals, Habits, Events, Choices, Principles)
- **Shared Knowledge:** 1 (ActivityKnowledgeIntelligenceService — serves all 6 activity domains)
- **Curriculum Domains:** 3 (KU, PS, LP)
- **Corpus Analytics:** 1 (KnowledgeHealthService — whole-subgraph structural gauge, ADR-080 Horizon 1)
- **Cross-Domain Analytics:** 1 (CrossDomainAnalyticsService — event-driven, wired every tier; `analytics_api.py` endpoints for learning-velocity / productivity / habit-consistency / dashboard)
- **Meta Intelligence:** 1 (UserContext - central intelligence hub)
- **Cross-Cutting:** 1 (Askesis - life context synthesis)
- **Specialized Graph:** 1 (ZPDService - curriculum ZPD graph analytics — FULL tier only)
- **LifePath:** 1 (LifePathIntelligenceService — lightweight recommendation logic, **not** a `BaseAnalyticsService`)

Of these, **11 extend `BaseAnalyticsService`** (6 Activity + 3 Curriculum + shared ActivityKnowledge + corpus KnowledgeHealth). UserContext uses a modular package, Askesis a custom facade, ZPDService a specialized graph service, and CrossDomainAnalyticsService and LifePath are plain classes.

**Scope of this count (to keep it stable):** it lists the services that *produce* domain / cross-domain / corpus analytics, intelligence, or recommendations. It deliberately **excludes** (a) pure infrastructure — `GraphIntelligenceService` (graph queries, in the Dependencies table below); (b) query plumbing — `CrossDomainQueryService`; and (c) the `AnalyticsService` **facade** (`core/services/analytics_service.py`), which aggregates/exposes the services above (e.g. `analyze_knowledge_subgraph_health()`) rather than being a distinct producer.

**Wired AI tier (FULL tier only, ADR-043).** A parallel layer of **10 `BaseAIService` subclasses** is constructed in `services_bootstrap/_ai_wiring.py` when `INTELLIGENCE_TIER=full` — 6 Activity (`TasksAIService` … `PrinciplesAIService`), 2 Curriculum (`PsAIService`, `LpAIService`), and 2 cross-cutting (`AskesisAIService`, `ContextAwareAIService`). These enhance the analytics services with LLM/embedding features and are `None` in CORE tier. They are **not** counted in the 16 above (which is the analytics/core-side inventory); see [@base-ai-service](../../.claude/skills/base-ai-service/SKILL.md) for the AI-tier reference.

**MOC has no intelligence service.** MOC is emergent identity — any `Entity` with outgoing `ORGANIZES` edges (CLAUDE.md; `docs/architecture/CURRICULUM_GROUPING_PATTERNS.md`). The old `MocIntelligenceService` was deleted in the January-2026 KU-based refactoring; a Ku that organizes others is analyzed as a Ku via `KuIntelligenceService`. See [MOC_INTELLIGENCE.md](./MOC_INTELLIGENCE.md).

**Note:** Finance is a standalone bookkeeping domain (no intelligence service).

**ZPDService** (`core/services/zpd/zpd_service.py`) is a specialized curriculum graph analytics service, distinct from the `BaseAnalyticsService` subclasses. It does NOT extend `BaseAnalyticsService` — it delegates Neo4j queries to `ZPDBackend` (`adapters/persistence/neo4j/zpd_backend.py`) and computes Zone of Proximal Development assessments from the results. Only available in FULL tier; gracefully degrades (returns empty assessment) when curriculum engagement relationships are absent.

**KnowledgeHealthService** (`core/services/analytics/knowledge_health_service.py`, ADR-080 Horizon 1) is a **corpus-level** `BaseAnalyticsService` — it *does* extend the base (no AI, CORE-tier safe), but unlike the 9 per-domain services it reports on the **whole knowledge subgraph** (Ku / PathStep / LearningPath / Exercise) rather than one entity type, and takes no `user_uid`. It consumes raw structural facts from `KnowledgeHealthBackend` (`adapters/persistence/neo4j/backends/curriculum_backends.py`) and derives coverage ratios, a composite **GDS-readiness score**, and human-readable **authoring-guidance flags** (orphan Kus, near-empty prerequisite DAG, missing ORGANIZES/MOC hierarchy). Surfaced via the `AnalyticsService` facade (`analyze_knowledge_subgraph_health()`), admin `/admin/knowledge-health`, `./dev knowledge-health [--json]`, and 6 knowledge-scoped Prometheus gauges (fed by the existing 5-min graph-health poller — no new worker). **A corpus/authoring gauge deliberately excludes user-generated data** (learner-state telemetry edges, PERSONAL/ASSIGNED/ASSESSMENT exercises) and matches knowledge nodes by `entity_type`, not domain label, so user activity never inflates the structural signal.

## Related Skills

For implementation guidance, see:
- [@base-analytics-service](../../.claude/skills/base-analytics-service/SKILL.md)
- [@base-ai-service](../../.claude/skills/base-ai-service/SKILL.md)

## One Path Forward (ADR-029)

**January 8, 2026:** GraphNativeMixin removed from UserContextIntelligence (366 lines).

**Architecture Alignment:**
- UserContextIntelligence uses **modular mixin architecture** (ADR-021)
- Simple context methods (8 lines) for cached analysis
- Domain services provide fresh Cypher queries when needed
- **No intermediate abstraction layers** - clear two-path model

**Deleted:** GraphNativeMixin with 4 methods creating alternative query paths
**Result:** UserContext methods are simple delegates to underlying data, intelligence services use domain services directly

**See:** [ADR-029](../decisions/ADR-029-graphnative-service-removal.md)

---

## Architecture Pattern

All domain intelligence services follow the `BaseAnalyticsService` pattern (ADR-024, updated January 2026) — 11 subclasses in total (see Overview). Services >350 lines are decomposed into focused mixins (April 2026):

```python
# Compact service (≤350 lines) — single inheritance
class HabitsIntelligenceService(BaseAnalyticsService["HabitsOperations", Habit]):
    _service_name = "habits.analytics"

    def __init__(self, backend, graph_intel, ...):
        super().__init__(backend, graph_intel, ...)

# Decomposed service (>350 lines) — shell + mixin files in same package directory
class TasksIntelligenceService(
    _CoreIntelligenceMixin,    # domain wrapper (inherits generic _CoreIntelligenceMixin[Task] + aliases)
    _AnalyticsMixin,           # behavioral + performance analytics
    _ProductivityMixin,        # analytics engine methods
    BaseAnalyticsService["TasksOperations", Task],
):
    """Shell: __init__ + protocol methods only."""

# PS/LP/KU/Events inherit the generic base directly — no per-package wrapper:
class PsIntelligenceService(
    _CoreIntelligenceMixin[PathStep],  # typed get_with_context() for free
    BaseAnalyticsService["BackendOperations[PathStep]", PathStep],
):
    ...
```

See `/docs/patterns/SERVICE_DECOMPOSITION_RULE.md` for decomposition thresholds (intelligence: ~350 lines, facade: ~700 lines + 4+ coherent methods).

**Exception:** UserContextIntelligence uses a modular package architecture (ADR-021) with mixin composition instead of BaseAnalyticsService inheritance.

**Two-Tier Design (January 2026):**
| Layer | Base Class | Dependencies | Purpose |
|-------|------------|--------------|---------|
| **Analytics** | `BaseAnalyticsService` | Graph queries + Python | Works without LLM |
| **AI** | `BaseAIService` | LLM + Embeddings | Optional AI features |

### File Naming Convention (Intelligence vs Analytics)

**Why `*_intelligence_service.py` not `*_analytics_service.py`?**

The naming reflects a semantic distinction:
- **File name** = User-facing capability (what it provides)
- **Base class** = Implementation detail (how it's built)

| Layer | File Pattern | Base Class | Rationale |
|-------|-------------|-----------|-----------|
| **Intelligence** | `*_intelligence_service.py` | `BaseAnalyticsService` | "Intelligence" = insights + recommendations + analysis |
| **AI** | `*_ai_service.py` | `BaseAIService` | "AI" = LLM-powered semantic features |

**The convention:**
- `*IntelligenceService` = Graph analytics (NO AI) - the critical path
- `*AIService` = LLM/embeddings features (OPTIONAL) - the enhancement layer

All 9 domain intelligence services correctly extend `BaseAnalyticsService` (as do the shared `ActivityKnowledgeIntelligenceService` and corpus-level `KnowledgeHealthService`) - the name "Intelligence" describes what users get (actionable insights), while `BaseAnalyticsService` describes how it's implemented (graph queries + Python).

**Benefits:**
- Standardized initialization and logging
- Dependency checks via inline `if not self.graph_intel` / `if not self.relationships` guards
- Consistent error handling via `Result[T]`
- Helper methods (`_to_domain_model()`)
- App runs without LLM dependencies (analytics-first design)

---

## Intelligence Protocols (January 2026, split March 2026)

The intelligence protocol layer has two levels:

### Core Protocols (`core/ports/intelligence_protocols.py`)

Split into focused ISP protocols (March 2026):

| Protocol | Methods | Implementor |
|----------|---------|-------------|
| `KnowledgeIntelligenceOperations` | 4 — `get_knowledge_suggestions`, `generate_knowledge_from_entities`, `get_knowledge_prerequisites`, `get_learning_opportunities` | `ActivityKnowledgeIntelligenceService` (shared singleton) |
| `DomainIntelligenceOperations` | 7 — `find_similar_content`, `search_by_features`, `get_learning_velocity`, `get_behavioral_insights`, `get_performance_analytics`, `get_cross_domain_opportunities`, `get_ai_insights` | Per-domain intelligence services (**largely aspirational — see note**) |
| `IntelligenceOperations` | 11 (composed) | Backward-compatible union of both (**not fully implemented by any service**) |

> **⚠️ `DomainIntelligenceOperations` (and therefore the composed `IntelligenceOperations`) is largely aspirational.** Of its 7 methods only `get_performance_analytics` is implemented across all domains. `find_similar_content` exists on LP only and `get_behavioral_insights` on Tasks only. Three — `search_by_features`, `get_cross_domain_opportunities`, and `get_ai_insights` — have **no implementation anywhere**. `get_learning_velocity` has no *conforming per-domain* implementation, but a live variant exists on `CrossDomainAnalyticsService` (`core/services/cross_domain_analytics_service.py`, signature `days_back=30` — not a per-domain intelligence class). The protocol is exported from `core/ports/` but never used as a runtime type. The contract the domain services *actually* satisfy is the 3-method route-factory surface below — which the code deliberately keeps as its **own separate** protocol (see the `IntelligenceOperations` docstring in `core/ports/intelligence_protocols.py`).

### Route Factory Protocol (`adapters/inbound/route_factories/intelligence_route_factory.py`)

All **9** domain intelligence services (6 Activity + KU/PS/LP) *implement* this separate 3-method protocol:

| Method | Returns | Purpose |
|--------|---------|---------|
| `get_with_context(uid, depth=2)` | `Result[tuple[T, GraphContext]]` | Entity with full graph neighborhood |
| `get_performance_analytics(user_uid, period_days=30)` | `Result[dict]` | User-specific analytics (or overall stats for shared content) |
| `get_domain_insights(uid, min_confidence=0.7)` | `Result[dict]` | Domain-specific intelligence and recommendations |

**Protocol conformance vs. route rollout are distinct.** All 9 services implement the three methods, but only **8** actually have routes generated by `IntelligenceRouteFactory` — the 6 Activity domains (via `create_activity_domain_route_config()`, which defaults `intelligence=IntelligenceRouteConfig()`) plus PS and LP (which set it explicitly at `ContentScope.SHARED`). **KU is the exception:** `KU_CONFIG` (`adapters/inbound/ku_routes.py`) does **not** set an `IntelligenceRouteConfig`, so no `IntelligenceRouteFactory` is wired and the generic `/api/ku/context|analytics|insights` routes are **not** generated. The **three route-factory methods** (`get_with_context` / `get_performance_analytics` / `get_domain_insights`) therefore have no HTTP surface for KU. **This is scoped to those three methods only — `KuIntelligenceService` itself is not unused:** its `assess_mastery_dual_track` is invoked by the Ku mastery-checkin route (`POST /explore/ku/{uid}/mastery-checkin` → `ExploreOrchestrator.assess_ku_mastery`).

**Implementation Pattern:**
```python
# get_with_context() is inherited from the shared _CoreIntelligenceMixin[T] and routes
# through mechanism B (registry-sourced) — no per-service override, no wiring step. The
# composition root injects a live relationship_service; BaseAnalyticsService stores it
# as self.relationships.
#   class _CoreIntelligenceMixin[T]:
#       @requires_graph_intelligence("get_with_context")
#       async def get_with_context(self, uid, depth=2) -> Result[tuple[T, GraphContext]]:
#           if self.relationships is None:
#               return Result.fail(Errors.system(...))
#           return await self.relationships.get_with_context(uid, depth)
# Edge vocabulary comes from the domain config's cross_domain_relationship_types.
```

**Routes Generated by IntelligenceRouteFactory** (for the 8 wired domains — 6 Activity + PS + LP; **not** KU, see above):
- `GET /api/{domain}/context?uid=...&depth=2`
- `GET /api/{domain}/analytics?period_days=30` (user_uid from session)
- `GET /api/{domain}/insights?uid=...&min_confidence=0.7`

**IntelligenceRouteFactory Security (January 2026):**
- **Content scope** via `scope` parameter (default: `ContentScope.USER_OWNED`)
- Activity Domains verify entity ownership before returning context/insights
- Shared curriculum content uses `scope=ContentScope.SHARED` — of the curriculum domains only **PS and LP** actually register the factory at this scope (KU is protocol-conformant but unwired, so no KU factory bypasses ownership; see above)
- Returns 404 (not 403) to prevent UID enumeration attacks

```python
from core.models.enums import ContentScope

# Factory with ownership verification (Activity Domains)
factory = IntelligenceRouteFactory(
    intelligence_service=tasks_service.intelligence,
    domain_name="tasks",
    scope=ContentScope.USER_OWNED,           # Default - ownership verification
    ownership_service=tasks_service,          # Must implement verify_ownership(uid, user_uid)
)

# Factory for shared content (Curriculum)
factory = IntelligenceRouteFactory(
    intelligence_service=ps_service.intelligence,
    domain_name="ps",
    scope=ContentScope.SHARED,                # No ownership checks
)
```

**FastHTML Route Parameter Style:**
Routes use function parameters with type hints (not `request.query_params`):
```python
async def context_route(request, uid: str, depth: int = 2) -> Result[Any]:
async def analytics_route(request, period_days: int = 30) -> Result[Any]:
async def insights_route(request, uid: str, min_confidence: float = 0.7) -> Result[Any]:
```

**Rollout Status (current):**

| Service | Protocol Methods | Routes wired (`IntelligenceRouteFactory`) |
|---------|------------------|-------------------------------------------|
| TasksIntelligenceService | ✅ | ✅ |
| GoalsIntelligenceService | ✅ | ✅ |
| HabitsIntelligenceService | ✅ | ✅ |
| EventsIntelligenceService | ✅ | ✅ |
| ChoicesIntelligenceService | ✅ | ✅ |
| PrinciplesIntelligenceService | ✅ | ✅ |
| KuIntelligenceService | ✅ | ❌ — `KU_CONFIG` sets no `IntelligenceRouteConfig` |
| PsIntelligenceService | ✅ | ✅ |
| LpIntelligenceService | ✅ | ✅ |

*"Protocol Methods ✅" = the class implements `get_with_context` / `get_performance_analytics` / `get_domain_insights`. "Routes wired" = an `IntelligenceRouteFactory` is registered so the generic `/api/{domain}/context|analytics|insights` routes exist — 8 of the 9 (KU conforms but is not wired; see the Route Factory Protocol section). Goals additionally has a pilot per-domain orchestrator (`create_goals_intelligence_routes`, `adapters/inbound/orchestration_routes.py`).*

*(The former `MocIntelligenceService` row was removed — the service was deleted in the January-2026 KU-based MOC refactoring; MOC is emergent, see Overview.)*

**Bug Fixes & Improvements (January 2026):**
- SUCCESS_RATE UNIT INCONSISTENCY: Fixed in `GoalsIntelligenceService` (Habit.success_rate is 0.0-1.0)
- Missing `is_on_track()`: Added to `Goal` model
- Unguarded `self.progress` calls: Added fail-fast guard
- Logging emoji: Removed from `IntelligenceRouteFactory`
- **Ownership verification**: Added to context/insights routes (security fix)
- **Parameter style consistency**: Routes use FastHTML function parameters with type hints

**Placeholder Convention (`_period_days`):**
`get_performance_analytics()` carries an unapplied `_period_days` in **3** services — Habits,
Choices, Principles — where the underscore prefix marks "API contract defined, implementation
deferred". **Goals is not one of them:** it takes a non-underscore `period_days` and filters on it
(though its filter has a separate defect — see the register). **Events** implements period
filtering, in Python, over its `event_date` domain field.

**The register is `docs/reference/PLACEHOLDER_INDEX.md` § "Group A — Period-Based Analytics
Filtering"** — verified coordinates, the reason the placeholder is a user-visible wrong answer, and
the correct fetch helper live there. Do not restate the deferral here; link to it.

**Tests:** 19/19 factory tests + 108/108 intelligence tests passing

---

## Dual-Track Assessment Pattern (ADR-030)

**Added:** January 18, 2026

SKUEL's core philosophy states: **"The user's vision is understood via the words they use to communicate, the UserContext is determined via user's actions."**

The Dual-Track Assessment Pattern implements this philosophy by comparing **user self-assessment (vision)** with **system measurement (action)** to generate perception gap analysis and insights.

### Template Method

`BaseAnalyticsService._dual_track_assessment()` provides a standardized template for all domains:

```python
async def _dual_track_assessment(
    self,
    uid: str,
    user_uid: UserUID,
    # USER-DECLARED (Vision)
    user_level: Any,
    user_evidence: str,
    user_reflection: str | None,
    # SYSTEM CALCULATION
    system_calculator: Callable[
        [Any, str], Awaitable[tuple[Any, float, list[str]]]  # (entity, user_uid)
    ],
    # LEVEL SCORING
    level_scorer: Callable[[Any], float],
    # OPTIONAL CUSTOMIZATION
    entity_type: str = "",
    require_entity: bool = True,          # False for user-level dims (uid == user_uid, no :Entity row)
    insight_generator: Callable[[str, float, str], list[str]] | None = None,
    recommendation_generator: Callable[[str, float, Any, list[str]], list[str]] | None = None,
    store_callback: Callable[[str, DualTrackResult[L]], Awaitable[None]] | None = None,  # persists the snapshot
) -> Result[DualTrackResult[L]]
```

### Generic Result Model

`DualTrackResult[L]` is a generic frozen dataclass that captures both tracks:

```python
@dataclass(frozen=True)
class DualTrackResult(Generic[L]):
    entity_uid: EntityUID
    entity_type: str

    # USER-DECLARED (Vision)
    user_level: L           # Domain-specific level enum
    user_score: float       # 0.0-1.0 normalized
    user_evidence: str
    user_reflection: str | None

    # SYSTEM-CALCULATED (Action)
    system_level: L
    system_score: float
    system_evidence: tuple[str, ...]

    # GAP ANALYSIS
    perception_gap: float   # Absolute difference
    gap_direction: str      # "user_higher" | "system_higher" | "aligned"

    # INSIGHTS
    insights: tuple[str, ...]
    recommendations: tuple[str, ...]
```

### Domain Implementations

**Seven** assessable dimensions implement dual-track assessment — the 6 Activity Domains plus the Knowledge dimension:

| Service | Method | Level Enum | Subject | System Metrics |
|---------|--------|------------|---------|----------------|
| **Principles** | `assess_alignment_dual_track()` | `AlignmentLevel` | per-entity | Goal alignment, choice consistency, habit support, entity count |
| **Goals** | `assess_progress_dual_track()` | `ProgressLevel` | per-entity | Milestone completion, habit support, on-track %, consistency |
| **Habits** | `assess_consistency_dual_track()` | `ConsistencyLevel` | per-entity | Completion rate, streak health, avg streak length, active ratio |
| **Tasks** | `assess_productivity_dual_track()` | `ProductivityLevel` | user-level | Completion rate, on-time %, overdue ratio, knowledge linking |
| **Events** | `assess_engagement_dual_track()` | `EngagementLevel` | user-level | Attendance rate, goal support, habit reinforcement, recency |
| **Choices** | `assess_decision_quality_dual_track()` | `DecisionQualityLevel` | user-level | Outcome quality, principle alignment, decision rate, confidence |
| **Knowledge** | `KuIntelligenceService.assess_mastery_dual_track()` | `MasteryLevel` | per-(user, Ku) | Substance score (`calculate_user_substance` — how much the Ku is applied across the user's life) |

- **Per-entity** (Goals/Habits/Principles, `require_entity=True`): assesses one entity; persists to the
  entity's inline `dual_track_checkins: tuple[dict]` field.
- **User-level** (Tasks/Events/Choices, `require_entity=False`, `uid == user_uid`): assesses the user
  across all their entities of a kind; persists to `User.dual_track_checkins` (keyed by `DualTrackDimension`).
- **Knowledge** (`require_entity=True` — a Ku *is* an `:Entity`): a Ku is SHARED, so the per-(user, Ku)
  check-in persists to a **separate** `User.knowledge_checkins` field (keyed by Ku UID), never the
  shared `:Ku` node.

**Atomic persistence.** All `store_callback`s route through one node-write-lock appender
(`adapters/persistence/neo4j/_dual_track_checkin_store.py::atomic_append_checkin`), so concurrent
same-subject check-ins can't lose a snapshot. Canonical per-entity callback:
`BaseAnalyticsService._store_dual_track_checkin`; user-level: `UserService.append_dual_track_checkin`;
Knowledge: `UserService.append_knowledge_checkin`.

**Cross-domain synthesis.** `UserContextIntelligence.get_cross_domain_perception_analysis()`
(`PerceptionIntelligenceMixin`) reads all three sources and buckets each domain/dimension as
over-rated / under-rated / accurate — spanning every assessable dimension.

### Level Enums

Most dimensions use a 5-level `StrEnum` with bidirectional conversion methods, all in
`core/models/enums/activity_enums.py` (the Knowledge dimension's `MasteryLevel` lives there too —
distinct from `MasteryImpact`). **Exception: Principles** uses `AlignmentLevel` (8 values, in
`core/models/enums/principle_enums.py`), not a 5-level activity enum:

```python
class ProductivityLevel(StrEnum):
    HIGHLY_PRODUCTIVE = "highly_productive"          # 1.0
    PRODUCTIVE = "productive"                         # 0.8
    MODERATELY_PRODUCTIVE = "moderately_productive"   # 0.6
    STRUGGLING = "struggling"                         # 0.35
    OVERWHELMED = "overwhelmed"                       # 0.15

    def to_score(self) -> float: ...
    @classmethod
    def from_score(cls, score: float) -> "ProductivityLevel": ...
```

### Usage Pattern

```python
# User provides self-assessment (user-level dim — accessed via .intelligence)
result = await tasks_service.intelligence.assess_productivity_dual_track(
    user_uid="user_mike",
    user_level=ProductivityLevel.HIGHLY_PRODUCTIVE,
    user_evidence="I complete all my tasks on time",
    store_callback=store_callback,  # optional: persists the snapshot
)

if result.is_ok:
    assessment = result.value
    if assessment.has_perception_gap():
        print(f"Gap: {assessment.gap_direction} ({assessment.perception_gap:.0%})")
        for insight in assessment.insights:
            print(f"  - {insight}")
```

### HTTP Surfaces (HTMX, server-rendered)

Dual-track is a server-rendered HTMX surface — each self-rating POSTs a self-rate form and swaps in a
gap card + check-in trend (all `@csrf_protected`, since each persists a check-in):

| Surface | Route | Dimensions |
|---------|-------|-----------|
| Self Check-In page | `POST /self-checkin/results` | user-level (Productivity / Engagement / Decision Quality) |
| Activity detail pages | `POST /{domain}/dual-track/results` | per-entity (Goals / Habits / Principles) |
| Ku detail page | `POST /explore/ku/{uid}/mastery-checkin` | Knowledge (per-Ku mastery) |

The per-entity route is registered by the activity UI factory (`adapters/inbound/activity_ui_factory.py`)
when `ActivityUIConfig.dual_track_assess` is set; the Self Check-In page lives in
`adapters/inbound/self_checkin_routes.py`; the Ku mastery route is wired manually in
`adapters/inbound/learning_loop_routes.py`. Shared UI primitives: `ui/dual_track_card.py` (gap card +
trend), `ui/self_checkin.py`, `ui/explore/ku_mastery.py`.

### See Also

- [ADR-030: Dual-Track Assessment Pattern](../decisions/ADR-030-dual-track-assessment-pattern.md)
- `core/models/shared/dual_track.py` - `DualTrackResult[L]` generic model
- `core/models/enums/activity_enums.py` - Level enums

---

## Shared Intelligence Utilities

**Guide:** [SHARED_INTELLIGENCE_UTILITIES.md](./SHARED_INTELLIGENCE_UTILITIES.md)

The 6 Activity Domain intelligence services share common patterns consolidated into 4 shared utilities + 1 template method (January 2026):

| Utility | Location | Purpose |
|---------|----------|---------|
| **RecommendationEngine** | `recommendation_engine.py` | Fluent builder for threshold-based recommendations |
| **MetricsCalculator** | `metrics_calculator.py` | Static utility methods for common calculations |
| **PatternAnalyzer** | `pattern_analyzer.py` | Pattern detection in text and data structures |
| **TrendAnalyzer** | `trend_analyzer.py` | Threshold-based trend classification |
| **Template Method** | `BaseAnalyticsService._analyze_entity_with_typed_context()` | Fetch entity → get path-aware typed context → calculate metrics → generate recommendations |

**Consolidation Results:**
- **51 helper methods** analyzed across 6 services
- **~640 lines** consolidated into shared utilities
- **38-49% reduction** in helper code duplication

**Import Pattern:**
```python
from core.services.intelligence import (
    RecommendationEngine,
    MetricsCalculator,
    PatternAnalyzer,
    analyze_completion_trend,
    compare_progress_to_expected,
)
```

---

## Intelligence Services by Domain

### Activity (6)

| Service | Guide | Lines | Key Focus |
|---------|-------|-------|-----------|
| **Tasks** | [TASKS_INTELLIGENCE.md](./TASKS_INTELLIGENCE.md) | ~265 shell + 3 mixins | Behavioral insights, performance analytics, cross-domain context |
| **Goals** | [GOALS_INTELLIGENCE.md](./GOALS_INTELLIGENCE.md) | ~1,139 | Progress forecasting, predictive analytics |
| **Habits** | [HABITS_INTELLIGENCE.md](./HABITS_INTELLIGENCE.md) | ~539 | Streak patterns, habit formation insights |
| **Events** | [EVENTS_INTELLIGENCE.md](./EVENTS_INTELLIGENCE.md) | ~169 shell + 3 mixins | Cross-domain impact, learning practice tracking |
| **Choices** | [CHOICES_INTELLIGENCE.md](./CHOICES_INTELLIGENCE.md) | ~679 | Decision support, outcome analysis |
| **Principles** | [PRINCIPLES_INTELLIGENCE.md](./PRINCIPLES_INTELLIGENCE.md) | ~1,324 | Alignment analysis, conflict detection |

### Shared Knowledge Intelligence (1 service + 1 pattern engine)

*(Counts as **1** in the Overview tally — `ActivityKnowledgeIntelligenceService` is the service; `KnowledgePatternAnalyzer` is a shared pattern engine it and the activity domains consume, not a standalone intelligence service.)*

| Service | Location | Lines | Key Focus |
|---------|----------|-------|-----------|
| **ActivityKnowledgeIntelligenceService** | `/core/services/knowledge/` | ~310 | Knowledge suggestions, prerequisites, learning opportunities — shared across all 6 activity domains |
| **KnowledgePatternAnalyzer** | `/core/services/knowledge/knowledge_pattern_analyzer.py` | ~350 | Generic 5-pattern learning-pattern engine (KNOWLEDGE_BUILDING, CROSS_DOMAIN_APPLICATION, LEARNING_SPIRAL, SKILL_SPECIALIZATION, KNOWLEDGE_BRIDGING) — wired into all 6 activity domain facades via `analyze_learning_patterns()` + `GET /api/{domain}/knowledge-patterns` |

`ActivityKnowledgeIntelligenceService` extracted from TasksIntelligenceService (March 2026) — domain-agnostic suggestions/prerequisites via `PatternAnalyzer` on entity titles and graph traversal. `KnowledgePatternAnalyzer` generalized from `AnalyticsEngine` (June 2026, #366–#368) — generic dataclass engine typed `Generic[EntityT, RelT]`; `TaskKnowledgeAnalyzer` (`/core/services/tasks/task_knowledge_analyzer.py`) extends it with Task-specific `MASTERY_VALIDATION` pattern and `calculate_knowledge_aware_priority`. All 6 activity domains have knowledge relationships in Neo4j.

**Backend:** Uses `UniversalNeo4jBackend[Entity]` with `NeoLabel.ENTITY` — queries across ALL entity types. `find_by(user_uid=...)` matches the denormalized `user_uid` PROPERTY (not the `(User)-[:OWNS]->` edge); shared entities (PathStep, Ku, etc.) lack `user_uid` and naturally filter out. The property is kept aligned to the canonical `:OWNS` owner by the live write-paths + the 2026-06 backfill (`USER_UID_OWNS_BACKFILL_2026-06.md`). Uses `EntityStatus.COMPLETED` (not `CompletionStatus.DONE`) for completed entity queries.

**Pattern:** This service is the first production realization of the [Shared Signal pattern](../patterns/SHARED_SIGNAL_PATTERN.md) — cross-cutting infrastructure consulted by every Activity Domain facade via a narrow protocol + delegation mixin.

---

### Curriculum (3)

| Service | Guide | Lines | Key Focus |
|---------|-------|-------|-----------|
| **KU** | [KU_INTELLIGENCE.md](./KU_INTELLIGENCE.md) | ~390 | Semantic recommendations, knowledge substance, per-user substance (January 2026) |
| **PS** | [PS_INTELLIGENCE.md](./PS_INTELLIGENCE.md) | ~394 | Readiness checks, practice completeness |
| **LP** | [LP_INTELLIGENCE.md](./LP_INTELLIGENCE.md) | 378 (facade) + 2,467 (sub-services) | Learning state analysis, content recommendations, adaptive sequencing |

**MOC has no intelligence service** — it is emergent identity (any `Entity` with `ORGANIZES` edges); a Ku that organizes others is analyzed as a Ku via `KuIntelligenceService`. See [MOC_INTELLIGENCE.md](./MOC_INTELLIGENCE.md).

---

### Meta Intelligence (1)

| Service | Guide | Lines | Key Focus |
|---------|-------|-------|-----------|
| **UserContext** | [USER_CONTEXT_INTELLIGENCE.md](./USER_CONTEXT_INTELLIGENCE.md) | ~3,124 (modular package) | Central hub, daily planning (flagship: `get_ready_to_work_on_today()`) |

---

### Cross-Cutting Intelligence (1)

| Service | Guide | Lines | Key Focus |
|---------|-------|-------|-----------|
| **Askesis** | [ASKESIS_INTELLIGENCE.md](./ASKESIS_INTELLIGENCE.md) | ~1,180 (facade + 5 sub-services) | Life context synthesis, 13-domain recommendations (flagship: `get_daily_work_plan()`) |

**Note:** Askesis uses a custom facade pattern (not `BaseAnalyticsService`) because it synthesizes across all entity types rather than managing a single domain's entities.

---

## Common Features

### Inherited from BaseAnalyticsService

All domain intelligence services (except UserContext) inherit from `BaseAnalyticsService`:

**Dependency Checks** (inline guards — no helper methods):
```python
if not self.graph_intel:
    raise ValueError(f"{self.__class__.__name__}.method_name() requires graph_intel")
if not self.relationships:
    raise ValueError(f"{self.__class__.__name__}.method_name() requires relationship_service")
```

**Standard Attributes:**
- `self.backend` - Domain operations (REQUIRED)
- `self.graph_intel` - GraphIntelligenceService (optional, validated on use)
- `self.relationships` - UnifiedRelationshipService (optional)
- `self.event_bus` - EventBus (optional)
- `self.logger` - Hierarchical logger (`skuel.analytics.{domain}`)

**NOTE:** Analytics services explicitly DO NOT have `embeddings` or `llm` attributes. This is intentional - they work without AI dependencies. For AI features, use `BaseAIService`.

**Helper Methods:**
- `_to_domain_model()` - Convert DTO/dict to domain model

---

## Usage Patterns

### Access via Facade (Activity & Curriculum Domains)

All Activity and Curriculum domain services create intelligence internally:

```python
# Tasks example
tasks_service = TasksService(
    backend=tasks_backend,
    graph_intel=graph_intelligence,
    embeddings_service=embeddings_service,
    llm_service=llm_service,
)

# Access intelligence
insights = await tasks_service.intelligence.get_behavioral_insights(user_uid)
```

### Direct Instantiation (Meta Services)

UserContextIntelligence is created directly via factory:

```python
from core.services.user.intelligence import UserContextIntelligenceFactory

# Create with required domain services
user_intel = UserContextIntelligenceFactory.create(
    context=user_context,
    tasks_service=tasks_service,
    goals_service=goals_service,
    habits_service=habits_service,
    # ... 10 more required services
)

# Use flagship method
daily_plan = await user_intel.get_ready_to_work_on_today(user_uid)
```

---

## Dependencies

### Infrastructure Services

Intelligence services depend on shared infrastructure:

| Service | Purpose | Used By |
|---------|---------|---------|
| **GraphIntelligenceService** | Graph queries, context retrieval | All services |
| **OpenAIEmbeddingsService** | Semantic search, similarity | KU, LP, Tasks |
| **LLMService** | AI insights, text generation | KU, LP, UserContext |
| **UnifiedRelationshipService** | Relationship queries | Activity domains, Goals (REQUIRED) |

---

## Testing

### Unit Tests
```bash
# Test specific intelligence service
uv run python -m pytest tests/unit/services/test_{domain}_intelligence_service.py -v

# Test all intelligence services
uv run python -m pytest tests/unit/services/ -k "intelligence" -v
```

### Integration Tests
```bash
# Test with real backends
uv run python -m pytest tests/integration/intelligence/ -v

# Test specific method
uv run python -m pytest tests/integration/intelligence/ -k "test_predict_goal_success" -v
```

---

## Migration Status (January 2026)

**Migrated to BaseAnalyticsService (ADR-024, updated ADR-030):**
- ✅ TasksIntelligenceService (2026-01-06, updated 2026-01-18)
- ✅ GoalsIntelligenceService (2026-01-06, updated 2026-01-18)
- ✅ HabitsIntelligenceService (2026-01-06, updated 2026-01-18)
- ✅ EventsIntelligenceService (2026-01-06, updated 2026-01-18)
- ✅ ChoicesIntelligenceService (2026-01-06, updated 2026-01-18)
- ✅ PrinciplesIntelligenceService (2026-01-06, updated 2026-01-18)
- ✅ KuIntelligenceService (2026-01-08, updated 2026-01-18)
- ✅ PsIntelligenceService (2026-01-06, updated 2026-01-18)
- ✅ LpIntelligenceService (2026-01-08, updated 2026-01-18)
- ~~MocIntelligenceService (2026-01-11)~~ — **subsequently deleted** in the KU-based MOC refactoring (late January 2026); MOC is now emergent (see [MOC_INTELLIGENCE.md](./MOC_INTELLIGENCE.md)).

**Architecture Update (2026-01-18):**
- `BaseIntelligenceService` (old) → Replaced by `BaseAnalyticsService` + `BaseAIService`
- All domain services now extend `BaseAnalyticsService` (NO AI deps) — 9 today (was 10 before MOC's service was removed)
- `BaseAIService` introduced as the optional AI tier (since wired in FULL tier — 10 subclasses; see Overview)

**IntelligenceOperations Protocol Rollout (2026-01-17):**
- ✅ All domain services implement the **3-method route-factory surface** (`get_with_context` / `get_performance_analytics` / `get_domain_insights`) — 9 today (was 10 before MOC's service was removed). ⚠️ This does **not** mean they implement the 7-method `DomainIntelligenceOperations` / 11-method composed `IntelligenceOperations`: those are largely aspirational (only `get_performance_analytics` is universal — see the protocol note above).
- ✅ GraphContextLoader pattern consistent across all services
- ✅ Bug fixes applied (success_rate units, is_on_track(), progress guards)

**Knowledge Intelligence Extraction + Wiring (2026-03-21):**
- ✅ `ActivityKnowledgeIntelligenceService` created (`core/services/knowledge/`)
- ✅ Wired into all 6 Activity Domain facades as `self.knowledge_intelligence` (shared singleton)
- ✅ 4 delegation methods provided by `KnowledgeIntelligenceDelegationMixin` (`core/services/mixins/`) — facades inherit it (April 2026, replaced copy-pasted methods)
- ✅ Skill vocabulary derived from Ku titles/tags in graph (replaces hardcoded programming keywords)
- Backend: `UniversalNeo4jBackend[Entity]` with `NeoLabel.ENTITY` — queries user-owned activity entities across all domains
- Type: `BaseAnalyticsService[BackendOperations[Entity], Entity]`

**Protocol Alignment (2026-03-21):**
- ✅ Monolithic `IntelligenceOperations` (11 methods) split into ISP protocols
- ✅ `KnowledgeIntelligenceOperations` (4 methods) — satisfied by `ActivityKnowledgeIntelligenceService`
- ✅ `DomainIntelligenceOperations` (7 methods) — per-domain intelligence services
- ✅ `IntelligenceOperations` remains as composed protocol for backward compatibility

**Intelligence Mixin Decomposition (2026-04-10):**
- ✅ `TasksIntelligenceService` decomposed: shell (~265 lines) + `_core_intelligence_mixin`, `_analytics_mixin`, `_productivity_mixin`
- ✅ `EventsIntelligenceService` decomposed: shell (~169 lines) + `_core_intelligence_mixin`, `_analytics_mixin`, `_behavioral_signals_mixin`
- See `/docs/patterns/SERVICE_DECOMPOSITION_RULE.md` for decomposition thresholds and mixin patterns

**Standalone (modular package architecture):**
- UserContextIntelligence (ADR-021, mixin composition pattern)

---

## Service-Specific Highlights

### Activity Domains

**Tasks:**
- Behavioral insights (completion time, procrastination, peak productivity)
- Performance analytics (completion rates, trends, duration calibration via ADR-048)
- Cross-domain context categorization (unique semantic grouping)
- Knowledge intelligence extracted to shared `ActivityKnowledgeIntelligenceService` and wired back via `self.knowledge_intelligence` (March 2026)

**Goals:**
- Progress forecasting with velocity metrics
- Predictive analytics (success probability, habit impact, scenarios)
- Completion probability modeling (35% progress + 35% consistency + 15% time + 15% momentum)

**Habits:**
- Streak pattern analysis
- Knowledge reinforcement effectiveness (0-10 scale)
- Goal contribution strength calculation

**Events:**
- Cross-domain impact tracking
- Learning practice verification (knowledge substance philosophy)
- Schedule optimization with actionable insights

**Choices:**
- Decision complexity assessment
- Cascade impact analysis with PathAwareAnalyzer
- Regret minimization through risk assessment

**Principles:**
- Cross-domain alignment measurement
- Multi-principle conflict detection
- Strength analysis (impact score 0-10)

### Curriculum Domains

**KU (Knowledge Units):**
- Semantic relationship analysis with confidence scoring
- Cross-domain knowledge connections
- Knowledge substance tracking (how knowledge is LIVED)
- Per-user substance calculation (January 2026 - KU-Activity Integration)
- New API: `GET /api/ku/{uid}/my-context` for personalized KU views

**PS (Path Steps):**
- Lightweight intelligence (intentional design)
- Practice completeness scoring (1/3 contribution per type)
- Guidance strength calculation (40% principles + 60% choices)

**LP (Learning Paths):**
- Facade over 4 sub-services (LearningStateAnalyzer, LearningRecommendationEngine, ContentAnalyzer, ContentQualityAssessor)
- Learning state analysis (5 readiness states)
- Personalized content recommendations
- Quality assessment and similarity search

**MOC (Maps of Content):**
- No dedicated intelligence service (emergent identity — any `Entity` with `ORGANIZES` edges).
- ORGANIZES relationships are managed by `PsOrganizationService` (`core/services/ps/ps_organization_service.py`); MOC edges are authored via ingestion (`core/services/ingestion/moc_links.py`, `moc: true` frontmatter).
- MOC navigation is surfaced through UserContext (`active_moc_uids`, `recently_viewed_moc_uids`); a Ku that organizes others is analyzed as a Ku via `KuIntelligenceService`.
- The former `MocIntelligenceService` (navigation/coverage/bridge analytics) was deleted in the January-2026 KU-based refactoring. See [MOC_INTELLIGENCE.md](./MOC_INTELLIGENCE.md).

### Meta Intelligence

**UserContext:**
- Central intelligence hub answering "What should I work on next?"
- 8 flagship methods across 5 mixins
- **Flagship method:** `get_ready_to_work_on_today()` - Daily planning based on goals, habits, knowledge, schedule
- Requires 12 domain services (6 Activity + 2 Curriculum + 3 Processing + 1 Temporal)
- Optional: `filtered_providers` dict (11 `FilteredContextProvider` facades) — consumed by daily planning for domain health warnings (all 6 Activity domains + cross-domain balance checks)
- Modular package architecture (~3,124 lines)

---

## See Also

### Architecture Documentation
- `/docs/intelligence/SHARED_INTELLIGENCE_UTILITIES.md` - **Shared utilities consolidation (5-phase guide)**
- `/docs/decisions/ADR-024-base-intelligence-service-migration.md` - Unified base service pattern (now BaseAnalyticsService)
- `/docs/decisions/ADR-021-user-context-intelligence-modularization.md` - UserContext modular package
- `/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md` - Domain overview
- `/CLAUDE.md` - Intelligence Services Architecture section

### Implementation
- `/core/services/base_analytics_service.py` - Base class for domain analytics (NO AI deps)
- `/core/services/base_ai_service.py` - Base class for AI-powered features (optional)
- `/core/services/intelligence/` - **Shared utilities package (RecommendationEngine, MetricsCalculator, etc.)**
- `/core/services/infrastructure/graph_intelligence_service.py` - Graph queries
- `/core/services/embeddings_service.py` - Semantic search
- `/core/services/llm_service.py` - AI insights
- `/core/services/llm_caller.py` - UnifiedLLMCaller (routes to OpenAI/Anthropic by model prefix; used by JournalOutputService + EntryReportService)
- `/core/services/user/intelligence/` - UserContextIntelligence modular package

---

## Quick Start

### To add a new intelligence method:

1. Identify the domain (e.g., Tasks)
2. Check if the service is decomposed (Tasks, Events, Goals, Habits — see `SERVICE_DECOMPOSITION_RULE.md`):
   - **Decomposed:** add the method to the appropriate mixin file (e.g., `_analytics_mixin.py` for behavioral metrics)
   - **Single file:** add to `{domain}_intelligence_service.py` directly; extract to a mixin if the file exceeds ~350 lines
3. Follow the pattern:
   ```python
   async def get_new_insight(self, user_uid: UserUID, ...) -> Result[dict[str, Any]]:
       if not self.graph_intel:
           raise ValueError(f"{self.__class__.__name__}.get_new_insight() requires graph_intel")
       # Implementation
       return Result.ok({"insight": data})
   ```
4. Document in `/docs/intelligence/{DOMAIN}_INTELLIGENCE.md`
5. Add tests in `tests/unit/services/test_{domain}_intelligence_service.py`

### To use an intelligence method:

```python
result = await {domain}_service.intelligence.{method_name}(...)
if result.is_ok:
    data = result.value
    # Use data
else:
    error = result.expect_error()
    # Handle error
```

---

## Architecture Summary

**Total Intelligence Services (analytics/core-side):** 16 (see Overview for the full breakdown + scope boundary)
- 11 extend `BaseAnalyticsService` (unified pattern, NO AI deps): 6 Activity + 3 Curriculum (KU/PS/LP) + shared ActivityKnowledge + corpus KnowledgeHealth
- 1 uses modular package architecture (UserContext)
- 1 custom facade (Askesis) · 1 specialized graph service (ZPDService, FULL tier) · 1 cross-domain analytics service (CrossDomainAnalyticsService) · 1 lightweight recommendation service (LifePath)

**Plus a parallel wired AI tier** of 10 `BaseAIService` subclasses (FULL tier only, ADR-043; `services_bootstrap/_ai_wiring.py`), counted separately — see Overview.

**Lines of Intelligence Code** (approximate — `tracking: conceptual`):
- Activity Domains: ~4,434 lines
- Curriculum Domains: KU/PS/LP facades + sub-services (the former ~790-line MOC service was deleted)
- Meta Intelligence: ~3,124 lines (modular package)

**Intelligence Philosophy:**
- Domain services provide focused, domain-specific intelligence
- UserContext synthesizes cross-domain intelligence for daily planning
- All services return `Result[T]` for consistent error handling
- Fail-fast validation ensures required dependencies are available
- Graph-native relationships eliminate N+1 queries

**January 2026 Achievements:**
- Complete intelligence architecture unification across all domains with BaseAnalyticsService pattern (ADR-024, ADR-030)
- Comprehensive documentation for all 11 services as of January 2026 (6 Activity + 4 Curriculum + 1 Meta) — MOC's service was deleted later that month; see the Overview for today's inventory
- Full migration including KU, LP, and MOC domains (MOC's intelligence service was subsequently removed)
- Shared utilities consolidation (5-phase consolidation reducing ~640 lines of duplicated helper code)
- **KU-Activity Integration Enhancement** (January 11, 2026): Per-user substance calculation via `calculate_user_substance()` and new `/api/ku/{uid}/my-context` endpoint
- **Finance Domain Simplification** (January 17, 2026): Finance reverted to standalone bookkeeping domain (no intelligence service)
- **IntelligenceOperations Protocol Rollout** (January 17, 2026): domain services implement the standardized route-factory protocol, enabling automatic route generation via IntelligenceRouteFactory. *(Since superseded: the `GraphContextLoader` pattern was later deleted — see the mechanism-B note at the end of this file; and route generation covers 8 of the 9 domains — KU is protocol-conformant but unwired.)*
- **Dual-Track Assessment Pattern** (January 18, 2026 - ADR-030): All 6 Activity Domain intelligence services now support dual-track assessment comparing user self-assessment (vision) with system measurement (action) for perception gap analysis
- **Complete Substance Data Pipeline** (March 21, 2026): All 6 activity channels (Tasks, Habits, Events, Choices, Principles) now flow real data through UserContext into `calculate_user_substance()`. Principles added as 6th channel (0.07/principle, max 0.15). Total capped at 1.0. Journals deferred (submissions, not activities).
- **Protocol Alignment** (March 21, 2026): Monolithic `IntelligenceOperations` (11 methods) split into `KnowledgeIntelligenceOperations` (4, shared) + `DomainIntelligenceOperations` (7, per-domain). Composed `IntelligenceOperations` kept for backward compatibility.
- **Intent-traversal ↔ registry convergence — context retrieval is mechanism B** (June 2026, #241): `GraphContextLoader`, `_init_context_loader`, and `self.context_loader` were **deleted** (supersedes the "GraphContextLoader pattern" noted in the Jan 17 entries above). `get_with_context()` is now inherited from `_CoreIntelligenceMixin[T]` and routes through `self.relationships.get_with_context`, whose edge vocabulary comes from `DomainConfig.cross_domain_relationship_types` (the registry). Cross-domain analysis runs on the canonical typed reader `BaseAnalyticsService._analyze_entity_with_typed_context` (+ per-domain `{Domain}CrossContext.from_categorized`). See `/docs/roadmap/intent-traversal-registry-convergence.md`.
