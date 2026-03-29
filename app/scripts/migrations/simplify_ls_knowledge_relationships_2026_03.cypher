// Migration: Simplify CONTAINS_KNOWLEDGE relationships
// Date: 2026-03-28
// Context: Removes the 'type' property from CONTAINS_KNOWLEDGE relationships,
// collapsing the primary/supporting distinction into a single graph-native pattern.
// See: LearningStep knowledge normalization plan
//
// Safe to run multiple times (idempotent).

MATCH ()-[r:CONTAINS_KNOWLEDGE]->()
WHERE r.type IS NOT NULL
REMOVE r.type
RETURN count(r) AS relationships_simplified;
