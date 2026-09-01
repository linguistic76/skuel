---
updated: 2026-06-21
---

# Activity Domain Inference Migration

**Status:** Tasks complete (ADR-065, PR #101 merged `4b082db4` 2026-05-28). Goals, Habits, Events, Choices, Principles pending — **blocked on product demand, not on engineering readiness** (see [Blockage status](#blockage-status-verified-2026-05-31)).
**Pattern owner:** [ADR-065 — Functional Inference Contract](../decisions/ADR-065-functional-inference-contract.md).
**Doctrine pointer:** [Three-Tier Type System § Intelligence is the Exception](../patterns/three_tier_type_system.md).

## Context

ADR-065 closed ADR-035's deferred "intelligence services would operate on mutable DTOs (risky)" risk flag by adopting a **functional inference contract**: inference services return typed `*InferenceResult` frozen dataclasses; callers apply enrichment via `dataclasses.replace(entity, **result.as_kwargs())`. No in-place DTO mutation inside intelligence services.

Tasks is the implemented template. The other five Activity Domains do not have inference services today — when they gain one, they will adopt the Tasks pattern. This roadmap captures what that adoption looks like so the work does not have to re-derive the contract per domain.

## Blockage status (verified 2026-05-31)

A functional-direction review (see [`functional-direction.md` § implementation status snapshot](functional-direction.md#implementation-status-snapshot-2026-05-31)) asked whether this migration could be pressed ahead. **It cannot be started usefully yet, and the blockage is product demand — not missing engineering.** The state below was confirmed empirically against the codebase:

- **The 5 non-Task domains have no inference service at all.** Their `_core_intelligence_mixin` files are thin stubs (Goals/Habits) or do unrelated analytics (Events `analyze_event_performance`, Choices `get_decision_intelligence`) — zero `EntityInferenceService` injection, zero inference calls. Verified across `core/services/{goals,habits,events,choices,principles}/`.
- **An `*InferenceResult` is the return type of a computation that does not exist.** Adding `GoalInferenceResult` etc. now would create the output shape of a service nobody has built, for demand nobody has expressed — speculative scaffolding, which SKUEL's One Path Forward philosophy forbids. The dataclass arrives *with* the inference service, not ahead of it.
- **The engine-generalization prerequisite must also wait.** `EntityInferenceService` still hardcodes `TaskInferenceResult` (the `entity_type` param is logging-only; the result-construction path is wired to `TaskInferenceResult`). The "Cross-cutting prerequisite" section below says to generalize it "before the second domain migrates" — doing it now would generalize a one-implementation dispatch with no second caller, which is premature abstraction (YAGNI). It is the *first step of the next domain's migration*, not standalone prep to do speculatively.

**Trigger to unblock:** a concrete product decision that a specific domain (Goals is the recommended first per the sequence below) needs knowledge-graph inference. At that point, start with the engine generalization, then that domain. Until then, this doc is a captured plan, not active work.

## Domain status

| Domain | Inference service today | `*InferenceResult` | `ku_inference_service` wired | `_core_intelligence_mixin` |
|--------|-------------------------|--------------------|-----------------------------|----------------------------|
| Tasks | ✅ `EntityInferenceService` (engine merged; was `EntityInferenceService` + `AdvancedInferenceEngine`) | ✅ `TaskInferenceResult` | ✅ injected | mech-B `get_with_context` (shared mixin; the domain-named alias was deleted in the tasks bloat campaign); cross-domain context now via the CANONICAL typed reader (`get_cross_domain_context_typed`), not a bespoke categorizer |
| Goals | ❌ | ❌ | ❌ | stub (~35 LOC, delegates to shared base) |
| Habits | ❌ | ❌ | ❌ | stub |
| Events | ❌ | ❌ | ❌ | stub |
| Choices | ❌ | ❌ | ❌ | stub |
| Principles | ❌ | ❌ | ❌ | stub |

## The pattern (per domain)

For each non-Task Activity Domain `X` to reach inference parity:

1. **Define `core/models/x/x_inference_result.py::XInferenceResult`** as a frozen dataclass with enrichment fields. The three knowledge-graph fields (`knowledge_confidence_scores`, `knowledge_inference_metadata`, `learning_opportunities_count`) are domain-general and apply to any Activity Domain that touches the KU graph. Domain-specific enrichment fields are TBD per domain — confirm against real use cases, do not pre-commit them in this roadmap.
2. **Re-export from `core/models/x/__init__.py`** (mirror `task/__init__.py`).
3. **Inject `ku_inference_service: EntityInferenceService` into `XCoreService.__init__`** and wire from `services_bootstrap/compose.py`. Cross-reference Tasks' wiring as the canonical example.
4. **Call inference from `create_x` / `update_x`** and apply via `dataclasses.replace(x_draft, **result.value.as_kwargs())`. The canonical caller pattern is `core/services/tasks/tasks_core_service.py::create_task` (post-ADR-065).
5. **Surface domain-specific cross-domain context** via the CANONICAL typed reader (`get_cross_domain_context_typed` → a path-aware `*CrossContext` with a `from_categorized` seam in `core/models/graph/path_aware_types.py`), consumed through `BaseAnalyticsService._analyze_entity_with_typed_context`. Reference: any migrated domain's `_core_intelligence_mixin.py` / `get_domain_insights` (Tasks, Events, Goals, etc.). The former bespoke `categorize_cross_domain_context()` mixin pattern is retired.

## Cross-cutting prerequisite — generalize the engine

`EntityInferenceService` (`core/services/entity_inference_service.py`) is currently Task-shaped at its construction boundary — `_analyze_content_advanced` reads `title` + `description` (already generic), but the result-construction path in `_enhance_with_advanced_inference` is wired to `TaskInferenceResult`. Before the second domain migrates, the service needs to dispatch on `EntityType` (or accept a result-type parameter) so it can build `GoalInferenceResult`, `HabitInferenceResult`, etc.

Note: `AdvancedInferenceEngine` was a separate class in `advanced_inference_engine.py`; it was merged directly into `EntityInferenceService` as private methods. The generalization prerequisite is now a single boundary in `EntityInferenceService`, not two separate files.

Estimated scope: ~50–100 LOC of generalization in a single PR, behavior-preserving for Tasks. This is the natural first step — once landed, each domain's adoption becomes mostly mechanical. **Do not do it speculatively:** it is the first step *of* the second domain's migration, not standalone prep (see [Blockage status](#blockage-status-verified-2026-05-31)). Generalizing a one-implementation dispatch with no second caller is premature abstraction.

## Recommended sequence

1. **Generalize `EntityInferenceService`** to be entity-type-aware (the engine is now merged into it). Single PR, no domain behavior changes. Prerequisite for every domain that follows.
2. **Goals second.** Closest in shape to Tasks — same template UI, same engagement flow, same activity model. Lowest-risk validation that the generalized pattern actually composes at a second domain before scaling.
3. **Habits, Events, Choices, Principles** in any order once #1 + #2 land. Each is largely independent.

This sequence is a recommendation, not a constraint. Sequencing decisions should be revisited if product priority surfaces a different domain first.

## What stays deferred

**Validation feedback as a feature.** Per ADR-065 sub-decision #2a, the dormant `_validation_feedback` machinery (instance-state defaultdict + `add_validation_feedback` + `validate_inference_batch` + the feedback-boost branch in `calculate_advanced_confidence_score`) was deleted from `AdvancedInferenceEngine`. Zero callers existed; no roadmap commitment.

When validation feedback becomes a real product feature, it must be designed in its own ADR against:
- Real callers (who fires `add_feedback`, when, with what signal),
- The completed 6-domain inference migration (cross-domain shape decided up front, not retrofitted),
- An explicit persistence-substrate decision (Neo4j-native relationship vs. separate store vs. in-memory-with-decay).

**Do NOT re-add `_validation_feedback` as instance state during the migration work above.** That decision was made deliberately; if the feature returns, it returns with a designed contract, not as resurrected dormant scaffolding.

## What this roadmap does NOT cover

This doc is scoped to the **inference contract migration** specifically — the work ADR-065 sets up for the 5 non-Task domains. The broader "Tasks is the lead Activity Domain; other domains migrate to it" picture includes more than inference (deeper `_core_intelligence_mixin` logic, knowledge-graph integration depth, bidirectional progress-impact fields, etc.) and would warrant its own roadmap doc when there is product pressure to scale that work.

## References

- [ADR-065 — Functional Inference Contract](../decisions/ADR-065-functional-inference-contract.md) — the pattern owner.
- [ADR-035 — Tier Selection Guidelines](../decisions/ADR-035-tier-selection-guidelines.md) — the original deferred risk flag, now closed.
- [Three-Tier Type System](../patterns/three_tier_type_system.md) — § "Intelligence is the Exception" documents the doctrinal carve-out.
- `core/models/task/task_inference_result.py` — the type template to mirror per domain.
- `core/services/tasks/tasks_core_service.py::create_task` — the canonical caller pattern.
- `core/services/tasks/_core_intelligence_mixin.py` — the mixin depth to mirror per domain.
