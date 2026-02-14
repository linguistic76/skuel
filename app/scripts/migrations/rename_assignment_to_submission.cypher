// Migration: Rename ku_type "assignment" → "submission"
// Date: 2026-02-15
// Context: KuType.ASSIGNMENT renamed to KuType.SUBMISSION
//   - "assignment" in plain English means what a teacher gives (KuProject)
//   - "submission" matches what this actually is: student-uploaded work
//   - Aligns with existing service names (KuSubmissionService, KuSubmissionOperations)
//   - Aligns with existing route language (/reports/submit)

// Step 1: Rename ku_type property value on all Ku nodes
MATCH (k:Ku) WHERE k.ku_type = 'assignment'
SET k.ku_type = 'submission'
RETURN count(k) AS nodes_updated;
