# Cross-Reference Index: Skills ↔ Documentation

**Purpose:** Single source of truth for bidirectional skill-documentation mapping.

**Generated:** This file is auto-generated from `skills_metadata.yaml` and pattern doc frontmatter.
**Regenerate:** Run `uv run python scripts/generate_cross_reference_index.py`

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
- [ENTITY_TYPE_ARCHITECTURE.md](/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md)

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
- [ADR-024](/docs/decisions/ADR-024-base-intelligence-service-migration.md)

### @base-analytics-service

**Description:** BaseAnalyticsService for domain analytics

**Intelligence:**
- [INTELLIGENCE_SERVICES_INDEX.md](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md)

**Patterns (Primary):**
- [SERVICE_CONSOLIDATION_PATTERNS.md](/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md)

**Patterns (Additional):**
- [CONFIGURATION_DRIVEN_SERVICE_ARCHITECTURE.md](/docs/patterns/CONFIGURATION_DRIVEN_SERVICE_ARCHITECTURE.md)
- [STANDALONE_SERVICE_PATTERN.md](/docs/patterns/STANDALONE_SERVICE_PATTERN.md)
- [UNIFIED_RELATIONSHIP_SERVICE.md](/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md)
- [search_service_pattern.md](/docs/patterns/search_service_pattern.md)

**ADRs:**
- [ADR-024](/docs/decisions/ADR-024-base-intelligence-service-migration.md)
- [ADR-031](/docs/decisions/ADR-031-baseservice-mixin-decomposition.md)

### @chartjs

**Description:** Chart.js data visualization in SKUEL

**Architecture:**
- [ADMIN_DASHBOARD_ARCHITECTURE.md](/docs/architecture/ADMIN_DASHBOARD_ARCHITECTURE.md)

### @curriculum-domains

**Description:** Curriculum domain patterns (KU, PS, LP)

**Architecture:**
- [CURRICULUM_GROUPING_PATTERNS.md](/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md)

**Domain Docs:**
- [ku.md](/docs/domains/ku.md)
- [ps.md](/docs/domains/ps.md)
- [lp.md](/docs/domains/lp.md)
- [moc.md](/docs/domains/moc.md)

**Patterns (Additional):**
- [OWNERSHIP_VERIFICATION.md](/docs/patterns/OWNERSHIP_VERIFICATION.md)

**ADRs:**
- [ADR-023](/docs/decisions/ADR-023-curriculum-baseservice-migration.md)

### @docker

**Description:** SKUEL's Docker setup — two-directory compose split, Dockerfile.production conventions, startup sequences, and local vs Droplet vs App Platform usage

*No documentation links yet.*

### @docs-skills-evolution

**Description:** How SKUEL's documentation and skills evolve in rhythm with the ecosystem

**Patterns (Primary):**
- [DOCSTRING_STANDARDS.md](/docs/patterns/DOCSTRING_STANDARDS.md)

**Other:**
- [ADR-TEMPLATE.md](/docs/decisions/ADR-TEMPLATE.md)

### @domain-route-config

**Description:** Configuration-driven route registration for *_routes.py files using DomainRouteConfig

**Patterns (Primary):**
- [DOMAIN_ROUTE_CONFIG_PATTERN.md](/docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md)

**Other:**
- [DOMAIN_ROUTE_CONFIG_MIGRATION_2026-02-03.md](/docs/migrations/DOMAIN_ROUTE_CONFIG_MIGRATION_2026-02-03.md)

**Patterns (Additional):**
- [ROUTE_FACTORIES.md](/docs/patterns/ROUTE_FACTORIES.md)
- [FASTHTML_ROUTE_REGISTRATION.md](/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md)

**ADRs:**
- [ADR-020](/docs/decisions/ADR-020-fasthtml-route-registration-pattern.md)

### @fasthtml

**Description:** FastHTML - Python's server-rendered hypermedia framework

**Patterns (Primary):**
- [FASTHTML_ROUTE_REGISTRATION.md](/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md)
- [FASTHTML_TYPE_HINTS_GUIDE.md](/docs/patterns/FASTHTML_TYPE_HINTS_GUIDE.md)
- [ROUTE_FACTORIES.md](/docs/patterns/ROUTE_FACTORIES.md)

