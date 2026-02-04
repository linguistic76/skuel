# Cross-Reference Index: Skills ↔ Documentation

**Purpose:** Single source of truth for bidirectional skill-documentation mapping.

**Generated:** This file is auto-generated from `skills_metadata.yaml` and pattern doc frontmatter.
**Regenerate:** Run `poetry run python scripts/generate_cross_reference_index.py`

---

## By Skill

For each skill, this section shows all related documentation (architecture docs, patterns, ADRs).

### @accessibility-guide

**Description:** Expert guide for building accessible web applications following WCAG standards

**Patterns (Primary):**
- [HTMX_ACCESSIBILITY_PATTERNS.md](/docs/patterns/HTMX_ACCESSIBILITY_PATTERNS.md)
- [UI_COMPONENT_PATTERNS.md](/docs/patterns/UI_COMPONENT_PATTERNS.md)

### @activity-domains

**Description:** Activity domain patterns (Tasks, Goals, Habits, Events, Choices, Principles)

**Architecture:**
- [FOURTEEN_DOMAIN_ARCHITECTURE.md](/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md)

**Patterns (Primary):**
- [SERVICE_CONSOLIDATION_PATTERNS.md](/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md)

**Domain Docs:**
- [tasks.md](/docs/domains/tasks.md)
- [goals.md](/docs/domains/goals.md)
- [habits.md](/docs/domains/habits.md)

**Patterns (Additional):**
- [OWNERSHIP_VERIFICATION.md](/docs/patterns/OWNERSHIP_VERIFICATION.md)

### @base-ai-service

**Description:** BaseAIService for AI/LLM features (optional)

**Intelligence:**
- [INTELLIGENCE_SERVICES_INDEX.md](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md)

**ADRs:**
- [ADR-024](/docs/decisions/ADR-024.md)

### @base-analytics-service

**Description:** BaseAnalyticsService for domain analytics

**Intelligence:**
- [INTELLIGENCE_SERVICES_INDEX.md](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md)

**Patterns (Primary):**
- [SERVICE_CONSOLIDATION_PATTERNS.md](/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md)

**Patterns (Additional):**
- [CONFIGURATION_DRIVEN_SERVICE_ARCHITECTURE.md](/docs/patterns/CONFIGURATION_DRIVEN_SERVICE_ARCHITECTURE.md)
- [DOMAIN_LATERAL_SERVICE_QUICK_START.md](/docs/patterns/DOMAIN_LATERAL_SERVICE_QUICK_START.md)
- [RELATIONSHIP_HELPERS_EXAMPLE_SERVICE.md](/docs/patterns/RELATIONSHIP_HELPERS_EXAMPLE_SERVICE.md)
- [SERVICE_INTEGRATION_RELATIONSHIP_HELPERS.md](/docs/patterns/SERVICE_INTEGRATION_RELATIONSHIP_HELPERS.md)
- [STANDALONE_SERVICE_PATTERN.md](/docs/patterns/STANDALONE_SERVICE_PATTERN.md)
- [UNIFIED_RELATIONSHIP_SERVICE.md](/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md)
- [search_service_pattern.md](/docs/patterns/search_service_pattern.md)

**ADRs:**
- [ADR-024](/docs/decisions/ADR-024.md)
- [ADR-031](/docs/decisions/ADR-031.md)

### @base-page-architecture

**Description:** Expert guide for BasePage layout system and page types

**Patterns (Primary):**
- [UI_COMPONENT_PATTERNS.md](/docs/patterns/UI_COMPONENT_PATTERNS.md)

### @chartjs

**Description:** Chart.js data visualization in SKUEL

**Architecture:**
- [ADMIN_DASHBOARD_ARCHITECTURE.md](/docs/architecture/ADMIN_DASHBOARD_ARCHITECTURE.md)

### @curriculum-domains

**Description:** Curriculum domain patterns (KU, LS, LP)

**Architecture:**
- [CURRICULUM_GROUPING_PATTERNS.md](/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md)

