// Migration: Backfill user_uid property to match the :OWNS owner (2026-06)
// =========================================================================
// Problem: a node's denormalized `user_uid` PROPERTY can diverge from its
//   authoritative (User)-[:OWNS]->(entity) edge. Onboarding/demo seed content
//   ingested on 2026-04-01 was :OWNS-linked to a real user but kept
//   user_uid="user_system". Property-based reads — every
//   UniversalNeo4jBackend.find_by(user_uid=…) caller — silently miss those
//   entities, while the :OWNS-traversing unified search path does see them.
//   The two ownership signals disagree for the affected user.
//
// Fix: the :OWNS edge is the canonical ownership signal
//   (DomainConfig.user_ownership_relationship=OWNS; unified search, ownership
//   verification, and the GDPR cascade all traverse it). The live write-paths
//   (_user_entity_mixin auto-OWNS, _spawn_orchestrator._build) already keep
//   property == owner, so this is a one-time stale-data fix: set
//   e.user_uid = owner.uid wherever an :OWNS owner exists and diverges.
//
// SAFE: only nodes that HAVE an :OWNS owner are touched. Ownerless system
//   catalog/template nodes (user_uid="user_system", no owner) are legitimately
//   system-owned and are left untouched. No multi-owner nodes exist (verified).
//
// CRITICAL: Back up the database before running.
// See: docs/migrations/USER_UID_OWNS_BACKFILL_2026-06.md
//
// Run phases in order. Phase 2 is a validation query — expected result: 0.

// --------------------------------------------------------------------
// Phase 1: Backfill — align the user_uid property to the :OWNS owner
// for every entity whose property diverges from (or is missing for) its owner.
// The explicit IS NULL case matters: `owner.uid <> null` evaluates to null, and
// WHERE keeps only true rows — so a null property would otherwise be skipped.
// --------------------------------------------------------------------
MATCH (owner:User)-[:OWNS]->(e:Entity)
WHERE e.user_uid IS NULL OR owner.uid <> e.user_uid
SET e.user_uid = owner.uid
RETURN count(e) AS backfilled_entities;

// --------------------------------------------------------------------
// Phase 2: Validation — expected result: 0 mismatched_entities
// Any non-zero result means an entity's :OWNS owner still disagrees with
// its user_uid property (the invariant we enforce going forward). The
// IS NULL case is counted as a mismatch for the same null-semantics reason.
// --------------------------------------------------------------------
MATCH (owner:User)-[:OWNS]->(e:Entity)
WHERE e.user_uid IS NULL OR owner.uid <> e.user_uid
RETURN count(e) AS mismatched_entities;
