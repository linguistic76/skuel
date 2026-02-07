// Unify Ingestion Relationship Types (February 2026)
// ===================================================
//
// Eliminates the ingestion/registry divergence by renaming edge types
// to match the Relationship Registry (single source of truth).
//
// Three fixes:
//   1. PREREQUISITE → REQUIRES_KNOWLEDGE (KU-to-KU, reverse direction)
//   2. ENABLES → ENABLES_KNOWLEDGE (KU-to-KU, same direction)
//   3. ALIGNED_WITH_PRINCIPLE → INFORMED_BY_PRINCIPLE (Choice→Principle)
//   4. REQUIRES → REQUIRES_KNOWLEDGE (legacy bulk template variant)
//
// Run each statement separately in Neo4j Browser or cypher-shell.
// See: ADR-026-unified-relationship-registry.md

// ---------------------------------------------------------------------------
// Step 1: PREREQUISITE → REQUIRES_KNOWLEDGE (reverse direction)
//
// Ingestion created: (prereq)-[:PREREQUISITE]->(dependent)
//   meaning "prereq is prerequisite for dependent"
// Registry expects:  (dependent)-[:REQUIRES_KNOWLEDGE]->(prereq)
//   meaning "dependent requires prereq"
// Same semantics, reversed direction + renamed.
// ---------------------------------------------------------------------------
MATCH (a:Ku)-[r:PREREQUISITE]->(b:Ku)
MERGE (b)-[:REQUIRES_KNOWLEDGE]->(a)
DELETE r
RETURN count(*) as prerequisite_edges_migrated;

// ---------------------------------------------------------------------------
// Step 2: REQUIRES → REQUIRES_KNOWLEDGE (same direction)
//
// Legacy bulk_knowledge_units.cypher template used REQUIRES (yet another
// variant). These already follow the dependent→prereq convention.
// ---------------------------------------------------------------------------
MATCH (a:Ku)-[r:REQUIRES]->(b:Ku)
MERGE (a)-[:REQUIRES_KNOWLEDGE]->(b)
DELETE r
RETURN count(*) as requires_edges_migrated;

// ---------------------------------------------------------------------------
// Step 3: ENABLES → ENABLES_KNOWLEDGE (same direction, KU-to-KU only)
//
// Both old and new use outgoing: (ku)-[:rel]->(target)
// Only rename Ku-to-Ku edges (ENABLES_TASK is a separate relationship).
// ---------------------------------------------------------------------------
MATCH (a:Ku)-[r:ENABLES]->(b:Ku)
MERGE (a)-[:ENABLES_KNOWLEDGE]->(b)
DELETE r
RETURN count(*) as enables_edges_migrated;

// ---------------------------------------------------------------------------
// Step 4: Choice ALIGNED_WITH_PRINCIPLE → INFORMED_BY_PRINCIPLE
//
// Ingestion bug: Choice edges used ALIGNED_WITH_PRINCIPLE (which the registry
// defines as Task→Principle). The registry expects INFORMED_BY_PRINCIPLE for
// Choice→Principle. Scoped to Choice→Principle only — Task→Principle edges
// with ALIGNED_WITH_PRINCIPLE are correct and unchanged.
// ---------------------------------------------------------------------------
MATCH (c:Choice)-[r:ALIGNED_WITH_PRINCIPLE]->(p:Principle)
MERGE (c)-[:INFORMED_BY_PRINCIPLE]->(p)
DELETE r
RETURN count(*) as choice_principle_edges_fixed;

// ---------------------------------------------------------------------------
// Step 5: Verification — all old edge types should return 0 remaining
// ---------------------------------------------------------------------------
MATCH ()-[r:PREREQUISITE]->()
RETURN 'PREREQUISITE' as type, count(r) as remaining
UNION ALL
MATCH (:Ku)-[r:ENABLES]->(:Ku)
RETURN 'ENABLES (Ku→Ku)' as type, count(r) as remaining
UNION ALL
MATCH (:Ku)-[r:REQUIRES]->(:Ku)
RETURN 'REQUIRES (Ku→Ku)' as type, count(r) as remaining
UNION ALL
MATCH (:Choice)-[r:ALIGNED_WITH_PRINCIPLE]->(:Principle)
RETURN 'Choice ALIGNED_WITH_PRINCIPLE' as type, count(r) as remaining;