**Domain Docs:**
- [ku.md](/docs/domains/ku.md)
- [ls.md](/docs/domains/ls.md)
- [lp.md](/docs/domains/lp.md)
- [moc.md](/docs/domains/moc.md)

**Patterns (Additional):**
- [OWNERSHIP_VERIFICATION.md](/docs/patterns/OWNERSHIP_VERIFICATION.md)

**ADRs:**
- [ADR-023](/docs/decisions/ADR-023.md)

### @custom-sidebar-patterns

**Description:** Expert guide for building custom sidebar navigation patterns

**Patterns (Primary):**
- [UI_COMPONENT_PATTERNS.md](/docs/patterns/UI_COMPONENT_PATTERNS.md)

### @daisyui

**Description:** DaisyUI component library

**Patterns (Primary):**
- [UI_COMPONENT_PATTERNS.md](/docs/patterns/UI_COMPONENT_PATTERNS.md)

### @docker

**Description:** SKUEL's Docker setup — the two-directory compose split, Dockerfile.production conventions, startup sequences, and local vs Droplet vs App Platform differences

**Deployment:**
- [DO_MIGRATION_GUIDE.md](/docs/deployment/DO_MIGRATION_GUIDE.md)
- [AURADB_MIGRATION_GUIDE.md](/docs/deployment/AURADB_MIGRATION_GUIDE.md)

**Development:**
- [GENAI_SETUP.md](/docs/development/GENAI_SETUP.md)

### @docs-skills-evolution

**Description:** How SKUEL's documentation and skills evolve in rhythm with the ecosystem

**Patterns (Primary):**
- [DOCSTRING_STANDARDS.md](/docs/patterns/DOCSTRING_STANDARDS.md)

**Other:**
- [ADR-TEMPLATE.md](/docs/decisions/ADR-TEMPLATE.md)

### @fasthtml

**Description:** FastHTML - Python's server-rendered hypermedia framework

**Patterns (Primary):**
- [FASTHTML_ROUTE_REGISTRATION.md](/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md)
- [FASTHTML_TYPE_HINTS_GUIDE.md](/docs/patterns/FASTHTML_TYPE_HINTS_GUIDE.md)
- [ROUTE_FACTORIES.md](/docs/patterns/ROUTE_FACTORIES.md)

**Patterns (Additional):**
- [DOMAIN_ROUTE_CONFIG_PATTERN.md](/docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md)
- [ROUTE_FACTORY_PATTERNS.md](/docs/patterns/ROUTE_FACTORY_PATTERNS.md)
- [ROUTE_NAMING_CONVENTION.md](/docs/patterns/ROUTE_NAMING_CONVENTION.md)

**ADRs:**
- [ADR-020](/docs/decisions/ADR-020.md)

### @html-htmx

**Description:** Semantic HTML and HTMX (HTTP-complete HTML)

**Patterns (Primary):**
- [UI_COMPONENT_PATTERNS.md](/docs/patterns/UI_COMPONENT_PATTERNS.md)

**Guides:**
- [HTMX_VERSION_STANDARDIZATION.md](/docs/guides/HTMX_VERSION_STANDARDIZATION.md)

**Patterns (Additional):**
- [FASTHTML_TYPE_HINTS_GUIDE.md](/docs/patterns/FASTHTML_TYPE_HINTS_GUIDE.md)
- [HTMX_ACCESSIBILITY_PATTERNS.md](/docs/patterns/HTMX_ACCESSIBILITY_PATTERNS.md)

### @html-navigation

**Description:** Building navigation components

**Patterns (Primary):**
- [UI_COMPONENT_PATTERNS.md](/docs/patterns/UI_COMPONENT_PATTERNS.md)

### @js-alpine

**Description:** Alpine.js - lightweight reactive JavaScript for HTML

**Architecture:**
- [ALPINE_JS_ARCHITECTURE.md](/docs/architecture/ALPINE_JS_ARCHITECTURE.md)

**Patterns (Primary):**
- [UI_COMPONENT_PATTERNS.md](/docs/patterns/UI_COMPONENT_PATTERNS.md)

### @neo4j-cypher-patterns

**Description:** Neo4j Cypher queries and SKUEL's graph patterns

