---
title: Documentation Index
updated: 2026-03-03
status: current
category: index
tags: [index, navigation, documentation]
related: []
---

# SKUEL Documentation Index

> **⚠️ SINGLE SOURCE OF TRUTH:** All technical documentation lives in `/home/mike/skuel/app/docs/`
>
> `/home/mike/0bsidian/skuel/docs/` contains **content** (KU docs), NOT technical documentation.

*Generated: 2025-12-07*
*Updated: 2026-03-03*
*Total: ~200 documents*

> **📝 Documentation Standards:**
> - **File Naming:** UPPERCASE for major reference docs/guides, lowercase for specific patterns
> - **Full Standards:** See [README.md](README.md#documentation-standards)

## Quick Links

- [Domains](#domains) - Entity type architecture documentation
- [Architecture](#architecture) - System design and domain structure
- [Patterns](#patterns) - Implementation patterns and coding standards
- [DSL](#dsl) - Activity DSL specification and usage
- [Decisions](#decisions) - Architecture Decision Records
- [Guides](#guides) - Step-by-step implementation guides
- [Tools](#tools) - Developer tooling and maintenance scripts
- [Reference](#reference) - Templates and checklists
- [Features](#features) - Implemented features with complete documentation
- [Migrations](#migrations) - Database and code migration guides

## Skills Quick Reference

For hands-on implementation, invoke these skills:
- [@python](../.claude/skills/python/SKILL.md) - Python patterns
- [@result-pattern](../.claude/skills/result-pattern/SKILL.md) - Error handling
- [@base-analytics-service](../.claude/skills/base-analytics-service/SKILL.md) - Analytics services
- [All 27 skills](../.claude/skills/INDEX.md)

See [CROSS_REFERENCE_INDEX.md](CROSS_REFERENCE_INDEX.md) for skills ↔ docs mapping.

---

## Domains

*17 Entity Types with behavioral traits — see [Entity Type Architecture](architecture/ENTITY_TYPE_ARCHITECTURE.md)*

| Document | Description |
|----------|-------------|
| [Domains Overview](domains/README.md) | Complete entity type reference |
| [Tasks](domains/tasks.md) | Work items with dependencies and deadlines |
| [Goals](domains/goals.md) | Objectives with milestones and progress |
| [Habits](domains/habits.md) | Recurring behaviors with streak tracking |
| [Events](domains/events.md) | Calendar items with scheduling |
| [Choices](domains/choices.md) | Decisions with outcome tracking |
| [Principles](domains/principles.md) | Values that guide goals and choices |
| [Finance](domains/finance.md) | Expense and budget tracking (admin-only) |
| [KU (Knowledge Unit)](domains/ku.md) | Atomic knowledge unit (point topology) |
| [LS (Learning Step)](domains/ls.md) | Sequential steps aggregating KUs (edge topology) |
| [LP (Learning Path)](domains/lp.md) | Complete learning sequences (path topology) |
| [Submissions + Feedback](domains/submissions.md) | Article→Exercise→Submission→Feedback→RevisedExercise learning loop |
| [Journals](domains/journals.md) | User journals (EntityType.JOURNAL, AI-processed) |
| Groups | Teacher-student class management (ADR-040) — doc pending |
| [MOC (Map of Content)](domains/moc.md) | Non-linear navigation (graph topology via ORGANIZES) |
| [LifePath](domains/lifepath.md) | "Am I living my life path?" |

---

## Architecture

*System architecture, domain structure, and design decisions*

| Document | Updated | Lines |
|----------|---------|-------|
| [Admin Dashboard Architecture](architecture/ADMIN_DASHBOARD_ARCHITECTURE.md) | 2026-02-08 | 527 |
| [Alpine.js Architecture](architecture/ALPINE_JS_ARCHITECTURE.md) | 2026-01-05 | 280 |
| [Curriculum Grouping Patterns: KU, LS, LP + MOC Organization](architecture/CURRICULUM_GROUPING_PATTERNS.md) | 2026-01-20 | 410 |
| **[Enum Architecture](architecture/ENUM_ARCHITECTURE.md)** | **2026-03-05** | **~330** |
| **[Priority & Confidence Architecture](architecture/PRIORITY_CONFIDENCE_ARCHITECTURE.md)** | **2026-03-05** | **~130** |
| [Finance Categories System](architecture/FINANCE_CATEGORIES_GUIDE.md) | 2025-11-27 | 562 |
| **[Five-Phased Learning Loop](architecture/FOUR_PHASED_LEARNING_LOOP.md)** | **2026-03-07** | **~130** |
| [Knowledge Substance Philosophy](architecture/knowledge_substance_philosophy.md) | 2025-10-17 | 371 |
| **[Model Architecture](architecture/MODEL_ARCHITECTURE.md)** | **2026-02-23** | **290** |
| **[Relationships Architecture](architecture/RELATIONSHIPS_ARCHITECTURE.md)** | **2026-03-03** | **—** |
| **[Feedback Architecture](architecture/FEEDBACK_ARCHITECTURE.md)** | **2026-03-03** | **—** |
| [SKUEL Entity Type Architecture](architecture/ENTITY_TYPE_ARCHITECTURE.md) | 2026-03-07 | — |
| [SKUEL Routing Architecture: Routes, Services, and ...](architecture/ROUTING_ARCHITECTURE.md) | 2025-11-27 | 647 |
| [Search Architecture - Unified Search System](architecture/SEARCH_ARCHITECTURE.md) | 2026-03-03 | — |
| [Service Architecture: File Organization & Topology](architecture/SERVICE_TOPOLOGY.md) | 2026-03-03 | — |
| [User Architecture — Model, Auth, Roles, UserContext](architecture/UNIFIED_USER_ARCHITECTURE.md) | 2026-03-03 | — |
| **[Hyperview Mobile Strategy](architecture/HYPERVIEW_STRATEGY.md)** | **2026-02-06** | **90** |
| [Askesis Architecture](architecture/ASKESIS_ARCHITECTURE.md) | 2025-11-27 | — |
| [Askesis Pedagogical Architecture](architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md) | 2026-03-05 | ZPD-aware Socratic companion vision — how Askesis teaches, not how it is built |
| [Analytics Architecture](architecture/ANALYTICS_ARCHITECTURE.md) | 2025-11-27 | — |
| [Core Systems Architecture](architecture/CORE_SYSTEMS_ARCHITECTURE.md) | 2026-02-08 | — |
| **[Service Topology](architecture/SERVICE_TOPOLOGY.md)** | **2026-01-29** | **—** |

## Patterns

*Implementation patterns, coding standards, and best practices*

| Document | Updated | Lines |
|----------|---------|-------|
| **[API Input Validation Patterns](patterns/API_VALIDATION_PATTERNS.md)** | **2026-01-24** | **760** |
| [Async/Sync Design Pattern](patterns/ASYNC_SYNC_DESIGN_PATTERN.md) | 2026-01-03 | 200 |
| [BackendOperations Protocol Architecture](patterns/BACKEND_OPERATIONS_ISP.md) | 2026-01-07 | 320 |
| [Code Quality Enforcement - Linter Rules](patterns/linter_rules.md) | 2025-10-17 | 209 |
| [Constants Usage Guide](patterns/constants_usage_guide.md) | 2025-11-27 | 493 |
| [Context-First Relationship Pattern](patterns/CONTEXT_FIRST_RELATIONSHIP_PATTERN.md) | 2026-02-10 | 712 |
| **[Domain Lateral Service Quick Start](patterns/DOMAIN_LATERAL_SERVICE_QUICK_START.md)** | **2026-01-31** | **350** |
| [Domain-Specific Hooks Pattern](patterns/DOMAIN_SPECIFIC_HOOKS.md) | 2025-11-08 | 440 |
| **[Lateral Relationships Visualization Pattern](patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md)** | **2026-02-01** | **1020** |
| [Error Handling Architecture](patterns/ERROR_HANDLING.md) | 2025-11-27 | 456 |
| [Event-Driven Architecture](patterns/event_driven_architecture.md) | 2025-10-17 | 204 |
| [FastHTML Type Hints Pattern Guide](patterns/FASTHTML_TYPE_HINTS_GUIDE.md) | 2025-11-18 | 434 |
| [UnifiedRelationshipService - Configuration-Driven](patterns/UNIFIED_RELATIONSHIP_SERVICE.md) | 2025-12-03 | 550 |
| [Graph Access Patterns Guide](patterns/GRAPH_ACCESS_PATTERNS.md) | 2025-11-27 | 999 |
| [HTTP Status Codes - REST Best Practices](patterns/http_status_codes.md) | 2025-10-17 | 167 |
| **[Insight Action Tracking Pattern](patterns/INSIGHT_ACTION_TRACKING.md)** | **2026-01-31** | **420** |
| [Logging Patterns](patterns/LOGGING_PATTERNS.md) | 2026-01-03 | 130 |
| [MetadataManagerMixin - Consistent Timestamp & Meta...](patterns/metadata_manager_mixin.md) | 2025-11-28 | 247 |
| [Model-to-Adapter Dynamic Architecture](patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md) | 2025-11-27 | 495 |
| [MyPy Pragmatic Strategy - Making Peace with 2200 E...](patterns/mypy_pragmatic_strategy.md) | 2025-11-27 | 351 |
| [Performance Monitoring System](patterns/PERFORMANCE_MONITORING.md) | 2025-11-27 | 1033 |
| [Protocol Architecture](patterns/protocol_architecture.md) | 2026-01-29 | 234 |
| [Protocol LSP Compliance Pattern](patterns/PROTOCOL_LSP_COMPLIANCE.md) | 2025-11-08 | 246 |
| [Pure Cypher vs APOC: Strategic Decision Guide](patterns/CYPHER_VS_APOC_STRATEGY.md) | 2025-11-27 | 631 |
| [Intent-Based Graph Traversal](patterns/INTENT_BASED_TRAVERSAL.md) | 2025-12-03 | 350 |
| [Query Architecture](patterns/query_architecture.md) | 2025-12-07 | 520 |
| [Curriculum Query Patterns](patterns/curriculum/curriculum_query_patterns.md) | 2025-11-27 | 707 |
| [SKUEL Query Template Usage Guide](patterns/SKUEL_QUERY_USAGE_GUIDE.md) | 2025-11-26 | 620 |
| [Return Type Error Propagation Pattern](patterns/RETURN_TYPE_ERROR_PROPAGATION.md) | 2025-11-08 | 255 |
| [SearchService Pattern for Activity Domains](patterns/search_service_pattern.md) | 2025-11-28 | 268 |
| **[Three-Tier Type System](patterns/three_tier_type_system.md)** | **2026-01-24** | **468** |
| **[Type Safety Architecture Overview](patterns/TYPE_SAFETY_OVERVIEW.md)** | **2026-02-28** | **247** |
| **[Any Usage Policy](patterns/ANY_USAGE_POLICY.md)** | **2026-02-28** | **169** |
| **[MyPy Type Safety Patterns](patterns/MYPY_TYPE_SAFETY_PATTERNS.md)** | **2026-02-28** | — |
| [Trial Limits Infrastructure](patterns/TRIAL_LIMITS.md) | 2026-01-04 | 180 |
| [Service Consolidation Patterns](patterns/SERVICE_CONSOLIDATION_PATTERNS.md) | 2026-01-07 | 350 |
| [Unified Ingestion Guide](patterns/UNIFIED_INGESTION_GUIDE.md) | 2026-01-07 | 300 |
| [FastHTML Route Registration](patterns/FASTHTML_ROUTE_REGISTRATION.md) | 2026-01-07 | 180 |
| [Standalone Service Pattern](patterns/STANDALONE_SERVICE_PATTERN.md) | 2026-01-07 | 320 |
| [Secondary Entity Pattern](patterns/SECONDARY_ENTITY_PATTERN.md) | 2026-01-19 | 220 |
| [Configuration-Driven Service Architecture](patterns/CONFIGURATION_DRIVEN_SERVICE_ARCHITECTURE.md) | 2026-01-07 | 280 |
| [Auth Patterns](patterns/AUTH_PATTERNS.md) | 2026-01-06 | 300 |
| [Ownership Verification](patterns/OWNERSHIP_VERIFICATION.md) | 2025-12-05 | 180 |
| **[Content Sharing Patterns](patterns/SHARING_PATTERNS.md)** | **2026-02-02** | **680** |
| **[Route Decorator Architecture](patterns/ROUTE_DECORATOR_ARCHITECTURE.md)** | **2026-02-08** | **240** |
| [Route Factories](patterns/ROUTE_FACTORIES.md) | 2025-12-05 | 200 |
| [Route Naming Convention](patterns/ROUTE_NAMING_CONVENTION.md) | 2026-01-12 | 120 |
| [Error Handling Decorators](patterns/error_handling_decorators.md) | 2025-11-27 | 180 |
| [UID Boundary Conversion](patterns/UID_BOUNDARY_CONVERSION.md) | 2025-11-27 | 150 |
| [Query Patterns](patterns/QUERY_PATTERNS.md) | 2025-11-27 | 300 |
| **[Integration Testing Patterns](patterns/TESTING_PATTERNS.md)** | **2026-01-07** | **280** |
| **[UI Component Patterns](patterns/UI_COMPONENT_PATTERNS.md)** | **2026-02-03** | **1395** |
| **[FormGenerator Guide](patterns/FORM_GENERATOR_GUIDE.md)** | **2026-03-08** | **—** |

## Dsl

*Activity DSL grammar, usage, and implementation*

| Document | Updated | Lines |
|----------|---------|-------|
| [SKUEL Activity DSL - Formal Specification](dsl/DSL_SPECIFICATION.md) | 2025-11-30 | 408 |
| [SKUEL Activity DSL - Implementation Guide](dsl/DSL_IMPLEMENTATION.md) | 2025-11-30 | 676 |
| [SKUEL Activity DSL - Usage Guide](dsl/DSL_USAGE_GUIDE.md) | 2025-11-30 | 518 |

## Decisions

*Architecture Decision Records (ADRs)*

| Document | Updated | Lines |
|----------|---------|-------|
| [ADR-001: Single Complex Query for Unified User Con...](decisions/ADR-001-unified-user-context-single-query.md) | 2026-01-20 | 440 |
| [ADR-002: Knowledge Coverage Calculation Query](decisions/ADR-002-user-progress-service-query.md) | 2025-11-27 | 348 |
| [ADR-003: Journal Context Gathering Query](decisions/ADR-003-journals-service-query.md) | 2025-11-17 | 362 |
| [ADR-004: Ready-to-Learn Knowledge Unit Query](decisions/ADR-004-ku-graph-service-query.md) | 2025-11-27 | 367 |
| [ADR-005: Ready-to-Learn Knowledge Query Architectu...](decisions/ADR-005-ready-to-learn-knowledge-query.md) | 2025-11-27 | 601 |
| [ADR-006: Knowledge Gaps for Goals Query Architectu...](decisions/ADR-006-knowledge-gaps-for-goals-query.md) | 2025-11-27 | 189 |
| [ADR-007: Graph-Sourced-Context-Builder Query Archi...](decisions/ADR-007-graph-sourced-context-builder-query.md) | 2025-11-26 | 46 |
| [ADR-008: Learning Path Blocker Identification Quer...](decisions/ADR-008-lp-validation-service-query.md) | 2025-11-27 | 329 |
| [ADR-009: Optimal Learning Path Recommendation Quer...](decisions/ADR-009-lp-validation-service-query.md) | 2025-11-27 | 374 |
| [ADR-010: Moc-Core-Service Query Architecture](decisions/ADR-010-moc-core-service-query.md) | 2025-11-26 | 339 |
| [ADR-011: Life Path Alignment Query Architecture](decisions/ADR-011-life-path-alignment-query.md) | 2025-11-27 | 650 |
| [ADR-012: Cross-Domain Knowledge Applications Query...](decisions/ADR-012-cross-domain-knowledge-applications-query.md) | 2025-11-27 | 568 |
| [ADR-013: KU UID Flat Identity](decisions/ADR-013-ku-uid-flat-identity.md) | 2025-12-03 | 200 |
| [ADR-014: Unified Content Ingestion](decisions/ADR-014-unified-ingestion.md) | 2025-12-03 | 180 |
| [ADR-015: MEGA-QUERY Rich Queries Completion](decisions/ADR-015-mega-query-rich-queries-completion.md) | 2025-12-04 | 220 |
| [ADR-016: Context Builder Decomposition](decisions/ADR-016-context-builder-decomposition.md) | 2025-12-04 | 120 |
| [ADR-017: Relationship Service Unification](decisions/ADR-017-relationship-service-unification.md) | 2025-12-05 | 240 |
| [ADR-018: Four-Tier User Role System](decisions/ADR-018-user-roles-four-tier-system.md) | 2025-12-06 | 241 |
| [ADR-019: Transcription Service Simplification](decisions/ADR-019-transcription-service-standalone.md) | 2025-12-06 | 257 |
| [ADR-020: FastHTML Route Registration Pattern](decisions/ADR-020-fasthtml-route-registration-pattern.md) | 2025-12-07 | 136 |
| [ADR-021: User Context Intelligence Modularization](decisions/ADR-021-user-context-intelligence-modularization.md) | 2026-01-03 | 180 |
| [ADR-022: Graph-Native Authentication](decisions/ADR-022-graph-native-authentication.md) | 2026-01-04 | 200 |
| [ADR-023: Unified BaseService Architecture](decisions/ADR-023-curriculum-baseservice-migration.md) | 2026-01-06 | 295 |
| [ADR-024: BaseAnalyticsService Migration](decisions/ADR-024-base-intelligence-service-migration.md) | 2026-01-06 | 200 |
| [ADR-025: Service Consolidation Patterns](decisions/ADR-025-service-consolidation-patterns.md) | 2026-01-07 | 296 |
| [ADR-026: Unified Relationship Registry](decisions/ADR-026-unified-relationship-registry.md) | 2026-01-07 | 326 |
| [ADR-027: Knowledge Carrier Protocol](decisions/ADR-027-knowledge-carrier-protocol.md) | 2026-01-07 | - |
| [ADR-028: KU & MOC Unified Relationship Migration](decisions/ADR-028-ku-moc-unified-relationship-migration.md) | 2026-01-07 | - |
| [ADR-029: GraphNative Service Removal](decisions/ADR-029-graphnative-service-removal.md) | 2026-01-08 | 450 |
| [ADR-030: UserContext File Consolidation](decisions/ADR-030-usercontext-file-consolidation.md) | 2026-01-20 | 95 |
| [ADR-031: BaseService Mixin Decomposition](decisions/ADR-031-baseservice-mixin-decomposition.md) | 2026-01-21 | 295 |
| [ADR-032: Search Routes Explicit Dependency Injection](decisions/ADR-032-search-routes-explicit-di.md) | 2026-01-26 | 346 |
| [ADR-034: Semantic Search Phase 1 Enhancement](decisions/ADR-034-semantic-search-phase1-enhancement.md) | 2026-01-30 | 270 |
| [ADR-035: Tier Selection Guidelines](decisions/ADR-035-tier-selection-guidelines.md) | 2026-01-30 | 430 |
| [ADR-036: Prometheus Primary Cache Pattern](decisions/ADR-036-prometheus-primary-cache-pattern.md) | 2026-01-31 | 230 |
| **[ADR-037: Lateral Relationships Visualization (Phase 5)](decisions/ADR-037-lateral-relationships-visualization-phase5.md)** | **2026-02-01** | **1330** |
| **[ADR-038: Content Sharing Model](decisions/ADR-038-content-sharing-model.md)** | **2026-02-02** | **480** |
| **[ADR-039: Hyperview Mobile Strategy](decisions/ADR-039-hyperview-mobile-strategy.md)** | **2026-02-06** | **130** |
| **[ADR-040: Teacher Assignment Workflow](decisions/ADR-040-teacher-assignment-workflow.md)** | **2026-02-06** | **102** |
| **[ADR-041: Unified Ku Model](decisions/ADR-041-unified-ku-model.md)** | **2026-02-14** | **—** |
| **[ADR-042: Privacy as First-Class Citizen](decisions/ADR-042-privacy-as-first-class-citizen.md)** | **2026-03-01** | **—** |
| **[ADR-043: Intelligence Tier Toggle](decisions/ADR-043-intelligence-tier-toggle.md)** | **2026-03-04** | **—** |
| **[ADR-044: Neo4j as Committed Architectural Choice](decisions/ADR-044-neo4j-committed-architectural-choice.md)** | **2026-03-05** | **—** |
| **[ADR-045: Priority & Confidence as First-Class Customization Dials](decisions/ADR-045-priority-confidence-customization-dials.md)** | **2026-03-05** | **—** |
| **[ADR-046: Activity Domains Connect to Ku via Graph Edges](decisions/ADR-046-activity-domains-not-ku-subtypes.md)** | **2026-03-06** | **—** |
| **[ADR-047: Entity Types Replace Domain Categories](decisions/ADR-047-entity-types-replace-domain-categories.md)** | **2026-03-07** | **—** |
| **[ADR-048: Adaptive Learning Loop Architecture](decisions/ADR-048-adaptive-learning-loop.md)** | **2026-03-09** | **—** |
| [ADR-XXX: [Short Title of Decision]](decisions/ADR-TEMPLATE.md) | 2025-11-26 | 325 |

## Tools

*Developer tooling — scripts and automation for codebase maintenance*

| Document | Updated | Description |
|----------|---------|-------------|
| **[Codebase Health Checks](tools/HEALTH_CHECKS.md)** | **2026-03-04** | Dead modules, broken doc links, stale names, cross-refs (`./dev health`) |
| [Automatic Documentation Check](tools/AUTOMATIC_DOCS_CHECK.md) | 2026-01-30 | Post-commit hook that suggests doc updates after code changes |

---

## User Guides

*Practical usage guides for SKUEL workflows and tools*

| Document | Updated | Description |
|----------|---------|-------------|
| [Tasks Quick Add](user-guides/tasks-quick-add.md) | — | Quick task creation guide |
| **[Documentation Freshness](user-guides/documentation-freshness.md)** | **2026-03-04** | How SKUEL's three doc freshness systems work together (hooks + health checks + cross-refs) |
| **[Zone of Proximal Development](user-guides/zpd.md)** | **2026-03-09** | How ZPD works — current zone, proximal zone, readiness scores, behavioral enrichment |

---

## Guides

*Step-by-step implementation and migration guides*

| Document | Updated | Lines |
|----------|---------|-------|
| [Askesis Search Architecture - Clean & Independent](guides/ASKESIS_SEARCH_ARCHITECTURE.md) | 2025-11-27 | 243 |
| **[GitHub Fundamentals - Local to Remote Workflow](guides/GITHUB_FUNDAMENTALS.md)** | **2026-01-29** | **980** |
| [Intelligence Route Factory - Usage Guide](guides/INTELLIGENCE_ROUTE_FACTORY_USAGE.md) | 2025-11-27 | 555 |
| [HTMX Version Standardization Guide](guides/HTMX_VERSION_STANDARDIZATION.md) | 2026-01-15 | 280 |
| [Protocol Implementation Guide](guides/PROTOCOL_IMPLEMENTATION_GUIDE.md) | 2026-01-03 | 475 |
| [Shared UI Components - Quick Reference Card](guides/SHARED_UI_QUICK_REFERENCE.md) | 2025-11-27 | 264 |
| [Shared UI Components Guide](guides/SHARED_UI_COMPONENTS_GUIDE.md) | 2026-01-15 | 674 |
| **[Article Content and Resources](guides/ARTICLE_CONTENT_AND_RESOURCES.md)** | **2026-03-09** | **140** |
| **[Troubleshooting Guide](TROUBLESHOOTING.md)** | **2026-01-31** | **650** |

## Deployment

*Infrastructure migration guides — local → DigitalOcean → AuraDB*

| Document | Updated | Description |
|----------|---------|-------------|
| [Neo4j Setup Migration Summary](deployment/NEO4J_SETUP_MIGRATION_SUMMARY.md) | 2026-02-05 | History and rationale of the three-stage deployment roadmap |
| [DigitalOcean Migration Guide](deployment/DO_MIGRATION_GUIDE.md) | 2026-02-05 | Stage 2: Droplet (Neo4j) + App Platform (app) |
| [AuraDB Migration Guide](deployment/AURADB_MIGRATION_GUIDE.md) | 2026-02-01 | Stage 3: Neo4j AuraDB production deployment |

---

## Reference

*Templates, checklists, and reference materials*

| Document | Updated | Lines |
|----------|---------|-------|
| [Code Review Checklist - Phase 7.3](reference/CODE_REVIEW_CHECKLIST.md) | 2025-11-27 | 602 |
| [Placeholder Parameter Index](reference/PLACEHOLDER_INDEX.md) | 2026-02-24 | — |
| [Protocol Definition Template](reference/templates/protocol_definition.md) | 2025-11-27 | 229 |
| [Protocol Reference Guide](reference/PROTOCOL_REFERENCE.md) | 2026-01-29 | 617 |
| [Search Models Reference](reference/models/SEARCH_MODELS.md) | 2026-01-04 | 480 |
| [Search Service Methods Reference](reference/SEARCH_SERVICE_METHODS.md) | 2026-01-06 | 580 |
| [Service Creation Template](reference/templates/service_creation.md) | 2025-11-27 | 156 |

## Intelligence

*AI features, roadmaps, and vision documents*

| Document | Updated | Lines |
|----------|---------|-------|
| [Discovery Analytics Implementation Roadmap](intelligence/DISCOVERY_ANALYTICS_ROADMAP.md) | 2025-11-27 | 210 |
| [Real-time Intelligence Implementation Roadmap](intelligence/REALTIME_INTELLIGENCE_ROADMAP.md) | 2025-11-27 | 241 |
| [SKUEL Intelligence Documentation](intelligence/README.md) | 2025-11-27 | 250 |
| [SKUEL Intelligence Roadmap](intelligence/INTELLIGENCE_ROADMAP.md) | 2025-11-27 | 214 |
| [Semantic Analysis Implementation Roadmap](intelligence/SEMANTIC_ANALYSIS_ROADMAP.md) | 2025-11-27 | 153 |
| [Ultimate Search Intelligence - Aspirational Vision](intelligence/ULTIMATE_VISION.md) | 2025-11-27 | 226 |

## Features

*Implemented features with complete documentation*

| Document | Updated | Lines |
|----------|---------|-------|
| **[SEL Adaptive Curriculum](features/SEL_ADAPTIVE_CURRICULUM.md)** | **2026-02-03** | **850** |

## Migrations

*Database and code migration guides*

| Document | Updated | Lines |
|----------|---------|-------|
| [**DomainConfig Migration Complete**](migrations/DOMAINCONFIG_MIGRATION_COMPLETE.md) | 2026-01-29 | 486 |
| [**BaseService Improvements 2026-01-29**](migrations/BASESERVICE_IMPROVEMENTS_2026-01-29.md) | 2026-01-29 | 513 |
| [Domain Route Config Migration - Phase 2](migrations/DOMAIN_ROUTE_CONFIG_MIGRATION_2026-01-24.md) | 2026-01-24 | 251 |
| **[Domain Route Config Migration - Phase 3](migrations/DOMAIN_ROUTE_CONFIG_MIGRATION_2026-02-03.md)** | **2026-02-03** | **1050** |
| [Neo4j Label Standardization Migration Plan](migrations/NEO4J_LABEL_STANDARDIZATION.md) | 2025-11-27 | 167 |
| [Ports to Protocols Migration History](migrations/PORTS_TO_PROTOCOLS_MIGRATION.md) | 2026-01-03 | 385 |
| [Assignments Routes Refactoring](migrations/assignments-refactoring-2026-01-25.md) | 2026-01-25 | 274 |
| [Visualization Routes Refactoring](migrations/visualization-refactoring-2026-01-25.md) | 2026-01-25 | 208 |
| [Service Refactoring Analysis](migrations/service-refactoring-analysis-2026-01-25.md) | 2026-01-25 | 298 |
| [Service Layer Refactoring Complete](migrations/service-layer-refactoring-complete-2026-01-25.md) | 2026-01-25 | 435 |
| [Context Health Score Enum Improvement](migrations/health-score-enum-improvement-2026-01-25.md) | 2026-01-25 | 334 |
| **[Lateral Relationships Implementation Complete](migrations/LATERAL_RELATIONSHIPS_COMPLETE_2026-01-31.md)** | **2026-01-31** | **452** |
| [KU Route Naming Standardization](migrations/KU_ROUTE_NAMING_STANDARDIZATION_2026-02-02.md) | 2026-02-02 | 167 |
| **[UI Factory Signature Standardization](migrations/UI_FACTORY_SIGNATURE_STANDARDIZATION_2026-02-03.md)** | **2026-02-03** | **180** |
| **[SEL Routes UX Modernization](migrations/SEL_UX_MODERNIZATION_2026-02-03.md)** | **2026-02-03** | **900** |
| **[SEL Routes DomainRouteConfig Migration](migrations/SEL_ROUTES_MIGRATION_2026-02-03.md)** | **2026-02-03** | **426** |
| [Config-Driven Factories Migration](migrations/CONFIG_DRIVEN_FACTORIES_MIGRATION_2026-02-05.md) | 2026-02-05 | — |
| [Profile Hub Modernization](migrations/PROFILE_HUB_MODERNIZATION_2026-02-01.md) | 2026-02-01 | — |
| [Embedding Infrastructure Alignment](migrations/EMBEDDING_INFRASTRUCTURE_ALIGNMENT_2026-02-01.md) | 2026-02-01 | — |
| [Protocol Mixin Alignment Complete](migrations/PROTOCOL_MIXIN_ALIGNMENT_COMPLETE_2026-01-29.md) | 2026-01-29 | — |
| [Relationship Registry Rename](migrations/RELATIONSHIP_REGISTRY_RENAME_2026-02-08.md) | 2026-02-08 | — |
| **[Domain Backends Position 2 Complete](migrations/DOMAIN_BACKENDS_POSITION_2_COMPLETE_2026-03-01.md)** | **2026-03-01** | **—** |

## Roadmap

*Deferred work with explicit triggers and review schedule*

| Document | Updated | Description |
|----------|---------|-------------|
| [Deferred Work](roadmap/deferred-work.md) | 2026-03-04 | Intelligence features and decision points deferred until data/business prerequisites exist |
| [Security Hardening — Deferred](roadmap/security-hardening-deferred.md) | 2026-03-04 | 5 deferred security items: dependency pinning, rate limiting, secret scanning, session rotation, CI CVE scanning |
| [ZPDService — Design & Architecture](roadmap/zpd-service-deferred.md) | 2026-03-09 | ZPDService + ZPDBackend architecture: ZPDAssessment, graph traversal, readiness scores, behavioral enrichment |
| [Conversation Neo4j Persistence — Deferred](roadmap/conversation-neo4j-persistence-deferred.md) | 2026-03-05 | Neo4j schema for persisted conversation sessions and turns; cross-session continuity design |
| [Teacher-Askesis Interface — Deferred](roadmap/teacher-askesis-interface-deferred.md) | 2026-03-05 | Teacher view/adjust/annotate interface; requires ZPDService + Neo4j persistence first |
| [Learning Loop Cross-Domain Search](roadmap/learning-loop-cross-domain-search.md) | 2026-03-07 | Level 3 roadmap: cross-loop graph traversal search, SubmissionReport/ActivityReport search |

## Examples

*Demos and example workflows*

| Document | Updated | Lines |
|----------|---------|-------|
| [Mindfulness 101 Demo](examples/mindfulness-101-demo.md) | 2026-01-25 | 198 |

## Technical Debt

*Known limitations and technical debt*

| Document | Updated | Lines |
|----------|---------|-------|
| [MyPy Limitations in Universal Backend](technical_debt/MYPY_BACKEND_LIMITATIONS.md) | 2025-11-18 | 196 |
| [Return Value Type Errors Analysis](technical_debt/RETURN_VALUE_ERRORS_ANALYSIS.md) | 2025-11-18 | 279 |

## Top-Level

*Top-level documentation files*

| Document | Updated | Lines |
|----------|---------|-------|
| [Claude Quick Start Guide](CLAUDE_QUICKSTART.md) | 2025-12-04 | 180 |
| [SKUEL Documentation Hub](README.md) | 2025-12-04 | 153 |

---

## Statistics

- **Total documents:** ~196 (core + migrations + roadmap + examples)
- **Categories:** 13 (Domains, Architecture, Patterns, DSL, Decisions, Guides, Reference, Intelligence, Migrations, Roadmap, Examples, Technical Debt, Top-Level)
- **ADRs:** 49 (ADR-001 through ADR-048, with template)