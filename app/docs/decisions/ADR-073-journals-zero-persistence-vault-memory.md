# ADR-073: Journals Are a Zero-Persistence Private Workshop; the Vault Is the Only Memory Channel

**Status:** Accepted — PR 1 (text sessions + allowlist) and PR 2 (upload/transcription, decision A) shipped; PR 3 (exemplars) remains (see *Implementation Status*).
**Date:** 2026-06-30
**Related:** ADR-054 (UserEntry collapse), ADR-069 (EXTRACT_ACTIVITIES pipeline + EntryReport), ADR-070 (bidirectional VaultBridge), PR #475 (SyncAllowlist fail-closed vault privacy wall)

---

## Context

The Journals domain accreted a persistence model that no longer matches its intended
purpose. Today, `/journals/start` and `/journals/upload` write a `UserEntry` to Neo4j so
the in-app chat is revisitable. Separately, the vault sync path (`/submissions/sync`) is the
channel through which SKUEL comes to *understand* a user — but its allowlist ships locked to a
single folder (`periodic_notes/`), and the shipped code contradicts the user-facing guides on
which folders are tracked (the guides say `je_raw/`/`je_pro/` are stored; the code excludes
them unconditionally).

The product intent, stated by the founder, is simpler and stronger than what shipped:

> A journal is a **workshop** — rough brainstorming. SKUEL processes it, hands the output
> back as a file the user keeps wherever they choose, and **remembers nothing**. The only way
> SKUEL comes to understand a user is when the user *deliberately* refines a thought into a
> note and places it in a synced folder. That deliberate act — not journaling — is the
> doorway.

This makes the Journals domain a **private user space**: SKUEL *can* technically read what
flows through it, but by design it *doesn't* — the same "this folder is mine, that folder is
shared" model users already understand from a filesystem.

## Decision

### 1. Two channels, deliberately separated

| Channel | Role | What SKUEL persists |
|---|---|---|
| **Journal (workshop)** | Rough brainstorm / thinking out loud. Process → return → download. | **Zero.** Nothing in the database. |
| **Vault sync (doorway)** | The user's deliberate "here is what I want SKUEL to know." | Only what sits in an allowlisted doorway folder. |

The journal never writes to SKUEL's model of the user and never creates domain entities.
Entity creation is exclusively the EXTRACT_ACTIVITIES path (ADR-069), reached only through a
doorway folder marked `pipeline: extract_activities`.

### 2. Folder taxonomy

**Workshop — `je_*` folders. SKUEL persists nothing from any of these; none are a doorway.**

| Folder | Who writes | What SKUEL does with it | Enters model of user? |
|---|---|---|---|
| `je_in/` | User (raw journal / audio) | Reads once to process, then forgets | ❌ never |
| `je_out/` | **SKUEL** (processed output for download) | **Write-only** — never read back | ❌ never |
| `je_raw/` + `je_pro/` | User (curated example input→output pairs) | Read **only to shape processing *style*** (few-shot exemplars for new `je_in`), never as facts about the user | ❌ never |

**Doorway — the ONLY channel into SKUEL's understanding of the user.**

| Folder | Frontmatter mode | Effect on sync |
|---|---|---|
| `periodic_notes/` | `extract_activities` or `journal` | Task extraction and/or soft context |
| `personal_notes/` | `journal` (soft context) or `extract_activities` | Feeds UserContext / Askesis |
| `activity_notes/` | `extract_activities` (typical) | Notes tied to the 6 Activity Domains |

Everything else in the vault is **walled off by default** (fail-closed `SyncAllowlist`).

### 3. Persistence rules

- **Journal sessions** (`/journals/start`, `/journals/upload`): **zero** Neo4j persistence.
  The durable artifact is the file SKUEL writes to `je_out/` for the user to download and keep.
- **Periodic notes** (daily / weekly / monthly): **kept** — stored as `UserEntry` and editable
  in-app (`/journals/{uid}/note`). This is a valued feature, distinct from a brainstorm session.
- **Doorway notes**: ingested on sync as `UserEntry`; `journal`-mode notes feed the context
  digest, `extract_activities`-mode notes create real entities (ADR-069).

### 4. Exemplar-guided processing (new capability)

`je_raw/` (example input) + `je_pro/` (example output) become live few-shot exemplars that
shape how the pipeline processes a new `je_in` item — teaching SKUEL *how the user likes
journals processed* without teaching it anything *about* the user. When used, the exemplars
are sent to the AI provider for that one request, same as any AI feature (they are the user's
own examples). They are never ingested as personal memory.

## Implementation Status

Progress against target (PR 1 + PR 2 shipped; PR 3 remains):

| Aspect | Was | Now |
|---|---|---|
| Journal session persistence | Writes `UserEntry` | ✅ **Zero** — process → return inline / `je_out/` file |
| File upload + transcription | Writes `UserEntry` (+ manual processing) | ✅ **Zero** — process → `je_out/` file (decision A) |
| Sync allowlist default | `periodic_notes/` only | ✅ `periodic_notes/`, `personal_notes/`, `activity_notes/` |
| `je_raw/`/`je_pro/` | Unconditionally excluded, inert | ⏳ PR 3 — read as processing exemplars |
| Periodic notes | Stored + in-app editable | **Unchanged (kept)** |
| Model-feeding read (`get_vault_notes_for_context`) | Filters `pipeline='journal'` + `vault_file_path` | Unchanged; already excludes journal sessions |