**Architecture:**
- [NEO4J_DATABASE_ARCHITECTURE.md](/docs/architecture/NEO4J_DATABASE_ARCHITECTURE.md)

**Patterns (Primary):**
- [query_architecture.md](/docs/patterns/query_architecture.md)
- [GRAPH_ACCESS_PATTERNS.md](/docs/patterns/GRAPH_ACCESS_PATTERNS.md)
- [CYPHER_VS_APOC_STRATEGY.md](/docs/patterns/CYPHER_VS_APOC_STRATEGY.md)

**Patterns (Additional):**
- [CONTEXT_FIRST_RELATIONSHIP_PATTERN.md](/docs/patterns/CONTEXT_FIRST_RELATIONSHIP_PATTERN.md)
- [DOMAIN_RELATIONSHIPS_PATTERN.md](/docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md)
- [HIERARCHICAL_RELATIONSHIPS_PATTERN.md](/docs/patterns/HIERARCHICAL_RELATIONSHIPS_PATTERN.md)
- [LATERAL_RELATIONSHIPS_VISUALIZATION.md](/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md)
- [QUERY_PATTERNS.md](/docs/patterns/QUERY_PATTERNS.md)
- [RELATIONSHIP_HELPERS_EXAMPLE_SERVICE.md](/docs/patterns/RELATIONSHIP_HELPERS_EXAMPLE_SERVICE.md)
- [RELATIONSHIP_INFRASTRUCTURE_PATTERN.md](/docs/patterns/RELATIONSHIP_INFRASTRUCTURE_PATTERN.md)
- [SERVICE_INTEGRATION_RELATIONSHIP_HELPERS.md](/docs/patterns/SERVICE_INTEGRATION_RELATIONSHIP_HELPERS.md)
- [SKUEL_QUERY_USAGE_GUIDE.md](/docs/patterns/SKUEL_QUERY_USAGE_GUIDE.md)
- [UNIFIED_RELATIONSHIP_SERVICE.md](/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md)

**ADRs:**
- [ADR-037](/docs/decisions/ADR-037.md)

### @neo4j-genai-plugin

**Description:** Neo4j GenAI plugin integration for AI-powered graph features

**Other:**
- [GENAI_SETUP.md](/docs/development/GENAI_SETUP.md)
- [AURADB_MIGRATION_GUIDE.md](/docs/deployment/AURADB_MIGRATION_GUIDE.md)

**Patterns (Additional):**
- [search_service_pattern.md](/docs/patterns/search_service_pattern.md)

**ADRs:**
- [ADR-034](/docs/decisions/ADR-034.md)

### @prometheus-grafana

**Description:** Prometheus metrics and Grafana dashboards in SKUEL

**Other:**
- [README.md](/monitoring/README.md)
- [OBSERVABILITY_PHASE1_COMPLETE.md](/OBSERVABILITY_PHASE1_COMPLETE.md)

**Patterns (Additional):**
- [PERFORMANCE_MONITORING.md](/docs/patterns/PERFORMANCE_MONITORING.md)

**ADRs:**
- [ADR-036](/docs/decisions/ADR-036.md)

### @pydantic

**Description:** Pydantic V2 validation models

**Patterns (Primary):**
- [three_tier_type_system.md](/docs/patterns/three_tier_type_system.md)
- [API_VALIDATION_PATTERNS.md](/docs/patterns/API_VALIDATION_PATTERNS.md)

**Patterns (Additional):**
- [DOMAIN_PATTERNS_CATALOG.md](/docs/patterns/DOMAIN_PATTERNS_CATALOG.md)
- [PERFORMANCE_MONITORING.md](/docs/patterns/PERFORMANCE_MONITORING.md)

**ADRs:**
- [ADR-035](/docs/decisions/ADR-035.md)

### @pytest

**Description:** SKUEL testing patterns - fixtures, async testing, mocking with Result[T]

**Patterns (Primary):**
- [TESTING_PATTERNS.md](/docs/patterns/TESTING_PATTERNS.md)

**Other:**
- [TESTING.md](/TESTING.md)

