---
title: "ADR-070: Bidirectional VaultBridge — Obsidian ↔ SKUEL Task Sync"
updated: 2026-08-25
status: accepted
category: decisions
tags: [adr, decisions, vault, obsidian, bidirectional-sync, vault-bridge]
related: [ADR-014, ADR-044, ADR-054, ADR-069]
related_skills: []
---

# ADR-070: Bidirectional VaultBridge — Obsidian ↔ SKUEL Task Sync

**Status:** Accepted — implemented in PR-3 (#319)

> **Status annotation (2026-08-24, cascade-residue PR-D):** implementation is **outbound-only for
> task state** — the INBOUND half of Model D (vault `[x]`/`[ ]` edits propagating to the SKUEL
> task) was never built. Decision 2's `[x]` and `✅` rows say "bidirectional" and Decision 3's LWW
> policy resolves conflicts for it: both describe design intent with no mechanism behind them — no
> status-reconciliation branch exists beside the extraction guards, which `continue` past an
> already-extracted line unconditionally (Decision 1's 2026-08-23 amendment, Guard 2b, makes that
> skip *deliberate* for any 🆔 line whose hash moved). Resolved Design Questions § 2's claim that
> inbound reopen "works for free" is false for the same reason. Ruled 2026-08-23 (cascade-residue
> disposition, #1139–#1143): docs corrected to the outbound truth; the build is parked with
> trigger + design sketch in `docs/roadmap/deferred-work.md` § "R4 Vault Inbound Propagation —
> Parked Build".
>
> **Amended 2026-08-24 (reopen-vault-surface arc):** the OUTBOUND half is now complete in both
> directions of task state — a reopen un-checks the line and strips the `✅` date (Resolved
> Design Question 2, amended below). That does not soften the annotation above: inbound is still
> unbuilt, so "bidirectional" in Decision 2's `[x]`/`✅` rows remains design intent for the
> vault→SKUEL direction alone.

**Date:** 2026-06-16

**Decision Type:** ⬜ Pattern/Practice  ⬜ Infrastructure  ✅ Architecture

**Related ADRs:**
- Extends: ADR-069 (EXTRACT_ACTIVITIES pipeline — one-way ingest)
- Depends on: ADR-044 (hexagonal boundary), ADR-054 (UserEntry), ADR-014 (ingestion one-way design)
- Context: PR-1 ✅ (#315), PR-2 ✅ (#316) — one-way PoC bricks already merged

---

## Context

Mike authors periodic notes (daily/weekly/monthly/yearly) in Obsidian using the
**obsidian-tasks plugin** checkbox syntax. PR-1 + PR-2 established one-way ingest:
periodic note → `UserEntry`, `- [ ]` lines → `Task` entities via `EXTRACT_ACTIVITIES`.

The intended final state is **full bidirectional** ("Model D"):

- Mark a task done in Obsidian OR in SKUEL → both reflect it.
- Notes are **living documents** (not write-once); tasks re-sync as notes evolve.
- SKUEL holds history/lineage/relationships the flat `.md` can never hold.
- The user triggers sync via an **"Update from my vault" button** in SKUEL — no background watcher.

This requires resolving five hard sub-problems, each with real prior-art implications:

1. **Durable line identity** — which mechanism survives edits?
2. **What fields belong to whom** — when Obsidian and SKUEL both know a task, who is canonical for which fields?
3. **Conflict resolution** — same field changed in both since last sync: what wins?
4. **Safe outbound writes** — how does SKUEL write `[x]`, `✅ date`, and `🆔 id` into a live `.md` file without corrupting prose or frontmatter?
5. **Secure local-agent transport** — today local filesystem; tomorrow the vault is on a user's private device; can the same sync logic survive both without a rewrite?

Deep research (112 agents, 29 sources, 18 verified findings, 2026-06-16) ground-truths the decisions below.

---

## Decision

### Decision 1 — Durable Join Key: obsidian-tasks `🆔` block IDs

**The `🆔 <id>` field in the obsidian-tasks emoji format is the durable line↔task join key.**

Evidence: three primary sources confirm `🆔` stores an `id` field (e.g. `- [ ] do this first 🆔 dcf64c`). The plugin's own docs state "Task id values are intended to be unique across the whole vault." The field is the only mechanism in the ecosystem that survives edits, moves, and re-syncs.

**Content-hash (PR-2's current mechanism) is NOT the durable join key.** It is sufficient for first-ingestion dedup (no ID → no match → create), but fails as soon as the user edits the task title or due date. The `source_line_hash` field on `EXTRACTED_FROM` edges is retained as a change-detection signal, not an identity key.

**ID minting is SKUEL's responsibility.** GitHub issue #3347 (obsidian-tasks, closed "not planned", Feb 2025) confirms the plugin will never auto-generate IDs for all new tasks — only for tasks created via the dependency UI. On first recognition of a task line without a `🆔` token, SKUEL's VaultWriter **injects the ID into the file** as an atomic write.

**ID format:** 6-character base-36 alphanumeric (`[a-z0-9]{6}`), matching the plugin's documented examples (`dcf64c`). This gives ~2.18 billion combinations — sufficient for vault-wide uniqueness. IDs are stored on the `EXTRACTED_FROM` edge as `vault_id`.

**Implementation consequence:** `EXTRACTED_FROM {vault_id, extracted_at, source_line_hash}` — `vault_id` is the stable join key; `source_line_hash` detects whether the line changed since last sync.

> **Amendment (2026-08-23, cascade-residue PR-C):** the 🆔 is now read as identity at *ingest* too. Extraction Guard 2 (`source_line_hash` dedup) gained an identity form — Guard 2b: a line whose 🆔 already carries an `EXTRACTED_FROM` edge to the entry is already extracted, whatever its hash says. Without it, SKUEL's own outbound write-back (`[x]` + `✅ date`) moved the line's hash, Guard 2 missed on the next sync, Guard 4 (ACTIVE twins only, by design) could not catch a just-completed task, and the primary personal-data path re-created every task it marked done (reproduced end-to-end in `tests/integration/test_vault_done_date_hash_roundtrip.py`). The digest itself is unchanged — the `✅` date stays inside it deliberately, as the only discriminator between two same-title completed occurrences in one note — so no stored hash moved and the agent protocol did not change.

---

### Decision 2 — Field Authority Table

Lossless round-trip between graph and markdown is **impossible**. Logseq DB confirmed this (their own docs: "Export as standard Markdown cannot capture all data in a graph"). SKUEL's bidirectional sync requires an explicit per-field canonical-authority policy.

| Field | Canonical authority | Sync direction | Notes |
|-------|--------------------|--------------|-|
| Task title / description | Markdown | vault→SKUEL | User edits title in Obsidian |
| Checkbox status done (`[x]`) | **Both** (merge) | bidirectional | Core round-trip: done in either → both done |
| Checkbox status undone (`[ ]`) | **SKUEL, for its own writes** | SKUEL→vault | Amended 2026-08-24: re-opening in SKUEL un-checks the line and strips the `✅` date it wrote. Gated on a TRAILING `✅` token, so a dateless `[x]` the USER ticked, and a `✅ date` inside their own task text, are both left alone. The vault→SKUEL direction was never built (see the status annotation) |
| Due date (📅) | Markdown | vault→SKUEL | User sets in Obsidian |
| Scheduled date (⏳) | Markdown | vault→SKUEL | User sets in Obsidian |
| Start date (🛫) | Markdown | vault→SKUEL | User sets in Obsidian |
| Done date (✅ YYYY-MM-DD) | **Both** (merge) | bidirectional | Written by whichever side marks done first |
| Priority (🔺⏫🔼🔽⏬) | Markdown | vault→SKUEL | User sets in Obsidian |
| `#hashtag` tags | Markdown | vault→SKUEL | Becomes `Task.tags` |
| `🆔` ID token | SKUEL (mints) | SKUEL→vault | Written on first sync |
| `entity_uid` | SKUEL | SKUEL only | Never in markdown |
| `OWNS` / `EXTRACTED_FROM` edges | SKUEL | SKUEL only | Graph-native relationships |
| Interaction history | SKUEL | SKUEL only | Log, not synced back |
| ZPD scores | SKUEL | SKUEL only | Computed, not stored in vault |
| `created_at` (graph) | SKUEL | SKUEL only | PR-1 upsert preserves it |
| `period:{kind}` tag | SKUEL | SKUEL only | Derived from `entry_kind`, not in Obsidian |
| Recurrence (🔁) | Markdown | vault→SKUEL (read-only) | SKUEL reads; does not write recurrence back |
| Dependencies (⛔) | Markdown | vault→SKUEL (read-only) | SKUEL reads; does not write back |

---

### Decision 3 — Conflict Resolution Policy

**Cross-field concurrent edits: field-level merge (always safe).** If Obsidian changed the title and SKUEL changed the status, both changes are accepted — no conflict.

**Same-field concurrent edits: LWW by timestamp.**

For **checkbox status** (the primary round-trip case):
- The `✅ YYYY-MM-DD` done-date IS the timestamp.
- SKUEL stores `completion_date` on the Task — stamped on every transition into
  COMPLETED (completion-stamping arc, 2026-08-22) — or parses it from the `✅` token on
  the DSL `[x]` create door. Outbound writes derive the `✅` from that field, never from
  the mutable `updated_at`.
- On sync: the side with the **later** completion timestamp wins.
- Practical reality: concurrent completion (both sides check it off within the same sync window) has identical semantic intent — either "winning" value is correct. LWW is sufficient.

For **title/description** (both sides edited):
- The current sync is user-triggered; the user just pushed "Update from my vault."
- SKUEL applies vault-wins for markdown-authoritative fields. The user's most recent Obsidian authoring is the intent.
- SKUEL records the previous title in graph history (via `updated_at`) — the graph IS the audit trail.

**No CRDT library required.** Ink & Switch's Peritext paper (CSCW 2022) explicitly defers block-level structured-record CRDTs — no production-grade library handles this as of 2026. Automerge handles same-property conflicts via actor-ID-ordered LWW exposed in `getConflicts()` — identical to the policy above but without the library dependency. For SKUEL's use case (atomic task-line records, one dominant merge scenario), application-level field-merge + LWW-by-timestamp is complete and correct.

---

### Decision 4 — Safe In-Place Markdown Editing (VaultWriter)

**Pattern: read → mutate lines → write to temp → `os.rename()`.**

POSIX `rename()` is atomic on local filesystems — the target is either fully replaced or untouched. No partial write is ever visible to Obsidian. This is the canonical safe-write pattern (python-atomicwrites, POSIX standard).

Three outbound write operations the VaultWriter performs:
1. **Status round-trip**: toggle `- [ ]` → `- [x]` AND append `✅ YYYY-MM-DD` as the LAST token on the line. (Trailing is load-bearing, not cosmetic: operation 3 reverses this write by that trailing marker, so a completion that failed to leave one — as it did when its own idempotency tests matched a `✅ date` anywhere, e.g. inside the task's own text — flipped a checkbox nothing could flip back. Amended 2026-08-24.) (Critical: the plugin only appends the done-date when IT toggles; an external raw `[x]` write does NOT trigger the plugin's date-append. SKUEL must write the `✅` itself.)
2. **ID injection**: append `🆔 <id>` to a task line that has no ID token. Idempotent: skip if `🆔` already present.
3. **Undone round-trip** (built 2026-08-24, amending Resolved Design Question 2): strip `[x]` → `[ ]` and strip the `✅ YYYY-MM-DD` token. Byte-exact reverse of operation 1 — the separating space operation 1 wrote in front of `✅` goes with the token, so a complete → reopen round-trip restores the line's original bytes. Driven by STATE, not by the `TaskReopened` event: the outbound pass queues it when a task is not `completed` and its line still carries the `✅` token, which is idempotent and re-evaluable on any sync. ⚠️ **A TRAILING `✅ date` is the trigger — not the checkbox, and not a token anywhere on the line.** Operation 1 always appends one at the END and — since 2026-08-24 — **keys its own two `✅` tests on the trailing marker too**, so it never changes a checkbox without leaving the marker that reverses it. That is what makes the two directions compose: SKUEL never authors a dateless `[x]` (one on a 🆔 line is the user's own Obsidian check, which does not reach SKUEL — Guard 2b), and a `✅ date` inside the task's own text is the user's prose (*"Compare ✅ 2025-01-01 vs now"*), never SKUEL's. Both wider readings destroy user-authored state: matching the checkbox reverts the user's own check, matching a token anywhere deletes words out of the description — and, on the completion side, suppresses the marker and leaves the `[x]` stuck forever. The un-check takes back only what SKUEL wrote.

**Change detection guard (stale-read prevention):**
Before writing, re-read the file and compute SHA-256. If it differs from the `vault_sync_hash` stored on the `UserEntry` Neo4j node (the hash at last successful sync), the file changed concurrently — abort the write and queue for re-sync. This handles Syncthing/iCloud delivery racing the write window. Hash is updated in the same Neo4j write as the task status update.

**Per-root sync serialization (added 2026-07-05, vault security arc PR 5):**
`VaultReconciler.sync` holds a lazily created `asyncio.Lock` keyed by the resolved vault root around the whole effectful body (consent gate + ingest + outbound). Two concurrent syncs of the SAME root serialize — the second waits, it never errors; distinct roots never block each other. The SHA-256 stale-read guard above remains the per-file defense against out-of-process writers; the lock removes in-process sync interleaving.

**`python-frontmatter`** library for YAML frontmatter-aware reads — preserves frontmatter structure during body mutation.

**NFS / network drives:** `rename()` atomicity is NOT guaranteed on NFS. If a user's vault is on a network drive, writes may appear partial to Obsidian. Document as unsupported; recommend local-disk vault.

---

### Decision 5 — VaultBridge as a Hexagonal Port

**All identity, change-detection, reconciliation, and conflict logic lives in `core/` behind a `VaultBridgePort` protocol.** The transport (filesystem vs. secure local-agent) is an interchangeable adapter.

```
core/ports/vault_bridge_protocol.py       ← VaultBridgePort protocol (pure interface)
core/services/vault/vault_reconciler.py   ← identity / merge / conflict (transport-agnostic)
adapters/vault/filesystem_adapter.py      ← Stage 1: direct file I/O (local Docker)
adapters/vault/local_agent_adapter.py     ← Stage 2+: secure agent channel (cloud)
```

The `VaultBridgePort` exposes:
- `read_note(user_uid, path) → NoteSnapshot`
- `write_task_updates(user_uid, path, updates, expected_sha256) → WriteResult`
- `list_changed_since(user_uid, since_hash) → list[ChangedNote]`

**Per-user from day one.** The port takes `user_uid` on every call — even though today only one user exists (Mike), the abstraction is multi-tenant. No global `INGESTION_PATH` is threaded through the port.

**Per-user personal ROOTS (amendment 2026-07-05).** "Per-user" originally stopped at the port signature: `VaultRegistry` held ONE personal template whose root every authenticated user resolved to (stamped with their own `owner_uid`), so in a multi-user deployment user B's sync would have ingested — and, after granting their own consent flag, written into — user A's vault directory. Resolution is now per-user end to end:

- The **primary** personal vault (`VAULT_ROOT`) is bound to one account at compose time (`SKUEL_PERSONAL_VAULT_OWNER`, defaulting to the `SKUEL_DEFAULT_USER_UID` chain; the `user_system` terminal default binds it to nobody). Its descriptor carries that real owner — the `SYSTEM_USER_UID` resolve-time stamping placeholder is gone.
- Every **other** user resolves to their own member vault at `{SKUEL_USER_VAULTS_ROOT}/{user_uid}/`, built on demand by a compose-injected `PersonalDescriptorFactory` (per-root fail-closed allowlist + root-bound bridge — the registry stays adapter-free, SKUEL022). A user with no member directory gets `Result.fail` — no code path serves one user another user's vault.
- `resolve_by_path` attributes personal paths to the vault's **bound** owner (primary root → its owner; `user_vaults/{uid}/…` → `{uid}`), making by-path ownership truly caller-independent. The nested-root guards treat member vaults as real vault roots (a scan of the user-vaults umbrella conflicts), and the reconciler's surface-independence guard refuses a sync whose by-kind and by-path owners disagree (e.g. a member family misplaced inside the primary root).

**ADR-044 compliance.** The port lives in `core/ports/` (SKUEL022-clean). The adapters live in `adapters/vault/` (below the hexagonal boundary). No raw filesystem calls in `core/`.

---

### Decision 6 — Security Model (North-Star; NOT implemented in Stage 1)

**Local-agent trust boundary:** the local agent holds the only filesystem handle to the user's vault. The cloud app pushes/pulls only scoped delta changes through an encrypted channel. The vault path is never transmitted to the server.

**Syncthing relay model** is the strongest prior art: TLS session established inside the relay's plaintext connection — relay sees connection metadata (peer IDs) but cannot decrypt payload. Apply the same principle: local agent encrypts vault deltas before transmission; cloud stores and routes ciphertext only.

**Authentication:** per-device keypair enrolled once (similar to Syncthing device IDs), short-lived session token per sync operation. Revocation path needed before cloud deployment.

**Stage 1 (today, local Docker):** `filesystem_adapter.py` — direct file access, same machine, no encryption layer needed. All identity/reconciliation/conflict logic is identical.

**Stage 2+ (cloud deployment):** swap `filesystem_adapter.py` for `local_agent_adapter.py` with the encrypted outbound-only channel. Zero changes to `core/`. This is the "drop-in, not a rewrite" guarantee.

### Decision 7 — Access rights are the single axis; ingest owner is descriptor-by-path (2026-07-01)

The content vault and a personal vault do **not** differ in sync *nature* — the sync mechanism is uniform (files → `ingest_directory` → Neo4j). The only real difference is **access rights**, which SKUEL already derives from `EntityType` (Content Origin Tiers): curriculum is SHARED (no ownership check), activities/UserEntry are USER_OWNED (404 on non-owner). So both vaults ride **one descriptor-driven `VaultReconciler`** spine.

**Access rights stay `f(EntityType)`, computed at read time — never materialized on the node.** No `visibility`/owner is written onto SHARED curriculum; there is no schema change. The one thing ingest must get right uniformly is the **owner of USER_OWNED entities**, and it is resolved from the **vault descriptor governing the file's path** (`VaultRegistry.resolve_by_path`) at the ingestion **mechanism** — so no ingest surface (dashboard, reconciler, `vault_watch`, script) can substitute its own identity. Every `user_uid=` argument is reinterpreted as an *acting-user hint*, overridden by the descriptor for content-vault paths. `content_owner_uid` shrinks to "the account the content vault *acts as*."

Applied at **both** ingestion seams: the per-file `ingest_file` path *and* the `ingest_directory` bulk-upsert path (activity domains are bulk-ingested and never traverse `ingest_file`).

**Explicitly out of scope (documented invariant):** chunking/embedding. It is triggered by `entity_type == PathStep` *inside* `ingest_file` (a curriculum concern), decoupled via `ChunkEmbeddingRequested` → worker (FULL tier). The ownership refactor does not touch it.

**See:** `docs/patterns/UNIFIED_INGESTION_GUIDE.md` (Ownership section), `core/services/vault/vault_descriptor.py`.

---

### Decision 8 — The sync allowlist is code-defined; operator-configurability is deferred to a per-user mechanism, never a global knob (2026-07-01)

PR #482 (Decision 7) removed the `SKUEL_VAULT_SYNC_ALLOWED_DIRS` env read from `build_sync_allowlist`. It was reading a **privacy wall** (which folders of a personal vault may be ingested) from the ambient process environment, **deep in the call stack**. Because `main.py` loads `.env` with `load_dotenv()` (default `override=False`, [verified empirically](#verification)), a stale *exported shell* var silently shadowed `.env` and walled off `knowledge/` while `.env` said otherwise. The fix made the code-level doorway defaults (`_DEFAULT_SYNC_SUBDIRS`: `periodic_notes/`, `personal_notes/`, `activity_notes/`, `knowledge/`) the single source of truth.

Both Codex and Kody flagged that operators who relied on the env var now have it silently ignored. **We deliberately keep it removed (code-defined only), for two reasons that compound:**

1. **Re-wiring via `os.getenv` is unsound at *any* layer** — compose root included. `override=False` means an exported shell var still wins over `.env`, reintroducing the exact shadow bug. (This is *not* unique to the allowlist — `VAULT_ROOT`/`INGESTION_PATH`/`SKUEL_CONTENT_VAULT_OWNER` are equally shadowable. We tolerate it there because those fail **loud**; the allowlist was uniquely dangerous because it is a privacy wall that fails **silent**.)
2. **There is no current need, and the future need has a different shape.** SKUEL is single-tenant today; the doorway folders are a deliberate ADR-073 design, a one-line `_DEFAULT_SYNC_SUBDIRS` edit if they ever change. Operator-configurability is **downstream of the hosting / multi-tenancy milestone** (ADR-073 §Consequences "multi-tenant allowlist" residual, R2, is hosting-gated). When it is needed it must be **per-user** — the personal vault *is* per-user (ADR-070 north star = per-user local agent). A global env var or a global config file is therefore **dominated: unneeded now, wrong shape later.**

**One Path Forward is preserved:** no second competing config source is introduced. `build_sync_allowlist(governed_root, *, allowed_dirs=..., content_root=...)` still accepts an explicit `allowed_dirs` (colon-separated, strictly-under-root validated, `":"` = wall-everything); compose simply never passes it. That parameter is the single seam — fed by code today, fed by a **per-user source** when hosting arrives.

**When the need is real, the mechanism is a vault-local marker file** (e.g. `.skuel-sync-allowed` at the personal vault root) read once and passed to `build_sync_allowlist(..., allowed_dirs=...)`. It is the only candidate that is per-user *without* moving allowlist resolution from compose-time to resolve-time, cannot be shadowed by shell env (read by path), reuses the existing strictly-under-root guard, and is owned/discoverable by the person whose privacy it governs. Graph-native per-user settings (UI-managed) remain the eventual north star but require resolve-time allowlist construction — a deliberate later step, not this decision.

**Rejected:** (a) `os.getenv` at compose (Kody's suggestion) — reintroduces the shadow; (b) a global app-level config file — shadow-proof but wrong shape (global, not per-user).

Fail-closed posture is unchanged: unset → doorway folders only; a newly-created folder stays silent until explicitly opted in; the `je_*` `STAGING_EXCLUDED_DIRS` floor applies unconditionally, beneath and independent of the allowlist.

<a name="verification"></a>**Verification (2026-07-01):** with a `.env` setting `X=from_dotenv` and an exported shell `X=from_shell`, `load_dotenv()` (override=False, as `main.py`) resolves `X=from_shell` — the shell shadows `.env`. `load_dotenv(override=True)` resolves `from_dotenv`. Confirms both that the original bug is real and that no `os.getenv`-based restore is sound while `main.py` loads with `override=False`.

**See:** `core/services/ingestion/config.py` (`build_sync_allowlist`, `_DEFAULT_SYNC_SUBDIRS`, `STAGING_EXCLUDED_DIRS`), `services_bootstrap/compose.py` (allowlist wiring), ADR-073 §Consequences (R2 multi-tenant allowlist residual).

---

### Decision 9 — Ingestion is human-initiated per event; one reconciler engine; the continuous watcher is deleted (2026-07-01)

`docs/Reviews/SYNC_UNIFICATION_REVIEW.md` (a *One Path Forward* pass over #482) surfaced two consolidation debts. PR 1's commit message promised PR 2 would *retire* `/api/ingest/directory` and `scripts/vault_watch.py`; PR 2 kept both working and removed only the admin button. The result: a parallel directory-ingest door (**A1**) and three sync triggers spanning two engines — the raw `/api/ingest/*` door vs. the `VaultReconciler` (**A2**). This decision resolves both. It also **enforces Alternative E** below, which rejected the continuous watcher in prose on 2026-06-16 while the code kept `vault_watch.py` alive as a live trigger — the exact intent-vs-reality drift the review caught.

**Ruling 1 — one engine (resolves A1).** The raw arbitrary-path `POST /api/ingest/directory` door is **deleted**. The single directory-ingest path is the `VaultReconciler`, reachable over HTTP as `POST /api/vault/sync` (PERSONAL, session user) and `POST /api/vault/sync/content` (CONTENT, admin, inbound-only); the admin dashboard's former "Ingest Directory" card becomes a **"Sync content vault"** button onto the latter. Arbitrary-path / glob admin ingest is retired with it — a pre-vault-era capability Mike confirmed (2026-07-01) is not needed, since the vault is the ingestion source of truth. PR 1's "to be retired" language is honoured, not deferred.

**Ruling 2 — human-initiated *per event* (resolves A2).** Ingestion happens exactly when a person asks for it. Sanctioned entry points, all explicit and all onto the one reconciler engine:
1. the "Update from my vault" button → `POST /api/vault/sync`;
2. single-file sync (the same route, single-path variant);
3. a one-shot, human-run `scripts/vault_bridge_sync.py` (in-process reconciler).

**No unattended scheduler of any kind.** The continuous poll-loop is deleted, and cron / systemd-timer ingestion is out of scope. Mike's rationale: *a continuous watcher adds no value when the machinery is human-started anyway; per-event initiation is the cleaner, more honest system — you sync because you decided to.*

**Why per-event, not merely "machinery human-started."** The looser reading (launching a daemon is itself the explicit act, so a background watcher is fine) was considered and rejected: it re-imports the property we are removing — a scheduled `--once` is a continuous watcher wearing a cron hat, "not human per event" via a timer instead of a poll-loop. Sanctioning it would reopen the same drift this decision closes.

**Enforcement (done in this PR):** deleted `scripts/vault_watch.py` (the continuous poll-loop) and `scripts/provision_vault_watcher.py` (the watcher's HTTP service-account provisioner — obsolete once sync is in-process); deleted `POST /api/ingest/directory` and its route-level test; added `POST /api/vault/sync/content` (admin) onto the reconciler; rewired the ingestion dashboard's directory card to a "Sync content vault" button; replaced `./dev vault-watch` with one-shot `./dev vault-sync` (→ `vault_bridge_sync.py`); updated the CLAUDE.md ingestion note.

**Rejected:** (a) cron / systemd `--once` as sanctioned automation — violates per-event-human initiation; it is Alternative E by another name. (b) keeping `/api/ingest/directory` as a parallel raw ingest door — One Path Forward forbids two live paths to one outcome.

**Unchanged:** this decision governs *triggers and engine count only*. Descriptor-by-path ingest ownership (Decision 7) and the code-defined default-deny sync allowlist (Decision 8) are untouched; the fail-closed privacy wall still applies beneath every entry point above.

**See:** `docs/Reviews/SYNC_UNIFICATION_REVIEW.md` (A1, A2), Alternative E (below), Decision 7, `scripts/vault_bridge_sync.py`, `adapters/inbound/vault_routes.py` (`POST /api/vault/sync`, `POST /api/vault/sync/content`), `core/services/vault/vault_reconciler.py` (`sync`).

---

## Resolved Design Questions (2026-06-16)

**1. Trigger scope:** Support BOTH — sync all changed notes (full vault incremental) AND sync a single note (single-file path). The API supports both from day one; the UX design (button placement, picker, confirmation) is deferred to a dedicated UX pass. Prior art: the existing ingestion system already distinguishes `ingest_file` (single) vs `ingest_directory` (vault-wide incremental) — the VaultBridge inherits the same duality.

**2. Undone round-trip (SKUEL→Obsidian `- [ ]` write):** Originally **OUT OF SCOPE for v1** — *"re-opening a completed task is not a current workflow and re-introducing it does not justify the complexity."* The deferral rested on three claims, and it was **AMENDED 2026-08-24** because two of them turned out to be false:
- ~~The INBOUND direction (Obsidian edit `- [ ]` → SKUEL re-opens task) works for free~~ — **false, and it is what made the deferral unsafe.** No status-reconciliation branch was ever built beside the extraction guards, and Guard 2b deliberately skips any already-🆔'd line (see the status annotation at the top of this ADR). So the vault could not correct itself either: a task re-opened in SKUEL kept its `- [x] … ✅ date` line indefinitely, with a ✅ date recording a completion that had been withdrawn.
- ~~It is only a UX gap, not an architectural inconsistency~~ — a stale `✅ date` in the user's own files is a **wrong record**, not a missing feature. The vault is the source of truth for personal data (ADR-070's own premise); SKUEL writing a completion into it and then never withdrawing it is the app falsifying that record.
- The complexity claim held, and was paid down first: the un-check inherits `WriteResult.updates_applied` (protocol v2), so it reports its own per-update outcome instead of hiding a miss inside a file-level success.

**The amendment (Mike, 2026-08-24), stated as built:** a reopen DOES un-check its vault line and strip the `✅` date — **but only the lines SKUEL itself completed.** A **trailing** `✅ date` token is the discriminator, not the checkbox: the done write always appends one at the end, so a dateless `[x]` on a 🆔 line is definitionally the user's own Obsidian check — and because it appends at the END, a `✅ date` inside the task's own text was never SKUEL's either. The done write keys on the same trailing predicate, so every checkbox SKUEL changes carries the marker that reverses it. Since a vault-side check does not reach SKUEL (Guard 2b, inbound parked), reverting it would silently erase a deliberate edit SKUEL cannot even read, on the sync right after they made it. So the operation is the narrow, defensible claim — *a withdrawn completion must not leave SKUEL's own completion token behind* — not a claim of ownership over the checkbox. A dateless `[x]` stays, diverging visibly, which is the pre-existing state § R4 exists to close. The trigger is the outbound pass's **state predicate** — "this task is not `completed` AND its line is still marked done" — not the `TaskReopened` event, which stays published and deliberately unsubscribed. `is_reopen` is only knowable after the guarded write returns the prior status (ADR-087), so the graph write has already committed before any consumer could run and a failed vault write would have **no retry**: re-issuing writes nothing, because the prior is no longer `completed`. A one-shot transition needs a state predicate, not an event. The field-authority table row for undone moves from "deferred" to SKUEL-authoritative.

⚠️ **This is outbound-only and must not be read as bidirectional.** A vault-side check or un-check of a 🆔 line still does NOT reach SKUEL; that half is parked with a design sketch in `docs/roadmap/deferred-work.md` § "R4 Vault Inbound Propagation — Parked Build".

**3. Hash database location:** Neo4j. Stored as `vault_sync_hash` on the `UserEntry` node — no extra state file alongside the vault.

**4. ID injection consent:** **First-run notice.** Before SKUEL ever writes to the vault (first "Update from my vault" invocation per user), surface a one-time confirmation that explains SKUEL will inject `🆔` IDs into task lines. User must acknowledge once; subsequent syncs proceed silently. Gate stored as a user preference flag.

**Amendment (2026-07-05, vault security review):** consent now gates the ENTIRE first sync — read (inbound ingest of the allowed doorway folders) AND write — not just outbound. Previously the first sync ingested the whole allowed vault tree before asking; `VaultReconciler.sync` now checks `vault_write_consent` before the first `ingest_directory` call and returns `first_run_notice` without reading anything. The content vault (admin, inbound-only) stays consent-free.

**Amendment (2026-07-05, vault security arc PR 7):** the dry-run preview (`VaultReconciler.preview`, "Preview sync" on `/submissions/sync`) shares the same consent gate — preview hashes/compares vault files, which is a read, so a not-yet-consented user gets `first_run_notice` (the consent form), never a preview.

---

## Alternatives Considered

### Alternative A — Content hash as join key (PR-2 current)
**Rejected.** Fails on any edit to the task line (title change, date change, tag edit). The normalized checkbox hash (`- [ ]` canonical) handles the check/uncheck case but not general edits. Not viable as a durable identity mechanism.

### Alternative B — Line number as join key
**Rejected.** Fails on any insertion above the target line. Fragile by construction.

### Alternative C — Obsidian block references (`^block-id`)
**Not chosen for task lines.** Obsidian block refs (`^id`) work on ANY block (paragraphs, headings, list items). They're independent of the obsidian-tasks plugin and appear at the END of the line after a space. However, obsidian-tasks 🆔 IDs are the canonical identity for task-specific round-tripping (the plugin reads and writes them); using block refs would require maintaining a parallel ID scheme. 🆔 is the right choice for tasks; block refs remain available for non-task line references.

### Alternative D — Full CRDT (Automerge/Yjs)
**Rejected for now.** Ink & Switch's Peritext (CSCW 2022) explicitly defers block-level structured-record CRDTs — no production library solves the "task line as structured record" problem at the character level. Automerge handles same-property conflicts via actor-ID LWW, which is identical to the chosen field-merge + LWW policy without the library dependency. May be revisited if SKUEL expands to collaborative editing across multiple users on the same vault.

### Alternative E — Continuous background watcher (the former `vault_watch.py`)
**Explicitly rejected by Mike** (2026-06-16), **deleted in code by Decision 9** (2026-07-01; `vault_watch.py` is gone). User-triggered sync is the correct UX. The watcher also used `POST /api/ingest/directory` → `batch.ingest_directory`, which bypassed `UserEntryService` entirely (no OWNS edge, no extraction, no processor) — architecturally the wrong path for periodic notes regardless of the UX choice. Decision 9 extends this rejection to *all* unattended scheduling (cron / systemd `--once`) and removed the watcher rather than leaving it live.

---

## Consequences

### Positive
- ✅ Both surfaces (Obsidian and SKUEL) are first-class — no "primary" editor.
- ✅ SKUEL is the history/lineage/graph authority; Obsidian is the authoring surface.
- ✅ VaultBridge port makes Stage 1 → Stage 2 transport swap a single-adapter replacement.
- ✅ Per-user from day one — every SKUEL user gets a private vault bridge, not just Mike.
- ✅ LWW-by-timestamp conflict policy is complete, correct, and operationally simple.
- ✅ Atomic rename() prevents corrupt notes even on process kill during write.

### Negative
- ⚠️ SKUEL now writes to the user's vault — this is a new class of action (ADR-014's "ingestion one-way" is superseded for the VaultWriter adapter specifically).
- ⚠️ ID injection modifies vault files silently on first sync. Must be communicated to users.
- ⚠️ NFS/network-drive vaults are not supported for the atomic-write guarantee.
- ⚠️ The local-agent security model (Stage 2) is NOT implemented now — Stage 1 is local-only; cloud deployment cannot proceed without completing Stage 2.

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| User edits file while sync write is in progress | Low (user-triggered, short window) | Medium (stale write) | SHA-256 stale-read guard — abort + re-queue |
| Duplicate `🆔` IDs (SKUEL mints same ID as plugin) | Low (different minting moments) | Medium (wrong task matched) | SKUEL mints from a `sk_` namespace prefix: `🆔 sk_<6chars>` to avoid collision space overlap |
| Plugin adds new emoji field in future version | Low | Medium (parse miss) | PR-2's obsidian adapter is the single parse boundary; update in one place |
| obsidian-tasks changes `🆔` semantics | Very low (stable since Tasks 6.1) | High | Pin a minimum Tasks plugin version in docs; monitor GitHub releases |

---

## Implementation Stages

**Stage 1 — Local filesystem VaultBridge (current target):**
- `VaultBridgePort` protocol + `FilesystemVaultAdapter`
- `VaultReconciler` — field-merge + LWW logic
- `VaultWriter` — atomic rename(), ID injection, status round-trip
- "Update from my vault" button → `POST /api/vault/sync` → reconciler
- Route the `user_entry` path out of `batch.ingest_directory` through `UserEntryService` (fixes the directory-routing gap discovered in PR-3 verification)
- Fix FULL-tier double-extraction (dsl_bridge must skip checkbox lines)

**Stage 2 — Local-agent transport (cloud deployment prerequisite):**
- `LocalAgentVaultAdapter` — encrypted outbound-only channel
- Per-device keypair enrollment + short-lived session tokens
- Relay-pattern: cloud routes ciphertext; never holds filesystem access
- **Concrete protocol + implementation spec: ADR-075 (2026-07-05)** — resolves the relay-vs-counterparty topology tension in Decision 6 and plans the B2/B3/B4 build.

**Not in scope for either stage:**
- Recurrence expansion in SKUEL (read `🔁`; create instances in Obsidian is the plugin's job)
- Dependency graph (⛔) write-back to vault (read-only import)
- Historical notes: periodic notes older than `INGESTION_PATH` scan start (treated as new on first sync)

---

## Documentation

### Related Documentation
- ADR-014: Ingestion one-way design (superseded by VaultWriter for vault sync only)
- ADR-044: Hexagonal boundary (VaultBridgePort lives in `core/ports/`)
- ADR-054: UserEntry unified pipeline
- ADR-069: EXTRACT_ACTIVITIES pipeline (one-way foundation)
- `docs/patterns/UNIFIED_INGESTION_GUIDE.md` (update when VaultWriter lands)

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2026-06-16 | Claude Code | Initial draft from deep research (112 agents, 29 sources) | 0.1 |
| 2026-06-16 | Mike | Resolved 4 design questions: trigger scope (both), undone (deferred v1), hash→Neo4j, ID injection→first-run notice | 0.2 |
| 2026-07-01 | Claude Code | Decision 7 — access rights as the single axis; ingest owner resolved descriptor-by-path at the mechanism (surface-independent); chunk/embed documented out of scope | 0.3 |
| 2026-07-01 | Claude Code | Decision 8 — sync allowlist stays code-defined; operator-configurability deferred to a per-user vault-local marker (hosting-gated); global env/file rejected (shadow + wrong shape). Closes PR #482 open question. | 0.4 |
| 2026-07-01 | Mike + Claude Code | Decision 9 — ingestion is human-initiated per event (1a); raw `/api/ingest/directory` deleted, content-vault sync unified onto the reconciler via new admin `POST /api/vault/sync/content` (resolves review A1); continuous watcher + provisioner deleted, all unattended scheduling out of scope, enforcing Alternative E (resolves review A2). | 0.5 |
| 2026-08-24 | Mike + Claude Code | **Resolved Design Question 2 AMENDED** — the undone round-trip is BUILT: a reopen un-checks its vault line and strips the `✅` date, byte-exact reverse of the done write, gated on a TRAILING `✅` token so it only ever takes back SKUEL's OWN write (a dateless `[x]` the user ticked, and a `✅ date` in their own task text, are both left alone). Two of the deferral's three premises were false (inbound does not "work for free"; a stale `✅` date is a wrong record, not a UX gap). Driven by the outbound pass's state predicate, not by `TaskReopened` (which stays published and deliberately unsubscribed). Field-authority row for undone moves to SKUEL. Wire-protocol change: `PROTOCOL_VERSION` 2 → 3. ⚠️ Outbound only — inbound propagation stays parked (deferred-work § R4). | 0.6 |
