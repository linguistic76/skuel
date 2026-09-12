---
updated: 2026-09-12
---

# Priority & Confidence Architecture
*Last updated: 2026-03-05*

> **Core Principle:** "Two orthogonal dials — Priority says how important, Confidence says how certain"

Priority and Confidence are SKUEL's two first-class customization dials. They are the most
fundamental way users and admins express dimensional weight across the knowledge graph.

**See:** `/docs/decisions/ADR-045-priority-confidence-customization-dials.md` — decision rationale

---

## The Two Dials

| Dial | Question | Set By | Lives On |
|------|----------|--------|----------|
| **Priority** | "How important is this right now?" | User | All UserOwnedEntity nodes |
| **Confidence** | "How certain are we about this?" | Admin (entity); User (edge) | Curriculum nodes; lateral relationship edges |

They are **independent dimensions** — any combination is valid:

```
HIGH + CERTAIN       → Execute now. Important AND well-founded.
HIGH + UNCERTAIN     → Investigate first. Important but uncertain.
LOW + CERTAIN        → Reliable background. Not urgent.
LOW + UNCERTAIN      → Prune or validate. Low signal.
```

---

## Where Priority Lives

**Field:** `UserOwnedEntity.priority: str | None`

**File:** `core/models/user_owned_entity.py`

**Enum:** `Priority` in `core/models/enums/activity_enums.py`

**Domains:** every model in the `UserOwnedEntity` hierarchy inherits `priority`:

| Model | EntityType |
|-------|-----------|
| Task | TASK |
| Goal | GOAL |
| Habit | HABIT |
| Event | EVENT |
| Choice | CHOICE |
| Principle | PRINCIPLE |
| UserEntry | USER_ENTRY |
| EntryReport | ENTRY_REPORT |
| ActivityReport | ACTIVITY_REPORT |
| RevisedExercise | REVISED_EXERCISE |
| FormSubmission | FORM_SUBMISSION |
| Interaction | INTERACTION |
| LifePath | LIFE_PATH |

**Values:**

| Level | `to_numeric()` | `get_color()` | Meaning |
|-------|----------------|---------------|---------|
| `LOW` | 1 | `#10B981` (green) | Can wait |
| `MEDIUM` | 2 | `#3B82F6` (blue) | Normal priority |
| `HIGH` | 3 | `#F59E0B` (amber) | Should do soon |

```python
from core.models.enums import Priority

Priority.HIGH.to_numeric()                   # → 3
Priority.HIGH.get_color()                    # → "#F59E0B" (amber)
Priority.from_search_text("urgent")          # → [Priority.HIGH]
```

---

## Where Confidence Lives

### On Curriculum Entities

**Field:** `Curriculum.confidence: str | None`

**File:** `core/models/curriculum.py`

**Request models:** `core/models/pathways/pathways_request.py` (PathStepCreateRequest, LpCreateRequest) — used by ingestion, not CRUD routes

**Domains:** KU, PS (PathStep), LP (LearningPath)

Set by admins when creating or updating curriculum content — "how certain are we that this
knowledge is accurate, pedagogically sound, and ready for learners?"

### On Lateral Relationship Edges

**Property:** `rel.confidence` — stored as `float` (0.0–1.0) on all lateral relationship edges

**Domains:** All 9 relationship-enabled domains (Tasks, Goals, Habits, Events, Choices, Principles,
KU, PS, LP)

**Enum:** `Confidence` in `core/models/enums/activity_enums.py`

**Values:**

| Level | `to_numeric()` | `get_color()` | Meaning |
|-------|----------------|---------------|---------|
| `UNCERTAIN` | 0.3 | `#EF4444` (red) | Speculative, needs validation |
| `LOW` | 0.5 | `#F59E0B` (amber) | Tentative working assumption |
| `MEDIUM` | 0.7 | `#3B82F6` (blue) | Reasonably confident |
| `HIGH` | 0.9 | `#10B981` (green) | Well-validated |
| `CERTAIN` | 1.0 | `#6D28D9` (purple) | Foundational, absolute |

