---
title: Sibling Signal Pattern
updated: 2026-05-22
status: proposed
category: patterns
tags: [patterns, activity-domains, intelligence, protocols, design]
related:
  - ADR-057-activity-domain-sibling-signals
  - patterns/SHARED_SIGNAL_PATTERN
  - patterns/BACKEND_OPERATIONS_ISP
  - patterns/protocol_architecture
---

# Sibling Signal Pattern

> **Status:** Proposed shape. No code has been written yet. This doc specifies *how* implementation should look when it proceeds. The "why" lives in [ADR-057](../decisions/ADR-057-activity-domain-sibling-signals.md).

**Core Principle:** *Each Activity Domain judges its own metric, but consults siblings for blind-spot correction.*

The 6 Activity Domains — Tasks, Goals, Habits, Events, Choices, Principles — already share a graph of cross-domain relationships. But each domain's `.intelligence` sub-service still computes its metrics in isolation. A Sibling Signal is a narrow, ISP-shaped protocol that exposes one corrective signal from one domain's intelligence to be consumed by another domain's intelligence method at the point of judgment.

See [@activity-domains](../../.claude/skills/activity-domains/SKILL.md) § "Harmony Without Over-Generalization" for the shared-shape philosophy that makes this possible.

## The Six Ways of Acting

| Domain | Verb | Distinctive strength |
|--------|------|----------------------|
| Tasks | **Execute** | Atomic, scheduled, prerequisite-aware work |
| Goals | **Aspire** | Directional, measurable outcomes |
| Habits | **Repeat** | Daily-calibrated loops with streaks |
| Events | **Occur** | Point-in-time commitments; the only domain materializing recurrence as discrete instances |
| Choices | **Decide** | Bounded-option forks that record regret |
| Principles | **Bind** | Values as gravity wells |

This is the canonical home for this framing. Docs that need to refer to "what each domain does" link here.

## The Three Primary Axes (Mutual Sharpening)

Each axis pairs two domains that address the same phenomenon from complementary angles. Within an axis, sharpening flows both ways.

### Axis 1 — Behavioral (Habits ↔ Goals)

*Repetition ↔ Direction.*

- **Habits → Goals**: Habit consistency trend corrects goal success prediction. A goal whose supporting habit dropped 40% consistency last week has a stale success figure.
- **Goals → Habits**: Goal purpose corrects habit drift. A 60%-consistent habit that reinforces *no active goal* is drift; the same habit reinforcing 3 active goals is leverage.

### Axis 2 — Ethical (Choices ↔ Principles)

*Decision ↔ Value.*

- **Principles → Choices**: Principle alignment corrects choice impact ranking. A "high-impact" choice may violate a core principle; impact-only ranking misses that.
- **Choices → Principles**: Choice adherence evidence corrects principle strength. A principle with no choices honoring it is rhetoric, not value.

### Axis 3 — Temporal (Tasks ↔ Events)

*Work ↔ Time.*

- **Events → Tasks**: Calendar collision corrects task capacity assumption. Priority means nothing if the calendar has already sold the block.
- **Tasks → Events**: Task throughput corrects event scheduling realism. An event in a window with 8 overdue tasks is a lie to yourself.

## The Seven Diagonals (Directed)

Not every useful signal flows both ways. These seven are asymmetric — one domain meaningfully sharpens another without a strong return channel today.

| Signal | From | To | Graph edge |
|--------|------|-----|------------|
| Values anchor direction | Principles | Goals | `GUIDED_BY_PRINCIPLE` |
| Behavior expresses value | Habits | Principles | `EMBODIES_PRINCIPLE` |
| Moments force decisions | Events | Choices | `TRIGGERS_CHOICE` |
| Work advances aspiration | Tasks | Goals | `CONTRIBUTES_TO_GOAL` |
| Aspiration directs work | Goals | Tasks | reverse of `CONTRIBUTES_TO_GOAL` |
| Values anchor execution | Principles | Tasks | `GUIDED_BY_PRINCIPLE` |
| Aspiration flags time commitment | Goals | Events | reverse of `ADVANCES_GOAL` |

## Protocol Shape

Each Sibling Signal is a narrow `Protocol` in a single grouped file. Keep the protocol tight — one or two methods, scoped to the signal, not the producing domain's full intelligence surface.

**Proposed location** (not yet created): `core/ports/sibling_signals.py`

