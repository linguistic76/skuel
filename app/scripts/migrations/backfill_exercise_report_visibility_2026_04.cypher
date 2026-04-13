// Backfill ExerciseReport.visibility = 'shared'
//
// Context: Before 2026-04, create_report_node created ExerciseReport nodes
// without setting visibility. UserOwnedEntity defaults visibility to
// 'private', which caused UnifiedSharingService.check_access to short-circuit
// — even students with a valid SHARES_WITH edge to their own report were
// denied access.
//
// Fix: set visibility='shared' on existing reports that have no visibility
// (or are still private). New reports now set it at create time.

MATCH (fb:ExerciseReport)
WHERE fb.visibility IS NULL OR fb.visibility = 'private'
SET fb.visibility = 'shared'
RETURN count(fb) AS updated;
