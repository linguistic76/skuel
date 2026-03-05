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
CRITICAL + CERTAIN   → Execute now. Important AND well-founded.
CRITICAL + UNCERTAIN → Investigate first. Important but uncertain.
LOW + CERTAIN        → Reliable background. Not urgent.
LOW + UNCERTAIN      → Prune or validate. Low signal.
```

---

## Where Priority Lives

**Field:** `UserOwnedEntity.priority: str | None`

**File:** `core/models/user_owned_entity.py`

**Enum:** `Priority` in `core/models/enums/activity_enums.py`

**Domains:** All 8 models in the UserOwnedEntity hierarchy:

| Domain | EntityType |
|--------|-----------|
| Tasks | TASK |
| Goals | GOAL |
| Habits | HABIT |
| Events | EVENT |
| Choices | CHOICE |
| Principles | PRINCIPLE |
| Submissions | SUBMISSION, JOURNAL |
| LifePath | LIFE_PATH |

**Values:**

| Level | `to_numeric()` | `get_color()` | Meaning |
|-------|----------------|---------------|---------|
| `LOW` | 1 | `#10B981` (green) | Can wait |
| `MEDIUM` | 2 | `#3B82F6` (blue) | Normal priority |
| `HIGH` | 3 | `#F59E0B` (amber) | Should do soon |
| `CRITICAL` | 4 | `#DC2626` (red) | Override today's plan |

```python
from core.models.enums import Priority

Priority.HIGH.to_numeric()                   # → 3
Priority.HIGH.get_color()                    # → "#F59E0B" (amber)
Priority.from_search_text("urgent")          # → [Priority.HIGH, Priority.CRITICAL]
```

---

## Where Confidence Lives

### On Curriculum Entities

**Field:** `Curriculum.confidence: str | None`

**File:** `core/models/curriculum/curriculum.py`

**Request models:** `core/models/curriculum/curriculum_requests.py` (KuCreateRequest, LsCreateRequest, LpCreateRequest)

**Domains:** KU, LS (LearningStep), LP (LearningPath)

Set by admins when creating or updating curriculum content — "how certain are we that this
knowledge is accurate, pedagogically sound, and ready for learners?"

### On Lateral Relationship Edges

**Property:** `rel.confidence` — stored as `float` (0.0–1.0) on all lateral relationship edges

**Domains:** All 9 relationship-enabled domains (Tasks, Goals, Habits, Events, Choices, Principles,
KU, LS, LP)

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

## Planning Layer: Priority → daily_planning.py

`get_ready_to_work_on_today()` applies a **CRITICAL priority override** before returning its
ranked `DailyWorkPlan`. Any entity with `priority = "critical"` from `context.entities_rich`
(all 6 Activity Domains) is moved to the front of its uid list, capped at **3 items total**
across all domains.

**Guard:** Only fires when `context.is_rich_context` is `True` — i.e., `build_rich()` was called,
not `build()`.

**File:** `core/services/user/intelligence/daily_planning.py` — "CRITICAL PRIORITY OVERRIDE" block

**Logic sketch:**

```python
# Collect CRITICAL entities across all 6 Activity domains
critical_uids = []
for domain_key in ["tasks", "goals", "habits", "events", "choices", "principles"]:
    for entity in context.entities_rich.get(domain_key, []):
        if entity.get("priority") == Priority.CRITICAL.value:
            critical_uids.append(entity["uid"])
            if len(critical_uids) >= 3:
                break

# Insert CRITICAL items at top of plan before returning
```

The cap of 3 prevents CRITICAL from becoming meaningless if users over-apply it.

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
| CRITICAL | 4px |
| HIGH | 3px |
| MEDIUM | 2px |
| LOW | 1px |

---

## Key Files

| File | Role |
|------|------|
| `core/models/enums/activity_enums.py` | `Priority` and `Confidence` enum definitions |
| `core/models/user_owned_entity.py` | `priority: str \| None` field declaration |
| `core/models/curriculum/curriculum.py` | `confidence: str \| None` field declaration |
| `core/models/curriculum/curriculum_requests.py` | `confidence` in KU/LS/LP create/update requests |
| `core/services/user/intelligence/daily_planning.py` | CRITICAL priority override in planning |
| `core/services/lateral_relationships/lateral_relationship_service.py` | `confidence` + `priority` on graph edges |
| `static/js/skuel.js` | vis.js edge styling by confidence and priority |

---

## Extension Points

Future capabilities enabled by these dials:

| Extension | Description |
|-----------|-------------|
| **Confidence-weighted search** | High-confidence KU ranks higher in search results |
| **Uncertainty review queue** | Admin dashboard for UNCERTAIN curriculum items awaiting review |
| **Priority-filtered notifications** | Push notifications only for CRITICAL items |
| **Confidence decay** | Certainty degrades over time without active reinforcement |
| **Cross-domain propagation** | If prerequisite KU is UNCERTAIN, dependent LS confidence drops automatically |

---

## See Also

- `/docs/decisions/ADR-045-priority-confidence-customization-dials.md` — decision rationale (why two dials, why enum, why these placements)
- `/docs/architecture/ENUM_ARCHITECTURE.md` — complete enum catalog; "Customization Dials" section
- `/docs/decisions/ADR-030-usercontext-file-consolidation.md` — Dual-Track Assessment (the self-assessment complement for Activity domains)
- `/docs/decisions/ADR-037-lateral-relationships-visualization-phase5.md` — vis.js graph where edge confidence appears
