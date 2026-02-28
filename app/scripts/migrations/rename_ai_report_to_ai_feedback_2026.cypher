// Migration: Rename AI_REPORT → AI_FEEDBACK
// Date: 2026-02-28
// Purpose: EntityType.AI_REPORT renamed to AI_FEEDBACK. ku_type value changes from
//          "ai_report" to "ai_feedback". Neo4j label :AiReport → :AiFeedback.
//
// Run this against the Neo4j instance AFTER deploying code changes.
// Verify: MATCH (n:Entity) WHERE n.ku_type = 'ai_report' RETURN count(n); // should be 0

// Step 1: Update ku_type property
MATCH (n:Entity {ku_type: 'ai_report'})
SET n.ku_type = 'ai_feedback'
RETURN count(n) AS nodes_updated;

// Step 2: Add :AiFeedback label, remove :AiReport label
// Note: APOC apoc.create.addLabels/removeLabels used here — allowed in migration scripts
// (domain services use pure Cypher per SKUEL001; migrations may use APOC)
MATCH (n:Entity {ku_type: 'ai_feedback'})
WHERE 'AiReport' IN labels(n)
CALL apoc.create.addLabels(n, ['AiFeedback']) YIELD node
CALL apoc.create.removeLabels(node, ['AiReport']) YIELD node AS updated
RETURN count(updated) AS labels_migrated;

// Step 3: Drop old index if it exists, create new index
DROP INDEX ai_report_type_idx IF EXISTS;
CREATE INDEX ai_feedback_type_idx IF NOT EXISTS FOR (n:AiFeedback) ON (n.ku_type);

// Verification query (run after migration):
// MATCH (n:Entity) WHERE n.ku_type = 'ai_report' RETURN count(n) AS should_be_zero;
// MATCH (n:Entity) WHERE n.ku_type = 'ai_feedback' RETURN count(n) AS migrated_count;
