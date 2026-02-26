---
title: Service File Organization
updated: 2026-01-21
status: current
category: architecture
tags: [services, organization, patterns, imports]
related: [SERVICE_CONSOLIDATION_PATTERNS.md, FOURTEEN_DOMAIN_ARCHITECTURE.md]
---

# Service File Organization

> **Core Principle:** "Facade at root, implementation in folder"

This document explains the intentional organization of service files in `/core/services/`.

## Three Categories of Services

### 1. DUAL-LOCATION Services (16 total)

Services with **both** a root-level facade AND a subfolder with sub-services.

| Category | Services | Pattern |
|----------|----------|---------|
| Activity Domains (6) | tasks, goals, habits, events, choices, principles | Facade + 6-11 sub-services |
| Curriculum Domains (3) | ku, lp, ls | Facade + 5-8 sub-services |
| Cross-Cutting (7) | user, askesis, moc, lp_intelligence, adaptive_lp, finance | Facade + specialized sub-services |

**Structure:**
```
/core/services/
  tasks_service.py          # Facade (public API)
  tasks/                    # Implementation folder
    __init__.py             # Re-exports sub-services
    tasks_core_service.py   # CRUD operations
    tasks_search_service.py # Search/discovery
    tasks_intelligence_service.py  # Graph analytics
    tasks_progress_service.py      # Progress tracking
    tasks_scheduling_service.py    # Scheduling logic
    tasks_planning_service.py      # Planning operations
    tasks_ai_service.py     # AI features (optional)
```

**Rationale:** This is the **intentional architecture**. The facade provides a stable public API while internal implementation can evolve freely. External code imports `TasksService` from the root; sub-services are implementation details.

### 2. FOLDER-ONLY Services (15 total)

Infrastructure modules that don't need a facade.

| Folder | Purpose |
|--------|---------|
| `search/` | Unified search across all domains |
| `relationships/` | UnifiedRelationshipService + configs |
| `protocols/` | Protocol definitions (all interfaces) |
| `intelligence/` | User context intelligence hub |
| `infrastructure/` | Cross-cutting helpers |
| `ingestion/` | UnifiedIngestionService |
| `query/` | Query builders (CypherGenerator, etc.) |
| `insight/` | Analytics/insights |
| `dsl/` | Activity DSL parser & engine |
| `mixins/` | Reusable mixins |
| `assignments/` | Assignments domain |
| `journals/` | Journals domain |
| `lifepath/` | LifePath domain |
| `reports/` | Reports meta-service |
| `transcription/` | Deepgram transcription |

**Rationale:** These are either:
- Infrastructure (no single entry point needed)
- Newer domains using folder-based organization exclusively

### 3. ROOT-ONLY Services (31 total)

Standalone services without subfolders.

| Category | Services |
|----------|----------|
| **Base Classes** | `base_service.py`, `base_analytics_service.py`, `base_ai_service.py`, `base_planning_service.py` |
| **AI/LLM** | `ai_service.py`, `llm_service.py`, `embeddings_service.py`, `context_aware_ai_service.py` |
| **Askesis Secondary** | `askesis_ai_service.py`, `askesis_citation_service.py` |
| **KU Generation** | `entity_chunking_service.py`, `insight_generation_service.py`, `entity_inference_service.py`, `ku_intelligence_service.py` |
| **Calendar** | `calendar_service.py`, `calendar_optimization_service.py` |
| **Analytics** | `cross_domain_analytics_service.py` |
| **Content** | `conversion_service.py`, `event_logger_service.py`, `content_enrichment_service.py` |
| **Reports** | `report_service.py`, `report_relationship_service.py` |
| **Schema** | `schema_service.py`, `schema_mapping_service.py` |
| **User Secondary** | `user_progress_service.py`, `user_relationship_service.py` |
| **System** | `performance_optimization_service.py`, `system_service.py`, `visualization_service.py` |

**Rationale:** These are either:
- Base classes (inherited, not instantiated directly)
- Single-responsibility utilities
- Secondary services for a domain (could move into folders, but functional as-is)

## When to Use Each Pattern

| Pattern | Use When |
|---------|----------|
| **DUAL** | Complex domain with multiple responsibilities; external API stability needed |
| **FOLDER-ONLY** | Infrastructure module; implementation details only; no facade needed |
| **ROOT-ONLY** | Single-responsibility service; utility/helper; base class |

## Import Guidelines

### For Domain Services (DUAL pattern)

**External code should import the facade:**
```python
# CORRECT - Import from facade
from core.services.tasks_service import TasksService
from core.services.goals_service import GoalsService
```

**Sub-services can be imported directly when needed:**
```python
# ALLOWED - Direct sub-service import for specific needs
from core.services.tasks import TasksCoreService
from core.services.tasks.tasks_intelligence_service import TasksIntelligenceService
```

### For Infrastructure (FOLDER-ONLY pattern)

**Import from package or specific module:**
```python
from core.ports import BackendOperations, TasksOperations
from core.services.relationships import UnifiedRelationshipService
from core.services.search.search_router import SearchRouter
```

### For Utilities (ROOT-ONLY pattern)

**Import directly:**
```python
from core.services.base_service import BaseService
from core.services.llm_service import LLMService
from core.services.embeddings_service import OpenAIEmbeddingsService
```

## Service Bootstrap

All services are composed in `/services_bootstrap.py` (2,106 lines). This file:
- Imports all facades and utilities
- Creates dependency graph
- Instantiates services with proper dependencies
- Exposes `Services` object with all service instances

## Potential Consolidation Candidates

The following ROOT-ONLY services COULD move into domain folders. They remain at root for historical reasons or simplicity:

| Service | Could Move To | Status |
|---------|---------------|--------|
| `askesis_ai_service.py` | `askesis/` | Functional as-is |
| `askesis_citation_service.py` | `askesis/` | Functional as-is |
| `entity_chunking_service.py` | `ku/` | Part of generation pipeline |
| `insight_generation_service.py` | `ku/` | Part of generation pipeline |
| `entity_inference_service.py` | `ku/` | Part of generation pipeline |
| `ku_intelligence_service.py` | `ku/` | Analytics service |
| `user_progress_service.py` | `user/` | Functional as-is |
| `user_relationship_service.py` | `user/` | Functional as-is |

**Decision:** Per "One Path Forward" philosophy, these remain at root until there's a compelling reason to consolidate. Moving files requires updating all imports and provides no functional benefit.

## Key Files Reference

| Purpose | Location |
|---------|----------|
| Service bootstrap | `/services_bootstrap.py` |
| Protocol definitions | `/core/ports/` |
| Base service | `/core/services/base_service.py` |
| Example facade | `/core/services/tasks_service.py` |
| Example sub-services | `/core/services/tasks/` |

## See Also

- [Service Consolidation Patterns](../patterns/SERVICE_CONSOLIDATION_PATTERNS.md)
- [14-Domain Architecture](FOURTEEN_DOMAIN_ARCHITECTURE.md)
- [Protocol Architecture](../patterns/protocol_architecture.md)
