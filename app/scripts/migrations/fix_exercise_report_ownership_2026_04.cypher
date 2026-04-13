// Migration: Fix ExerciseReport ownership vs authorship (2026-04)
// ================================================================
// Problem: user_uid on ExerciseReport previously meant the report's
//   *author* (teacher for HUMAN reports, student for LLM reports).
// Fix: user_uid now always stores the *student* (access ownership).
//   author_uid is a new property storing the teacher for HUMAN reports
//   and null for LLM/AI reports.
//
// Run phases in order. Phase 3 is a validation query — expected result: 0.

// --------------------------------------------------------------------
// Phase 1: Fix learning-loop teacher reports (created via create_report_node)
// These reports have REPORT_FOR → submission and a student reachable
// via (student)-[:OWNS]->(submission).
// --------------------------------------------------------------------
MATCH (teacher:User)-[owns_rel:OWNS]->(report:ExerciseReport {processor_type: 'human'})
MATCH (report)-[:REPORT_FOR]->(submission:Entity)<-[:OWNS]-(student:User)
WHERE teacher.uid <> student.uid
  AND (report.author_uid IS NULL OR report.user_uid <> student.uid)
SET report.author_uid = teacher.uid,
    report.user_uid = student.uid
DELETE owns_rel
MERGE (student)-[:OWNS]->(report)
RETURN count(report) AS fixed_learning_loop_reports;

// --------------------------------------------------------------------
// Phase 2: Fix standalone teacher assessments (created via backend.create()
// + ASSESSMENT_OF). These have no REPORT_FOR but do have ASSESSMENT_OF
// pointing to the student.
// --------------------------------------------------------------------
MATCH (teacher:User)-[owns_rel:OWNS]->(report:ExerciseReport {processor_type: 'human'})
WHERE NOT (report)-[:REPORT_FOR]->()
MATCH (report)-[:ASSESSMENT_OF]->(student:User)
WHERE teacher.uid <> student.uid
  AND report.user_uid <> student.uid
SET report.author_uid = teacher.uid,
    report.user_uid = student.uid
DELETE owns_rel
MERGE (student)-[:OWNS]->(report)
RETURN count(report) AS fixed_standalone_assessments;

// --------------------------------------------------------------------
// Phase 3: Validation — expected result: 0 mismatched_reports
// Any non-zero result means a report's OWNS edge source doesn't match
// the user_uid property (the invariant we're enforcing).
// --------------------------------------------------------------------
MATCH (owner:User)-[:OWNS]->(report:ExerciseReport)
WHERE owner.uid <> report.user_uid
RETURN count(report) AS mismatched_reports;