**Patterns (Additional):**
- [GRAPH_ACCESS_PATTERNS.md](/docs/patterns/GRAPH_ACCESS_PATTERNS.md)
- [RELATIONSHIP_HELPERS_EXAMPLE_SERVICE.md](/docs/patterns/RELATIONSHIP_HELPERS_EXAMPLE_SERVICE.md)
- [SHARING_PATTERNS.md](/docs/patterns/SHARING_PATTERNS.md)

### @python

**Description:** Python development patterns in SKUEL

**Patterns (Primary):**
- [three_tier_type_system.md](/docs/patterns/three_tier_type_system.md)
- [ASYNC_SYNC_DESIGN_PATTERN.md](/docs/patterns/ASYNC_SYNC_DESIGN_PATTERN.md)
- [protocol_architecture.md](/docs/patterns/protocol_architecture.md)

**Patterns (Additional):**
- [DOCSTRING_STANDARDS.md](/docs/patterns/DOCSTRING_STANDARDS.md)
- [DOMAIN_PATTERNS_CATALOG.md](/docs/patterns/DOMAIN_PATTERNS_CATALOG.md)
- [PROTOCOL_LSP_COMPLIANCE.md](/docs/patterns/PROTOCOL_LSP_COMPLIANCE.md)
- [event_driven_architecture.md](/docs/patterns/event_driven_architecture.md)
- [linter_rules.md](/docs/patterns/linter_rules.md)

**ADRs:**
- [ADR-022](/docs/decisions/ADR-022.md)
- [ADR-035](/docs/decisions/ADR-035.md)

### @result-pattern

**Description:** Result[T] error handling pattern

**Patterns (Primary):**
- [ERROR_HANDLING.md](/docs/patterns/ERROR_HANDLING.md)
- [RETURN_TYPE_ERROR_PROPAGATION.md](/docs/patterns/RETURN_TYPE_ERROR_PROPAGATION.md)

**Patterns (Additional):**
- [error_handling_decorators.md](/docs/patterns/error_handling_decorators.md)
- [event_driven_architecture.md](/docs/patterns/event_driven_architecture.md)

**ADRs:**
- [ADR-022](/docs/decisions/ADR-022.md)

### @skuel-component-composition

**Description:** Expert guide for composing reusable UI components in SKUEL

**Patterns (Primary):**
- [UI_COMPONENT_PATTERNS.md](/docs/patterns/UI_COMPONENT_PATTERNS.md)

**Patterns (Additional):**
- [HIERARCHY_COMPONENTS_GUIDE.md](/docs/patterns/HIERARCHY_COMPONENTS_GUIDE.md)

### @skuel-form-patterns

**Description:** Expert guide for building accessible, validated forms in SKUEL

**Patterns (Primary):**
- [API_VALIDATION_PATTERNS.md](/docs/patterns/API_VALIDATION_PATTERNS.md)

**Patterns (Additional):**
- [PERFORMANCE_MONITORING.md](/docs/patterns/PERFORMANCE_MONITORING.md)

### @skuel-search-architecture

**Description:** SKUEL's unified search architecture and SearchRouter

**Architecture:**
- [SEARCH_ARCHITECTURE.md](/docs/architecture/SEARCH_ARCHITECTURE.md)

**Patterns (Primary):**
- [query_architecture.md](/docs/patterns/query_architecture.md)

**Other:**
- [SEARCH_SERVICE_METHODS.md](/docs/reference/SEARCH_SERVICE_METHODS.md)

**Patterns (Additional):**
- [search_service_pattern.md](/docs/patterns/search_service_pattern.md)

### @tailwind-css

**Description:** Utility-first CSS with Tailwind

**Patterns (Primary):**
- [UI_COMPONENT_PATTERNS.md](/docs/patterns/UI_COMPONENT_PATTERNS.md)

### @ui-error-handling

**Description:** Expert guide for UI error handling patterns and user feedback

**Patterns (Primary):**
- [ERROR_HANDLING.md](/docs/patterns/ERROR_HANDLING.md)

