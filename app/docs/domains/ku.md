---
title: KU (Knowledge Unit) Domain
created: 2025-12-04
updated: 2026-01-11
status: current
category: domains
tags:
- ku
- knowledge
- curriculum-domain
- domain
- adr-030
related_skills:
- curriculum-domains
---

# KU (Knowledge Unit) Domain

**Type:** Curriculum Domain (1 of 4)
**UID Prefix:** `ku_` (flat UIDs, hierarchy in ORGANIZES relationships)
**Entity Label:** `Ku`
**Topology:** Point (atomic content)

## Purpose

**Skill:** [@curriculum-domains](../../.claude/skills/curriculum-domains/SKILL.md)

Knowledge Units are atomic pieces of knowledge content. They represent the fundamental building blocks that other curriculum patterns aggregate.

## UID Format

```
ku_{slug}_{random}
```

**Examples:**
- `ku_machine-learning_a1b2c3d4`
- `ku_python-basics_e5f6g7h8`
- `ku_meditation-fundamentals_i9j0k1l2`

**Note:** UIDs are flat (not hierarchical). See ADR-013.

## Service Architecture (ADR-030)

KuService coordinates 9 sub-services (4 common + 5 domain-specific):

| Sub-service | Class | Purpose |
|-------------|-------|---------|
| `.core` | KuCoreService | CRUD operations |
| `.search_service` | KuSearchService | Search and discovery |
| `.relationships` | UnifiedRelationshipService | Prerequisite associations |
| `.intelligence` | KuIntelligenceService | Knowledge suggestions, cross-domain |
| `.backend` | KuBackend | Graph queries, learning state (Studying + Understood), mastery (Ku-native). Contract: `KuOperations` protocol (23 methods, April 2026) |

**Initialization:** Via `create_curriculum_sub_services()` factory.
**graph_intel:** REQUIRED (fail-fast validation)

**Architectural principle:** Ku never depends on PsService. Learning state (Studying → Understood) and mastery are Ku-native capabilities on `KuBackend`.

```python
from core.services.ku_service import KuService

# In services_bootstrap/_learning_services.py
atomic_ku_service = KuService(
    backend=atomic_ku_backend,
    graph_intel=graph_intelligence,  # REQUIRED
    event_bus=event_bus,
)

# Access sub-services
await ku_service.core.create(ku)
await ku_service.search.search(query)
await ku_service.intelligence.get_usage_summary(ku_uid)
await ku_service.mark_as_studying(user_uid, ku_uid)
await ku_service.mark_as_understood(user_uid, ku_uid)
await ku_service.get_path_steps(ku_uid)
```

## Key Files

| Component | Location |
|-----------|----------|
| Facade | `/core/services/ku_service.py` |
| Core Service | `/core/services/ku/ku_core_service.py` |
| Search Service | `/core/services/ku/ku_search_service.py` |
| Intelligence Service | `/core/services/ku/ku_intelligence_service.py` |
| Backend | `/adapters/persistence/neo4j/backends/curriculum_backends.py` (`KuBackend`) |
| Model | `/core/models/ku/ku.py` |
| DTO | `/core/models/ku/ku_dto.py` |
| Routes | `/adapters/inbound/ku_routes.py` + `/adapters/inbound/ku_ui.py` |
| Relationship Config | `KU_CONFIG` in `/core/models/relationship_registry.py` |

**Architectural principle:** Ku is the atom, PathStep is the molecule. Ku never depends on PsService. Learning state (Studying → Understood) and mastery are Ku-native capabilities on `KuBackend`.

## Model Fields (Ku-Specific)

Ku extends Entity directly (not Curriculum). These are the 3 Ku-specific fields beyond the ~29 Entity base fields:

