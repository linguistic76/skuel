---
updated: 2026-08-21
---

# ADR-078: Discussion Sessions Are Stored but Never Understood

**Status:** Accepted — **founder-confirmed 2026-07-13** ("I confirm I abide by the ADR").
Storage/route/service code NOT yet written; this ADR was the doc-first gate for P2 of the
journals discussion-first arc, and the gate is now cleared — the storage-implementation PRs
are unblocked and must be built to the shape decided here.
**Date:** 2026-07-12
**Amended 2026-07-13 (§3 + new *Learning from Askesis* section):** founder ruled "neutral seams,
journals-only build." Backend placement resolved (dedicated thin `ConversationBackend`, NOT the
universal Entity path); the ownership edge is the **neutral `HAS_SESSION`** (not `HAS_DISCUSSION`)
and the session carries a **`kind`** discriminator, so Askesis can adopt one shared store later.
Grounded in a study of how Askesis persists conversations today — see the new section.
**Amended 2026-07-13 (§3/§6, self-consistency):** dropped `state` (no writer — the exact
vestigial-field trap this ADR criticizes) and de-stored `turn_count` (derived by `COUNT`-ing
`HAS_TURN`, not denormalized); and made §6 honest that freeform discussion is *more* sensitive
than a curated doorway note (same encryption mechanism, but a candidate to prioritize first).
**Amended 2026-07-13 (§1 + §5 + §7, founder realignment — persistence is OPT-IN, not automatic):**
the founder re-established the blunt Journals privacy rule that recent work had blurred. A
discussion is **ephemeral by default** (zero persistence, exactly as ADR-073) and is stored
**only when the user explicitly chooses to save it**. This reverses the *implemented* auto-save
(P2 created a session on the first reply) and reverses §5's original "the accumulator is
removed": the client-side accumulator is **retained** as the ephemeral-default substrate; a
`:ConversationSession` is created only by an explicit *Save this chat* action. The rationale is
not only privacy but **signal vs noise** — saving everything forces later weight-sorting of
noise, whereas saving only what the user deliberately keeps yields a high-signal corpus by
construction. The understanding wall (§2) is unchanged: a saved chat is still never understood.
**Amends:** ADR-073 §1 and §3 (see *Relationship to ADR-073* below) — the "zero persistence"
commitment is narrowed to carve exactly one exception: owner-private discussion sessions **the
user chose to save**.
**Related:** ADR-073 (journals zero-persistence + vault-as-only-memory-channel), ADR-042
(privacy as a first-class citizen / field-level encryption), ADR-054 (UserEntry collapse),
ADR-069 (EXTRACT_ACTIVITIES pipeline), ADR-077 (canon scoped retrieval),
`docs/roadmap/done/journals-discussion-first.md` (arc source of truth, choices C1/C2/C6),
`docs/roadmap/done/conversation-neo4j-persistence-deferred.md` (the deferred Askesis schema this
adapts).

---

## Context

