// Migration: Hash session tokens at rest (2026-03-04)
// =====================================================
// Backfills token_hash on existing Session nodes and removes raw session_token.
//
// Prerequisites:
//   - APOC plugin installed (for apoc.util.sha256)
//   - Run AFTER deploying the new session_backend.py that queries by token_hash
//
// Step 1: Backfill token_hash from session_token
MATCH (s:Session)
WHERE s.session_token IS NOT NULL AND (s.token_hash IS NULL OR s.token_hash = "")
SET s.token_hash = apoc.util.sha256([s.session_token])
RETURN count(s) AS backfilled;

// Step 2: Verify all sessions have token_hash
MATCH (s:Session)
WHERE s.token_hash IS NULL OR s.token_hash = ""
RETURN count(s) AS missing_hash;
// Expected: 0

// Step 3: Remove raw session_token from all Session nodes
// IMPORTANT: Only run AFTER verifying Step 2 returns 0
MATCH (s:Session)
WHERE s.session_token IS NOT NULL
REMOVE s.session_token
RETURN count(s) AS cleaned;

// Step 4: Create index on token_hash for fast lookups
CREATE INDEX session_token_hash_idx IF NOT EXISTS FOR (s:Session) ON (s.token_hash);
