# Content-hash-assisted move detection for uid-less vault files

**Status:** COMPLETE — Phase 1 SHIPPED #617, Phase 2 SHIPPED #618 (both 2026-07-12).
The "later layer" the #616 contract deferred (`plans/uidless-vault-entry-identity-upsert.md`).
The rename-identity gap for uid-less vault files is fully closed: pure renames (exact hash)
and rename+edit-in-one-sync (mutual-best similarity, T=0.8, uid-less-UserEntry-gated both
sides) both preserve identity; everything else stays delete+create.

**Two phases, two PRs — the full solution, sequenced by risk:**
- **Phase 1 — exact-hash move detection** (pure renames). Clean, deterministic, low-risk.
  Ships first and stands alone. Branch `feat/hash-assisted-move-detection`.
- **Phase 2 — similarity matching** (rename + edit in one sync). Heuristic; needs threshold
  tuning + false-positive validation, so it ships as its own PR **after** Phase 1 is proven.
  Branch `feat/rename-edit-similarity-matching`. Fully specced below — not a hand-wave.

Together they close the rename-identity gap completely; Phase 1 handles the common case,
Phase 2 handles rename-and-edit-at-once. Do Phase 1 first; only start Phase 2 once Phase 1 is
merged and its pre-pass seam exists to extend.

## Problem

Renaming or moving a **uid-less** vault file (a personal knowledge note with no `uid:`
frontmatter) is currently a **delete + recreate**: the note loses its uid, its
`APPLIES_KNOWLEDGE` grounding edges, any manual links/MOC edges, and its `created_at`.

