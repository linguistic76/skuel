---
title: Unified Ingestion Implementation Guide
updated: 2026-07-23
category: patterns
related_skills: []
related_docs:
- /docs/decisions/ADR-014-unified-ingestion.md
- /docs/decisions/ADR-054-user-entry-unified-submissions.md
---

# Unified Ingestion Implementation Guide

The "hips" of SKUEL - stability through clarity. Connects content (MD/YAML) to the knowledge graph (Neo4j).

**Decision context:** See [ADR-014](/docs/decisions/ADR-014-unified-ingestion.md) for architectural decisions.

---

## Minimum frontmatter to be ingested

The vault is a mixed authoring space — a file **opts in** to ingestion; anything without the opt-in is a plain note. For a `.md`/`.yaml`/`.yml` file to become a graph entity, its YAML frontmatter (markdown) or YAML body needs:

1. **`type:` — non-empty, an accepted entity type.** One of: `ku`, `ps`, `lp`, `exercise`, `resource`, `user_entry`, `task`, `goal`, `habit`, `event`, `choice`, `principle`, `group`, `lifepath`, `interaction` (aliases like `lesson`/`pathstep`/`learningpath` also resolve — `TYPE_MAPPING` in `core/services/ingestion/detector.py`). No `type:` (or an empty one) → non-entity note, skipped. Two exceptions/rejections: `moc: true` ingests without a type (as a PathStep — see § MOC files), and the retired strings `je_input`/`je_output`/`exercise_submission` (ADR-054) and `expense`/`finance` (ADR-052) are rejected with a pointer, never aliased.
2. **The type's required fields** — see § Entity Configuration for the full table. Most types need only `title`, which auto-falls back to the filename (`name:` is accepted as an alias). Notable extras: `exercise` → `instructions`, `principle` → `statement`, `lifepath` → `user_uid`, `group` → `name`, `interaction` → `interaction_type` + `target_uid`; `user_entry` files additionally need an explicit `pipeline:` (door-level rule, § UserEntry YAMLs).
3. **`uid:` is optional.** Omit it to auto-generate `{prefix}.{filename}`. If declared, it must be non-empty and start with the type's prefix (`ku:`/`ku.` for a Ku, etc. — § UID Format Validation). An empty `uid:` line is never silently replaced with a generated one — the file is ignored with that reason. **`user_entry` differs on both halves** (its branch bypasses the preparer): a declared uid is an opaque join key with no prefix check (ADR-013 never-sniff), and an omitted `uid:` resolves to a derived periodic uid (`ue:daily:{user}:{date}`), the tracker's prior path-keyed uid, or a service-minted random `ue_` uid — never `{prefix}.{filename}` (§ Optional field: `uid`, § Path-keyed identity). A vault sync still ignores a `user_entry` file whose `uid:` line is present but empty (the batch parse stage runs the preparer's guard).

Standalone edge files use `type: edge` + `from`/`to`/`relationship` instead (§ Edge Ingestion).

Files that fall short are **ignored and reported with a per-file reason** on every sync — never treated as sync errors. See § Ignored files vs sync errors.

---

## Default Vault

The default ingestion folder is `/home/mike/0bsidian/0vault/` (the Obsidian vault). This is where Ku YAMLs (`ku_*.yaml`), PathStep YAMLs (`ps_*.yaml`), Exercise YAMLs (`exercise_*.yaml`), edge YAMLs (`edges/edge_*.yaml`), and markdown content files live. Configurable via `INGESTION_PATH` env var.

### Endpoint Path Allowlist (default-deny)

The HTTP ingestion endpoints (`/api/ingest/**`) **do not accept arbitrary host paths**, even from an authenticated admin. `adapters/inbound/ingestion_api.py::_validate_ingestion_path` resolves the request path and rejects it unless it sits under at least one root from `_resolve_allowed_ingestion_roots()`. Precedence chain:

1. `SKUEL_INGESTION_ALLOWED_PATHS` — colon-separated explicit override (multi-vault / staging setups)
2. `INGESTION_PATH` — the single configured vault root (also the documented default)
3. Neither set → **empty list → reject every path** (fail closed)

The admin role gate authorizes *ownership of the action*, not *filesystem reach* — a compromised admin session still can't ingest from `/etc` or `/root`. CLI/programmatic ingestion via `UnifiedIngestionService` bypasses this check (it's HTTP-boundary defense, not a core-service check) — keep ad-hoc paths to scripts you trust.

## Quick Start

```python
from core.services.ingestion import UnifiedIngestionService

service = UnifiedIngestionService(driver)

# Ingest a single file
result = await service.ingest_file(Path("ku.machine-learning.md"))

# Ingest the default vault
stats = await service.ingest_directory(Path("data/vault"), pattern="ku_*.yaml")

# Ingest a directory (full ingestion)
stats = await service.ingest_directory(Path("/docs"), pattern="*.md")

# Incremental ingestion - skip unchanged files (recommended for large vaults)
stats = await service.ingest_directory(
    Path("/docs"),
    ingestion_mode="incremental",      # Skip files with unchanged content hash
    validate_targets=True,        # Validate relationship UIDs exist
)

# Acting-user hint (owner is resolved from the vault descriptor for the path)
result = await service.ingest_file(Path("task_example.yaml"), user_uid=UserUID("user_mike"))

# Ingest an Obsidian vault
stats = await service.ingest_vault(Path("/vault"), subdirs=["docs", "notes"])

# Ingest a bundle with manifest
stats = await service.ingest_bundle(Path("/bundles/mindfulness"))
```

---

## UserEntry YAMLs (`type: user_entry`) — ADR-054

`UserEntry` YAMLs take a dedicated path: `ingest_file()` detects
`type: user_entry` and delegates to
`core/services/ingestion/user_entry_ingestion.py`, which builds a
`UserEntryCreateRequest` and calls `UserEntryService.create_entry()` —
the same method the `/submit` form uses. Both front-ends share the
Interaction audit, TRANSFORMS edge, sharing fan-out, and compensation
delete.

### Required field: `pipeline`

Every UserEntry YAML must declare a pipeline. One of:

- `none` — persisted as-is, no downstream processing.
- `teacher_review` — queued for teacher feedback.
- `llm_summary` — sent to the LLM for a structured summary.
- `extract_activities` — DSL-parsed into real activities (the `/submissions/sync`
  daily-note path, ADR-069). Used by `periodic_notes/`.
- `knowledge` — "developed files": the user's own vault notes in the
  `knowledge/` doorway (or a frontmatter-consented `je_pro/` file — ADR-073
  amendment), shared to teach SKUEL about them. Persisted as-is (no
  processing) and, unlike `reference`, surfaced in the personal-notes context
  digest that informs UserContext. Not counted as a learning-loop submission.
- `reference` — RESERVED for the planned per-user *stored* journal-exemplar
  layer; no producer today. `je_raw/`/`je_pro/` exemplars are read off disk,
  never ingested as REFERENCE (ADR-073 §4).

Audio pipelines (`transcribe`, `transcribe_and_structure`) are not
valid in YAML-ingested UserEntry files.

### Optional field: `audience`

`audience:` declares who sees the submission. Defaults to `teachers`
when omitted. Accepted values:

| Value | Meaning |
|-------|---------|
| `teachers` (default) | Expand to every group the uploader is a student-member of (via `AudienceResolver.resolve_default_teachers`). Zero student-role groups → no shares (no silent broadcast). |
| `group:<group_uid>` | Share with exactly one group. |
| `public` | Set `visibility=PUBLIC` (portfolio). |
| `private` | No shares, no visibility change. |

