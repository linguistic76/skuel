# SKUEL Quick Start - Mindfulness 101 Demo

## True Fresh Start (Recommended)

### Step 1: Complete Database Reset

**Remove EVERYTHING (data + constraints + indexes):**

```bash
poetry run python scripts/clear_neo4j.py reset
```

**When prompted, type:** `DELETE EVERYTHING`

This gives you a completely clean Neo4j database - like a fresh install.

### Step 2: Ingest Mindfulness 101

**Load the complete curriculum bundle:**

```bash
poetry run python scripts/fresh_start_mindfulness.py
```

**When prompted, type:** `FRESH START`

This will:
- Create fresh constraints for the curriculum entities
- Ingest all Knowledge Units (3)
- Ingest all Learning Steps (2)
- Ingest the Learning Path (1)
- **Note**: Supporting entities (principles, habits, tasks, etc.) will show in the manifest but won't be ingested yet - they need handlers added to YamlIngestionService

### Step 3: Verify in Neo4j Browser

**Open:** http://localhost:7474

**Run:**
```cypher
// See what was created
MATCH (n) RETURN n LIMIT 25

// Count by type
MATCH (n)
RETURN labels(n) as type, count(n) as count
ORDER BY count DESC

// View the learning path structure
MATCH (lp:Lp {uid: 'lp:mindfulness-101'})
OPTIONAL MATCH (lp)-[:HAS_STEP]->(ls:Ls)
OPTIONAL MATCH (ls)-[:PRIMARY_KNOWLEDGE]->(ku:Curriculum)
RETURN lp, ls, ku
```

## Current State

### ✅ What Works Now

**Core Curriculum Ingestion** (6 entities):
- 3 Knowledge Units (ku)
- 2 Learning Steps (ls)
- 1 Learning Path (lp)

These use the YamlIngestionService and will ingest successfully.

### 🚧 What Needs Extension

**Supporting Entities** (13 entities):
- 2 Principles
- 3 Choices
- 2 Habits
- 2 Tasks
- 1 Event
- 1 Goal
- 2 Conversations (not created yet)

These YAML files exist but YamlIngestionService doesn't have handlers for them yet.

## Expected Output

### Reset Output:
```
⚠️  WARNING: This will DELETE ALL DATA, CONSTRAINTS, AND INDEXES!
   Connection: bolt://localhost:7687

   Type 'DELETE EVERYTHING' to confirm: DELETE EVERYTHING

🗑️  Deleting all nodes and relationships...
🗑️  Dropping all constraints...
   Dropped 12 constraints
🗑️  Dropping all indexes...
   Dropped 8 indexes
✅ Database completely cleared (data, constraints, indexes)
```

### Fresh Start Output:
```
======================================================================
  FRESH START: Mindfulness 101 Domain Bundle
======================================================================

📊 Found 0 existing nodes
✅ Deleted 0 nodes successfully

📦 Ingesting bundle from: yaml_templates/domains/mindfulness_101
✅ Knowledge unit created: ku:breath-awareness-basics
✅ Knowledge unit created: ku:posture-basics
✅ Knowledge unit created: ku:mind-wandering-happens
✅ Learning step created: ls:mindfulness-101:step-1
✅ Learning step created: ls:mindfulness-101:step-2
✅ Learning path created: lp:mindfulness-101

📊 Final database stats:
   Total nodes: 6

======================================================================
  ✅ FRESH START COMPLETE!
======================================================================
```

## Next: Extend the Ingestion Service

To ingest the full bundle (all 19 entities), we need to add handlers to YamlIngestionService for:

1. **Principles** - Add `ingest_principle_yaml()`
2. **Choices** - Add `ingest_choice_yaml()`
3. **Habits** - Add `ingest_habit_yaml()`
4. **Tasks** - Add `ingest_task_yaml()`
5. **Events** - Add `ingest_event_yaml()`
6. **Goals** - Add `ingest_goal_yaml()`

Each follows the same pattern as Knowledge/LearningStep:
```python
async def ingest_principle_yaml(self, yaml_path: Path) -> Result[Principle]:
    # 1. Load YAML
    # 2. Validate type
    # 3. Tier 1: Pydantic validation
    # 4. Tier 2: Convert to DTO
    # 5. Tier 3: Convert to Pure
    # 6. Save via UniversalNeo4jBackend
```

## Adjusting the Demo

After ingestion, you can adjust entities directly in Neo4j Browser:

```cypher
// Update a knowledge unit
MATCH (ku:Curriculum {uid: 'ku:breath-awareness-basics'})
SET ku.content = 'Your updated content here'
RETURN ku

// Update a learning step
MATCH (ls:Ls {uid: 'ls:mindfulness-101:step-1'})
SET ls.title = 'Your new title'
RETURN ls
```

Or edit the YAML files and re-run the ingestion scripts.

## Troubleshooting

### Neo4j Not Running
```bash
# Check status
neo4j status

# Start Neo4j
neo4j start
```

### Connection Refused
Check URI in scripts is correct: `bolt://localhost:7687`

### No Entities Created
Verify YAML files exist:
```bash
ls yaml_templates/domains/mindfulness_101/*.yaml
```

Should show 19 YAML files + manifest.yaml + README.md

## Summary

**Your workflow:**
1. `poetry run python scripts/clear_neo4j.py reset` → Type `DELETE EVERYTHING`
2. `poetry run python scripts/fresh_start_mindfulness.py` → Type `FRESH START`
3. Open http://localhost:7474 and explore!

**You'll get:**
- Clean Neo4j database
- 6 core curriculum entities (ku, ls, lp)
- Ready to adjust and experiment

**To get all 19 entities:**
- Extend YamlIngestionService with handlers for supporting entity types
- Re-run fresh_start_mindfulness.py
