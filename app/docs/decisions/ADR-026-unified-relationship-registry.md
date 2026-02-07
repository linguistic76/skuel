---
title: ADR-026: Unified Relationship Registry
updated: 2026-02-07
status: accepted (evolved)
category: decisions
tags: [adr, decisions, relationships, consolidation, single-source-of-truth]
related: [ADR-017-relationship-service-unification.md, ADR-025-service-consolidation-patterns.md]
---

# ADR-026: Unified Relationship Registry

**Status:** Accepted (Evolved February 2026)

**Date:** 2026-01-07

**February 2026 Evolution:** The intermediate `RelationshipConfig`/`domain_configs.py` translation layer described in this ADR has been removed. All consumers now use `DomainRelationshipConfig` directly from `relationship_registry.py`. The `generate_relationship_config()` and `generate_relationship_config_by_label()` functions were deleted. Named configs (e.g., `TASKS_UNIFIED`, `KU_UNIFIED`) are imported directly from the registry. ~395 lines of translation ceremony removed.

**Decision Type:** ☑ Pattern/Practice

**Related ADRs:**
- Extends: ADR-017 (Relationship Service Unification)
- Related to: ADR-025 (Service Consolidation Patterns)

---

## Context

**What is the issue we're facing?**

SKUEL had a **dual-source problem** for relationship configurations. The same relationships were defined in two separate places:

```python
# Source 1: relationship_registry.py (for DomainConfig/graph_aware_search)
GRAPH_ENRICHMENT_REGISTRY["Task"] = [
    (RelationshipName.APPLIES_KNOWLEDGE.value, "Ku", "applied_knowledge", "outgoing"),
]

# Source 2: domain_configs.py (for RelationshipConfig/UnifiedRelationshipService)
TASK_CONFIG.outgoing_relationships = {
    "knowledge": RelationshipSpec(RelationshipName.APPLIES_KNOWLEDGE, "outgoing"),
}
```

**Problems:**
1. **Drift risk**: Updates to one source don't propagate to the other
2. **Maintenance burden**: Two files to update for every relationship change
3. **Inconsistent formats**: Tuples vs. dataclasses for the same data
4. **Curriculum gap**: Curriculum domains (KU, LS, LP) and MOC (Content/Organization) lacked RelationshipConfig, limiting their integration with UnifiedRelationshipService

**Constraints:**
- Must maintain backward compatibility with existing imports
- Must support both Activity (user-owned) and Curriculum (shared) domains
- Must preserve type safety with RelationshipName enum

---

## Decision

**What is the change we're proposing/making?**

Create `RelationshipRegistry` as THE single source of truth for all relationship configurations. Both `relationship_registry.py` and `domain_configs.py` become facades that generate their data from this registry.

**Implementation:**

1. **New dataclasses** in `/core/models/relationship_registry.py`:

```python
@dataclass(frozen=True)
class UnifiedRelationshipDefinition:
    """Single source of truth for one relationship."""
    relationship: RelationshipName
    target_label: str
    direction: str  # "outgoing", "incoming", "both"
    context_field_name: str  # For graph enrichment
    method_key: str  # For RelationshipConfig
    filter_property: str | None = None
    filter_value: str | None = None
    is_cross_domain_mapping: bool = True
    use_directional_markers: bool = False

@dataclass(frozen=True)
class DomainRelationshipConfig:
    """All relationships for one domain."""
    domain: Domain
    entity_label: str
    dto_class: type
    model_class: type
    ownership_relationship: RelationshipName | None
    relationships: tuple[UnifiedRelationshipDefinition, ...]
    scoring_weights: dict[str, float]
    is_shared_content: bool = False
    use_semantic_helper: bool = True
    post_processors: tuple[PostProcessor, ...] = ()  # Phase 3 (January 2026)

@dataclass(frozen=True)
class PostProcessor:
    """Post-query Python calculation for computed fields."""
    source_field: str       # Field from graph_context to process
    target_field: str       # Field name for computed result
    processor_name: str     # Function name in PROCESSOR_REGISTRY
```

2. **Two registries** for access patterns:

```python
# Access by Domain enum (6 Activity + 2 Curriculum primaries)
UNIFIED_REGISTRY: dict[Domain, DomainRelationshipConfig] = {
    Domain.TASKS: TASKS_UNIFIED,
    Domain.GOALS: GOALS_UNIFIED,
    # ... 8 domains total
}

# Access by Neo4j label (all 10 domain labels)
UNIFIED_REGISTRY_BY_LABEL: dict[str, DomainRelationshipConfig] = {
    "Task": TASKS_UNIFIED,
    "Ku": KU_UNIFIED,
    "Lp": LP_UNIFIED,
    "MapOfContent": MOC_UNIFIED,
    # ... 10 labels total
}
```

3. **Generator functions** that produce outputs for both consumers:

