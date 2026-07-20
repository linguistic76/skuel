// Migration: drop the stale :Document / :Conversation bootstrap constraints (2026-07)
// ====================================================================================
// SKUEL030 findings tranche 3 — see docs/patterns/CYPHER_VOCABULARY_FINDINGS.md §2.
//
// Neo4jAdapter.bootstrap_indexes() created uniqueness constraints for two
// labels nothing in the repo ever writes:
//
//   document_id_unique      FOR (d:Document)     REQUIRE d.id IS UNIQUE
//   conversation_id_unique  FOR (c:Conversation) REQUIRE c.id IS UNIQUE
//
// There is no :Document label anywhere in SKUEL, and the real conversation
// store uses :ConversationSession / :ConversationMessage (both live, both with
// writers). The CREATE statements are gone from bootstrap_indexes(), but that
// only stops NEW environments from getting them — any environment where
// bootstrap has already run keeps them in SHOW CONSTRAINTS forever, advertising
// graph vocabulary that does not exist.
//
// The constraints are inert (a constraint on an unused label never fires), so
// this moves no data and cannot fail on a graph that has rows. It exists purely
// so the live schema stops describing labels that were never real.
//
// Idempotent: IF EXISTS makes re-running a no-op, and running against a graph
// that never had them (e.g. the current dev database) is also a no-op.

DROP CONSTRAINT document_id_unique IF EXISTS;
DROP CONSTRAINT conversation_id_unique IF EXISTS;

// ---------------------------------------------------------------------
// Verification (expects an empty result)
// ---------------------------------------------------------------------
// SHOW CONSTRAINTS YIELD name
// WHERE name IN ['document_id_unique', 'conversation_id_unique']
// RETURN name;
