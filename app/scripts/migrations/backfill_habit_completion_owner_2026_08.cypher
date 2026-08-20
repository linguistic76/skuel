// Backfill the owner on :HabitCompletion nodes created before the field existed.
// ============================================================================
//
// Context: `HabitCompletion` shipped without a `user_uid` field. `_create_node`
// writes the `(User)-[:OWNS]->(entity)` edge only for entities carrying one, so
// pre-existing completion nodes have NEITHER the property nor the edge. Three
// separate reads were silently returning nothing as a result (#1099, #1100).
//
// Making `user_uid` a required dataclass field changes the failure mode on any
// such node from "invisible to owner-scoped reads" to "invisible to ALL reads":
// `from_neo4j_node` cannot construct a required field that is absent, the
// TypeError is swallowed as a malformed-row warning, and the row disappears
// from its own listing. Run this BEFORE deploying that model change.
//
// The owner is derived from the completion's Habit, which has always carried
// `user_uid`. A completion whose habit_uid matches no Habit cannot be attributed
// and is reported by the verification query below rather than guessed at.
//
// Idempotent: only touches nodes WHERE hc.user_uid IS NULL, and MERGEs the edge.
//
// ⚠ MEASURED 2026-08-20 against AuraDB `d2d160c4` (THE graph): 0 :HabitCompletion
// nodes exist, so this is a no-op there. It is written for any environment that
// was not measured — a local sandbox, a restored snapshot, or a future import.

// --- 1. Property + OWNS edge, derived from the completion's Habit ---
MATCH (hc:HabitCompletion)
WHERE hc.user_uid IS NULL
MATCH (h:Habit {uid: hc.habit_uid})
MATCH (owner:User {uid: h.user_uid})
SET hc.user_uid = h.user_uid
MERGE (owner)-[owns:OWNS]->(hc)
  ON CREATE SET
    owns.created_at = toString(datetime()),
    owns.last_accessed = toString(datetime()),
    owns.access_count = 0,
    owns.is_active = true
RETURN count(hc) AS completions_attributed;

// --- 2. Verification: anything still unattributed must be looked at by hand ---
// A non-zero count here means a completion references a Habit that no longer
// exists (or whose owner User is gone). Those nodes are orphans: they cannot be
// attributed from the graph, and they will vanish from reads once `user_uid` is
// required. Decide explicitly — reattach or delete — do not leave them.
MATCH (hc:HabitCompletion)
WHERE hc.user_uid IS NULL
RETURN count(hc) AS orphan_completions,
       collect(hc.uid)[..25] AS sample_uids;