```python
def generate_graph_enrichment(entity_label: str) -> list[tuple[str, str, str, str]]:
    """Generate graph enrichment patterns for relationship_registry.py"""

def generate_prerequisite_relationships(entity_label: str) -> list[str]:
    """Generate prerequisite relationship types"""

def generate_enables_relationships(entity_label: str) -> list[str]:
    """Generate enables relationship types"""

def generate_relationship_config(domain: Domain) -> RelationshipConfig | None:
    """Generate RelationshipConfig for domain_configs.py"""
```

4. **Post-Query Processors** for calculated fields (Phase 3):

```python
# In relationship_registry.py - GOALS_UNIFIED example
GOALS_UNIFIED = DomainRelationshipConfig(
    # ... relationships ...
    post_processors=(
        PostProcessor(
            source_field="milestones",
            target_field="milestone_progress",
            processor_name="calculate_milestone_progress",
        ),
    ),
)

# In post_processors.py - processor implementation
def calculate_milestone_progress(milestones: list[dict]) -> dict:
    """Calculate milestone completion percentage."""
    total = len(milestones)
    completed = sum(1 for m in milestones if m.get("is_completed"))
    percentage = round((completed / total * 100.0), 2) if total > 0 else 0.0
    return {"total": total, "completed": completed, "percentage": percentage}

PROCESSOR_REGISTRY = {
    "calculate_milestone_progress": calculate_milestone_progress,
    "calculate_habit_streak_summary": calculate_habit_streak_summary,
    "calculate_task_status_summary": calculate_task_status_summary,
}

# BaseService._parse_context_result() applies processors automatically
for processor in config.post_processors:
    source_data = graph_context.get(processor.source_field, [])
    if source_data:
        graph_context[processor.target_field] = apply_processor(
            processor.processor_name, source_data
        )
```

5. **Facades** that call generators:

```python
# relationship_registry.py - now a facade
GRAPH_ENRICHMENT_REGISTRY = {
    "Task": generate_graph_enrichment("Task"),
    "Ku": generate_graph_enrichment("Ku"),
    # ... all 10 domains
}

# domain_configs.py - now a facade
TASK_CONFIG = generate_relationship_config(Domain.TASKS)
```

---

## Alternatives Considered

### Alternative 1: Manual Synchronization

**Description:** Keep both files, manually keep them in sync.

**Pros:**
- No code changes required
- Simpler individual files

**Cons:**
- Drift is inevitable
- Double maintenance burden
- No single source of truth

**Why rejected:** Violates DRY principle; drift already observed in codebase.

### Alternative 2: Generate relationship_registry from domain_configs

**Description:** Make domain_configs.py the source, generate relationship_registry from it.

**Pros:**
- Single source
- Simpler than new registry

**Cons:**
- RelationshipConfig has different shape than graph enrichment tuples
- Would require adding fields to RelationshipSpec not needed for its primary purpose
- Curriculum domains don't have RelationshipConfig

**Why rejected:** Forces RelationshipConfig to carry data it doesn't need.

### Alternative 3: Remove relationship_registry entirely

**Description:** Have services query RelationshipRegistry directly.

**Pros:**
- Eliminates intermediate layer
- Simpler architecture

**Cons:**
- Breaking change for all services using GRAPH_ENRICHMENT_REGISTRY
- Would require updating ~20 service files

**Why rejected:** Too disruptive; facade pattern maintains backward compatibility.

---

## Consequences

### Positive Consequences
- ✅ **Single source of truth**: All relationship data defined once
- ✅ **Type safety**: RelationshipName enum throughout
- ✅ **Curriculum integration**: All 10 domains now have relationship configs
- ✅ **Backward compatible**: Existing imports continue to work
- ✅ **Reduced drift risk**: Changes in one place propagate everywhere

### Negative Consequences
- ⚠️ **Indirection**: Must look at relationship_registry.py to see actual definitions
- ⚠️ **Startup cost**: Generator functions run at import time (minimal impact)

### Neutral Consequences
- ℹ️ New file to maintain (relationship_registry.py)
- ℹ️ 11 new RelationshipName enum values added for curriculum domains

### Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Generator produces wrong output | Low | High | 26 unit tests verify all outputs |
| New RelationshipNames break existing code | Low | Medium | Added values only, no removals |
| Import cycle with new module | Low | Medium | Carefully structured imports |

---

## Implementation Details

### Code Location
- **Primary file:** `/core/models/relationship_registry.py`
- **Related files:**
  - `/core/models/relationship_registry.py` (now facade)
  - `/core/services/relationships/domain_configs.py` (now facade)
  - `/core/models/relationship_names.py` (11 new values)
  - `/core/models/query/cypher/post_processors.py` (Phase 3 - processor functions)
  - `/core/services/base_service.py` (`_parse_context_result()` applies processors)
- **Tests:** `/tests/test_relationship_registry.py`

### New RelationshipName Values (Phase 2)

