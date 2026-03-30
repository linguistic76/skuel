# Curriculum Domain Patterns

> Implementation patterns for Lesson, KU, LS, LP features.

---

## Pattern: Adding a Curriculum Domain Service Config

All core/search services use `_config = create_curriculum_domain_config(...)` (not bare class attributes).

```python
from core.services.domain_config import create_curriculum_domain_config

class LessonCoreService(BaseService[LessonOperations, Lesson]):
    _config = create_curriculum_domain_config(
        dto_class=LessonDTO,
        model_class=Lesson,
        domain_name="lesson",
        search_fields=("title", "description", "content"),
        category_field="domain",
    )
```

**Key difference from Activity Domains:** No `user_ownership_relationship` — curriculum content is shared (`_user_ownership_relationship = None` is set automatically by `create_curriculum_domain_config`).

---

## Pattern: Lesson Organization (Non-Linear Navigation)

Any Lesson can organize other Lessons via `ORGANIZES` relationships. There is no `MocService` — this is `LessonOrganizationService`:

```python
# Create non-linear structure
await lesson_service.organize(
    parent_uid="l_yoga-fundamentals_abc123",
    child_uid="l_meditation-basics_xyz789",
    order=1,
    importance="core",
)

# Navigate the structure
children = await lesson_service.get_organized_children("l_yoga-fundamentals_abc123", depth=2)
parents = await lesson_service.find_organizers("l_meditation-basics_xyz789")
root_organizers = await lesson_service.list_root_organizers()

# Check if a Lesson acts as an organizer
is_org = await lesson_service.is_organizer("l_yoga-fundamentals_abc123")

# Prev/next sibling navigation (used by /api/lesson/{uid}/navigation)
# Returns KuNavigation dataclass — propagates DB errors, returns empty nav for legitimate empty states
result = await lesson_service.get_navigation("l_meditation-basics_xyz789")
nav = result.value  # KuNavigation(prev_uid, prev_title, next_uid, next_title)
```

**When to use this pattern:** When users want to navigate knowledge non-linearly (exploring a topic map rather than following a prescribed sequence). This replaces the old MOC domain entirely.

**Key dataclass:** `KuNavigation` (frozen, from `core/services/lesson/lesson_organization_service.py`) — prev/next sibling in MOC ORGANIZES order. Exported via `core/services/lesson/__init__.py`.

---

## Pattern: LS Knowledge Relationship CRUD (Backend-Delegated)

Knowledge relationships (CONTAINS_KNOWLEDGE) are managed via `PsBackend` — services delegate, no inline Cypher:

```python
# Backend (PsBackend) — owns the Cypher
await backend.add_knowledge(ps_uid, ku_uid, "primary")
await backend.remove_knowledge(ps_uid, ku_uid)
knowledge = await backend.list_knowledge(ps_uid, knowledge_type="primary")
summary = await backend.get_knowledge_summary(ps_uid)  # {primary_count, supporting_count, ...}

# Service (PsCoreService) — validates + delegates
async def add_knowledge_relationship(self, ps_uid, ku_uid, knowledge_type="primary"):
    if knowledge_type not in ("primary", "supporting"):
        return Result.fail(Errors.validation(...))
    return await self.backend.add_knowledge(ps_uid, ku_uid, knowledge_type)
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
await backend.reorder_steps(path_uid, ["ls:step2", "ls:step1"])

# Service (LpCoreService) — validates + converts to domain models
async def get_steps(self, path_uid, depth=1):
    result = await self.backend.get_steps_raw(path_uid, depth)
    return Result.ok([from_neo4j_node(data, PathStep) for data in result.value])
```

---

## Pattern: Cross-Domain LP → LS Dependency

LP requires PsService injected at construction — the only cross-domain service dependency in the curriculum stack:

```python
# In services_bootstrap/_learning_services.py (order matters!)
ps_service = PsService(driver, graph_intel, event_bus)
lp_service = LpService(driver, ps_service, graph_intel, event_bus)  # <- ps_service required
```

When adding a new LP feature that needs LS data, access it via `self.ps_service` (available on `LpCoreService`), not via direct Neo4j queries.

---

**See Also**: [SKILL.md](SKILL.md) for domain overview, [DOMAIN_SPECIFICS.md](DOMAIN_SPECIFICS.md) for per-domain details
