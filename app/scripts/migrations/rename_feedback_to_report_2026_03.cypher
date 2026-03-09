// ============================================================================
// Migration: Rename Feedback → Report — 2026-03
// ============================================================================
//
// Renames:
//   EntityType value: "submission_feedback" → "submission_report"
//   ContentOrigin value: "feedback" → "report"
//   NeoLabel: :SubmissionFeedback → :SubmissionReport
//   Relationship: FEEDBACK_FOR → REPORT_FOR
//   Relationship: RESPONDS_TO_FEEDBACK → RESPONDS_TO_REPORT
//   Data fields: .feedback → .report_content, .feedback_generated_at → .report_generated_at
//
// Run this against the active Neo4j instance BEFORE deploying the updated code.
//
// Verification queries are included at the end.
// ============================================================================


// ----------------------------------------------------------------------------
// Step 1: Rename entity_type property value
// ----------------------------------------------------------------------------

MATCH (n:Entity {entity_type: 'submission_feedback'})
SET n.entity_type = 'submission_report'
RETURN count(n) AS entity_type_nodes_updated;


// ----------------------------------------------------------------------------
// Step 2: Rename Neo4j domain label
// ----------------------------------------------------------------------------

MATCH (n:SubmissionFeedback)
REMOVE n:SubmissionFeedback
SET n:SubmissionReport
RETURN count(n) AS label_nodes_updated;


// ----------------------------------------------------------------------------
// Step 3: Rename data fields on SubmissionReport nodes
// ----------------------------------------------------------------------------

MATCH (n:SubmissionReport) WHERE n.feedback IS NOT NULL
SET n.report_content = n.feedback
REMOVE n.feedback
RETURN count(n) AS feedback_field_renamed;

MATCH (n:SubmissionReport) WHERE n.feedback_generated_at IS NOT NULL
SET n.report_generated_at = n.feedback_generated_at
REMOVE n.feedback_generated_at
RETURN count(n) AS feedback_generated_at_field_renamed;


// ----------------------------------------------------------------------------
// Step 4: Rename relationship types
// ----------------------------------------------------------------------------

MATCH (a)-[r:FEEDBACK_FOR]->(b)
CREATE (a)-[r2:REPORT_FOR]->(b)
SET r2 = properties(r)
DELETE r
RETURN count(r2) AS feedback_for_rels_renamed;

MATCH (a)-[r:RESPONDS_TO_FEEDBACK]->(b)
CREATE (a)-[r2:RESPONDS_TO_REPORT]->(b)
SET r2 = properties(r)
DELETE r
RETURN count(r2) AS responds_to_feedback_rels_renamed;


// ----------------------------------------------------------------------------
// Step 5: Rename ContentOrigin values (if stored as property)
// ----------------------------------------------------------------------------

MATCH (n) WHERE n.content_origin = 'feedback'
SET n.content_origin = 'report'
RETURN count(n) AS content_origin_nodes_updated;


// ----------------------------------------------------------------------------
// Step 6: Verification
// ----------------------------------------------------------------------------

// Confirm no old entity_type values remain
MATCH (n:Entity {entity_type: 'submission_feedback'})
RETURN count(n) AS old_entity_type_remaining;
// Expected: 0

// Confirm no old labels remain
MATCH (n:SubmissionFeedback)
RETURN count(n) AS old_label_remaining;
// Expected: 0

// Confirm no old data fields remain
MATCH (n:SubmissionReport) WHERE n.feedback IS NOT NULL
RETURN count(n) AS old_feedback_field_remaining;
// Expected: 0

// Confirm no old relationships remain
MATCH ()-[r:FEEDBACK_FOR]->()
RETURN count(r) AS old_feedback_for_remaining;
// Expected: 0

MATCH ()-[r:RESPONDS_TO_FEEDBACK]->()
RETURN count(r) AS old_responds_to_feedback_remaining;
// Expected: 0

// Confirm new nodes exist (if any existed before)
MATCH (n:SubmissionReport)
RETURN count(n) AS submission_report_count;
