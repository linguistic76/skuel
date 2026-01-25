---
title: SKUEL Documentation Hub
created: 2025-10-17
updated: 2025-12-04
status: active
audience: all
tags: [documentation, index, hub, architecture, patterns]
---

# SKUEL Documentation Hub

> **⚠️ SINGLE SOURCE OF TRUTH FOR TECHNICAL DOCUMENTATION**
>
> This directory (`/home/mike/skuel/app/docs/`) is the **ONLY** location for technical, architectural, and developer documentation. Do NOT reference or create technical docs elsewhere.
>
> **Note:** `/home/mike/0bsidian/skuel/docs/` contains Knowledge Unit (KU) **content** for the knowledge graph - learning materials about topics like investment, life, environment, etc. It is NOT technical documentation.

**Location:** `/home/mike/skuel/app/docs/`
**Last Updated:** 2026-01-02
**Total Documents:** 123

---

## Quick Navigation

**Start here:**
- **[INDEX.md](INDEX.md)** - Complete document index with tables by category
- **[CLAUDE.md](/home/mike/skuel/app/CLAUDE.md)** - Main instructions for Claude/AI assistants

**By role:**
- **New to SKUEL?** → [Architecture Overview](architecture/ARCHITECTURE_OVERVIEW.md)
- **Adding a feature?** → [14-Domain Architecture](architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md)
- **Writing queries?** → [Query Architecture](patterns/query_architecture.md)
- **Working with relationships?** → [Unified Relationship Service](patterns/UNIFIED_RELATIONSHIP_SERVICE.md)

---

## Documentation Categories

| Category | Description | Key Documents |
|----------|-------------|---------------|
| **[architecture/](architecture/)** | System design, domain structure | [14-Domain Architecture](architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md), [Neo4j Architecture](architecture/NEO4J_DATABASE_ARCHITECTURE.md) |
| **[patterns/](patterns/)** | Implementation patterns, coding standards | [Query Architecture](patterns/query_architecture.md), [Error Handling](patterns/ERROR_HANDLING.md) |
| **[decisions/](decisions/)** | Architecture Decision Records (ADRs) | [ADR-015 MEGA-QUERY](decisions/ADR-015-mega-query-rich-queries-completion.md), [ADR-016 Context Builder](decisions/ADR-016-context-builder-decomposition.md) |
| **[dsl/](dsl/)** | Activity DSL specification | [DSL Specification](dsl/DSL_SPECIFICATION.md), [DSL Usage Guide](dsl/DSL_USAGE_GUIDE.md) |
| **[guides/](guides/)** | Step-by-step implementation guides | [Event-Driven Migration](guides/EVENT_DRIVEN_MIGRATION_GUIDE.md), [UI Components](guides/SHARED_UI_COMPONENTS_GUIDE.md) |
| **[reference/](reference/)** | Templates, checklists, enums | [Protocol Reference](reference/PROTOCOL_REFERENCE.md), [Enum Reference](reference/ENUM_REFERENCE.md) |
| **[intelligence/](intelligence/)** | AI features roadmap | [Intelligence Roadmap](intelligence/INTELLIGENCE_ROADMAP.md) |
| **[technical_debt/](technical_debt/)** | Known limitations | [MyPy Backend Limitations](technical_debt/MYPY_BACKEND_LIMITATIONS.md) |
| **[domains/](domains/)** | Domain-specific documentation | Individual domain guides |
| **[migrations/](migrations/)** | Migration guides | Schema and data migrations |
| **[user-guides/](user-guides/)** | User-facing documentation | End-user help and guides |

---

## Current Architecture (December 2025)

### Core Patterns

| Pattern | Documentation | Status |
|---------|---------------|--------|
| **14-Domain Architecture** | [FOURTEEN_DOMAIN_ARCHITECTURE.md](architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md) | Active |
| **6 Activity Domains** | Tasks, Goals, Habits, Events, Choices, Principles | Active |
| **UnifiedRelationshipService** | [UNIFIED_RELATIONSHIP_SERVICE.md](patterns/UNIFIED_RELATIONSHIP_SERVICE.md) | Active (6 domains) |
| **MEGA-QUERY** | [ADR-015](decisions/ADR-015-mega-query-rich-queries-completion.md) | Active |
| **Context Builder Decomposition** | [ADR-016](decisions/ADR-016-context-builder-decomposition.md) | Active |
| **Three-Tier Type System** | [three_tier_type_system.md](patterns/three_tier_type_system.md) | Active |
| **Result[T] Error Handling** | [ERROR_HANDLING.md](patterns/ERROR_HANDLING.md) | Active |

### Key Files

