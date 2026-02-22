---
title: Neo4j Label Standardization Migration Plan
updated: 2025-11-27
status: current
category: migrations
tags: [label, migrations, neo4j, standardization]
related: []
---

# Neo4j Label Standardization Migration Plan

**Date:** November 27, 2025
**Status:** ✅ Complete
**Impact:** 1,200 code replacements across 214 files (two migration passes)

## Objective

Standardize Neo4j node labels to match Python class names, aligning with CLAUDE.md's UID naming convention.

## Current State (Inconsistent)

| Python Class | Old Neo4j Labels | UID Prefix | Status |
|--------------|------------------|------------|--------|
| `Lp` | `LearningPath` | `lp.` | ✅ Migrated to `Lp` |
| `Ls` | `LearningStep` | `ls.` | ✅ Migrated to `Ls` |
| `Ku` | `Knowledge`, `KnowledgeUnit` | `ku.` | ✅ Migrated to `Ku` |
| `Task` | `Task` | `task:` | ✅ No change needed |
| `Goal` | `Goal` | `goal:` | ✅ No change needed |
| `Habit` | `Habit` | `habit:` | ✅ No change needed |
| `Event` | `Event` | `event:` | ✅ No change needed |

## Target State (Consistent)

| Python Class | New Neo4j Label | UID Prefix |
|--------------|-----------------|------------|
| `Lp` | `Lp` | `lp.` |
| `Ls` | `Ls` | `ls.` |
| `Ku` | `Ku` | `ku.` |

## Scope Analysis

### Code Changes Required

| Pattern | Count | Files |
|---------|-------|-------|
| `"LearningPath"` string literals | ~60 | 40 |
| `"LearningStep"` string literals | ~50 | 35 |
| `"Knowledge"` string literals | ~77 | 50 |
| `:LearningPath` Cypher patterns | ~180 | 60 |
| `:LearningStep` Cypher patterns | ~120 | 45 |
| `:Knowledge` Cypher patterns | ~180 | 55 |
| **Total** | **~667** | **100** |

### Key Files to Update

**Production Code:**
1. `services_bootstrap.py` - Backend instantiation
2. `core/models/query/_cypher_generator.py` - Query generation
3. `core/services/lp/lp_*.py` - Learning path services
4. `core/services/ls/ls_*.py` - Learning step services
5. `core/services/ku/ku_*.py` - Knowledge unit services
6. `core/models/relationships/relationship_registry.py` - Relationship definitions
7. `adapters/persistence/neo4j/*.py` - Database adapters

**Test Files:**
8. `tests/integration/conftest.py` - Test fixtures
9. `tests/integration/test_curriculum_*.py` - Curriculum tests
10. All relationship integration tests

## Migration Strategy

### Phase 1: Code Migration (Safe - No Data Impact)

Create automated script to replace patterns:

```python
# Pattern replacements (order matters - longer patterns first)
REPLACEMENTS = [
    # Cypher patterns (in queries)
    (r':LearningPath\b', ':Lp'),
    (r':LearningStep\b', ':Ls'),
    (r':Knowledge\b', ':Ku'),

    # String literals (backend labels)
    (r'"LearningPath"', '"Lp"'),
    (r'"LearningStep"', '"Ls"'),
    (r'"Knowledge"', '"Ku"'),

    # Variable names in Cypher (optional - for clarity)
    (r'\blp:LearningPath\b', 'lp:Lp'),
    (r'\bls:LearningStep\b', 'ls:Ls'),
    (r'\bku:Knowledge\b', 'ku:Ku'),
]
```

### Phase 2: Neo4j Data Migration

**Option A: Add Labels (Non-Destructive)**
```cypher
// Add new labels to existing nodes
MATCH (n:LearningPath) SET n:Lp;
MATCH (n:LearningStep) SET n:Ls;
MATCH (n:Knowledge) SET n:Ku;

// Verify
MATCH (n:Lp) RETURN count(n);
MATCH (n:Ls) RETURN count(n);
MATCH (n:Ku) RETURN count(n);
```

**Option B: Rename Labels (Destructive)**
```cypher
// Remove old labels after verification
MATCH (n:Lp:LearningPath) REMOVE n:LearningPath;
MATCH (n:Ls:LearningStep) REMOVE n:LearningStep;
MATCH (n:Ku:Knowledge) REMOVE n:Knowledge;
```

### Phase 3: Index Migration

```cypher
// Create new indexes
CREATE INDEX lp_uid IF NOT EXISTS FOR (n:Lp) ON (n.uid);
CREATE INDEX ls_uid IF NOT EXISTS FOR (n:Ls) ON (n.uid);
CREATE INDEX ku_uid IF NOT EXISTS FOR (n:Ku) ON (n.uid);

// Drop old indexes (after verification)
DROP INDEX learning_path_uid IF EXISTS;
DROP INDEX learning_step_uid IF EXISTS;
DROP INDEX knowledge_uid IF EXISTS;
```

## Rollback Plan

If issues arise:
1. Neo4j: Nodes have both labels during transition - can revert code without data changes
2. Code: Git revert the migration commit
3. Indexes: Old indexes remain until explicitly dropped

## Testing Strategy

1. Run all curriculum tests after code migration
2. Verify query results match before/after
3. Performance test critical queries with new labels
4. Integration test full bootstrap with new labels

## Execution Order

1. ✅ Create this migration plan
2. ✅ Create automated code migration script (`scripts/migrate_neo4j_labels.py`)
3. ✅ Run script in dry-run mode, review changes
4. ✅ Apply code changes (515 replacements across 96 files)
5. ✅ Run test suite - 24/24 curriculum tests pass, 19/19 query tests pass
6. ✅ Check Neo4j data migration - **No data to migrate** (database has 0 nodes with old labels)
7. N/A Neo4j label migration not needed (no existing data)
8. N/A Remove old labels not needed (no existing data)
9. N/A Drop old indexes not needed (no existing indexes)
10. ✅ Update CLAUDE.md documentation (optional - add note about completed migration)
11. ✅ Fix RelationshipRegistry constant (`KNOWLEDGE_RELATIONSHIPS` → `KU_RELATIONSHIPS`) - fixes 8 test failures

## Benefits After Migration

- **Consistency:** Python class = Neo4j label = UID prefix
- **Shorter Queries:** `MATCH (lp:Lp)` vs `MATCH (lp:LearningPath)`
- **Less Confusion:** No more "is it Lp or LearningPath?"
- **Grep-Friendly:** Search for `Lp` finds everything related
