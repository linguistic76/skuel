# Journals Discussion-First — Design & Choices

**Status:** Draft — fundamental workflow rulings settled with the founder 2026-07-12;
implementation choices below awaiting confirmation. This document is the arc's source of truth.
**Related:** ADR-073 (journals zero-persistence), ADR-076 (canon quotation & citation),
ADR-077 (scoped canon retrieval), `docs/roadmap/conversation-neo4j-persistence-deferred.md`
(deferred Askesis conversation storage — reuse candidate).

---

## Intent

Discussion is a fundamental part of the Journals domain — the concept of "journal" stretches
toward "discussion." A user can have a conversation without submitting any files: grounded in
what the app knows about them, the canon, and their vault, and led primarily by how *they*
lead the interaction. This requires more flexibility than the fixed scribe → thought-partner
workflow shapes.

## Settled fundamentals (founder rulings, 2026-07-12)

These are decided. The choices section below is about *how*, not *whether*.

1. **The user always initiates by typing.** There is no AI-opens-the-conversation affordance.
2. **Two doors in, the same sources behind both.** A session begins via chat (typed words) or
   via processing files (the historical default whenever files are involved). Canon, personal
   vault, and UserContext are available grounding in *both* doors.
3. **Sources are live from message one** in the chat door — not follow-up-only as today.
4. **One discussion experience, two ways in (convergence).** After entry, everything
   converges: one conversation surface, same composer, same source access. A processed file's
   content is simply part of what is on the table.
5. **Canon selection = the shelf as checkboxes.** The source panel lists every shelved book
   with a checkbox; the user composes the session's canon each time. (Chosen over
   whole-shelf-default and over the current boolean summon dial.)
6. **Real storage.** Discussions should be revisitable and continuable. This deliberately
   reopens the storage decision that ADR-073 and the deferred conversation-persistence design
   both parked — and it must be reconciled with ADR-073 by design, not erosion.

**Deliberately deferred** (founder: "details I want to refine as we progress"): how
processed-file content is *weighted* against canon/vault/UserContext; per-source default-on
states beyond the canon-checkbox ruling.

## Current state (verified against code 2026-07-12)

| Surface | Today |
|---|---|
| Chat door, first message | `POST /journals/respond` → `run_standard()` — UserContext digest only; **no canon/vault dials** |
| Chat door, follow-ups | `POST /journals/follow-up` → `run_follow_up()` — canon + vault dials (FOUNDER-gated server-side), quote-and-cite via `to_discussion_block()` |
| File door | `POST /journals/upload` → `run_compiled()` — **already carries both `summon_canon`/`summon_vault` form flags** |
| Canon scoping | `CanonRetrievalService.retrieve(resource_uids=...)` already supports restricting to specific books (built for Askesis, ADR-077 PR-A) — the checkbox picker has an existing seam |
| Vault grounding | `retrieve_vault()` (canon P3) — owner-scoped, private-gated, replaces the shallow note digest when it lands |
| UserContext | `_build_context_summary()` (goals/tasks/habits + vault-note snippets) baked into every prompt already |
| Conversation memory | **Client-side only**: hidden form fields (`original_entry`, `ai_response`) accumulated per turn via OOB swaps. Evaporates on reload. Zero Neo4j persistence (ADR-073) |
| Post-file discussion | Partially exists: `Stage3Fragment` carries a follow-up composer after DNWF completes |

Reading of the gap: rulings 2 and 4 are *mostly* wiring and UI (the seams exist); rulings 3
and 5 are a contained feature; ruling 6 is the substantial design work.

## Design choices

### C1 — Storage substrate

The deferred design `conversation-neo4j-persistence-deferred.md` (written for Askesis)
already specifies `:ConversationSession` / `:ConversationTurn` nodes, an owner-private
model, and a migration path from in-memory state. Its trigger condition — a user with real
sessions requesting cross-session memory — is exactly what the founder's ruling fires.

| Option | Shape | For | Against |
|---|---|---|---|
| **A. Neo4j sessions/turns (recommended)** | Adapt the deferred schema; one conversation-persistence capability shared by Journals and (later) Askesis | Queryable revisit list in-app; continue-thread reads the real history instead of a growing hidden form field; ONE design for both companions (build-on-the-stack); delete = detach-delete one session subtree | Amends ADR-073 (see C2); plaintext-at-rest until field-level encryption lands (same residual as doorway notes) |
| **B. Transcript `.md` files** | Each discussion saved as a markdown file; revisit = reload file | Honors "the vault is the only memory channel" literally; user-ownable artifact; markdown-first | ADR-073 makes `je_out/` **write-only, never read back** — a read-back folder is a new folder class with its own consent story, not a smaller change than A; no in-app list/continue without scanning disk; multi-user story is worse (flat-folder residuals already flagged in ADR-073) |
| **C. Server-side session memory only** | Discussion survives navigation within a login session; gone on restart | No ADR tension; cheap | Does not deliver revisit-past-chats or continue-later — fails the ruling; rejected unless as a stopgap phase |

