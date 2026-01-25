---
title: Model Architecture
updated: 2025-11-27
status: current
category: architecture
tags: [architecture, model]
related: []
---

# Model Architecture

## Core Philosophy: Relationship-Centric Design

**Everything in SKUEL has relationships.** This is the fundamental principle that drives our architecture. Every entity - tasks, events, habits, knowledge units - exists in a graph of connections.

## Unified Architecture Pattern

The model and service layers work in harmony through:

1. **Relationship-Centric Models** (`base_models_consolidated.py`)
   - All entities inherit relationship support
   - Graph connections are first-class citizens
   - Immutable models with relationship UIDs

2. **Unified Base Service** (`base_service.py`)
   - Single service base for ALL entities
   - Built-in relationship operations
   - Graph traversal and pathfinding

3. **Three-Tier Type System**
   - **Pydantic Models**: External validation at boundaries
   - **DTOs**: Mutable transfer objects with relationship metadata
   - **Domain Models**: Frozen dataclasses with relationships

## Directory Structure

```
/core/models/
├── base_models_consolidated.py  # Unified base with relationship support
├── knowledge_unit.py            # Core knowledge domain model
├── knowledge_unit_semantic.py   # Semantic-enhanced knowledge unit
├── semantic_relationships.py    # RDF-inspired semantic relationships
├── ontology_generator.py        # Pydantic schema to ontology generation
├── knowledge_dto.py             # Knowledge DTO with relationships
├── knowledge_content.py         # Content facet for knowledge units
├── shared_enums.py             # All shared enumerations
├── constants.py                # System constants
├── type_hints.py               # Type definitions and guards
├── /learning/
│   ├── curriculum.py           # Learning paths and steps
│   ├── scheduled.py            # Calendar-aware sessions
│   └── learning_models.py     # Insights and analytics
├── task_pure.py               # Task domain model
├── habit_pure.py              # Habit domain model
├── event_pure.py              # Event domain model
├── finance_pure.py            # Finance domain model
├── progress_unified.py        # Universal progress tracking
├── unified_relationships.py   # Relationship management
└── user_context_simplified.py # User context model

/core/services/
├── base_service.py                        # Unified relationship-centric base
├── tasks_service.py                       # Inherits from BaseService
├── events_service.py                      # Inherits from BaseService
├── habits_service.py                      # Inherits from BaseService
├── finance_service.py                     # Inherits from BaseService
├── unified_knowledge_service.py           # Enhanced with semantic capabilities
├── unified_knowledge_service_semantic.py  # Semantic-enhanced version
├── learning_path_service_semantic.py      # A* search with semantic distance
├── semantic_search_service.py             # Intent-based semantic search
├── cross_domain_discovery_service.py      # Cross-domain relationship discovery
├── semantic_relationship_collector.py     # Semantic relationship management
└── journal_core_service.py               # Inherits from BaseService
```

## Key Design Principles

### 1. Everything Has Relationships (Enhanced with Semantic Precision)
- Models include `RelationshipMixin` with `relationship_uids`
- **NEW**: Semantic relationships with RDF-inspired precision via `SemanticKnowledgeUnit`
- Services provide `add_relationship()`, `get_relationships()`, `traverse()`
- **NEW**: Semantic search and discovery with intent-based queries
- DTOs transfer relationship metadata between layers
- Graph operations are fundamental, not optional

### 2. Unified Base Pattern
- **ONE** base service class (`BaseService`)
- **ONE** base model hierarchy (`base_models_consolidated.py`)
- **ONE** error handling pattern (`Result[T]` with `Errors`)
- **NO** alternative paths or backwards compatibility complexity

### 3. Core Fields Present Everywhere
Every entity has:
- `content`: Generic content field (markdown, notes, etc.)
- `status`: Current state tracking
- `progress`: 0-100% completion/mastery
- `relationship_uids`: Graph connections
- Standard timestamps and metadata

### 4. Result-Based Validation
- ALL validation returns `Result[bool]`
- NEVER throw exceptions from validation
- Consistent error handling via `result_simplified`
- Errors at boundaries, Results internally

## Model Categories Quick Reference

