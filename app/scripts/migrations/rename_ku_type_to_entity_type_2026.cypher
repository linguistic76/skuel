// Migration: Rename ku_type -> entity_type on all Entity nodes
// Date: 2026-03-06
// Context: Aligning Neo4j property names with Python field rename.
//          "Everything is a Ku" philosophy replaced with entity-centric naming.
//          Only 71 nodes in dev database; no batching needed.

// Step 1: Rename ku_type -> entity_type
MATCH (n:Entity) WHERE n.ku_type IS NOT NULL
SET n.entity_type = n.ku_type
REMOVE n.ku_type
RETURN count(n) AS entities_migrated;

// Step 2: Rename parent_ku_uid -> parent_entity_uid (if any exist)
MATCH (n:Entity) WHERE n.parent_ku_uid IS NOT NULL
SET n.parent_entity_uid = n.parent_ku_uid
REMOVE n.parent_ku_uid
RETURN count(n) AS parent_uids_migrated;
