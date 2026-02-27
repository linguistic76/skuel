// =============================================================================
// Migration: Rename EntityType.CURRICULUM → EntityType.KU in Neo4j
// Date: 2026-02-27
// =============================================================================
//
// Context:
//   - EntityType.CURRICULUM ("curriculum") → EntityType.KU ("ku")
//   - NeoLabel.CURRICULUM ("Curriculum") → NeoLabel.KU ("Ku")
//   - The Curriculum Python class is now a BASE CLASS only
//   - Ku(Curriculum) is the concrete leaf class for atomic knowledge units
//
// Three steps:
//   1. Update ku_type property: 'curriculum' → 'ku'
//   2. Relabel nodes: remove :Curriculum, add :Ku (for nodes with old dual-label)
//   3. Add :Ku label to nodes that only have :Entity label (single-label format)
//
// After migration: MATCH (n:Entity {ku_type:'curriculum'}) RETURN count(n) → 0
//                  MATCH (n:Ku) RETURN count(n)                             → 44
//                  MATCH (n:Entity {ku_type:'ku'}) RETURN count(n)          → 44
//
// Backward compat: EntityType.from_string("curriculum") still resolves to KU
//                  via alias in _ENTITY_TYPE_ALIASES dict
// =============================================================================


// Step 1: Update ku_type property: 'curriculum' → 'ku'
MATCH (n:Entity {ku_type: 'curriculum'})
SET n.ku_type = 'ku'
RETURN count(n) AS nodes_updated;

// Step 2: Relabel :Entity:Curriculum → :Entity:Ku
//   (nodes that have the old :Curriculum domain label)
MATCH (n:Entity:Curriculum)
REMOVE n:Curriculum
SET n:Ku
RETURN count(n) AS nodes_relabeled_from_curriculum;

// Step 3: Add :Ku label to :Entity nodes with ku_type='ku' that don't have it yet
//   (nodes that were in single-label format, now upgraded to dual-label)
MATCH (n:Entity {ku_type: 'ku'})
WHERE NOT n:Ku
SET n:Ku
RETURN count(n) AS nodes_labeled_ku;
