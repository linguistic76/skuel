// ============================================================================
// Migration: Merge Journal Domain into Reports Domain
// Date: 2026-02-06
// Description: Converts all :Journal nodes to :Report nodes with
//              report_type="journal", and :JournalProject to :ReportProject.
// ============================================================================

// Step 1: Add :Report label to all existing :Journal nodes
MATCH (j:Journal)
SET j:Report;

// Step 2: Set report_type="journal" on former journal nodes
MATCH (j:Journal:Report)
WHERE j.report_type IS NULL
SET j.report_type = "journal";

// Step 3: Map ContentStatus -> ReportStatus
// "transcribed" -> "processing" (content received, being processed)
MATCH (r:Journal:Report)
WHERE r.status = "transcribed"
SET r.status = "processing";

// "processed" -> "completed" (processing finished)
MATCH (r:Journal:Report)
WHERE r.status = "processed"
SET r.status = "completed";

// "published" -> "completed" + public visibility
MATCH (r:Journal:Report)
WHERE r.status = "published"
SET r.status = "completed", r.visibility = "public";

// Step 4: Remove :Journal label from all nodes
MATCH (j:Journal:Report)
REMOVE j:Journal;

// Step 5: Migrate :JournalProject -> :ReportProject
MATCH (jp:JournalProject)
SET jp:ReportProject;

MATCH (jp:JournalProject:ReportProject)
REMOVE jp:JournalProject;

// ============================================================================
// Verification Queries (run individually to confirm migration)
// ============================================================================

// Expect 0 remaining :Journal nodes
// MATCH (j:Journal) RETURN count(j) AS remaining_journals;

// Expect 0 remaining :JournalProject nodes
// MATCH (jp:JournalProject) RETURN count(jp) AS remaining_projects;

// Show count of migrated journal-type reports
// MATCH (r:Report {report_type: "journal"}) RETURN count(r) AS journal_reports;

// Show count of migrated report projects
// MATCH (rp:ReportProject) RETURN count(rp) AS report_projects;