**Patterns (Additional):**
- [DOMAIN_ROUTE_CONFIG_PATTERN.md](/docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md)
- [ROUTE_FACTORIES.md](/docs/patterns/ROUTE_FACTORIES.md)
- [ROUTE_NAMING_CONVENTION.md](/docs/patterns/ROUTE_NAMING_CONVENTION.md)

**ADRs:**
- [ADR-020](/docs/decisions/ADR-020-fasthtml-route-registration-pattern.md)

### @journals

**Description:** Implementation guide for Journals domain — STANDARD/FOUNDER tiers, DNWF stages, JournalService, instruction_loader, EnrichmentMode distinction

**Architecture:**
- [JOURNALS_DOMAIN_ARCHITECTURE.md](/docs/architecture/JOURNALS_DOMAIN_ARCHITECTURE.md)

**ADRs:**
- [ADR-003](/docs/decisions/ADR-003-journals-service-query.md)
- [ADR-054](/docs/decisions/ADR-054-user-entry-unified-submissions.md)

### @learning-loop

**Description:** SKUEL's Learning Loop — the development lens for PathStep, Exercise, UserEntry, Report, RevisedExercise, Interaction; every feature must strengthen a loop phase

**Architecture:**
- [LEARNING_LOOP_ARCHITECTURE.md](/docs/architecture/LEARNING_LOOP_ARCHITECTURE.md)

### @neo4j-cypher-patterns

**Description:** Neo4j Cypher queries and SKUEL's graph patterns

**Patterns (Primary):**
- [query_architecture.md](/docs/patterns/query_architecture.md)
- [GRAPH_ACCESS_PATTERNS.md](/docs/patterns/GRAPH_ACCESS_PATTERNS.md)
- [CYPHER_VS_APOC_STRATEGY.md](/docs/patterns/CYPHER_VS_APOC_STRATEGY.md)

**Patterns (Additional):**
- [CONTEXT_FIRST_RELATIONSHIP_PATTERN.md](/docs/patterns/CONTEXT_FIRST_RELATIONSHIP_PATTERN.md)
- [LATERAL_RELATIONSHIPS_VISUALIZATION.md](/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md)
- [QUERY_PATTERNS.md](/docs/patterns/QUERY_PATTERNS.md)
- [UNIFIED_RELATIONSHIP_SERVICE.md](/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md)

**ADRs:**
- [ADR-037](/docs/decisions/ADR-037-lateral-relationships-visualization-phase5.md)

### @prometheus-grafana

**Description:** Prometheus metrics and Grafana dashboards in SKUEL

**Other:**
- [README.md](/monitoring/README.md)

**Patterns (Additional):**
- [PERFORMANCE_MONITORING.md](/docs/patterns/PERFORMANCE_MONITORING.md)

**ADRs:**
- [ADR-036](/docs/decisions/ADR-036-prometheus-primary-cache-pattern.md)

### @prompt-templates

**Description:** SKUEL's centralized LLM prompt template registry (PROMPT_REGISTRY) connecting services to templates

*No documentation links yet.*

### @pwa

**Description:** Progressive Web App — service worker, manifest, offline support, caching strategies

**Architecture:**
- [PWA_ARCHITECTURE.md](/docs/architecture/PWA_ARCHITECTURE.md)

**ADRs:**
- [ADR-050](/docs/decisions/ADR-050-pwa-mobile-strategy.md)

### @pydantic

**Description:** Pydantic V2 validation models

**Patterns (Primary):**
- [three_tier_type_system.md](/docs/patterns/three_tier_type_system.md)
- [API_VALIDATION_PATTERNS.md](/docs/patterns/API_VALIDATION_PATTERNS.md)

**Patterns (Additional):**
- [DOMAIN_PATTERNS_CATALOG.md](/docs/patterns/DOMAIN_PATTERNS_CATALOG.md)
- [PERFORMANCE_MONITORING.md](/docs/patterns/PERFORMANCE_MONITORING.md)

**ADRs:**
- [ADR-035](/docs/decisions/ADR-035-tier-selection-guidelines.md)

