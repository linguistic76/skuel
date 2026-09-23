---
updated: 2026-09-23
---

# KuIntelligenceService - Usage, Organization & Per-User Substance

## Overview

**Architecture:** Extends `_CoreIntelligenceMixin[Ku]` + `BaseAnalyticsService[BackendOperations[Ku], Ku]` — graph queries and Python only, no AI dependencies
**Location:** `/core/services/ku/ku_intelligence_service.py`
**Service Name:** `ku.intelligence`
**Facade slot:** `KuService.intelligence` (`/core/services/ku_service.py`)

PathStep-grain intelligence (readiness, practice, guidance, PathStep substance) is a separate service — see [PS_INTELLIGENCE.md](PS_INTELLIGENCE.md).

---

## Purpose

A Ku is an atomic, shared knowledge unit. KuIntelligenceService answers three questions about one:

1. **How is it used by the curriculum?** — how many PathSteps compose it (`USES_KU`) or train it (`TRAINS_KU`), and how deep an `ORGANIZES` tree sits below it.
2. **How much has this learner lived it?** — the per-(user, Ku) substance score, from the learner's activity→Ku channels in `UserContext`.
3. **Does the learner's self-rating match that evidence?** — the Knowledge dual-track dimension (ADR-030).

---

## Methods

### Route-factory surface

`get_with_context(uid, depth=2)` (inherited from `_CoreIntelligenceMixin[Ku]`), `get_performance_analytics(user_uid, period_days=30)` and `get_domain_insights(uid, min_confidence=0.7)` implement the three-method `IntelligenceRouteFactory` surface. **KU has no routes for them:** `KU_CONFIG` wires no `IntelligenceRouteConfig` (see [INTELLIGENCE_SERVICES_INDEX.md](INTELLIGENCE_SERVICES_INDEX.md) § Route Factory Protocol).

- `get_performance_analytics` returns corpus-level counts, not per-user data (Kus are shared content): `total_kus` and `by_nous` (Ku count per NOUS topic; a Ku with no topic counts under `"unassigned"`). `user_uid` and `period_days` are echoed back, not filtered on.
- `get_domain_insights` returns the Ku's title, alias count, `get_usage_summary()` result and `get_organization_depth()`.

### get_usage_summary(ku_uid) → `Result[dict[str, int]]`

Counts `path_steps_using` (`USES_KU`), `path_steps_training` (`TRAINS_KU`) and `organized_children` (`ORGANIZES`). Backend: `KuBackend.get_usage_summary`. Delegated by `KuService.get_usage_summary`.

### get_organization_depth(ku_uid) → `Result[int]`

Depth of the `ORGANIZES` tree below the Ku; 0 when it organizes nothing. Backend: `KuBackend.get_organization_depth`.

### is_trained(ku_uid) / is_organized(ku_uid) → `Result[bool]`

Existence checks: does any PathStep train this Ku; does it have `ORGANIZES` children (i.e. act as a MOC).

### calculate_user_substance(ku_uid, user_context) → `Result[KuUserSubstanceResult]`

How much this learner has applied the Ku in their life. **Requires a rich context** (`UserContextBuilder.build_rich`) — the standard build leaves the channel maps empty, and an empty map scores a confident 0.0, indistinguishable from a learner who applied nothing.

The six channels, their `UserContext` fields and their weights live in one table, `USER_SUBSTANCE_CHANNELS` (`/core/services/knowledge/user_substance.py`); this service owns the presentation, not the arithmetic:

| Channel | `UserContext` field | Weight / instance | Cap |
|---------|---------------------|-------------------|-----|
| tasks | `task_knowledge_applied` | 0.05 | 0.25 |
| habits | `habit_knowledge_applied` | 0.10 | 0.30 |
| events | `event_knowledge_applied` | 0.05 | 0.25 |
| entries | `entry_knowledge_applied` | 0.07 | 0.20 |
| choices | `choice_knowledge_informed` | 0.07 | 0.15 |
| principles | `principle_knowledge_grounded` | 0.07 | 0.15 |

The total is capped at 1.0. The result (`KuUserSubstanceResult`, `/core/ports/query_types.py`):

| Key | Meaning |
|-----|---------|
| `user_substance_score` | Per-user score, 0.0–1.0 |
| `global_substance_score` | The Ku node's own substance score, or `None` |
| `breakdown` | Per-channel contribution |
| `mastery_level` | `mastered` (≥ 0.8) / `in_progress` (≥ 0.5) / `started` (> 0) / `unstarted`, from `user_context.knowledge_mastery` |
| `is_ready_to_learn` | `user_substance_score >= 0.05` |
| `recommendations` | Up to 3 prompts for channels the learner has not used yet |
| `status_message` | One line by score band (≥ 0.7, ≥ 0.4, ≥ 0.1, below) |

### assess_mastery_dual_track(user_uid, ku_uid, user_level, user_evidence, user_context, user_reflection=None, store_callback=None) → `Result[DualTrackResult[MasteryLevel]]`

The Knowledge dual-track dimension (ADR-030): compares the learner's self-rated `MasteryLevel` with the system side, `MasteryLevel.from_score(user_substance_score)`, and reports the perception gap. A Ku is shared, so the check-in is per-(user, Ku): `store_callback` persists it on the user (`UserService.append_knowledge_checkin`), never on the `:Ku` node.

**Consumer:** `POST /explore/ku/{uid}/mastery-checkin` (`adapters/inbound/learning_loop_routes.py`) → `ExploreOrchestrator.assess_ku_mastery` → `KuService.assess_mastery_dual_track`.

---

## Construction

`KuService.__init__` builds it through `create_curriculum_sub_services()`; the facade has four sub-services — `core`, `search`, `relationships`, `intelligence`.

```python
from core.services.ku.ku_intelligence_service import KuIntelligenceService

service = KuIntelligenceService(backend=ku_backend, graph_intel=graph_intelligence)
assert service._service_name == "ku.intelligence"
```

Constructor: `backend` (required), `graph_intel`, `relationship_service`, `event_bus` (all optional).

**Tests:** `tests/unit/services/ku/test_ku_intelligence_service.py`.

---

## See Also

- [INTELLIGENCE_SERVICES_INDEX.md](INTELLIGENCE_SERVICES_INDEX.md) - Master index
- [PS_INTELLIGENCE.md](PS_INTELLIGENCE.md) - PathStep intelligence
- [MOC_INTELLIGENCE.md](MOC_INTELLIGENCE.md) - A Ku that organizes others is analyzed as a Ku
- `/docs/architecture/knowledge_substance_philosophy.md` - Knowledge substance tracking
- `/core/services/knowledge/user_substance.py` - The per-user substance weight table
- `/core/services/ku_service.py` - KuService facade
