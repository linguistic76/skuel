# Curriculum Domain Patterns

> Implementation patterns for Article, KU, LS, LP features.

---

## Pattern: Adding a Curriculum Domain Service Config

All core/search services use `_config = create_curriculum_domain_config(...)` (not bare class attributes).

```python
from core.services.domain_config import create_curriculum_domain_config

class ArticleCoreService(BaseService[ArticleOperations, Article]):
    _config = create_curriculum_domain_config(
        dto_class=ArticleDTO,
        model_class=Article,
        domain_name="articles",
        search_fields=("title", "description", "content"),
        category_field="domain",
    )
```

**Key difference from Activity Domains:** No `user_ownership_relationship` — curriculum content is shared (`_user_ownership_relationship = None` is set automatically by `create_curriculum_domain_config`).

---

## Pattern: Article Organization (Non-Linear Navigation)

Any Article can organize other Articles via `ORGANIZES` relationships. There is no `MocService` — this is `ArticleOrganizationService`:

```python
# Create non-linear structure
await article_service.organize_article(
    parent_uid="a_yoga-fundamentals_abc123",
    child_uid="a_meditation-basics_xyz789",
    order=1,
    importance="core",
)

# Navigate the structure
children = await article_service.get_organized_children("a_yoga-fundamentals_abc123", depth=2)
parents = await article_service.get_parent_articles("a_meditation-basics_xyz789")
root_organizers = await article_service.list_root_organizers()

# Check if an Article acts as an organizer
is_org = await article_service.is_organizer("a_yoga-fundamentals_abc123")
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
