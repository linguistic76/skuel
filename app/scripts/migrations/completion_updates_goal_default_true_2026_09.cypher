// Migration: completion_updates_goal defaults to true (2026-09)
// =============================================================
// `Task.completion_updates_goal` / `TaskTemplate.completion_updates_goal` said
// "completion updates goal progress" but nothing read it, and it defaulted to
// false. The goal-progress tally now reads it — a task linked to a goal by
// FULFILLS_GOAL counts toward that goal unless it opts out — and the default is
// true, so an ordinary link keeps counting (docs/roadmap/done/goal-progress-recompute-lost-update.md).
//
// The DTO persists every field, so an app-created task stores an explicit false
// the new default cannot reach. This rewrites ONLY the falses that are provably
// that old default, and leaves every false that could have been authored:
//
// - rewritten: tasks created by an app door. TaskCreateRequest and
//   TaskUpdateRequest do not carry the field, and the one service writer that set
//   it (goal_task_generator) wrote true — so a false on such a task is the
//   default, never a choice.
// - left alone: task templates (TaskTemplateUpdateRequest can set false, and a
//   vault template can author it); tasks spawned from a template
//   (source_path_step_uid set — they copy the template's value); tasks a vault
//   file wrote (an IngestionMetadata row — the file can author it).
//
// Measured on the AuraDB graph 2026-09-23 (read-only): 75 tasks false, all 75
// app-created (none spawned, none vault-ingested); 0 task templates false. None
// of the 75 is linked to a goal yet, so this is safe before or after deploy.
//
// Idempotent: a re-run matches nothing.

MATCH (n:Entity {entity_type: 'task'})
WHERE n.completion_updates_goal = false
  AND n.source_path_step_uid IS NULL
  AND NOT EXISTS { MATCH (:IngestionMetadata {entity_uid: n.uid}) }
SET n.completion_updates_goal = true
RETURN count(n) AS rewritten;
