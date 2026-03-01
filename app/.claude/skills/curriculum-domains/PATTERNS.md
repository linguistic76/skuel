# Curriculum Domain Patterns

> Implementation patterns for KU, LS, LP features.

---

## Pattern: Adding a Curriculum Domain Service Config

All core/search services use `_config = create_curriculum_domain_config(...)` (not bare class attributes).

```python
from core.services.domain_config import create_curriculum_domain_config

class KuCoreService(BaseService[KuOperations, Curriculum]):
    _config = create_curriculum_domain_config(
        dto_class=CurriculumDTO,
        model_class=Curriculum,
        domain_name="ku",
        search_fields=("title", "description", "content"),
        category_field="domain",
    )
```

**Key difference from Activity Domains:** No `user_ownership_relationship` — curriculum content is shared (`_user_ownership_relationship = None` is set automatically by `create_curriculum_domain_config`).

---

## Pattern: KU Organization (Non-Linear Navigation)

Any Ku can organize other Kus via `ORGANIZES` relationships. There is no `MocService` — this is `KuOrganizationService`:

```python
# Create non-linear structure
await ku_service.organize_ku(
    parent_uid="ku_yoga-fundamentals_abc123",
    child_uid="ku_meditation-basics_xyz789",
    order=1,
    importance="core",
)

# Navigate the structure
subkus = await ku_service.get_subkus("ku_yoga-fundamentals_abc123", depth=2)
parents = await ku_service.get_parent_kus("ku_meditation-basics_xyz789")
root_organizers = await ku_service.list_root_organizers()

# Check if a KU acts as an organizer
is_org = await ku_service.is_organizer("ku_yoga-fundamentals_abc123")
```

**When to use this pattern:** When users want to navigate knowledge non-linearly (exploring a topic map rather than following a prescribed sequence). This replaces the old MOC domain entirely.

---

## Pattern: Cross-Domain LP → LS Dependency

LP requires LsService injected at construction — the only cross-domain service dependency in the curriculum stack:

```python
# In services_bootstrap.py (order matters!)
ls_service = LsService(driver, graph_intel, event_bus)
lp_service = LpService(driver, ls_service, graph_intel, event_bus)  # ← ls_service required
```

When adding a new LP feature that needs LS data, access it via `self.ls_service` (available on `LpCoreService`), not via direct Neo4j queries.

---

**See Also**: [SKILL.md](SKILL.md) for domain overview, [DOMAIN_SPECIFICS.md](DOMAIN_SPECIFICS.md) for per-domain details
