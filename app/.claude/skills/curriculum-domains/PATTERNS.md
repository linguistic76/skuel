# Curriculum Domain Patterns

> Implementation patterns for Ku, PathStep (PS), and LearningPath (LP) features.

---

## Pattern: Adding a Curriculum Domain Service Config

All core/search services use `_config = create_curriculum_domain_config(...)` (not bare class attributes).

```python
from core.services.domain_config import create_curriculum_domain_config

class PsCoreService(BaseService["PsOperations", PathStep]):
    _config = create_curriculum_domain_config(
        dto_class=PathStepDTO,
        model_class=PathStep,
        entity_label="Entity",
        domain_name="ps",
        search_fields=("title", "intent", "description"),
        search_order_by="updated_at",
        category_field="nous",  # NOUS topic membership (array — `has` semantics)
        content_field="description",
    )
```

**Key difference from Activity Domains:** `create_curriculum_domain_config` leaves `user_ownership_relationship` at `None` — curriculum content is shared. Ku passes `entity_label="Ku"` and `supports_user_progress=False`.

---

## Pattern: PathStep Organization (Non-Linear Navigation)

Any PathStep can organize other PathSteps via `ORGANIZES` relationships. There is no `MocService` — this is `PsOrganizationService` (a sub-service of `PsService`; the facade delegates every method). Its reads and `organize` take a PathStep subject and return shared-curriculum entities only; other edges (PathStep → Ku, a personal `moc: true` map) are authored in the vault:

```python
# Create non-linear structure — both uids must be PathSteps
await ps_service.organization.organize(
    parent_uid="ps.mindfulness.foundations",
    child_uid="ps.mindfulness.breath-awareness-basics",
    order=1,
)

# Navigate the structure
children = await ps_service.organization.get_organized_children("ps.mindfulness.foundations")
view = await ps_service.organization.get_organization_view("ps.mindfulness.foundations", max_depth=3)
parents = await ps_service.organization.find_organizers("ps.mindfulness.breath-awareness-basics")
root_organizers = await ps_service.organization.list_root_organizers()

# Check if a PathStep acts as an organizer
is_org = await ps_service.organization.is_organizer("ps.mindfulness.foundations")

# Prev/next sibling navigation in MOC ORGANIZES order.
# Returns a StepNavigation dataclass — propagates DB errors, returns empty nav for legitimate empty states.
result = await ps_service.organization.get_navigation("ps.mindfulness.breath-awareness-basics")
nav = result.value  # StepNavigation(prev_uid, prev_title, next_uid, next_title)
```

**When to use this pattern:** When users want to navigate knowledge non-linearly (exploring a topic map rather than following a prescribed sequence). This is the emergent MOC pattern.

**Key dataclass:** `StepNavigation` (frozen, from `core/services/ps/ps_organization_service.py`) — prev/next sibling in MOC ORGANIZES order.

---

## Pattern: PS Knowledge Composition (Authored, Registry-Driven)

A PathStep's knowledge edges are authored in its vault frontmatter and written by ingestion
from the `PS_CONFIG` registry entries — there is no service method that adds or removes them:

| Frontmatter field | Edge | Registry `method_key` |
|-------------------|------|------------------------|
| `uses_kus:` | `(PathStep)-[:USES_KU]->(Ku)` | `uses_ku` |
| `trains_ku_uids:` | `(PathStep)-[:TRAINS_KU]->(Ku)` | `trains_ku` |
| `knowledge_uids:` | `(PathStep)-[:CONTAINS_KNOWLEDGE]->(Entity)` | `knowledge` |

Read them through the relationship service or the core summary:

```python
ku_uids = await ps_service.relationships.get_related_uids("uses_ku", ps_uid)  # Result[list[str]]
summary = await ps_service.core.get_knowledge_summary(ps_uid)  # CONTAINS_KNOWLEDGE {count, uids}
```

`LpBackend.persist_path_with_steps` is the one programmatic `USES_KU` writer: it draws the edges
from each new step's `knowledge_uids` when an LP is created with its steps.

---

## Pattern: LP Step Management (Backend-Delegated)

Step relationships (HAS_STEP) are managed via `LpBackend` — services delegate:

```python
# Backend (LpBackend, _LpStepMixin) — owns the Cypher and maps nodes to models
steps = await backend.get_steps_raw(path_uid, depth=1)      # Result[list[PathStep]]
parent = await backend.get_parent_path_raw(step_uid)         # Result[LearningPath | None]
await backend.add_step_to_path(path_uid, step_uid, sequence=0)
await backend.remove_step_from_path(path_uid, step_uid)      # auto-reorders remaining
await backend.reorder_steps(path_uid, ["ps.python.control-flow", "ps.python.first-program"])

# Service (LpCoreService) — delegates; despite the `_raw` suffix, the values are typed models
async def get_steps(self, path_uid: str, depth: int = 1) -> Result[list[PathStep]]:
    result = await self.backend.get_steps_raw(path_uid, depth)
    if result.is_error:
        return Result.fail(result)
    return Result.ok(result.value)
```

---

## Pattern: LP Intelligence Delegation (Backend-Delegated)

Intelligence Cypher lives on `LpBackend` via `_LpIntelligenceMixin`. `LpIntelligenceService` (and its `_path_analysis_mixin.py`) delegates, then transforms raw records into typed results. Search queries live on `_LpProgressMixin` (`get_paths_aligned_with_goal`, `get_paths_by_knowledge`, `get_user_paths_prioritized`, `get_paths_containing_step`, …). `LpSearchService` is typed as `BaseService["LpOperations", LearningPath]` to access these.

**Critical:** these intelligence backend methods return `Result[list[dict[str, Any]]]` — a list of Neo4j records. Always extract records from the list before accessing keys:

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
ps_service = PsService(backend=knowledge_backend, executor=query_executor,
                       graph_intel=graph_intelligence, event_bus=event_bus, ...)
learning_paths = LpService(
    backend=lp_backend,
    ps_service=ps_service,  # <- required
    graph_intel=graph_intelligence,
    event_bus=event_bus,
    ...
)
```

When adding a new LP feature that needs PS data, access it via `self.ps_service` (available on `LpCoreService`), not via direct Neo4j queries.

---

**See Also**: [SKILL.md](SKILL.md) for domain overview, [DOMAIN_SPECIFICS.md](DOMAIN_SPECIFICS.md) for per-domain details