Why: identity for uid-less files is path-keyed (#616). A rename is a *new path*, so:
- the new path has no tracker row → ingestion mints a **fresh random `ue_` uid**;
- the old path's tracker row points at the old uid, its file is gone → deletion
  reconciliation **deletes the old node** (`delete_rows` in `plan_deletions`).

The two nodes are unrelated, so everything hanging off the old uid is lost. In Obsidian,
renaming notes is routine, so this bites often.

**Authored-uid files are already safe.** A Ku / PathStep carries its uid in frontmatter
(`ku.foo`), so a rename keeps the same uid at the new path; the existing **uid-based** move
detection (`ingestion_tracker.py:438-444` — "same entity_uid still claimed by a collectible
file → only the stale tracking row is removed, entity survives") recognizes it as a move.
This PR closes the remaining hole: **uid-less** files, whose uid is not stable across paths.

## Design — content hash is the identity bridge (composes with #616)

The tracker already stores a SHA-256 `content_hash` per file. A pure rename preserves
content, so **old-path row and new-path file share a content hash.** Use that to detect the
move and rewrite the tracker row's path (old → new, **same uid, same hash**) **before**
ingestion. Then #616 does the rest for free:

1. Move-detection pre-pass rewrites the tracker row: `old_path → uid` becomes `new_path → uid`.
2. Ingestion of `new_path` calls `_resolve_prior_user_entry_uid(new_path)`, finds the rewritten
   row, reuses `uid` → **upserts the same node in place** (path-keyed identity, #616).
3. Deletion reconciliation sees no row for `old_path` → **no deletion**. The node, its uid,
   its grounding edges, and `created_at` all survive; only `updated_at` refreshes.

No new identity machinery — move detection is a thin pre-pass that turns a
delete+create into an update, and the #616 upsert channel carries it.

### Safety: only unambiguous, non-trivial matches

A content hash can collide (two empty notes, duplicated templates). Match **only** when:
- exactly **one** gone-and-would-be-deleted path has hash `H`, **and**
- exactly **one** new (untracked, would-be-ingested) file has hash `H` (a 1:1 pair);
- the content is **non-trivial** (skip empty / whitespace-only files — hash collisions there
  are meaningless). Enforce via a minimum byte length or by excluding the empty-file hash.

Any ambiguity (2+ gone or 2+ new sharing `H`) → **fall back to delete+create** (today's
behavior). Log every applied move (`old → new`, uid) and every ambiguous skip.

### Phase 1 boundary (closed by Phase 2, not accepted)

**Rename + edit in the same sync** changes the content hash → Phase 1's exact match misses it →
delete+create. This is Phase 1's scope boundary, **not a permanent limitation**: **Phase 2**
(below) catches it with similarity matching. Until Phase 2 ships, the interim workaround is
two-step (rename → sync, then edit → sync), which Phase 1 already preserves. Phase 1's PR
description should say "rename+edit-at-once is handled by the Phase 2 follow-up," not "accepted."

## Phase 1 implementation

### 1. Backend: expose `content_hash` on tracked rows
`IngestionBackend.get_tracked_files_under` (`adapters/persistence/neo4j/ingestion_backend.py:210`)
currently returns `{file_path, entity_uid}`. Add `s.content_hash AS content_hash` to the
RETURN. (The property is already written on every row — see `update_ingestion_metadata`.)

### 2. Move-detection pre-pass in the reconciler
New method on `IngestionTracker` (e.g. `detect_and_apply_moves(directory, files_to_process,
pattern, allowlist) -> MovePlan`), called from `batch.ingest_directory` **after** the
file/tracker-row collection and **before** the per-file ingestion loop (so the rewritten rows
are visible to `_resolve_prior_user_entry_uid`). Steps:
- Gather **would-be-deleted** rows: reuse `plan_deletions`' classification (gone + uid not
  reclaimed by a collectible path = `delete_rows`), carrying `content_hash` now.
- Gather **new** files: those in `files_to_process` with **no** tracker row.
- Compute/collect content hashes; build a 1:1 hash → (old_row, new_file) map after dropping
  ambiguous hashes and trivial content.
- For each unambiguous pair: rewrite the tracker row (delete `old_path` row, upsert
  `new_path → uid` with the new file's hash/mtime). Return the applied moves for the sync stats.
- **Only rewrite rows whose entity_uid names a live node** (belt-and-braces, mirrors #616 P1):
  a stale row pointing at a deleted node is not a move source.

### 3. Wire into the sync flow + surface in stats
- `batch.ingest_directory`: call the pre-pass; add `moves_detected` (and the `old → new` list)
  to `VaultSyncStats` / `IncrementalStats` so a rename shows as a move, not a delete + a create.
- Ordering: move-pass → ingest (reuses uid) → tracker stamp → deletion reconciliation. The
  deletion pass must run *after* the move-pass so a moved path is never also a deletion.

### 4. Tests (unit — CI runs tests/unit/ only)
- Uid-less rename (same content) → node uid preserved, grounding edges intact, no delete.
- Rename + edit (hash differs) → falls back to delete+create (this is the Phase 2 case).
- Ambiguous hash (2 gone or 2 new share content) → no move, delete+create, logged.
- Trivial/empty content collision → never matched.
- Authored-uid rename → still handled by the existing uid-based path (regression guard).
- The 1:1 matcher is a pure function → unit-test it against fixture rows directly.

### 5. Docs
`docs/patterns/UNIFIED_INGESTION_GUIDE.md` — the path-keyed-identity section: document that a
uid-less rename is detected via content hash (single-step rename preserves identity;
rename+edit-in-one-sync is preserved once Phase 2 ships — link it).

### 6. Leave the seam for Phase 2
Structure the pre-pass so Phase 2 can extend it without a rewrite: after exact-hash matching,
compute the **residual** — the still-unmatched delete-candidate rows and still-unmatched new
files — and pass both out of the matcher (or leave them clearly available). Phase 2's similarity
pass consumes exactly that residual. Name/shape the matcher so "add a second matching strategy
over the residual" is a drop-in, not surgery.

## Traps (verify in code before editing)
1. **Ordering** — the move-pass MUST run before the ingestion loop *and* before deletion
   reconciliation. If it runs after ingestion, the new path already minted a fresh uid.
2. **Smart mode** — a renamed file is a new path → smart mode flags it "new" (needs ingestion),
   so it IS in `files_to_process`. But an unchanged-content move means the new file's hash
   equals the old row's hash; confirm `files_to_process` is computed before the move-pass so
   the new file is available to match. A `--force` run re-processes everything — the matcher
   must still key on (gone-row, new-file) pairs, not on the "changed" flag.
3. **Mass-reorg** — a large vault reorganization could produce many moves; ensure the pre-pass
   doesn't fight the mass-deletion valve (moves REMOVE rows from the delete set, so they can
   only *reduce* deletions — safe, but verify the valve counts post-move).
4. **content_hash freshness** — the tracker row's hash is the *last-ingested* content. A pure
   rename's on-disk content equals that, so hashes match. Confirm the new file's hash is
   computed from disk at pre-pass time (`tracker.compute_file_hash`), not assumed.
5. **Non-UserEntry uid-less files** — in practice only personal knowledge notes are uid-less;
   Ku/PathStep/LP carry authored uids. The pre-pass is entity-type-agnostic (it rewrites tracker
   rows by path/hash), which is fine — but the primary beneficiary is uid-less UserEntries.

## Phase 1 runtime verification (before closing Phase 1)
1. Create a uid-less knowledge note, sync (grounds to a Ku), note its uid + grounding edge.
2. Rename the file in the vault (no content change), sync → **same uid**, grounding edge
   intact, `moves_detected: 1`, `entities_deleted: 0`, no new node.
3. Rename + edit in one sync → delete+create, `moves_detected: 0` (the Phase 2 case).
4. Rename two identical-content notes at once → no move (ambiguous), both delete+create, logged.
5. `./dev quality` + `./dev smoke` green.

### Phase 1 verification results (2026-07-12 — ALL PASSED, live vault + Docker Neo4j)
1. ✅ Note ingested as `ue_8647f07c` (grounding judge wrote 0 edges for the test content, so
   edge survival was verified via the node's HAS_CONTENT/SHARED_WITH_GROUP/OWNS edges —
   identical mechanism: the node is never deleted, so ALL edges survive).
2. ✅ Pure rename → SAME uid, `created_at` preserved, edges intact, ONE tracker row at the
   new path with hash re-stamped; `moves_detected: 1`, `entities_deleted: 0`, vault-relative
   move line in stats.
3. ✅ Rename+edit in one sync → `moves_detected: 0`, `entities_deleted: 1`, fresh node.
4. ✅ Two identical twins renamed at once → ambiguous log line, `moves_detected: 0`, both
   delete+create.
5. ✅ `./dev quality` all green (incl. MyPy/Pyright); `./dev smoke` green; full
   `tests/unit/` 5796 passed.

## Phase 1 implementation learnings (feed Phase 2)
- **Pending markers on the rewritten row** (not in the original plan): the move-pass writes
  the new-path row with `content_hash=""` / `file_mtime=0.0`, and the normal post-ingest
  stamp overwrites them. If this run's ingest of the new path FAILS, the next sync re-processes
  it instead of hash-skipping a node whose path metadata never updated (a real-hash rewrite
  would have skipped forever — the content genuinely matches). Phase 2 must keep this.
- **Candidate source = the shared valve-free classification** (`_classify_gone_rows`,
  extracted from `plan_deletions` after Codex #617's P1). First cut sourced candidates
  from `plan_deletions().entity_deletions`, but the PHYSICAL-existence valve returned an
  empty plan for a whole-folder rename (all old paths gone = "unmounted vault") — the
  exact scenario the feature exists for, and at N gone of 2N tracked the later
  reconciliation's threshold valve (strict `> 0.5`) does NOT refuse, so the old nodes
  really deleted. Ruling: the mass-deletion valves protect DELETION only and never gate
  MOVE classification — a true unmount produces no new files to match, so the move pass
  is naturally inert there. `plan_deletions` = shared classification + valves on top;
  the move pass consumes the classification directly. `PlannedEntityDeletion` grew
  `content_hash`; the backend's `get_tracked_files_under` now returns it.
- **Live-node guard** needed a new backend method `get_live_entity_uids` (the 3 uid-bearing
  shapes: :Entity/:Group/:Expense) — `get_entity_owner_uids` can't do it (ownerless nodes
  yield no row).
- **New-file detection queries the tracker directly** (`get_ingestion_metadata(files_to_process)`,
  untracked = new) rather than reusing smart-mode "changed" flags — force runs classify
  identically (Trap 2 resolved as planned).
- **Move lines are NOT warnings**: `IncrementalStats.moves_detected`/`moves` →
  `VaultSyncStats` (asdict auto-flows to API/CLI) + a fragment line. Putting them in
  `warnings` would flip `is_clean` and report a clean rename as a problem sync.
- **Phase 2 seam landed as designed**: `move_detection.py` `HashMatchResult.residual_rows`/
  `residual_files` (ambiguous candidates INCLUDED in the residual — mutual-best similarity
  may legitimately resolve what exact-hash calls ambiguous).

---

## Phase 2 — similarity matching for rename + edit (separate follow-up PR)

**Do NOT start until Phase 1 is merged.** Phase 2 extends Phase 1's pre-pass to catch a
rename that also changed content, where the exact hash no longer matches.

### Design — compare against the node's own stored content (no new storage)
The comparison source is already in the graph: a uid-less UserEntry's **last-ingested body is
`Entity.content` on the gone path's node**. So Phase 2 needs no extra fingerprint column — it
reads the gone-candidate nodes' `content` and compares against the new files' on-disk content.
Runs over **only the Phase-1 residual** (unmatched delete-candidates × unmatched new files).

- **Metric:** a cheap, synchronous, CORE-tier-safe **lexical similarity** — token-set or
  line-shingle **Jaccard** (or normalized Levenshtein) over normalized content. NOT embeddings:
  the new file isn't embedded at pre-pass time, and an inline embed call would add API cost,
  latency, and a FULL-tier dependency. (Embedding cosine is a possible *later* refinement, noted
  only.)
- **Matching = mutual best match above a threshold** (git-style, avoids greedy mis-assignment):
  a (gone G, new N) pair is a move iff N's best gone-candidate is G **and** G's best new-file is
  N **and** their similarity ≥ `T`. Everything else stays delete+create. This makes a wrong
  merge require two-way agreement, not a single lucky score.
- **Threshold `T` is the crux — tune empirically, don't guess.** Start conservative (≈0.8),
  validate on real rename+edit samples from Mike's vault history, and measure the
  false-positive rate (unrelated notes merged) vs. false-negative rate (real move missed). A
  false positive silently fuses two notes' identities, so bias HIGH — a missed move (delete+
  create) is the safe failure, a wrong merge is not.
- **Same safety rails as Phase 1:** live-node guard, log every similarity move (`old → new`,
  score) distinctly from exact moves, ambiguity → delete+create.

### Phase 2 tests
- Rename + small edit (≥T similar) → move detected, uid preserved.
- Rename + rewrite (<T similar) → delete+create (correctly NOT merged).
- Two unrelated notes, one deleted + one added, low similarity → never merged (false-positive
  guard).
- Mutual-best-match resolution: G1~N1 and G1~N2 where N1 is the mutual best → only G1↔N1.
- The similarity scorer + bipartite matcher are pure functions → unit-test directly, including
  the threshold boundary.

### Phase 2 runtime verification
- Rename + edit one note in a single sync → `moves_detected` includes it (similarity), uid + a
  fresh grounding pass preserved on the same node; `entities_deleted: 0`.
- A genuinely-replaced file (delete note A, add unrelated note B same sync) → NOT merged.
- Re-run Phase 1's checks (exact moves still work; no regression).

### Phase 2 verification results (2026-07-12 — ALL PASSED, live vault + Docker Neo4j)
1. ✅ Rename + one-sentence edit in ONE sync → similarity move at **0.910**, SAME uid,
   `created_at` preserved, edges intact, content updated; `moves_detected: 1`,
   `entities_deleted: 0`; stats line annotated `(similarity 0.91)`.
2. ✅ Genuinely-replaced file (delete A + add unrelated B, one sync) → NOT merged
   (`moves_detected: 0`, `entities_deleted: 1`, fresh node).
3. ✅ Pure-rename regression → exact-hash move, no similarity annotation, `entities_deleted: 0`.
4. ✅ Sub-threshold rename+edit (+30% tokens on a 64-token note, score 0.765) → safe
   delete+create fallback, exactly as designed (see threshold empirics below).
5. ✅ `./dev quality` all green; `./dev smoke` green; full `tests/unit/` 5816 passed.
   Test notes cleaned from vault AND graph (0 residue).

### Phase 2 implementation learnings
- **T = 0.8 CONFIRMED empirically — do not lower casually.** Measured over all 81 real
  vault notes (≥10 tokens): genuinely-unrelated cross-pairs score ≤ 0.08, but **near-duplicate
  note FAMILIES** (draft copies: `hypermedia2.md` vs `0-Hyper-Media-Systems.md`) reach
  **0.768** — the real false-positive band is duplicates, not unrelated notes. One-sentence
  edits score 0.75–0.81 on short notes (56–80 tokens), ≥ 0.83 on longer ones, median 0.97.
  There is NO clean separation on short notes — any T in [0.75, 0.85] trades duplicate-fusion
  risk against short-note misses; 0.8 sits just above the observed duplicate band, and the
  ruled bias (wrong merge ≫ missed move) settles the trade. A missed short-note rename+edit
  delete+creates — the documented safe failure.
- **Live-node guard for similarity = the content fetch itself**: `get_entity_contents`
  MATCHes live `:Entity` only, so a hand-deleted node yields no comparison content and its
  row can never be a similarity move source — no second `get_live_entity_uids` round-trip.
  :Group/:Expense rows carry no `content` and naturally never similarity-match.
- **Frontmatter TRAP handled as specced**: `_resolve_markdown_comparison_content` mirrors
  `build_user_entry_request` (explicit `content:` wins by KEY PRESENCE — `content: ""`
  suppresses matching entirely — else markdown body); markdown-only (YAML files author uids,
  have no body). Scoring raw file text instead would dilute below T on bulky frontmatter
  (unit-tested premise).
- **Scorer**: word-trigram Jaccard, lowercased, `str.split()` whitespace-normalized (reflow-
  proof); unigram fallback when either side < 3 tokens. Mutual-best with TIE-ABSTENTION:
  a tied top score on either side abstains (logged), never guesses.
- **Exact pass unchanged**: similarity consumes `HashMatchResult`'s residual exactly as the
  P1 seam intended — drop-in, zero surgery on the hash matcher. Shared `_rewrite_move_row`
  keeps P1's rails (pending markers `content_hash=""`/`mtime 0.0`, upsert-new-then-delete-old
  crash ordering) for both strategies; similarity moves log distinctly with score.
- **Codex #618 (P1, real — candidacy must be gated to the uid-less UserEntry world on BOTH
  sides).** Phase 1's "authored-uid rows pass through harmlessly" reasoning relied on exact
  hash ⇒ identical bytes ⇒ same authored uid; similarity breaks that equivalence. Ungated,
  (a) a gone authored/periodic user_entry + a similar uid-less note would FUSE (the #616
  prior-uid gates check only the NEW file, so the rewritten row's authored uid gets reused),
  and (b) a new file that ignores the prior uid (authored `uid:`, periodic, turn-in, or
  `type: Ku` → curriculum pipeline) re-stamps the row while the old row is already deleted →
  gone node ORPHANED, never reconciled. Fix: sources must match the minted shape
  `ue_[0-9a-f]{8}` (provenance-by-spelling — sanctioned; NOT a type sniff), destinations must
  pass `_similarity_candidate_content`'s gates (type resolves to USER_ENTRY, no `uid:`, no
  `fulfills_exercise_uid:`, no periodic `entry_kind`). Exclusion = delete+create, the safe
  failure. Codex #618 P2 (also real): non-mapping YAML frontmatter (a list) aborted the whole
  sync via `AttributeError` on `.get` — now an isinstance gate skips the file.