The journals discussion-first arc (P1 shipped in #627) established discussion as a
fundamental part of the Journals domain: a user can converse with a companion grounded in the
canon, their private vault, and what the app already knows about them, led primarily by how
*they* lead. The founder ruled (roadmap ruling 6) that **discussions should be revisitable and
continuable** — which requires real storage.

Today a discussion persists nothing. `run_discussion` / `run_follow_up`
(`core/services/journal/journal_service.py`) return an ephemeral `JournalFollowUp`, and
conversation "memory" is a client-side accumulator: hidden form fields (`original_entry`,
`ai_response`) grown per turn via HTMX OOB swaps, gone on reload. This satisfies ADR-073's
zero-persistence contract literally, but it cannot deliver revisit or continue: there is
nothing to come back to.

Storing discussions collides head-on with ADR-073, whose title is literally *"Journals Are a
**Zero-Persistence** Private Workshop."* The collision is real and must be resolved **by
design, not by erosion** (roadmap C2). The key observation is that ADR-073 bundles two
commitments that are in fact **separable**:

1. **Zero persistence** — the transcript does not exist after the session ends.
2. **Zero understanding** — journaling never feeds SKUEL's model of the user; the vault
   doorway is the *only* channel into understanding.

The founder's ruling relaxes **(1)** for discussions only. It leaves **(2)** completely
untouched. This ADR names, bounds, and makes testable that single relaxation.

### Why a sibling ADR rather than an inline ADR-073 amendment

The je_pro doorway (ADR-073 amendment, 2026-07-11, #608) was a *refinement within the existing
frame*: it stayed on the "understanding via deliberate placement" axis and only adjusted which
placements count. Discussion storage is a **new conceptual quadrant** ADR-073 never modeled —
*persisted **and** deliberately excluded from understanding*. It also carries an ADR's worth of
independent decision surface: a Neo4j schema, a backend, an owner-private access model, a
migration off the client-side accumulator, an export action, and a shifted testability bar.

Folding all of that inline would either bury it or quietly turn ADR-073's "zero-persistence"
title into a falsehood. Instead this sibling ADR owns the exception in full and **amends
ADR-073 with a one-line carve-out + forward pointer**, keeping ADR-073 honest: zero persistence
*except* owner-private discussion sessions, which persist but are never understood.

## Decision

### 1. One narrow exception, precisely bounded

Discussion sessions and their turns persist to Neo4j, **owner-private**, for **exactly two
purposes**: *revisit* a past discussion and *continue* it. Nothing more — and **only when the
user explicitly chooses to save the discussion.** Persistence is **opt-in, never automatic**: by
default a discussion is ephemeral (zero persistence, exactly as ADR-073), living only in the
browser for the active session and gone on reload. A `:ConversationSession` exists *only*
because the user pressed *Save this chat*. This is the chat analogue of the `je_pro` doorway —
sharing/keeping is always a deliberate gesture, never a side effect. Every other property of
ADR-073 holds unchanged — the workshop file taxonomy (`je_in`/`je_out`/`je_raw`), the `je_pro`
conditional doorway, periodic notes, and above all the understanding wall.

This is the whole exception. The rest of this ADR is about making "nothing more" provable.

**Why opt-in, not automatic (the founder's realignment, 2026-07-13).** Two reasons, both blunt
on purpose. *Privacy:* the Journals domain is private by default; auto-saving every chat silently
eroded that. *Signal vs noise:* saving everything forces the app to later sort relevance by
weights — an unbounded noise problem — whereas saving only what the user deliberately keeps
produces a high-signal corpus for free. Bluntness (a clear save / don't-save line) is a feature:
it keeps both the privacy contract and the code simple.

### 2. Stored ≠ understood (the wall this ADR must not breach)

Persisting discussion content must not create a second channel into SKUEL's model of the user.
The **only** channel into understanding remains the vault doorway (ADR-073 §2). Concretely,
discussion sessions/turns are **forbidden** from reaching any of:

| Surface | Guarantee |
|---|---|
| `_build_context_summary()` / UserContext | Never reads discussion nodes. The prompt-context builder is fed by `get_vault_notes_for_context()` (doorway/periodic only) — discussion labels are not a source. |
| Embeddings | No `*EmbeddingRequested` event is published for `:ConversationSession`/`:ConversationTurn`. They carry no vector and are invisible to vector search (ADR-074). |
| `SearchRouter` | The new labels are **not** registered as searchable domains. Cross-domain sweeps and every strategy (text/tags/graph/faceted) never see them. |
| ZPD / intelligence | No signal, no "explored KUs", no current-zone contribution. Phase 1 writes **no `MENTIONS` / enrichment / `APPLIES_KNOWLEDGE` edges** from turns to any `:Entity`. |
| Activity/entity creation | A discussion never creates a domain entity. That path stays exclusively EXTRACT_ACTIVITIES through a doorway folder (ADR-069). |

The deferred Askesis schema (`conversation-neo4j-persistence-deferred.md`) explicitly modeled
`(:ConversationTurn)-[:MENTIONS]->(:Entity)`, an `anchor_ku_uid` / `ANCHORED_TO` curriculum
link, LLM `topic_summary`, ZPD "explored KUs" reads, and teacher `MONITORS` visibility. **All
of these are stripped.** They are Askesis-era understanding features; importing them would
breach commitment (2). See *Out of scope / rejected* for the itemized list.

### 3. Schema — `:ConversationSession` / `:ConversationTurn` (adapted, stripped)

Adapted from the deferred design, reduced to what revisit + continue require.

**Backend placement — RESOLVED *(2026-07-13)*: a dedicated thin `ConversationBackend`, NOT the
universal Entity path.** `:ConversationSession`/`:ConversationTurn` are **not** `:Entity` nodes
and are **not** one of the 25 EntityTypes; they follow the thin-backend precedent of
**`SessionBackend` / `DeviceBackend`** — standalone classes (no superclass) that take the shared
`AsyncDriver` and run owner-scoped Cypher via `driver.session()`. *(The original draft cited Group
here, but `GroupBackend` in fact subclasses `UniversalNeo4jBackend` — the exact universal path §3
says to avoid; `Session`/`Device` are the faithful precedent that delivers the structural wall.)*
This is not merely a placement preference — routing them through `UniversalNeo4jBackend` would
auto-wire the search + embedding machinery that §2 **forbids**. The thin backend keeps the
understanding wall structural (the nodes are never in the universal path to begin with), not just
policy. They carry the domain label alone.

```cypher
(:ConversationSession {
    session_id:    string,     // UUID
    user_uid:      string,     // owner FK — the ONLY access key
    kind:          string,     // companion discriminator — "discussion" (journals). The seam
                               //   that lets Askesis adopt this store later without a rewrite
                               //   (its rows would carry a different kind). Journals writes only
                               //   "discussion"; nothing else reads/branches on kind in phase 1.
    started_at:    datetime,
    last_activity: datetime,   // touched on each appended turn; the revisit list orders by it
    title:         string,     // user-facing label for the revisit list (user-set or
                               //   first-message-derived — NOT an LLM understanding summary)
    source_selection: string,  // JSON: the canon shelf checkboxes + vault toggle used, so a
                               //   continued session restores its own last selection (C3)
    model:         string      // the per-conversation LLM choice (the switcher), so a continued
                               //   session resumes on the model it last used (last-write-wins).
                               //   A pre-switcher session with no stored model reads back as the
                               //   app-safe default (normalized in the backend, not stored null)
})

(:ConversationTurn {
    turn_id:     string,       // UUID
    session_id:  string,       // FK to session
    role:        string,       // "user" | "assistant"
    content:     string,       // message text — plaintext at rest until §6 encryption lands
    timestamp:   datetime,
    turn_number: integer       // ordinal within session
})
```

**Relationships — two, both owner-private:**

```cypher
(:User)-[:HAS_SESSION {started_at: datetime}]->(:ConversationSession)
(:ConversationSession)-[:HAS_TURN {turn_number: integer}]->(:ConversationTurn)
```

**Deliberately dropped from the deferred schema:** `guidance_mode`, `anchor_ku_uid`,
`ANCHORED_TO`, `topic_summary` (LLM), `ku_refs`, `MENTIONS`, `MONITORS`. Each is an
understanding or teacher-sharing hook (commitment 2 / rejected scope).

**Also dropped — `state` and `turn_count` *(amended 2026-07-13, self-consistency fix)*.** The
first draft carried `state: "active" | "completed"` and a stored `turn_count`. Both are cut: this
ADR argues at length that Askesis rotted because it kept fields with no live reader/writer, so it
must not do the same. Nothing in the revisit/continue flow **transitions** a session to
"completed" — every session is simply the user's owned history, resumable until deleted — so
`state` has no writer and is exactly the vestigial trap. `turn_count` is a denormalization of what
`HAS_TURN` already encodes and drifts on every append (Askesis's own `add_turn` bug shape); it is
**derived** (`COUNT` the `HAS_TURN` edges) at read time, not stored. If a future need for an
explicit lifecycle state or a cached count appears, add it **then, with its writer** — not
speculatively now.

**Edge naming — neutral `HAS_SESSION`, not `HAS_DISCUSSION` *(amended 2026-07-13)*.** The
ownership edge is deliberately companion-neutral so a single conversation-persistence store can
be shared later. Journals-vs-Askesis separation is carried by the `kind` **property**, not by a
journals-specific edge label — the understanding wall (§2) is enforced by SearchRouter/embedding
non-registration and the guard tests (§7), not by edge-name obscurity. (This reverses the
original ADR text, which chose a distinct `HAS_DISCUSSION` for grep-distinctness; the founder's
"neutral seams" ruling makes shared-adoptability the higher-value property.)

**Do NOT reuse the in-memory model.** The existing in-memory `ConversationSession` /
`ConversationTurn` dataclasses (`core/models/user/conversation.py`, used today by Askesis, not
journals) carry ~40 fields of pedagogical / search / analytics state. The *Learning from Askesis*
section below documents that ~35 of them are vestigial even in Askesis. The storage PR builds
**new minimal frozen models** mapping only the identity + transcript subset above; the
pedagogical fields are not persisted and not modeled.

### 4. Access model — owner-private, delete first-class

- **Owner-only, every path.** Read, list, continue, and delete are all keyed on
  `user_uid == session owner`. A session the user does not own returns **404, not 403**
  (SKUEL ownership convention). No sharing, no group scope, no admin read (see rejected scope).
- **Delete is a first-class, per-session action.** Deleting a session detaches-and-deletes its
  whole subtree (`DETACH DELETE` the session + all its `:ConversationTurn` nodes). The user can
  see every session they own and delete any of them — this is the load-bearing half of the new
  testability bar (§7).
- **Revisit list** = the user's own `:ConversationSession` nodes, most-recent first, showing
  `title` + `last_activity`. **Continue** reads the ordered `:ConversationTurn` history for one
  owned session and rehydrates the composer — replacing the client-side hidden-field
  accumulator as the source of conversation memory.

### 5. The client-side accumulator is retained (ephemeral default); *Save* promotes to a session

*(Revised 2026-07-13 — this reverses the original "remove the accumulator" text, which assumed
auto-save. Persistence is opt-in per §1.)*

Active, unsaved conversation memory lives where it always did: hidden form fields
(`original_entry` / `ai_response`) accumulated via OOB swaps. This is the **ephemeral default** —
it dies on reload, which is exactly what "not saved" means. It is **not** removed; it is the
substrate for every discussion until (and unless) the user saves.

**Save this chat** is the single, explicit persistence gesture. It promotes the current
ephemeral transcript into an owner-private `:ConversationSession` + its `:ConversationTurn`
pairs (the store defined in §3). After saving, the discussion is session-backed: further turns
append to the saved session, and it appears in the revisit list. An unsaved discussion creates
**zero** `:ConversationSession` nodes.

There is no auto-create and no dual-write: a chat is either ephemeral (accumulator only) or
saved (session-backed), and the transition happens exactly once, by explicit user action.
**P2 shipped the wrong default** — an automatic create-on-first-reply, and it removed the typed
door's accumulator. **P3 corrects both**: it restores the ephemeral default on the typed door
and adds the *Save this chat* action to both the typed and file/audio doors. (The file/audio
door joining the store — **P3/C6** — was always deferred past this ADR.)

### 6. At-rest encryption joins the existing plan

`:ConversationTurn.content` is plaintext at rest in Neo4j — the **same mechanism** of residual
doorway notes and periodic notes already carry (ADR-073 residual gap; ADR-042 field-level-
encryption phase). It does **not** get a bespoke encryption scheme; discussion turn content joins
that one field-level-encryption backlog. But the *sensitivity* is not equivalent: a doorway note
is a deliberate, curated artifact, whereas a freeform discussion is more intimate and less
considered — so discussion turns are a **candidate to prioritize first** within the ADR-042 work,
not merely lumped in. Until that phase lands, operator-level DB access can read discussion turns
exactly as it can read doorway notes today — a known, documented residual, not a regression
introduced here.

### 7. Testability — the bar shifts from "stores zero" to "stores only the visible, deletable, un-understood"

ADR-073's provable contract was "stores zero / reads zero." For discussions, "stores zero" is
no longer the *unconditional* claim — but it remains the **default**: persistence is the
exception, gated on an explicit save (guard 7). The claim is narrower and still fully provable.
The storage PR must ship these guard tests:

1. **Owner-visibility symmetry** — every `:ConversationSession` a user owns appears in that
   user's revisit list; a session owned by another user is invisible and its direct fetch
   returns 404. (Stores *only* sessions the user can see.)
2. **Delete completeness** — per-session delete removes the `:ConversationSession` **and** all
   its `:ConversationTurn` nodes (no orphaned turns); the session vanishes from the revisit
   list. (Everything stored is deletable.)
3. **Understanding-wall: context builder** — `get_vault_notes_for_context()` /
   `_build_context_summary()` return nothing sourced from a `:ConversationSession` or
   `:ConversationTurn`, even after discussions exist. (The ADR-073 test 2 invariant, re-asserted
   against the new nodes.)
4. **Understanding-wall: no embeddings** — creating a discussion session/turn publishes **no**
   `*EmbeddingRequested` event; the nodes carry no embedding property. (Provably invisible to
   vector search.)
5. **Understanding-wall: search invisibility** — a `SearchRouter` sweep (all strategies, all
   domains) never returns a `:ConversationSession`/`:ConversationTurn`; the labels are not
   registered as a searchable domain.
6. **No enrichment edges** — creating/continuing a discussion writes **zero** `MENTIONS` /
   enrichment / `APPLIES_KNOWLEDGE` edges from turns to any `:Entity`.
7. **Opt-in persistence** *(added 2026-07-13)* — an unsaved discussion (the user never pressed
   *Save this chat*) creates **zero** `:ConversationSession` / `:ConversationTurn` nodes. A
   session exists only after the explicit save action. This is the load-bearing "not saved by
   default" guard: it fails loudly if any door ever auto-creates a session again (the exact P2
   regression this amendment corrects).

Tests 3–6 are the operational form of "stored ≠ understood": the understanding paths provably
read nothing from the discussion store. Test 7 is the operational form of "not saved by
default": nothing reaches the store without a deliberate save.

### 8. Export to `.md` (design note)

C1's recommendation keeps B's ownership virtue via an explicit **per-session export to `.md`**
action: a user can export any owned discussion to a markdown transcript they keep wherever they
choose (the artifact pattern they already have from `je_out/`). Neo4j remains the system of
record for in-app revisit/continue; the `.md` export is a user-ownable copy, not a read-back
folder class (which ADR-073 deliberately does not have). Export is a **design note here**, small
enough to land in the storage PR or a fast follow — not a separate arc.

## Learning from Askesis (design evidence, 2026-07-13)

Before committing the storage shape, we studied how Askesis — the one component already running
the in-memory `ConversationSession`/`ConversationTurn` model — persists conversations today. The
finding shaped every decision above, and it is a **cautionary tale, not a template**: Askesis has
**three incoherent, half-built conversation representations** and none delivers revisit/continue.

| Representation | Where | Reality (verified) |
|---|---|---|
| In-memory `ConversationSession`/`Turn`/`Context` | `core/models/user/conversation.py` | ~40 fields, but only **5 load-bearing** (`session_id`, `user_uid`, `turns`, `turn_count`, `last_activity`) + `to_llm_messages()`. All pedagogical/search/analytics fields are written-never-read or never-written. Evaporates on process restart. |
| Deferred `:ConversationSession`/`:Turn` schema | `conversation-neo4j-persistence-deferred.md` | Never built. |
| Shipped `:ConversationMessage` + `(:User)-[:HAS_MESSAGE]->` | `user_backend.py:1021` (`add_conversation_message`) | **Write-only — verified zero read-back at any layer** (create exists at backend/service/port; no `MATCH` reads it anywhere). Fire-and-forget async write. **Flat — no session grouping.** So a restart wipes "persisted" history, and there is no unit to list or delete. |

**What this proves, mapped to the decisions above:**

- **Don't reuse the in-memory model** (§3) — Askesis leaves ~35 of its 40 fields vestigial;
  reusing it would import that dead weight. New minimal frozen models instead.
- **Journals must build the read-back Askesis never did** — revisit/continue *is* read-back; the
  write is the feature, so it is **awaited** in the `Result` chain, not fire-and-forget.
- **A parent `:ConversationSession` node is required** (§3) — the flat `:ConversationMessage`
  shape structurally cannot do a revisit-list or a per-session `DETACH DELETE` (§4).
- **Don't port the dead lifecycle** — `cleanup_inactive_sessions` / `should_summarize` /
  timeout are all defined-never-called in Askesis; journals sessions are durable + user-deleted.

**The reconciliation that makes a *shared* store possible (why the seams are neutral).** Journals
and Askesis have **opposite** relationships to understanding: an Askesis conversation is *meant*
to feed the learner model (ZPD, explored-KUs — the deferred doc's entire purpose); a journal
discussion is *forbidden* from it (§2). This is not a conflict — it is the constraint that makes
one store viable: **the storage layer must be understanding-agnostic.** It persists sessions and
turns and nothing else; all understanding wiring (embeddings, `MENTIONS`, ZPD reads) lives
*above* the store, opt-in per consumer. Journals opts out entirely (the wall); a future Askesis
adoption opts in. This independently re-confirms the stripped schema (§2/§3): Askesis is the
evidence that `guidance_mode`/`anchor_ku_uid`/`topic_summary` go vestigial even for their
intended owner, so they do not belong in a shared node.

**Scope ruling (founder, 2026-07-13): neutral seams, journals-only build.** The storage PR builds
the thin `ConversationBackend` + minimal models **for journals only**, but with a companion-
neutral shape (`kind` discriminator, neutral `HAS_SESSION` edge, understanding-agnostic node) so
Askesis *can* adopt one shared store later. **Askesis is not touched in this arc** — its
write-only `:ConversationMessage` path and the vestigial in-memory container stay until a
separate, consented migration (its own arc, its own confirmation, since it also has to design the
opt-*in* understanding wiring journals refuses). Consolidating the three representations is the
prize; this arc lays the one real foundation without over-reaching into a second consumer.

## Relationship to ADR-073

This ADR **amends ADR-073 §1 (Two channels) and §3 (Persistence rules)** with a single
carve-out. ADR-073's wording changes from an unqualified "the journal never writes to SKUEL's
model of the user and **never persists**" to:

> The journal never writes to SKUEL's model of the user. It persists **nothing except
> owner-private discussion sessions the user explicitly chose to save (ADR-078)** — stored for
> revisit/continue only, never automatically, and, by the same guarantee, *never understood*:
> they reach no context builder, embedding, search, or intelligence surface.

Commitment (2) — zero understanding, vault-doorway-only — is **unchanged and reinforced**.
ADR-073 receives a matching forward-pointer amendment note (dated 2026-07-12).

## Out of scope / rejected

Recorded as explicitly rejected for phase 1 (each would breach commitment 2 or the founder's
rulings):

- **Model-feeding from discussions** — no embeddings, no UserContext contribution, no ZPD
  signal, no `MENTIONS`/enrichment edges. The understanding wall holds; the vault doorway
  remains the only channel in. *(Roadmap "Out of scope"; ADR-073 commitment 2.)*
- **Teacher visibility / sharing of discussions** — the deferred schema's
  `(:User)-[:MONITORS]->(:ConversationSession)` and topic-summary teacher view are **not**
  imported. Discussions are owner-private, full stop.
- **Auto-summon heuristics** — `_maybe_summon_canon` stays the single seam; automatic
  source-summoning graduation remains a later, separate decision.
- **LLM `topic_summary` / `anchor_ku_uid` / curriculum anchoring** — dropped from the schema;
  they are understanding-derived metadata.
- **AI-initiated openings** — the user always types first (founder ruling 1); no schema or
  route affordance for an AI-opened session.

## Consequences

- **Positive:** discussions become revisitable and continuable (the founder's ruling) without
  reopening the understanding wall **and without eroding the "private by default" contract** —
  persistence is opt-in; ONE conversation-persistence shape now exists that Askesis can later
  adopt (build-on-the-stack); the client-side hidden-field accumulator is **retained as the
  deliberate ephemeral default** (reload-lossy is the point — "not saved" means not saved), and
  a chat is persisted only by an explicit *Save* gesture; the privacy contract stays *testable*
  along both axes (never-understood **and** not-saved-by-default).
- **Cost:** ADR-073's headline "zero-persistence" is now qualified — the honesty is preserved by
  making the exception explicit and narrow, but the one-sentence pitch is longer.
- **Residual (plaintext at rest):** discussion turn content is plaintext in Neo4j until the
  ADR-042 field-level-encryption phase lands — the same *mechanism* as doorway/periodic notes (not
  a new class of exposure), though freeform discussion is more sensitive than a curated note, so it
  is a candidate to prioritize first in that work (§6).
- **Residual (multi-tenant):** owner-private is enforced by `user_uid` ownership + 404-not-403,
  the same model the rest of SKUEL uses; no new trust-boundary default is introduced. A future
  hosted deployment inherits the same per-user-vault considerations already flagged in ADR-073,
  nothing more.