**Patterns (Additional):**
- [RETURN_TYPE_ERROR_PROPAGATION.md](/docs/patterns/RETURN_TYPE_ERROR_PROPAGATION.md)
- [error_handling_decorators.md](/docs/patterns/error_handling_decorators.md)

### @user-context-intelligence

**Description:** UserContextIntelligence - central cross-domain intelligence hub

**Architecture:**
- [UNIFIED_USER_ARCHITECTURE.md](/docs/architecture/UNIFIED_USER_ARCHITECTURE.md)

**Intelligence:**
- [USER_CONTEXT_INTELLIGENCE.md](/docs/intelligence/USER_CONTEXT_INTELLIGENCE.md)

**ADRs:**
- [ADR-030](/docs/decisions/ADR-030.md)

### @vis-network

**Description:** Expert guide to Vis.js Network for interactive graph visualization in SKUEL. Use when visualizing lateral relationships, building force-directed graphs, creating relationship network diagrams, or when the user mentions vis.js, graph visualization, relationship networks, interactive graphs, or lateral relationships.

**Architecture:**
- [LATERAL_RELATIONSHIPS_CORE.md](/docs/architecture/LATERAL_RELATIONSHIPS_CORE.md)

**Patterns (Primary):**
- [LATERAL_RELATIONSHIPS_VISUALIZATION.md](/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md)

**Patterns (Additional):**
- [LATERAL_RELATIONSHIPS_VISUALIZATION.md](/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md)

**ADRs:**
- [ADR-037](/docs/decisions/ADR-037.md)

---

## By Document Category

For each documentation category, this section shows which skills are relevant.

### Architecture Docs

- [ADMIN_DASHBOARD_ARCHITECTURE.md](/docs/architecture/ADMIN_DASHBOARD_ARCHITECTURE.md) → @chartjs
- [ALPINE_JS_ARCHITECTURE.md](/docs/architecture/ALPINE_JS_ARCHITECTURE.md) → @js-alpine
- [CURRICULUM_GROUPING_PATTERNS.md](/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md) → @curriculum-domains
- [FOURTEEN_DOMAIN_ARCHITECTURE.md](/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md) → @activity-domains
- [LATERAL_RELATIONSHIPS_CORE.md](/docs/architecture/LATERAL_RELATIONSHIPS_CORE.md) → @vis-network
- [NEO4J_DATABASE_ARCHITECTURE.md](/docs/architecture/NEO4J_DATABASE_ARCHITECTURE.md) → @neo4j-cypher-patterns
- [SEARCH_ARCHITECTURE.md](/docs/architecture/SEARCH_ARCHITECTURE.md) → @skuel-search-architecture
- [UNIFIED_USER_ARCHITECTURE.md](/docs/architecture/UNIFIED_USER_ARCHITECTURE.md) → @user-context-intelligence

### Intelligence Docs

- [INTELLIGENCE_SERVICES_INDEX.md](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md) → @base-ai-service, @base-analytics-service
- [USER_CONTEXT_INTELLIGENCE.md](/docs/intelligence/USER_CONTEXT_INTELLIGENCE.md) → @user-context-intelligence

### Pattern Docs

