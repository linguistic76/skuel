// =============================================================================
// Migration: Rename KuProject → Assignment in Neo4j
// =============================================================================
// Date: 2026-02-16
// Context: Renaming KuProject nodes to Assignment as part of the
//          KuProject→Assignment refactoring (code already updated).
//
// Run each statement separately in Neo4j Browser or via cypher-shell.
// Back up your database before running.
// =============================================================================

// 1. Add :Assignment label to all existing :KuProject nodes
MATCH (p:KuProject)
SET p:Assignment
RETURN count(p) AS nodes_relabeled;

// 2. Remove the old :KuProject label
MATCH (p:KuProject)
REMOVE p:KuProject
RETURN count(p) AS old_labels_removed;

// 3. Verify migration — no :KuProject nodes should remain
MATCH (p:KuProject) RETURN count(p) AS remaining_kuprojects;
// remaining_kuprojects should be 0

// 4. Verify :Assignment nodes exist
MATCH (a:Assignment) RETURN count(a) AS total_assignments;

// 5. Verify relationships are intact
//    FOR_GROUP: Assignment targets a Group
MATCH (a:Assignment)-[r:FOR_GROUP]->(g:Group)
RETURN count(r) AS for_group_relationships;

//    FULFILLS_PROJECT: Ku fulfills an Assignment
MATCH (k:Ku)-[r:FULFILLS_PROJECT]->(a:Assignment)
RETURN count(r) AS fulfills_project_relationships;

//    OWNS: User owns an Assignment
MATCH (u:User)-[r:OWNS]->(a:Assignment)
RETURN count(r) AS owns_relationships;
