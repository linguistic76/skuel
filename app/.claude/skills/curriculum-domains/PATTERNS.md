# Curriculum Domain Patterns

> Implementation patterns for Ku, PathStep (PS), and LearningPath (LP) features.

---

## Pattern: Adding a Curriculum Domain Service Config

All core/search services use `_config = create_curriculum_domain_config(...)` (not bare class attributes).

```python
from core.services.domain_config import create_curriculum_domain_config

class PsCoreService(BaseService[PsOperations, PathStep]):
    _config = create_curriculum_domain_config(
        dto_class=PathStepDTO,
        model_class=PathStep,
        domain_name="path_step",
        search_fields=("title", "description", "content"),
        category_field="nous",  # NOUS topic membership (array — `has` semantics)
    )
```

**Key difference from Activity Domains:** No `user_ownership_relationship` — curriculum content is shared (`_user_ownership_relationship = None` is set automatically by `create_curriculum_domain_config`).

---

## Pattern: PathStep Organization (Non-Linear Navigation)

Any PathStep can organize other PathSteps via `ORGANIZES` relationships. There is no `MocService` — this is `PsOrganizationService` (a sub-service of `PsService`):

```python
# Create non-linear structure
await ps_service.organization.organize(
    parent_uid="ps:core:yoga-fundamentals",
    child_uid="ps:core:meditation-basics",
    order=1,
    importance="core",
)

# Navigate the structure
children = await ps_service.organization.get_organized_children("ps:core:yoga-fundamentals", depth=2)
parents = await ps_service.organization.find_organizers("ps:core:meditation-basics")
root_organizers = await ps_service.organization.list_root_organizers()

# Check if a PathStep acts as an organizer
is_org = await ps_service.organization.is_organizer("ps:core:yoga-fundamentals")

# Prev/next sibling navigation in MOC ORGANIZES order.
# Returns a StepNavigation dataclass — propagates DB errors, returns empty nav for legitimate empty states.
result = await ps_service.organization.get_navigation("ps:core:meditation-basics")
nav = result.value  # StepNavigation(prev_uid, prev_title, next_uid, next_title)
```

**When to use this pattern:** When users want to navigate knowledge non-linearly (exploring a topic map rather than following a prescribed sequence). This is the emergent MOC pattern.

**Key dataclass:** `StepNavigation` (frozen, from `core/services/ps/ps_organization_service.py`) — prev/next sibling in MOC ORGANIZES order.

---

## Pattern: PS Knowledge Relationship CRUD (Backend-Delegated)

Knowledge relationships (`USES_KU` / `TRAINS_KU`) are managed via `PsBackend` — services delegate, no inline Cypher:

```python
# Backend (PsBackend) — owns the Cypher
await backend.add_uses_ku(ps_uid, ku_uid, role="primary")
await backend.remove_uses_ku(ps_uid, ku_uid)
ku_refs = await backend.list_ku_refs(ps_uid, role="primary")
summary = await backend.get_knowledge_summary(ps_uid)  # {primary_count, supporting_count, ...}

# Service (PsCoreService) — validates + delegates
async def add_ku_reference(self, ps_uid, ku_uid, role="primary"):
    if role not in ("primary", "supporting"):
        return Result.fail(Errors.validation(...))
    return await self.backend.add_uses_ku(ps_uid, ku_uid, role)
```

---

## Pattern: LP Step Management (Backend-Delegated)

Step relationships (HAS_STEP) are managed via `LpBackend` — services delegate:

```python
# Backend (LpBackend) — owns the Cypher
steps = await backend.get_steps_raw(path_uid, depth=1)      # raw dicts
parent = await backend.get_parent_path_raw(step_uid)         # raw dict or None
await backend.add_step_to_path(path_uid, step_uid, sequence=0)
await backend.remove_step_from_path(path_uid, step_uid)      # auto-reorders remaining
await backend.reorder_steps(path_uid, ["ps:step2", "ps:step1"])

# Service (LpCoreService) — validates + converts to domain models
async def get_steps(self, path_uid, depth=1):
    result = await self.backend.get_steps_raw(path_uid, depth)
    return Result.ok([from_neo4j_node(data, PathStep) for data in result.value])
```

---

## Pattern: LP Intelligence Delegation (Backend-Delegated)

Intelligence Cypher queries live on `LpBackend` via `_LpIntelligenceMixin` (8 methods). `LpIntelligenceService` delegates, then transforms raw records into typed results. Search queries live on `_LpProgressMixin` (4 methods including `get_paths_aligned_with_goal`, `get_paths_by_knowledge`, `get_user_paths_prioritized`, `get_paths_containing_step`). `LpSearchService` is typed as `BaseService["LpOperations", LearningPath]` to access these.

**Critical:** `execute_query` returns `Result[list[dict]]` — a list of Neo4j records. Always extract records from the list before accessing keys:

```python
# Single-record queries (blocker_analysis, recommendations, path_context):
result = await self.backend.identify_path_blockers(path_uid, user_uid)
records = result.value or []
record = records[0] if records else None
if not record:
    return Result.ok({...empty fallback...})
analysis = record["blocker_analysis"]  # extract the named RETURN alias

# Multi-record queries (validate_path_prerequisites):
result = await self.backend.validate_path_prerequisites(path_uid)
records = result.value or []
validations = [r["validation"] for r in records]  # one record per step
```

**Never** call `.get()` directly on `result.value` — that's a list, not a dict.

---

## Pattern: Cross-Domain LP → PS Dependency

LP requires PsService injected at construction — the only cross-domain service dependency in the curriculum stack:

```python
# In services_bootstrap/_learning_services.py (order matters!)
ps_service = PsService(driver, graph_intel, event_bus)
lp_service = LpService(driver, ps_service, graph_intel, event_bus)  # <- ps_service required
```

When adding a new LP feature that needs PS data, access it via `self.ps_service` (available on `LpCoreService`), not via direct Neo4j queries.

---

**See Also**: [SKILL.md](SKILL.md) for domain overview, [DOMAIN_SPECIFICS.md](DOMAIN_SPECIFICS.md) for per-domain details
