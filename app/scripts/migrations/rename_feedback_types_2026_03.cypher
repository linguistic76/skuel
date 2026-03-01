// ============================================================================
// Migration: Rename Feedback EntityTypes — 2026-03
// ============================================================================
//
// Renames:
//   AI_FEEDBACK     (ku_type: "ai_feedback")     → ACTIVITY_REPORT ("activity_report")
//   FEEDBACK_REPORT (ku_type: "feedback_report") → SUBMISSION_FEEDBACK ("submission_feedback")
//
// Neo4j label changes:
//   :AiFeedback  → :ActivityReport
//   :Feedback    → :SubmissionFeedback
//
// Run this against the active Neo4j instance BEFORE deploying the updated code.
//
// Verification queries are included at the end.
// ============================================================================


// ----------------------------------------------------------------------------
// Step 1: Rename ku_type property values
// ----------------------------------------------------------------------------

// AI_FEEDBACK → ACTIVITY_REPORT
MATCH (n:Entity {ku_type: 'ai_feedback'})
SET n.ku_type = 'activity_report'
RETURN count(n) AS activity_report_nodes_updated;

// FEEDBACK_REPORT → SUBMISSION_FEEDBACK
MATCH (n:Entity {ku_type: 'feedback_report'})
SET n.ku_type = 'submission_feedback'
RETURN count(n) AS submission_feedback_nodes_updated;


// ----------------------------------------------------------------------------
// Step 2: Rename Neo4j domain labels
// ----------------------------------------------------------------------------

// :AiFeedback → :ActivityReport
MATCH (n:AiFeedback)
REMOVE n:AiFeedback
SET n:ActivityReport
RETURN count(n) AS activity_report_labels_updated;

// :Feedback → :SubmissionFeedback
MATCH (n:Feedback)
REMOVE n:Feedback
SET n:SubmissionFeedback
RETURN count(n) AS submission_feedback_labels_updated;


// ----------------------------------------------------------------------------
// Step 3: Verification
// ----------------------------------------------------------------------------

// Confirm no old ku_type values remain
MATCH (n:Entity)
WHERE n.ku_type IN ['ai_feedback', 'feedback_report']
RETURN count(n) AS old_type_nodes_remaining;
// Expected: 0

// Confirm no old labels remain
MATCH (n:AiFeedback)
RETURN count(n) AS old_ai_feedback_labels_remaining;
// Expected: 0

MATCH (n:Feedback)
RETURN count(n) AS old_feedback_labels_remaining;
// Expected: 0

// Confirm new nodes exist (if any existed before)
MATCH (n:Entity)
WHERE n.ku_type IN ['activity_report', 'submission_feedback']
RETURN n.ku_type, count(n) AS node_count;
