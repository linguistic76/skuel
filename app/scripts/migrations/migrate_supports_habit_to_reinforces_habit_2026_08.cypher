// Migration: SUPPORTS_HABIT → REINFORCES_HABIT
// Date: 2026-08-10  (#1010)
//
// Context: `SUPPORTS_HABIT` was removed from RelationshipName when Task→Habit
// consolidated onto REINFORCES_HABIT (matching Event's identical concept and the
// `reinforces_habit` field name). Two code comments asserted the old edge "was
// never written" — the live graph disagreed: `scripts/audit_graph_vocabulary.py`
// found one, `task.track-one-pattern -[:SUPPORTS_HABIT]-> habit.pause-and-name`.
//
// Why it mattered: SUPPORTS_HABIT is no longer a RelationshipName member, and
// SKUEL030 forbids naming a non-member in Cypher — so NO reader can traverse it.
// Neo4j answers an unknown relationship type with zero rows rather than an error,
// which is why this sat unnoticed rather than failing loudly.
//
// On the graph this was written against, the canonical REINFORCES_HABIT edge
// already existed between the same pair and the stray carried no properties —
// a pure duplicate. This migration is written to be correct in BOTH cases:
// MERGE creates the canonical edge only if it is missing, ON CREATE carries any
// properties across, and the stray is deleted either way.
//
// Run with: cypher-shell -f scripts/migrations/migrate_supports_habit_to_reinforces_habit_2026_08.cypher
// Verify with: uv run python scripts/audit_graph_vocabulary.py

// =============================================================================
// Step 1: Re-point every SUPPORTS_HABIT edge onto REINFORCES_HABIT, then drop it
// =============================================================================

MATCH (source)-[stale:SUPPORTS_HABIT]->(target)
MERGE (source)-[canonical:REINFORCES_HABIT]->(target)
ON CREATE SET canonical = properties(stale)
DELETE stale
RETURN count(stale) AS edges_migrated;

// =============================================================================
// Step 2: Validate — no SUPPORTS_HABIT edges may remain
// =============================================================================

MATCH ()-[r:SUPPORTS_HABIT]->()
RETURN count(r) AS remaining_supports_habit;
// Expected: 0