- [API_VALIDATION_PATTERNS.md](/docs/patterns/API_VALIDATION_PATTERNS.md) → @pydantic, @skuel-form-patterns
- [ASYNC_SYNC_DESIGN_PATTERN.md](/docs/patterns/ASYNC_SYNC_DESIGN_PATTERN.md) → @python
- [CONFIGURATION_DRIVEN_SERVICE_ARCHITECTURE.md](/docs/patterns/CONFIGURATION_DRIVEN_SERVICE_ARCHITECTURE.md) → @base-analytics-service
- [CONTEXT_FIRST_RELATIONSHIP_PATTERN.md](/docs/patterns/CONTEXT_FIRST_RELATIONSHIP_PATTERN.md) → @neo4j-cypher-patterns
- [CYPHER_VS_APOC_STRATEGY.md](/docs/patterns/CYPHER_VS_APOC_STRATEGY.md) → @neo4j-cypher-patterns
- [DOCSTRING_STANDARDS.md](/docs/patterns/DOCSTRING_STANDARDS.md) → @docs-skills-evolution, @python
- [DOMAIN_LATERAL_SERVICE_QUICK_START.md](/docs/patterns/DOMAIN_LATERAL_SERVICE_QUICK_START.md) → @base-analytics-service
- [DOMAIN_PATTERNS_CATALOG.md](/docs/patterns/DOMAIN_PATTERNS_CATALOG.md) → @pydantic, @python
- [DOMAIN_RELATIONSHIPS_PATTERN.md](/docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md) → @neo4j-cypher-patterns
- [DOMAIN_ROUTE_CONFIG_PATTERN.md](/docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md) → @fasthtml
- [ERROR_HANDLING.md](/docs/patterns/ERROR_HANDLING.md) → @result-pattern, @ui-error-handling
- [FASTHTML_ROUTE_REGISTRATION.md](/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md) → @fasthtml, @html-htmx
- [FASTHTML_TYPE_HINTS_GUIDE.md](/docs/patterns/FASTHTML_TYPE_HINTS_GUIDE.md) → @fasthtml, @html-htmx
- [GRAPH_ACCESS_PATTERNS.md](/docs/patterns/GRAPH_ACCESS_PATTERNS.md) → @neo4j-cypher-patterns, @pytest
- [HIERARCHICAL_RELATIONSHIPS_PATTERN.md](/docs/patterns/HIERARCHICAL_RELATIONSHIPS_PATTERN.md) → @neo4j-cypher-patterns
- [HIERARCHY_COMPONENTS_GUIDE.md](/docs/patterns/HIERARCHY_COMPONENTS_GUIDE.md) → @skuel-component-composition
- [HTMX_ACCESSIBILITY_PATTERNS.md](/docs/patterns/HTMX_ACCESSIBILITY_PATTERNS.md) → @accessibility-guide, @html-htmx
- [LATERAL_RELATIONSHIPS_VISUALIZATION.md](/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md) → @neo4j-cypher-patterns, @vis-network
- [OWNERSHIP_VERIFICATION.md](/docs/patterns/OWNERSHIP_VERIFICATION.md) → @activity-domains, @curriculum-domains
- [PERFORMANCE_MONITORING.md](/docs/patterns/PERFORMANCE_MONITORING.md) → @prometheus-grafana, @pydantic, @skuel-form-patterns
- [PROTOCOL_LSP_COMPLIANCE.md](/docs/patterns/PROTOCOL_LSP_COMPLIANCE.md) → @python
- [QUERY_PATTERNS.md](/docs/patterns/QUERY_PATTERNS.md) → @neo4j-cypher-patterns
- [RELATIONSHIP_HELPERS_EXAMPLE_SERVICE.md](/docs/patterns/RELATIONSHIP_HELPERS_EXAMPLE_SERVICE.md) → @base-analytics-service, @neo4j-cypher-patterns, @pytest
- [RELATIONSHIP_INFRASTRUCTURE_PATTERN.md](/docs/patterns/RELATIONSHIP_INFRASTRUCTURE_PATTERN.md) → @neo4j-cypher-patterns
- [RETURN_TYPE_ERROR_PROPAGATION.md](/docs/patterns/RETURN_TYPE_ERROR_PROPAGATION.md) → @result-pattern, @ui-error-handling
- [ROUTE_FACTORIES.md](/docs/patterns/ROUTE_FACTORIES.md) → @fasthtml
- [ROUTE_FACTORY_PATTERNS.md](/docs/patterns/ROUTE_FACTORY_PATTERNS.md) → @fasthtml
- [ROUTE_NAMING_CONVENTION.md](/docs/patterns/ROUTE_NAMING_CONVENTION.md) → @fasthtml
- [SERVICE_CONSOLIDATION_PATTERNS.md](/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md) → @activity-domains, @base-analytics-service
- [SERVICE_INTEGRATION_RELATIONSHIP_HELPERS.md](/docs/patterns/SERVICE_INTEGRATION_RELATIONSHIP_HELPERS.md) → @base-analytics-service, @neo4j-cypher-patterns
- [SHARING_PATTERNS.md](/docs/patterns/SHARING_PATTERNS.md) → @pytest
- [SKUEL_QUERY_USAGE_GUIDE.md](/docs/patterns/SKUEL_QUERY_USAGE_GUIDE.md) → @neo4j-cypher-patterns
- [STANDALONE_SERVICE_PATTERN.md](/docs/patterns/STANDALONE_SERVICE_PATTERN.md) → @base-analytics-service
- [TESTING_PATTERNS.md](/docs/patterns/TESTING_PATTERNS.md) → @pytest
- [UI_COMPONENT_PATTERNS.md](/docs/patterns/UI_COMPONENT_PATTERNS.md) → @accessibility-guide, @base-page-architecture, @custom-sidebar-patterns, @daisyui, @html-htmx, @html-navigation, @js-alpine, @skuel-component-composition, @tailwind-css
- [UNIFIED_RELATIONSHIP_SERVICE.md](/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md) → @base-analytics-service, @neo4j-cypher-patterns
- [error_handling_decorators.md](/docs/patterns/error_handling_decorators.md) → @result-pattern, @ui-error-handling
- [event_driven_architecture.md](/docs/patterns/event_driven_architecture.md) → @python, @result-pattern
- [linter_rules.md](/docs/patterns/linter_rules.md) → @python
- [protocol_architecture.md](/docs/patterns/protocol_architecture.md) → @python
- [query_architecture.md](/docs/patterns/query_architecture.md) → @neo4j-cypher-patterns, @skuel-search-architecture
- [search_service_pattern.md](/docs/patterns/search_service_pattern.md) → @base-analytics-service, @neo4j-genai-plugin, @skuel-search-architecture
- [three_tier_type_system.md](/docs/patterns/three_tier_type_system.md) → @pydantic, @python

