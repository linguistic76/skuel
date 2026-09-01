---
title: "ADR-057: Activity-Domain Sibling Signals"
updated: 2026-09-01
status: current
category: decisions
tags: [adr, decisions, architecture, activity-domains, intelligence, design]
related:
  - ADR-047-entity-types-replace-domain-categories
  - ADR-055-architectural-lenses
  - ADR-043-intelligence-tier-toggle
  - SIBLING_SIGNAL_PATTERN
  - SHARED_SIGNAL_PATTERN
---

# ADR-057: Activity-Domain Sibling Signals

**Status:** Proposed (design only; implementation not scheduled)
**Date:** 2026-04-21
**Related:**
[ADR-047 Entity Types Replace Domain Categories](ADR-047-entity-types-replace-domain-categories.md),
[ADR-055 Architectural Lenses](ADR-055-architectural-lenses.md),
[ADR-043 Intelligence Tier Toggle](ADR-043-intelligence-tier-toggle.md)

> *"As iron sharpens iron, so one person sharpens another."* — Proverbs 27:17

## Context

SKUEL's 6 Activity Domains — **Tasks, Goals, Habits, Events, Choices, Principles** — share a common BaseService shape. That shape is the *contract for interconnectivity*: unified search, user-context aggregation, cross-domain queries, and ZPD assessment all work because every domain answers the same way. Domain-specific sub-services preserve *uniqueness inside that shape* (see `.claude/skills/activity-domains/SKILL.md` § "Harmony Without Over-Generalization").

Each of the 6 has **one irreducible verb** — a way of acting no other domain expresses:

| Domain | Verb | Distinctive strength |
|--------|------|----------------------|
| Tasks | **Execute** | Atomic, scheduled, prerequisite-aware work |
| Goals | **Aspire** | Directional, measurable outcomes |
| Habits | **Repeat** | Daily-calibrated loops with streaks |
| Events | **Occur** | Point-in-time commitments; the only domain materializing recurrence as discrete instances |
| Choices | **Decide** | Bounded-option forks that record regret |
| Principles | **Bind** | Values as gravity wells |

These verbs are not interchangeable. A goal cannot *repeat* — only a habit can. A task cannot *bind* — only a principle can. Each domain sees a dimension of reality the others cannot.

Today, the **grammar of mutual influence is largely wired in the graph** — roughly 18 cross-domain relationships connect the 6 Activity Domains (`SUPPORTS_GOAL`, `EMBODIES_PRINCIPLE`, `GUIDED_BY_PRINCIPLE`, `IMPACTS_HABIT`, `DEMONSTRATES_PRINCIPLE`, `TRIGGERS_CHOICE`, `CONTRIBUTES_TO_GOAL`, `INFORMED_BY_PRINCIPLE`, …).

But each domain's `.intelligence` sub-service still **judges in isolation**. A goal's `predict_goal_success()` weights `habit.success_rate` but misses *trend* — a habit whose consistency dropped 40% last week leaves the prediction stale. A choice's `analyze_choice_impact()` ranks impact but ignores principle alignment — a "high-impact" choice may violate core values. A task's `calculate_knowledge_aware_priorities()` ignores whether the goal it serves is at 30% success probability and declining.

Cross-domain correction today happens *only* at the `UserContextIntelligence` aggregate layer (`synergy_intelligence.py`, `life_path_intelligence.py`, `daily_planning.py`). That is the right layer for *whole-user* scores like life-path alignment. It is the *wrong* layer for *per-entity* judgments that are called from many places — those live in domain intelligence services and cannot see sideways.

The edges exist. The intelligence plumbing does not.

## Decision

Introduce a **Sibling Signal** pattern: narrow, ISP-shaped protocols in `core/ports/` that expose a *single corrective signal* from one Activity Domain's intelligence, consumed by a sibling domain's intelligence method at the point of judgment.

### Related pattern: Shared Signal

Not every cross-domain consultation is peer-to-peer. Some corrective signals are produced by **infrastructure serving all 6 Activity Domains** — `ActivityKnowledgeIntelligenceService` is the first productionized example, already delegated from every facade via `KnowledgeIntelligenceDelegationMixin`. The same shape applies to future Calendar- and user-capacity-sourced signals.

That shape is a distinct pattern — *Shared Signal* — covered separately in [`docs/patterns/SHARED_SIGNAL_PATTERN.md`](../patterns/SHARED_SIGNAL_PATTERN.md). Sibling Signal is sibling-to-sibling (Habits → Goals, Principles → Choices, …); Shared Signal is infrastructure → every-peer. The two are complementary, not competing: the 9-gap appendix below identifies which gaps fit each pattern.

