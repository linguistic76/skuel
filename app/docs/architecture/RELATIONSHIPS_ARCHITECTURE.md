---
title: Relationships Architecture
updated: 2026-01-17
status: current
category: architecture
tags: [architecture, relationships, unified-service, infrastructure]
related: [UNIFIED_RELATIONSHIP_SERVICE.md, RELATIONSHIP_INFRASTRUCTURE_PATTERN.md, ADR-028]
---

# Relationships Architecture

**Last Updated**: 2026-01-17
**Status**: 13 of 14 Domains use UnifiedRelationshipService (Finance is standalone bookkeeping)

> **See Also:** [Relationship Infrastructure Pattern](/docs/patterns/RELATIONSHIP_INFRASTRUCTURE_PATTERN.md) for the foundational mixin layer (`core/infrastructure/relationships/`) - storage, validation, and semantic relationship primitives.

## Current Architecture (January 2026)

### Unified Relationship Architecture

**13 of 14 domains** use `UnifiedRelationshipService` for harmonious architecture via `self.relationships` attribute. Finance is a standalone bookkeeping domain.

| Category | Domains | Relationship Access | Intelligence |
|----------|---------|---------------------|--------------|
| **Activity Domains (6)** | Tasks, Goals, Habits, Events, Choices, Principles | `self.relationships` | Domain-specific intelligence services |
| **Curriculum Domains (3)** | KU, LS, LP | `self.relationships` | Specialized services (KuGraphService, etc.) |
| **Content/Organization (3)** | Journals, Assignments, MOC | `self.relationships` | MocDiscoveryService, etc. |

**Note:** Finance is a standalone bookkeeping domain (no relationship service or intelligence service).

### Activity Domains (6) - UnifiedRelationshipService

Tasks, Goals, Habits, Events, Choices, Principles use `UnifiedRelationshipService`:

```python
from core.models.relationship_registry import TASKS_UNIFIED
from core.services.relationships import UnifiedRelationshipService

service = UnifiedRelationshipService(backend, TASKS_UNIFIED, graph_intel)
knowledge = await service.get_related_uids("knowledge", "task:123")
context = await service.get_cross_domain_context_typed("task:123")
actionable = await service.get_actionable_for_user(user_context)
```

**Old services archived:** `zarchives/relationships/`

### Curriculum Domains (3) + MOC - Unified + Specialized (January 2026)

All curriculum domains and MOC now use `UnifiedRelationshipService` via `self.relationships`:

| Domain | Category | Relationship Service | Specialized Intelligence |
|--------|----------|---------------------|-------------------------|
| **KU** | Curriculum | `ku_service.relationships` | KuGraphService (54k lines), KuSemanticService (20k lines) |
| **LS** | Curriculum | `ls_service.relationships` | LsIntelligenceService |
| **LP** | Curriculum | `lp_service.relationships` | LpIntelligenceService |
| **MOC** | Content/Org | `moc_service.relationships` + `moc_service.section_relationships` | MocDiscoveryService |

**Note:** MOC is architecturally a Content/Organization domain (not Curriculum), but uses the same relationship patterns for knowledge navigation.

**Key Decision (ADR-028):** Specialized services (KuGraphService, KuSemanticService) were **kept** because they provide graph intelligence, not basic relationship CRUD.

**Deleted Services:**
- `moc_relationship_service.py` (~650 lines) - Replaced by UnifiedRelationshipService

**See:** `/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md` for complete documentation.
**See:** ADR-028 for the KU & MOC migration rationale.

---

## Overview

The RelationshipsAdapter enriches the knowledge graph with semantic relationships extracted from YAML frontmatter in markdown files. This allows any entity type (KnowledgeUnit, Task, Event, Habit, and **Learning Schemas**) to define rich relationships that create a more connected and navigable knowledge graph.

**NEW**: Enhanced with **Semantic RDF-Inspired Capabilities** providing precise relationship semantics, confidence scoring, and cross-domain discovery through the three-phase semantic implementation.

## Schema Integration

The relationship system now works seamlessly with the schema-first approach, supporting both traditional entities and new learning schemas.

## Key Features

### Learning-Appropriate Relationship Types

Instead of generic family metaphors, we use domain-specific relationship types:

#### Prerequisites & Enables
- **Prerequisites**: Concepts/tasks that must be understood/completed first
- **Enables**: What this entity unlocks or makes possible

