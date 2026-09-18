---
updated: 2026-09-18
---

# SKUEL Quick Start - Mindfulness 101 Demo

The smallest end-to-end curriculum in SKUEL: one learning path, three path steps and one
exercise, authored as Markdown in the **content vault** and ingested by the content-vault door.
This walkthrough resets the graph, ingests the vault, and shows you the result in the Neo4j
Browser.

## True Fresh Start (Recommended)

### Step 0: Confirm the content vault holds the bundle

The bundle is authored in the content vault — an Obsidian vault outside this repository, at
`INGESTION_PATH` (default `/home/mike/0bsidian/0vault/`):

| File | Entity | UID |
|---|---|---|
| `Lp/lp_mindfulness-101.md` | LearningPath | `lp.mindfulness-101` |
| `Ps/Ps_dev/mindfulness-101_Ps.md` | PathStep (intro) | `ps.mindfulness-101.intro` |
| `Ps/Ps_dev/mindfulness-101_step-1_Ps.md` | PathStep | `ps.mindfulness-101.step-1` |
| `Ps/Ps_dev/mindfulness-101_step-2_Ps.md` | PathStep | `ps.mindfulness-101.step-2` |
| `Exer/mindfulness-starter_exer.md` | Exercise | `ex.mindfulness.starter-practice` |

A clean clone has no such vault, and Step 1 is destructive, so check the files are there first:

```bash
ls "${INGESTION_PATH:-/home/mike/0bsidian/0vault}"/Lp/lp_mindfulness-101.md \
   "${INGESTION_PATH:-/home/mike/0bsidian/0vault}"/Ps/Ps_dev/mindfulness-101*.md \
   "${INGESTION_PATH:-/home/mike/0bsidian/0vault}"/Exer/mindfulness-starter_exer.md
```

If `ls` reports a missing file, stop: point `INGESTION_PATH` at a vault that holds the bundle
before resetting anything. (`./dev vault-sync --vault content --preview` is the dry run of the
sync itself, but it lists only new and changed files — an already-synced bundle is not in it.)

### Step 1: Complete Database Reset

**Remove EVERYTHING (data + constraints + indexes):**

```bash
uv run python scripts/clear_neo4j.py reset
```

**When prompted, type:** `DELETE EVERYTHING`

This gives you a completely clean Neo4j database - like a fresh install. It targets whatever
`NEO4J_URI` in `.env` names — on this repo's default configuration that is the AuraDB Free
instance, not a local container; read the URI the prompt echoes back before you confirm.

### Step 2: Ingest the content vault

```bash
./dev vault-sync --vault content
```

This runs the one-shot content-vault reconciler (`scripts/vault_bridge_sync.py`) over every
typed file in the vault — the bundle above among them, plus every other Ku, PathStep,
LearningPath and Exercise the vault holds. Files without a `type:` frontmatter field are set
aside (they are notes, not entities); unchanged files are skipped on later runs.

**What you'll see** — a `=== VaultSyncStats ===` block, one line per counter (`entries_ingested`,
`edges_written`, `entries_failed`, the ignored-file reasons), followed by the embedding drain
when the app runs at the FULL intelligence tier. The bundle's entities and their edges
(`(LearningPath)-[:HAS_STEP]->(PathStep)`, `(PathStep)-[:USES_KU]->(Ku)`) are written in this
step.

### Step 3: Verify in Neo4j Browser

**Open:** the browser for the instance `NEO4J_URI` names (the AuraDB console's "Query" tab, or
http://localhost:7474 for the local sandbox).

**Run:**
```cypher
// Count by entity type
MATCH (n:Entity)
RETURN n.entity_type AS type, count(n) AS count
ORDER BY count DESC

// View the learning path structure
MATCH (lp:Entity {uid: 'lp.mindfulness-101'})
OPTIONAL MATCH (lp)-[:HAS_STEP]->(ps:Entity)
OPTIONAL MATCH (ps)-[:USES_KU]->(ku:Entity)
RETURN lp, ps, ku
```

## Adjusting the Demo

The vault is the source of truth. Edit the Markdown files in the vault — the frontmatter
(`title`, `uid`, the edge-carrying fields) and the body — then re-run Step 2: only the files
that changed are re-ingested, and a target dropped from a frontmatter field loses its edge on
that file's next ingest. Editing a node in the Neo4j Browser instead is overwritten by the next
sync of its file.

The authoring rules for each entity type — which frontmatter fields are enum-governed, how
edges are declared — are in `/docs/guides/YAML_AUTHORING_GUIDE.md`; the ingestion pipeline
itself in `/docs/patterns/UNIFIED_INGESTION_GUIDE.md`.

## Troubleshooting

### The sync ingested nothing

Every bundle file already matched its tracker row — nothing changed since the last sync. Force a
re-ingest with `./dev vault-sync --vault content --force` (unchanged files are re-processed;
the wall and deletion reconciliation stay in place).

### A file was "set aside (no 'type:' field)"

It is a note, not an entity. Every ingestible file declares its entity type in frontmatter
(`type: PathStep`, `type: LearningPath`, …); the ingest gate refuses to guess.

### Connection refused / Unauthorized

`NEO4J_URI` and `NEO4J_USERNAME` in `.env` are the live values. For AuraDB the username is the
instance id, not `neo4j`, and an instance idle for more than 72 hours is paused until resumed
from the console — see `/docs/deployment/AURADB_MIGRATION_GUIDE.md` § 6.1.

## Summary

**Your workflow:**
1. `ls` the bundle files in the content vault (Step 0) — stop if any is missing
2. `uv run python scripts/clear_neo4j.py reset` → Type `DELETE EVERYTHING`
3. `./dev vault-sync --vault content`
4. Open the Neo4j Browser and run the queries above

**You'll get:**
- Clean Neo4j database
- The content vault's typed entities — the Mindfulness 101 learning path, its three path steps and its exercise among them
- Ready to adjust and experiment: edit the vault files and re-run the sync
