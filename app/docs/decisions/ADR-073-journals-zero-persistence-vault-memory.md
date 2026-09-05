---
updated: 2026-09-05
---

# ADR-073: Journals Are a Zero-Persistence Private Workshop; the Vault Is the Only Memory Channel

**Status:** Accepted — PR 1 (text sessions + allowlist), PR 2 (upload/transcription, decision A),
and PR 3 (disk-only exemplars) shipped (see *Implementation Status*).
**Amended 2026-07-11 (§2/§3/§4):** `je_pro/` split from the workshop wall into a **conditional
doorway** — a stored understanding channel gated on explicit frontmatter consent, scoped by the
`je_use:` enum. `je_in`/`je_out`/`je_raw` stay unconditionally walled. Part of the
entry-enrichment arc (je_pro doorway → UserEntry embeddings → entry→Ku grounding).
**Amended 2026-07-12 (§1/§3 — see ADR-078):** the "zero persistence" commitment is narrowed by
**one** carve-out: owner-private **discussion sessions** persist to Neo4j for revisit/continue
only. This relaxes persistence (commitment 1) for discussions **without** touching the
understanding wall (commitment 2) — discussion sessions/turns reach no context builder,
embedding, search, ZPD, or intelligence surface. Full reconciliation, schema, access model, and
shifted testability bar live in **ADR-078** (Discussion Sessions Are Stored but Never
Understood).
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

### 2. Folder taxonomy *(amended 2026-07-11: je_pro split out of the workshop wall)*

**Workshop — `je_in`/`je_out`/`je_raw`. SKUEL persists nothing from these; none are a doorway.**

| Folder | Who writes | What SKUEL does with it | Enters model of user? |
|---|---|---|---|
| `je_in/` | User (raw journal / audio) | Reads once to process, then forgets | ❌ never |
| `je_out/` | **SKUEL** (processed output for download) | **Write-only** — never read back. ALL processed outputs land here (plain transcripts and intimately-processed files alike — the app never distinguishes) | ❌ never |
| `je_raw/` | User (raw half of curated example pairs) | Read **only to shape processing *style*** (few-shot exemplars for new `je_in`), never as facts about the user | ❌ never |

**Doorway — the ONLY channel into SKUEL's understanding of the user.**

| Folder | Frontmatter mode | Effect on sync |
|---|---|---|
| `periodic_notes/` | `extract_activities` or `journal` | Task extraction and/or soft context |
| `personal_notes/` | `journal` (soft context) or `extract_activities` | Feeds UserContext / Askesis |
| `activity_notes/` | `extract_activities` (typical) | Notes tied to the 6 Activity Domains |
| `knowledge/` | `knowledge` | "Developed files" — the user's own notes, shared to teach SKUEL about them |
| `je_pro/` | **Conditional** — see below | Frontmatter-gated understanding channel + processed half of exemplar pairs |

**`je_pro/` is a *conditional* doorway (dual duty).** A je_pro file serves as the processed
half of a stem-matched `je_raw`↔`je_pro` exemplar pair, and — only with explicit frontmatter —
as a stored understanding entry. **Consent = placement AND frontmatter**: a file ingests only
when it declares an explicit `pipeline:` (`type: user_entry` + `pipeline: knowledge` is the
expected/knowledge-contract form) and a compatible `je_use:`. A bare je_pro file stays
exemplar-only — exactly the pre-amendment behavior.

The `je_use:` frontmatter enum scopes the dual duty (ONE field — two booleans were rejected as
self-contradictable):

| `je_use:` | Style exemplar? | Ingested (understanding)? |
|---|---|---|
| absent / `both` | ✅ | ✅ (iff `pipeline:` declared) |
| `exemplar` | ✅ | ❌ never ("learn nothing about me") |
| `understanding` | ❌ never | ✅ (iff `pipeline:` declared) |

Two consumers must respect it: the exemplar loader (`JournalBatchService._load_exemplars` skips
`understanding` files and strips frontmatter from exemplar text) and the ingestion gate
(`je_pro_skip_reason` skips `exemplar` files and bare files, with a per-file sync warning
telling the author how to promote). An unrecognized `je_use` value is honored in *neither*
direction (fail-closed both ways) and warned. An `exemplar` file with no stem-matched je_raw
twin gets a gentle sync warning — it is used in neither direction.

**Consent narrowing is honored:** the gate lives inside `is_ingestible_path()` — the single
predicate collection AND deletion reconciliation share — so a stored je_pro entry whose file
later loses its `pipeline:` or flips to `je_use: exemplar` reads as not-collectible and is
**deleted from the graph on the next sync**.

Everything else in the vault is **walled off by default** (fail-closed `SyncAllowlist`).

### 3. Persistence rules

- **Journal sessions** (`/journals/start`, `/journals/upload`): **zero** Neo4j persistence.
  The durable artifact is the file SKUEL writes to `je_out/` for the user to download and keep.
- **Periodic notes** (daily / weekly / monthly / quarterly / yearly): **kept** — stored as `UserEntry` and editable
  in-app (`/journals/{uid}/note`). This is a valued feature, distinct from a brainstorm session.