#### Taxonomic Relationships
- **Broader**: Parent concepts in a hierarchy
- **Narrower**: More specific child concepts

#### Lateral Connections
- **RelatedConcepts**: Semantically related entities
- **See Also**: Additional relevant references

#### Application Relationships
- **AppliesTo**: Where this knowledge/skill is applicable
- **UsedBy**: What systems/components use this

### Semantic Enhancement (NEW)

The relationship system now includes **RDF-inspired semantic precision** with:

#### Semantic Relationship Types
- **Namespaced predicates**: `learn:`, `task:`, `cross:`, `skill:`, `concept:`, `time:`
- **Precise semantics**: Replace generic "REQUIRES" with specific "learn:requires_theoretical_understanding"
- **Rich metadata**: Confidence scores, strength values, temporal validity, evidence
- **Cross-domain bridges**: Automatic discovery of interdisciplinary connections

#### Three-Phase Implementation
1. **Phase 1**: Core semantic components (SemanticRelationshipType, SemanticKnowledgeUnit, TripleBuilder)
2. **Phase 2**: Enhanced services (semantic search, A* path generation, migration tools)
3. **Phase 3**: Production features (REST/GraphQL APIs, UI components, deployment)

#### Semantic Capabilities
- **Intent-based search**: 6 query intents (FIND_PREREQUISITES, FIND_NEXT_STEPS, etc.)
- **Confidence scoring**: Relationship strength and confidence metrics (0-1)
- **Cross-domain discovery**: 4 bridge types (direct, analogical, methodological, skill-based)
- **Temporal relationships**: Time-aware validity and scheduling
- **Ontology generation**: Formal domain constraints from Pydantic schemas

## Architecture

### Integration with UnifiedMarkdownSync

The RelationshipsAdapter is located in `/adapters/persistence/relationships_adapter.py` as it handles database persistence of relationships.

```python
class UnifiedMarkdownSync:
    def __init__(self, repository):
        self.repository = repository
        # Import from persistence adapters
        from adapters.persistence.relationships_adapter import RelationshipsAdapter
        self.relationships_adapter = RelationshipsAdapter(repository)

    async def sync_markdown_file(self, file_path: Path):
        # Extract and parse frontmatter
        frontmatter, body = self._extract_frontmatter(content)

        # Create entity (KnowledgeUnit, Task, etc.)
        entity = self._parse_entity(frontmatter, body, file_path)

        # Sync to Neo4j
        await self._sync_to_neo4j(entity)

        # Process relationships if present (optional)
        if "Relationships" in frontmatter:
            await self.relationships_adapter.process_relationships(
                frontmatter,
                entity.uid,
                entity_type
            )
```

### Relationship Processing Flow

1. **Extraction**: Parse Relationships block from YAML
2. **Normalization**: Handle various formats (string, list, comma-separated)
3. **UID Generation**: Create consistent UIDs from titles
4. **Neo4j Creation**: Generate appropriate graph edges with directionality

## YAML Frontmatter Format

### Basic Structure

```yaml
---
uid: ku.python_functions
title: Python Functions
type: KnowledgeUnit

Relationships:
  Prerequisites:
    - Python Variables
    - Control Flow
  Enables: Advanced Python Features
  Broader: Programming Concepts
  Narrower: [Parameters, Return Values, Scope]
  RelatedConcepts:
    - JavaScript Functions
    - Ruby Methods
---
```

### Semantic Relationship Format (NEW)

Enhanced YAML format with semantic precision and metadata:

```yaml
---
uid: ku.machine_learning_fundamentals
title: Machine Learning Fundamentals
type: SemanticKnowledgeUnit

# Traditional relationships (still supported)
Relationships:
  Prerequisites: [Statistics, Linear Algebra, Python Programming]
  Enables: [Deep Learning, Computer Vision, NLP]

# Enhanced semantic relationships with metadata
SemanticRelationships:
  - predicate: "learn:requires_theoretical_understanding"
    object: "ku.statistics_fundamentals"
    confidence: 0.95
    strength: 0.9
    source: "curriculum_design"
    notes: "Strong statistical foundation essential"

  - predicate: "learn:requires_practical_application"
    object: "ku.python_programming"
    confidence: 0.9
    strength: 0.8
    source: "expert_analysis"

  - predicate: "cross:applies_knowledge_to"
    object: "domain.healthcare"
    confidence: 0.85
    strength: 0.7
    evidence: ["medical_imaging", "drug_discovery", "diagnosis_systems"]

# Ontology classification
ontology_class: "ConceptualKnowledge"
semantic_tags: ["algorithm", "mathematical", "applied"]
---
```

