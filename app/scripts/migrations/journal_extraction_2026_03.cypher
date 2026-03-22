// Journal Domain Extraction — March 2026
// ========================================
//
// Migrates JournalSubmission → JeInput and JournalReport → JeOutput
// as part of extracting Journal as a standalone domain.
//
// Journal is NOT a submission (no authority receives it) and its processed
// form is NOT a report (transformation, not interpretation).
//
// Pipeline: JE_INPUT(audio) → Deepgram → JE_INPUT(text) → LLM → JE_OUTPUT
//
// Run with: cat scripts/migrations/journal_extraction_2026_03.cypher | cypher-shell -u neo4j -p <password>

// Step 1: Rename :JournalSubmission nodes → :JeInput
// Remove :Submission base label (no longer a submission)
MATCH (n:JournalSubmission)
SET n:JeInput, n.entity_type = 'je_input'
REMOVE n:JournalSubmission, n:Submission;

// Step 2: Rename :JournalReport nodes → :JeOutput
// Remove :SubmissionReport base label (no longer a report)
MATCH (n:JournalReport)
SET n:JeOutput, n.entity_type = 'je_output'
REMOVE n:JournalReport, n:SubmissionReport;

// Step 3: Create TRANSFORMS relationships from existing REPORT_FOR
// (JeOutput was linked to JeInput via REPORT_FOR — rename to TRANSFORMS)
MATCH (o:JeOutput)-[r:REPORT_FOR]->(i:JeInput)
MERGE (o)-[:TRANSFORMS]->(i)
DELETE r;

// Step 4: Migrate field names on JeOutput nodes
// report_content → output_content, report_generated_at → output_generated_at
// subject_uid → source_je_input_uid, report_file_path → output_file_path
MATCH (o:JeOutput)
WHERE o.report_content IS NOT NULL
SET o.output_content = o.report_content,
    o.output_generated_at = o.report_generated_at,
    o.source_je_input_uid = o.subject_uid,
    o.output_file_path = o.report_file_path
REMOVE o.report_content, o.report_generated_at, o.subject_uid, o.report_file_path;

// Step 5: Verify migration
MATCH (n:JeInput) RETURN 'JeInput' AS label, count(n) AS count
UNION ALL
MATCH (n:JeOutput) RETURN 'JeOutput' AS label, count(n) AS count
UNION ALL
MATCH (n:JournalSubmission) RETURN 'JournalSubmission (should be 0)' AS label, count(n) AS count
UNION ALL
MATCH (n:JournalReport) RETURN 'JournalReport (should be 0)' AS label, count(n) AS count;
