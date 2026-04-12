// Add :ExerciseReport label to existing exercise_report nodes
//
// Context: Prior to 2026-04, SubmissionsBackend.create_report_node stamped only
// the :Entity label when creating ExerciseReport nodes, leaving typed reads via
// ExerciseReportBackend (which MATCH :ExerciseReport) broken against those rows.
//
// The write-side fix lands the multi-label CREATE going forward. This migration
// backfills any pre-fix rows. Idempotent — safe to run multiple times.
//
// Run manually against local Neo4j.

MATCH (r:Entity {entity_type: 'exercise_report'})
WHERE NOT r:ExerciseReport
SET r:ExerciseReport
RETURN count(r) AS backfilled
