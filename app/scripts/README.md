# SKUEL Database Management Scripts

Scripts for managing the Neo4j database. Ingestion is not a script of its own:
the reconciler is the one ingestion system (`./dev vault-sync --vault content`,
ADR-070 Decision 9).

## Quick Start

### 🚀 Fresh Start

```bash
uv run python scripts/clear_neo4j.py          # type DELETE ALL
./dev vault-sync --vault content              # re-ingest the content vault
```

### 🧹 Clear Database Only

**Remove all data (keep constraints/indexes):**

```bash
uv run python scripts/clear_neo4j.py
```

Prompts: Type `DELETE ALL` to confirm

**Complete reset (remove data + constraints + indexes):**

```bash
uv run python scripts/clear_neo4j.py reset
```

Prompts: Type `DELETE EVERYTHING` to confirm

## Available Scripts

### `clear_neo4j.py`

Flexible database clearing with multiple modes.

**Mode 1: Clear Data (Default)**
```bash
uv run python scripts/clear_neo4j.py
# or
uv run python scripts/clear_neo4j.py clear
```

- Deletes: All nodes and relationships
- Keeps: Constraints and indexes
- Safety: Prompts for `DELETE ALL` confirmation

**Mode 2: Complete Reset**
```bash
uv run python scripts/clear_neo4j.py reset
```

- Deletes: All nodes, relationships, constraints, indexes
- Use for: Completely fresh database
- Safety: Prompts for `DELETE EVERYTHING` confirmation

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

All scripts read connection details from environment variables, with development defaults:

```python
neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
neo4j_user = os.getenv("NEO4J_USERNAME", "neo4j")
```

Passwords are resolved via `get_credential()` (`core.config.credential_store`), which reads the backend `SKUEL_CREDENTIAL_BACKEND` selects and falls back to the environment. Load them once with `uv run python -m core.config`.

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

### 1. Start Fresh

```bash
uv run python scripts/clear_neo4j.py          # DELETE ALL (keeps constraints/indexes)
./dev vault-sync --vault content              # re-ingest the content vault
```

### 2. Complete Database Reset

```bash
uv run python scripts/clear_neo4j.py reset    # DELETE EVERYTHING
uv run python main.py                         # boot recreates constraints + indexes
./dev vault-sync --vault content
```

### 3. Verify What's in Database

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
1. Check Neo4j credentials in `.env` or environment
2. Set password via the credential setup tool: `uv run python -m core.config`
3. Or reset Neo4j password

### Ingestion problems

`./dev vault-sync --vault content` reports per-file errors and warnings; fix the file and
sync again (smart mode re-processes only what changed). `--preview` shows what a sync
would do without writing.

## Script Architecture

The script follows SKUEL patterns:

- ✅ **Result[T]** pattern for error handling
- ✅ **Async/await** for Neo4j operations
- ✅ **Logging** with structured output
- ✅ **Safety confirmations** for destructive ops
- ✅ **Statistics reporting** for transparency
