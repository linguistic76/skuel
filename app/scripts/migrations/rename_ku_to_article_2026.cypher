// =============================================================================
// Migration: Rename :Ku → :Article in Neo4j
// Date: 2026-03-06
// Context: KU→Article split — old Ku (unit for learning) becomes Article,
//          KU is reused for new atomic knowledge units
// =============================================================================

// Step 1: Update ku_type property from 'ku' to 'article'
MATCH (n:Entity {ku_type: 'ku'})
SET n.ku_type = 'article'
RETURN count(n) AS nodes_updated;

// Step 2: Relabel :Ku → :Article
MATCH (n:Entity:Ku)
REMOVE n:Ku
SET n:Article
RETURN count(n) AS nodes_relabeled;

// Step 3: Verify — catch any stragglers
MATCH (n:Entity {ku_type: 'article'})
WHERE NOT n:Article
SET n:Article
RETURN count(n) AS fixed;

// Step 4: Verify no old :Ku nodes remain with ku_type='article'
MATCH (n:Ku)
RETURN count(n) AS remaining_ku_nodes;
// Expected: 0 (or only new atomic Ku nodes if they've been created)