| Component | Location |
|-----------|----------|
| MEGA-QUERY | `/core/services/user/user_context_queries.py` |
| Context Builder | `/core/services/user/user_context_builder.py` |
| Domain Configs | `/core/services/relationships/domain_configs.py` |
| UnifiedRelationshipService | `/core/services/relationships/unified_relationship_service.py` |
| EntityType Enum | `/core/models/shared_enums.py` |

---

## Recent ADRs

| ADR | Title | Date |
|-----|-------|------|
| [ADR-016](decisions/ADR-016-context-builder-decomposition.md) | Context Builder Decomposition | December 2025 |
| [ADR-015](decisions/ADR-015-mega-query-rich-queries-completion.md) | MEGA-QUERY Rich Queries Completion | December 2025 |
| [ADR-014](decisions/ADR-014-unified-ingestion.md) | Unified Content Ingestion | December 2025 |
| [ADR-013](decisions/ADR-013-ku-uid-flat-identity.md) | KU UID Flat Identity | December 2025 |

See [decisions/](decisions/) for all 16 ADRs.

---

## Documentation Standards

### YAML Frontmatter

All markdown documents include:

```yaml
---
title: Document Title
updated: 2025-12-04
status: current
category: patterns
tags: [tag1, tag2]
related: [other_doc.md]
---
```

### Status Values

| Status | Meaning |
|--------|---------|
| `current` | Active, maintained |
| `active` | In use |
| `superseded` | Replaced by newer pattern |
| `archived` | Historical reference |

### File Naming Convention

**Purpose:** File names signal document scope and importance through casing.

| Casing | When to Use | Examples |
|--------|-------------|----------|
| **UPPERCASE** | Major reference docs, complete guides, architecture overviews | `FOURTEEN_DOMAIN_ARCHITECTURE.md`, `ERROR_HANDLING.md`, `SIMPLE_SEARCH_SETUP_GUIDE.md` |
| **lowercase** | Specific patterns, tactical guides, focused topics | `query_architecture.md`, `search_service_pattern.md`, `three_tier_type_system.md` |

**Directory Patterns:**
- `/architecture/` - Mostly UPPERCASE (major system design docs)
- `/guides/` - All UPPERCASE (comprehensive step-by-step guides)
- `/patterns/` - Mixed (UPPERCASE for major patterns, lowercase for specific implementations)
- `/reference/` - Mostly UPPERCASE (canonical references)

**Guidelines:**
- **UPPERCASE** signals: "This is a major reference document covering a broad topic"
- **lowercase** signals: "This is a focused implementation pattern or specific guide"
- Consistency within a category is more important than rigid rules
- When in doubt, match the predominant pattern in that directory

---

## Finding Information

### By Task

| Task | Start Here |
|------|------------|
| Add new domain | [FOURTEEN_DOMAIN_ARCHITECTURE.md](architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md) |
| Add relationships | [UNIFIED_RELATIONSHIP_SERVICE.md](patterns/UNIFIED_RELATIONSHIP_SERVICE.md) |
| Write Cypher queries | [query_architecture.md](patterns/query_architecture.md) |
| Handle errors | [ERROR_HANDLING.md](patterns/ERROR_HANDLING.md) |
| Create service | [service_creation.md](reference/templates/service_creation.md) |
| Understand UserContext | [UNIFIED_USER_ARCHITECTURE.md](architecture/UNIFIED_USER_ARCHITECTURE.md) |

### By Component

| Component | Documentation |
|-----------|---------------|
| Tasks | Part of 6 Activity Domains - see [domain_configs.py](../core/services/relationships/domain_configs.py) |
| Goals | Part of 6 Activity Domains |
| Habits | Part of 6 Activity Domains |
| Events | Part of 6 Activity Domains |
| Choices | Part of 6 Activity Domains |
| Principles | Part of 6 Activity Domains |
| KU/LS/LP/MOC | Curriculum domains - [CURRICULUM_GROUPING_PATTERNS.md](architecture/CURRICULUM_GROUPING_PATTERNS.md) |
| Finance | Standalone - NOT an Activity Domain |

---

## External Resources

- **Main Codebase:** `/home/mike/skuel/app/`
- **Infrastructure:** `/home/mike/infra/` (Neo4j and future services)
- **CLAUDE.md:** `/home/mike/skuel/app/CLAUDE.md`
- **FastHTML Docs:** `/home/mike/skuel/app/docs/fasthtml-llms.txt` (359KB)
- **DaisyUI Docs:** `/home/mike/skuel/app/docs/Daisyui_llms.txt` (62KB)

---

**See [INDEX.md](INDEX.md) for the complete document listing.**
