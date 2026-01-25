---
title: Claude Skills Index
updated: 2026-01-17
---

# SKUEL Claude Skills Index

> Quick navigation for all 20 project-specific Claude skills.

## Skill Stacks

### CSS/Styling Layer (Progressive Abstraction)

| Skill | Purpose | Foundation |
|-------|---------|------------|
| [tailwind-css](tailwind-css/SKILL.md) | Utility-first CSS | None (base layer) |
| [daisyui](daisyui/SKILL.md) | Semantic CSS components | tailwind-css |
| [monsterui](monsterui/SKILL.md) | FastHTML component library | daisyui, tailwind-css |

### Core Python Stack

| Skill | Purpose | Foundation |
|-------|---------|------------|
| [python](python/SKILL.md) | Python patterns, type hints, protocols | None (base layer) |
| [result-pattern](result-pattern/SKILL.md) | Result[T] error handling | python |
| [pydantic](pydantic/SKILL.md) | Validation & serialization | python |
| [pytest](pytest/SKILL.md) | Testing patterns | python, result-pattern |

### Frontend/Web Stack

| Skill | Purpose | Foundation |
|-------|---------|------------|
| [html-htmx](html-htmx/SKILL.md) | Hypermedia & server communication | None (base layer) |
| [js-alpine](js-alpine/SKILL.md) | Client-side reactivity | html-htmx |
| [html-navigation](html-navigation/SKILL.md) | Navigation components (navbar, sidebar, mobile) | html-htmx, js-alpine |
| [fasthtml](fasthtml/SKILL.md) | Python server-rendered framework | html-htmx, monsterui |

### Database & Search

| Skill | Purpose | Foundation |
|-------|---------|------------|
| [neo4j-cypher-patterns](neo4j-cypher-patterns/SKILL.md) | Graph queries & relationships | None (base layer) |
| [skuel-search-architecture](skuel-search-architecture/SKILL.md) | Unified search routing | neo4j-cypher-patterns |

### SKUEL Architecture

| Skill | Purpose | Foundation |
|-------|---------|------------|
| [activity-domains](activity-domains/SKILL.md) | Tasks, Goals, Habits, Events, Choices, Principles | python, result-pattern, neo4j-cypher-patterns |
| [curriculum-domains](curriculum-domains/SKILL.md) | KU, LS, LP, MOC (shared knowledge content) | python, result-pattern, neo4j-cypher-patterns |

### Intelligence Layer

| Skill | Purpose | Foundation |
|-------|---------|------------|
| [base-analytics-service](base-analytics-service/SKILL.md) | Domain analytics services (10 services, no AI) | python, result-pattern |
| [base-ai-service](base-ai-service/SKILL.md) | AI-powered features (optional LLM/embeddings) | base-analytics-service |
| [user-context-intelligence](user-context-intelligence/SKILL.md) | Central cross-domain intelligence hub (8 methods) | base-analytics-service, activity-domains, curriculum-domains |

### Visualization

| Skill | Purpose | Foundation |
|-------|---------|------------|
| [chartjs](chartjs/SKILL.md) | Data visualization | js-alpine |

---

## Full Inventory

| Skill | Files | Description |
|-------|-------|-------------|
| activity-domains | 4 | 6 Activity Domains: Tasks, Goals, Habits, Events, Choices, Principles |
| base-ai-service | 3 | BaseAIService pattern for optional AI features (LLM, embeddings) |
| base-analytics-service | 4 | BaseAnalyticsService pattern for 10 domain analytics services (no AI) |
| chartjs | 4 | Chart.js data visualization with Alpine.js state |
| curriculum-domains | 4 | 4 Curriculum Domains: KU, LS, LP, MOC (shared knowledge) |
| daisyui | 3 | DaisyUI semantic component library |
| fasthtml | 4 | FastHTML Python framework patterns |
| html-htmx | 4 | Semantic HTML + HTMX hypermedia |
| html-navigation | 4 | Navigation components (navbar, sidebar, mobile) |
| js-alpine | 4 | Alpine.js client-side reactivity |
| monsterui | 3 | MonsterUI FastHTML components |
| neo4j-cypher-patterns | 3 | Cypher query patterns for graph database |
| pydantic | 3 | Pydantic validation & three-tier types |
| pytest | 4 | Testing patterns with Result[T] |
| python | 4 | Python development patterns |
| result-pattern | 2 | Result[T] error handling pattern |
| skuel-search-architecture | 1 | SearchRouter unified search |
| tailwind-css | 5 | Tailwind CSS utilities |
| user-context-intelligence | 4 | Central cross-domain intelligence hub (8 flagship methods) |

---

## Connection to /docs/

Key documentation links by topic:

| Topic | Documentation |
|-------|---------------|
| Activity Domains | `/docs/domains/tasks.md`, `goals.md`, `habits.md`, `events.md`, `choices.md`, `principles.md` |
| Curriculum Domains | `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md`, `/docs/intelligence/KU_INTELLIGENCE.md`, `LS_INTELLIGENCE.md`, `LP_INTELLIGENCE.md`, `MOC_INTELLIGENCE.md` |
| Intelligence Services | `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md`, `/docs/intelligence/USER_CONTEXT_INTELLIGENCE.md`, `/docs/decisions/ADR-030-analytics-vs-ai-separation.md` |
| Error Handling | `/docs/patterns/ERROR_HANDLING.md` |
| Type System | `/docs/patterns/three_tier_type_system.md` |
| Query Architecture | `/docs/patterns/query_architecture.md` |
| Search Architecture | `/docs/architecture/SEARCH_ARCHITECTURE.md` |
| Protocol Architecture | `/docs/patterns/protocol_architecture.md` |
| Route Registration | `/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md` |
| Service Consolidation | `/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md` |

---

## Skill Relationships Diagram

```
CSS/Styling Layer:
    tailwind-css (utilities)
         |
         v
    daisyui (semantic)
         |
         v
    monsterui (FastHTML-native)

Core Python:
    python (patterns)
      |
      +---> result-pattern (errors)
      |           |
      +---> pydantic (validation)
      |
      +---> pytest (testing) <--- result-pattern

Frontend/Web:
    html-htmx (server comm)
         |
         v
    js-alpine (client state)
         |
         +---> html-navigation (navbar, sidebar)
         |
         v
    fasthtml (Python framework) <--- monsterui

Database/Search:
    neo4j-cypher-patterns
         |
         v
    skuel-search-architecture

SKUEL Architecture (domains + intelligence):

    python + result-pattern + neo4j-cypher-patterns
                        |
                        v
              +------------------+
              |  Domain Skills   |
              +------------------+
              |                  |
              v                  v
       activity-domains    curriculum-domains
       (6 user-owned)      (4 shared content)
       Tasks, Goals...     KU, LS, LP, MOC
              |                  |
              +--------+---------+
                       |
                       v
          +------------------------+
          |  Intelligence Layer    |
          +------------------------+
                       |
                       v
          base-analytics-service
            (10 domains, no AI)
                       |
          +------------+------------+
          |                         |
          v                         v
  base-ai-service          user-context-
  (optional LLM/           intelligence
   embeddings)              (8 methods)

Visualization:
    js-alpine ---> chartjs
```
