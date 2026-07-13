# P2 Storage Implementation — Journals Discussion Sessions

**Contract for the storage-implementation arc.** Founder-confirmed ADR-078 (2026-07-13) is the
gate — now cleared (PR #631). This plan translates ADR-078 into a concrete, PR-sequenced build.

- **SoT:** `docs/roadmap/journals-discussion-first.md` (choices C1/C2/C6)
- **Governing ADR:** `docs/decisions/ADR-078-discussion-sessions-stored-not-understood.md` — **the
  binding shape.** If this plan and ADR-078 ever disagree, ADR-078 wins.
- **Amends:** ADR-073 §1/§3 (already noted in-repo)
- **Memory:** [[project_journals_discussion_arc]], [[project_journal_privacy_commitment]]

---

## The one-sentence job

Persist discussion sessions + turns to Neo4j — **owner-private, for revisit + continue only** —
in an **understanding-agnostic** store the understanding paths provably never read, replacing
today's reload-lossy client-side hidden-field accumulator.

---

## Architecture — resolved decisions (do not re-litigate)

These are settled by ADR-078 + code investigation. Build to them.

### 1. Thin standalone backend — mirror `SessionBackend`/`UserBackend`, NOT `GroupBackend`

ADR-078 §3 cites "the Group thin-backend precedent," but investigation shows `GroupBackend`
**subclasses `UniversalNeo4jBackend`** — the exact universal Entity path §3 says to avoid. The
faithful precedent (delivers the structural wall) is **`SessionBackend` / `UserBackend`**:

- `adapters/persistence/neo4j/session_backend.py:48` — `class SessionBackend:` (no superclass)
- `def __init__(self, driver: AsyncDriver)` — takes the shared driver, nothing else
- Runs Cypher directly: `async with self.driver.session() as session: await session.run(...)`
- `add_conversation_message` (`user_backend.py:998`) already uses exactly this shape

`ConversationBackend` is a **new standalone class** in a new file
`adapters/persistence/neo4j/backends/conversation_backend.py`, constructor `(driver: AsyncDriver)`,
Cypher via `driver.session()`. It never touches `UniversalNeo4jBackend`, DTO lifecycle, the search
mixin, or the embedding publisher. **The wall is structural: the nodes are never in the universal
path to begin with.** (Update ADR-078 §3's precedent citation from Group → Session/User backend as
part of PR1 — one-line accuracy fix.)

### 2. New minimal frozen models — do NOT reuse the in-memory `ConversationSession`

`core/models/user/conversation.py` carries ~40 fields across `ConversationSession`(24) /
`ConversationTurn`(11) / `ConversationContext`(5); ADR-078 + the Askesis study prove ~35 are
vestigial. Build **new minimal frozen dataclasses** in `core/models/conversation/` (new package,
companion-neutral — not under `user/`), mapping ONLY the ADR-078 §3 subset:

```python
@dataclass(frozen=True, kw_only=True)
class ConversationSession:
    session_id: str            # "cs_<uuid hex[:12]>"
    user_uid: str              # owner FK — the ONLY access key
    kind: str                  # "discussion" (journals). Askesis-adoption seam; nothing branches on it in P1
    started_at: datetime
    last_activity: datetime    # touched on each append; revisit list orders by it
    title: str                 # user-set or first-message-derived — NOT an LLM summary
    source_selection: str      # JSON: canon shelf checkboxes + vault toggle (C3 restore)
    # turn_count is DERIVED (COUNT of HAS_TURN) — never stored (ADR-078 self-consistency)
    # NO state field — no writer, the vestigial trap ADR-078 criticizes

@dataclass(frozen=True, kw_only=True)
class ConversationTurn:
    turn_id: str               # "ct_<uuid hex[:12]>"
    session_id: str
    role: str                  # "user" | "assistant"
    content: str               # plaintext at rest until ADR-042 field-level encryption
    timestamp: datetime
    turn_number: int
```

Reuse the existing `MessageRole` enum for `role` only if it's a clean 2-value fit; otherwise a
plain `"user"`/`"assistant"` string is fine (schema says string). Do not import the 40-field model.

### 3. Neo4j labels + DDL

- Add `CONVERSATION_SESSION = "ConversationSession"` and `CONVERSATION_TURN = "ConversationTurn"`
  to `NeoLabel` (`core/models/enums/neo_labels.py:46`). **These are NeoLabels only — NOT added to
  `EntityType`.** That non-membership is the load-bearing wall guarantee.
- Constraints/indexes via `Neo4jSchemaManager` (idempotent `IF NOT EXISTS`), wired into the
  bootstrap schema-sync sequence (`services_bootstrap/compose.py` schema block):
  - `CONSTRAINT` unique on `ConversationSession.session_id`, `ConversationTurn.turn_id`
  - `INDEX` on `ConversationSession.user_uid` (revisit-list query), `ConversationTurn.session_id`

### 4. Edges — two, both owner-private

```cypher
(:User)-[:HAS_SESSION {started_at: datetime}]->(:ConversationSession)
(:ConversationSession)-[:HAS_TURN {turn_number: integer}]->(:ConversationTurn)
```

Neutral `HAS_SESSION` (not `HAS_DISCUSSION`) — companion-neutral for later Askesis adoption. Add
both to the `RelationshipName` enum (SKUEL013).

### 5. Neutral thin service — owner-private access boundary

`ConversationService` in `core/services/conversation/` (new package, companion-neutral), wrapping
`ConversationBackend`. It is the **owner-private boundary** and the understanding-agnostic store:
it persists sessions/turns and nothing else. All understanding wiring lives *above* it, opt-in per
consumer — **journals opts out entirely.** Methods (all `Result[...]`, all keyed on owner):

- `create_session(user_uid, kind, title, source_selection) -> Result[ConversationSession]`
- `append_turn(session_id, user_uid, role, content) -> Result[ConversationTurn]` (owner-checked;
  touches `last_activity`)
- `get_session(session_id, user_uid) -> Result[ConversationSession | None]` (404-not-403 on
  non-owner)
- `list_sessions(user_uid, limit) -> Result[list[ConversationSession]]` (revisit list, `last_activity` desc)
- `get_turns(session_id, user_uid) -> Result[list[ConversationTurn]]` (ordered; continue-thread)
- `delete_session(session_id, user_uid) -> Result[bool]` (`DETACH DELETE` session + all its turns)

Port/protocol `ConversationOperations` in `core/ports/`. `JournalService` gains a
`conversation_service` dependency (or routes call it directly — see PR2).

### 6. The understanding wall — enforced by ABSENCE, locked by guard tests

The wall is not policy code; it is the design. Because the nodes are **not `EntityType`s**, they
are structurally absent from every understanding surface (verified surfaces in parens):

| Surface | Why it can't see discussions |
|---|---|
| `_build_context_summary` / `get_vault_notes_for_context` | Cypher anchors on `(:Entity {entity_type:'user_entry'})` + `pipeline IN ['journal','knowledge']` (`_user_entry_content_mixin.py:113`) — ConversationSession/Turn are neither |
| Embeddings | `EMBEDDING_EVENT_TYPES` (`embedding_publisher.py:59`) is keyed by `EntityType`; no key → `publish_embedding_requested` returns `False`. No event class is created for these |
| `SearchRouter` | `_SEARCHABLE_DOMAINS` / `_SERVICE_REGISTRY` (`search_router.py:234,262`) are `EntityType`-keyed; the labels are never registered |
| ZPD / intelligence | No signal, no `MENTIONS`/`ANCHORED_TO`/`APPLIES_KNOWLEDGE` edges written from turns |

**Guard tests lock this against regression** (ADR-078 §7). Note: because these are not EntityTypes,
several guards are *structural* (assert-absence), which is the point — the test fails loudly if a
future change registers them:

1. **Owner-visibility symmetry** (integration) — every session a user owns appears in their
   revisit list; another user's session is invisible and direct fetch returns 404.
2. **Delete completeness** (integration) — per-session delete removes the session AND all its
   turns (no orphans); it vanishes from the revisit list.
3. **Context-builder isolation** (unit, source-inspection like `test_vault_notes_private_gate.py`;
   + integration) — context builder returns nothing sourced from the new labels even after
   discussions exist.
4. **No embeddings** (unit) — no `ConversationSession/Turn` embedding event class exists; the
   labels are absent from `EMBEDDING_EVENT_TYPES`/`EMBEDDING_NODE_LABELS`.
5. **Search invisibility** (unit + integration sweep) — labels absent from `_SEARCHABLE_DOMAINS`;
   a full SearchRouter sweep never returns them.
6. **No enrichment edges** (integration) — after a discussion, zero `MENTIONS`/enrichment/
   `APPLIES_KNOWLEDGE` edges from any `:ConversationTurn` to any `:Entity`.

**CI caveat:** CI runs only `tests/unit/`. Guards 1,2,6 are integration (local Docker Neo4j +
`neo4j-cypher` MCP to verify); guards 3,4,5 have unit forms that DO run in CI. Every guard needs a
unit form where structurally possible so the wall is CI-protected, not just local.

---

## Open refinements to pin in-arc (ADR-078 left these to the storage PR)

Decide these explicitly in the PR that implements each; don't let them drift.

1. **`source_selection` restore (C3).** On continue, rehydrate the composer's canon-shelf
   checkboxes + vault toggle from the stored JSON. **Ruling to confirm:** a *new* session starts
   all-unchecked (ADR-078 / C3 "deliberate grounding"); a *continued* session restores its own
   last selection. Store the selection at session create and update it if the user changes sources
   mid-thread (last-write-wins on the session).
2. **`title` derivation.** No LLM (that would be understanding). **Proposed:** first ~60 chars of
   the opening user turn, user-editable inline in the revisit list. Confirm the char budget + the
   edit affordance in PR3.
3. **Export-to-`.md` timing.** ADR-078 §8 allows it in the storage PR or a fast follow. **Proposed:**
   PR3 (with revisit/continue UI) — a per-session "Export" that renders turns to a markdown
   transcript download. It is a user-ownable copy, **not** a read-back folder class (ADR-073 has
   none). Keep it a download, not a vault write.

---

## Execution model — the arc self-drives PR → PR (no founder gating)

**Founder ruling (2026-07-13): run the whole arc continuously; do not stop between PRs.** This
plan is the standing authorization for all three PRs. Concretely:

- **No merge-call wait.** Each PR merges as soon as CI Gate is green **and** a real Codex verdict
  (exit 0 clean, or exit 2 findings-read-and-addressed) is in and its `codex-considered` gate is
  cleared. Do **not** pause to ask "merge?" — standing merge authorization covers app-code here.
- **No fresh-context hand-off.** The moment a PR merges, sync `main` and **immediately begin the
  next PR in the same run** (branch → implement → PR → merge). Do not hand the founder a
  kickoff prompt for the next PR; do not wait to be told to continue.
- **Roll to the end.** PR1 → PR2 → PR3 flow without a founder checkpoint. Report progress as each
  PR merges, but keep going.

**The only stop conditions** (per standing merge authorization — [[feedback_standing_merge_after_reviews]]):
1. A genuine **design decision / scope change** not already settled here (the three refinements
   below have proposed rulings — proceed on them; a *new* fork that they don't cover = stop + ask).
2. A **destructive migration** (none is expected — these are additive nodes/edges).
3. CI red or **no real Codex verdict** (quota/outage): follow the Codex workflow — never merge on a
   timer; surface the block rather than pushing past it.

Absent one of those, the arc does not return control to the founder until PR3 is merged.

## PR sequencing

Standard multi-PR arc, run back-to-back per the execution model above: branch-first, commit → PR →
Codex (app-code) → merge on green → straight into the next PR.

### PR1 — Neutral store foundation (capability + guards, no user-facing change)
- New models (`core/models/conversation/`), `NeoLabel` + `RelationshipName` additions, schema DDL
  wired into bootstrap, `ConversationBackend` (all 6 ops), `ConversationService` + port, bootstrap
  wiring into the `Services` container.
- Unit guards 3,4,5 (structural absence) + backend/service unit tests.
- One-line ADR-078 §3 precedent-citation fix (Group → Session/User backend).
- **Nothing wired into the live journal flow yet** — pure, safe, independently reviewable.
- Integration guards 1,2 runnable locally against the new store.

### PR2 — Migrate the live discussion flow onto the store
- `POST /journals/start` → creates a session + first user/assistant turn pair; returns the fragment
  carrying `session_id` (not the transcript).
- `POST /journals/follow-up` → appends turns; **reads prior turns from Neo4j** to build context
  instead of the hidden `original_entry`/`ai_response` accumulator.
- **Delete the accumulator** (`_Composer` hidden fields + the route's `combined` concatenation +
  the OOB Input swaps in `FollowUpFragment`) — One Path Forward, no dual-write. Composer carries
  only `session_id` (+ the existing `canon_book_uids` scope, now also persisted in
  `source_selection`).
- Owner-private enforcement (404-not-403) on every session touch.
- Integration coverage of the create → append → read-back flow; guard 6 (no enrichment edges).

### PR3 — Revisit, continue, delete, export
- Revisit list (the user's sessions, `last_activity` desc, `title` + timestamp) — a journals UI
  surface (unblocks the parked "Revisit Past Chats", [[project_journals_ux_refinement]]).
- Continue-thread: open a session → rehydrate composer from stored turns + `source_selection`.
- Per-session delete (first-class button → `delete_session`).
- Export-to-`.md` (refinement 3).
- `title` inline edit (refinement 2).

Export can split to a PR4 fast-follow if PR3 grows; keep each PR one coherent surface.

---

## Explicitly OUT OF SCOPE (ADR-078 rejected — do not build)

- Model-feeding (embeddings / UserContext / ZPD / `MENTIONS` edges) — the wall holds.
- Teacher visibility / sharing / `MONITORS` — owner-private, full stop.
- Auto-summon heuristics — `_maybe_summon_canon` stays the single seam.
- LLM `topic_summary` / `anchor_ku_uid` / curriculum anchoring — understanding-derived; not stored.
- AI-initiated openings — user always types first.
- **Touching Askesis** — its write-only `:ConversationMessage` path + in-memory container stay
  until a separate consented migration arc (its own confirmation; it must design opt-*in*
  understanding wiring journals refuses). This arc lays the neutral foundation only.

---

## Residuals carried forward (known, documented — not regressions)

- **Plaintext at rest:** `ConversationTurn.content` is plaintext in Neo4j until ADR-042 field-level
  encryption. Same *mechanism* as doorway/periodic notes, but freeform discussion is more
  sensitive → ADR-078 §6 flags it as a **candidate to prioritize first** in that work. Track, don't
  block.