- **Doorway notes**: ingested on sync as `UserEntry`; `knowledge` notes feed the context
  digest, `extract_activities` notes create real entities (ADR-069). *(Amended 2026-09-02:
  `Pipeline.JOURNAL` is deleted. It had been authored-never-assigned since #479 re-stamped the
  vault notes to `knowledge` and #608 purged the stored rows — `knowledge` + `private:` is the
  one path for a context note; the count it fed, `total_journal_count`, went with it. A
  `knowledge` note with no `audience:` is **private**, and so is an `extract_activities`
  periodic note — the door's `teachers` default is submission semantics,
  `Pipeline.shares_by_default()`; follow-ups to #1227.)*
- **je_pro entries** *(amended 2026-07-11)*: a frontmatter-consented je_pro file ingests as a
  stored `UserEntry` exactly like a `knowledge/` doorway note. Withdrawing consent in the file
  (dropping `pipeline:` or flipping to `je_use: exemplar`) deletes the stored node on the next
  sync — the graph never holds a je_pro entry whose file no longer consents.

### 4. Exemplar-guided processing (new capability)

`je_raw/` (example input) + `je_pro/` (example output) become live few-shot exemplars that
shape how the pipeline processes a new `je_in` item — teaching SKUEL *how the user likes
journals processed* without teaching it anything *about* the user. When used, the exemplars
are sent to the AI provider for that one request, same as any AI feature (they are the user's
own examples). *(Amended 2026-07-11:)* exemplar use itself still persists nothing, but a
je_pro file may **separately** consent to ingestion via frontmatter (§2); `je_use:` scopes
which duties apply, and the loader strips any frontmatter block before injecting exemplar
text (consent metadata is not style).

**Shipped as disk-only (PR 3).** Matched `je_raw`↔`je_pro` pairs (by filename stem, bounded to a
few small pairs) are read *off disk at processing time* and injected into the STANDARD
journal-processing prompt as labeled few-shot examples. Nothing is ingested, stored, or turned
into an entity — the zero-persistence contract holds literally. Missing/empty folders degrade
cleanly to the no-exemplar prompt.

**Two conceptual layers (PLANNED, collapsed while single-user).** These exemplars carry two
purposes that are one and the same today because there is a single user:

- **#1 — global / domain-process exemplars** (user-agnostic): teach the *craft* of processing a
  journal, the same for everyone. Conceptually a **product asset** (alongside the global journal
  guidance in `data/instructions/`), not per-user private data.
- **#2b — per-user personal journal style** (private): how *this* user likes *their* journals
  processed. The per-user mirror of #1; the future home of `Pipeline.REFERENCE` — stored
  privately, excluded from context, marked as a journal exemplar.

(**#2a** — what SKUEL learns *about* the user from journaling — is **not** new: it is the vault
doorway, `pipeline: knowledge` feeding UserContext.) `Pipeline.REFERENCE` is **reserved**
for the #2b stored layer and has **no producer today**; disk-only exemplars satisfy the
functional need without it. Splitting #1 (product-default) from #2b (per-user stored) is deferred
until there is more than one user.

## Implementation Status

Progress against target (PR 1 + PR 2 shipped; PR 3 remains):

| Aspect | Was | Now |
|---|---|---|
| Journal session persistence | Writes `UserEntry` | ✅ **Zero** — process → return inline / `je_out/` file |
| File upload + transcription | Writes `UserEntry` (+ manual processing) | ✅ **Zero** — process → `je_out/` file (decision A) |
| Sync allowlist default | `periodic_notes/` only | ✅ `periodic_notes/`, `personal_notes/`, `activity_notes/`, `knowledge/`, `je_pro/` (conditional) |
| `je_raw/` | Unconditionally excluded, inert | ✅ **Disk-only** — read at processing time as few-shot exemplars; never ingested |
| `je_pro/` | Unconditionally excluded, inert | ✅ **Dual duty** (2026-07-11) — disk-only exemplar half AND frontmatter-gated understanding channel, scoped by `je_use:`; delete-on-narrow |
| Periodic notes | Stored + in-app editable | **Unchanged (kept)** |
| Model-feeding read (`get_vault_notes_for_context`) | Filters `pipeline='journal'` + `vault_file_path` | ✅ `pipeline='knowledge'` only (the `journal` value is gone, 2026-09-02); already excluded journal sessions |

**One Path Forward deletions** made by the code pass (machinery that existed only to serve
storage the design removes): the journal-session chat page (`/journals/{uid}` is now
periodic-notes-only), the recent-sessions landing + sidebar lists, the suggestions-cache-in-
metadata helpers, and `UserEntryService.submit_file`/`_store_file` (the bytes-to-disk +
entry-creation helper journals was the sole consumer of). Periodic-note machinery is retained.

**Sequenced code pass:** PR 1 ✅ (stateless text
sessions + expanded allowlist, the privacy win), PR 2 ✅ (upload/transcription), PR 3 ✅ (disk-only
exemplar processing; the #1 global / #2b per-user stored split remains PLANNED).

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
4. **Unconditional workshop exclusion** — `is_staging_path()` keeps every
   `je_in`/`je_out`/`je_raw` component out of ingestion regardless of allowlist configuration.
5. **je_pro consent gate** *(2026-07-11)* — a bare je_pro file is skipped (with a promotion
   hint), a `pipeline:`-consented one ingests, a `je_use: exemplar` one is skipped, and
   flipping a stored file to `je_use: exemplar` deletes its node on the next sync.

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
  in review (Kody, PR #477) and deferred, not dismissed. **The configuration mechanism for that
  per-user opt-in is settled in ADR-070 Decision 8: a vault-local marker file — never a global env
  var or config file (both dominated: unneeded now, wrong shape later; env is also silently
  shadow-prone).**
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
