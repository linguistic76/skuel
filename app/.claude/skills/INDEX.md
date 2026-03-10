---
title: Claude Skills Index
updated: 2026-02-01
---

# SKUEL Claude Skills Index

> Quick navigation for all 28 project-specific Claude skills.

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
| [domain-route-config](domain-route-config/SKILL.md) | Configuration-driven route registration (4 variants) | fasthtml, python |

### UX Patterns (SKUEL-Specific)

| Skill | Purpose | Foundation |
|-------|---------|------------|
| [base-page-architecture](base-page-architecture/SKILL.md) | Consistent page layouts (STANDARD, HUB, CUSTOM) | fasthtml, daisyui, html-navigation |
| [ui-error-handling](ui-error-handling/SKILL.md) | Result[T] propagation to UI, error banners | result-pattern, fasthtml |
| [custom-sidebar-patterns](custom-sidebar-patterns/SKILL.md) | Collapsible sidebars (Profile Hub pattern) | base-page-architecture, js-alpine |
| [skuel-form-patterns](skuel-form-patterns/SKILL.md) | Three-tier validation, HTMX forms | daisyui, html-htmx, ui-error-handling |
| [accessibility-guide](accessibility-guide/SKILL.md) | WCAG 2.1 Level AA standards | All UX skills |
| [skuel-component-composition](skuel-component-composition/SKILL.md) | Reusable component composition | daisyui, tailwind-css, fasthtml |

### Database & Search

| Skill | Purpose | Foundation |
|-------|---------|------------|
| [neo4j-cypher-patterns](neo4j-cypher-patterns/SKILL.md) | Graph queries & relationships | None (base layer) |
| [neo4j-genai-plugin](neo4j-genai-plugin/SKILL.md) | AI-powered graph features (embeddings, vector search, RAG) | neo4j-cypher-patterns |
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

### Security

| Skill | Purpose | Foundation |
|-------|---------|------------|
| [security](security/SKILL.md) | Security posture, route checklist, code review checks | python |

### Observability

| Skill | Purpose | Foundation |
|-------|---------|------------|
| [prometheus-grafana](prometheus-grafana/SKILL.md) | Metrics collection & visualization | python, result-pattern |

### Visualization

| Skill | Purpose | Foundation |
|-------|---------|------------|
| [chartjs](chartjs/SKILL.md) | Data visualization | js-alpine |

---

## Full Inventory

| Skill | Files | Description |
|-------|-------|-------------|
| accessibility-guide | 1 | WCAG 2.1 Level AA accessibility standards (keyboard nav, ARIA, screen readers) |
| activity-domains | 4 | 6 Activity Domains: Tasks, Goals, Habits, Events, Choices, Principles |
| base-ai-service | 3 | BaseAIService pattern for optional AI features (LLM, embeddings) |
| base-analytics-service | 4 | BaseAnalyticsService pattern for 10 domain analytics services (no AI) |
| base-page-architecture | 1 | Consistent page layouts (STANDARD, HUB, CUSTOM) using BasePage |
| chartjs | 4 | Chart.js data visualization with Alpine.js state |
| curriculum-domains | 4 | 4 Curriculum Domains: KU, LS, LP, MOC (shared knowledge) |
| custom-sidebar-patterns | 1 | Collapsible sidebars, drawer navigation (Profile Hub pattern) |
| daisyui | 3 | DaisyUI semantic component library |
| domain-route-config | 3 | Configuration-driven route registration (Standard, API-only, UI-only, Multi-factory) |
| fasthtml | 4 | FastHTML Python framework patterns |
| html-htmx | 4 | Semantic HTML + HTMX hypermedia |
| html-navigation | 4 | Navigation components (navbar, sidebar, mobile) |
| js-alpine | 4 | Alpine.js client-side reactivity |
| monsterui | 3 | MonsterUI FastHTML components |
| neo4j-cypher-patterns | 3 | Cypher query patterns for graph database |
| neo4j-genai-plugin | 3 | Neo4j GenAI plugin integration (embeddings, vector search, RAG) |
| prometheus-grafana | 4 | Prometheus metrics + Grafana dashboards |
| pydantic | 3 | Pydantic validation & three-tier types |
| pytest | 4 | Testing patterns with Result[T] |
| python | 4 | Python development patterns |
| result-pattern | 2 | Result[T] error handling pattern |
| security | 1 | Security posture, route checklist, code review checks |
| skuel-component-composition | 1 | Reusable component composition (entity cards, stats grids, layouts) |
| skuel-form-patterns | 1 | Three-tier validation, accessible forms, HTMX submission |
| skuel-search-architecture | 1 | SearchRouter unified search |
| tailwind-css | 5 | Tailwind CSS utilities |
| ui-error-handling | 1 | Result[T] propagation to UI, error banners, pure computation helpers |
| user-context-intelligence | 4 | Central cross-domain intelligence hub (8 flagship methods) |