### @pytest

**Description:** SKUEL testing patterns - fixtures, async testing, mocking with Result[T]

**Patterns (Primary):**
- [TESTING_PATTERNS.md](/docs/patterns/TESTING_PATTERNS.md)

**Other:**
- [TESTING.md](/TESTING.md)

**Patterns (Additional):**
- [GRAPH_ACCESS_PATTERNS.md](/docs/patterns/GRAPH_ACCESS_PATTERNS.md)
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
- [ADR-022](/docs/decisions/ADR-022-graph-native-authentication.md)
- [ADR-035](/docs/decisions/ADR-035-tier-selection-guidelines.md)

### @result-pattern

**Description:** Result[T] error handling pattern

**Patterns (Primary):**
- [ERROR_HANDLING.md](/docs/patterns/ERROR_HANDLING.md)
- [RETURN_TYPE_ERROR_PROPAGATION.md](/docs/patterns/RETURN_TYPE_ERROR_PROPAGATION.md)

**Patterns (Additional):**
- [error_handling_decorators.md](/docs/patterns/error_handling_decorators.md)
- [event_driven_architecture.md](/docs/patterns/event_driven_architecture.md)

**ADRs:**
- [ADR-022](/docs/decisions/ADR-022-graph-native-authentication.md)

### @security

**Description:** Security posture, route checklist, and code review security checks

**Patterns (Primary):**
- [AUTH_PATTERNS.md](/docs/patterns/AUTH_PATTERNS.md)
- [OWNERSHIP_VERIFICATION.md](/docs/patterns/OWNERSHIP_VERIFICATION.md)

**Other:**
- [ROUTE_AUTH_REQUIREMENTS.md](/docs/security/ROUTE_AUTH_REQUIREMENTS.md)

**Patterns (Additional):**
- [ERROR_HANDLING.md](/docs/patterns/ERROR_HANDLING.md)

**ADRs:**
- [ADR-022](/docs/decisions/ADR-022-graph-native-authentication.md)

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

### @skuel-ui

**Description:** SKUEL UI patterns — BasePage, components, navigation, sidebars, forms (self-contained)

**Patterns (Primary):**
- [UI_COMPONENT_PATTERNS.md](/docs/patterns/UI_COMPONENT_PATTERNS.md)

**Patterns (Additional):**
- [HIERARCHY_COMPONENTS_GUIDE.md](/docs/patterns/HIERARCHY_COMPONENTS_GUIDE.md)
- [API_VALIDATION_PATTERNS.md](/docs/patterns/API_VALIDATION_PATTERNS.md)

### @ui-browser

**Description:** SKUEL browser interactivity — HTMX for server communication + Alpine.js for client-side state

**Architecture:**
- [ALPINE_JS_ARCHITECTURE.md](/docs/architecture/ALPINE_JS_ARCHITECTURE.md)

**Patterns (Primary):**
- [UI_COMPONENT_PATTERNS.md](/docs/patterns/UI_COMPONENT_PATTERNS.md)
- [HTMX_ACCESSIBILITY_PATTERNS.md](/docs/patterns/HTMX_ACCESSIBILITY_PATTERNS.md)

**Patterns (Additional):**
- [FASTHTML_TYPE_HINTS_GUIDE.md](/docs/patterns/FASTHTML_TYPE_HINTS_GUIDE.md)
- [HTMX_ACCESSIBILITY_PATTERNS.md](/docs/patterns/HTMX_ACCESSIBILITY_PATTERNS.md)

### @ui-css

**Description:** SKUEL CSS layer — Tailwind + ui.components (SKUEL-owned pure-Tailwind layer, ADR-071)

**Patterns (Primary):**
- [UI_COMPONENT_PATTERNS.md](/docs/patterns/UI_COMPONENT_PATTERNS.md)

### @ui-error-handling

**Description:** Expert guide for UI error handling patterns and user feedback

**Patterns (Primary):**
- [ERROR_HANDLING.md](/docs/patterns/ERROR_HANDLING.md)

**Patterns (Additional):**
- [RETURN_TYPE_ERROR_PROPAGATION.md](/docs/patterns/RETURN_TYPE_ERROR_PROPAGATION.md)
- [error_handling_decorators.md](/docs/patterns/error_handling_decorators.md)