| Type | Base Class | Characteristics | Use Case | Import |
|------|------------|-----------------|----------|---------|
| **Domain Model** | `BaseEntity` | Frozen dataclass, immutable, relationships | Core business logic | `from core.models.base_models_consolidated import BaseEntity` |
| **DTO** | `BaseDTO` | Mutable dataclass, relationship metadata | Layer-to-layer transfer | `from core.models.base_models_consolidated import BaseDTO` |
| **API Schema** | `BaseCreateSchema` | Pydantic model, validation | External boundaries | `from core.models.base_models_consolidated import BaseCreateSchema` |

### Domain Models (Frozen Dataclasses)
Pure business entities with relationship support:
```python
from core.models.base_models_consolidated import BaseEntity

@dataclass(frozen=True)
class TaskPure(BaseEntity):  # Inherits RelationshipMixin
    priority: Priority
    context: TaskContext
    # Relationships stored in relationship_uids:
    # - DEVELOPS_MASTERY_OF → KnowledgeUnit
    # - DEPENDS_ON → TaskPure
    # - PART_OF → Goal
```

### DTOs (Mutable Dataclasses)
Transfer objects with relationship metadata:
```python
from core.models.base_models_consolidated import BaseDTO

@dataclass
class TaskDTO(BaseDTO):
    priority: str  # String for transfer
    context: str   # String for transfer
    # Inherited from BaseDTO:
    relationships_out: List[Relationship]  # Outgoing edges
    relationships_in: List[Relationship]   # Incoming edges
```

### Pydantic Schemas (External Boundaries)
API schemas with relationship specification:
```python
from core.models.base_models_consolidated import BaseCreateSchema

class TaskCreateRequest(BaseCreateSchema):
    priority: Priority = Field(..., description="Task priority")
    context: Optional[str] = None
    # Inherited from BaseCreateSchema:
    relationships: Optional[Dict[str, List[str]]]  # Initial graph setup

    @field_validator('title')
    def clean_title(cls, v):
        return v.strip()
```

## Relationship Types

### Traditional Relationship Types
Core relationship types that connect everything:
- **Knowledge Graph**: REQUIRES, ENABLES, HAS_NARROWER, BROADER_THAN
- **Task Relations**: DEVELOPS_MASTERY_OF, DEPENDS_ON, BLOCKS
- **Goal Hierarchies**: CONTRIBUTES_TO, PART_OF, MILESTONE_OF
- **Learning Paths**: PREREQUISITE_FOR, NEXT_STEP, ALTERNATIVE_TO
- **Habit Connections**: TRIGGERS, REINFORCES, COMPETES_WITH

### Semantic Relationship Types (RDF-Inspired)
**NEW**: Semantically precise relationships with namespaced organization:

#### Learning Domain (`learn:`)
- `learn:requires_theoretical_understanding`
- `learn:requires_practical_application`
- `learn:builds_mental_model`
- `learn:extends_pattern`
- `learn:deepens_understanding`
- `learn:contrasts_with`
- `learn:complements`

#### Task Domain (`task:`)
- `task:blocks_until_complete`
- `task:enables_start_of`
- `task:shares_resources_with`
- `task:produces_input_for`
- `task:validates_output_of`

#### Cross-Domain (`cross:`)
- `cross:implements_via_task`
- `cross:practices_via_habit`
- `cross:demonstrates_in_project`
- `cross:applies_knowledge_to`
- `cross:reveals_pattern_in`

#### Skill Domain (`skill:`)
- `skill:develops_skill`
- `skill:practices_technique`
- `skill:masters_through`
- `skill:requires_skill_level`

#### Conceptual Domain (`concept:`)
- `concept:derives_from`
- `concept:generalizes`
- `concept:specializes`
- `concept:abstracts`

#### Temporal Domain (`time:`)
- `time:occurs_before`
- `time:occurs_after`
- `time:deadline_for`
- `time:scheduled_with`

## Semantic Enhancement Architecture

### Three-Phase Semantic Implementation

SKUEL's semantic capabilities were implemented in three phases:

#### Phase 1: Core Semantic Components
- **SemanticRelationshipType**: RDF-inspired relationship types with namespaces
- **SemanticKnowledgeUnit**: Enhanced knowledge unit with semantic relationships
- **RelationshipMetadata**: Rich context for relationships (confidence, strength, source)
- **SemanticTriple**: RDF-inspired triple representation (subject-predicate-object)
- **TripleBuilder**: Fluent interface for constructing semantic triples

