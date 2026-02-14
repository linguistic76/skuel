// ============================================================================
// Migration: Unify Report → Ku (February 2026)
// ============================================================================
// "Ku is the heartbeat of SKUEL"
//
// This migration converts all :Report nodes to :Ku nodes as part of the
// unified Ku model. Reports are user-submitted content; Ku is now the single
// content entity for both curriculum AND submissions.
//
// Changes:
//   1. :Report nodes → :Ku label, report_type → ku_type, status mapping
//   2. Existing :Ku nodes → set ku_type = 'curriculum'
//   3. :ReportProject → :KuProject
//   4. HAS_REPORT relationships → HAS_KU
//   5. HAS_REPORTPROJECT relationships → HAS_KUPROJECT
//
// Preconditions:
//   - Report nodes have report_type property ("assignment", "journal", etc.)
//   - Existing Ku nodes have NO ku_type property (null)
//
// Safe to re-run: All steps use SET (idempotent) and conditional matching.
// ============================================================================

// --- Step 1: Convert :Report nodes to :Ku ---
// Map report_type → ku_type:
//   "assignment" → "submission" (KuType.SUBMISSION — renamed Feb 2026)
//   "journal" → "submission" (journals are SUBMISSION with journal metadata)
//   "progress" → "ai_report" (system-generated)
//   "assessment" → "feedback_report" (teacher feedback)
//   everything else → "submission" (default)
// NOTE: Run rename_assignment_to_submission.cypher after this migration
//       if any nodes were created with ku_type="assignment".

MATCH (r:Report)
SET r:Ku,
    r.ku_type = CASE r.report_type
        WHEN 'assignment' THEN 'submission'
        WHEN 'journal' THEN 'submission'
        WHEN 'transcript' THEN 'submission'
        WHEN 'image_analysis' THEN 'submission'
        WHEN 'video_summary' THEN 'submission'
        WHEN 'progress' THEN 'ai_report'
        WHEN 'assessment' THEN 'feedback_report'
        ELSE 'submission'
    END
REMOVE r:Report
RETURN count(r) as report_nodes_converted;

// --- Step 2: Set ku_type on existing curriculum Ku nodes ---
// These were created before the unified model and have ku_type = null

MATCH (k:Ku)
WHERE k.ku_type IS NULL
SET k.ku_type = 'curriculum'
RETURN count(k) as curriculum_nodes_updated;

// --- Step 3: Convert :ReportProject to :KuProject ---

MATCH (rp:ReportProject)
SET rp:KuProject
REMOVE rp:ReportProject
RETURN count(rp) as projects_converted;

// --- Step 4: Convert HAS_REPORT relationships to HAS_KU ---
// UniversalNeo4jBackend uses HAS_{LABEL} pattern for ownership

MATCH (u)-[old:HAS_REPORT]->(k:Ku)
MERGE (u)-[:HAS_KU]->(k)
DELETE old
RETURN count(old) as report_rels_converted;

// --- Step 5: Convert HAS_REPORTPROJECT relationships to HAS_KUPROJECT ---

MATCH (u)-[old:HAS_REPORTPROJECT]->(kp:KuProject)
MERGE (u)-[:HAS_KUPROJECT]->(kp)
DELETE old
RETURN count(old) as project_rels_converted;