### Deployment Docs

- [DO_MIGRATION_GUIDE.md](/docs/deployment/DO_MIGRATION_GUIDE.md) → @docker, @neo4j-genai-plugin
- [AURADB_MIGRATION_GUIDE.md](/docs/deployment/AURADB_MIGRATION_GUIDE.md) → @docker, @neo4j-genai-plugin
- [NEO4J_SETUP_MIGRATION_SUMMARY.md](/docs/deployment/NEO4J_SETUP_MIGRATION_SUMMARY.md) → @docker

### ADRs (Architecture Decision Records)

- [ADR-020](/docs/decisions/ADR-020.md) → @fasthtml
- [ADR-022](/docs/decisions/ADR-022.md) → @python, @result-pattern
- [ADR-023](/docs/decisions/ADR-023.md) → @curriculum-domains
- [ADR-024](/docs/decisions/ADR-024.md) → @base-ai-service, @base-analytics-service
- [ADR-030](/docs/decisions/ADR-030.md) → @user-context-intelligence
- [ADR-031](/docs/decisions/ADR-031.md) → @base-analytics-service
- [ADR-034](/docs/decisions/ADR-034.md) → @neo4j-genai-plugin
- [ADR-035](/docs/decisions/ADR-035.md) → @pydantic, @python
- [ADR-036](/docs/decisions/ADR-036.md) → @prometheus-grafana
- [ADR-037](/docs/decisions/ADR-037.md) → @neo4j-cypher-patterns, @vis-network

---

## Statistics

- **Total skills:** 29
- **Architecture docs:** 8 docs linked to skills
- **Intelligence docs:** 2 docs linked to skills
- **Pattern docs:** 43 docs linked to skills
- **ADRs:** 10 ADRs linked to skills

---

## Maintenance

**When to Update:**
- After adding a new skill
- After creating a new pattern doc
- After writing a new ADR
- After updating skills_metadata.yaml

**How to Update:**
```bash
poetry run python scripts/generate_cross_reference_index.py
```

**Related Files:**
- `.claude/skills/skills_metadata.yaml` - Machine-readable metadata
- `docs/patterns/*.md` - Pattern doc frontmatter
- `scripts/generate_cross_reference_index.py` - This generator script