### Supported Formats

Each relationship can be specified as:

1. **Single String**
   ```yaml
   Broader: Python Programming
   ```

2. **List Format**
   ```yaml
   Prerequisites:
     - Database Design
     - SQL Basics
   ```

3. **Inline Array**
   ```yaml
   Enables: [User Management, Access Control, Audit Logging]
   ```

4. **Comma Separated**
   ```yaml
   RelatedConcepts: JavaScript, TypeScript, CoffeeScript
   ```

## Neo4j Graph Structure

### Relationship Directionality

Different relationship types have specific directionality patterns:

#### Prerequisites (Incoming)
```cypher
(Prerequisite)-[:REQUIRES]->(ThisEntity)
```
"This entity requires these prerequisites"

#### Enables (Outgoing)
```cypher
(ThisEntity)-[:ENABLES]->(EnabledConcept)
```
"This entity enables these concepts"

#### Broader/Narrower (Hierarchical)
```cypher
(BroaderConcept)-[:HAS_NARROWER]->(ThisEntity)
(ThisEntity)-[:HAS_NARROWER]->(NarrowerConcept)
```

#### Related (Bidirectional)
```cypher
(ThisEntity)-[:RELATED_TO]->(RelatedEntity)
(RelatedEntity)-[:RELATED_TO]->(ThisEntity)
```

### Stub Node Creation

When a relationship references an entity that doesn't exist yet, a stub node is created:

```cypher
CREATE (n:Ku {
  uid: "ku.referenced_concept",
  title: "Referenced Concept",
  is_stub: true,
  created_from: "relationship_reference"
})
```

These stubs are replaced when the actual entity is synced.

### Semantic Neo4j Structure (NEW)

Enhanced relationship storage with semantic metadata:

```cypher
// Semantic relationships with rich metadata
(ku_fundamentals)-[r:REQUIRES_THEORETICAL_UNDERSTANDING {
    confidence: 0.95,
    strength: 0.9,
    source: "curriculum_design",
    notes: "Strong statistical foundation essential",
    created_at: "2025-09-27T10:00:00Z",
    namespace: "learn"
}]->(ku_statistics)

// Cross-domain relationships
(ku_ml)-[r:APPLIES_KNOWLEDGE_TO {
    confidence: 0.85,
    strength: 0.7,
    evidence: ["medical_imaging", "drug_discovery"],
    bridge_type: "methodological",
    namespace: "cross"
}]->(domain_healthcare)

// Temporal relationships with validity
(task_setup)-[r:OCCURS_BEFORE {
    valid_from: "2025-09-27T09:00:00Z",
    valid_until: "2025-12-31T23:59:59Z",
    confidence: 1.0,
    namespace: "time"
}]->(task_implementation)
```

### Semantic Query Examples (NEW)

```cypher
// Find high-confidence prerequisites
MATCH (ku:Ku)-[r:REQUIRES_THEORETICAL_UNDERSTANDING]->(prereq)
WHERE r.confidence > 0.9
RETURN ku.title, prereq.title, r.confidence
ORDER BY r.confidence DESC

// Cross-domain discovery
MATCH (a)-[r]->(b)
WHERE r.namespace = "cross"
  AND r.bridge_type = "methodological"
RETURN a.title, type(r), b.title, r.confidence

// Temporal relationship validation
MATCH (a)-[r]->(b)
WHERE r.namespace = "time"
  AND datetime(r.valid_from) <= datetime()
  AND datetime(r.valid_until) >= datetime()
RETURN a.title, type(r), b.title
```

## Use Cases

### 1. Learning Path Construction (Schema-First)

**New**: Direct integration with LearningPathSchema and LearningPathStepSchema:

```yaml
---
uid: path.python_oop
title: Python Object-Oriented Programming
type: LearningPath

Relationships:
  Prerequisites:
    - path.python_basics
    - path.python_functions
  Enables:
    - path.python_advanced_oop
    - path.design_patterns
  RelatedConcepts:
    - Java OOP
    - C++ Classes

# Schema fields are automatically processed
learning_path:
  difficulty_level: intermediate
  is_sequential: true
  category: programming
---
```

