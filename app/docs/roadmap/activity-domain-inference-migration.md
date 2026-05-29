# Activity Domain Inference Migration

**Status:** Tasks complete (ADR-065, PR #101 merged `4b082db4` 2026-05-28). Goals, Habits, Events, Choices, Principles pending.
**Pattern owner:** [ADR-065 — Functional Inference Contract](../decisions/ADR-065-functional-inference-contract.md).
**Doctrine pointer:** [Three-Tier Type System § Intelligence is the Exception](../patterns/three_tier_type_system.md).

## Context

ADR-065 closed ADR-035's deferred "intelligence services would operate on mutable DTOs (risky)" risk flag by adopting a **functional inference contract**: inference services return typed `*InferenceResult` frozen dataclasses; callers apply enrichment via `dataclasses.replace(entity, **result.as_kwargs())`. No in-place DTO mutation inside intelligence services.

Tasks is the implemented template. The other five Activity Domains do not have inference services today — when they gain one, they will adopt the Tasks pattern. This roadmap captures what that adoption looks like so the work does not have to re-derive the contract per domain.

## Domain status

| Domain | Inference service today | `*InferenceResult` | `ku_inference_service` wired | `_core_intelligence_mixin` |
|--------|-------------------------|--------------------|-----------------------------|----------------------------|
| Tasks | ✅ `EntityInferenceService` + `AdvancedInferenceEngine` | ✅ `TaskInferenceResult` | ✅ injected | ✅ ~80 LOC with `categorize_cross_domain_context()` |
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
5. **Deepen `_core_intelligence_mixin`** from the current shared-stub call into domain-specific `categorize_cross_domain_context()` logic. Reference: `core/services/tasks/_core_intelligence_mixin.py`.

## Cross-cutting prerequisite — generalize the engine

`AdvancedInferenceEngine` (`core/services/advanced_inference_engine.py`) is currently Task-shaped at its construction boundary — `analyze_content_advanced` reads `title` + `description` (already generic), but the result-construction path is wired to `TaskInferenceResult`. Before the second domain migrates, the engine needs to dispatch on `EntityType` (or accept a result-type parameter) so it can build `GoalInferenceResult`, `HabitInferenceResult`, etc.

Estimated scope: ~50–100 LOC of generalization in a single PR, behavior-preserving for Tasks. This is the natural first step — once landed, each domain's adoption becomes mostly mechanical.

`EntityInferenceService` (`core/services/entity_inference_service.py`) needs the same generalization at the `enhance_*_with_knowledge_inference` boundary.

## Recommended sequence

1. **Generalize `AdvancedInferenceEngine` + `EntityInferenceService`** to be entity-type-aware. Single PR, no domain behavior changes. Prerequisite for every domain that follows.
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
