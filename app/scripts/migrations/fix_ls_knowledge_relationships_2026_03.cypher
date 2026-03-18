// Migration: Fix LS knowledge relationships
// Date: 2026-03-18
// Context: CRUD methods in ls_core_service.py incorrectly used REQUIRES_KNOWLEDGE
// for primary/supporting KU links. The canonical relationship is CONTAINS_KNOWLEDGE.
// REQUIRES_KNOWLEDGE with type 'prerequisite' is correct and left unchanged.

// Step 1: Migrate primary knowledge relationships
MATCH (ls:Entity {entity_type: 'learning_step'})-[r:REQUIRES_KNOWLEDGE {type: 'primary'}]->(ku:Entity)
CREATE (ls)-[:CONTAINS_KNOWLEDGE {
    type: 'primary',
    created_at: coalesce(r.created_at, datetime()),
    updated_at: datetime(),
    confidence: r.confidence
}]->(ku)
DELETE r
RETURN count(*) AS migrated_primary;

// Step 2: Migrate supporting knowledge relationships
MATCH (ls:Entity {entity_type: 'learning_step'})-[r:REQUIRES_KNOWLEDGE {type: 'supporting'}]->(ku:Entity)
CREATE (ls)-[:CONTAINS_KNOWLEDGE {
    type: 'supporting',
    created_at: coalesce(r.created_at, datetime()),
    updated_at: datetime(),
    confidence: r.confidence
}]->(ku)
DELETE r
RETURN count(*) AS migrated_supporting;

// Step 3: Verify prerequisite relationships are untouched
MATCH (ls:Entity {entity_type: 'learning_step'})-[r:REQUIRES_KNOWLEDGE {type: 'prerequisite'}]->(ku:Entity)
RETURN count(*) AS prerequisite_count_unchanged;

// Step 4: Verify no primary/supporting REQUIRES_KNOWLEDGE remain
MATCH (ls:Entity {entity_type: 'learning_step'})-[r:REQUIRES_KNOWLEDGE]->(ku:Entity)
WHERE r.type IN ['primary', 'supporting']
RETURN count(*) AS should_be_zero;
