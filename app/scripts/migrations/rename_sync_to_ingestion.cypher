// Migration: Rename Sync → Ingestion Node Labels
// Date: 2026-02-08
// Context: The ingestion system was incorrectly called "sync" despite being
//          a one-way pipeline (Markdown/YAML → Neo4j). No write-back exists.
//          This migration aligns Neo4j node labels with the new terminology.

// Step 1: Rename :SyncMetadata → :IngestionMetadata
MATCH (n:SyncMetadata)
SET n:IngestionMetadata
REMOVE n:SyncMetadata;

// Step 2: Rename property last_synced_at → last_ingested_at on IngestionMetadata nodes
MATCH (n:IngestionMetadata)
WHERE n.last_synced_at IS NOT NULL
SET n.last_ingested_at = n.last_synced_at
REMOVE n.last_synced_at;

// Step 3: Rename :SyncHistory → :IngestionHistory
MATCH (n:SyncHistory)
SET n:IngestionHistory
REMOVE n:SyncHistory;

// Step 4: Drop old constraints
DROP CONSTRAINT sync_metadata_file_path IF EXISTS;

// Step 5: Create new constraints
CREATE CONSTRAINT ingestion_metadata_file_path IF NOT EXISTS
FOR (n:IngestionMetadata) REQUIRE n.file_path IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS
FOR (ih:IngestionHistory) REQUIRE ih.operation_id IS UNIQUE;