```python
# core/ports/sibling_signals.py
from typing import Protocol

from core.models.type_hints import Neo4jProperties


class HabitConsistencySignal(Protocol):
    """Consistency-trend signal exposed by HabitsIntelligenceService.

    Consumed at judgment time by sibling intelligence methods that need
    to correct for declining behavioral support (e.g. goal success
    prediction, principle embodiment scoring).
    """

    async def get_consistency_trend(
        self,
        habit_uid: str,
        window_days: int = 14,
    ) -> TrendResult: ...


class PrincipleAlignmentSignal(Protocol):
    """Alignment signal exposed by PrinciplesIntelligenceService."""

    async def score_alignment(
        self,
        entity_uid: str,
    ) -> AlignmentScore: ...


class GoalFeasibilitySignal(Protocol):
    """Success-probability + risk signal exposed by GoalsIntelligenceService."""

    async def assess_feasibility(
        self,
        goal_uid: str,
    ) -> FeasibilityScore: ...


# … one protocol per signal in the 3 axes + 7 diagonals.
```

**Naming rule:** `{SourceConcept}{Signal}` — `HabitConsistencySignal`, not `HabitsSiblingSignal`. The name identifies the *carried information*, not the producing service.

## Consumption Shape

The consumer is an intelligence method *inside a sibling domain's intelligence service*. It takes the signal as a constructor dependency (protocol, not concrete service) and consults it when computing its judgment.

```python
# ILLUSTRATIVE — in goals/_predictive_mixin.py (not yet implemented)

class _PredictiveMixin:
    _habit_signal: HabitConsistencySignal  # injected via __init__

    async def predict_goal_success(
        self, goal_uid: str
    ) -> GoalPrediction:
        base = await self._compute_base_prediction(goal_uid)

        # Consult sibling signals at judgment time
        supporting_habits = await self._get_supporting_habit_uids(goal_uid)
        trend_adjustments = [
            await self._habit_signal.get_consistency_trend(h)
            for h in supporting_habits
        ]

        return base.adjust_for_trends(trend_adjustments)
```

**Consumption rules:**

1. **Constructor injection.** The sibling signal is a `__init__` parameter typed as the `Protocol`. Never reach across to another facade or sub-service at call time.
2. **Consult, don't aggregate.** A sibling signal contributes to a judgment; it does not replace the consumer's own metric. If you find yourself returning the signal verbatim, you are doing aggregation — that belongs in `UserContextIntelligence`, not here.
3. **Idempotent queries.** Signal methods are read-only and do not mutate state. No event publishes, no counters incremented, no cached writes.
4. **Narrow result types.** Signal methods return specific TypedDicts or frozen dataclasses (`TrendResult`, `AlignmentScore`, `FeasibilityScore`), never `Result[Any]`. See `/docs/patterns/RETURN_TYPE_ERROR_PROPAGATION.md`.

## Placement Rule

All **peer-to-peer** sibling-signal protocols live in **one file**: `core/ports/sibling_signals.py`. This mirrors how `core/ports/domain_protocols.py` groups ISP slices. Single file keeps the edge↔signal mapping table (below) colocated with the contracts themselves.

Implementations live on the *existing* intelligence services — no new sub-service is created. `HabitsIntelligenceService` implements `HabitConsistencySignal` by having a `get_consistency_trend()` method; structural typing does the rest.

Cross-cutting signals (where the producer is infrastructure serving all 6 domains — Knowledge, Calendar, user-capacity) do **not** live here. Those belong in `core/ports/intelligence_protocols.py` alongside `KnowledgeIntelligenceOperations`. See [Shared Signal Pattern](SHARED_SIGNAL_PATTERN.md) for that placement.

## Edge ↔ Signal Mapping

Each sibling signal rides on a Neo4j relationship that already exists. Keep this table in sync when either side changes.

| Signal | Neo4j edge(s) | Direction in graph |
|--------|---------------|--------------------|
| `HabitConsistencySignal` | `(Habit)-[:SUPPORTS_GOAL]->(Goal)` | Habits are located by goal |
| `PrincipleAlignmentSignal` | `(Choice)-[:INFORMED_BY_PRINCIPLE]->(Principle)`, `(Task)-[:GUIDED_BY_PRINCIPLE]->(Principle)` | Principles are located by consumer entity |
| `GoalFeasibilitySignal` | `(Task)-[:CONTRIBUTES_TO_GOAL]->(Goal)`, `(Event)-[:ADVANCES_GOAL]->(Goal)` | Goals are located by supporting activity |
| `EventCollisionSignal` | `(Event)-[:OCCURS_AT]->(TimeSlot)` or direct `event_date` property | Events are located by calendar window |
| `ChoiceAdherenceSignal` | `(Choice)-[:INFORMED_BY_PRINCIPLE]->(Principle)` | Historical adherence count per principle |
| `HabitEmbodimentSignal` | `(Habit)-[:EMBODIES_PRINCIPLE]->(Principle)` | Habits embodying a principle |
| `EventDecisionTriggerSignal` | `(Event)-[:TRIGGERS_CHOICE]->(Choice)` | Upcoming events triggering choices |

Every row maps to exactly one graph edge (or a small set of semantically-equivalent edges). If you find yourself wanting to add a user-scoped aggregate row (e.g. task throughput, user capacity, knowledge mastery), the producer is infrastructure, not a peer domain — that belongs in the [Shared Signal Pattern](SHARED_SIGNAL_PATTERN.md) mapping instead.