#### Phase 2: Enhanced Services
- **UnifiedKnowledgeService**: Enhanced with semantic search and discovery
- **LearningPathService**: A* search with semantic distance for optimal paths
- **Migration utilities**: Batch migration from traditional to semantic relationships

#### Phase 3: Production Features
- **REST API endpoints**: Semantic search, cross-domain discovery, path generation
- **GraphQL schema**: Complex nested queries for semantic relationships
- **UI components**: Interactive semantic search and exploration (FrankenUI)
- **Production deployment**: Performance optimization, caching, monitoring

### Semantic Knowledge Unit Enhancement

```python
from core.models.knowledge_unit_semantic import SemanticKnowledgeUnit
from core.models.semantic_relationships import SemanticRelationshipType

# Create enhanced knowledge unit
semantic_ku = SemanticKnowledgeUnit(
    knowledge_unit=traditional_ku,  # Composition over inheritance
    semantic_relationships=[],
    semantic_context={},
    ontology_class="ConceptualKnowledge"
)

# Add semantic relationships
semantic_ku.add_semantic_relationship(
    predicate=SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
    object_uid="ku.prerequisite_concept",
    confidence=0.9,
    strength=0.8,
    source="expert_analysis"
)
```

### RDF-Inspired Triple System

```python
from core.models.semantic_relationships import SemanticTriple, TripleBuilder

# Build semantic triples
triples = TripleBuilder("ku.linear_algebra") \
    .requires_understanding("ku.basic_algebra", confidence=0.9) \
    .builds_model("mental_model.matrix_operations", strength=0.8) \
    .enables_task("task.implement_neural_network") \
    .contrasts_with("ku.nonlinear_algebra", notes="Different mathematical approach") \
    .build()

# Convert to Cypher for Neo4j
for triple in triples:
    cypher = triple.to_cypher_merge()
    params = triple.to_cypher_params()
```

### Semantic Search and Discovery

```python
from core.services.semantic_search_service import SemanticSearchService
from core.models.semantic_relationships import QueryIntent

# Intent-based semantic search
results = await search_service.semantic_search(
    query="machine learning prerequisites",
    intent=QueryIntent.FIND_PREREQUISITES,
    limit=10
)

# Cross-domain discovery
bridges = await search_service.discover_cross_domain_connections(
    domain_a="mathematics",
    domain_b="computer_science",
    bridge_types=["methodological", "skill_based"]
)
```

### Ontology Generation

```python
from core.models.ontology_generator import PydanticOntologyGenerator

# Generate formal ontology from Pydantic schemas
generator = PydanticOntologyGenerator()
ontology = generator.generate_from_module(learning_schemas)

# Apply constraints to Neo4j
constraints = ontology.to_cypher_constraints()
validation_rules = ontology.to_validation_rules()
```

### Semantic Relationship Metadata

All semantic relationships carry rich metadata:

```python
@dataclass
class RelationshipMetadata:
    confidence: float = 1.0           # Confidence in relationship (0-1)
    strength: float = 1.0             # Relationship strength (0-1)
    source: Optional[str] = None      # Source of relationship
    evidence: List[str] = []          # Supporting evidence
    notes: Optional[str] = None       # Human-readable notes
    valid_from: Optional[datetime] = None  # Temporal validity
    valid_until: Optional[datetime] = None
```

### Performance and Scalability

- **Caching**: Relationship inference results cached with TTL
- **Batch processing**: Bulk operations for large datasets
- **A* search**: Optimal path finding with semantic distance heuristics
- **Lazy loading**: Semantic context loaded on demand
- **Index optimization**: Neo4j indexes for semantic relationship queries

## Service-Model Harmony

The service and model layers are designed to work together:

| Model Feature | Service Operation |
|--------------|-------------------|
| `relationship_uids` | `add_relationship()`, `get_relationships()` |
| `content` field | `update_content()`, `get_with_content()` |
| `progress` field | `update_progress()` |
| `status` field | `update_status()` with transitions |
| `validate()` → Result | Error handling with `@boundary_handler` |

## Progress & Status Tracking