**Recommendation: A**, with an explicit per-session **export to `.md`** action (the artifact
pattern users already have) so B's ownership virtue is kept without making files the system
of record.

### C2 — The privacy wall under storage (the ADR-073 reconciliation)

ADR-073 makes two commitments that are separable:

1. **Zero persistence** of journal sessions (the transcript doesn't exist afterward).
2. **Zero understanding** — journaling never feeds SKUEL's model of the user; the vault
   doorway is the only channel into understanding.

The founder's ruling relaxes (1) for discussions. It does **not** touch (2). Proposed
reconciliation, to be written as an ADR-073 amendment (or a sibling ADR) when confirmed:

- Discussion sessions/turns persist, **owner-private**, for exactly two purposes: revisit and
  continue.
- **Stored ≠ understood.** Discussion content never reaches `_build_context_summary`,
  UserContext, embeddings, search (`SearchRouter` never sees the labels), ZPD, or any
  intelligence surface. No `MENTIONS`/enrichment edges in phase 1 — the deferred schema's
  ZPD/teacher integrations are Askesis-era ideas, explicitly out of scope here.
- **Delete is first-class**: per-session delete, and the testability bar extends —
  "stores zero" becomes "stores only sessions the user can see and delete; understanding
  paths provably read nothing from them."
- The workshop file taxonomy (`je_in`/`je_out`/`je_raw`) is untouched.
- At-rest encryption of turn content joins the existing field-level-encryption plan
  (doorway notes have the same residual today).

### C3 — Shelf checkboxes

Replace the boolean `summon_canon` dial with a shelf panel: one checkbox per shelved book
(shelf membership = "chunked = on the shelf", unchanged), wired through the existing
`resource_uids` parameter. Checked-none = no canon (today's dial-off); checked-some = scoped
retrieval (the exact-cosine scoped branch already built for Askesis); checked-all =
whole-shelf (today's dial-on).

**Open sub-choice:** initial checkbox state. Proposed: all unchecked (deliberate grounding,
matches the founder's most-explicit ruling); once storage (C1) exists, a continued session
restores its own last selection. Per-user sticky defaults are a later refinement.

The vault dial stays a single toggle (it is one corpus), placed in the same source panel.

### C4 — Sources on the first message

Thread the source panel (shelf checkboxes + vault toggle) into the initial composer and
through `/journals/respond` → `run_standard()` (and the FOUNDER `/journals/start` staged
path, whose Stage 2/3 already accept the flags). UserContext stays always-on as today — it
is what makes the companion *theirs*, is ADR-073-clean (ephemeral prompt context), and the
founder's original intent names it ("what the app knows about me"). FOUNDER server-side
gating of canon/vault follows the existing follow-up pattern.

### C5 — Discussion voice

The scribe/thought-partner/what-is-related shapes are *processing* templates; a discussion
led by the user needs a lighter frame. `follow_up_system_prompt()` (continuation directive,
no forced headings) is already close. Proposed: a first-message discussion prompt in the
same family — companion voice, user leads, no imposed structure — rather than routing the
first message through a `JournalMode` template. Whether this is a new `JournalMode` value or
a distinct instruction file is an implementation detail for the PR; the concept is "the
existing modes become tools the discussion can invoke, not the frame."

### C6 — Convergence mechanics

With storage (C1), both doors create a session: the chat door on first send; the file door
when processing completes (the compiled output becomes the session's opening context, as the
`Stage3Fragment` follow-up composer already sketches). One conversation surface renders
either. File-content weighting inside the prompt is the deferred refinement — phase 1 simply
includes the processed output as context, as the follow-up path does today.

## Phasing

| Phase | Delivers | Depends on |
|---|---|---|
| **P1 — sources from message one** | Source panel (shelf checkboxes via `resource_uids` + vault toggle) on the initial composer; first-message discussion voice (C3, C4, C5) | Nothing — all seams exist; no storage |
| **P2 — real storage** | ADR-073 amendment/sibling ADR (C2) written and confirmed FIRST, then sessions/turns, revisit list, continue-thread (replacing the hidden-field accumulator), delete, export-to-md (C1) | P1 useful but not required |
| **P3 — convergence & refinement** | File door creates sessions (C6); remembered source selections; file weighting; relevance tuning | P2 |

P1 is independently valuable and small. P2 is where the ADR work lives — doc-first, per the
canon-arc precedent.

## Out of scope / rejected

- **AI-initiated openings** — rejected by the founder; the user always types first.
- **Model-feeding from discussions** (embeddings, UserContext, ZPD, MENTIONS edges) — the
  understanding wall holds; the vault doorway remains the only channel.
- **Teacher visibility / sharing of discussions** — Askesis-era idea in the deferred doc;
  not part of this arc.
- **Auto-summon heuristics** — `_maybe_summon_canon` stays the single seam; graduation
  remains a later, separate decision.
