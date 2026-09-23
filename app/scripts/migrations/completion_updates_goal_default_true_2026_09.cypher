// Migration: completion_updates_goal defaults to true (2026-09)
// =============================================================
// `Task.completion_updates_goal` / `TaskTemplate.completion_updates_goal` said
// "completion updates goal progress" but nothing read it, and it defaulted to
// false. The goal-progress tally now reads it — a task linked to a goal by
// FULFILLS_GOAL counts toward that goal unless it opts out — and the default is
// true, so an ordinary link keeps counting (docs/roadmap/done/goal-progress-recompute-lost-update.md).
//
// Every `false` stored before this change is the old default, not a choice: no
// door ever set it to false on purpose. The goal picker and the task create and
// update requests do not carry the field, and the one writer that set it wrote
// true (goal_task_generator). The content vault authors it only as true.
// The DTO persists every field, so app-created tasks and templates store an
// explicit false that the new default cannot reach; this rewrites them.
//
// Measured on the AuraDB graph 2026-09-23 (read-only): 75 tasks false, 2 tasks
// absent, 1 task template true, 0 task templates false. None of the 75 is linked
// to a goal yet — which is what makes this safe to run before or after deploy.
//
// Idempotent: a re-run matches nothing.

MATCH (n:Entity)
WHERE n.entity_type IN ['task', 'task_template']
  AND n.completion_updates_goal = false
SET n.completion_updates_goal = true
RETURN n.entity_type AS entity_type, count(n) AS rewritten;