Legacy aliases `je_input` / `je_output` / `exercise_submission` are
**rejected** with an ADR-054 error (no compat shim — One Path Forward).

### Optional fields: `status`, `description`, `ownership`

The door does not silently drop authored frontmatter it understands:

- **`status:`** — parsed via `EntityStatus.from_string` (case-insensitive,
  alias-aware: `in progress` / `in process` → `active`, `done` →
  `completed`, …). Unrecognized values **fail the file** with the accepted
  list — never silently replaced. Omitted/empty → the pipeline default
  (`submitted` for `teacher_review`, `active` otherwise). Re-syncing an
  edited `status:` updates the node in place (deterministic-uid upsert).
  **`teacher_review` exception:** status is service-owned there (the review
  workflow is the only writer after create) — any authored value other than
  a truthful `submitted` fails the file, so a submission can't be created
  pre-`completed`/`archived` to fake or dodge review.
- **`description:`** — flows onto the node's `description` field.
- **`ownership:`** (alias: `user_uid:`) — a *consistency check*, not a
  transfer: ownership is always stamped from the syncing user. The declared
  value (`linguistic76` or canonical `user_linguistic76`) must match the
  syncing user; a mismatch fails the file honestly instead of the entry
  being claimed by whoever ran the sync. Omitted → no check.

### Optional field: `private` (companion-retrieval opt-out — canon P3)

`private: true` marks a note the journal companion must never draw on:

- The note is **never embedded and never chunked** — no entity vector, no
  `:ContentChunk` subtree exists for it (structural unreachability), and every
  companion-retrieval Cypher additionally carries a hard
  `coalesce(private, false) = false` exclusion (belt and suspenders).
- **Flip semantics:** editing a synced note to `private: true` retracts on the
  next sync — the upsert null-removes the entity embedding and the ingest
  door's unconditional chunk step takes the clear path (deletes the stale
  `:Content`/`:ContentChunk` subtree). Removing the marker restores
  retrievability on the next sync the same way. Retraction depends on the flip
  landing on the **same node**: this holds for authored/periodic uids and, via
  the path-keyed identity above, for uid-less notes too (before that fix a flip
  minted a fresh private node and the old public copy kept its chunks).
  `APPLIES_KNOWLEDGE` grounding edges are deliberately **not** retracted on a
  private flip — `private:` is a companion-*retrieval* opt-out, not an evidence
  opt-out; ZPD grounding is owner-scoped signal about the owner's own learning.
  The retraction surface is chunks (the canon retrieval substrate).
- **Default retrievable:** an absent marker means the (knowledge-pipeline)
  note participates in companion grounding.
- **Scope:** gates companion retrieval ONLY. Orthogonal to `audience`/
  `visibility` (sharing) and `je_use` (ingestion consent); the owner's own
  surfaces (`/gradebook`, `/submissions/knowledge`, search) still show
  private notes.
- Must be a genuine YAML boolean — a quoted `"true"` **fails the file** (an
  authored privacy intent is never silently ignored).

**Backfill campaign:** after a deploy that introduces chunking or changes the
marker's mechanics, run `./dev vault-sync --user <uid> --force` — force
re-processing pushes every knowledge note back through the chunk step (and the
clear path for private ones); the in-process drain embeds the new chunks.

### Optional field: `uid` (deterministic upsert)

By default a UserEntry is minted a random `ue_<...>` UID and **created**
fresh on every ingest. When a deterministic UID is known, the service
switches to **MERGE-on-uid upsert** instead: re-ingesting an edited file
updates the existing node in place rather than duplicating it.
`created_at` is preserved across re-syncs; `updated_at` and content are
refreshed. An exercise-linked file **without** a `uid:` is the turn-in
path (`fulfills_exercise_uid` mints a random UID, fresh node every time);
**with** a deterministic `uid:` it becomes the vault exercise channel's
living entry — see the next section.

**Periodic notes** (`entry_kind: daily | weekly | monthly`) get a
deterministic UID automatically — no explicit `uid:` needed:

| `entry_kind` | auto-derived UID |
|--------------|-----------------|
| `daily` | `ue:daily:{user_uid}:{date}` (e.g. `ue:daily:user_mike:2026-06-28`) |
| `weekly` | `ue:weekly:{user_uid}:{week_of}` |
| `monthly` | `ue:monthly:{user_uid}:{YYYY-MM}` |

This is the same UID the calendar routes use, so vault-synced daily notes
resolve to the correct SKUEL journal page automatically. You may still
supply an explicit `uid:` to override.

An **explicit authored** `uid:` follows the vault convention (colons in the
file, dots in the graph): `uid: moc:worldview` persists as `moc.worldview`.
Any authored prefix is accepted — a UserEntry uid is an opaque deterministic
join key, never type information (ADR-013 never-sniff; the entity kind is
whatever `type:` says). The *derived* periodic UIDs in the table above are
deliberately NOT normalized — their colon form is the calendar routes' join
contract.

### Path-keyed identity for uid-less vault entries

A vault knowledge note with **no** authored `uid:` and no periodic
`entry_kind:` still gets a stable identity — from its **file path**. On first
sync it mints a random `ue_<...>` uid; the ingestion tracker records the
`path → uid` row (the same row that drives deletion propagation). Every later
sync of that path resolves the prior uid and reuses it, routing the note
through the **MERGE-on-uid upsert channel** so an edit updates the node in
place instead of orphaning it. Path *is* identity — the deletion contract and
the update contract now agree.

Resolved once at `UnifiedIngestionService.ingest_file`'s USER_ENTRY branch
(both ingest doors converge there, so the reconciler sync path is covered) and
passed to `build_user_entry_request`, which honors it only when **all** hold:

- no authored/periodic `uid:` (an explicit identity always wins);
- no `fulfills_exercise_uid:` — a turn-in file must keep minting fresh nodes;
  injecting a uid would silently kill the turn-in channel (frozen copy, edge,
  revision, teacher routing);
- an absolute file path — `/upload` callers pass a temp/relative path and must
  keep minting fresh uids.

**Renames preserve identity too (content-based move detection).** A
rename/move of a uid-less note is recognized by the move-detection pre-pass
(`IngestionTracker.detect_and_apply_moves`, run at the start of every tracked
directory sync), two strategies in sequence. **Exact hash** (pure rename): the
gone path's tracker row and the new file share a SHA-256, so the row is
rewritten (old path → new path, SAME uid) and the resolution above reuses the
uid — node, grounding edges, MOC/manual links, and `created_at` all survive;
the sync reports it as `moves_detected`, not a delete + a create. **Lexical
similarity** (rename + edit *in the same sync*): over the exact pass's
residual, the gone node's last-ingested body (`Entity.content`) is compared
against each new markdown file's resolved content (frontmatter `content:`
wins, else the body — the same resolution ingestion applies) with word-shingle
Jaccard; only a MUTUAL best match at or above `SIMILARITY_MOVE_THRESHOLD`
moves, and the sync annotates it with its score. Similarity candidacy is gated
to the uid-less UserEntry world on both sides: sources must carry a minted
`ue_<8hex>` uid, destinations must be `type: user_entry` markdown files with
no authored `uid:`, no periodic `entry_kind`, and no `fulfills_exercise_uid:`
— a file that would not honor the rewritten uid must never be bridged (it
would fuse identities or orphan the gone node).

