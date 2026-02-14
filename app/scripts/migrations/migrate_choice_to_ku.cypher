// ============================================================================
// Migration: Choice → Ku (February 2026)
// ============================================================================
// Phase 4 of Unified Ku Model migration (Activity Domains).
//
// Converts all :Choice nodes to :Ku nodes with ku_type='choice'.
//
// Changes:
//   1. :Choice nodes → :Ku label + ku_type='choice'
//   2. Status mapping: ChoiceStatus → KuStatus
//   3. Convert HAS_CHOICE → HAS_KU relationships
//
// Status mapping:
//   pending     → draft
//   decided     → active
//   implemented → active
//   evaluated   → completed
//   archived    → archived
//
// Preconditions:
//   - Choice nodes exist with status property (ChoiceStatus values)
//   - Ku model already expanded with DECISION fields (Phase 1)
//   - UniversalNeo4jBackend supports default_filters (Phase 2)
//
// Safe to re-run: All steps use SET (idempotent) and conditional matching.
// ============================================================================

// --- Step 1: Convert :Choice nodes to :Ku with ku_type='choice' ---
MATCH (n:Choice)
SET n:Ku,
    n.ku_type = 'choice',
    n.status = CASE n.status
        WHEN 'pending' THEN 'draft'
        WHEN 'decided' THEN 'active'
        WHEN 'implemented' THEN 'active'
        WHEN 'evaluated' THEN 'completed'
        WHEN 'archived' THEN 'archived'
        ELSE COALESCE(n.status, 'draft')
    END
REMOVE n:Choice
RETURN count(n) as choice_nodes_converted;

// --- Step 2: Convert HAS_CHOICE → HAS_KU relationships ---
MATCH (u)-[old:HAS_CHOICE]->(k:Ku {ku_type: 'choice'})
MERGE (u)-[:HAS_KU]->(k)
DELETE old
RETURN count(old) as has_choice_relationships_converted;

// --- Step 3: Verify no :Choice nodes remain ---
MATCH (n:Choice)
RETURN count(n) as remaining_choice_nodes;