```python
from core.models.enums import Confidence

Confidence.HIGH.to_numeric()              # → 0.9
Confidence.CERTAIN.get_color()            # → "#6D28D9" (purple)
Confidence.from_numeric(0.6)              # → Confidence.MEDIUM
Confidence.from_search_text("unsure")     # → [Confidence.UNCERTAIN, Confidence.LOW]
```

### NOT on Activity Domains (By Design)

Activity domains (Tasks, Goals, Habits, Events, Choices, Principles) use the **Dual-Track
Assessment system** (ADR-030) for self-assessment: ProductivityLevel, ProgressLevel,
ConsistencyLevel, EngagementLevel, DecisionQualityLevel. These five enums capture
"how am I doing?" per domain — a richer signal than a single Confidence level.

Adding Confidence to Activity domains would duplicate this signal and clutter the UI.

---

## Planning Layer: Priority → ranking

`daily_planning.py` does not read Priority. Priority reaches planning through the surfaces that
rank by it — every one of them through the enum's own methods, never a hand-written ladder:

| Surface | Read |
|---------|------|
| Calendar optimization (`calendar_optimization_service.py`, `_strategies.py`) | HIGH tasks add intrinsic load and join the peak-energy bucket, ordered by `sort_order()` |
| Search scoring (`core/models/search/scoring.py`) | `score_priority_level` → HIGH 1.0 / MEDIUM 0.5 / LOW 0.25 |
| Profile previews, list sorts (`profile_orchestrator.py`, `core/utils/entity_filters.py`) | sort by `sort_order()`; the view vocabulary IS the enum's three values (the day view orders by date, not priority — every priority renders there) |
| Goal scheduling (`goals_scheduling_service.py`) | priority weight in the goal score; the HIGH-count recommendation is advisory |

---

## Graph Layer: Confidence → vis.js Edge Styling

`get_relationship_graph()` returns `confidence` and `priority` on each edge in vis.js format.

**File:** `core/services/lateral_relationships/lateral_relationship_service.py`

**Edge styling** in `static/js/skuel.js` `renderNetwork()`:

| Confidence | Line Style | Opacity |
|------------|------------|---------|
| `≥ 0.8` (HIGH/CERTAIN) | Solid | 100% |
| `0.5–0.8` (MEDIUM) | Dashed `[8, 4]` | 70% |
| `< 0.5` (LOW/UNCERTAIN) | Dotted `[3, 3]` | 50% |

**Edge width** from Priority (stored on edge as string, converted via `to_numeric()`):

| Priority | Width |
|----------|-------|
| HIGH | 3px |
| MEDIUM | 2px |
| LOW | 1px |

---

## Key Files

| File | Role |
|------|------|
| `core/models/enums/activity_enums.py` | `Priority` and `Confidence` enum definitions |
| `core/models/user_owned_entity.py` | `priority: str \| None` field declaration |
| `core/models/curriculum.py` | `confidence: str \| None` field declaration |
| `core/models/pathways/pathways_request.py` | `confidence` in PS/LP create requests |
| `core/services/lateral_relationships/lateral_relationship_service.py` | `confidence` + `priority` on graph edges |
| `static/js/skuel.js` | vis.js edge styling by confidence and priority |

---

## Extension Points

Future capabilities enabled by these dials:

| Extension | Description |
|-----------|-------------|
| **Confidence-weighted search** | High-confidence KU ranks higher in search results |
| **Uncertainty review queue** | Admin dashboard for UNCERTAIN curriculum items awaiting review |
| **Priority-filtered notifications** | Push notifications only for HIGH items |
| **Confidence decay** | Certainty degrades over time without active reinforcement |
| **Cross-domain propagation** | If prerequisite KU is UNCERTAIN, dependent PS confidence drops automatically |

---

## See Also

- `/docs/decisions/ADR-045-priority-confidence-customization-dials.md` — decision rationale (why two dials, why enum, why these placements)
- `/docs/architecture/ENUM_ARCHITECTURE.md` — complete enum catalog; "Customization Dials" section
- `/docs/decisions/ADR-030-usercontext-file-consolidation.md` — Dual-Track Assessment (the self-assessment complement for Activity domains)
- `/docs/decisions/ADR-037-lateral-relationships-visualization-phase5.md` — vis.js graph where edge confidence appears
