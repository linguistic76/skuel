// Migration: Remove legacy JournalProject node and relationship
// Date: 2026-02-08
// Context: Journal domain was merged into Reports (2026-02-06).
//          ReportProject node already exists as the replacement.
//          JournalProject is a stale duplicate with identical data.
//
// Pre-migration state:
//   (User:user_system)-[:HAS_JOURNALPROJECT]->(JournalProject {uid: "jp.transcript_default"})
//   (User:user_system)-[:HAS_REPORTPROJECT]->(ReportProject {uid: "jp.transcript_default"})
//
// Post-migration state:
//   (User:user_system)-[:HAS_REPORTPROJECT]->(ReportProject {uid: "jp.transcript_default"})
//   JournalProject node and HAS_JOURNALPROJECT relationship deleted.

// Step 1: Delete the HAS_JOURNALPROJECT relationship and the JournalProject node
MATCH (u:User)-[r:HAS_JOURNALPROJECT]->(jp:JournalProject)
DELETE r, jp;
