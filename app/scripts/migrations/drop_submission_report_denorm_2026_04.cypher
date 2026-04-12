// Strip dead denormalized fields from existing ExerciseSubmission nodes.
// The authoritative data lives on the ExerciseReport node reached via REPORT_FOR.
// Idempotent: re-running is a no-op.
MATCH (s:ExerciseSubmission)
WHERE s.report_content IS NOT NULL OR s.report_generated_at IS NOT NULL
REMOVE s.report_content, s.report_generated_at
RETURN count(s) AS stripped
