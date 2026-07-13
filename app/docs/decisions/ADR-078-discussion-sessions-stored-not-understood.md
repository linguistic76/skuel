# ADR-078: Discussion Sessions Are Stored but Never Understood

**Status:** Accepted (design) — storage/route/service code NOT yet written; this ADR is the
doc-first gate for P2 of the journals discussion-first arc. Founder confirmation pending.
**Date:** 2026-07-12
**Amends:** ADR-073 §1 and §3 (see *Relationship to ADR-073* below) — the "zero persistence"
commitment is narrowed to carve exactly one exception: owner-private discussion sessions.
**Related:** ADR-073 (journals zero-persistence + vault-as-only-memory-channel), ADR-042
(privacy as a first-class citizen / field-level encryption), ADR-054 (UserEntry collapse),
ADR-069 (EXTRACT_ACTIVITIES pipeline), ADR-077 (canon scoped retrieval),
`docs/roadmap/journals-discussion-first.md` (arc source of truth, choices C1/C2/C6),
`docs/roadmap/conversation-neo4j-persistence-deferred.md` (the deferred Askesis schema this
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
purposes**: *revisit* a past discussion and *continue* it. Nothing more. Every other property
of ADR-073 holds unchanged — the workshop file taxonomy (`je_in`/`je_out`/`je_raw`), the
`je_pro` conditional doorway, periodic notes, and above all the understanding wall.

This is the whole exception. The rest of this ADR is about making "nothing more" provable.

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

Adapted from the deferred design, reduced to what revisit + continue require. Multi-label
follows the universal pattern (`:Entity` + domain label) only if these are ever routed through
`UniversalNeo4jBackend`; if a dedicated thin backend is used they may carry the domain label
alone — an implementation choice for the storage PR, **provided the SearchRouter non-
registration in §2 holds regardless**.

```cypher
(:ConversationSession {
    session_id:    string,     // UUID
    user_uid:      string,     // owner FK — the ONLY access key
    started_at:    datetime,
    last_activity: datetime,
    state:         string,     // "active" | "completed"
    title:         string,     // user-facing label for the revisit list (user-set or
                               //   first-message-derived — NOT an LLM understanding summary)
    turn_count:    integer,
    source_selection: string   // JSON: the canon shelf checkboxes + vault toggle used, so a
                               //   continued session restores its own last selection (C3)
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
(:User)-[:HAS_DISCUSSION {started_at: datetime}]->(:ConversationSession)
(:ConversationSession)-[:HAS_TURN {turn_number: integer}]->(:ConversationTurn)
```

**Deliberately dropped from the deferred schema:** `guidance_mode`, `anchor_ku_uid`,
`ANCHORED_TO`, `topic_summary` (LLM), `ku_refs`, `MENTIONS`, `MONITORS`. Each is an
understanding or teacher-sharing hook (commitment 2 / rejected scope). A distinct edge name
`HAS_DISCUSSION` (not the deferred `HAS_SESSION`) keeps discussion sessions grep-distinct from
any future Askesis conversation store and prevents an accidental shared traversal.

The existing in-memory `ConversationSession` / `ConversationTurn` dataclasses
(`core/models/user/conversation.py`, used today by Askesis, not journals) carry pedagogical and
extraction fields. The persisted journals shape maps only the identity + transcript subset
above; the pedagogical fields are **not** persisted.

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

### 5. Migration off the client-side accumulator

Today's memory lives in hidden form fields (`original_entry`, `ai_response`) accumulated via
OOB swaps. The storage PR replaces this substrate:

1. First user send in the chat door **creates** a `:ConversationSession` and its first
   user/assistant `:ConversationTurn` pair.
2. Each subsequent turn **appends** `:ConversationTurn` nodes; the composer no longer needs to
   carry the full transcript in hidden fields — it carries only the `session_id`.
3. Continue-thread reads history from Neo4j instead of a growing hidden field.

This is a One-Path-Forward replacement: the hidden-field accumulator is **removed**, not kept
as a fallback. There is no legacy dual-write. (The file door creating sessions on
processing-complete is **P3/C6**, not this ADR.)

### 6. At-rest encryption joins the existing plan

`:ConversationTurn.content` is plaintext at rest in Neo4j — the **same residual** doorway notes
and periodic notes already carry (ADR-073 residual gap; ADR-042 field-level-encryption phase).
Discussion turn content is added to that field-level-encryption backlog; it does **not** get a
bespoke encryption scheme. Until that phase lands, operator-level DB access can read discussion
turns exactly as it can read doorway notes today — a known, documented residual, not a
regression introduced here.

### 7. Testability — the bar shifts from "stores zero" to "stores only the visible, deletable, un-understood"

ADR-073's provable contract was "stores zero / reads zero." For discussions, "stores zero" is
no longer the claim; the claim is narrower and still fully provable. The storage PR must ship
these guard tests:

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

Tests 3–6 are the operational form of "stored ≠ understood": the understanding paths provably
read nothing from the discussion store.

### 8. Export to `.md` (design note)

C1's recommendation keeps B's ownership virtue via an explicit **per-session export to `.md`**
action: a user can export any owned discussion to a markdown transcript they keep wherever they
choose (the artifact pattern they already have from `je_out/`). Neo4j remains the system of
record for in-app revisit/continue; the `.md` export is a user-ownable copy, not a read-back
folder class (which ADR-073 deliberately does not have). Export is a **design note here**, small
enough to land in the storage PR or a fast follow — not a separate arc.

## Relationship to ADR-073

This ADR **amends ADR-073 §1 (Two channels) and §3 (Persistence rules)** with a single
carve-out. ADR-073's wording changes from an unqualified "the journal never writes to SKUEL's
model of the user and **never persists**" to:

> The journal never writes to SKUEL's model of the user. It persists **nothing except
> owner-private discussion sessions (ADR-078)** — which are stored for revisit/continue only and
> are, by the same guarantee, *never understood*: they reach no context builder, embedding,
> search, or intelligence surface.

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
  reopening the understanding wall; ONE conversation-persistence shape now exists that Askesis
  can later adopt (build-on-the-stack); the client-side hidden-field accumulator — fragile,
  reload-lossy — is deleted (One Path Forward); the privacy contract stays *testable*, just
  along a shifted axis.
- **Cost:** ADR-073's headline "zero-persistence" is now qualified — the honesty is preserved by
  making the exception explicit and narrow, but the one-sentence pitch is longer.
- **Residual (plaintext at rest):** discussion turn content is plaintext in Neo4j until the
  ADR-042 field-level-encryption phase lands — the same residual as doorway/periodic notes, not
  a new class of exposure.
- **Residual (multi-tenant):** owner-private is enforced by `user_uid` ownership + 404-not-403,
  the same model the rest of SKUEL uses; no new trust-boundary default is introduced. A future
  hosted deployment inherits the same per-user-vault considerations already flagged in ADR-073,
  nothing more.
