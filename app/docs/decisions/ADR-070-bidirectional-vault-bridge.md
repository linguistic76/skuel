---
title: "ADR-070: Bidirectional VaultBridge — Obsidian ↔ SKUEL Task Sync"
updated: 2026-06-16
status: accepted
category: decisions
tags: [adr, decisions, vault, obsidian, bidirectional-sync, vault-bridge]
related: [ADR-014, ADR-044, ADR-054, ADR-069]
related_skills: []
---

# ADR-070: Bidirectional VaultBridge — Obsidian ↔ SKUEL Task Sync

**Status:** Accepted — implemented in PR-3 (#319)

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

---

### Decision 2 — Field Authority Table

Lossless round-trip between graph and markdown is **impossible**. Logseq DB confirmed this (their own docs: "Export as standard Markdown cannot capture all data in a graph"). SKUEL's bidirectional sync requires an explicit per-field canonical-authority policy.

| Field | Canonical authority | Sync direction | Notes |
|-------|--------------------|--------------|-|
| Task title / description | Markdown | vault→SKUEL | User edits title in Obsidian |
| Checkbox status done (`[x]`) | **Both** (merge) | bidirectional | Core round-trip: done in either → both done |
| Checkbox status undone (`[ ]`) | Markdown | vault→SKUEL only | SKUEL→vault undone write deferred (v1 out of scope) |
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
- SKUEL stores `completed_at` on the Task (or infers from the `✅` token).
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
1. **Status round-trip**: toggle `- [ ]` → `- [x]` AND append `✅ YYYY-MM-DD` inline on the same line. (Critical: the plugin only appends the done-date when IT toggles; an external raw `[x]` write does NOT trigger the plugin's date-append. SKUEL must write the `✅` itself.)
2. **ID injection**: append `🆔 <id>` to a task line that has no ID token. Idempotent: skip if `🆔` already present.
3. **Undone round-trip** (future): strip `[x]` → `[ ]` and strip `✅ YYYY-MM-DD` token.

**Change detection guard (stale-read prevention):**
Before writing, re-read the file and compute SHA-256. If it differs from the `vault_sync_hash` stored on the `UserEntry` Neo4j node (the hash at last successful sync), the file changed concurrently — abort the write and queue for re-sync. This handles Syncthing/iCloud delivery racing the write window. Hash is updated in the same Neo4j write as the task status update.

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
- `write_task_update(user_uid, path, vault_id, update) → WriteResult`
- `list_changed_since(user_uid, since_hash) → list[ChangedNote]`

**Per-user from day one.** The port takes `user_uid` on every call — even though today only one user exists (Mike), the abstraction is multi-tenant. No global `INGESTION_PATH` is threaded through the port.

**ADR-044 compliance.** The port lives in `core/ports/` (SKUEL022-clean). The adapters live in `adapters/vault/` (below the hexagonal boundary). No raw filesystem calls in `core/`.

---

### Decision 6 — Security Model (North-Star; NOT implemented in Stage 1)

**Local-agent trust boundary:** the local agent holds the only filesystem handle to the user's vault. The cloud app pushes/pulls only scoped delta changes through an encrypted channel. The vault path is never transmitted to the server.

**Syncthing relay model** is the strongest prior art: TLS session established inside the relay's plaintext connection — relay sees connection metadata (peer IDs) but cannot decrypt payload. Apply the same principle: local agent encrypts vault deltas before transmission; cloud stores and routes ciphertext only.

**Authentication:** per-device keypair enrolled once (similar to Syncthing device IDs), short-lived session token per sync operation. Revocation path needed before cloud deployment.

**Stage 1 (today, local Docker):** `filesystem_adapter.py` — direct file access, same machine, no encryption layer needed. All identity/reconciliation/conflict logic is identical.

**Stage 2+ (cloud deployment):** swap `filesystem_adapter.py` for `local_agent_adapter.py` with the encrypted outbound-only channel. Zero changes to `core/`. This is the "drop-in, not a rewrite" guarantee.

---

## Resolved Design Questions (2026-06-16)

**1. Trigger scope:** Support BOTH — sync all changed notes (full vault incremental) AND sync a single note (single-file path). The API supports both from day one; the UX design (button placement, picker, confirmation) is deferred to a dedicated UX pass. Prior art: the existing ingestion system already distinguishes `ingest_file` (single) vs `ingest_directory` (vault-wide incremental) — the VaultBridge inherits the same duality.

**2. Undone round-trip (SKUEL→Obsidian `- [ ]` write):** Explicitly **OUT OF SCOPE for v1.** Re-opening a completed task is not a current workflow and re-introducing it does not justify the complexity. Deferral is safe because:
- The INBOUND direction (Obsidian edit `- [ ]` → SKUEL re-opens task) works for free — vault wins on checkbox in the field-authority table, so if a user manually unchecks in Obsidian, the next sync picks it up.
- The OUTBOUND direction (SKUEL marks not-done → writes `- [ ]` to vault) is the deferred capability; it does not create an architectural inconsistency, only a UX gap.
- The field-authority table reflects this: checkbox status is "Both (merge)" for done, "deferred" for undone.

**3. Hash database location:** Neo4j. Stored as `vault_sync_hash` on the `UserEntry` node — no extra state file alongside the vault.

**4. ID injection consent:** **First-run notice.** Before SKUEL ever writes to the vault (first "Update from my vault" invocation per user), surface a one-time confirmation that explains SKUEL will inject `🆔` IDs into task lines. User must acknowledge once; subsequent syncs proceed silently. Gate stored as a user preference flag.

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

### Alternative E — Continuous background watcher (existing `vault_watch.py`)
**Explicitly rejected by Mike.** User-triggered button is the correct UX. The watcher also uses `POST /api/ingest/directory` → `batch.ingest_directory`, which bypasses `UserEntryService` entirely (no OWNS edge, no extraction, no processor) — it is architecturally the wrong path for periodic notes regardless of the UX choice.

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
