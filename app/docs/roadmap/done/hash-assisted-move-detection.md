# Content-hash move detection for uid-less vault files

**Shipped** 2026-07-12 — Phase 1 exact-hash (#617), Phase 2 similarity (#618). Closes the
rename-identity gap left open by
[uidless-vault-entry-identity-upsert.md](uidless-vault-entry-identity-upsert.md) (#616).
This is the contract `core/services/ingestion/move_detection.py` cites.

## Problem

Identity for uid-less vault files is path-keyed, so a rename is a *new path*: the new path
has no tracker row and mints a fresh random `ue_` uid, while the old path's row is
reconciled as a deletion. The two nodes are unrelated, so the note loses its uid, its
`APPLIES_KNOWLEDGE` grounding edges, its MOC and manual links, and its `created_at`.
Renaming notes is routine in Obsidian, so this bit often.

Authored-uid files were never affected — a Ku or PathStep carries its uid in frontmatter,
so the existing uid-based move detection already recognizes the rename.

## Design — content hash as the identity bridge

The tracker already stores a SHA-256 `content_hash` per file, and a pure rename preserves
content. A pre-pass rewrites the tracker row's path (old → new, same uid) **before**
ingestion, and the path-keyed upsert channel does the rest:

1. The pre-pass rewrites `old_path → uid` into `new_path → uid`.
2. Ingestion of `new_path` resolves the rewritten row and upserts the same node in place.
3. Deletion reconciliation finds no row for `old_path`, so nothing is deleted.

The node, its uid, its edges and its `created_at` all survive; only `updated_at` moves.
Move detection is a thin pre-pass that turns a delete+create into an update.

**Ordering is load-bearing:** move-pass → ingest → tracker stamp → deletion reconciliation.
Run the move-pass after ingestion and the new path has already minted a fresh uid.

## Two strategies over one residual

**Phase 1 — exact hash.** Match only when exactly one gone row and exactly one new file
share hash `H` (a 1:1 pair) and the content is non-trivial. Any ambiguity falls back to
delete+create.

**Phase 2 — lexical similarity**, over Phase 1's residual only. A rename *and* edit in one
sync changes the hash, so the gone node's last-ingested body (`Entity.content`) is compared
against the new file's on-disk content with word-trigram Jaccard. Only a **mutual best
match** at or above the threshold counts: N's best candidate is G *and* G's best is N. A
wrong merge therefore requires two-way agreement rather than one lucky score.

Not embeddings: the new file is not embedded at pre-pass time, and an inline embed call
would add cost, latency and a FULL-tier dependency to a CORE-safe path.

**A missed move is the safe failure; a wrong merge is not** — it silently fuses two notes'
identities. Every rule below biases that way.

## T = 0.8 — confirmed empirically, do not lower casually

Measured over all 81 real vault notes of ≥10 tokens:

| Population | Score |
|---|---|
| Genuinely unrelated cross-pairs | ≤ 0.08 |
| **Near-duplicate note families** (draft copies) | **up to 0.768** |
| One-sentence edits, short notes (56–80 tokens) | 0.75–0.81 |
| One-sentence edits, longer notes | ≥ 0.83 (median 0.97) |

The real false-positive band is **duplicates, not unrelated notes**. There is no clean
separation on short notes: any T in [0.75, 0.85] trades duplicate-fusion risk against
short-note misses. 0.8 sits just above the observed duplicate band, and the ruled bias
settles the trade — a missed short-note rename+edit delete+creates, the documented safe
failure.

## Candidacy gates — both sides

Phase 1's "authored-uid rows pass through harmlessly" reasoning relied on exact hash ⇒
identical bytes ⇒ same authored uid. **Similarity breaks that equivalence**, so both sides
are gated to the uid-less UserEntry world:

- **Sources** must match the minted shape `ue_[0-9a-f]{8}` — provenance-by-spelling, which
  is sanctioned here; NOT a type sniff.
- **Destinations** must pass `_similarity_candidate_content`'s gates: type resolves to
  USER_ENTRY, no `uid:`, no `fulfills_exercise_uid:`, no periodic `entry_kind`.

Ungated, a gone authored or periodic entry plus a similar uid-less note would **fuse** (the
prior-uid gates check only the new file, so the rewritten row's authored uid gets reused);
and a new file that ignores the prior uid would re-stamp the row after the old row was
already deleted, **orphaning** the gone node permanently. Exclusion means delete+create —
the safe failure.

**Every gate must mirror the real ingestion path's behavior** — its gates, its detector,
its evidence requirements — never an approximation of it:

- A bare `uid:` (YAML null) DOES honor the prior uid, because the door gates on `is None`,
  not key presence. The destination gate mirrors those None-checks exactly. (`uid: ""`
  stays excluded — it fails the gate there and mints fresh.)
- `EntityType.from_string` aliases the ADR-054-retired types back to USER_ENTRY, but the
  detector rejects them, so the gate calls `detect_entity_type` itself rather than
  duplicating its logic.

### Where the gate deliberately stops

The gate mirrors **only** the conditions that change which uid a *successful* ingest
honors — the identity-corruption class. It does **not** try to predict whether ingest will
succeed: that is unbounded, partly database-dependent, and drifts forever.

A post-rewrite ingest failure is designed for. Pending markers retry and re-report the
error every sync (never silent); fixing the file ingests with identity preserved; deleting
the file leaves the uid unclaimed, so reconciliation deletes the node normally. Every
terminal state is correct.

## Rulings worth keeping

- **Mass-deletion valves protect DELETION only and never gate MOVE classification.** The
  first cut sourced candidates from `plan_deletions().entity_deletions`, but the
  physical-existence valve returned an empty plan for a whole-folder rename — precisely the
  scenario the feature exists for. `plan_deletions` is shared classification with valves on
  top; the move pass consumes the classification directly. A true unmount produces no new
  files to match, so the move pass is naturally inert there.
- **Pending markers on the rewritten row.** The move-pass writes the new-path row with
  `content_hash=""` and `file_mtime=0.0`, and the normal post-ingest stamp overwrites them.
  If this run's ingest fails, the next sync re-processes it instead of hash-skipping
  forever — a real-hash rewrite would skip permanently, because the content genuinely
  matches.
- **Move lines are not warnings.** They flow to `VaultSyncStats` as `moves_detected` /
  `moves`. Putting them in `warnings` would flip `is_clean` and report a clean rename as a
  problem sync.
- **Scoring uses resolved content, not raw file text.** `_similarity_candidate_content`
  (`core/services/ingestion/ingestion_tracker.py`) is one function doing both jobs: it
  gates the candidate *and* returns the comparison content, resolved the way ingestion
  resolves it — an explicit frontmatter `content:` wins by key presence rather than
  truthiness, otherwise the markdown body. The gone node's stored `content` is the
  *resolved* body, so scoring raw file text would dilute the score with frontmatter noise.
  Unparseable or oversized files, non-mapping frontmatter, and empty resolved content all
  return `None` — not a candidate.
- **Abstention beats guessing.** Word-trigram Jaccard, lowercased and whitespace-normalized
  (reflow-proof). A tied top score on either side abstains and logs. Below a ten-token
  floor (`_MIN_TOKENS`) it abstains entirely — an earlier unigram fallback let two
  unrelated notes whose body was "done" score 1.0 and fuse. The shortest real vault note
  measured 20 tokens.

## Traps

1. **Ordering** — before the ingestion loop *and* before deletion reconciliation.
2. **Force runs** — new-file detection queries the tracker directly (untracked = new)
   rather than reusing smart-mode "changed" flags, so `--force` classifies identically.
3. **Mass reorg** — moves remove rows from the delete set, so they can only reduce
   deletions. Safe, but verify the valve counts post-move.
4. **Hash freshness** — the tracker row's hash is the *last-ingested* content, so the new
   file's hash must be computed from disk at pre-pass time, not assumed.

**Related:** `docs/patterns/UNIFIED_INGESTION_GUIDE.md` § path-keyed identity.