The pattern has three commitments:

1. **Protocols, not service-to-service calls.** Each signal is a `Protocol`, and they would live together in one sibling-signals module under `core/ports/` (nothing is built yet — this ADR is Proposed). Consumers depend on the narrow protocol, not the producing facade. This avoids circular imports, preserves ISP, and makes testing straightforward.
2. **Consulted at judgment time, not ingestion time.** When `predict_goal_success()` runs, it consults the habit consistency signal right then — not when habits are created or updated. This keeps per-entity latency honest and avoids a combinatorial enrichment layer.
3. **Not a new service tier.** Siblings remain the same intelligence services. No new facade, no new sub-service. The protocol is the thin contract between existing services.

The 6 domains organize into **3 primary axes** (mutual sharpening — A↔B) plus **7 diagonals** (directed — A→B):

### Primary axes (mutual)

| Axis | Pair | Mutual signals |
|------|------|----------------|
| **Behavioral** | Habits ↔ Goals | Habit consistency trend sharpens goal success prediction; goal purpose sharpens habit drift detection |
| **Ethical** | Choices ↔ Principles | Principle alignment sharpens choice impact ranking; choice adherence evidence sharpens principle strength |
| **Temporal** | Tasks ↔ Events | Event calendar collision sharpens task capacity assumption; task throughput sharpens event scheduling realism |

### Diagonals (directed)

| Signal | From | To | Graph edge today |
|--------|------|-----|------------------|
| Values anchor direction | Principles | Goals | `GUIDED_BY_PRINCIPLE` |
| Behavior expresses value | Habits | Principles | `EMBODIES_PRINCIPLE` |
| Moments force decisions | Events | Choices | `TRIGGERS_CHOICE` |
| Work advances aspiration | Tasks | Goals | `CONTRIBUTES_TO_GOAL` |
| Aspiration directs work | Goals | Tasks | reverse of `CONTRIBUTES_TO_GOAL` |
| Values anchor execution | Principles | Tasks | `GUIDED_BY_PRINCIPLE` |
| Aspiration flags time commitment | Goals | Events | reverse of `ADVANCES_GOAL` |

### Vocabulary

The code-facing term is **Sibling Signal** — neutral and descriptive. The biblical framing belongs in prose (this ADR's preamble, the pattern doc's introduction), not in class names. Protocols are named for the signal they carry — e.g. `HabitConsistencySignal`, `PrincipleAlignmentSignal` — not `IronSharpensIronProtocol`.

The consumption verb is **consult** — e.g. `consult_sibling_signals()` on an intelligence method — which reads as "ask the sibling before judging," the behavior we actually want.

### Scope of this ADR

This ADR **captures the design**. It does not schedule implementation. A companion pattern doc — `docs/patterns/SIBLING_SIGNAL_PATTERN.md` — specifies the shape code should take when implementation proceeds.

No new protocols, services, or enums are introduced by this ADR. Nothing ships.

## Alternatives Considered

1. **Aggregate everything in `UserContextIntelligence`.** Push all cross-domain correction into the existing aggregate layer. Rejected — it centralizes what belongs locally, forces per-entity queries (one goal, one choice) through a whole-user path, and re-computes context every page load. UserContextIntelligence is the right layer for *holistic* scoring; sibling signals are about *per-entity* judgment.
2. **Direct service-to-service calls.** `GoalsIntelligenceService` holds a reference to `HabitsIntelligenceService`. Rejected — creates circular-dependency risk, no ISP boundary, hard to test, and couples domains at the whole-service level when only a narrow signal is needed.
3. **Event-bus-driven reactive correction.** On `habit.consistency_dropped`, enqueue an event that updates cached goal predictions. Rejected for query-time consultation — events fit state-change propagation, not *judgment-time* correction. A goal's predicted-success figure that depends on "the last time an event fired" is harder to reason about than one that consults a signal when called.
4. **Wait and see — defer the design.** Do not capture the pattern at all; implement ad-hoc cross-domain consultation inside intelligence methods as the need arises. Rejected — the 9 concrete gaps surfaced during audit will otherwise be solved inconsistently (one method fetches a sibling service directly, another goes via UserContext, a third re-queries the graph). Naming the pattern now keeps future implementation coherent, even with no code today.

## Consequences

**Positive**

- Per-entity judgments gain cross-domain context without inflating `UserContextIntelligence`.
- The graph edges that already exist (~18 cross-domain relationships) get a consistent *query-time* contract built over them. Sibling signals make the edges *functional* rather than merely recorded.
- Each Activity Domain keeps its own verb and its own metric. The pattern adds correction without diluting domain identity.
- Future decisions about *when* to wire specific signals can reference a shared name and shape. Reviewers can check that a new cross-domain intelligence touch follows the pattern rather than inventing one.

