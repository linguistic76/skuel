---
title: LifePath Domain
created: 2025-12-04
updated: 2026-06-12
status: current
category: domains
tags: [lifepath, destination-domain, domain]
---

# LifePath Domain

**Type:** Destination Domain
**Purpose:** "Am I living my life path?"

## Core Philosophy

LifePath is the destination that gives meaning to all other domains. Every task, goal, habit, choice, and piece of knowledge ultimately flows toward this question:

> "Am I living my life path?"

The key insight:

> "The user's vision is understood via the words user uses to communicate,
> the UserContext is determined via user's actions."

LifePath bridges the gap between:
- **VISION** (user's expressed intent in their own words)
- **ACTIONS** (actual behavior tracked via UserContext)
- **ALIGNMENT** (measured gap between vision and actions)

## Architecture Overview

```
Activity (6)              Curriculum (4)         Learning Loop
├── Tasks                 ├── Ku                 ├── UserEntries
├── Goals                 ├── PS                 ├── Exercises/Reports
├── Habits     ──────────►├── LP     ───────────►└── (ADR-054 pipeline)
├── Events                └── Exercise                    │
├── Choices                      │                        │
└── Principles                   │                        │
       │                         │                        │
       └─────────────────────────┴────────────────────────┘
                                         │
                                         ▼
                           ╔═════════════════════════╗
                           ║       LIFE PATH         ║
                           ║   The Destination       ║
                           ╚═════════════════════════╝
```

## Key Concept

LifePath is NOT a stored entity - it's a **DESIGNATION** that elevates a Learning Path (LP) to life path status, combined with the user's vision statement.

The flow:
1. User expresses **vision** in their own words ("I want to become a mindful technical leader")
2. System extracts **themes** from vision (leadership, mindfulness, technology)
3. Themes are matched to **LP candidates** (lp:mindful-engineer, lp:tech-leadership)
4. User **designates** an LP as their life path
5. System measures **alignment** between declared vision and actual behavior

## Service Architecture

LifePath uses the **facade pattern** with 4 specialized sub-services:

```
LifePathService (Facade)
├── .vision     → LifePathVisionService    (capture, analyze, recommend)
├── .core       → LifePathCoreService      (designation CRUD)
├── .alignment  → LifePathAlignmentService (calculate alignment)
└── .intelligence → LifePathIntelligenceService (recommendations)
```

### Sub-Service Responsibilities

| Sub-Service | Purpose |
|-------------|---------|
| **vision** | Capture user's vision statement, extract themes via LLM, recommend matching LPs; carries the staged word-action lens |
| **core** | CRUD for designation, manage ULTIMATE_PATH relationship, store vision data |
| **alignment** | Calculate 5-dimension alignment score from graph edges |
| **intelligence** | Generate personalized recommendations based on alignment |

## Key Files

| Component | Location |
|-----------|----------|
| **Service Facade** | `/core/services/lifepath/lifepath_service.py` |
| **Vision Service** | `/core/services/lifepath/lifepath_vision_service.py` |
| **Core Service** | `/core/services/lifepath/lifepath_core_service.py` |
| **Alignment Service** | `/core/services/lifepath/lifepath_alignment_service.py` |
| **Intelligence Service** | `/core/services/lifepath/lifepath_intelligence_service.py` |
| **Service-Layer Types** | `/core/services/lifepath/lifepath_types.py` (LifePathDesignation, VisionTheme, VisionCapture, LpRecommendation, WordActionAlignment) |
| **Entity Model + DTO** | `/core/models/life_path/` (EntityType.LIFE_PATH registry entry) |
| **Request Models** | `/core/models/lifepath_request.py` |
| **Backend** | `/adapters/persistence/neo4j/lifepath_backend.py` (LifePathBackendOperations) |
| **Routes** | `/adapters/inbound/lifepath_routes.py` (factory) |
| **API Routes** | `/adapters/inbound/lifepath_api.py` (4 routes) |
| **UI Routes** | `/adapters/inbound/lifepath_ui.py` (5 routes, thin — delegates to `ui/lifepath/`) |

## Domain Model

### LifePathDesignation (Frozen Dataclass)

```python
@dataclass(frozen=True)
class LifePathDesignation:
    user_uid: UserUID

    # THE VISION (user's own words)
    vision_statement: str
    vision_themes: tuple[str, ...]
    vision_captured_at: datetime | None

    # THE DESIGNATION (LP that embodies vision)
    life_path_uid: str | None
    designated_at: datetime | None

    # THE MEASUREMENT (stored overall score; alignment_level derived)
    alignment_score: float  # 0.0-1.0 overall
    alignment_level: AlignmentLevel
```

Per-dimension scores live on the `ULTIMATE_PATH` edge (written by
`update_alignment_score`); fresh dimension breakdowns come from
`LifePathAlignmentService.calculate_alignment`, not from this view.

### AlignmentLevel Enum

| Level | Score Range | Description |
|-------|-------------|-------------|
| **FLOURISHING** | 0.9+ | Life purpose deeply integrated |
| **ALIGNED** | 0.7-0.9 | Consistent alignment with life path |
| **EXPLORING** | 0.4-0.7 | Making progress, some drift |
| **DRIFTING** | <0.4 | Significant misalignment |

## 5-Dimension Alignment

LifePath calculates alignment across 5 weighted dimensions:

| Dimension | Weight | What It Measures | No data |
|-----------|--------|------------------|---------|
| **Knowledge** | 25% | Mastery of the path's Kus (0.6) + what the learner has DONE with them, scored by `USER_SUBSTANCE_CHANNELS` | 0.0 |
| **Activity** | 25% | What share of the learner's tasks and habits point at the life path, blended in the table's task:habit proportion (⅓ : ⅔) | 0.0 |
| **Goal** | 20% | Active goals that `SERVES_LIFE_PATH` | 0.0 |
| **Principle** | 15% | Active principles that `SERVES_LIFE_PATH` | 0.0 |
| **Momentum** | 15% | Rate of NEW path-aligned commitments — tasks *and* habits created — last 7 days vs the 7 before | **0.5** |

**Formula:**
```python
alignment_score = (
    knowledge_alignment * 0.25 +
    activity_alignment * 0.25 +
    goal_alignment * 0.20 +
    principle_alignment * 0.15 +
    momentum * 0.15
)
```

**Where the scoring lives.** `LifePathBackend` returns mastery and counts only;
`LifePathAlignmentService` owns every ratio, weight, band and the no-data rule.
The per-instance substance weights come from
`core/services/knowledge/user_substance.py` and are not restated in Cypher —
they were, and that copy drifted into reading habits over `APPLIES_KNOWLEDGE`,
an edge no habit writer emits.

**Habits reach knowledge over `REINFORCES_KNOWLEDGE`** (writer:
`HabitsCoreService`); tasks over `APPLIES_KNOWLEDGE`. The two are told apart by
`entity_type` at the tail, not by the edge.

**A level with no evidence scores 0.0, not 0.5.** Only momentum keeps a neutral
default, being a rate rather than a level. Scores recorded before 2026-08-12 are
on the old basis and are not comparable. See
[knowledge_substance_philosophy.md](../architecture/knowledge_substance_philosophy.md)
§ Ruling: the five-dimension metric reads the table too.

**Failures propagate.** `get_alignment`, `designate_and_calculate` and
`get_full_status` all return `Result.fail` on a failed read rather than a low
score or `alignment=None` — with no-data at 0.0, a silent fallback is
indistinguishable from a learner who has done nothing, and gets persisted as
one.

## Routes

**Architecture:** DomainRouteConfig pattern (migrated 2026-02-03)
- Main file: 32 lines (configuration factory)
- API routes: 121 lines (4 JSON endpoints)
- UI routes: 501 lines (5 pages + 7 helper functions)

See: [DomainRouteConfig Pattern](../patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md)

### UI Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/lifepath` | GET | Main life path dashboard |
| `/lifepath/vision` | GET | Vision capture page |
| `/lifepath/vision` | POST | Process vision capture |
| `/lifepath/designate` | POST | Designate an LP as life path |
| `/lifepath/alignment` | GET | Alignment dashboard |

### API Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/lifepath/status` | GET | Get full status (JSON) |
| `/api/lifepath/vision` | POST | Capture vision (JSON) |
| `/api/lifepath/designate` | POST | Designate life path (JSON) |
| `/api/lifepath/alignment` | GET | Get alignment data (JSON) |

## Relationships

| Relationship | Direction | Source | Description |
|--------------|-----------|--------|-------------|
| `SERVES_LIFE_PATH` | Incoming | All Domains | Everything flows toward life path |
| `ULTIMATE_PATH` | `(User)-[:ULTIMATE_PATH]->(Lp)` | User → LP | User's designated life path; carries current alignment score + dimension scores |
| `ALIGNMENT_SNAPSHOT` | `(User)-[:ALIGNMENT_SNAPSHOT {date, score}]->(Lp)` | User → LP | Daily alignment history — one per day, idempotent; powers trend analysis |

## Usage Example

```python
from core.services.lifepath import LifePathService

lifepath = LifePathService(driver, lp_service, ku_service, user_service, llm_service)

# 1. Capture vision
vision = await lifepath.vision.capture_vision(
    user_uid,
    "I want to become a mindful technical leader who builds meaningful products"
)
# Themes extracted: ["leadership", "mindfulness", "technology", "impact"]

# 2. Get LP recommendations based on vision
recommendations = await lifepath.vision.recommend_learning_paths(vision.themes)

# 3. Designate an LP as life path
designation = await lifepath.core.designate_life_path(user_uid, "lp:tech-leadership")

# 4. Calculate alignment
alignment = await lifepath.get_alignment(user_uid)
# alignment_score: 0.72 (ALIGNED); per-dimension scores in alignment["dimensions"]

# 5. Get recommendations
recs = await lifepath.intelligence.get_recommendations(user_uid, alignment)
```

## Three-Tier Type System

LifePath follows SKUEL's three-tier pattern:

| Tier | File | Purpose |
|------|------|---------|
| **External (Tier 1)** | `core/models/lifepath_request.py` | Pydantic validation for API |
| **Transfer (Tier 2)** | `core/models/life_path/life_path_dto.py` | Mutable DTOs for data transfer |
| **Core (Tier 3)** | `core/models/life_path/life_path.py`, `core/services/lifepath/lifepath_types.py` | Frozen domain models + service-layer views |

## UserContext Wiring

The MEGA-QUERY surfaces the designation to the whole intelligence stack
(flagship `calculate_life_path_alignment`, Analytics, Askesis, ZPD): it
matches the designated node by `entity_type: 'life_path'` (designation flips
the property, never the label) and reads `alignment_score` off the
`ULTIMATE_PATH` edge — see `user_context_queries.py` "LIFE PATH" section.

## Key Insight

LifePath answers the meta-question that SKUEL is designed around:

> "You do not rise to the level of your goals. You fall to the level of your systems." - James Clear

LifePath measures whether your SYSTEMS (habits, knowledge, principles) are aligned with your ultimate PURPOSE. It bridges the gap between what you SAY you want (vision) and what you actually DO (actions).

## See Also

- [Goals Domain](goals.md) - Goals serve life path
- [LP Domain](lp.md) - One LP is the "life path"
- [ADR-011: Life Path Alignment Query](../decisions/ADR-011-life-path-alignment-query.md)
- [Knowledge Substance Philosophy](../architecture/knowledge_substance_philosophy.md)
- [Entity Type Architecture](../architecture/ENTITY_TYPE_ARCHITECTURE.md)