```python
# Curriculum Relationships (January 2026 - Phase 2 Consolidation)
CONTAINS_KNOWLEDGE = "CONTAINS_KNOWLEDGE"  # (ls)-[:CONTAINS_KNOWLEDGE]->(ku)
REQUIRES_STEP = "REQUIRES_STEP"            # (ls)-[:REQUIRES_STEP]->(ls)
BUILDS_HABIT = "BUILDS_HABIT"              # (ls)-[:BUILDS_HABIT]->(habit)
ASSIGNS_TASK = "ASSIGNS_TASK"              # (ls)-[:ASSIGNS_TASK]->(task)
SCHEDULES_EVENT = "SCHEDULES_EVENT"        # (ls)-[:SCHEDULES_EVENT]->(event)
ALIGNED_WITH_GOAL = "ALIGNED_WITH_GOAL"    # (lp)-[:ALIGNED_WITH_GOAL]->(goal)
HAS_MILESTONE_EVENT = "HAS_MILESTONE_EVENT"# (lp)-[:HAS_MILESTONE_EVENT]->(event)
CONTAINS_PATH = "CONTAINS_PATH"            # (moc)-[:CONTAINS_PATH]->(lp)
CONTAINS_PRINCIPLE = "CONTAINS_PRINCIPLE"  # (moc)-[:CONTAINS_PRINCIPLE]->(principle)
BRIDGES_TO = "BRIDGES_TO"                  # (moc)-[:BRIDGES_TO]->(moc)
RELATED_TO_MOC = "RELATED_TO_MOC"          # (moc)-[:RELATED_TO_MOC]->(moc)
```

### Testing Strategy
- [x] Unit tests: 26 tests covering all domains and generators
- [x] Integration tests: Verify generated configs work with domain_configs module
- [x] Regression tests: Verify relationship_registry patterns unchanged

---

## Documentation & Communication

### Pattern Documentation Checklist

- [x] Updated `/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md`
- [x] Updated plan file with completion status
- [ ] Update CLAUDE.md with quick reference (if widely used)

### Related Documentation
- Architecture docs: `/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md`
- Pattern guide: `/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md`
- Other ADRs: ADR-017, ADR-025

---

## Future Considerations

### When to Revisit
- If new domains are added (add to registry)
- If relationship patterns diverge significantly between Activity and Curriculum
- If performance issues arise from generator execution at import time

### Evolution Path
- Could add validation layer to check graph enrichment patterns match Neo4j schema
- Could generate relationship service methods dynamically from registry

### Scope Boundary: Ingestion Config is Independent

The **ingestion relationship config** (`core/services/ingestion/config.py`) is intentionally
**outside** the scope of this registry. Ingestion configs define YAML field path → Neo4j edge
creation during Markdown/YAML import. They are independent because:

1. **YAML field paths** (`connections.requires`, etc.) have no registry equivalent
2. **KU uses different relationship types**: Ingestion creates `PREREQUISITE`/`ENABLES` (KU-to-KU
   edges), while the registry defines `REQUIRES_KNOWLEDGE`/`ENABLES_KNOWLEDGE` (cross-domain
   enrichment edges). Both coexist in Neo4j and are queried by different services.
3. **Ingestion is a small subset**: 17 relationships out of 100+ in the registry

See `core/services/ingestion/config.py` for the full cross-reference table.

### Technical Debt
- None created; this ADR reduces technical debt by eliminating dual-source problem

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2026-01-07 | Claude | Initial implementation (Phase 1 + Phase 2) | 1.0 |
| 2026-01-10 | Claude | Phase 3: Post-Query Processors (PostProcessor dataclass, PROCESSOR_REGISTRY) | 1.1 |

---

## Appendix

### Domain Coverage

| Domain | UNIFIED_REGISTRY | UNIFIED_REGISTRY_BY_LABEL | RelationshipConfig |
|--------|------------------|---------------------------|-------------------|
| Tasks | ✅ Domain.TASKS | ✅ "Task" | ✅ Generated |
| Goals | ✅ Domain.GOALS | ✅ "Goal" | ✅ Generated |
| Habits | ✅ Domain.HABITS | ✅ "Habit" | ✅ Generated |
| Events | ✅ Domain.EVENTS | ✅ "Event" | ✅ Generated |
| Choices | ✅ Domain.CHOICES | ✅ "Choice" | ✅ Generated |
| Principles | ✅ Domain.PRINCIPLES | ✅ "Principle" | ✅ Generated |
| KU | ✅ Domain.KNOWLEDGE | ✅ "Ku" | ✅ Generated |
| LS | ✅ Domain.LEARNING | ✅ "Ls" | ✅ Generated |
| LP | - | ✅ "Lp" | ✅ Generated |
| MOC | - | ✅ "MapOfContent" | ✅ Generated |

**Note:** LP and MOC accessible via label registry only (no Domain enum mapping).

### Test Results

```
tests/test_relationship_registry.py - 26 tests passing
├── TestUnifiedRegistry (3 tests)
├── TestUnifiedRelationshipDefinition (3 tests)
├── TestGenerateGraphEnrichment (3 tests)
├── TestGeneratePrerequisiteRelationships (2 tests)
├── TestGenerateEnablesRelationships (2 tests)
├── TestGenerateRelationshipConfig (5 tests)
├── TestHelperFunctions (2 tests)
├── TestCurriculumDomains (4 tests)
└── TestActivityDomainIntegration (2 tests)
```