**Negative**

- Each sibling signal is one more protocol to maintain.
- Risk of drift between a graph edge (e.g. `EMBODIES_PRINCIPLE`) and the signal protocol that rides on it (e.g. `HabitEmbodimentSignal`) — they can evolve independently. Mitigation: the pattern doc's edge↔signal mapping table is the single place to keep them synchronized.
- Intelligence methods become slightly harder to read in isolation — a `predict_goal_success()` that consults sibling signals depends on more than its own sub-service. Mitigation: follow the precedent set by `KnowledgeIntelligenceDelegationMixin`, where cross-cutting intelligence is mounted explicitly and visible on the class signature.

**No code changes.** This ADR introduces no new enums, no new types, no new services. It is a documentation and vocabulary decision.

## Out of Scope

- **Implementation sequencing.** Whether to wire one axis first (e.g. Behavioral), prototype against a real gap, or roll out all 9 signals at once is deferred. The pattern doc's protocol and consumption shapes are canonical; the order of adoption is not.
- **UserContextIntelligence changes.** The aggregate layer stays as it is. Sibling signals are additive and do not replace `synergy_intelligence.py` or `life_path_intelligence.py`.
- **Cross-domain lateral relationships in visualization.** The Vis.js graph view (`LATERAL_RELATIONSHIPS_VISUALIZATION.md`) currently renders only same-domain lateral edges. Whether to render sibling-signal-backing edges is a separate UI decision, not blocked by this ADR.
- **Non-Activity domains.** Ku, PathStep, LearningPath, Exercise, and the Learning Loop entities are not in scope. The pattern is specifically about the 6 Activity Domains and their shared BaseService shape.

## Appendix — The 9 Concrete Gaps

Discovered during the Phase 1 audit. On review, the 9 gaps split across two patterns: 6 are peer-to-peer sibling signals (this ADR), 3 are cross-cutting signals produced by infrastructure serving all 6 domains ([Shared Signal pattern](../patterns/SHARED_SIGNAL_PATTERN.md)). Original row numbering is preserved so existing references still resolve.

### 9a. Sibling Gaps (6)

Peer-to-peer consultation at judgment time. Each rides a single cross-domain graph edge.

| # | Source domain | Target method | Signal |
|---|---------------|---------------|--------|
| 1 | Principles | `ChoicesIntelligenceService.analyze_choice_impact()` | alignment |
| 2 | Goals | `TasksIntelligenceService.calculate_knowledge_aware_priorities()` | goal feasibility |
| 3 | Habits | `GoalsIntelligenceService.predict_goal_success()` | consistency trend |
| 6 | Principles | `TasksIntelligenceService.generate_task_insights()` | alignment gap |
| 7 | Goals | `EventsIntelligenceService.analyze_event_performance()` | goal risk |
| 9 | Habits | `PrinciplesIntelligenceService.assess_principle_alignment()` | embodiment evidence |

See [`docs/patterns/SIBLING_SIGNAL_PATTERN.md`](../patterns/SIBLING_SIGNAL_PATTERN.md) for the protocol and consumption shapes these gaps would be implemented with.

### 9b. Cross-Cutting Gaps (3)

The producer is infrastructure — not a peer domain — and the signal is typically user-scoped rather than entity-scoped. Same consumption shape as sibling signals (narrow ISP protocol, delegation mixin, constructor injection), but the producer is a shared service every facade mounts. The [`ActivityKnowledgeIntelligenceService`](../../core/services/knowledge/activity_knowledge_intelligence_service.py) + [`KnowledgeIntelligenceDelegationMixin`](../../core/services/mixins/knowledge_intelligence_mixin.py) is the first realization.

| # | Source (infrastructure) | Target method | Signal |
|---|-------------------------|---------------|--------|
| 4 | User-capacity / throughput service (new) | `HabitsIntelligenceService.analyze_habit_performance()` | throughput / capacity |
| 5 | Calendar (cross-cutting system) | `HabitsIntelligenceService.analyze_habit_performance()` | calendar collision |
| 8 | Knowledge mastery (existing `ActivityKnowledgeIntelligenceService`) | `ChoicesIntelligenceService.get_decision_intelligence()` | mastery score |

See [`docs/patterns/SHARED_SIGNAL_PATTERN.md`](../patterns/SHARED_SIGNAL_PATTERN.md) for the shape these gaps would be implemented with.
