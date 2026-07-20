// Migration: retire the LEARNING edge and the :Expense label (2026-07)
// =====================================================================
// SKUEL030 findings tranche 2 — see docs/patterns/CYPHER_VOCABULARY_FINDINGS.md
// §6 and §11.
//
// Part 1 — LEARNING → IN_PROGRESS
//   RelationshipName.LEARNING was replaced by IN_PROGRESS (asserted by
//   tests/unit/test_no_legacy_patterns.py), but UserBackend.record_knowledge_progress
//   kept writing the retired type. Every (User)-[:LEARNING]->(Entity) edge is
//   therefore invisible to the IN_PROGRESS readers that drive learning state.
//   The writer now emits IN_PROGRESS; this folds the historical edges over.
//
//   Property carry-over — LEARNING wrote {progress, time_invested_minutes,
//   difficulty_rating, last_updated}; IN_PROGRESS uses {progress, started_at,
//   time_invested_minutes, difficulty_rating, last_accessed}. last_updated maps
//   onto last_accessed and doubles as the started_at floor (the true start was
//   never recorded). Where an IN_PROGRESS edge already exists for the same pair,
//   the two are merged: progress/difficulty take the more advanced value,
//   time_invested_minutes sums, timestamps take the wider span. Pairs the user
//   has already MASTERED drop the LEARNING edge outright rather than convert —
//   mastery retires in-progress state, it does not coexist with it.
//
// Part 2 — stray :Expense nodes
//   ADR-052 Phase 5 demolished the native expense module, but the ingestion
//   config kept minting :Expense nodes from `type: expense` vault files. The
//   config is gone; this removes any nodes it created (plus their ingestion
//   tracking rows, so a re-sync does not report them as vault deletions).
//
// Idempotent: re-running is a no-op once no LEARNING edge and no :Expense node
// remains. Safe to run against a graph that never had either.

// ---------------------------------------------------------------------
// Part 1a: pairs already MASTERED — drop the LEARNING edge, don't convert
// ---------------------------------------------------------------------
// The state progression is VIEWED -> IN_PROGRESS -> MASTERED, and MASTERED
// retires IN_PROGRESS (UserProgressBackend.record_mastery,
// UserBackend.record_knowledge_mastery). Converting here would resurrect an
// active-study edge on knowledge the user has already mastered, so
// count_in_progress_path_steps and friends would count it as in progress.
MATCH (u:User)-[l:LEARNING]->(k)
WHERE EXISTS { (u)-[:MASTERED]->(k) }
DELETE l;

// ---------------------------------------------------------------------
// Part 1b: fold LEARNING into an EXISTING IN_PROGRESS edge for the same pair
// ---------------------------------------------------------------------
MATCH (u:User)-[l:LEARNING]->(k)
MATCH (u)-[p:IN_PROGRESS]->(k)
SET p.progress = CASE
        WHEN coalesce(l.progress, 0.0) > coalesce(p.progress, 0.0)
        THEN l.progress ELSE p.progress END,
    p.time_invested_minutes =
        coalesce(p.time_invested_minutes, 0) + coalesce(l.time_invested_minutes, 0),
    p.difficulty_rating = coalesce(p.difficulty_rating, l.difficulty_rating),
    p.started_at = CASE
        WHEN p.started_at IS NULL THEN l.last_updated
        WHEN l.last_updated IS NOT NULL AND l.last_updated < p.started_at
        THEN l.last_updated ELSE p.started_at END,
    p.last_accessed = CASE
        WHEN p.last_accessed IS NULL THEN l.last_updated
        WHEN l.last_updated IS NOT NULL AND l.last_updated > p.last_accessed
        THEN l.last_updated ELSE p.last_accessed END
DELETE l;

// ---------------------------------------------------------------------
// Part 1c: convert the remaining LEARNING edges (no IN_PROGRESS counterpart)
// ---------------------------------------------------------------------
MATCH (u:User)-[l:LEARNING]->(k)
MERGE (u)-[p:IN_PROGRESS]->(k)
SET p.progress = l.progress,
    p.time_invested_minutes = coalesce(l.time_invested_minutes, 0),
    p.difficulty_rating = l.difficulty_rating,
    p.started_at = coalesce(l.last_updated, datetime()),
    p.last_accessed = coalesce(l.last_updated, datetime())
DELETE l;

// ---------------------------------------------------------------------
// Part 2: drop stray :Expense nodes and their ingestion tracking rows
// ---------------------------------------------------------------------
MATCH (x:Expense)
OPTIONAL MATCH (s:IngestionMetadata {entity_uid: x.uid})
DETACH DELETE x, s;

// ---------------------------------------------------------------------
// Verification (expects 0, 0)
// ---------------------------------------------------------------------
// MATCH ()-[r:LEARNING]->() RETURN count(r) AS remaining_learning_edges;
// MATCH (x:Expense) RETURN count(x) AS remaining_expense_nodes;
