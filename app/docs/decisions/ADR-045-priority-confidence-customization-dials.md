---
title: ADR-045: Priority & Confidence as First-Class Customization Dials
updated: 2026-03-05
status: current
category: decisions
tags: [adr, decisions, enums, priority, confidence, planning, graph-visualization]
related: [ADR-030, ADR-037]
---

# ADR-045: Priority & Confidence as First-Class Customization Dials

**Status:** Accepted

**Date:** 2026-03-05

**Decision Type:** ⬜ Query Architecture  ⬜ Graph Schema  ✅ Pattern/Practice

**Related ADRs:**
- Related to: ADR-030 (Dual-Track Assessment — the self-assessment system for Activity domains)
- Related to: ADR-037 (Lateral Relationships Visualization — where edge confidence appears in vis.js)

---

## Context

SKUEL needed a lightweight mechanism for users and admins to express dimensional weight on entities
and relationships across the knowledge graph — independent of domain-specific metadata.

Two orthogonal concerns emerged from actual usage:

1. **Importance/urgency** — "How much does this matter right now?" This belongs on *activity entities*
   (Tasks, Goals, Habits, Events, Choices, Principles) where urgency is user-controlled.

2. **Epistemic certainty** — "How sure are we about this?" This belongs on *curriculum entities*
   (KU, LS, LP) where knowledge confidence is admin-assessed, and on *lateral relationship edges*
   where it represents the strength of the assertion that two entities are related.

These dimensions appear together constantly in real planning:
> "I have a CRITICAL task (priority), but I'm UNCERTAIN (confidence) whether it'll be completed."
> "This KU is CERTAIN (confidence) foundational knowledge, LOW priority for *this* user right now."

Without first-class support, both dimensions collapsed into ad-hoc string fields or got lost.

---

## Decision

**Priority and Confidence are first-class enum fields — SKUEL's two fundamental customization dials.**

```python
# Priority — on UserOwnedEntity (all Activity domains + Submissions + LifePath)
class Priority(str, Enum):
    LOW      = "low"       # to_numeric() → 1, get_color() → green
    MEDIUM   = "medium"    # → 2, blue
    HIGH     = "high"      # → 3, amber
    CRITICAL = "critical"  # → 4, red  ← surfaces to top of daily plan

# Confidence — on Curriculum (KU, LS, LP) + ALL lateral relationship edges
class Confidence(str, Enum):
    UNCERTAIN = "uncertain"  # → 0.3, red    (exploratory, speculative)
    LOW       = "low"        # → 0.5, amber
    MEDIUM    = "medium"     # → 0.7, blue   (working assumption)
    HIGH      = "high"       # → 0.9, green
    CERTAIN   = "certain"    # → 1.0, purple (foundational)
```

Both enums live in `core/models/enums/activity_enums.py`.

**Priority placement:** `UserOwnedEntity.priority: str | None` — present on all 8 models in the
UserOwnedEntity hierarchy (Tasks, Goals, Habits, Events, Choices, Principles, Submissions, LifePath).

**Confidence placement (two slots):**
- Entity: `Curriculum.confidence: str | None` — present on KU, LS, LP (and their request models)
- Edge: `rel.confidence: float` — property on all lateral relationship edges across all 9 domains

---

## Why Two Dials, Not One

Priority and Confidence are **orthogonal dimensions** — any combination is valid and carries
distinct meaning:

| Priority | Confidence | Meaning |
|----------|------------|---------|
| CRITICAL | CERTAIN    | Execute now. Important AND well-founded. |
| CRITICAL | UNCERTAIN  | Investigate first. Important but uncertain. |
| LOW      | CERTAIN    | Reliable background. Not urgent. |
| LOW      | UNCERTAIN  | Prune or validate. Low signal. |

