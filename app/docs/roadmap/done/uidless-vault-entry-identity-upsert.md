# Path-keyed upsert for uid-less vault UserEntries (+ private-flip retraction + stale cleanup)

**Status:** APPROVED (Mike ratified "path-keyed upsert" 2026-07-12). EXECUTE — this file is the contract.
**Scope:** one PR (door fix + retraction + cleanup script + tests), then post-merge runtime verification + supervised cleanup run.
**Branch:** `fix/uidless-vault-entry-identity`

## Problem (measured 2026-07-12, live graph)

Knowledge notes without `uid:` frontmatter mint a fresh random `ue_` uid on **every**
re-ingest (`UserEntryService.create_entry`, `core/services/user_entry/user_entry_service.py:226`),
while the ingestion tracker's `IngestionMetadata` path→uid row is simply overwritten
(`core/services/ingestion/batch.py:1220–1241`) — the old node is orphaned forever.

Live damage:
- **357** knowledge-pipeline UserEntry nodes; only **81** tracked/live; **276 stale orphans**.
- Stale copies hold **0 chunks** (retrieval is clean today) but carry **660 edges**, including
  **380 of 502 `APPLIES_KNOWLEDGE` grounding edges (76%)** — the ZPD 4th signal counts the same
  note 3–4×. Honest deduped baseline ≈ 122 edges / 37 Kus.
- **Privacy retraction is broken:** flipping a note `private: true` creates a NEW private node;
  the old public copy keeps its chunks and keeps grounding until the next unrelated overwrite.
- Scoping query confirmed blast radius: ALL untracked vault-origin UserEntries are
  `pipeline: knowledge` (276), with **zero** `FULFILLS_EXERCISE` and **zero** incoming
  `EXTRACTED_FROM` edges. Periodic notes are safe (deterministic `ue:daily:...` uids → upsert).

## Design ruling (do not re-litigate)

**Path = identity for uid-less vault files.** This is ALREADY the deletion-propagation contract
(the tracker keys deletions on path). Updates now honor the same contract: at the vault ingest
door, look up the tracker's prior uid for the file path and pass it as `request.uid`, routing the
note through the **existing** MERGE-on-uid living-entry channel
(`user_entry_service.py:286–297`). No vault mutation, no new identity machinery.

