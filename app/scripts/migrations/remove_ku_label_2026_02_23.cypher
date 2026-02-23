// Migration: Remove legacy :Ku label from all entity nodes
// Date: 2026-02-23
// Context: All :Ku nodes already have :Entity label (verified: 0 nodes have :Ku without :Entity).
//          Code now uses :Entity exclusively. This migration removes the legacy :Ku label.
//
// Pre-check (run first):
//   MATCH (n:Ku) WHERE NOT n:Entity RETURN count(n)  → should be 0
//
// Run with: cypher-shell -u neo4j -p <password> -f scripts/migrations/remove_ku_label_2026_02_23.cypher

// --- Step 1: Verify all :Ku nodes have :Entity ---
MATCH (n:Ku) WHERE NOT n:Entity
RETURN count(n) AS nodes_without_entity;
// Expected: 0 — if > 0, STOP and investigate

// --- Step 2: Create vector index on :Entity if not exists ---
// (This replaces the :Ku-based vector index)
CREATE VECTOR INDEX entity_embedding_idx IF NOT EXISTS
FOR (n:Entity) ON (n.embedding)
OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}};

// --- Step 3: Create standard indexes on :Entity if not exists ---
CREATE INDEX entity_uid_idx IF NOT EXISTS FOR (n:Entity) ON (n.uid);
CREATE INDEX entity_type_idx IF NOT EXISTS FOR (n:Entity) ON (n.ku_type);

// --- Step 4: Remove :Ku label from all nodes ---
MATCH (n:Ku) REMOVE n:Ku RETURN count(n) AS nodes_updated;

// --- Step 5: Drop legacy :Ku indexes ---
DROP INDEX ku_uid_idx IF EXISTS;
DROP INDEX ku_type_idx IF EXISTS;
DROP INDEX ku_embedding_idx IF EXISTS;

// --- Step 6: Verify ---
MATCH (n:Ku) RETURN count(n) AS remaining_ku_nodes;
// Expected: 0
