// Migration: remove leftover :ContentMetadata nodes (2026-07)
// ============================================================
// SKUEL030 findings tranche 3 — see docs/patterns/CYPHER_VOCABULARY_FINDINGS.md §7.
//
// The `(Content)-[:HAS_METADATA]->(ContentMetadata)` WRITE was removed in July
// 2026 (L1 ruling 2026-07-02, guarded by
// tests/unit/adapters/test_content_adapter_chunk_persistence.py). The matching
// READS were left behind as dead `OPTIONAL MATCH` clauses in three delete
// queries; tranche 3 removed those clauses.
//
// On a graph that never had the writer this is pure dead-clause removal. But on
// any environment whose content was ingested BEFORE the write was removed, real
// :ContentMetadata nodes still hang off :Content. Those delete queries were the
// only thing pruning them leaf-first — without the clause, `DETACH DELETE
// content` merely detaches them and leaves them orphaned (Codex P2 on #737).
//
// This migration removes them once, so the reads can stay gone. Run it BEFORE
// (or with) deploying the tranche-3 code on any long-lived environment.
//
// Idempotent: re-running is a no-op once none remain, and running against a
// graph that never had the writer (e.g. the current dev database) is also a
// no-op. DETACH DELETE clears the HAS_METADATA edge along with the node.

// ---------------------------------------------------------------------
// Part 1: metadata still attached to a Content node
// ---------------------------------------------------------------------
MATCH (:Content)-[:HAS_METADATA]->(meta:ContentMetadata)
DETACH DELETE meta;

// ---------------------------------------------------------------------
// Part 2: metadata already orphaned by an earlier subtree delete
// ---------------------------------------------------------------------
// A delete that ran between the writer's removal and this migration detached
// these without deleting them — exactly the leak this closes.
MATCH (meta:ContentMetadata)
DETACH DELETE meta;

// ---------------------------------------------------------------------
// Verification (expects 0)
// ---------------------------------------------------------------------
// MATCH (m:ContentMetadata) RETURN count(m) AS remaining_content_metadata;