### @ui-orchestrator

**Description:** Creating and wiring a UI Orchestrator to resolve Dependency Gravity in Hub pages

**Patterns (Primary):**
- [HUB_PAGE_PATTERN.md](/docs/patterns/HUB_PAGE_PATTERN.md)

### @user-context-intelligence

**Description:** UserContextIntelligence - central cross-domain intelligence hub

**Architecture:**
- [UNIFIED_USER_ARCHITECTURE.md](/docs/architecture/UNIFIED_USER_ARCHITECTURE.md)

**Intelligence:**
- [USER_CONTEXT_INTELLIGENCE.md](/docs/intelligence/USER_CONTEXT_INTELLIGENCE.md)

**ADRs:**
- [ADR-030](/docs/decisions/ADR-030-usercontext-file-consolidation.md)

### @vis-network

**Description:** Expert guide to Vis.js Network for interactive graph visualization in SKUEL. Use when visualizing lateral relationships, building force-directed graphs, creating relationship network diagrams, or when the user mentions vis.js, graph visualization, relationship networks, interactive graphs, or lateral relationships.

**Architecture:**
- [RELATIONSHIPS_ARCHITECTURE.md](/docs/architecture/RELATIONSHIPS_ARCHITECTURE.md)

**Patterns (Primary):**
- [LATERAL_RELATIONSHIPS_VISUALIZATION.md](/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md)

**Patterns (Additional):**
- [LATERAL_RELATIONSHIPS_VISUALIZATION.md](/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md)

**ADRs:**
- [ADR-037](/docs/decisions/ADR-037-lateral-relationships-visualization-phase5.md)

### @zpd

**Description:** SKUEL's Zone of Proximal Development — readiness scoring, blocking gaps, compound evidence, recommended actions, ZPD snapshots (the pedagogical gravity well)

**Other:**
- [zpd.md](/docs/user-guides/zpd.md)

---

## By Document Category

For each documentation category, this section shows which skills are relevant.

### Architecture Docs

- [ADMIN_DASHBOARD_ARCHITECTURE.md](/docs/architecture/ADMIN_DASHBOARD_ARCHITECTURE.md) → @chartjs
- [ALPINE_JS_ARCHITECTURE.md](/docs/architecture/ALPINE_JS_ARCHITECTURE.md) → @ui-browser
- [CURRICULUM_GROUPING_PATTERNS.md](/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md) → @curriculum-domains
- [ENTITY_TYPE_ARCHITECTURE.md](/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md) → @activity-domains
- [JOURNALS_DOMAIN_ARCHITECTURE.md](/docs/architecture/JOURNALS_DOMAIN_ARCHITECTURE.md) → @journals
- [LEARNING_LOOP_ARCHITECTURE.md](/docs/architecture/LEARNING_LOOP_ARCHITECTURE.md) → @learning-loop
- [PWA_ARCHITECTURE.md](/docs/architecture/PWA_ARCHITECTURE.md) → @pwa
- [RELATIONSHIPS_ARCHITECTURE.md](/docs/architecture/RELATIONSHIPS_ARCHITECTURE.md) → @vis-network
- [SEARCH_ARCHITECTURE.md](/docs/architecture/SEARCH_ARCHITECTURE.md) → @skuel-search-architecture
- [UNIFIED_USER_ARCHITECTURE.md](/docs/architecture/UNIFIED_USER_ARCHITECTURE.md) → @user-context-intelligence

### Intelligence Docs

- [INTELLIGENCE_SERVICES_INDEX.md](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md) → @base-ai-service, @base-analytics-service
- [USER_CONTEXT_INTELLIGENCE.md](/docs/intelligence/USER_CONTEXT_INTELLIGENCE.md) → @user-context-intelligence

### Pattern Docs

