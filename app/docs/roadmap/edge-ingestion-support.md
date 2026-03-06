# Roadmap: Edge Ingestion Support

**Status:** Not started
**Priority:** Next after template evolution work
**Depends on:** YAML template evolution (complete)

## Summary

Enable standalone edge YAML files to be ingested into Neo4j as typed, evidence-bearing relationships between entities.

## Current State

- Edge YAML template exists at `yaml_templates/_schemas/edge_template.yaml`
- Example edge at `yaml_templates/edges/caffeine_exacerbates_buzzing.yaml`
- `TYPE_MAPPING` in `detector.py` does NOT include `"edge"` or `"relationship"`
- No `EntityIngestionConfig` for edges (edges are not entities)
- Evidence relationships like `EXACERBATED_BY` are not yet in `RelationshipName` enum

## Implementation Plan

### 1. TYPE_MAPPING Addition

Add edge detection to `core/services/ingestion/detector.py`:

```python
# In TYPE_MAPPING or separate EDGE_TYPE_MAPPING
"edge": "EDGE"
"relationship": "EDGE"
```

Edges are NOT entities, so they should not map to `EntityType`. A separate detection path is needed.

### 2. Edge-Specific Validation

Before creating a relationship:
- `from` UID must reference an existing entity in Neo4j
- `to` UID must reference an existing entity in Neo4j
- `relationship` must be a valid `RelationshipName` enum value (or allowlisted evidence type)
- `confidence` must be 0.0-1.0
- `polarity` must be -1, 0, or 1
- `temporality` must be one of: minutes, hours, days, chronic
- `source` must be one of: self_observation, research, teacher, clinical

### 3. Property Mapping to Neo4j

Edge properties stored directly on the Neo4j relationship:

```cypher
MATCH (from:Entity {uid: $from_uid})
MATCH (to:Entity {uid: $to_uid})
CREATE (from)-[r:EXACERBATED_BY {
  evidence: $evidence,
  confidence: $confidence,
  polarity: $polarity,
  temporality: $temporality,
  source: $source,
  observed_at: $observed_at,
  created_at: datetime()
}]->(to)
```

### 4. New Evidence Relationship Types

Add to `RelationshipName` enum:
- `EXACERBATED_BY` - A worsens B
- `REDUCED_BY` - A lessens B
- `CORRELATED_WITH` - A and B co-occur
- `CAUSES` - A directly causes B
- `PRECEDES` - A temporally precedes B

### 5. Ingestion Pipeline Changes

The `UnifiedIngestionService` needs a separate code path for edges:
- Detect `type: Edge` in YAML
- Skip entity creation (no node)
- Validate from/to UIDs exist
- Create relationship with evidence properties

### 6. Batch Edge Ingestion

Support ingesting a directory of edge files:
- Read all edge YAML files
- Group by from/to pairs (merge evidence)
- Validate all referenced UIDs
- Create relationships in batch

## Open Questions

1. Should evidence relationships be additive (multiple edges between same nodes) or merged?
2. Should confidence decay over time without re-observation?
3. How do evidence edges interact with the existing `RelationshipName` enum?
4. Should edge ingestion support markdown files (frontmatter + evidence body)?

## Timeline

After the YAML template evolution is complete and Ku ingestion is verified working.