The relationship system enriches LearningPathSchema objects:

```python
from core.models.learning_schemas import LearningPathSchema

# Schema object enriched with relationship data
path = LearningPathSchema(...)
path.prerequisite_path_uids = ["path.python_basics", "path.python_functions"]
path.enables_path_uids = ["path.python_advanced_oop"]  # From relationships

# Vector integration enhances with semantic connections
similar_paths = await vector_learning.find_similar_content(path.uid)
```

### 2. Task Dependencies
```yaml
type: Task
Relationships:
  Prerequisites: Database Migration Complete
  Enables: [API Development, Frontend Integration]
```
Tasks can define their dependencies and what they unlock.

### 3. Habit Progression
```yaml
type: Habit
Relationships:
  Prerequisites: Basic Exercise Routine
  Enables: Advanced Training Programs
  RelatedConcepts: [Nutrition, Sleep, Recovery]
```

### 4. Cross-Domain Connections
```yaml
Relationships:
  RelatedConcepts:
    - Mathematics::Linear Algebra
    - Physics::Mechanics
  AppliesTo:
    - Machine Learning
    - Game Development
```

### 5. Semantic Search and Discovery (NEW)

```python
from core.services.semantic_search_service import SemanticSearchService
from core.models.semantic_relationships import QueryIntent

# Intent-based semantic search
search_service = SemanticSearchService()

# Find prerequisites with confidence filtering
prerequisites = await search_service.semantic_search(
    query="machine learning fundamentals",
    intent=QueryIntent.FIND_PREREQUISITES,
    min_confidence=0.8
)

# Cross-domain discovery
bridges = await search_service.discover_cross_domain_connections(
    domain_a="mathematics",
    domain_b="computer_science",
    bridge_types=["methodological", "skill_based"]
)

# Semantic neighborhood exploration
neighborhood = await search_service.explore_semantic_neighborhood(
    center_uid="ku.linear_algebra",
    radius=2,
    relationship_types=["learn:requires_theoretical_understanding", "cross:applies_knowledge_to"]
)
```

### 6. Learning Path Optimization (NEW)

```python
from core.services.learning_path_service_semantic import LearningPathServiceSemantic

path_service = LearningPathServiceSemantic()

# Generate optimal path using A* with semantic distance
optimal_path = await path_service.generate_optimal_path(
    start_uid="ku.programming_basics",
    goal_uid="ku.machine_learning_advanced",
    learning_style="visual",  # Affects heuristic weighting
    constraints={"max_cognitive_load": 0.8}
)

# Analyze path characteristics
analysis = await path_service.analyze_path_semantics(optimal_path)
# Returns: cognitive_load, semantic_distance, cross_domain_opportunities
```

## Benefits

### 1. Rich Knowledge Graph
- Transforms flat files into interconnected graph
- Enables graph traversal for discovery
- Supports multiple relationship types

### 2. Learning Intelligence
- AskesisService can leverage relationships for recommendations
- Prerequisites ensure proper learning order
- Related concepts enable lateral exploration