- **Codex #618 rounds 3–5 (all real, all accepted).** R3: a bare `uid:` (YAML null) DOES
  honor the prior uid (`build_user_entry_request` gates on `is None`, not key presence) —
  the destination gate now mirrors the None-checks exactly (`uid: ""` stays excluded: it
  fails the gate there and mints fresh). R4: `EntityType.from_string` aliases ADR-054-retired
  types (je_input/je_output/exercise_submission) back to USER_ENTRY but the detector REJECTS
  them → gate now calls `detect_entity_type` itself (the detector's own verdict, zero
  duplication). R5: the scorer's unigram fallback let two unrelated notes with body "done"
  score 1.0 and fuse → replaced with ABSTENTION below a 10-token-per-side floor
  (`_MIN_TOKENS`; shortest real vault note measured 20 tokens). Meta-lesson: every gate must
  mirror the REAL ingestion path's behavior (its gates, its detector, its evidence
  requirements), never an approximation of it.
- **Codex #618 round 6 (REJECTED with consideration — the line the gate stops at).** Finding:
  a gated-in file with missing/invalid `pipeline:` fails ingest after the rewrite, so the
  gone node isn't delete+created. Ruling: the gate mirrors ONLY the conditions that change
  which uid a *successful* ingest honors (identity-corruption class); it does NOT try to
  predict ingest success (unbounded, partly DB-dependent, drifts forever). A post-rewrite
  ingest failure is designed-for: pending markers retry + re-report the error EVERY sync
  (never silent); fixing the file ingests with preserved identity (better than delete+
  create); deleting the file leaves the uid unclaimed → reconciliation deletes the node
  normally. Every terminal state correct.

## Workflow (each phase, its own PR)
Branch first → implement → `./dev quality` → commit → PR →
`scripts/request_codex_review.sh <PR#>` → address → `scripts/apply_codex_considered.sh <PR#>`
→ merge (standing authorization). Reflect learnings back into this plan between phases.
