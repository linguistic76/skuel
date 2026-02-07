// Fix Principle Relationship Swap in Ingestion Config
// ====================================================
//
// Context: Ingestion config had Goal and Choice principle relationship types
// swapped. Goal ingestion created ALIGNED_WITH_PRINCIPLE edges (should be
// GUIDED_BY_PRINCIPLE), and Choice ingestion created GUIDED_BY_PRINCIPLE
// edges (should be ALIGNED_WITH_PRINCIPLE).
//
// Evidence:
//   - Goal services query GUIDED_BY_PRINCIPLE (goal.py, goals_recommendation_service, GOALS_UNIFIED registry)
//   - Choice services query ALIGNED_WITH_PRINCIPLE (choice.py, choices_search_service, CHOICES_UNIFIED registry)
//
// Run each statement separately.

// Step 1: Fix Goal->Principle: ALIGNED_WITH_PRINCIPLE -> GUIDED_BY_PRINCIPLE
MATCH (g:Goal)-[r:ALIGNED_WITH_PRINCIPLE]->(p:Principle)
MERGE (g)-[:GUIDED_BY_PRINCIPLE]->(p)
DELETE r
RETURN count(*) as goals_fixed;

// Step 2: Fix Choice->Principle: GUIDED_BY_PRINCIPLE -> ALIGNED_WITH_PRINCIPLE
MATCH (c:Choice)-[r:GUIDED_BY_PRINCIPLE]->(p:Principle)
MERGE (c)-[:ALIGNED_WITH_PRINCIPLE]->(p)
DELETE r
RETURN count(*) as choices_fixed;
