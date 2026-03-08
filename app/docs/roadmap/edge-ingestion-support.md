# Edge Ingestion Support

*Created: 2026-03-07*
*Completed: 2026-03-08*

**Status:** Complete

## Summary

Standalone edge YAML files (`type: Edge`) are ingested into Neo4j as typed, evidence-bearing relationships between entities.

## What Was Built

### Detection

`is_edge_type()` in `detector.py` checks for `type: Edge` in parsed YAML. Edges are NOT entities — they bypass `EntityType` detection entirely.

### Validation

`validate_edge_data()` in `validator.py` enforces:
- `from` UID must be present
- `to` UID must be present
- `relationship` must be a valid `RelationshipName` enum value
- `confidence` must be 0.0-1.0
- `polarity` must be -1, 0, or 1
- `temporality` must be one of: minutes, hours, days, chronic
- `source` must be one of: self_observation, research, teacher, clinical

### Preparation

`prepare_edge_data()` in `preparer.py` normalizes UIDs (colon to dot) and extracts evidence properties into a structured dict with `from_uid`, `to_uid`, `relationship`, and `properties`.

### Ingestion

`UnifiedIngestionService.ingest_edge()` runs raw Cypher (not BulkIngestionEngine, since edges create relationships, not nodes):

```cypher
MATCH (a {uid: $from_uid})
MATCH (b {uid: $to_uid})
MERGE (a)-[r:EXACERBATED_BY]->(b)
SET r += $props
```

If either entity is missing, returns a `NotFound` error identifying which UID(s) don't exist.

### Single-File and Batch Support

- `ingest_file()` detects `type: Edge` and routes to `ingest_edge()`
- `batch.py` marks edge data with `_is_edge` sentinel for downstream routing during directory ingestion

### Evidence Relationship Types

Five evidence types in `RelationshipName` enum:

| Type | Meaning |
|------|---------|
| `EXACERBATED_BY` | A worsens B |
| `REDUCED_BY` | A lessens B |
| `CORRELATED_WITH` | A and B co-occur |
| `CAUSES` | A directly causes B |
| `PRECEDES` | A temporally precedes B |

## Key Files

| File | Role |
|------|------|
| `core/services/ingestion/detector.py` | `is_edge_type()` |
| `core/services/ingestion/validator.py` | `validate_edge_data()` |
| `core/services/ingestion/preparer.py` | `prepare_edge_data()` |
| `core/services/ingestion/unified_ingestion_service.py` | `ingest_edge()` |
| `core/services/ingestion/batch.py` | Batch edge handling |
| `yaml_templates/_schemas/edge_template.yaml` | Full field reference |
| `yaml_templates/edges/caffeine_exacerbates_buzzing.yaml` | Working example |

## Open Questions

1. Should evidence relationships be additive (multiple edges between same nodes) or merged? Currently uses MERGE — same from/to/type updates rather than duplicates.
2. Should confidence decay over time without re-observation?
3. Should edge ingestion support markdown files (frontmatter + evidence body)?
