---
title: LifePath Domain
created: 2025-12-04
updated: 2026-01-07
status: current
category: domains
tags: [lifepath, destination-domain, domain]
---

# LifePath Domain

**Type:** Destination Domain (The 14th Domain)
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
Activity (6)              Curriculum (3)         Content/Org (3)
├── Tasks                 ├── KU                 ├── Journals
├── Goals                 ├── LS                 ├── Assignments
├── Habits     ──────────►└── LP     ───────────►└── MOC (graph)
├── Events                      │                        │
├── Choices                     │                        │
└── Principles                  │                        │
       │                        │                        │
       │    Finance (1)         │                        │
       └──►├── Expenses ────────┴────────────────────────┘
                                         │
                                         ▼
                           ╔═════════════════════════╗
                           ║       LIFE PATH         ║
                           ║   Domain #14: The       ║
                           ║   Destination           ║
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
| **vision** | Capture user's vision statement, extract themes via LLM, recommend matching LPs |
| **core** | CRUD for designation, manage ULTIMATE_PATH relationship, store vision data |
| **alignment** | Calculate 5-dimension alignment score, measure word-action gap |
| **intelligence** | Generate personalized recommendations based on alignment |

## Key Files

| Component | Location |
|-----------|----------|
| **Service Facade** | `/core/services/lifepath/lifepath_service.py` |
| **Vision Service** | `/core/services/lifepath/lifepath_vision_service.py` |
| **Core Service** | `/core/services/lifepath/lifepath_core_service.py` |
| **Alignment Service** | `/core/services/lifepath/lifepath_alignment_service.py` |
| **Intelligence Service** | `/core/services/lifepath/lifepath_intelligence_service.py` |
| **Domain Model** | `/core/models/lifepath/lifepath.py` |
| **Vision Models** | `/core/models/lifepath/vision.py` |
| **DTOs** | `/core/models/lifepath/lifepath_dto.py` |
| **Request Models** | `/core/models/lifepath/lifepath_request.py` |
| **Routes** | `/adapters/inbound/lifepath_routes.py` |

## Domain Model

### LifePathDesignation (Frozen Dataclass)

```python
@dataclass(frozen=True)
class LifePathDesignation:
    user_uid: str

    # THE VISION (user's own words)
    vision_statement: str
    vision_themes: tuple[str, ...]
    vision_captured_at: datetime | None

    # THE DESIGNATION (LP that embodies vision)
    life_path_uid: str | None
    designated_at: datetime | None

    # THE MEASUREMENT (5-dimensional alignment)
    alignment_score: float  # 0.0-1.0 overall
    word_action_gap: float
    alignment_level: AlignmentLevel

    # Dimension scores
    knowledge_alignment: float   # 25%
    activity_alignment: float    # 25%
    goal_alignment: float        # 20%
    principle_alignment: float   # 15%
    momentum: float              # 15%
```

### AlignmentLevel Enum

| Level | Score Range | Description |
|-------|-------------|-------------|
| **FLOURISHING** | 0.9+ | Life purpose deeply integrated |
| **ALIGNED** | 0.7-0.9 | Consistent alignment with life path |
| **EXPLORING** | 0.4-0.7 | Making progress, some drift |
| **DRIFTING** | <0.4 | Significant misalignment |

## 5-Dimension Alignment

LifePath calculates alignment across 5 weighted dimensions:

| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| **Knowledge** | 25% | Mastery of knowledge in life path LP |
| **Activity** | 25% | Tasks/habits supporting life path |
| **Goal** | 20% | Active goals contributing to life path |
| **Principle** | 15% | Values aligned with life path direction |
| **Momentum** | 15% | Recent activity trend toward life path |

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

## Routes

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
| `ULTIMATE_PATH` | `(User)-[:ULTIMATE_PATH]->(Lp)` | User → LP | User's designated life path |

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
alignment = await lifepath.alignment.calculate_alignment(user_uid)
# alignment_score: 0.72 (ALIGNED)
# weakest dimension: "knowledge" (needs more KU mastery)

# 5. Get recommendations
recs = await lifepath.intelligence.get_recommendations(user_uid, alignment)
```

## Three-Tier Type System

LifePath follows SKUEL's three-tier pattern:

| Tier | File | Purpose |
|------|------|---------|
| **External (Tier 1)** | `lifepath_request.py` | Pydantic validation for API |
| **Transfer (Tier 2)** | `lifepath_dto.py` | Mutable DTOs for data transfer |
| **Core (Tier 3)** | `lifepath.py`, `vision.py` | Frozen domain models |

## Key Insight

LifePath answers the meta-question that SKUEL is designed around:

> "You do not rise to the level of your goals. You fall to the level of your systems." - James Clear

LifePath measures whether your SYSTEMS (habits, knowledge, principles) are aligned with your ultimate PURPOSE. It bridges the gap between what you SAY you want (vision) and what you actually DO (actions).

## See Also

- [Goals Domain](goals.md) - Goals serve life path
- [LP Domain](lp.md) - One LP is the "life path"
- [ADR-011: Life Path Alignment Query](../decisions/ADR-011-life-path-alignment-query.md)
- [Knowledge Substance Philosophy](../architecture/knowledge_substance_philosophy.md)
- [Fourteen Domain Architecture](../architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md)
