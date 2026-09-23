// Migration: completion_updates_goal → true where false is the unauthored default
// ===============================================================================
// Sets completion_updates_goal = true on tasks created by an app door: no
// source_path_step_uid and no IngestionMetadata row. Those doors cannot carry the
// field, so a false there is never an authored opt-out. Task templates,
// template-spawned tasks and vault-written tasks keep their value.
//
// Why, and the census that makes it safe:
// docs/roadmap/done/goal-progress-recompute-lost-update.md § What shipped.
//
// Idempotent: a re-run matches nothing.

MATCH (n:Entity {entity_type: 'task'})
WHERE n.completion_updates_goal = false
  AND n.source_path_step_uid IS NULL
  AND NOT EXISTS { MATCH (:IngestionMetadata {entity_uid: n.uid}) }
SET n.completion_updates_goal = true
RETURN count(n) AS rewritten;