- [API_VALIDATION_PATTERNS.md](/docs/patterns/API_VALIDATION_PATTERNS.md) → @pydantic, @skuel-ui
- [ASYNC_SYNC_DESIGN_PATTERN.md](/docs/patterns/ASYNC_SYNC_DESIGN_PATTERN.md) → @python
- [AUTH_PATTERNS.md](/docs/patterns/AUTH_PATTERNS.md) → @security
- [CONFIGURATION_DRIVEN_SERVICE_ARCHITECTURE.md](/docs/patterns/CONFIGURATION_DRIVEN_SERVICE_ARCHITECTURE.md) → @base-analytics-service
- [CONTEXT_FIRST_RELATIONSHIP_PATTERN.md](/docs/patterns/CONTEXT_FIRST_RELATIONSHIP_PATTERN.md) → @neo4j-cypher-patterns, @user-context-intelligence
- [CYPHER_VS_APOC_STRATEGY.md](/docs/patterns/CYPHER_VS_APOC_STRATEGY.md) → @neo4j-cypher-patterns
- [DOCSTRING_STANDARDS.md](/docs/patterns/DOCSTRING_STANDARDS.md) → @docs-skills-evolution, @python
- [DOMAIN_PATTERNS_CATALOG.md](/docs/patterns/DOMAIN_PATTERNS_CATALOG.md) → @pydantic, @python
- [DOMAIN_ROUTE_CONFIG_PATTERN.md](/docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md) → @domain-route-config, @fasthtml
- [ERROR_HANDLING.md](/docs/patterns/ERROR_HANDLING.md) → @result-pattern, @security, @ui-error-handling
- [FASTHTML_ROUTE_REGISTRATION.md](/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md) → @domain-route-config, @fasthtml, @ui-browser
- [FASTHTML_TYPE_HINTS_GUIDE.md](/docs/patterns/FASTHTML_TYPE_HINTS_GUIDE.md) → @fasthtml, @ui-browser
- [GRAPH_ACCESS_PATTERNS.md](/docs/patterns/GRAPH_ACCESS_PATTERNS.md) → @neo4j-cypher-patterns, @pytest
- [HIERARCHY_COMPONENTS_GUIDE.md](/docs/patterns/HIERARCHY_COMPONENTS_GUIDE.md) → @skuel-ui
- [HTMX_ACCESSIBILITY_PATTERNS.md](/docs/patterns/HTMX_ACCESSIBILITY_PATTERNS.md) → @accessibility-guide, @ui-browser
- [HUB_PAGE_PATTERN.md](/docs/patterns/HUB_PAGE_PATTERN.md) → @ui-orchestrator
- [KNOWLEDGE_APPLICATION_TRACKING.md](/docs/patterns/KNOWLEDGE_APPLICATION_TRACKING.md) → @activity-domains, @learning-loop, @neo4j-cypher-patterns
- [LATERAL_RELATIONSHIPS_VISUALIZATION.md](/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md) → @neo4j-cypher-patterns, @vis-network
- [MYPY_TYPE_SAFETY_PATTERNS.md](/docs/patterns/MYPY_TYPE_SAFETY_PATTERNS.md) → @python
- [OWNERSHIP_VERIFICATION.md](/docs/patterns/OWNERSHIP_VERIFICATION.md) → @activity-domains, @curriculum-domains, @security
- [PERFORMANCE_MONITORING.md](/docs/patterns/PERFORMANCE_MONITORING.md) → @prometheus-grafana, @pydantic, @skuel-ui
- [PROTOCOL_LSP_COMPLIANCE.md](/docs/patterns/PROTOCOL_LSP_COMPLIANCE.md) → @python
- [QUERY_PATTERNS.md](/docs/patterns/QUERY_PATTERNS.md) → @neo4j-cypher-patterns
- [RETURN_TYPE_ERROR_PROPAGATION.md](/docs/patterns/RETURN_TYPE_ERROR_PROPAGATION.md) → @result-pattern, @ui-error-handling
- [ROUTE_DECORATOR_ARCHITECTURE.md](/docs/patterns/ROUTE_DECORATOR_ARCHITECTURE.md) → @domain-route-config, @fasthtml, @result-pattern
- [ROUTE_FACTORIES.md](/docs/patterns/ROUTE_FACTORIES.md) → @domain-route-config, @fasthtml
- [ROUTE_NAMING_CONVENTION.md](/docs/patterns/ROUTE_NAMING_CONVENTION.md) → @fasthtml
- [SERVICE_CONSOLIDATION_PATTERNS.md](/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md) → @activity-domains, @base-analytics-service
- [SERVICE_DOCSTRING_STYLE.md](/docs/patterns/SERVICE_DOCSTRING_STYLE.md) → @python
- [SHARING_PATTERNS.md](/docs/patterns/SHARING_PATTERNS.md) → @pytest
- [STANDALONE_SERVICE_PATTERN.md](/docs/patterns/STANDALONE_SERVICE_PATTERN.md) → @base-analytics-service
- [TESTING_PATTERNS.md](/docs/patterns/TESTING_PATTERNS.md) → @pytest
- [UI_COMPONENT_PATTERNS.md](/docs/patterns/UI_COMPONENT_PATTERNS.md) → @accessibility-guide, @skuel-ui, @ui-browser, @ui-css
- [UI_ORCHESTRATOR_PATTERN.md](/docs/patterns/UI_ORCHESTRATOR_PATTERN.md) → @fasthtml, @ui-orchestrator
- [UNIFIED_RELATIONSHIP_SERVICE.md](/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md) → @base-analytics-service, @neo4j-cypher-patterns
- [error_handling_decorators.md](/docs/patterns/error_handling_decorators.md) → @result-pattern, @ui-error-handling
- [event_driven_architecture.md](/docs/patterns/event_driven_architecture.md) → @python, @result-pattern
- [linter_rules.md](/docs/patterns/linter_rules.md) → @python
- [protocol_architecture.md](/docs/patterns/protocol_architecture.md) → @python
- [query_architecture.md](/docs/patterns/query_architecture.md) → @neo4j-cypher-patterns, @skuel-search-architecture
- [search_service_pattern.md](/docs/patterns/search_service_pattern.md) → @base-analytics-service, @skuel-search-architecture
- [three_tier_type_system.md](/docs/patterns/three_tier_type_system.md) → @pydantic, @python

