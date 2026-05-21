// Audit: Students exceeding MAX_STUDENT_GROUPS (=4)
// ====================================================
//
// The /groups hub (commit 5244fa53) introduced MAX_STUDENT_GROUPS = 4 —
// enforced server-side in GroupService.add_member() for role="student".
// The cap is forward-looking; it does not retroactively remove a student
// from groups they were already in.
//
// This script is READ-ONLY. It surfaces any students who are already
// members of more than 4 groups, so a teacher can decide which groups
// to remove them from. No MERGE, SET, or DELETE.
//
// Mirrors add_member() cap semantics: counts ALL MEMBER_OF edges from a
// user to a Group, without filtering by per-edge role, because that is
// how GroupService.add_member() evaluates the cap (line 225 calls
// get_user_groups(user_uid) which returns every group the user belongs
// to).
//
// Run:
//   cypher-shell -u neo4j -p <password> \
//     -f scripts/migrations/audit_students_exceeding_group_cap_2026_04.cypher

MATCH (u:User)-[:MEMBER_OF]->(g:Group)
WITH u, count(g) AS n_groups
WHERE n_groups > 4
RETURN u.user_uid AS user_uid,
       u.display_name AS display_name,
       n_groups
ORDER BY n_groups DESC;
