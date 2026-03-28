// Migration: Collapse SubmissionReport into ExerciseReport
// Date: 2026-03-28
//
// Context: SubmissionReport was a base class with ExerciseReport as its only
// subclass (adding zero fields). After the journal extraction removed the
// second subclass (JournalReport → JeOutput), SubmissionReport became a
// pointless abstraction. This migration removes the stale Neo4j label.
//
// Before: Nodes have labels :Entity:SubmissionReport:ExerciseReport
// After:  Nodes have labels :Entity:ExerciseReport
//
// Safe to run multiple times (idempotent).

// Step 1: Remove :SubmissionReport label from all ExerciseReport nodes
MATCH (n:SubmissionReport)
REMOVE n:SubmissionReport;

// Step 2: Verify — should return 0
MATCH (n:SubmissionReport) RETURN count(n) AS remaining_submission_report_nodes;
