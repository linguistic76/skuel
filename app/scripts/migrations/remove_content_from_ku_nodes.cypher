// Migration: Remove content from Ku nodes
// Date: 2026-02-10
// Purpose: Content body now lives exclusively on :Content nodes (via HAS_CONTENT).
//          Ku nodes store word_count as computed metadata instead.
//
// Prerequisites: Ensure all Ku nodes have corresponding :Content nodes
//                via HAS_CONTENT relationships before running this migration.

// Step 1: Compute and store word_count from content before removing
MATCH (ku:Ku)
WHERE ku.content IS NOT NULL
SET ku.word_count = size(split(ku.content, ' '))
REMOVE ku.content
RETURN count(ku) as updated;

// Step 2: Set word_count = 0 for any Ku nodes that had no content
MATCH (ku:Ku)
WHERE ku.word_count IS NULL
SET ku.word_count = 0
RETURN count(ku) as backfilled;
