// Migration: Collapse ExerciseSubmission + JeInput + JeOutput into UserEntry
// Date: 2026-04-14
// ADR: docs/decisions/ADR-054-user-entry-unified-submissions.md
//
// Context: ADR-054 collapses four parallel user-authored content types
// (Submission abstract base, ExerciseSubmission, JeInput, JeOutput) into a
// single UserEntry(UserOwnedEntity). The split was cosmetic. This migration
// relabels legacy nodes, assigns the new `pipeline` property based on their
// former type, moves `revision_number` from a node field to an edge property
// on FULFILLS_EXERCISE, and rebuilds the label-keyed indexes.
//
// Before: Nodes labelled :Entity:ExerciseSubmission / :Entity:JeInput /
//         :Entity:JeOutput, each with its own entity_type string.
// After:  Nodes labelled :Entity:UserEntry, entity_type='user_entry',
//         pipeline set from the old label, revision on the edge.
//
// Idempotent: re-running is a no-op because there are no legacy-labelled
// nodes left to match after the first successful run.

// ---------------------------------------------------------------------------
// 1. ExerciseSubmission -> UserEntry (pipeline = teacher_review)
// ---------------------------------------------------------------------------
CALL apoc.periodic.iterate(
  "MATCH (n:ExerciseSubmission) RETURN n",
  "SET n:UserEntry
   SET n.pipeline = 'teacher_review'
   SET n.entity_type = 'user_entry'
   REMOVE n:ExerciseSubmission",
  {batchSize: 500, parallel: false}
) YIELD batches, total
RETURN 'exercise_submission' AS source, batches, total;

// ---------------------------------------------------------------------------
// 2. JeInput -> UserEntry (pipeline depends on file_type)
// ---------------------------------------------------------------------------
CALL apoc.periodic.iterate(
  "MATCH (n:JeInput) RETURN n",
  "SET n:UserEntry
   SET n.pipeline = CASE
     WHEN n.file_type STARTS WITH 'audio/' THEN 'transcribe_and_structure'
     ELSE 'none' END
   SET n.entity_type = 'user_entry'
   REMOVE n:JeInput",
  {batchSize: 500, parallel: false}
) YIELD batches, total
RETURN 'je_input' AS source, batches, total;

// ---------------------------------------------------------------------------
// 3. JeOutput -> UserEntry (already processed; pipeline = none)
// ---------------------------------------------------------------------------
CALL apoc.periodic.iterate(
  "MATCH (n:JeOutput) RETURN n",
  "SET n:UserEntry
   SET n.pipeline = 'none'
   SET n.entity_type = 'user_entry'
   REMOVE n:JeOutput",
  {batchSize: 500, parallel: false}
) YIELD batches, total
RETURN 'je_output' AS source, batches, total;

// ---------------------------------------------------------------------------
// 4. Move revision_number from node field to FULFILLS_EXERCISE edge property
// ---------------------------------------------------------------------------
MATCH (u:UserEntry)-[r:FULFILLS_EXERCISE]->(:Exercise)
WHERE u.revision_number IS NOT NULL
SET r.revision = u.revision_number
REMOVE u.revision_number;

// Default revision to 1 on any FULFILLS_EXERCISE edge missing it
MATCH (:UserEntry)-[r:FULFILLS_EXERCISE]->(:Exercise)
WHERE r.revision IS NULL
SET r.revision = 1;

// ---------------------------------------------------------------------------
// 5. Drop legacy indexes
// ---------------------------------------------------------------------------
DROP INDEX exercise_submission_fulltext_idx IF EXISTS;
DROP INDEX je_input_fulltext_idx IF EXISTS;
DROP INDEX je_output_fulltext_idx IF EXISTS;
DROP INDEX exercise_submission_uid_idx IF EXISTS;
DROP INDEX je_input_uid_idx IF EXISTS;
DROP INDEX je_output_uid_idx IF EXISTS;

// ---------------------------------------------------------------------------
// 6. Create new UserEntry indexes
// ---------------------------------------------------------------------------
CREATE FULLTEXT INDEX user_entry_fulltext_idx IF NOT EXISTS
FOR (n:UserEntry) ON EACH [n.title, n.original_filename, n.processed_content, n.content];

CREATE INDEX user_entry_uid_idx IF NOT EXISTS
FOR (n:UserEntry) ON (n.uid);

CREATE INDEX user_entry_pipeline_idx IF NOT EXISTS
FOR (n:UserEntry) ON (n.pipeline);

// ---------------------------------------------------------------------------
// 7. Verification — all three counts must be zero
// ---------------------------------------------------------------------------
MATCH (n) WHERE n:ExerciseSubmission OR n:JeInput OR n:JeOutput
RETURN count(n) AS remaining_legacy_nodes;

MATCH (:UserEntry)-[r:FULFILLS_EXERCISE]->(:Exercise) WHERE r.revision IS NULL
RETURN count(r) AS fulfills_without_revision;

MATCH (u:UserEntry) WHERE u.revision_number IS NOT NULL
RETURN count(u) AS user_entries_with_stale_revision_field;
