// Migration: Type RevisedExercise feedback points
// Date: 2026-03-28
// Context: Rename feedback_points_addressed → feedback_points on RevisedExercise nodes.
//          Existing string list values become legacy format; the model's __post_init__
//          parser handles both old (list[str]) and new (list[{category, detail}]) formats.

// Step 1: Rename property (preserves existing values as-is)
MATCH (re:Entity {entity_type: 'revised_exercise'})
WHERE re.feedback_points_addressed IS NOT NULL
SET re.feedback_points = re.feedback_points_addressed
REMOVE re.feedback_points_addressed
RETURN count(re) AS nodes_migrated;
