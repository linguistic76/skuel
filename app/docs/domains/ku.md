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
**UID Prefix:** `ku.` (dot notation, NOT colon)
**Entity Label:** `Ku`
**Topology:** Point (atomic content)

## Purpose

Knowledge Units are atomic pieces of knowledge content. They represent the fundamental building blocks that other curriculum patterns aggregate.

## UID Format

```
ku.{filename}
```

**Examples:**
- `ku.machine-learning`
- `ku.python-basics`
- `ku.meditation-fundamentals`

**Note:** UIDs are flat (not hierarchical). See ADR-013.

## Service Architecture (ADR-030)

KuService coordinates 9 sub-services (4 common + 5 domain-specific):

| Sub-service | Class | Purpose |
|-------------|-------|---------|
| `.core` | KuCoreService | CRUD operations |
| `.search` | KuSearchService | Search and discovery |
| `.relationships` | UnifiedRelationshipService | Prerequisite associations |
| `.intelligence` | KuIntelligenceService | Knowledge suggestions, cross-domain |
| `.graph` | KuGraphService | Graph navigation, prerequisites |
| `.semantic` | KuSemanticService | Semantic relationships, RDF-style |
| `.learning_paths` | KuLpService | Learning path operations (optional) |
| `.practice` | KuPracticeService | Practice tracking (event-driven) |
| `.interaction` | KuInteractionService | Pedagogical state tracking |

**Initialization:** Manual (non-standard core signature requires multiple dependencies)
**graph_intel:** REQUIRED (fail-fast validation)

```python
from core.services.ku_service import KuService

# In services_bootstrap.py
ku_service = KuService(
    repo=ku_backend,
    graph_intelligence_service=graph_intelligence,  # REQUIRED
    embeddings_service=embeddings_service,
    llm_service=llm_service,
    event_bus=event_bus,
)

# Access sub-services
await ku_service.core.create(ku)
await ku_service.search.search_by_title_template(query)
await ku_service.relationships.get_related_uids("prerequisites", ku_uid)
await ku_service.intelligence.get_knowledge_suggestions(user_uid, ku_uid)
await ku_service.graph.get_prerequisite_chain(ku_uid)
await ku_service.semantic.get_semantic_neighborhood(ku_uid)
```

## Key Files

| Component | Location |
|-----------|----------|
| Facade | `/core/services/ku_service.py` |
| Core Service | `/core/services/ku/ku_core_service.py` |
| Search Service | `/core/services/ku/ku_search_service.py` |
| Intelligence Service | `/core/services/ku_intelligence_service.py` |
| Graph Service | `/core/services/ku/ku_graph_service.py` |
| Semantic Service | `/core/services/ku/ku_semantic_service.py` |
| LP Service | `/core/services/ku/ku_lp_service.py` |
| Practice Service | `/core/services/ku/ku_practice_service.py` |
| Interaction Service | `/core/services/ku/ku_interaction_service.py` |
| Model | `/core/models/ku/ku.py` |
| DTO | `/core/models/ku/ku_dto.py` |
| Relationships Container | `/core/models/ku/ku_relationships.py` |
| Relationship Config | `/core/services/relationships/domain_configs.py` (`get_ku_config()`) |

## Model Fields

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Unique identifier (`ku.filename`) |
| `title` | `str` | Knowledge unit title |
| `content` | `str` | Markdown content |
| `domain` | `Domain` | TECH, HEALTH, PERSONAL, etc. |
| `difficulty` | `Difficulty` | Beginner, Intermediate, Advanced |
| `estimated_minutes` | `int` | Estimated reading/learning time |
| `source_file` | `str?` | Original markdown file path |
| `frontmatter` | `dict?` | YAML frontmatter metadata |
| `created_at` | `datetime` | Creation timestamp |
| `updated_at` | `datetime` | Last update timestamp |

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

**Note:** KU uses `REQUIRES_KNOWLEDGE` and `ENABLES_KNOWLEDGE` (not `PREREQUISITE` or `ENABLES`)
for KU-to-KU relationships. The RelationshipName enum is the single source of truth.

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
- `GET /api/knowledge/{uid}` - Get KU
- `PUT /api/knowledge/{uid}` - Update KU
- `DELETE /api/knowledge/{uid}` - Delete KU
- `GET /api/knowledge` - List KUs with pagination

### Personalized Context (January 2026)

**`GET /api/knowledge/{uid}/my-context`** - Returns how the authenticated user uses this knowledge.

Requires authentication. Returns per-user substance score, activity breakdown, and recommendations.

```json
{
    "ku_uid": "ku.python-basics",
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
- `GET /api/knowledge/{uid}/relationships` - Get relationships
- `GET /api/knowledge/{uid}/prerequisites` - Get prerequisites
- `GET /api/knowledge/{uid}/dependencies` - Get dependents
- `GET /api/knowledge/search?q=...` - Search KUs
- `GET /api/knowledge/related/{uid}` - Find related KUs
- `GET /api/knowledge/analytics/summary` - Summary analytics

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

1. **`self.relationships`** - UnifiedRelationshipService for harmonious relationship access
2. **KuGraphService** - Specialized intelligence (prerequisite chains, hub scores, learning recommendations)
3. **KuSemanticService** - Specialized intelligence (RDF-inspired semantics, confidence scoring)
4. **KuIntelligenceService** - Cross-domain opportunities, knowledge suggestions

```python
# Via KuService facade - harmonious relationship access
ku_service = services.ku
enables = await ku_service.get_enables("ku.advanced-python")  # Uses UnifiedRelationshipService

# Via specialized services - intelligence operations
prereq_chain = await ku_service.graph.get_prerequisite_chain("ku.advanced-python")
semantic_neighborhood = await ku_service.semantic.get_semantic_neighborhood("ku.ml-basics")
suggestions = await ku_service.intelligence.get_knowledge_suggestions(user_uid, "ku.python")
```

## Relationship Config

KU uses `get_ku_config()` for UnifiedRelationshipService:

```python
from core.services.relationships.domain_configs import get_ku_config

config = get_ku_config()
# Defines: prerequisites, enables, broader, narrower, related
```

## Related ADRs

- [ADR-013: KU UID Flat Identity](../decisions/ADR-013-ku-uid-flat-identity.md)
- [ADR-023: Curriculum BaseService Migration](../decisions/ADR-023-curriculum-base-service.md)
- [ADR-024: BaseAnalyticsService Migration](../decisions/ADR-024-base-intelligence-service.md)
- [ADR-028: KU & MOC Unified Relationship Migration](../decisions/ADR-028-ku-moc-unified-relationship-migration.md)
- [ADR-030: Curriculum Domain Unification](../decisions/ADR-030-curriculum-domain-unification.md)

## See Also

- [LS Domain](ls.md) - Learning Steps aggregate KUs
- [LP Domain](lp.md) - Learning Paths sequence KUs
- [MOC Domain](moc.md) - MOCs navigate KUs
- [Curriculum Grouping Patterns](../architecture/CURRICULUM_GROUPING_PATTERNS.md)