## Precedent to Imitate

The consumption shape — narrow protocol + delegation mixin + constructor injection — is borrowed from the shared [ActivityKnowledgeIntelligenceService](../../core/services/knowledge/activity_knowledge_intelligence_service.py) + [KnowledgeIntelligenceMixin](../../core/services/mixins/knowledge_intelligence_mixin.py), already in production.

**Important:** that service is the first realization of the sibling [Shared Signal](SHARED_SIGNAL_PATTERN.md), not this Sibling Signal pattern. Shared Signal is the right home for cross-cutting infrastructure → every-peer consultation. Sibling Signal takes the same delegation machinery and applies it *peer-to-peer* — many narrow concerns (consistency, alignment, feasibility, …), each typed as its own protocol, each implemented on the producing Activity Domain's intelligence service rather than a shared singleton.

## What This Pattern Is *Not*

- **Not a cross-cutting infrastructure service.** Those live in [Shared Signal Pattern](SHARED_SIGNAL_PATTERN.md). If the producer is infrastructure serving all 6 domains (Knowledge, Calendar, user-capacity), use Shared Signal instead. Rule of thumb: if the signal is user-scoped (aggregate across all of a user's entities) rather than entity-scoped (a single peer entity's metric), the producer is infrastructure, not a peer.
- **Not a replacement for `UserContextIntelligence`.** Aggregate life-path scoring, synergy detection, and daily-planning synthesis stay where they are. Sibling signals are for *per-entity* judgment, not whole-user aggregation.
- **Not an event-bus mechanism.** Signals are consulted synchronously at query time. If you need to *react* to a state change (e.g. send a notification when a habit streak breaks), use the existing event bus (`core/events/`).
- **Not a cross-domain facade.** Each domain's facade stays the way it is. No `CrossDomainIntelligenceService` appears. The sibling signal is injected directly into the mixin or method that needs it.
- **Not a lateral relationship type.** The 6 lateral types (`BLOCKS`, `PREREQUISITE_FOR`, `ALTERNATIVE_TO`, `COMPLEMENTARY_TO`, `SIBLING`, `RELATED_TO`) are user-authored edges. Sibling signals ride on *architectural* cross-domain edges (`SUPPORTS_GOAL`, `EMBODIES_PRINCIPLE`, etc.).

## Testing Shape

Each protocol gets a focused unit test with a fake implementation. For each consumer intelligence method that consults a sibling signal, one integration test demonstrates the "before/after" sharpening:

```python
# ILLUSTRATIVE
async def test_goal_success_downgrades_on_habit_consistency_drop():
    # Given a goal supported by a habit
    goal_uid, habit_uid = await _seed_goal_with_supporting_habit()

    # Baseline prediction (healthy habit)
    baseline = await goals_intel.predict_goal_success(goal_uid)

    # When the habit's consistency drops 40%
    await _record_habit_misses(habit_uid, days=5)

    # The goal prediction reflects the drop
    updated = await goals_intel.predict_goal_success(goal_uid)
    assert updated.probability < baseline.probability
```

## Implementation Checklist (When Proceeding)

1. Create `core/ports/sibling_signals.py` with one Protocol per signal.
2. Create the supporting result types (`TrendResult`, `AlignmentScore`, etc.) — either alongside the protocols or in `core/ports/query_types.py` if they are reused.
3. For each target intelligence mixin: add the signal as an `__init__` parameter typed as the Protocol, and consult it at the judgment site.
4. Wire the signal implementations in `services_bootstrap/compose.py` — the producing intelligence service is passed as the sibling-signal parameter; structural typing does the rest.
5. Add integration tests for each wired axis (see Testing Shape above).
6. Update the Edge ↔ Signal mapping table in this file if the implementation surfaces any missing edges.

## Related Documentation

- **Architecture:** [ADR-057](../decisions/ADR-057-activity-domain-sibling-signals.md) — the decision record
- **Companion pattern:** [Shared Signal Pattern](SHARED_SIGNAL_PATTERN.md) — for cross-cutting infrastructure → every-peer consultation
- **Philosophy:** [@activity-domains](../../.claude/skills/activity-domains/SKILL.md) — shared-shape-with-unique-verbs
- **Protocol shape:** [Protocol Architecture](protocol_architecture.md) — how protocols are defined and consumed in SKUEL
- **ISP pattern:** [BackendOperations ISP](BACKEND_OPERATIONS_ISP.md) — precedent for narrow Protocol slices
- **Return types:** [Return Type Error Propagation](RETURN_TYPE_ERROR_PROPAGATION.md) — why signals return typed results, not `Result[Any]`
- **Precedent:** [Service Consolidation Patterns](SERVICE_CONSOLIDATION_PATTERNS.md) — how shared cross-domain intelligence services are mounted today
