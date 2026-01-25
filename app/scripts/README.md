# SKUEL Database Management Scripts

Scripts for managing Neo4j database and curriculum ingestion.

## Quick Start

### 🚀 Fresh Start with Mindfulness 101 (Recommended)

**One command to clear database and load curriculum:**

```bash
poetry run python scripts/fresh_start_mindfulness.py
```

This will:
1. Prompt for confirmation (type `FRESH START`)
2. Delete all existing Neo4j data
3. Ingest complete Mindfulness 101 bundle (19 entities)
4. Show detailed results

### 🧹 Clear Database Only

**Remove all data (keep constraints/indexes):**

```bash
poetry run python scripts/clear_neo4j.py
```

Prompts: Type `DELETE ALL` to confirm

**Complete reset (remove data + constraints + indexes):**

```bash
poetry run python scripts/clear_neo4j.py reset
```

Prompts: Type `DELETE EVERYTHING` to confirm

**Clear specific bundle only:**

```bash
poetry run python scripts/clear_neo4j.py bundle mindfulness_101
```

## Available Scripts

### `fresh_start_mindfulness.py`

Combined script for clean slate ingestion.

**Default Usage:**
```bash
poetry run python scripts/fresh_start_mindfulness.py
```

**Custom Bundle:**
```bash
poetry run python scripts/fresh_start_mindfulness.py yaml_templates/domains/study_skills_101
```

**What it does:**
1. ✅ Counts existing data
2. 🗑️ Deletes all nodes and relationships
3. 📦 Ingests domain bundle via manifest
4. 📊 Reports detailed statistics
5. ✅ Verifies final state

**Output:**
```
======================================================================
  FRESH START: Mindfulness 101 Domain Bundle
======================================================================

📊 Found 0 existing nodes
🗑️  Deleting all nodes and relationships...
✅ Deleted 0 nodes successfully

📦 Ingesting bundle from: yaml_templates/domains/mindfulness_101
✅ Knowledge unit created: ku:breath-awareness-basics
✅ Knowledge unit created: ku:posture-basics
...

======================================================================
RESULTS
======================================================================

📦 Bundle: mindfulness_101
   Total attempted: 19
   ✅ Successful: 19
   ❌ Failed: 0

✅ Entities Created:
   • ku:breath-awareness-basics
   • ku:posture-basics
   • ku:mind-wandering-happens
   • ls:mindfulness-101:step-1
   • ls:mindfulness-101:step-2
   • lp:mindfulness-101
   • principle:small-steps
   • principle:attention-over-intensity
   • choice:2-minutes-right-now
   • choice:2-minutes-before-bed
   • choice:label-one-wander
   • habit:daily-2min-breath
   • habit:label-wander-daily
   • task:log-first-5-sessions
   • task:reflect-on-first-week
   • event:practice-block-2min
   • goal:mindfulness-beginner

📊 Final database stats:
   Total nodes: 19

======================================================================
  ✅ FRESH START COMPLETE!
======================================================================
```

### `clear_neo4j.py`

Flexible database clearing with multiple modes.

**Mode 1: Clear Data (Default)**
```bash
poetry run python scripts/clear_neo4j.py
# or
poetry run python scripts/clear_neo4j.py clear
```

- Deletes: All nodes and relationships
- Keeps: Constraints and indexes
- Safety: Prompts for `DELETE ALL` confirmation

**Mode 2: Complete Reset**
```bash
poetry run python scripts/clear_neo4j.py reset
```

- Deletes: All nodes, relationships, constraints, indexes
- Use for: Completely fresh database
- Safety: Prompts for `DELETE EVERYTHING` confirmation

**Mode 3: Bundle-Specific Clear**
```bash
poetry run python scripts/clear_neo4j.py bundle mindfulness_101
```

- Deletes: Only entities with UIDs matching bundle
- Keeps: Everything else
- Safer option for incremental changes

**Output:**
```
📊 Counting existing data...
   Found 157 nodes
   Found 89 relationships
🗑️  Deleting all nodes and relationships...
✅ Deleted 157 nodes and their relationships
🔍 Checking constraints...
   Found 12 constraints (keeping for schema)
🔍 Checking indexes...
   Found 8 indexes (keeping for performance)
✅ Database successfully cleared!
```

## Configuration

All scripts use these defaults (can be changed in script):

```python
uri = "bolt://localhost:7687"
username = "neo4j"
password = "password"
```

To use different credentials, edit the script or modify the function calls.

## Safety Features

### Confirmation Prompts

All destructive operations require explicit confirmation:

- **Clear data**: Type `DELETE ALL`
- **Complete reset**: Type `DELETE EVERYTHING`
- **Fresh start**: Type `FRESH START`

### Statistics Reporting

Scripts show:
- ✅ What will be deleted (before deletion)
- ✅ What was deleted (after deletion)
- ✅ What was created (after ingestion)
- ✅ Verification of final state

### Error Handling

- Validates Neo4j connection
- Reports ingestion failures with details
- Verifies deletions succeeded
- Shows which entities failed and why

## Common Workflows

### 1. Start Fresh with Mindfulness 101

```bash
# One command!
poetry run python scripts/fresh_start_mindfulness.py
```

### 2. Clear and Load Different Bundle

```bash
# Clear database
poetry run python scripts/clear_neo4j.py

# Then use ingestion example
poetry run python examples/yaml_ingestion_example.py
```

### 3. Replace One Bundle with Another

```bash
# Clear specific bundle
poetry run python scripts/clear_neo4j.py bundle mindfulness_101

# Ingest new bundle
poetry run python examples/yaml_ingestion_example.py
```

### 4. Complete Database Reset

```bash
# Nuclear option - removes everything
poetry run python scripts/clear_neo4j.py reset

# Then recreate constraints and ingest
poetry run python scripts/fresh_start_mindfulness.py
```

### 5. Verify What's in Database

After any operation, check Neo4j:

```bash
# Open Neo4j Browser
open http://localhost:7474

# Run query
MATCH (n) RETURN n LIMIT 25
```

Or count entities:

```cypher
// Count by type
MATCH (n)
RETURN labels(n) as type, count(n) as count
ORDER BY count DESC
```

## Troubleshooting

### Connection Refused

```
Error: Could not connect to Neo4j
```

**Solution:**
1. Check Neo4j is running: `neo4j status`
2. Start Neo4j: `neo4j start`
3. Verify URI: `bolt://localhost:7687`

### Authentication Failed

```
Error: Invalid username or password
```

**Solution:**
1. Check Neo4j credentials
2. Update script with correct username/password
3. Or reset Neo4j password

### Partial Ingestion

```
Total attempted: 19
✅ Successful: 15
❌ Failed: 4
```

**Solution:**
1. Review error details in output
2. Check YAML file syntax
3. Verify entity relationships exist
4. Re-run after fixing issues

### Constraint Violations

```
Error: Node(123) already exists with uid 'ku:example'
```

**Solution:**
1. Clear database first: `poetry run python scripts/clear_neo4j.py`
2. Then re-ingest bundle

## Next Steps

After successful ingestion:

1. **Explore in Neo4j Browser**: http://localhost:7474
2. **Run example queries**: See bundle README for Cypher examples
3. **Create more bundles**: Use Mindfulness 101 as template
4. **Test relationships**: Verify graph connections

## Script Architecture

Both scripts follow SKUEL patterns:

- ✅ **Result[T]** pattern for error handling
- ✅ **Async/await** for Neo4j operations
- ✅ **Logging** with structured output
- ✅ **Safety confirmations** for destructive ops
- ✅ **Statistics reporting** for transparency