Unified across all entities:
- **Progress**: 0-100 percentage for any measurable advancement
  - Task completion
  - Knowledge mastery
  - Habit streaks
  - Goal achievement
- **Status**: Flexible state management
  - Defined per domain (TaskStatus, HabitStatus, etc.)
  - Transition rules enforced at service layer

### Complete Example: Creating a Related Task

```python
from core.models.base_models_consolidated import EntityFactory
from core.services.base_service import BaseService

# Create domain model with relationships
task = EntityFactory.create_with_relationships(
    TaskPure,
    title="Learn Linear Algebra",
    prefix="task",
    relationships={
        "DEVELOPS_MASTERY_OF": ["ku_linear_algebra"],
        "DEPENDS_ON": ["task_calculus_101"],
        "PART_OF": ["goal_mathematics"]
    },
    progress=0.0,
    status="pending"
)

# Service handles graph operations
service = TasksService(backend=task_backend)
result = await service.add_relationship(
    from_uid=task.uid,
    rel_type="TRIGGERS",
    to_uid="habit_daily_math"
)

# Traverse to find learning path
paths = await service.traverse(
    start_uid=task.uid,
    rel_pattern="DEVELOPS_MASTERY_OF+",
    max_depth=3
)
```

## Best Practices

1. **Always think in relationships** - How does this entity connect to others?
2. **Use immutable domain models** - Frozen dataclasses prevent bugs
3. **Return Results, not exceptions** - Consistent error handling
4. **Include relationship UIDs in models** - Enable offline/YAML operations
5. **Validate at boundaries** - Pydantic for external, Result for internal
6. **Leverage the unified base** - Don't recreate what BaseService provides
7. **Keep models graph-aware** - Store connections for Neo4j operations

## Import Migration Guide

### Old vs New Imports
```python
# ❌ Old (pre-consolidation)
from core.models.base_entities import BaseEntity
from core.models.base_models import BasePureModel
from core.services.base_domain_service import BaseDomainService
from core.services.base_knowledge_service import BaseKnowledgeService

# ✅ New (consolidated & relationship-centric)
from core.models.base_models_consolidated import (
    BaseEntity,           # Domain models with relationships
    BaseDTO,             # Transfer objects with relationship metadata
    BaseCreateSchema,    # API validation schemas
    EntityFactory,       # Entity creation with relationships
)
from core.services.base_service import (
    BaseService,         # Unified service base
    Relationship,        # Relationship data structure
    GraphPath,          # Graph traversal results
)
```

### Migration Status: ✅ COMPLETE
- All models migrated to `base_models_consolidated.py`
- All services use unified `BaseService`
- Relationship support added throughout
- Result-based validation everywhere
- Backwards compatibility maintained via aliases

## Graph-First Philosophy

SKUEL is fundamentally a **knowledge graph** application:
1. Knowledge units form the core graph
2. Tasks develop mastery of knowledge
3. Events schedule learning sessions
4. Habits reinforce knowledge retention
5. Goals organize learning objectives

Every feature should consider: **"How does this connect to the graph?"**

## Future Directions

The relationship-centric architecture with semantic enhancement enables:

### Traditional Capabilities
- **Smart Recommendations**: Traverse relationships to suggest next steps
- **Dependency Analysis**: Understand cascading effects of changes
- **Learning Optimization**: Find shortest paths through knowledge
- **Pattern Recognition**: Identify successful learning/habit patterns
- **Collaborative Filtering**: Connect users through shared knowledge graphs

### Semantic-Enhanced Capabilities
- **Intelligent Query Understanding**: Natural language queries mapped to semantic intents
- **Cross-Domain Discovery**: Automatic identification of connections between domains
- **Semantic Path Optimization**: A* search with semantic distance for optimal learning paths
- **Context-Aware Recommendations**: Relationship strength and confidence scoring
- **Ontology-Driven Validation**: Formal domain constraints from Pydantic schemas
- **Temporal Relationship Reasoning**: Time-aware relationship validity
- **Confidence-Based Learning**: Uncertainty-aware knowledge recommendations
- **Pattern-Based Insights**: Discovery of learning patterns through semantic analysis

---

*Last Updated: After integrating semantic enhancement with RDF-inspired thinking, three-phase implementation complete with production-ready semantic capabilities.*