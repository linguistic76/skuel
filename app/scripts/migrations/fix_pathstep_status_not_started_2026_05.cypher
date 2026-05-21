// Migration: Fix PathStep status='not_started' → status='active'
// Date: 2026-05-08
// Context: Some PathStep nodes were seeded with status='not_started', which is
//          a value of MasteryStatus (learning_enums.py), not EntityStatus. The
//          DTO converter logs a warning and drops the field on every read,
//          surfaced loudly by /path-steps which lists all PathSteps.
//
// Audit before fix: 5 PathStep records with status='not_started' (all
//                   labels=["Entity","PathStep"], entity_type='path_step').
//
// Decision: map → 'active' (these are published curriculum content, visible
//          to users — 'active' is the right EntityStatus for that state).
//
// Run with: cypher-shell -f scripts/migrations/fix_pathstep_status_not_started_2026_05.cypher

// =============================================================================
// Step 1: Count records that will be migrated
// =============================================================================

MATCH (ps:PathStep)
WHERE ps.status = 'not_started'
RETURN count(ps) AS pathsteps_to_migrate;
// Expected: 5

// =============================================================================
// Step 2: Update status → 'active'
// =============================================================================

MATCH (ps:PathStep)
WHERE ps.status = 'not_started'
SET ps.status = 'active',
    ps.updated_at = datetime()
RETURN count(ps) AS pathsteps_migrated;
// Expected: 5

// =============================================================================
// Step 3: Validate — no PathSteps with status='not_started' should remain
// =============================================================================

MATCH (ps:PathStep)
WHERE ps.status = 'not_started'
RETURN count(ps) AS remaining_not_started_pathsteps;
// Expected: 0

// =============================================================================
// Step 4: Sanity check — confirm no other Entity types carry 'not_started'
// =============================================================================

MATCH (n:Entity)
WHERE n.status = 'not_started'
RETURN labels(n) AS labels, n.entity_type AS entity_type, count(*) AS n
ORDER BY n DESC;
// Expected: empty result set
