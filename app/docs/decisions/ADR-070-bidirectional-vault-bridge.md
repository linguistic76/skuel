---
title: "ADR-070: Bidirectional VaultBridge — Obsidian ↔ SKUEL Task Sync"
updated: 2026-09-22
status: accepted
category: decisions
tags: [adr, decisions, vault, obsidian, bidirectional-sync, vault-bridge]
related: [ADR-014, ADR-044, ADR-054, ADR-069]
related_skills: []
---

# ADR-070: Bidirectional VaultBridge — Obsidian ↔ SKUEL Task Sync

**Status:** Accepted — implemented in PR-3 (#319); **bidirectional for task state since
2026-09-16.** The inbound half — a vault-side check, uncheck, field edit, move or deletion of a
🆔 line reaching its task — is the R4 arc (#1343 identity survives one sync, #1344 the three-way
reconciliation, #1345 deletion cancels open tasks, #1346 these docs). Decisions 1–3 state the
mechanism as built; the record is
[r4-vault-inbound-propagation.md](../roadmap/done/r4-vault-inbound-propagation.md). The period
in which task state was outbound-only (2026-08-24 → 2026-09-16) is in the Changelog.

**Date:** 2026-06-16

**Decision Type:** ⬜ Pattern/Practice  ⬜ Infrastructure  ✅ Architecture

**Related ADRs:**
- Extends: ADR-069 (EXTRACT_ACTIVITIES pipeline — one-way ingest)
- Depends on: ADR-044 (hexagonal boundary), ADR-054 (UserEntry), ADR-014 (ingestion one-way design)
- Context: PR-1 ✅ (#315), PR-2 ✅ (#316) — one-way PoC bricks already merged

---

## Context

Mike authors periodic notes (daily/weekly/monthly/quarterly/yearly) in Obsidian using the
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

**Implementation consequence:** `EXTRACTED_FROM {vault_id, extracted_at, source_line_hash, source_line}` — `vault_id` is the stable join key; `source_line_hash` detects whether the line changed since last sync; `source_line` is the line verbatim as SKUEL last saw it, the base Decision 3's merge diffs the current line against.

> **Amendment (2026-08-23, cascade-residue PR-C):** the 🆔 is now read as identity at *ingest* too. Extraction Guard 2 (`source_line_hash` dedup) gained an identity form — Guard 2b: a line whose 🆔 already carries an `EXTRACTED_FROM` edge to the entry is already extracted, whatever its hash says. Without it, SKUEL's own outbound write-back (`[x]` + `✅ date`) moved the line's hash, Guard 2 missed on the next sync, Guard 4 (ACTIVE twins only, by design) could not catch a just-completed task, and the primary personal-data path re-created every task it marked done (reproduced end-to-end in `tests/integration/test_vault_done_date_hash_roundtrip.py`). The digest itself is unchanged — the `✅` date stays inside it deliberately, as the only discriminator between two same-title completed occurrences in one note — so no stored hash moved and the agent protocol did not change.

> **Amendment (2026-09-15, line-deletion retirement):** the two keys also decide when an edge's line is **gone**. File-level deletion propagation deletes a task's edges with its note; a 🆔 line deleted from a note that *survives* was invisible — the edge and its digest stayed behind, feeding Guards 2/2b on every later sync of the entry, and the same text typed back later hashed into the dead edge and was swallowed (the #1143 census found five such edges into one weekly note). The extraction pre-pass now retires every `EXTRACTED_FROM` edge whose line is gone by **both** keys — 🆔 nowhere in the text AND digest on no 🆔-less line — (`UserEntryService.retire_extracted_from_links`, keyed on the 🆔 as read so a concurrently re-keyed edge is left alone) and drops its digest from the exact-match set before any line is checked. **The task stays, stamped** by that same statement with the edge's 🆔 and base (`retired_vault_id`, `retired_source_line`, `vault_line_retired_at`) — the one-sync grace record a re-appearing 🆔 re-links by; an OPEN task whose 🆔 stays gone is cancelled by the end-of-sync sweep two syncs later, a terminal one is left as it is (the R4 amendment below). **One key gone is not a deletion:** a 🆔-less line still hashing to its edge is that line with its token stripped — it is recognised by hash as before (retiring it would re-mint a duplicate `[x] ✅` task, the very shape Guard 2b closed), and the outbound pass's injection arm, which now runs for any edge whose 🆔 the file does not carry, mints a fresh 🆔 onto it and re-keys the edge. The residual ambiguity is a same-edit race: a completed-in-SKUEL task whose unchecked line is deleted and retyped *before* the write-back lands reads as a stripped token (re-keyed, then checked off), not as a new occurrence; after the write-back the `✅` inside the digest tells them apart. An empty body (a note emptied down to its frontmatter) is a legitimate extraction run — it is the case where every 🆔 edge is a gone line — not a validation failure. Pre-existing dangling edges on files unchanged since are retired by one `./dev vault-sync --force`.

> **Amendment (2026-09-16, R4 — identity, base and grace, as built in #1343):** the edge carries one more property and the Task three.
>
> - **`EXTRACTED_FROM.source_line`** — the line verbatim, 🆔 token included, as SKUEL last saw it: the *base* of Decision 3's three-way merge. Written on create; **seeded** where an edge has none (the first sight after the property existed applies nothing — SKUEL's state stands and the outbound pass writes it back); **carried unchanged** by a re-point and a revival (a line edited or checked during a move must still diff against what SKUEL last saw); **advanced** only when its diff has been consumed — on an ok reconciliation write, or a verdict with nothing to write (`advance_extracted_from_links`) — and by SKUEL's own outbound writes, each of which is applied to the base as to the file (`_OwnWrite` in `VaultReconciler`: the `[x] ✅` write-back, the un-check, the 🆔 injection), so SKUEL never reads its own write-back as a vault edit. A refused or failed write holds the base, and the next sync sees the same diff.
> - **`Task.retired_vault_id` / `retired_source_line` / `vault_line_retired_at`** — the grace record, non-null only between a 🆔 line's disappearance and the sweep (or its re-link). Written by the retiring statement itself from the edge it deletes (the extraction pre-pass for a line gone from a surviving note; `IngestionBackend.delete_entities_with_metadata` for a deleted note — and a note moved out of the synced folders is a deleted note to the tracker), with `datetime()` as the database's own clock. The record is on the Task, not a tombstone on the edge, because an edge cannot outlive its note. Read by the user-wide 🆔 lookup (`find_task_by_vault_id`: live edges ∪ stamped tasks) and by the end-of-sync sweep; cleared by a revival or by the sweep after it has acted.
> - **Moves re-point.** A 🆔 the note's parser reads on an activity line that none of the entry's own edges carry is looked up user-wide *before* the guards run: a live edge on another entry is moved here in **one statement** (`repoint_extracted_from_link`: delete the old edge keyed on `(task, 🆔)`, MERGE the new one carrying base, digest and `extracted_at` unchanged); a stamped task with no edge is **revived** in one statement (the stamp's base becomes the new edge's, the three stamps cleared). Two calls would leave a window in which the task's only identity edge is gone and a retry mints a twin. A 🆔 found nowhere is a phantom the guards resolve as before. A 🆔-less line Guard 4 merges into an owned OPEN twin that has no edge to this entry now gets one (`merged_links`) — a line retyped for an open task is tracked again.
> - **The sweep.** At the end of every sync with the task round-trip, `list_vault_retired_tasks(owner, cutoff)` returns every stamp older than the sync's start, the cutoff read from the graph clock *before* anything this sync retires (an application-clock cutoff against a database-clock stamp lets skew erase the grace). Terminal, or still tracked from another note (a task can hold two lines; losing one is not losing the task) ⇒ stamp cleared. **Open and untracked ⇒ `CANCELLED` through `TasksService.update_task` (the status-guarded door, ADR-087), the stamp cleared only when that write returns ok** — a refused cancel keeps its stamp as the retry record and is one warning naming the task; a task whose stored status cannot be read is held the same way. The sweep does nothing at all over an incomplete inbound pass (`VaultSyncStats.inbound_pass_incomplete`: a failed or unreadable file, a stale local-agent mirror file, or a vault that read as empty or whose deletion valve refused) — a note that has not had its say may hold the very line that would revive a stamped task, and clearing even a terminal task's stamp then would let the next clean sync mint a duplicate completed task. The count of cancels surfaces as `VaultSyncStats.tasks_cancelled_by_deletion` (rendered only when nonzero); a retirement alone still is not reported. **The stamp clears with the cancel:** a 🆔 line typed back *after* its cancel is a phantom — Guard 4 ignores terminal twins, so it mints a new open task beside the cancelled one, which stays as the record of the deletion. The two doors that keep a task: re-type the line *before* the next sync (the revival), or un-cancel in SKUEL *first* and then type it back (Guard 4 merges it into the open twin by title and writes the edge).

---

### Decision 2 — Field Authority Table

Lossless round-trip between graph and markdown is **impossible**. Logseq DB confirmed this (their own docs: "Export as standard Markdown cannot capture all data in a graph"). SKUEL's bidirectional sync requires an explicit per-field canonical-authority policy.

Every vault→SKUEL row below is read the same way on a tracked line (one carrying a 🆔 SKUEL
already holds an edge for): **three-way per field on the note's re-ingest** — base = the edge's
`source_line`, theirs = the current line, ours = the task. A field is applied only when the line's
value differs from the base's (`theirs ≠ base`); a field the vault left alone keeps SKUEL's value,
and the outbound pass writes it back. The fields go into one `TaskUpdateRequest(...).to_intent()`
with the checkbox verdict — one `update_task`, one write, one verdict per line. A refusal by the
domain door (a task keeps a day — removing its only date; a future `✅` date; a blank title) is a
sync warning naming the line, re-raised every sync until the line and the task agree; nothing is
written and the base holds. On a **first extraction** (no 🆔 yet) the row is simply the field the
line mints the task with.

| Field | Canonical authority | Sync direction | Notes |
|-------|--------------------|--------------|-|
| Task title / description | Markdown | vault→SKUEL | The line's description; a retitle in Obsidian follows on the next sync, a retitle in SKUEL with an untouched line survives it (the line is then out of date until the user edits it — title is not written back) |
| Checkbox status done (`[x]`) | **Both** (merge) | bidirectional | Done in either → both done. SKUEL→vault: the outbound pass writes `[x]` + `✅ date` from `completion_date`. Vault→SKUEL: a `[x] ✅ D` completes the task with `completion_date = D`; a **dateless** tick (the plugin did not write a date) completes with today, and the outbound pass then appends SKUEL's `✅ today` — from then on SKUEL owns that completion. Both sides completed: Decision 3 |
| Checkbox status undone (`[ ]`) | **Both** (merge) | bidirectional | SKUEL→vault (2026-08-24): re-opening in SKUEL un-checks the line and strips the `✅` date it wrote — gated on a TRAILING `✅` token, so it takes back only its own write. Vault→SKUEL (R4): un-checking a line SKUEL had completed reopens the task (`status = ACTIVE`); a stale trailing `✅` the user left behind is SKUEL's and the outbound un-check strips it. `[ ]` on a **CANCELLED** task is *not* a reopen — cancel is SKUEL's decision, and the line diverges visibly until the user acts (`[x]` on a cancelled task is a check, applied) |
| Due date (📅) | Markdown | vault→SKUEL | Three-way; removing the only date is refused (keep-a-day) with a warning naming the line |
| Scheduled date (⏳) | Markdown | vault→SKUEL | Three-way |
| Start date (🛫) | Markdown | not synced | `Task` has no start field: the marker is stripped from the title and otherwise ignored, on first extraction and on re-ingest alike (R4: out of scope by name) |
| Done date (✅ YYYY-MM-DD) | **Both** (merge) | bidirectional | The completion timestamp Decision 3 compares. Written by the side that marks done; a vault-side move of the `✅` date on a task SKUEL did not touch since re-dates the task as written |
| Priority (🔺⏫🔼🔽⏬) | Markdown | vault→SKUEL | Three-way; emoji → `Priority`, absence = medium |
| `#hashtag` tags | Markdown | vault→SKUEL | Three-way as a **set**: tags the vault added join `Task.tags`, tags it removed leave, tags SKUEL holds that the line never carried (`period:{kind}`, one set in the UI) are kept |
| `🆔` ID token | SKUEL (mints) | SKUEL→vault | Written on first sync |
| 🆔 line **moved** between notes | Markdown | vault→SKUEL | The `EXTRACTED_FROM` edge is re-pointed in one statement, base and digest unchanged — never a deletion plus a re-mint; a cut whose paste lands one sync later is a revival by the stamp (Decision 1, R4 amendment). Same note or another is the same case |
| 🆔 line **deleted** (or its note deleted, or moved out of the synced folders) | Markdown | vault→SKUEL | Retired and stamped on the file's re-ingest (or the note's deletion); gone for **two consecutive syncs** ⇒ an OPEN task is `CANCELLED` by the end-of-sync sweep, a terminal one is left as it is. Re-type the line before the next sync to keep the task; after the cancel, un-cancel in SKUEL and type it back — typed back alone it is a new task |
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
- On sync, when **both** sides completed since SKUEL last saw the line: the side with the
  **later** completion date wins; an equal date is a tie and changes nothing; a dateless vault
  tick makes no date claim, so SKUEL's date stands and is written onto the line.
- Practical reality: concurrent completion (both sides check it off within the same sync window) has identical semantic intent — either "winning" value is correct. LWW is sufficient.

**The merge, as built (R4, 2026-09-16 — `core/services/dsl/line_reconciliation.py`).** "Concurrent"
is decided against the line as SKUEL last saw it, never by comparing the line to the task: the
sync runs inbound *before* outbound, so on the sync right after a task is completed in SKUEL its
line still reads `- [ ]`, and a bare "line ≠ task ⇒ apply the line" would reopen it before the
write-back ever ran (the mirror: reopen in SKUEL, the line still reads `[x] ✅`, re-completed). So
each field is judged three ways — **base** = `EXTRACTED_FROM.source_line` (Decision 1), **theirs** =
the current line, **ours** = the task:

- theirs = base ⇒ the vault did not touch the field; SKUEL's value stands and the outbound pass
  writes it back (a completion or reopen made in SKUEL survives the next sync).
- theirs ≠ base, ours = base ⇒ only the vault changed it; applied (vault wins its own fields).
- theirs ≠ base, ours ≠ base ⇒ both changed it; **the vault wins** (the user just pushed "sync") —
  for the checkbox by the later `✅` date, a tie changing nothing.
- One exception by rule: `[ ]` on a `CANCELLED` task is not a reopen (Decision 2).

The verdict and the field patch go into **one intent, one `update_task`** (ADR-087's status-guarded
door: legality, the `completion_date` stamp and clear, `TaskCompleted` / `TaskReopened`, the
keep-a-day rule). **The base advances only when that write has landed**, or when the verdict asked
nothing — a refusal or failure holds base and digest, so the next sync sees the same `theirs ≠
base` and retries, re-warning until the line and the task agree — **and it advances with SKUEL's
own outbound writes**, each applied to the base as to the file, so a write-back is never mistaken
for a vault edit on the next ingest. First sight of a 🆔 line whose edge has no base seeds it and
applies nothing.

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
2. **ID injection**: write `🆔 <id>` onto a task line that has no ID token — at the end of the line, except on a CHECKED line ending in a `✅ date`, where it goes in front of that marker so the marker stays the last token (the plugin's own ordering; amended 2026-09-15: appended *after* the marker, the 🆔 un-trailed it, so operation 1's no-op test failed on the next sync and appended a second date to an already-done line). On an UNCHECKED line a trailing `✅ date` is the user's own stray token — the adapter reads no completion from it — and the 🆔 is appended after it, which is what keeps it out of reach of operations 1 and 3 (left trailing, the un-check would strip it as SKUEL's and the done write would adopt it as the completion date). Idempotent: skip if `🆔` already present. The digest is 🆔-blind and whitespace-collapsed, so it is the same either way.
3. **Undone round-trip** (built 2026-08-24, amending Resolved Design Question 2): strip `[x]` → `[ ]` and strip the `✅ YYYY-MM-DD` token. Byte-exact reverse of operation 1 — the separating space operation 1 wrote in front of `✅` goes with the token, so a complete → reopen round-trip restores the line's original bytes. Driven by STATE, not by the `TaskReopened` event: the outbound pass queues it when a task is not `completed` and its line still carries the `✅` token, which is idempotent and re-evaluable on any sync. ⚠️ **A TRAILING `✅ date` is the trigger — not the checkbox, and not a token anywhere on the line.** Operation 1 always appends one at the END and — since 2026-08-24 — **keys its own two `✅` tests on the trailing marker too**, so it never changes a checkbox without leaving the marker that reverses it. That is what makes the two directions compose: SKUEL never authors a dateless `[x]` (one on a 🆔 line is the user's own Obsidian check — the inbound pass completes the task with today from it, Decision 3, and this pass then appends SKUEL's `✅ today`, after which SKUEL owns that completion), and a `✅ date` inside the task's own text is the user's prose (*"Compare ✅ 2025-01-01 vs now"*), never SKUEL's. Both wider readings destroy user-authored state: matching the checkbox reverts the user's own check, matching a token anywhere deletes words out of the description — and, on the completion side, suppresses the marker and leaves the `[x]` stuck forever. The un-check takes back only what SKUEL wrote.

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

`docs/Reviews/SYNC_UNIFICATION_REVIEW.md` (a *One Path Forward* pass over #482) surfaced two consolidation debts. PR 1's commit message promised PR 2 would *retire* `/api/ingest/directory` and `scripts/vault_watch.py`; PR 2 kept both working and removed only the admin button. The result: a parallel directory-ingest door (**A1**) and three sync triggers spanning two engines — the raw `/api/ingest/*` door vs. the `VaultReconciler` (**A2**). This decision resolves both. It also **enforces Alternative E** below, which rejected the continuous watcher in prose on 2026-06-16 while the code kept `vault_watch.py` alive as a live trigger — the exact intent-vs-reality drift the review caught. <!-- historical -->

**Ruling 1 — one engine (resolves A1).** The raw arbitrary-path `POST /api/ingest/directory` door is **deleted**. The single directory-ingest path is the `VaultReconciler`, reachable over HTTP as `POST /api/vault/sync` (PERSONAL, session user) and `POST /api/vault/sync/content` (CONTENT, admin, inbound-only); the admin dashboard's former "Ingest Directory" card becomes a **"Sync content vault"** button onto the latter. Arbitrary-path / glob admin ingest is retired with it — a pre-vault-era capability Mike confirmed (2026-07-01) is not needed, since the vault is the ingestion source of truth. PR 1's "to be retired" language is honoured, not deferred.

**Ruling 2 — human-initiated *per event* (resolves A2).** Ingestion happens exactly when a person asks for it. Sanctioned entry points, all explicit and all onto the one reconciler engine:
1. the "Update from my vault" button → `POST /api/vault/sync`;
2. the admin "Sync content vault" button → `POST /api/vault/sync/content` (the content vault, inbound-only);
3. a one-shot, human-run `scripts/vault_bridge_sync.py` (in-process reconciler).

**No unattended scheduler of any kind.** The continuous poll-loop is deleted, and cron / systemd-timer ingestion is out of scope. Mike's rationale: *a continuous watcher adds no value when the machinery is human-started anyway; per-event initiation is the cleaner, more honest system — you sync because you decided to.*

**Why per-event, not merely "machinery human-started."** The looser reading (launching a daemon is itself the explicit act, so a background watcher is fine) was considered and rejected: it re-imports the property we are removing — a scheduled `--once` is a continuous watcher wearing a cron hat, "not human per event" via a timer instead of a poll-loop. Sanctioning it would reopen the same drift this decision closes.

**Enforcement (done in this PR):** deleted `scripts/vault_watch.py` (the continuous poll-loop) and `scripts/provision_vault_watcher.py` (the watcher's HTTP service-account provisioner — obsolete once sync is in-process); deleted `POST /api/ingest/directory` and its route-level test; added `POST /api/vault/sync/content` (admin) onto the reconciler; rewired the ingestion dashboard's directory card to a "Sync content vault" button; replaced `./dev vault-watch` with one-shot `./dev vault-sync` (→ `vault_bridge_sync.py`); updated the CLAUDE.md ingestion note. <!-- historical -->

**Rejected:** (a) cron / systemd `--once` as sanctioned automation — violates per-event-human initiation; it is Alternative E by another name. (b) keeping `/api/ingest/directory` as a parallel raw ingest door — One Path Forward forbids two live paths to one outcome. <!-- historical -->

**Unchanged:** this decision governs *triggers and engine count only*. Descriptor-by-path ingest ownership (Decision 7) and the code-defined default-deny sync allowlist (Decision 8) are untouched; the fail-closed privacy wall still applies beneath every entry point above.

**Amendment (2026-09-21, Mike's ruling — Ruling 1 made true in code).** Two more raw directory doors outlived the 2026-07-01 deletion: `POST /api/ingest/vault` (`vault_path` + `subdirs`) and `POST /api/ingest/domain/{domain_name}` (`source_path` + glob `pattern`, the domain name a label, not a filter). Both called `ingest_directory` directly over a caller-chosen sub-directory — the partial ingest that leaves deletions unreconciled, authored edges unretracted and 🆔 lines unretired — and neither had a consumer (the domain door's only poster, a list-page trigger, was never mounted and was deleted 2026-02-26; nothing ever posted to the vault door). Both are deleted, with `UnifiedIngestionService.ingest_vault`, the `ingest_directory(dry_run=True)` preview mode (`DryRunPreview`, `check_existing_entities`) that only the domain door reached, and the two result fragments only it rendered — and with `scripts/ingest_user_activities.py`, a 2026-03 one-off (hard-coded user, a `data/user_vaults/` input that no longer exists, raw `ingest_directory` twice plus a hand-written `OWNS` merge the bulk upsert has written itself since ADR-086). **The reconciler is now the one directory-ingest path and `VaultReconciler.preview` the one dry run**; a scoped re-ingest, if ever wanted, is a `--path` option on `scripts/vault_bridge_sync.py`, never an HTTP door. `POST /api/ingest/file` (single file) and `POST /api/ingest/bundle` (manifest-listed files) remain — neither is a directory ingest. <!-- historical -->

**Amendment (2026-09-22, Mike's ruling — one ingestion system).** The two doors the first amendment left standing are deleted, with everything only they reached. `POST /api/ingest/bundle` → `UnifiedIngestionService.ingest_bundle` → `batch.ingest_bundle` (`manifest.yaml` → `import_order` → `find_entity_file` → per-file `ingest_file`, reported as `BundleStats`): nothing ever posted to it, no `manifest.yaml` exists in either vault or the repo (the five SEL bundles left the tree with `yaml_templates/` in 2026-03), and its one capability — caller-ordered phases — is what the two-phase directory ingest makes unnecessary (every node lands before any edge; same-sync forward references resolve on one pass). `POST /api/ingest/file` and the dashboard's "Ingest File" card: the card had posted without the CSRF header since the door was CSRF-protected on 2026-04-19, so every click 403'd for five months and nobody noticed — and a one-file re-sync is what smart mode already is (an edited file is the only one the walk re-processes; `--force` re-processes the rest). With them go `_validate_ingestion_path` / `_resolve_allowed_ingestion_roots` / `_reject_symlink_file` and the `SKUEL_INGESTION_ALLOWED_PATHS` knob — a path allowlist for HTTP doors that no longer exist (the reconciler resolves roots from vault descriptors, never from a request body) — and `scripts/ingest_nous.py` + `scripts/generate_kus_from_moc.py` + `core/utils/hierarchy_parser.py`, an initial-commit pair that generated a `ku:`-spelled file per MOC heading (the colon spelling is retired; the input MOC and output folder no longer exist; `moc: true` frontmatter is the ORGANIZES authoring surface). `ingest_file` the *method* stays: it is the per-file pipeline the walk runs and the vault UserEntry door. **Ruling 2's entry points are the three doors as built** — the two sync buttons and the script; the reconciler has no single-path variant, and a scoped re-ingest, if ever wanted, is a `--path` option on `scripts/vault_bridge_sync.py`. `ingestion_api.py` keeps one route, the chunk-regeneration admin tool. <!-- historical -->

**See:** `docs/Reviews/SYNC_UNIFICATION_REVIEW.md` (A1, A2), Alternative E (below), Decision 7, `scripts/vault_bridge_sync.py`, `adapters/inbound/vault_routes.py` (`POST /api/vault/sync`, `POST /api/vault/sync/content`), `core/services/vault/vault_reconciler.py` (`sync`).

---

### Decision 10 — Curriculum ingestion is one-way; the content vault is the sole author of curriculum structure (2026-09-03)

"Bidirectional" in this ADR is task state on PERSONAL vaults (Decisions 1–4). The content vault has
one direction: Obsidian authors, SKUEL ingests, nothing writes curriculum back. Mike ruled it
2026-07-11, when a "make the content vault bidirectional like the personal vault" request resolved,
on clarification, to the edit-and-resync workflow the inbound sync already is — an edited file
re-ingests on the next human-initiated sync (Decision 9); a deleted file removes what it declared.
The re-sync contract is stated once, in the `unified_ingestion_service` module docstring.

**Curriculum structure** here means Ku, PathStep and LearningPath — their properties, bodies and
edges — plus CURRICULUM-scope Exercises. Verified 2026-09-03:

- Ku, PathStep and LearningPath have no create/update/delete route: their `DomainRouteConfig`s
  (`ku_routes.py`, `path_steps_routes.py`, `pathways_routes.py`) declare no `crud=`. The PathStep
  composition endpoints (`/api/path-steps/{content,attach-to-path,detach-from-path,relationships,
  tags,organize,unorganize,reorder}` in `path_steps_api.py`) have no UI caller — the UI posts only
  learner state (`start`, `bookmark`, `mark-read`; Ku `mark-studying`, `mark-understood`).
- `ExerciseCreateRequest` refuses `scope: curriculum` — such exercises "are authored in the
  content vault and ingested, not created via the API".
- The one in-app curriculum-edge write, prerequisite-suggestion approval, lands as an Edge YAML in
  the content vault's `edges/` (`PrereqSuggestionService`) — the vault stays the author and the
  next sync reads it back.

**What SKUEL does author in-app** (the sole-author claim stops here): PERSONAL / ASSIGNED /
ASSESSMENT exercises, which are user-owned. The six PathStep-owned Activity Templates keep a
`/api/pathstep-{domain}-templates/*` JSON CRUD (TEACHER+), but the vault is their author.

> **Amended 2026-09-05 — Activity Templates are no longer an exception.** Decision 10 named them
> in-app-authored because the teaching UI was their only door. It was also the reason zero
> templates existed: they had been given precisely the surface the Activity instances deleted in
> March. They are now vault-ingestible (`type: task_template`, …; a PathStep attaches them via
> `{domain}_template_uids:` frontmatter), so Decision 10's sole-author claim extends to them and
> the remaining exception is user-owned exercises. The teaching create/edit/detach forms were
> deleted 2026-09-06; `/teaching/ps/{ps_uid}/templates` survives as a read-only panel on the PS
> detail page. See [activity-templates-vault-door.md](../roadmap/done/activity-templates-vault-door.md).

**Consequence.** A SKUEL-side editor for curriculum structure is a new decision, not an extension
of this one: it needs outbound-before-inbound ordering in the reconciler, two-sided conflict
handling (dirty entity + changed file SHA → skip both, warn, explicit accept-vault / accept-SKUEL),
and merge-in-place frontmatter edits under Decision 4's VaultWriter rules. Until one ships, "make
the content vault bidirectional" resolves to this decision.

**See:** Decision 7 (the two vaults differ only in access rights), Decision 9 (human-initiated
sync), CLAUDE.md § Unified Content Ingestion, `docs/user-guides/how-your-content-is-used.md` (the
personal vault's own direction statement).

---

## Resolved Design Questions (2026-06-16)

**1. Trigger scope:** Originally "support BOTH — sync all changed notes AND sync a single note; the API supports both from day one." **As built (Decision 9, amended 2026-09-22): one trigger.** `VaultReconciler.sync` walks the whole vault in smart mode, so "sync a single note" is what the one button does when one note changed — the unchanged rest is hash-skipped. No single-path API variant was ever built, the raw per-file HTTP door that stood in for it is deleted, and a scoped re-ingest, if ever wanted, is a `--path` option on `scripts/vault_bridge_sync.py`.

**2. Undone round-trip (SKUEL→Obsidian `- [ ]` write):** Originally **OUT OF SCOPE for v1** — *"re-opening a completed task is not a current workflow and re-introducing it does not justify the complexity."* The deferral rested on three claims, and it was **AMENDED 2026-08-24** because two of them turned out to be false:
- ~~The INBOUND direction (Obsidian edit `- [ ]` → SKUEL re-opens task) works for free~~ — **false, and it is what made the deferral unsafe.** At the time no status-reconciliation branch existed beside the extraction guards, and Guard 2b deliberately skipped any already-🆔'd line (it was built later, as the R4 arc — Decision 3). So the vault could not correct itself either: a task re-opened in SKUEL kept its `- [x] … ✅ date` line indefinitely, with a ✅ date recording a completion that had been withdrawn.
- ~~It is only a UX gap, not an architectural inconsistency~~ — a stale `✅ date` in the user's own files is a **wrong record**, not a missing feature. The vault is the source of truth for personal data (ADR-070's own premise); SKUEL writing a completion into it and then never withdrawing it is the app falsifying that record.
- The complexity claim held, and was paid down first: the un-check inherits `WriteResult.updates_applied` (protocol v2), so it reports its own per-update outcome instead of hiding a miss inside a file-level success.

**The amendment (Mike, 2026-08-24), stated as built:** a reopen DOES un-check its vault line and strip the `✅` date — **but only the lines SKUEL itself completed.** A **trailing** `✅ date` token is the discriminator, not the checkbox: the done write always appends one at the end, so a dateless `[x]` on a 🆔 line is definitionally the user's own Obsidian check — and because it appends at the END, a `✅ date` inside the task's own text was never SKUEL's either. The done write keys on the same trailing predicate, so every checkbox SKUEL changes carries the marker that reverses it. A vault-side dateless check is the user's edit — the inbound pass reads it as a completion (Decision 3) — and reverting it here would fight the completion it produced. So the operation is the narrow, defensible claim — *a withdrawn completion must not leave SKUEL's own completion token behind* — not a claim of ownership over the checkbox. A dateless `[x]` is not SKUEL's to take back: the inbound pass completes the task from it and the done write then dates the line. The trigger is the outbound pass's **state predicate** — "this task is not `completed` AND its line is still marked done" — not the `TaskReopened` event, which stays published and deliberately unsubscribed. `is_reopen` is only knowable after the guarded write returns the prior status (ADR-087), so the graph write has already committed before any consumer could run and a failed vault write would have **no retry**: re-issuing writes nothing, because the prior is no longer `completed`. A one-shot transition needs a state predicate, not an event. The field-authority table row for undone moves from "deferred" to SKUEL-authoritative.

**Inbound (R4, #1344, 2026-09-16):** a vault-side check or un-check of a 🆔 line reaches SKUEL on the note's ingest — Decision 3's merge, as built. The two directions meet on the base: SKUEL's own un-check advances it, so the next ingest does not read the restored `- [ ]` as a vault edit.

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
| 2026-09-03 | Mike + Claude Code | **Decision 10** — curriculum ingestion is one-way; the content vault is the sole author of curriculum structure (Ku/PathStep/LP + CURRICULUM-scope exercises: no create/update/delete route; the PS composition endpoints have no UI caller; prereq approval writes into the vault). The in-app-authored exceptions are named: Activity Templates (teaching UI) and user-scoped exercises. Records Mike's 2026-07-11 ruling (signal arc, Q3). | 0.7 |
| 2026-09-05 | Mike + Claude Code | **Decision 10 AMENDED** — Activity Templates leave the in-app-authored exception list: they are vault-ingestible (`type: <domain>_template`, PathStep attaches via `{domain}_template_uids:`). The teaching UI was their only door and the whole explanation for zero templates existing. User-scoped exercises remain the one exception. See `roadmap/done/activity-templates-vault-door.md`. | 0.8 |
| 2026-09-15 | Claude Code | **Decision 1 AMENDED** — a 🆔 line deleted from a surviving note retires its `EXTRACTED_FROM` edge on the file's re-ingest (both keys gone: 🆔 absent, digest on no 🆔-less line); the task stays, edge-less. A stripped token (one key gone) is recognised by hash and re-minted by the outbound injection arm, which now runs for any edge whose 🆔 the file does not carry. **Decision 4 op. 2 AMENDED** — the 🆔 is written in front of a trailing `✅ date`, so the done marker stays trailing and the next sync does not append a second date. Closes deferred-work § "Line Deletions Leave `EXTRACTED_FROM` Edges" (`roadmap/done/line-deletions-leave-extracted-from-edges.md`). | 0.9 |
| 2026-09-15 | Mike + Claude Code | **R4 PR 1 (#1343) — identity survives a line's disappearance for one sync.** `EXTRACTED_FROM.source_line` (the base — written on create, seeded where absent, carried by re-point and revival, not yet advanced); the three grace stamps on Task, written by the retiring statement (pre-pass and note deletion alike); `find_task_by_vault_id` (live edges ∪ stamped tasks); moves re-pointed and revivals re-linked in one statement each; Guard 4 writes the edge for a twin with none to the entry; the end-of-sync sweep (graph-clock cutoff, hold over an incomplete inbound pass) clears terminal and still-tracked tasks' stamps. | 0.10 |
| 2026-09-15 | Mike + Claude Code | **R4 PR 2 (#1344) — reconciliation, both directions.** Decision 3's merge built: `reconcile_task_line` (three-way per field: checkbox both ways, title, 📅, ⏳, priority, `#tags`), one intent through `update_task`, base and digest advance only on ok; a refusal re-warns every sync and leaves the note un-stamped. Found while building: SKUEL's own outbound writes advance the base too (`_OwnWrite`). A dateless vault tick completes with today; `[ ]` on a cancelled task is not a reopen. Decision 2's `[x]`/`[ ]`/field rows became true. | 0.11 |
| 2026-09-16 | Mike + Claude Code | **R4 PR 3 (#1345) — deletion cancels open tasks.** The sweep posts `CANCELLED` through the facade for an open, untracked task whose stamp predates the sync, clearing the stamp only on ok; `VaultSyncStats.tasks_cancelled_by_deletion`. Review-found: the hold was blind to a vault in doubt as a whole — `vault_read_refused` (empty walk / mass-deletion refusal) joined `inbound_pass_incomplete`. Ruled: the stamp clears with the cancel (a line typed back after it is a new task); a note moved into a walled folder is a deleted note to the tracker. | 0.12 |
| 2026-09-16 | Claude Code | **R4 PR 4 (#1346) — this ADR states the built mechanism.** Status annotation retired; Decision 1 gains the R4 amendment (base, stamps, moves, sweep); Decision 2's table rewritten row by row (three-way per field, the deletion and move rows, 🛫 not synced); Decision 3 gains "the merge, as built"; Decision 4 op. 3 and Resolved Design Question 2 no longer say a vault-side check does not reach SKUEL. Build plan → `roadmap/done/r4-vault-inbound-propagation.md`. | 1.0 |
| 2026-09-21 | Mike + Claude Code | **Decision 9 AMENDED** — Ruling 1 made true in code: `POST /api/ingest/vault` and `POST /api/ingest/domain/{domain_name}` (raw `ingest_directory` over a caller-chosen sub-directory, no consumer) deleted with `ingest_vault`, the `dry_run` preview mode of `ingest_directory` and its two fragments; the reconciler is the one directory door, `VaultReconciler.preview` the one dry run. | 1.1 |
| 2026-09-22 | Mike + Claude Code | **Decision 9 AMENDED again — one ingestion system.** `POST /api/ingest/file` (+ the dashboard card that had 403'd since 2026-04-19) and `POST /api/ingest/bundle` (+ `ingest_bundle`, `BundleStats`, `find_entity_file`; no manifest ever existed) deleted with the HTTP path allowlist (`_validate_ingestion_path`, `SKUEL_INGESTION_ALLOWED_PATHS`) and the nous generator pair (`ingest_nous.py`, `generate_kus_from_moc.py`, `hierarchy_parser.py`). Ruling 2's entry points restated as the three doors built; Resolved Design Question 1 restated as built (one trigger). | 1.2 |