**Threshold rationale (`SIMILARITY_MOVE_THRESHOLD = 0.8`).** Measured
2026-07-12 by scoring all 81 real vault notes (≥10 tokens) pairwise:
genuinely unrelated notes score ≤ 0.08, but **near-duplicate note families**
(draft copies of one note, e.g. two hypermedia drafts at 0.768) are the real
false-positive band — one deleted + one added in a sync is exactly the shape
a wrong merge takes. Realistic rename+edit lands above: one added sentence
scores 0.75–0.81 on short notes (56–80 tokens), ≥ 0.83 on longer ones,
median 0.97 across the vault. There is no clean separation on short notes —
any T in [0.75, 0.85] trades duplicate fusion against short-note misses —
so 0.8 sits just above the observed duplicate band and the design bias
settles the trade: a wrong merge silently fuses two notes' identities, a
missed move only delete+creates. Two related guards: the scorer abstains
entirely below 10 tokens per side (a tiny body is no identity evidence),
and matching requires MUTUAL best agreement, so one lucky score can't
merge. Re-measure before changing T — the duplicate band is a property of
the vault's authoring habits, not of the algorithm. Only unambiguous matches with
non-trivial content qualify; ambiguity (shared hashes, tied similarity) and
sub-threshold edits fall back to delete+create — a missed move is the safe
failure, a wrong merge is not. Contracts:
`plans/uidless-vault-entry-identity-upsert.md` (#616),
`plans/hash-assisted-move-detection.md` (#617 + Phase 2).

### Vault exercise channel: `uid` + `fulfills_exercise_uid` + `status`

Any exercise, any file: work an exercise in your own vault, sync freely
while in progress, flip one frontmatter line to submit. The channel is
defined by **deterministic `uid:` + `fulfills_exercise_uid:`** on one file
(see `plans/moc-knowledge-channel-design-notes.md` § Phase 0 rulings):

- **Living entry** (`status: in process` or any non-submitted status):
  ONE node, upserted in place every sync. The exercise declaration is
  stored as the `fulfills_exercise_uid` **node property — declared intent**
  ("exercise in progress"), never a `FULFILLS_EXERCISE` edge, no revision,
  no Interaction. Removing the frontmatter line withdraws the intent (the
  property clears on the next sync). Authorization is validated at first
  sync (`query_user_can_use_exercise` — owner, group member, or
  IN_PROGRESS on an anchored PathStep) and fails the file loudly.
- **`status: submitted` + sync = the turn-in signal.** Sync files a
  **frozen copy** through the existing turn-in machinery: fresh random-uid
  node, `FULFILLS_EXERCISE {revision}` edge, Interaction audit record,
  `pipeline: teacher_review` with truthful service-stamped `submitted`,
  audience auto-routing to the exercise's groups. A copy is filed **only
  when content changed since the last copy** — the newest copy IS the
  dedup state (no hash bookkeeping), so idle re-syncs while still marked
  `submitted` are no-ops, and editing while submitted files the next
  revision. Flip back to `in process` to revise in peace. Sync never
  writes into the user's file.
- **The living entry's own status stays `active`** while the file says
  `submitted` — it is not itself in a review queue; the submitted state
  belongs to the frozen copy (#507: TEACHER_REVIEW status is
  service-owned). Consequently `pipeline: teacher_review` + `uid:` +
  `fulfills_exercise_uid:` is rejected: turn-ins are frozen, living files
  author a non-review pipeline (typically `knowledge`).
- **A submitted copy that reaches no teacher/group is an ERROR** in the
  sync results (the copy is compensated/deleted, the living entry stays;
  the file is retried next sync). Every exercise should have a reachable
  reviewer — an unreviewable turn-in is never a silent success.
- **Visibility:** the declared intent surfaces as an **"In Progress"**
  status pill on the exercise lists (`/library/exercises`, profile
  Exercises tab, PathStep detail) with a "View Entry →" link to the living
  entry at `/gradebook/{uid}`; a filed turn-in outranks the intent on the
  pill. A living entry with `moc: true` body links additionally renders
  its ORGANIZES children as a "Map of Content" card section on its
  `/gradebook/{uid}` page.

```yaml
---
type: user_entry
pipeline: knowledge
uid: ue:vault:my-tasks-list        # deterministic — the living entry
fulfills_exercise_uid: ex_list_tasks_abc123
status: in process                 # flip to `submitted` to turn in
---
- Ship the garden bed
- Call the notary
```

### Markdown body → `content`

For a `type: user_entry` **markdown** file, the parsed body (everything
after the frontmatter) becomes `content` when no explicit `content:` field
is present (explicit `content:` wins). This keeps the note prose — and the
`- [ ]` checkbox lines a periodic note carries — available to downstream
processing instead of being discarded.

### Example

```yaml
version: 1.0
type: user_entry
title: Reflection on Meditations chapter 3
pipeline: teacher_review
audience: teachers          # optional; this is the default

content: |
  My takeaways from Marcus Aurelius on impermanence…
tags: [reading, stoicism]

# Optional — link to an exercise this entry fulfills
# fulfills_exercise_uid: ex_marcus-aurelius_abc123
```

### Shared resolver

`AudienceResolver` (`core/services/user_entry/audience_resolver.py`) is
the single implementation of:

1. Pipeline/audience validation (ADR §3 + §5 guardrails — `teacher_review`
   needs a real audience; `transcribe_and_structure` is private by policy).
2. Share fan-out via `UnifiedSharingService` (explicit groups/users +
   auto-share to exercise groups).
3. `resolve_default_teachers(user_uid)` — used by the YAML preparer to
   expand `audience: teachers` into explicit group UIDs.

`UserEntryService` and the ingestion bridge both hold the same resolver
instance; there is no second code path.

---

## MOC files (`moc: true`) — body links → ORGANIZES edges

`moc: true` is a frontmatter field **any** ingestible file can carry — it is
orthogonal to `type:`, pipeline, and vault. Its one effect: after the entity
persists, the file's body links become
`(entity)-[:ORGANIZES {order}]->(target)` edges to each link target that
resolves to an already-ingested entity (order = document position, 0-based).
MOC identity stays **emergent**: the `moc` field flows onto the node as an
inert, human-visible property that nothing queries — a node is a MOC because
it has ORGANIZES edges (the "ORGANIZES Path" to knowledge).

- **Link forms:** wiki-links (`[[target]]`, `|alias`, `#heading`) and
  markdown links (`[label](target.md)`, URL-encoded paths decoded). External
  URLs, image embeds, and non-`.md` attachments are ignored.
- **Resolution:** link target → vault file path suffix →
  `IngestionMetadata` path→uid row, scoped to the vault that governs the MOC
  file. Only file-backed entities resolve.
- **Two postures, one mechanism (ruled 2026-07-04):** in a *personal* vault
  an unresolved link is a **plan**, not an error — skipped silently, filling
  in when the MOC file is next re-ingested after the target lands. The
  *content* vault keeps Arc E strict dangling-target warnings.
- **Re-sync semantics:** editing the MOC re-draws its edges on next sync —
  removed links drop their edges (full refresh, mirroring how rel-config
  `order_property` values refresh); an unchanged file is skipped entirely
  (no-op). File deletion propagates through the normal deletion
  reconciliation (entity + edges). The refresh spares the file's own
  `organizes:` frontmatter targets — the rel-config authoring surface and
  the body-link surface coexist on one file.
- **Batch timing:** the directory door applies MOC passes at the END of a
  sync — after `IngestionMetadata` stamping and deletion reconciliation — so
  a MOC and its targets ingested in the *same* sync link correctly.

Implementation: `core/services/ingestion/moc_links.py` (extraction),
`UnifiedIngestionService._apply_moc_links` (resolution + posture),
`IngestionWriteBackend.resolve_path_suffixes` / `refresh_moc_organizes`
(Cypher).

---

## UX Guide: Using Ingestion Features (2026-02-06)

### Dry-Run Preview

Preview changes before ingesting to Neo4j:

```python
# Preview without writing
result = await service.ingest_directory(
    Path("/docs"),
    dry_run=True  # Preview mode
)

preview = result.value  # DryRunPreview object

# Inspect what would change
print(f"Would create: {len(preview.files_to_create)} files")
print(f"Would update: {len(preview.files_to_update)} files")
print(f"Would skip: {len(preview.files_to_skip)} files")
print(f"Relationships: {len(preview.relationships_to_create)}")
```

**Use Cases:**
- Verify file detection before large ingestion
- Check entity type classification
- Validate relationship targets
- Estimate ingestion impact (nodes/edges)

### Ingestion History & Audit Trail

Track all ingestion operations in Neo4j:

```python
from core.services.ingestion import IngestionHistoryService

history = IngestionHistoryService(driver)

# Create history entry before ingestion
operation_id = await history.create_entry(
    operation_type="directory",
    user_uid="user_admin",
    source_path="/vault/docs"
)

# Perform ingestion
result = await service.ingest_directory(Path("/vault/docs"))

# Update history with results
await history.update_entry(
    operation_id=operation_id,
    status="completed" if result.is_ok else "failed",
    stats=result.value.__dict__,
    errors=result.value.errors if result.is_ok else []
)

# Retrieve history (paginated)
entries = await history.get_history(limit=50, offset=0)
for entry in entries.value:
    print(f"{entry.started_at}: {entry.operation_type} - {entry.status}")
    print(f"  Files: {entry.stats['successful']}/{entry.stats['total_files']}")
```

**Graph Model:**
```cypher
(:IngestionHistory {
  operation_id: "uuid",
  operation_type: "directory",
  started_at: datetime(),
  completed_at: datetime(),
  status: "completed",
  total_files: 1000,
  successful: 995,
  failed: 5
})-[:HAD_ERROR]->(:IngestionError {
  file: "/vault/bad.md",
  error: "Missing title",
  stage: "validation"
})
```

### Domain-Integrated Ingestion (Admin)

Trigger ingestion via the admin panel or API endpoints:

```bash
# Ingest a specific domain (admin only)
POST /api/ingest/domain/ku
```

**See:** `/docs/architecture/CORE_SYSTEMS_ARCHITECTURE.md` for ingestion architecture

### User Data Ingestion

Personal data enters SKUEL via:
- **`/submissions/sync`** — bidirectional Obsidian sync (primary path); daily notes with `pipeline: extract_activities` become Activity entities; task completions round-trip back to the vault. (`/settings/vault` → 301 redirect here; HTMX POST endpoints remain at `/settings/vault/sync` and `/settings/vault/consent`.)
- **`/submissions/exercise`** — exercise worksheet submission (single file, exercise-linked). (`/submit` → 302 redirect here.)

---

## Package Structure

```
core/services/ingestion/
├── __init__.py                    # Public API exports
├── unified_ingestion_service.py   # Orchestration (~370 lines)
├── config.py                      # Entity configs + constants
├── types.py                       # Data classes (Stats, Errors)
├── parser.py                      # MD/YAML parsing
├── detector.py                    # Format/type detection
├── preparer.py                    # Data preparation
├── validator.py                   # Validation pipeline
├── batch.py                       # Concurrent operations
└── ingestion_tracker.py           # Incremental ingestion state
```

**Import (One Path Forward):**
```python
from core.services.ingestion import UnifiedIngestionService
```

---

## Ingestion Modes

The service supports three ingestion strategies for directory and vault operations:

| Mode | Description | Use Case |
|------|-------------|----------|
| `"full"` | Process all files (default) | Initial import, clean slate |
| `"incremental"` | Skip files with unchanged content hash | Regular ingestion after initial import |
| `"smart"` | Use mtime for fast filtering, verify with hash | Large vaults, frequent ingestion |

**`force=True` (orthogonal flag, force ≠ full):** re-process every surviving file
regardless of the hash/mtime match while KEEPING tracked-mode semantics — the
fail-closed allowlist, metadata re-stamping, and deletion reconciliation all stay
active. This is the sanctioned re-chunk/migration path (the ADR-074 PathStep
migration previously required manual `IngestionMetadata` tracker-row invalidation).
A `"full"`-mode request with `force` is coerced to `"smart"`; full mode itself skips
reconciliation and would leak the vault wall. Surfaces: `POST /api/vault/sync/content`
body `{"force": true}` and `./dev vault-sync --force`. Script-mode runs refresh
embeddings in-process (worker subscribe-then-drain, ADR-074 §7);
`scripts/generate_embeddings_batch.py [--stale]` is the backstop for pre-existing drift.

### Incremental Ingestion

Tracks file state in Neo4j to skip unchanged files:

```python
# First ingestion - processes all files, stores ingestion metadata
stats = await service.ingest_directory(Path("/vault"), ingestion_mode="incremental")
# IncrementalStats: total_files=1000, files_ingested=1000, files_skipped=0

# Second ingestion - skips unchanged files
stats = await service.ingest_directory(Path("/vault"), ingestion_mode="incremental")
# IncrementalStats: total_files=1000, files_ingested=5, files_skipped=995, skip_efficiency=99.5%
```

**How it works:**
1. Computes SHA-256 hash of file content
2. Stores hash + mtime in Neo4j `IngestionMetadata` nodes
3. On subsequent ingestion, compares current hash/mtime to stored values
4. Only processes files where content has changed

### IncrementalStats Response

Incremental ingestion returns `IncrementalStats` instead of `IngestionStats`:

```python
@dataclass
class IncrementalStats:
    total_files: int          # Total files found
    files_checked: int        # Files examined for changes
    files_skipped: int        # Unchanged files (skipped)
    files_ingested: int       # Files actually processed
    files_failed: int         # Files with errors
    nodes_created: int
    nodes_updated: int
    relationships_created: int
    duration_seconds: float
    skipped_unchanged: int    # Skipped due to mtime match
    skipped_hash_match: int   # Skipped due to hash match
    errors: list[dict]

    @property
    def skip_efficiency(self) -> float:  # Percentage of files skipped
```

---

## Relationship Creation — Two-Phase, Ordered

Directory ingest is two-phase: ALL node batches (every entity type) land
before ANY relationship batch runs, so references between entities of the
same sync always resolve. Relationship Cypher `MATCH`es targets (never
`MERGE` — no stub nodes); a target missing after phase 1 genuinely doesn't
exist. This matters under incremental sync: an edge dropped on first contact
would never be retried, because the unchanged source file skips forever.

Ordered relationship fields (registry `order_by_property`, e.g. LP
`connections.contains_steps:` → `HAS_STEP.sequence`, `organizes:` →
`ORGANIZES.order`) persist the YAML list index (0-based) onto the edge,
refreshed on every re-ingest — reordering the list in the vault reorders the
graph. See `adapters/persistence/neo4j/bulk_upsert_backend.py`.

## Relationship Validation

Validate that referenced UIDs exist before creating edges. Dangling targets
otherwise no-op silently inside the relationship Cypher (the MATCH miss drops
the UNWIND row), so this pre-check is the only place a phantom UID becomes
visible. Real reconciler syncs (`VaultReconciler.sync` — both vault doors and
`./dev vault-sync`) always pass `validate_targets=True` (Arc E, G10); every
missing (source, target) pair lands in the stats `warnings` list and surfaces
through the sync UI/API.

The pre-check is **payload-aware**: a target that resolves to another entity
being ingested in the *same* sync is valid even though it isn't in the graph
yet. The two-phase ingest persists ALL nodes before ANY relationships (Phase 1
then Phase 2), so same-sync forward references resolve on the single pass — a
wave of new, mutually-referencing entities links completely on one sync with no
warning and no `--force` follow-up. Only targets missing from BOTH the graph and
the sync payload (typos, cross-vault references) warn:

```python
stats = await service.ingest_directory(
    Path("/docs"),
    validate_targets=True,  # Enable validation
)

# stats.warnings — one entry per missing reference:
# "lp.mindfulness-101: relationship target 'ps.phantom-step' does not exist — edge not created"
```

### Direct Validation API

```python
from core.services.ingestion import validate_relationship_targets

result = await validate_relationship_targets(
    entities=[{"uid": "ku.test", "connections.requires": ["ku.prereq"]}],
    relationship_config=ENTITY_CONFIGS[EntityType.CURRICULUM].relationship_config,
    write_backend=write_backend,
    # Optional: same-sync UIDs grouped by the labels each node will carry — a
    # target counts as valid before it lands in the graph only under the label
    # the relationship's target_label (and Phase-2 MATCH) will look for.
    known_uids_by_label={"Ku": {"ku.test", "ku.prereq"}, "Entity": {"ku.test", "ku.prereq"}},
)

if not result.value.valid:
    print(f"Missing UIDs: {result.value.missing_uids}")
    for entity_uid, missing in result.value.missing_by_entity.items():
        print(f"  {entity_uid} references: {missing}")
```

---

## Ownership: descriptor-by-path, not caller identity (ADR-070)

**Access rights are `f(EntityType)`, computed at read time — never materialized on
the node.** Curriculum (Ku/PathStep/LP/Exercise) is SHARED-by-type and receives *no*
owner; USER_OWNED types (the 6 activity domains, UserEntry) carry a `user_uid`.

The one thing ingest must get right uniformly is **who owns a USER_OWNED entity**, and
that is resolved from the **vault descriptor governing the file's path** — not from the
caller. Every `user_uid=` argument on `ingest_file` / `ingest_directory` / `ingest_vault`
is only an **acting-user hint**:

| File lives in… | Owner attributed | Hint |
|----------------|------------------|------|
| Content vault (`INGESTION_PATH`) | `content_owner_uid` ("acts-as" account) | ignored |
| Primary personal vault (`VAULT_ROOT`) | its bound owner (`SKUEL_PERSONAL_VAULT_OWNER`) | ignored |
| A member vault (`{user_vaults_root}/{uid}/`) | `{uid}` — the directory's user | ignored |
| Neither root                     | content acts-as (safe default)          | ignored |

(Personal roots are per-user — ADR-070 Decision 5 amendment 2026-07-05. When a
registry governs, the hint never decides ownership; it only matters as the
fallback in registry-less minimal composes.)

`VaultRegistry.resolve_by_path()` performs the resolution; `UnifiedIngestionService`
applies it at the ingestion **mechanism** — both the per-file `ingest_file` seams *and*
the `ingest_directory` bulk-upsert seam (activity domains are bulk-ingested and never
pass through `ingest_file`). The single-file door also resolves its fail-closed **wall**
from the file's descriptor, so a content `je_*` staging file is rejected consistently
with the directory/reconciler paths. Consequence: **the same file ingested via any
surface — the `/ingest` dashboard, the `VaultReconciler`, or a bare
script — yields the same owner.** The reconciler still passes `user_uid=`/`allowlist=`
explicitly; that is belt-and-suspenders — a by-path caller reproduces the same result.

**Ownership is persisted on BOTH signals, single owner.** Any `:Entity` row the
bulk upsert persists with a `user_uid` property also gets its
`(User)-[:OWNS]->(entity)` edge in the same template (`build_node_upsert_template`
— one chokepoint, both ingest doors), and any :OWNS edge from a DIFFERENT user is
deleted (a former owner must not keep access after re-ingest under a new owner).
This keeps the `user_uid == :OWNS owner` single-owner invariant that OWNS-consuming
read paths (faceted search, `get_user_entities`) depend on. The owner is `MATCH`ed,
not `MERGE`d — an unknown user produces no edge and no stub. Curriculum types never
carry `user_uid`, so they stay edge-free by construction. Ingested exercises are
validated to `scope: curriculum`: shared templates owned by the curriculum itself,
visible to everyone. That is the shared-node model, not a missing owner — a user's
ownership of an exercise materializes on their engagement chain (their `OWNS`ed
UserEntry `-[:FULFILLS_EXERCISE]->` the shared exercise, plus its report/revision
nodes), never as an `:OWNS` edge on the template. One authoritative template per
exercise keeps content-vault edits propagating to every learner; a user who wants a
template of their own creates a fresh PERSONAL exercise via the `/submit`
save-template flow.

**Authored enum casing is canonicalized at the preparer.** `normalize_enum_casing()`
(the enum sibling of `normalize_uid`'s colon→dot rewrite) rewrites values whose only
problem is casing — `learning_level: BEGINNER` is stored as `beginner` — against
`core/models/enum_field_registry.py`, THE field→Enum association registry the DTOs
also slice. Values that are wrong even lowercased fall through untouched for the
validator/DTO boundary to reject. Exact-match property filters (the faceted
`sel_category` facet) therefore never meet non-canonical casing in the graph.

A directory scan attributes one owner + one wall to the whole batch, so it must belong
to a single vault: a scan of an ancestor directory that **nests** another vault's root is
rejected fail-closed (`VaultRegistry.nested_vault_roots`) rather than sweeping and
mis-attributing the nested vault. Sibling / coincident roots do not trip this.

A file **cannot spoof ownership**: under descriptor-governed ingestion the resolved owner
is *authoritative* and overrides any `user_uid:` written into the frontmatter/YAML (so a
personal-vault task claiming `user_uid: someone_else` is still owned by the vault's owner).

**Excluded dirs inside an open vault:** `SyncAllowlist.excluded_dirs` walls specific
subtrees even when the allowlist is whole-vault. The content vault excludes `Resources/`
(the raw reference library — full book texts with no `type:` frontmatter, never
ingestible; without the wall the sweep re-attempted all of it on every sync). This wall
is DELIBERATE and permanent (Arc D ruling 2026-07-03, descriptor-only): `Resource` nodes
ingest from small descriptor `.md` files elsewhere in the content vault (`Res/`,
`type: resource`, UID prefix `resource:`), while the raw texts stay reference-only on
disk. `resource_uids:` on PathStep/Ku YAML creates `CITES_RESOURCE` edges to them.
Full-text book ingestion is a possible later capability with its own design pass — do
not remove the `services_bootstrap/compose.py` exclusion without that ruling.

> Stage-1 boundary (accepted): pointing the dashboard at *another* user's personal vault
> stamps the acting admin as owner — the shared personal descriptor is a template and the
> path alone cannot name the real user. The per-user local-agent topology (ADR-070 north
> star) is the future fix.

## Service Methods

### ingest_file(path)

Ingest a single file (Markdown or YAML).

```python
result = await service.ingest_file(Path("/docs/ku.python-basics.md"))

if result.is_ok:
    entity = result.value
    print(f"Ingested: {entity['uid']}")
else:
    print(f"Error: {result.error.message}")
```

### ingest_directory(path, ...)

Batch ingest all matching files in a directory.

```python
stats = await service.ingest_directory(
    Path("/docs/curriculum"),
    pattern="*.md",              # Or "*.yaml" or "*" for all
    ingestion_mode="incremental",     # Skip unchanged files
    validate_targets=True,       # Validate relationship UIDs exist
)

if stats.is_ok:
    print(f"Ingested: {stats.value.files_ingested}")
    print(f"Skipped: {stats.value.files_skipped}")
    for error in stats.value.errors or []:
        print(f"  - {error['file']}: {error['error']}")
```

### ingest_vault(path, subdirs=None, *, user_uid=None)

Ingest an Obsidian vault. Optionally limit to specific subdirectories.
`user_uid` is an **acting-user hint**, not an owner override: the real owner of
each USER_OWNED entity is resolved from the vault descriptor governing its path
(see [Ownership](#ownership-descriptor-by-path-not-caller-identity-adr-070)). The
API routes pass `current_user.uid`, but for content-vault paths that hint is
ignored in favour of the content acts-as account.

```python
stats = await service.ingest_vault(
    Path("/home/mike/0bsidian/skuel"),
    subdirs=["docs", "curriculum"],  # Optional: limit to these folders
    user_uid=UserUID("user_mike"),   # Optional: override default user
)
```

### ingest_bundle(path)

Ingest a manifest-driven bundle.

```python
# Bundle structure:
# /bundles/mindfulness/
# ├── manifest.yaml          # Lists files to ingest
# ├── ku.breath-awareness.md
# ├── ku.body-scan.md
# └── lp.mindfulness-basics.yaml

stats = await service.ingest_bundle(Path("/bundles/mindfulness"))
```

---

## Configuration

### Default User UID

Configurable via environment variable:

```bash
export SKUEL_DEFAULT_USER_UID="user:admin"
```

Falls back to `"user:system"` if not set.

```python
from core.services.ingestion import DEFAULT_USER_UID
print(DEFAULT_USER_UID)  # "user:admin" or "user:system"
```

---

## Content Formats

### Markdown Files (.md)

Best for text-heavy content like PathSteps. **Requires an explicit `type` field in frontmatter** — markdown files without a `type` field are rejected:

```yaml
# /vault/ps_machine-learning.md
---
type: PathStep
title: Machine Learning
domain: tech
tags: [ml, ai, algorithms]
connections:
  requires:
    - ku.python-basics
    - ku.statistics
  enables:
    - ku.deep-learning
---

Your markdown content here...

## Key Concepts
- Supervised learning
- Unsupervised learning
```

### YAML Files (.yaml, .yml)

Best for structured entities like Tasks, Goals, Events:

```yaml
# /curriculum/task.log-sessions.yaml
type: task
uid: task.log-sessions
title: Log First 5 Sessions
description: Record your meditation sessions
priority: high
status: pending
connections:
  applies_knowledge:
    - ku.meditation-basics
  fulfills_goal:
    - goal.establish-practice
```

---

## Entity Configuration

15 entity configs — 14 of the 25 EntityTypes plus one NonKuDomain type
(GROUP). Configuration in `config.py`. A `name:` field satisfies a
`title` requirement (the preparer renames `name` → `title`); `title`/`name`
also auto-fall back to the filename.

| Entity Type | Prefix | Neo4j Labels | Required Fields | Example File |
|-------------|--------|-------------|-----------------|--------------|
| `exercise` | `ex.` | `:Entity:Exercise` | title, instructions | `exercise_know-yourself.yaml` |
| `ku` | `ku.` | `:Entity:Ku` | title | `ku.python-basics.md` |
| `ps` | `ps.` | `:Entity:PathStep` | title | `ps.learn-variables.md` |
| `lp` | `lp.` | `:Entity:LearningPath` | title | `lp.python-journey.yaml` |
| `resource` | `resource.` | `:Entity:Resource` | title | `resource.atomic-habits.yaml` |
| `task` | `task.` | `:Entity:Task` | title | `task.complete-exercise.yaml` |
| `goal` | `goal.` | `:Entity:Goal` | title | `goal.learn-python.yaml` |
| `habit` | `habit.` | `:Entity:Habit` | title | `habit.daily-practice.yaml` |
| `event` | `event.` | `:Entity:Event` | title | `event.workshop.yaml` |
| `choice` | `choice.` | `:Entity:Choice` | title | `choice.career-path.yaml` |
| `principle` | `principle.` | `:Entity:Principle` | title, statement | `principle.consistency.yaml` |
| `user_entry` | `ue.` | `:Entity:UserEntry` | title (+ `pipeline:`, door-level) | `ue.journal-2026-06-12.yaml` |
| `interaction` | `ia.` | `:Entity:Interaction` | interaction_type, target_uid | `ia.viewed-ps.yaml` |
| `group` | `group.` | `:Group` | name | `group.class-of-2026.yaml` |
| `lifepath` | `lifepath.` | `:Entity:LifePath` | user_uid | `lifepath.vision.yaml` |

**Multi-label architecture:** All domain entities get both `:Entity` (universal base) and a domain-specific label (e.g., `:Task`). This enables cross-domain queries via `:Entity` and fast indexed queries via domain labels. Group is the exception — `:Group` only, no `:Entity` base label (it lives in `NonKuDomain`, ADR-053).

**Retired:** `type: expense` / `type: finance` are rejected by the detector with an ADR pointer — ADR-052 Phase 5 demolished the native expense module (finance is a Firefly III sidecar, not vault-ingestible).

**Indexes:** Domain indexes (UID, user_uid, status, date, composite) are created automatically at bootstrap via `Neo4jSchemaManager.sync_domain_indexes()`. See `scripts/indexes.cypher` for the reference list.

### Entity Type Detection

The service detects entity type from:
1. **Explicit `type` field** in YAML or markdown frontmatter (required — no silent defaults)

**No implicit defaults:** Markdown files without an explicit `type` field are not ingested. YAML files require an explicit `type` field. An empty `type:` line (YAML → `None`) is treated the same as a missing one, with a reason that names the half-finished opt-in; a declared-but-unrecognized type gets its own "unknown type" reason (never reported as "no type field").

### Ignored files vs sync errors (2026-07-23 ruling)

Vault-sync doors (`VaultReconciler` → `VaultSyncStats`) classify per-file ingestion failures by the stage the engine tagged (`IngestionError.stage`):

- **Content-fault stages** (`parsing`, `type_detection`, `validation`, `preparation`) → the file is **ignored** and reported in `VaultSyncStats.ignored` as a vault-relative `path — reason` line (`files_ignored` counts them). These are the file's own frontmatter: no/empty `type:`, empty `uid:`, an invalid enum value, broken YAML. USER_ENTRY pipeline failures classify as content only when a *frontmatter field* failed validation (`classify_user_entry_failure` — fields `pipeline`/`status`/`je_use`/`private`/`audience`/`metadata`); validation errors that encode pipeline state (an unreachable reviewer on a turn-in, a TEACHER_REVIEW request with no resolvable audience) stay errors.
- **Everything else** (`ingestion` = DB write, `edge_ingestion`, `relationships`, `moc_edge_pass`, `file_io`, `user_entry_pipeline`, `unknown`, stage-less reconciliation dicts) → `errors` + `files_failed`. `errors` is **reserved for system faults** (IO, Neo4j, real bugs). Parser-internal IO failures (unreadable/unstat-able file) are re-tagged `file_io` before the `parsing` stage is assigned — an unreadable file is never "ignored".

A sync whose only findings are ignored files **is clean** ("Sync complete" + the ignored list). The reason text keeps two flavors distinct: a file with no `type:` at all (likely a deliberate non-entity note) vs. a file that *declared* a type but has a malformed field — the latter renders as `path — declared 'type: X' but not ingested: reason`, easy to spot for fixing. The default-deny gate is unchanged — nothing is inferred or ingested; only severity and reporting changed.

Ignored files carry no ingestion stamp, so they **re-report on every sync**. That standing visibility is the design (the vault owner always sees what's opted out), not noise.

Classification lives in `_merge_ingest_stats` / `_CONTENT_FAULT_STAGES` (`core/services/vault/vault_reconciler.py`); the raw ingestion API (`/api/ingest/**`) still returns the engine's unclassified `IngestionStats.errors`.

### UID Format Validation

Explicit UIDs in vault files are validated against the expected prefix for their entity type. A `type: PathStep` file with `uid: ku.something` is rejected — the prefix must match (e.g., `ps.` for PathSteps, `ku.` for Kus, `ex.` for Exercises). If no UID is declared, one is auto-generated from the filename with the correct prefix.

---

## UID Format

**Standard:** Dot notation (`entity.name`)

```
ku.breath-awareness      ✅ Correct
task.log-sessions        ✅ Correct
ku:breath-awareness      ❌ Auto-normalized to ku.breath-awareness
```

### Auto-Normalization

The service automatically normalizes:
- Colon notation: `ku:name` → `ku.name`
- Spaces: `ku.my name` → `ku.my-name`
- Case: Preserved (lowercase recommended)

---

## Relationships (Graph-Native)

Define relationships in the `connections` field:

```yaml
connections:
  requires:                    # REQUIRES_KNOWLEDGE relationship
    - ku.python-basics
  enables:                     # ENABLES_KNOWLEDGE relationship
    - ku.advanced-ml
  applies_knowledge:           # APPLIES_KNOWLEDGE relationship
    - ku.statistics
  fulfills_goal:               # FULFILLS_GOAL relationship
    - goal.learn-ml
```

### Available Relationship Types

| Connection Field | Relationship Type | Target Entity | Used By |
|-----------------|-------------------|---------------|---------|
| `requires` | REQUIRES_KNOWLEDGE | Entity | PathStep |
| `enables` | ENABLES_KNOWLEDGE | Entity | PathStep |
| `related` | RELATED_TO | Entity | PathStep |
| `depends_on` | DEPENDS_ON | Task | Task |
| `applies_knowledge` | APPLIES_KNOWLEDGE | Entity | Task, Event |
| `requires_knowledge` | REQUIRES_KNOWLEDGE | Entity | Goal |
| `reinforces_knowledge` | REINFORCES_KNOWLEDGE | Entity | Habit |
| `fulfills_goal` | FULFILLS_GOAL | Goal | Task |
| `reinforces_habit` | SUPPORTS_HABIT | Entity | Task |
| `supports_goal` | SUPPORTS_GOAL | Goal | Habit |
| `embodies_principle` | EMBODIES_PRINCIPLE | Principle | Habit |
| `prerequisite_habits` | REQUIRES_PREREQUISITE_HABIT | Entity | Habit |
| `aligned_with_principle` | GUIDED_BY_PRINCIPLE | Principle | Goal |
| `parent_goal` | SUBGOAL_OF | Goal | Goal |
| `sub_goals` | SUBGOAL_OF (incoming) | Goal | Goal |
| `supporting_habits` | SUPPORTS_GOAL (incoming) | Entity | Goal |
| `informed_by_knowledge` | INFORMED_BY_KNOWLEDGE | Entity | Choice |
| `guided_by_principle` | INFORMED_BY_PRINCIPLE | Principle | Choice |
| `affects_goal` | AFFECTS_GOAL | Goal | Choice |
| `impacts_habit` | IMPACTS_HABIT | Entity | Choice |
| `contributes_to_goal` | CONTRIBUTES_TO_GOAL | Goal | Event |
| `reinforces_habit` | REINFORCES_HABIT | Entity | Event |
| `executes_task` | EXECUTES_TASK | Task | Event |
| `grounded_in_knowledge` | GROUNDED_IN_KNOWLEDGE | Entity | Principle |
| `guides_goal` | GUIDES_GOAL | Goal | Principle |
| `inspires_habit` | INSPIRES_HABIT | Entity | Principle |
| `contains_steps` | HAS_STEP | Entity | LP |
| `organizes` | ORGANIZES | Entity | PathStep |

#### Path Step Fields (12 total)

| YAML Field | Relationship Type | Target | Direction |
|-----------|-------------------|--------|-----------|
| `knowledge_uids` | CONTAINS_KNOWLEDGE | Entity | outgoing |
| `trains_ku_uids` | TRAINS_KU | Ku | outgoing |
| `prerequisite_step_uids` | REQUIRES_STEP | Entity | outgoing |
| `prerequisite_knowledge_uids` | REQUIRES_KNOWLEDGE | Entity | outgoing |
| `principle_uids` | GUIDED_BY_PRINCIPLE | Principle | outgoing |
| `choice_uids` | INFORMS_CHOICE | Entity | outgoing |
| `habit_uids` | BUILDS_HABIT | Entity | outgoing |
| `task_uids` | ASSIGNS_TASK | Task | outgoing |
| `event_template_uids` | SCHEDULES_EVENT | Event | outgoing |
| `learning_path_uids` | HAS_STEP | Entity | incoming |

> **Note:** Single-value fields `learning_path_uid` and `knowledge_uid` are auto-converted
> to their list equivalents (`learning_path_uids`, `knowledge_uids`) during preparation.

> **Note:** Relationship types are unified with the Relationship Registry.
> Ingestion config is derived from the registry via `generate_ingestion_relationship_config()`.
> See `core/services/ingestion/config.py` for the full mapping.

---

## Edge Ingestion (Standalone Relationships)

Edge files declare relationships between existing entities. They create graph edges, not nodes.

```yaml
type: Edge
from: ku:caffeine
to: ku:tinnitus-buzzing
relationship: EXACERBATED_BY
confidence: 0.8
polarity: -1
temporality: hours
source: self_observation
evidence: "Buzzing consistently worse 30-60 min after coffee"
tags: [health, nervous-system]
```

**How it works:**
- `is_edge_type()` detects `type: Edge` before entity type detection
- `validate_edge_data()` validates required fields and value constraints
- `prepare_edge_data()` normalizes UIDs (colon→dot) and extracts evidence properties
- `ingest_edge()` uses `MERGE (a)-[r:REL_TYPE]->(b) SET r += $props` (idempotent)
- In batch mode, edges are processed AFTER entities (so referenced nodes exist)

**Validation rules:**
- Required: `from`, `to`, `relationship` (must be valid `RelationshipName`)
- `confidence`: 0.0–1.0
- `polarity`: -1, 0, or 1
- `temporality`: minutes, hours, days, chronic
- `source`: self_observation, research, teacher, clinical, inferred-approved (app-stamped by the `/admin/prereq-suggestions` approve action)

**Evidence relationship types:** `EXACERBATED_BY`, `REDUCED_BY`, `CORRELATED_WITH`, `CAUSES`, `PRECEDES`

---

## API Endpoints

| Endpoint | Method | Request Body | Response |
|----------|--------|--------------|----------|
| `/api/ingest/file` | POST | `{"file_path": "/path/to/file"}` | Entity dict |
| `/api/ingest/vault` | POST | `{"vault_path": "/vault", "subdirs": ["docs"]}` | IngestionStats (full mode) |
| `/api/ingest/bundle` | POST | `{"bundle_path": "/bundle"}` | BundleStats |
| `/ingest` | GET | - | Dashboard UI |

All endpoints are admin-only and CSRF-protected — a scripted caller needs an authenticated
session plus the `X-CSRF-Token` header.

**Whole-vault incremental sync goes through the reconciler, not a raw ingest door** (ADR-070
Decision 9). The arbitrary-path `/api/ingest/directory` door was removed; ingest the content
vault via `POST /api/vault/sync/content` (admin) or the in-process
`scripts/vault_bridge_sync.py --vault content` (both run `VaultReconciler.sync` in `smart`
mode). Personal vaults sync via `POST /api/vault/sync`.

**Remote vaults ride a staging mirror (ADR-075, `VAULT_TRANSPORT=local_agent`):** when a
personal vault lives on the user's machine, `VaultReconciler.sync` runs a mirror-refresh
pre-phase (`VaultMirrorPuller`, `core/services/vault/mirror_sync.py`) before ingest — it
pulls changed/new allowed files from the user's connected `skuel-vault-agent` into the
member-vault directory (`{SKUEL_USER_VAULTS_ROOT}/{user_uid}/`, which IS the mirror) and
deletes mirror files absent from the agent's listing. Everything below the mirror phase —
smart-mode skip, this deletion propagation, both valves, owner scoping, preview — runs on
the mirror byte-for-byte unchanged; the ingestion engine cannot tell Stage 2 from Stage 1.
`force=True` keeps its meaning: it re-processes unchanged files, never re-fetches
hash-identical content. Preview never dials the agent — it reports the mirror as of the
last refresh.

**Deletion propagation (incremental/smart only):** vault file deleted → graph entity deleted.
After processing, tracked files under the directory that no longer exist on disk have their
entity + content subtree (Content/ContentChunk/ContentMetadata) + IngestionMetadata removed
(`IngestionTracker.reconcile_deletions`). Edge YAMLs propagate too — tracked with the
relationship identity (`edge:{from}|{REL}|{to}`) in the uid slot, so deleting the file deletes
exactly that relationship (and unchanged edge files skip on later runs). Moved/renamed files
lose only the stale tracking row. Reconciliation honors the run's `pattern` — a `*.md`-scoped
run never deletes tracked YAML entities. Two mass-deletion safety valves: the **GLOBAL valve**
refuses when NO tracked file under the directory physically exists (unmounted vault, sync
wipe); the **THRESHOLD valve** — evaluated after every metadata-only path (moved/stale
split, unparseable-edge cleanup) and after owner-scope filtering, so vault reorganizations,
malformed edges, and foreign-owned skips never inflate the ratio and a refusal still leaves
that cleanup done — refuses when at least `MASS_DELETION_MIN_COUNT` (10) entities/edges
would actually be deleted AND they exceed `MASS_DELETION_MAX_FRACTION` (0.5) of all
tracked files (deleting all-but-one file must not wipe the graph in one sync). Refusals
surface as `refusal_warning` → stats `warnings`; escape hatch: delete explicitly via the
ingestion dashboard, or sync in smaller batches. **Owner scope (descriptor-governed syncs):** a tracked
user-owned node whose owner differs from the syncing vault's owner is never deleted —
node and tracking row both survive and the mismatch is surfaced as a warning
(`ownership_mismatches` → stats `warnings`); the owner lookup failing fails the run closed.
The lookup covers every shape the delete removes: `:Entity` `user_uid`, `:Group` `owner_uid`,
`:Expense` `user_uid`.
Ownerless SHARED curriculum and Edge YAMLs (relationships carry no owner) stay path-scoped.
Reconciliation is split plan/execute: `IngestionTracker.plan_deletions` performs the full
classification read-only (it backs the vault sync preview — `VaultReconciler.preview` /
`POST /api/vault/preview`), and `reconcile_deletions` executes the resulting `DeletionPlan`.
Response fields: `entities_deleted`, `edges_deleted`, `stale_metadata_removed`.
User-facing warning/error strings render paths **vault-relative** — the vault root's
absolute host path never reaches stats (`core/utils/path_display.py`, vault security
arc PR 5); full absolute detail stays in logs.

### Example: Human-initiated incremental vault sync

Ingestion is human-initiated per event — there is no background watcher (ADR-070
Decision 9). Sync when you decide to:

```bash
# One-shot content-vault sync (in-process reconciler, smart mode)
./dev vault-sync --vault content

# One-shot personal-vault sync as a given user
./dev vault-sync --user <user_uid>

# Force re-ingest: re-process unchanged files too (re-chunk/migration campaigns);
# the wall and deletion reconciliation stay active. Embeddings refresh in-process
# via the post-sync worker drain (ADR-074 §7).
./dev vault-sync --vault content --force
```

Or from the UI: the personal-vault "Sync from Obsidian" button, or the admin
ingestion dashboard's "Sync content vault" button (`POST /api/vault/sync/content`).

---

## Response Types

### IngestionStats (Full Ingestion)

```python
@dataclass
class IngestionStats:
    total_files: int
    successful: int
    failed: int
    nodes_created: int
    nodes_updated: int
    relationships_created: int
    edges_created: int          # Standalone edge files ingested
    duration_seconds: float
    errors: list[dict] | None
```

### IncrementalStats (Incremental Ingestion)

```python
@dataclass
class IncrementalStats:
    total_files: int
    files_checked: int
    files_skipped: int
    files_ingested: int
    files_failed: int
    nodes_created: int
    nodes_updated: int
    relationships_created: int
    duration_seconds: float
    skipped_unchanged: int
    skipped_hash_match: int
    errors: list[dict] | None

    @property
    def skip_efficiency(self) -> float
```

### RelationshipValidationResult

```python
@dataclass
class RelationshipValidationResult:
    valid: bool
    total_references: int
    valid_references: int
    missing_references: int
    missing_by_entity: dict[str, list[str]]
    missing_uids: set[str]
    warnings: list[str]
```

### ValidationResult

```python
@dataclass
class ValidationResult:
    valid: bool
    file_path: str
    entity_type: str
    uid: str
    title: str | None
    format: str
    warnings: list[str]
    errors: list[str]
    prepared_data: dict | None
    relationship_targets: dict[str, list[str]]
```

---

## Validation

Pre-validate files before ingestion:

```python
from core.services.ingestion import validate_file, validate_directory

# Single file
result = await service.validate_file(Path("/docs/ku.test.md"))
if result.value.valid:
    print(f"Valid: {result.value.entity_type} - {result.value.uid}")
else:
    for error in result.value.errors:
        print(f"Error: {error}")

# Directory
dir_result = await service.validate_directory(Path("/docs"))
print(f"Valid: {dir_result.value.valid_files}")
print(f"Invalid: {dir_result.value.invalid_files}")
```

---

## Direct Module Usage

For advanced use cases, import modules directly:

```python
from core.services.ingestion import (
    # Parsing
    parse_markdown,
    parse_yaml,

    # Detection
    detect_format,
    detect_entity_type,

    # Preparation
    generate_uid,
    normalize_uid,
    prepare_entity_data,

    # Validation
    validate_file,
    validate_entity_data,
    validate_required_fields,
    validate_relationship_targets,

    # Ingestion tracking
    IngestionTracker,
    FileIngestionMetadata,
    IngestionDecision,

    # Configuration
    ENTITY_CONFIGS,
    EntityIngestionConfig,
    DEFAULT_USER_UID,
)

# Example: Check if file needs ingestion
tracker = IngestionTracker(driver)
metadata_map = await tracker.get_ingestion_metadata([Path("/docs/ku.test.md")])
decision = tracker.needs_ingestion(Path("/docs/ku.test.md"), metadata_map.get("/docs/ku.test.md"))
print(f"Needs ingestion: {decision.needs_ingestion} ({decision.reason})")
```

---

## See Also

- **Decision context:** [ADR-014](/docs/decisions/ADR-014-unified-ingestion.md) - Architecture decisions
- **UID format:** [ADR-013](/docs/decisions/ADR-013-ku-uid-flat-identity.md) - Why dot notation
- **Domain architecture:** `/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md`