### 3. Maintainability
- Relationships defined with content (single source of truth)
- Optional processing (doesn't break existing files)
- Clean separation of concerns

### 4. Extensibility
- Easy to add new relationship types
- Works with all entity types
- Can be queried via Neo4j for analytics

### 5. Semantic Intelligence (NEW)
- **Precise semantics**: RDF-inspired relationship types with clear meaning
- **Confidence scoring**: Uncertainty-aware recommendations and learning paths
- **Cross-domain discovery**: Automatic identification of interdisciplinary connections
- **Intent-based search**: Natural language queries mapped to semantic operations
- **Temporal reasoning**: Time-aware relationship validity and scheduling
- **Ontology validation**: Formal domain constraints ensure data integrity

## Query Examples

### Find Prerequisites for a Concept
```cypher
MATCH (ku:Ku {uid: "ku.python_classes"})
MATCH (ku)-[:REQUIRES]->(prereq)
RETURN prereq.title, prereq.uid
```

### Find Learning Path
```cypher
MATCH path = (start:Ku)-[:ENABLES*]->(end:Ku)
WHERE start.uid = "ku.python_basics"
RETURN path
```

### Find Related Concepts
```cypher
MATCH (ku:Ku {uid: "ku.recursion"})
MATCH (ku)-[:RELATED_TO]-(related)
RETURN related.title, related.uid
```

### Find What a Task Enables
```cypher
MATCH (t:Task {uid: "task.setup_database"})
MATCH (t)-[:ENABLES]->(enabled)
RETURN enabled.title, enabled.type
```

## Implementation Details

### RelationshipsAdapter Class

Located in `/adapters/persistence/relationships_adapter.py`

Key methods:
- `extract_relationships()`: Parse YAML Relationships block
- `create_relationships()`: Generate Neo4j relationship tuples
- `process_relationships()`: Complete pipeline from extraction to Neo4j

### Schema Integration

The RelationshipsAdapter now works directly with schemas:

```python
from core.models.learning_schemas import LearningPathSchema, LearningPathStepSchema
from adapters.persistence.relationships_adapter import RelationshipsAdapter

class SchemaRelationshipProcessor:
    def __init__(self, relationships_adapter: RelationshipsAdapter):
        self.relationships_adapter = relationships_adapter

    async def process_learning_path_relationships(
        self,
        path: LearningPathSchema,
        frontmatter: dict
    ) -> LearningPathSchema:
        """Process relationships and enrich schema"""

        # Extract relationship data
        if "Relationships" in frontmatter:
            await self.relationships_adapter.process_relationships(
                frontmatter, path.uid, "Lp"
            )

        # Enrich schema with relationship UIDs
        if "Prerequisites" in frontmatter.get("Relationships", {}):
            prereq_titles = frontmatter["Relationships"]["Prerequisites"]
            path.prerequisite_path_uids.extend(
                [self._title_to_uid(title) for title in prereq_titles]
            )

        return path
```

### Vector-Enhanced Relationships

Relationships now combine explicit graph connections with semantic vector similarity:

```python
class VectorEnhancedRelationships:
    async def find_related_paths(
        self,
        path: LearningPathSchema
    ) -> dict[str, list[LearningPathSchema]]:
        """Find related paths using both relationships and vectors"""

        # Graph-based relationships (explicit)
        graph_related = await self.get_graph_relationships(path.uid)

        # Vector-based similarities (semantic)
        vector_similar = await self.vector_learning.find_similar_content(
            path.uid, limit=10
        )

        return {
            "explicit_relationships": graph_related,
            "semantic_similarities": vector_similar,
            "combined_recommendations": self._merge_recommendations(
                graph_related, vector_similar
            )
        }
```

### Supported Relationship Mappings

```python
RELATIONSHIP_MAPPINGS = {
    # Learning flow
    "prerequisites": ("REQUIRES", "incoming"),
    "enables": ("ENABLES", "outgoing"),

    # Taxonomy
    "broader": ("HAS_NARROWER", "incoming"),
    "narrower": ("HAS_NARROWER", "outgoing"),

    # Lateral
    "related": ("RELATED_TO", "bidirectional"),

    # Application
    "applies_to": ("APPLIES_TO", "outgoing"),
    "used_by": ("USED_BY", "outgoing")
}
```

## Testing

Run tests with:
```bash
poetry run python tests/test_relationships_adapter.py
```

Tests cover:
- Extraction from various YAML formats
- Normalization of values
- UID generation
- Neo4j relationship creation
- All entity types

## Future Enhancements

1. **Relationship Strength**: Add weights to relationships
2. **Temporal Relationships**: Before/After/During for events
3. **Conditional Relationships**: Prerequisites based on context
4. **Relationship Validation**: Verify referenced entities exist
5. **Bulk Processing**: Efficient batch relationship creation
6. **Visualization**: Graph visualization of relationships

## Migration Guide

### Adding to Existing Files

Simply add a Relationships block to any markdown file:

```yaml
---
existing: fields
remain: unchanged

Relationships:
  Prerequisites: [Concept A, Concept B]
  Enables: Advanced Topic
---
```

### No Breaking Changes

- Files without Relationships blocks work as before
- Processing is optional and isolated
- Errors in relationships don't affect entity sync

## Conclusion

The RelationshipsAdapter transforms SKUEL from a collection of isolated knowledge units into a rich, interconnected knowledge graph. By using learning-appropriate relationship types and seamless YAML integration, it enhances the system's ability to provide intelligent guidance while maintaining the simplicity of markdown-based content management.