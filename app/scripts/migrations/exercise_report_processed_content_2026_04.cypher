// Migrate ExerciseReport.content → ExerciseReport.processed_content
//
// Context: Before 2026-04, create_report_node wrote LLM/teacher-generated
// feedback onto the inherited Entity.content property. Entity.content is
// semantically "user-drafted text"; processor-generated analysis belongs on
// processed_content — the same field ActivityReport uses.
//
// This migration copies existing content to processed_content and removes the
// old content property from ExerciseReport nodes. Idempotent: the WHERE guard
// skips nodes already migrated.
//
// Safe to re-run: nodes with processed_content already set are skipped.
//
// See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
//      /scripts/migrations/backfill_exercise_report_visibility_2026_04.cypher

MATCH (r:ExerciseReport)
WHERE r.content IS NOT NULL AND r.processed_content IS NULL
SET r.processed_content = r.content
REMOVE r.content
RETURN count(r) AS migrated;
