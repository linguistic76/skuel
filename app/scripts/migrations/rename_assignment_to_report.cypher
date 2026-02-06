// =============================================================================
// Migration: Rename Assignment → Report in Neo4j
// =============================================================================
// Date: 2026-02-06
// Context: Unifying Assignments + Reports under "Reports" domain
//
// Run each statement separately in Neo4j Browser or via cypher-shell.
// Back up your database before running.
// =============================================================================

// 1. Add :Report label to all existing :Assignment nodes
MATCH (a:Assignment)
SET a:Report
RETURN count(a) AS nodes_relabeled;

// 2. Remove the old :Assignment label
MATCH (a:Assignment)
REMOVE a:Assignment
RETURN count(a) AS old_labels_removed;

// 3. Update UID prefixes: assignment_ → report_
MATCH (r:Report) WHERE r.uid STARTS WITH 'assignment_'
SET r.uid = 'report_' + substring(r.uid, 11)
RETURN count(r) AS uids_updated;

// 4. Rename assignment_type property → report_type
//    Also flip the value: 'report' → 'assignment' (ReportType.ASSIGNMENT)
MATCH (r:Report) WHERE r.assignment_type IS NOT NULL
SET r.report_type = CASE r.assignment_type
    WHEN 'report' THEN 'assignment'
    ELSE r.assignment_type
END
REMOVE r.assignment_type
RETURN count(r) AS properties_renamed;

// 5. Update any SHARES_WITH relationships that reference assignment UIDs
//    (The relationship itself doesn't change, just verify integrity)
MATCH (u:User)-[s:SHARES_WITH]->(r:Report)
RETURN count(s) AS sharing_relationships_verified;

// 6. Verify migration
MATCH (r:Report) RETURN count(r) AS total_reports;
MATCH (a:Assignment) RETURN count(a) AS remaining_assignments;
// remaining_assignments should be 0
