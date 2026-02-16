// ============================================================================
// Migration: Voice-First Journal Refactoring
// Date: 2026-02-16
// ============================================================================
//
// What this migration does:
// 1. Add max_retention field to existing journal Ku nodes
//    - Audio journals (file_type starts with "audio/") → max_retention: 3 (FIFO)
//    - Text journals → max_retention: null (permanent)
// 2. Remove stale journal metadata fields (journal_type, journal_category, journal_mode)
// 3. Copy enrichment_mode from metadata to top-level field on Assignment nodes
//
// Prerequisites:
// - Ku nodes with ku_type="journal" must already exist
// - Run AFTER remove_moc_ku_type.cypher
//
// Rollback: Not needed — max_retention=null is the default for new fields
// ============================================================================

// Step 1: Set max_retention=3 on audio journal Ku nodes (FIFO behavior)
MATCH (k:Ku {ku_type: "journal"})
WHERE k.file_type STARTS WITH "audio/"
  AND k.max_retention IS NULL
SET k.max_retention = 3
RETURN count(k) AS audio_journals_updated;

// Step 2: Ensure text journal Ku nodes have no max_retention (permanent by default)
// This is a no-op since null is already the default, but documents intent
MATCH (k:Ku {ku_type: "journal"})
WHERE NOT k.file_type STARTS WITH "audio/"
  AND k.max_retention IS NOT NULL
REMOVE k.max_retention
RETURN count(k) AS text_journals_cleared;

// Step 3: Remove stale journal metadata properties from Ku nodes
// These enum-based fields are replaced by max_retention and enrichment_mode
MATCH (k:Ku {ku_type: "journal"})
WHERE k.journal_type IS NOT NULL
   OR k.journal_category IS NOT NULL
   OR k.journal_mode IS NOT NULL
REMOVE k.journal_type, k.journal_category, k.journal_mode
RETURN count(k) AS metadata_cleaned;

// Step 4: Copy enrichment_mode from Assignment metadata to top-level field
// (if any Assignment nodes have enrichment_mode in their metadata JSON)
// Note: This is forward-looking — new assignments will have enrichment_mode as a field
MATCH (a:Assignment)
WHERE a.enrichment_mode IS NULL
  AND a.metadata IS NOT NULL
  AND a.metadata CONTAINS "enrichment_mode"
RETURN count(a) AS assignments_needing_enrichment_mode_migration;
// Manual step: If count > 0, parse JSON metadata and extract enrichment_mode

// Step 5: Verify migration
MATCH (k:Ku {ku_type: "journal"})
WITH count(k) AS total,
     count(CASE WHEN k.max_retention IS NOT NULL THEN 1 END) AS with_retention,
     count(CASE WHEN k.journal_type IS NOT NULL THEN 1 END) AS stale_journal_type,
     count(CASE WHEN k.journal_category IS NOT NULL THEN 1 END) AS stale_journal_category,
     count(CASE WHEN k.journal_mode IS NOT NULL THEN 1 END) AS stale_journal_mode
RETURN total AS total_journals,
       with_retention AS journals_with_max_retention,
       stale_journal_type AS remaining_journal_type,
       stale_journal_category AS remaining_journal_category,
       stale_journal_mode AS remaining_journal_mode;
// Expected: remaining_* should all be 0
