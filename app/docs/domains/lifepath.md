---
title: LifePath Domain
created: 2025-12-04
updated: 2026-10-31
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
2. System extracts **themes** from vision (leadership, mindfulness, technology) — by the LLM in FULL tier, by keyword matching in CORE and whenever the LLM's reply yields no usable theme
3. Themes are matched to **LP candidates** (lp.mindful-engineer, lp.tech-leadership)
4. User **designates** an LP as their life path
5. System measures **alignment** between declared vision and actual behavior

## Service Architecture

LifePath uses the **facade pattern** with 4 specialized sub-services:

```
LifePathService (Facade)
├── .vision     → LifePathVisionService    (capture, analyze, match)
├── .core       → LifePathCoreService      (designation CRUD)
├── .alignment  → LifePathAlignmentService (calculate alignment)
└── .intelligence → LifePathIntelligenceService (recommendations)
```

### Sub-Service Responsibilities

| Sub-Service | Purpose |
|-------------|---------|
| **vision** | Capture user's vision statement, extract themes (the `lifepath_vision_themes` prompt in FULL tier; keyword matching in CORE, and whenever a provider failure or an unreadable reply leaves the LLM's answer with no usable theme — a vision is never refused for its extraction), match LPs to them (`match_learning_paths`); carries the staged word-action lens |
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
- `lifepath_routes.py` — the configuration factory
- `lifepath_api.py` — 4 JSON endpoints
- `lifepath_ui.py` — the pages, their HTMX fragments and the alignment radar's chart config

See: [DomainRouteConfig Pattern](../patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md)

### UI Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/lifepath` | GET | Main life path dashboard — with a saved vision, a "Recommended Paths" button beside "View Alignment Details" and "Update Vision"; while no path is chosen, the alignment card links "See your recommended Learning Paths" too |
| `/lifepath/vision` | GET | Vision capture page — the form holds the saved vision (`get_vision`); a failed read is its banner and no form |
| `/lifepath/vision` | POST | Capture the vision (`capture_vision`: extract the themes, save both) — 303 to `/lifepath/vision/recommendations`; a refused or unsaved vision re-renders the form with its banner and the learner's text |
| `/lifepath/vision/recommendations` | GET | Learning Paths recommended from the **saved** vision's themes (`get_vision`, then `match_learning_paths` — no theme extraction, so a reload costs a search); no saved vision → 303 to `/lifepath/vision`; no themes → the way back to revise it; a failed read is a banner; each card is a native "Choose This Path" form, but the learner's designated path's, which says "Your current path" in its place |
| `/lifepath/designate` | POST | Designate an LP as life path — a native form post: 303 to `/lifepath/alignment`, or the refusal in the Life Path shell with the way back to the recommendations |
| `/lifepath/alignment` | GET | Alignment page: the 5-dimension breakdown (the page's one alignment figure), then the path's steps by `SubstanceBand` and where the practice comes from — `AnalyticsService.calculate_life_path_alignment`, read beside `get_full_status`; a failed substance read banners only its two cards; with no designated path the content answers `HX-Redirect` to `/lifepath/vision/recommendations`, where a path is chosen |

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

lifepath = LifePathService(
    backend, lp_service, ku_service, user_service, llm_service, cross_domain_backend
)

# 1. Capture the vision: extract its themes and save both (a failed save fails it)
vision = (await lifepath.capture_vision(
    user_uid,
    "I want to become a mindful technical leader who builds meaningful products"
)).value
# vision["themes"]: CORE's keyword match finds ["technical", "meaning"]; FULL's LLM reads more

# 2. Recommend LPs from the saved themes — one search per theme, best match first
saved = (await lifepath.get_vision(user_uid)).value  # statement, themes, life_path_uid
recommendations = await lifepath.match_learning_paths(saved["themes"])

# 3. Designate an LP as life path and score its alignment
designation = await lifepath.designate_and_calculate(user_uid, "lp.tech.leadership")

# 4. Calculate alignment
alignment = await lifepath.get_alignment(user_uid)
# alignment_score: 0.72 (ALIGNED); per-dimension scores in alignment["dimensions"]
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
(flagship `calculate_life_path_alignment`, Analytics, Askesis, ZPD): it reaches
the designated path by **traversing `ULTIMATE_PATH`** and reads `alignment_score`
off that same edge — see `user_context_queries.py` "LIFE PATH" section.

⚠ **Nothing on the node marks it as a life path.** Designation is the edge and
only the edge; the path keeps its `:LearningPath` label and its
`'learning_path'` entity_type throughout, so a predicate of
`{entity_type: 'life_path'}` matches **zero rows** and would report every
designated learner as having no life path. It used to flip that property in
place, which put the label and the discriminator into permanent disagreement —
see [LIFEPATH_ALIGNMENT_DEBT.md](../technical_debt/LIFEPATH_ALIGNMENT_DEBT.md)
item 2 for what that cost.

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
