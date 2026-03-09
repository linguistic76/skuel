// Migration: Rename submission/report entity types and add multi-labels
// Date: 2026-03-09
// Context: Submission/Report Hierarchy Refactoring
//
// Changes:
//   entity_type 'submission' → 'exercise_submission'
//   entity_type 'journal' → 'journal_submission'
//   entity_type 'submission_report' → 'exercise_report'
//   New labels: :ExerciseSubmission, :JournalSubmission, :ExerciseReport
//   Removed labels: :Journal (replaced by :JournalSubmission)
//   Kept labels: :Submission (base for multi-label queries), :SubmissionReport (base)
//
// Run with: cat scripts/migrations/rename_submission_types_2026_03.cypher | cypher-shell -u neo4j -p <password>

// ============================================================================
// Step 1: Rename entity_type property values
// ============================================================================

// submission → exercise_submission
MATCH (n:Entity) WHERE n.entity_type = 'submission'
SET n.entity_type = 'exercise_submission'
RETURN count(n) AS submissions_renamed;

// journal → journal_submission
MATCH (n:Entity) WHERE n.entity_type = 'journal'
SET n.entity_type = 'journal_submission'
RETURN count(n) AS journals_renamed;

// submission_report → exercise_report
MATCH (n:Entity) WHERE n.entity_type = 'submission_report'
SET n.entity_type = 'exercise_report'
RETURN count(n) AS reports_renamed;

// ============================================================================
// Step 2: Add new domain-specific labels (multi-label architecture)
// ============================================================================

// :ExerciseSubmission on exercise submissions (keeps :Submission base label)
MATCH (n:Entity) WHERE n.entity_type = 'exercise_submission'
SET n:ExerciseSubmission
RETURN count(n) AS exercise_submission_labels_added;

// :JournalSubmission on journal submissions (keeps :Submission base label)
MATCH (n:Entity) WHERE n.entity_type = 'journal_submission'
SET n:JournalSubmission
RETURN count(n) AS journal_submission_labels_added;

// :ExerciseReport on exercise reports (keeps :SubmissionReport base label)
MATCH (n:Entity) WHERE n.entity_type = 'exercise_report'
SET n:ExerciseReport
RETURN count(n) AS exercise_report_labels_added;

// ============================================================================
// Step 3: Remove obsolete labels
// ============================================================================

// Remove :Journal label (replaced by :JournalSubmission)
MATCH (n:Journal)
REMOVE n:Journal
RETURN count(n) AS journal_labels_removed;

// Keep :Submission label on submission nodes (base label for multi-label queries)
// Keep :SubmissionReport label on report nodes (base label for multi-label queries)

// ============================================================================
// Step 4: Verification
// ============================================================================

// Verify no nodes have old entity_type values
MATCH (n:Entity) WHERE n.entity_type IN ['submission', 'journal', 'submission_report']
RETURN n.entity_type AS stale_type, count(n) AS count;

// Count new types
MATCH (n:Entity) WHERE n.entity_type IN ['exercise_submission', 'journal_submission', 'exercise_report']
RETURN n.entity_type AS new_type, count(n) AS count;