Rejected alternatives (recorded, don't revisit): uid-injection write-back into Mike's notes
(invasive, dual-transport write-back); reconciler retirement sweep (symptom-only, retraction
stays broken between sweeps).

Known accepted trade-off: a moved/renamed file = new path = identity loss (delete + recreate) —
identical to today's deletion semantics. Hash-assisted move detection is a possible later layer,
NOT this PR.

## Implementation

### 1. Plumb prior-uid lookup to the UserEntry door

- Caller side: wherever the vault doors invoke the USER_ENTRY branch (trace both: single-file
  `ingest_file` in `core/services/ingestion/unified_ingestion_service.py` AND the batch door in
  `batch.py`; the reconciler sync path must be covered — that's the door that matters), resolve
  `prior = await tracker.get_ingestion_metadata(file_path)`
  (`core/services/ingestion/ingestion_tracker.py:157`) and pass `prior_uid=prior.entity_uid`
  (or None) down to `ingest_user_entry` → `build_user_entry_request`
  (`core/services/ingestion/user_entry_ingestion.py:230`).
- Door side, in `build_user_entry_request`: after the existing `uid_override` derivation
  (`user_entry_ingestion.py:357–389`), add:
  reuse `prior_uid` **only when ALL of**:
  - `uid_override` is still None (authored/periodic uid always wins),
  - `data.get("fulfills_exercise_uid")` is None (**critical** — see Traps),
  - `file_path.is_absolute()` (vault-tracked files only; uploads pass temp paths).
- First sync of a new file: no tracker row → mint random uid exactly as today.

### 2. Private-flip chunk retraction

- The shared chunk step (`_chunk_entity_content` / the ingest_file USER_ENTRY branch that runs
  off the result dict's `pipeline`/`private` flags — see `user_entry_ingestion.py:584–588`)
  currently *skips* chunking for `private: true`. Add the retraction half: when the entry is
  private, **delete any existing chunks** for that uid (find or add a backend primitive; check
  what `store_content_with_chunks` already does for chunk replacement — there is likely a
  delete-then-recreate step to reuse).
- **Ruling to state in the PR description:** `APPLIES_KNOWLEDGE` grounding edges are NOT
  retracted on private-flip. `private:` is a *companion-retrieval opt-out*
  (docstring, `user_entry_ingestion.py:181`), not an evidence opt-out — ZPD grounding is
  owner-scoped signal about the owner's own learning. Entity-level embedding also stays
  (owner-scoped search only). Retraction surface = chunks, because chunks are the canon/vault
  retrieval substrate (`semantic_search_chunks`).

### 3. Cleanup script (one-time migration, dry-run first)

- `scripts/cleanup_untracked_vault_entries.py`, dry-run by default, `--apply` to execute.
- Criterion (verified surgical on live graph):
  `UserEntry` where metadata contains `vault_file_path` AND `uid NOT IN` any
  `IngestionMetadata.entity_uid` AND no outgoing `FULFILLS_EXERCISE` edge (belt-and-braces —
  frozen submission copies never carry `vault_file_path`, see `user_entry_ingestion.py:637–639`).
- Expected: 276 nodes, ~660 edges (380 `APPLIES_KNOWLEDGE`, plus OWNS / SHARED_WITH_GROUP).
  `DETACH DELETE`. Print per-pipeline counts + edge-type breakdown in dry-run.
- Verify how `metadata` is persisted (JSON-string property vs flattened) and match precisely —
  don't ship a `CONTAINS` heuristic if a structured check is possible.

### 4. Tests (unit — CI runs tests/unit/ only)

- Door gating: (a) knowledge note + tracker row → request.uid = prior uid → upsert channel;
  (b) first sync (no row) → random mint; (c) authored `uid:` wins over prior uid;
  (d) `fulfills_exercise_uid` present → NO reuse (turn-in channel untouched);
  (e) non-absolute path (upload) → NO reuse.
- Retraction: private upsert triggers chunk deletion; non-private upsert re-chunks.
- Lesson from #615 P1: mocks hid a body-erasing bug. Unit tests are necessary but NOT
  sufficient — the runtime verification below is part of the arc, not optional.

### 5. Docs

- `docs/patterns/UNIFIED_INGESTION_GUIDE.md` — UserEntry section: document the path-keyed
  identity contract for uid-less vault entries + the private-flip retraction behavior.

## Traps (all verified in code — read before editing)

1. **`user_entry_service.py:222`:** `turn_in_exercise_uid = None if request.uid else
   request.fulfills_exercise_uid` — injecting a uid into a request that has
   `fulfills_exercise_uid` silently kills the turn-in channel (frozen copy, Interaction,
   teacher routing). Hence the hard gate in step 1. Vault exercise-channel files
   (#508/#509) are living entries with authored uids — unaffected, but don't break them.
2. **#615 P1 precedent:** `store_content_with_chunks` has `clear_inline_body` semantics —
   the UserEntry ingest door must keep `preserve_entity_body=True`. A knowledge note's body
   must survive every sync byte-identical.
3. Periodic-note derived uids (`ue:daily:{user}:{date}`) are deliberately NOT normalized
   (colon form is the calendar-routes join contract, `user_entry_ingestion.py:359–365`).
   Don't touch that block.
4. 4 vault files fail ingest on junk `status:` frontmatter (pre-existing, #615 backfill).
   Out of scope — they can't duplicate because they never persist.
5. Tracker rows are also used for edge identities (`EDGE_UID_PREFIX` encoding,
   `ingestion_tracker.py:54–61`) — prior-uid lookup for a .md entity file will never hit one,
   but don't assume every `entity_uid` in the table is a node uid elsewhere.

## Post-merge runtime verification (same arc, before closing)

1. Sync vault twice, no edits → knowledge UE node count stable (no new nodes second run).
2. Edit one knowledge note → SAME uid updated in place; chunks refreshed; embedding event fired
   once (content-hash idempotency on the unchanged ones).
3. Flip a note `private: true` + sync → same node flips private, **chunks deleted**; canon
   `retrieve_vault` probe no longer surfaces it (probe recipe: memory topic
   canon-p3-vault-grounding-arc — `composed.value.journal._canon.retrieve_vault(...)`).
   Flip back → re-chunks.
4. Cleanup: run dry-run, show Mike the counts (expected 276 / ~660 edges), get explicit go
   (destructive-migration stop rule), then `--apply`. Re-run the baseline queries:
   0 untracked vault UEs; `APPLIES_KNOWLEDGE` from knowledge entries ≈ 122 edges / 37 Kus.
5. `./dev quality` + `./dev smoke` green.

## Workflow

Branch first → implement → `./dev quality` → commit → PR → `scripts/request_codex_review.sh <PR#>`
(real verdict required; .py in diff) → address → `scripts/apply_codex_considered.sh <PR#>` →
merge (standing authorization; the ONLY stop is the cleanup `--apply` sign-off above).