Collapsing them into a single "importance" scalar would lose the epistemic dimension entirely.
A task can be CRITICAL (must happen today) while UNCERTAIN (you're not sure the approach is right).
A KU can be CERTAIN (foundational, proven knowledge) while LOW priority for a specific learner.

---

## Why Enum, Not Float

Named levels are **actionable for users**. "HIGH" is a decision — a user can make it. "0.87" is not.

Internally, `to_numeric()` / `from_numeric()` preserve full sortability for Cypher queries and
vis.js edge styling. The enum is the interface; the float is the implementation detail.

---

## Why Confidence on Curriculum + Edges, Not Activity Domains

Activity domains already have the **Dual-Track Assessment system** (ADR-030) for self-assessment:
ProductivityLevel, ProgressLevel, ConsistencyLevel, EngagementLevel, DecisionQualityLevel.
These measure "how am I doing?" — not epistemic certainty.

Adding Confidence to Activity domains would:
- Duplicate the self-assessment signal already captured by Dual-Track
- Clutter the user interface with a second uncertainty dial
- Create ambiguity between "I'm uncertain I'll do this" vs. "I'm uncertain this is the right approach"

**Curriculum content benefits from admin-assessed certainty** — a KU marked CERTAIN is foundational
knowledge with strong pedagogical confidence. UNCERTAIN KU is speculative or under review.

**Lateral edges benefit from confidence as assertion strength** — the strength of "Task A BLOCKS Task B"
varies. Some blocks are CERTAIN (hard dependency), others UNCERTAIN (soft dependency, maybe).
This applies uniformly regardless of which domain the entities belong to.

---

## Consequences

### Positive Consequences
- ✅ Planning layer responds to Priority: CRITICAL items override the top of `DailyWorkPlan`
- ✅ Graph visualization expresses relationship certainty via vis.js edge styling (solid/dashed/dotted)
- ✅ Admin-curated curriculum carries explicit epistemic confidence — search and ZPD can rank by it
- ✅ Named levels are user-friendly and actionable (no raw floats in the UI)
- ✅ `to_numeric()` / `from_numeric()` bridge user-facing labels to sortable Cypher query parameters

### Negative Consequences
- ⚠️ `None` is valid for both fields — neither is required. Intelligence services must handle absence gracefully.
- ⚠️ Confidence on edges is stored as float, not as the enum string. `Confidence.from_numeric()` bridges the gap, but callers must know which representation to use.

### Neutral Consequences
- ℹ️ Confidence enum docstring mentions `UserOwnedEntity.confidence` as a planned use case.
  As of 2026-03-05, Confidence is only on `Curriculum` entities and lateral edges — not UserOwnedEntity.
  Activity domains use Dual-Track Assessment for self-assessment instead.

---

## Implementation Details

### Code Location

- Primary enums: `core/models/enums/activity_enums.py` — `Priority` and `Confidence` classes
- Priority field: `core/models/user_owned_entity.py` — `priority: str | None = None`
- Confidence field: `core/models/curriculum.py` — `confidence: str | None = None`
- Confidence request models: `core/models/article/article_request.py`, `core/models/pathways/pathways_request.py`
- Planning integration: `core/services/user/intelligence/daily_planning.py` — "CRITICAL PRIORITY OVERRIDE" block
- Graph visualization: `core/services/lateral_relationships/lateral_relationship_service.py` — returns `confidence` + `priority` on each edge
- Vis.js edge styling: `static/js/skuel.js` — `renderNetwork()` function

### Testing Strategy

- [x] Unit tests: `Priority` and `Confidence` enum methods tested in `tests/unit/test_activity_enums.py`
- [x] Integration: Planning service tests verify CRITICAL items surface correctly
- [x] Graph visualization: vis.js edge styling verified in browser

---

## Extension Points

Future capabilities enabled by these dials:

| Extension | Description | Trigger |
|-----------|-------------|---------|
| Confidence-weighted search | High-confidence KU ranks higher in results | When search quality becomes the bottleneck |
| Uncertainty review queue | Admin dashboard for UNCERTAIN curriculum items | When curriculum grows >500 KUs |
| Priority-filtered notifications | Push only CRITICAL items | When notification system is built |
| Confidence decay | Certainty degrades over time without reinforcement | When longitudinal knowledge tracking is needed |
| Cross-domain propagation | If prerequisite KU is UNCERTAIN, dependent LS confidence drops | When ZPD service is in production |

---

## Documentation & Communication

### Related Documentation
- Architecture: `/docs/architecture/PRIORITY_CONFIDENCE_ARCHITECTURE.md` — canonical reference
- Enum catalog: `/docs/architecture/ENUM_ARCHITECTURE.md` — "Customization Dials" section

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2026-03-05 | SKUEL | Initial implementation + ADR | 1.0 |