**One Path Forward deletions** made by the code pass (machinery that existed only to serve
storage the design removes): the journal-session chat page (`/journals/{uid}` is now
periodic-notes-only), the recent-sessions landing + sidebar lists, the suggestions-cache-in-
metadata helpers, and `UserEntryService.submit_file`/`_store_file` (the bytes-to-disk +
entry-creation helper journals was the sole consumer of). Periodic-note machinery is retained.

**Sequenced code pass:** `plans/journals-zero-persistence-code-pass.md` — PR 1 ✅ (stateless text
sessions + expanded allowlist, the privacy win), PR 2 ✅ (upload/transcription), PR 3 ⏳ (exemplar
processing).

**Async-transcription decision — resolved to (A).** "Sessions store zero" is trivial for text
(process → return → download) but was harder for **audio**, which previously attached its
transcript to a `UserEntry`. **Decision (A)** was chosen: transcription is synchronous and
file-based (audio → `je_out/` transcript → download; FOUNDER continues to the DNWF review→Scribe
flow), fully stateless. This is strictly better than the rejected **(B)** (transient pending-job
entry, delete-after): there is no background worker, so STANDARD audio uploads previously created
an entry that was *never* auto-processed — (B) would have preserved a UX that did not function.
Single-file upload, multi-file upload, and `folder-process` now share one stateless batch engine
(`je_in`/temp dir → `je_out/`).

## Testability (the contract must be provable, not promised)

The "stores zero / reads zero" contract is enforceable by tests, not policy alone:

1. **Zero session persistence** — posting to `/journals/start` and `/journals/upload` leaves
   the `UserEntry` store count unchanged.
2. **Zero model influence** — `get_vault_notes_for_context()` (the only path by which
   journal-ish content reaches `_build_context_summary`) returns nothing sourced from a
   `je_*` folder or a journal session; only doorway notes appear.
3. **Fail-closed wall** — `SyncAllowlist` ingests a file under a doorway folder and walls off
   an identical file placed anywhere else.
4. **Unconditional `je_*` exclusion** — `is_staging_path()` keeps every `je_*` component out
   of ingestion regardless of allowlist configuration.

## Consequences

- **Positive:** an honest, testable privacy contract; a genuinely private journal; deletion of
  storage-only machinery (One Path Forward); the vault becomes the single, deliberate source of
  truth for what SKUEL knows.
- **Cost:** in-app journal *session* history is lost (by design — the user keeps the file).
  Two-way pressure on periodic notes (edited in-app **and** synced from the vault) is a known
  reconciliation concern deferred to the VaultBridge work (ADR-070), not this ADR.
- **Residual gap:** doorway notes and periodic notes are still plaintext at rest in Neo4j.
  Field-level encryption remains the planned close on operator-level access (see the privacy
  user guide).
- **Residual (multi-tenant default):** the expanded default allowlist (`periodic_notes/` +
  `personal_notes/` + `activity_notes/`, PR 1) is *default-on* — a deliberate single-user choice
  so the doorways aren't dark. For a future hosted / multi-tenant deployment this is a
  trust-boundary default worth revisiting: prefer a **per-user opt-in** over a global default
  before that milestone, since a folder named `personal_notes/` could be assumed private. Raised
  in review (Kody, PR #477) and deferred, not dismissed.
- **Residual (flat `je_out/`, PR 2):** browser-upload outputs are written *flat* to `je_out/`
  with the predictable `{stem}{suffix}` name, and `GET /journals/je-out/{filename}` serves that
  flat folder behind an auth + path-containment guard only. This is deliberate: `je_out/` is the
  user's own local Obsidian vault folder, and flat is what makes the files openable there — the
  feature is single-user-local by design (one vault per install). On a hosted / shared-filesystem
  deployment this same flatness would let one authenticated user overwrite or download another's
  output by basename; a per-user vault mount (so `je_out/` resolves per-user) or a per-output
  unguessable token is the fix at that milestone. Raised in review (Codex, PR #478) and
  **accepted-as-designed** for the single-user-local model, deferred for hosting — not dismissed.
  The same flatness means a folder rerun keyed by `{stem}` overwrites a prior same-stem output
  ("newest wins" in the user's own folder) — intended for one vault; the per-user-mount fix
  above covers it for hosting (Kody, PR #478).
- **Residual (fresh-vs-reuse transcription, PR 2):** `transcribe_and_instructions` forces
  fresh transcription (`skip_existing=False`) so the structured `_out.md` always reflects the
  *current* audio — a folder rerun after the audio was replaced under the same basename must not
  structure a stale `je_out/{stem}.txt`. The deliberate cost: a rerun cannot reuse an existing
  on-disk transcript, so a *transient* Deepgram failure means re-running rather than falling back
  to the stored transcript. Fully satisfying both (correct-content **and** reuse-on-failure) needs
  freshness validation (reuse a transcript only when it is newer than its source audio), which is
  filesystem-mtime fragile and disproportionate here. Both horns were raised across review rounds
  (Kody, PR #478); force-fresh is the **correctness-preferring default**, revisit with freshness
  validation if transcription cost/robustness becomes a driver. `transcribe_only` keeps per-caller
  reuse (folder-process idempotent, uploads fresh).
