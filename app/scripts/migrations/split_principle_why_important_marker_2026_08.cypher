// Migration: Split the spliced why_important marker out of Principle.description (2026-08)
// ==========================================================================
// Problem: ``why_important`` was a request-only field with no Principle column.
//   The create/update flow appended it to ``description`` behind a canonical
//   marker ("\n\nWhy this matters:\n") via merge_why_important(), and the edit
//   form reversed the splice with split_why_important() for prefill. One field's
//   text lived inside another field's column, invisible to anything that read
//   ``description`` as prose.
//
// Fix (same PR as this file): ``why_important`` became a real column on
//   Principle / PrincipleDTO / PrincipleUpdateIntent, and both splice helpers
//   were deleted. This migration converges rows already written the old way.
//
// Note the graph was ALREADY ahead of the model here: vault-authored principles
//   carry a real ``why_important`` property (ingestion writes frontmatter keys
//   verbatim), which the model simply could not read. Those rows need nothing —
//   the promotion alone makes them legible. Only rows written through the API /
//   UI door carry the marker.
//
// Idempotent: the WHERE clause matches only descriptions that still contain the
//   marker, and the split removes it — a second run matches zero rows.
//
// Non-destructive on conflict: a row that somehow has BOTH a spliced marker and
//   a non-null ``why_important`` is left alone (statement 2 reports it) rather
//   than having one silently overwrite the other.
//
// Verify (before/after):
//   MATCH (p:Principle) WHERE p.description CONTAINS 'Why this matters:'
//   RETURN count(p) AS still_spliced
//   -- After: 0. Audit of 2026-08-18 (AuraDB d2d160c4): 0 before as well —
//   -- both live principles are vault-authored and were never spliced.

// Statement 1: split marker-carrying descriptions into (description, why_important).
// rpartition semantics of split_why_important(): the LAST marker is the separator,
// everything before it stays description. An empty half becomes null, matching the
// helper's `or None` returns.
MATCH (p:Principle)
WHERE p.description CONTAINS '\n\nWhy this matters:\n'
  AND p.why_important IS NULL
WITH p,
     split(p.description, '\n\nWhy this matters:\n') AS parts
WITH p,
     parts,
     size(parts) AS n
WITH p,
     // everything before the LAST marker, re-joined with the marker itself
     reduce(acc = '', i IN range(0, n - 2) |
       CASE WHEN i = 0 THEN parts[i] ELSE acc + '\n\nWhy this matters:\n' + parts[i] END
     ) AS prose,
     parts[n - 1] AS why
SET p.description = CASE WHEN prose = '' THEN null ELSE prose END,
    p.why_important = CASE WHEN why = '' THEN null ELSE why END,
    // The stored embedding text changes, so drop the freshness hash: the next
    // `./dev embed-backfill --stale` (or a normal update) re-embeds this node
    // instead of skipping it as unchanged (ADR-074 §8).
    p.embedding_text_hash = null;

// Statement 2: report — never rewrite — rows where both halves are already populated.
// A non-empty result means a principle carries a spliced marker AND a real
// why_important column; decide per row rather than letting either win silently.
MATCH (p:Principle)
WHERE p.description CONTAINS '\n\nWhy this matters:\n'
  AND p.why_important IS NOT NULL
RETURN p.uid AS uid, p.why_important AS existing_why_important, p.description AS description;
