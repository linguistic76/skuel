// Migration: converge the graph on two promoted Activity columns (2026-08)
// ==========================================================================
// PR: Principle.why_important and Choice.decision_context became real columns.
// Three things in the graph need converging, and only the first is a data move —
// the other two are embedding invalidations, because the same PR changed what
// text an entity's vector is built from.
//
// ---------------------------------------------------------------------------
// 1. why_important spliced into description (the data move)
// ---------------------------------------------------------------------------
// ``why_important`` had no Principle column. The create/update flow appended it
// to ``description`` behind a marker ("\n\nWhy this matters:\n") via
// merge_why_important(), and the edit form reversed the splice for prefill. One
// field's text lived inside another field's column. Both helpers are deleted;
// statement 1 below moves the text to its own column.
//
// Note the graph was ALREADY ahead of the model here: vault-authored principles
// carry a real ``why_important`` property (ingestion writes frontmatter keys
// verbatim), which the model simply could not read. Those rows need no move —
// the promotion alone makes them legible. Only rows written through the API / UI
// door carry the marker, and this graph holds none (audit 2026-08-18: 2
// principles, 0 spliced, 2 already carrying the column).
//
// ---------------------------------------------------------------------------
// 2 + 3. Vectors whose text recipe changed (the invalidation)
// ---------------------------------------------------------------------------
// EMBEDDING_FIELD_MAPS gained ``why_important`` for PRINCIPLE and swapped CHOICE's
// phantom ``outcome`` for the real ``actual_outcome``. Any node already carrying
// one of those properties was embedded from the OLD recipe, so its stored vector
// omits text the current recipe includes.
//
// Nothing would have caught this on its own. ``generate_embeddings_batch.py``'s
// ``--stale`` coarse filter selects on version-mismatch or updated_at drift ONLY;
// a changed recipe moves neither, so these nodes never reach the hash comparison
// that would notice. Clearing ``embedding_text_hash`` alone does NOT help for the
// same reason — a null hash is not a coarse-filter predicate.
//
// So statements 2 and 3 null ``embedding_version``, which does both jobs:
//   - the coarse filter selects it (``n.embedding_version IS NULL``), and
//   - ``EmbeddingsService.verify_fresh_embeddings`` cannot call it fresh
//     (version outranks hash — a version mismatch is never fresh).
// The stale hash is cleared alongside, since it now describes text that is no
// longer what the node would embed.
//
// Deliberately NOT done: bumping the global EMBEDDING_VERSION constant (that
// re-embeds all 16 entity types for a change that touched 2), or touching
// ``updated_at`` (which would lie about when the entity itself last changed).
//
// AFTER RUNNING THIS, RUN:  ./dev embed-backfill --stale
// (without it the affected nodes keep serving their old vectors — correct rows,
// stale semantics. `--audit` also catches them, but `--stale` now suffices.)
//
// Idempotent throughout: statement 1 matches only descriptions that still carry
// the marker and removes it; statements 2-3 match only nodes whose version is
// still non-null, and null it.
//
// Verify (after):
//   MATCH (p:Principle) WHERE p.description CONTAINS 'Why this matters:'
//   RETURN count(p) AS still_spliced;                          // expect 0
//   MATCH (n) WHERE n.embedding_version IS NULL AND n.embedding IS NOT NULL
//   RETURN labels(n) AS labels, count(*) AS awaiting_reembed;  // expect 0 after
//                                                              // ./dev embed-backfill --stale

// ---------------------------------------------------------------------------
// Statement 1: split marker-carrying descriptions into (description, why_important).
// Reproduces split_why_important()'s rpartition semantics: the LAST marker is the
// separator, earlier marker text stays in the prose half. An empty half becomes
// null, matching the helper's `or None` returns. Verified against these exact
// four shapes before deletion, including the double-marker case.
// ---------------------------------------------------------------------------
MATCH (p:Principle)
WHERE p.description CONTAINS '\n\nWhy this matters:\n'
  AND p.why_important IS NULL
WITH p, split(p.description, '\n\nWhy this matters:\n') AS parts
WITH p, parts, size(parts) AS n
WITH p,
     // everything before the LAST marker, re-joined with the marker itself
     reduce(acc = '', i IN range(0, n - 2) |
       CASE WHEN i = 0 THEN parts[i] ELSE acc + '\n\nWhy this matters:\n' + parts[i] END
     ) AS prose,
     parts[n - 1] AS why
SET p.description = CASE WHEN prose = '' THEN null ELSE prose END,
    p.why_important = CASE WHEN why = '' THEN null ELSE why END,
    p.embedding_version = null,
    p.embedding_text_hash = null;

// ---------------------------------------------------------------------------
// Statement 2: report — never rewrite — rows where both halves are populated.
// A non-empty result means a principle carries a spliced marker AND a real
// why_important column; decide per row rather than letting either win silently.
// ---------------------------------------------------------------------------
MATCH (p:Principle)
WHERE p.description CONTAINS '\n\nWhy this matters:\n'
  AND p.why_important IS NOT NULL
RETURN p.uid AS uid, p.why_important AS existing_why_important, p.description AS description;

// ---------------------------------------------------------------------------
// Statement 3: invalidate Principle vectors built before why_important joined the
// recipe. Scoped to nodes that actually carry the property — a principle without
// one embeds identical text under either recipe and must not be re-embedded.
// ---------------------------------------------------------------------------
MATCH (p:Principle)
WHERE p.why_important IS NOT NULL
  AND p.embedding IS NOT NULL
  AND p.embedding_version IS NOT NULL
SET p.embedding_version = null,
    p.embedding_text_hash = null;

// ---------------------------------------------------------------------------
// Statement 4: the same for Choice vectors built while the map named the phantom
// ``outcome`` instead of ``actual_outcome``. Zero rows at authoring time (audit
// 2026-08-18: no choice carries an outcome yet) — written generally so it is
// still correct whenever this actually runs.
// ---------------------------------------------------------------------------
MATCH (c:Choice)
WHERE c.actual_outcome IS NOT NULL
  AND c.embedding IS NOT NULL
  AND c.embedding_version IS NOT NULL
SET c.embedding_version = null,
    c.embedding_text_hash = null;
