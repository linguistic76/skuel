// Migration: Remove KuType.MOC — Generalize ORGANIZES to All KuTypes
// Date: 2026-02-16
// Context: MOC identity is emergent (defined by ORGANIZES relationships),
//          not a type discriminator. Existing MOC nodes become CURRICULUM.
//          ORGANIZES relationships are preserved — they are generic graph infrastructure.

// Step 1: Migrate existing MOC nodes to CURRICULUM
MATCH (ku:Ku {ku_type: 'moc'})
SET ku.ku_type = 'curriculum'
RETURN count(ku) AS migrated_count;

// Step 2: Verify no MOC nodes remain
MATCH (ku:Ku {ku_type: 'moc'})
RETURN count(ku) AS remaining_moc_count;
// Expected: 0

// Step 3: Verify ORGANIZES relationships are intact
MATCH ()-[r:ORGANIZES]->()
RETURN count(r) AS organizes_count;