---

## Connection to /docs/

Key documentation links by topic:

| Topic | Documentation |
|-------|---------------|
| Activity Domains | `/docs/domains/tasks.md`, `goals.md`, `habits.md`, `events.md`, `choices.md`, `principles.md` |
| Curriculum Domains | `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md`, `/docs/intelligence/KU_INTELLIGENCE.md`, `LS_INTELLIGENCE.md`, `LP_INTELLIGENCE.md`, `MOC_INTELLIGENCE.md` |
| Intelligence Services | `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md`, `/docs/intelligence/USER_CONTEXT_INTELLIGENCE.md`, `/docs/decisions/ADR-030-analytics-vs-ai-separation.md` |
| UI/UX Patterns | `/docs/patterns/UI_COMPONENT_PATTERNS.md`, `/docs/migrations/PROFILE_HUB_MODERNIZATION_2026-02-01.md`, `/ui/layouts/base_page.py`, `/ui/profile/layout.py` |
| Error Handling | `/docs/patterns/ERROR_HANDLING.md` |
| Type System | `/docs/patterns/three_tier_type_system.md` |
| Query Architecture | `/docs/patterns/query_architecture.md` |
| Search Architecture | `/docs/architecture/SEARCH_ARCHITECTURE.md` |
| Protocol Architecture | `/docs/patterns/protocol_architecture.md` |
| Route Registration | `/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md` |
| Service Consolidation | `/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md` |
| GenAI Setup | `/docs/development/GENAI_SETUP.md`, `/docs/architecture/SEARCH_ARCHITECTURE.md` |

---

## Using Skills with Documentation

Skills provide **quick-start implementation guidance**. Documentation provides **architectural context and decision rationale**.

### Recommended Workflow

When working on a task, follow this pattern for maximum effectiveness:

1. **Start with skill** - Get patterns and quick reference for immediate implementation
   - Skills provide concrete code examples and decision trees
   - Focus on "how" - practical implementation steps
   - Example: `@fasthtml` shows route registration patterns

2. **Consult docs** - Understand "why" and architectural context
   - Architecture docs explain system design decisions
   - Pattern docs show the broader approach
   - Example: `/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md` explains the pattern philosophy

3. **Check ADRs** - Review historical decisions and alternatives considered
   - ADRs document the "why not" - alternatives we rejected
   - Shows evolution of patterns over time
   - Example: `ADR-020` explains why we chose decorator-based routes

4. **Return to skill** - Apply concrete implementation with full context
   - Use skill's code examples with architectural understanding
   - Make informed decisions about edge cases
   - Adapt patterns to your specific use case

### Finding Related Documentation

**Each skill has "Deep Dive Resources" section:**
- Links to architecture docs (system design)
- Links to pattern docs (implementation approaches)
- Links to ADRs (decision rationale)
- Links to migration docs (evolution history)

**Complete Cross-Reference Index:**
- See [CROSS_REFERENCE_INDEX.md](/docs/CROSS_REFERENCE_INDEX.md) for comprehensive skill ↔ doc mapping
- Organized by skill (find all docs for a skill)
- Organized by category (find all skills for a doc type)

**Quick Reference in CLAUDE.md:**
- See [CLAUDE.md](/CLAUDE.md#skills--documentation-cross-reference) for quick lookup table
- All 27 skills with primary documentation
- Organized by architectural layer

### Bidirectional Linking System

The cross-reference system works in both directions:

**Skills → Docs:**
- Skills metadata (`skills_metadata.yaml`) contains `primary_docs`, `patterns`, `related_adrs`
- Each skill's SKILL.md has "Deep Dive Resources" section
- Machine-readable and human-readable

**Docs → Skills:**
- Pattern docs have `related_skills` in YAML frontmatter
- Many docs have auto-generated "Related Skills" sections
- Some docs have manually curated "Quick Start" sections with skill references

**Validation:**
- Pre-commit hook prevents broken cross-references
- Validation script checks bidirectional consistency
- Currently: 100% bidirectional linking (36/36), 0 broken links

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
         |
         +---> domain-route-config (route wiring)
         |
         v
    +------------------------------------------+
    |         UX Patterns (SKUEL-Specific)     |
    +------------------------------------------+
         |
         +---> base-page-architecture (layouts)
         |           |
         |           +---> custom-sidebar-patterns (Profile Hub)
         |
         +---> ui-error-handling (Result[T] to UI)
         |
         +---> skuel-form-patterns (validation)
         |
         +---> skuel-component-composition (reusable)
         |
         +---> accessibility-guide (WCAG 2.1 AA)

Database/Search:
    neo4j-cypher-patterns
         |
         +---> neo4j-genai-plugin (embeddings, vector search, RAG)
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
       Tasks, Goals,       KU, LS, LP, MOC
       Habits, Events...
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
