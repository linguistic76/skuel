# Curriculum Domain Patterns

> Implementation patterns for Lesson, KU, LS, LP features.

---

## Pattern: Adding a Curriculum Domain Service Config

All core/search services use `_config = create_curriculum_domain_config(...)` (not bare class attributes).

```python
from core.services.domain_config import create_curriculum_domain_config

class LessonCoreService(BaseService[LessonOperations, Article]):
    _config = create_curriculum_domain_config(
        dto_class=LessonDTO,
        model_class=Lesson,
        domain_name="articles",
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
await lesson_service.organize_article(
    parent_uid="l_yoga-fundamentals_abc123",
    child_uid="l_meditation-basics_xyz789",
    order=1,
    importance="core",
)

# Navigate the structure
children = await lesson_service.get_organized_children("l_yoga-fundamentals_abc123", depth=2)
parents = await lesson_service.get_parent_articles("l_meditation-basics_xyz789")
root_organizers = await lesson_service.list_root_organizers()

# Check if a Lesson acts as an organizer
is_org = await lesson_service.is_organizer("l_yoga-fundamentals_abc123")
```

**When to use this pattern:** When users want to navigate knowledge non-linearly (exploring a topic map rather than following a prescribed sequence). This replaces the old MOC domain entirely.

---

## Pattern: Cross-Domain LP → LS Dependency

LP requires LsService injected at construction — the only cross-domain service dependency in the curriculum stack:

```python
# In services_bootstrap.py (order matters!)
ls_service = LsService(driver, graph_intel, event_bus)
lp_service = LpService(driver, ls_service, graph_intel, event_bus)  # <- ls_service required
```

When adding a new LP feature that needs LS data, access it via `self.ls_service` (available on `LpCoreService`), not via direct Neo4j queries.

---

**See Also**: [SKILL.md](SKILL.md) for domain overview, [DOMAIN_SPECIFICS.md](DOMAIN_SPECIFICS.md) for per-domain details