| Field | Type | Description |
|-------|------|-------------|
| `aliases` | `tuple[str, ...]` | Alternative names for search/cross-referencing |
| `sel_category` | `SELCategory?` | SEL competency: self_awareness, self_management, social_awareness, relationship_skills, responsible_decision_making |
| `nous` | `tuple[str, ...]` | NOUS topic membership (stories, body, self-awareness, ...) — the category vocabulary (#534 "nous IS the category") |

> The former `namespace` / `ku_category` / `source` fields were retired (vault+graph 2026-07-06, model 2026-07-06). Grouping now lives in `nous` topics.

## Relationships

| Relationship | Direction | Target | Description |
|--------------|-----------|--------|-------------|
| `REQUIRES_KNOWLEDGE` | Outgoing | Ku | Prerequisite knowledge |
| `ENABLES_KNOWLEDGE` | Outgoing | Ku | Enables learning |
| `PART_OF` | Outgoing | Lp | Part of learning path |
| `HAS_BROADER` | Outgoing | Ku | Broader concept |
| `HAS_NARROWER` | Outgoing | Ku | Narrower concept |
| `RELATED_TO` | Both | Ku | Related concepts |
| `APPLIES_KNOWLEDGE` | Incoming | Task, Event | Applied in activities |
| `REQUIRES_KNOWLEDGE` | Incoming | Task, Goal | Required by activities |
| `REINFORCES_KNOWLEDGE` | Incoming | Habit | Reinforced by habits |

**Note:** KU uses `REQUIRES_KNOWLEDGE` and `ENABLES_KNOWLEDGE` for all KU-to-KU relationships.
Legacy types (`PREREQUISITE`, `REQUIRES`, `ENABLES`) were removed from the RelationshipName enum
in February 2026. Ingestion config derives from the relationship registry — see ADR-026.

## Intelligence Methods

KuIntelligenceService provides knowledge analytics:

| Method | Returns | Description |
|--------|---------|-------------|
| `get_knowledge_suggestions(user_uid, ku_uid)` | `dict` | Related concepts, paths, gaps |
| `get_cross_domain_opportunities(user_uid, ku_uid)` | `dict` | Cross-domain connections |
| `get_performance_analytics(user_uid, days, context)` | `dict` | Personalized substance metrics |
| `calculate_user_substance(ku_uid, context)` | `dict` | Per-user substance score (January 2026) |

## API Endpoints

### Standard CRUD (CRUDRouteFactory)
- `POST /api/knowledge` - Create KU
- `GET /api/ku/{uid}` - Get KU
- `PUT /api/ku/{uid}` - Update KU
- `DELETE /api/ku/{uid}` - Delete KU
- `GET /api/knowledge` - List KUs with pagination

### Personalized Context (January 2026)

**`GET /api/ku/{uid}/my-context`** - Returns how the authenticated user uses this knowledge.

Requires authentication. Returns per-user substance score, activity breakdown, and recommendations.

```json
{
    "ku_uid": "ku_python-basics_e5f6",
    "user_substance_score": 0.45,
    "breakdown": {
        "tasks": {"count": 3, "uids": [...], "score": 0.15},
        "habits": {"count": 1, "uids": [...], "score": 0.10},
        "events": {"count": 0, "uids": [], "score": 0.00},
        "journals": {"count": 0, "uids": [], "score": 0.00},
        "choices": {"count": 0, "uids": [], "score": 0.00}
    },
    "recommendations": [
        {"type": "journal", "message": "Reflect on...", "impact": "+0.07"}
    ],
    "status_message": "Applied but not yet integrated. Build habits."
}
```

### Other Endpoints
- `GET /api/ku/{uid}/relationships` - Get relationships
- `GET /api/ku/{uid}/prerequisites` - Get prerequisites
- `GET /api/ku/{uid}/dependencies` - Get dependents
- `GET /api/ku/search?q=...` - Search KUs
- `GET /api/ku/related/{uid}` - Find related KUs
- `GET /api/ku/analytics/summary` - Summary analytics

## MEGA-QUERY Sections

- `knowledge_mastery` - Mastery scores `{uid, score, mastered_at, confidence}`
- `mastered_knowledge_uids` - UIDs with mastery >= 0.8
- `knowledge_units_rich` - Full KU data with graph context

## Substance Philosophy

Knowledge substance measures how knowledge is LIVED:

| Application Type | Weight | Max |
|------------------|--------|-----|
| Habits | 0.10 | 0.30 |
| Journals | 0.07 | 0.20 |
| Choices | 0.07 | 0.15 |
| Principles | 0.07 | 0.15 |
| Events | 0.05 | 0.25 |
| Tasks | 0.05 | 0.25 |

## BaseService Inheritance

Both KuCoreService and KuSearchService extend `BaseService` (verified January 2026):

```python
class KuCoreService(BaseService["BackendOperations[Ku]", Ku]):
    _dto_class = Ku
    _model_class = Ku
    _user_ownership_relationship = None  # Shared curriculum content
    ...

class KuSearchService(BaseService["BackendOperations[Ku]", Ku]):
    _dto_class = Ku
    _model_class = Ku
    _search_fields = ["title", "content", "description"]
    _user_ownership_relationship = None  # Shared content
    ...
```

## Service Pattern

KU uses a **hybrid pattern** (January 2026):

`KuService` has exactly **four** sub-services (read them off its `__init__`, not off this
list — a list drifts, the constructor cannot):

1. **`self.core`** — `KuCoreService`, CRUD
2. **`self.search`** — `KuSearchService`
3. **`self.relationships`** — `UnifiedRelationshipService` for harmonious relationship access
4. **`self.intelligence`** — `KuIntelligenceService`, cross-domain opportunities and knowledge suggestions

Prerequisite chains, hub scores and RDF-inspired semantics belong to **PathStep**, not Ku:
`KuGraphService` / `KuSemanticService` were renamed to `PsGraphService` / `PsSemanticService`
in `2b8176602` (2026-03-06, "rename Ku → Article + create new atomic Ku entity"). Reach them
through `PsService`.

```python
# Via KuService facade - harmonious relationship access
ku_service = services.ku
enables = await ku_service.get_enables("ku_advanced-python_a1b2")  # Uses UnifiedRelationshipService

# Via sub-services - intelligence operations
suggestions = await ku_service.intelligence.get_knowledge_suggestions(user_uid, "ku_python_f7g8")

# Prerequisite chains and semantics live on PathStep
prereq_chain = await services.ps.get_prerequisite_chain("ps.core.advanced-python")
semantic_neighborhood = await services.ps.get_semantic_neighborhood("ps.core.ml-basics")
```

## Relationship Config

KU uses `KU_CONFIG` from the relationship registry:

```python
from core.models.relationship_registry import KU_CONFIG

config = KU_CONFIG
# Defines: prerequisites, enables, broader, narrower, related, organizes
```

## Related ADRs

- [ADR-013: KU UID Flat Identity](../decisions/ADR-013-ku-uid-flat-identity.md)
- [ADR-023: Curriculum BaseService Migration](../decisions/ADR-023-curriculum-base-service.md)
- [ADR-024: BaseAnalyticsService Migration](../decisions/ADR-024-base-intelligence-service.md)
- [ADR-028: KU & MOC Unified Relationship Migration](../decisions/ADR-028-ku-moc-unified-relationship-migration.md)
- [ADR-030: Curriculum Domain Unification](../decisions/ADR-030-curriculum-domain-unification.md)

## See Also

- [PS Domain](ls.md) - Path Steps aggregate KUs
- [LP Domain](lp.md) - Learning Paths sequence KUs
- [MOC Domain](moc.md) - MOCs navigate KUs
- [Curriculum Grouping Patterns](../architecture/CURRICULUM_GROUPING_PATTERNS.md)