### ADRs (Architecture Decision Records)

- [ADR-003](/docs/decisions/ADR-003-journals-service-query.md) → @journals
- [ADR-020](/docs/decisions/ADR-020-fasthtml-route-registration-pattern.md) → @domain-route-config, @fasthtml
- [ADR-022](/docs/decisions/ADR-022-graph-native-authentication.md) → @python, @result-pattern, @security
- [ADR-023](/docs/decisions/ADR-023-curriculum-baseservice-migration.md) → @curriculum-domains
- [ADR-024](/docs/decisions/ADR-024-base-intelligence-service-migration.md) → @base-ai-service, @base-analytics-service
- [ADR-030](/docs/decisions/ADR-030-usercontext-file-consolidation.md) → @user-context-intelligence
- [ADR-031](/docs/decisions/ADR-031-baseservice-mixin-decomposition.md) → @base-analytics-service
- [ADR-035](/docs/decisions/ADR-035-tier-selection-guidelines.md) → @pydantic, @python
- [ADR-036](/docs/decisions/ADR-036-prometheus-primary-cache-pattern.md) → @prometheus-grafana
- [ADR-037](/docs/decisions/ADR-037-lateral-relationships-visualization-phase5.md) → @neo4j-cypher-patterns, @vis-network
- [ADR-050](/docs/decisions/ADR-050-pwa-mobile-strategy.md) → @pwa
- [ADR-054](/docs/decisions/ADR-054-user-entry-unified-submissions.md) → @journals

---

## Statistics

- **Total skills:** 30
- **Architecture docs:** 10 docs linked to skills
- **Intelligence docs:** 2 docs linked to skills
- **Pattern docs:** 42 docs linked to skills
- **ADRs:** 12 ADRs linked to skills

---

## Maintenance

**When to Update:**
- After adding a new skill
- After creating a new pattern doc
- After writing a new ADR
- After updating skills_metadata.yaml

**How to Update:**
```bash
uv run python scripts/generate_cross_reference_index.py
```

**Related Files:**
- `.claude/skills/skills_metadata.yaml` - Machine-readable metadata
- `docs/patterns/*.md` - Pattern doc frontmatter
- `scripts/generate_cross_reference_index.py` - This generator script
