# P3 — Ephemeral by Default, *Save this Chat* to Persist (both doors)

> **✅ Confirmed and shipped 2026-07-13.** The rulings below were founder-confirmed and the
> arc was built to them — PR1–PR3 all SHIPPED (see the phasing table: "P3 arc COMPLETE").
> The "no code until confirmed" gate below describes a gate that was then passed, not an
> open state.

**Design-first choices doc for the Journals discussion arc, phase 3.** Mirrors the P2
ADR-first precedent: **write + confirm the choices, THEN build.** No code until the founder
confirms the rulings below.

**⚠️ Realigned 2026-07-13 (founder ruling).** This doc was originally scoped as "the file door
*auto-creates* sessions + delete the accumulator." That was **wrong** — it inherited P2's
drifted default. The founder re-established the blunt Journals privacy rule: **a chat is not
saved by default; there is an explicit choice to save it.** ADR-078 is amended to match (§1/§5/§7,
2026-07-13). This doc is rewritten around that rule.

- **Arc SoT:** `docs/roadmap/done/journals-discussion-first.md` (§C6 convergence, §Phasing P3)
- **Governing ADR:** `docs/decisions/ADR-078-discussion-sessions-stored-not-understood.md` — the
  binding shape (now amended to opt-in persistence). If this doc and ADR-078 disagree, ADR-078 wins.
- **Predecessor:** `docs/roadmap/done/journals-discussion-storage-p2.md` (the store this reuses)
- **Privacy commitment:** ADR-073

---

## The one-sentence job

Restore **ephemeral-by-default** discussion on both doors, add a single explicit **Save this
chat** gesture that promotes the current transcript into the P2 owner-private
`:ConversationSession` store, and correct P2's two mistakes on the typed door — **without**
touching the understanding wall.

---

## The re-established privacy rule (the spine of this arc)

Journals are **private by default**, on two independent axes, and *keeping/sharing is always a
deliberate, explicit act*:

| Axis | Rule | Explicit opt-in gesture |
|---|---|---|
| **Understanding** — does it feed SKUEL's model of you? | **Never**, for any chat (saved or not) | the `je_pro/` doorway (file + `type: user_entry` frontmatter) — chat has **no** understanding opt-in at all |
| **Persistence** — is it stored at all? | **No, by default** — ephemeral, gone on reload | **Save this chat** (this arc) |

**Why blunt / why not-save-by-default** (record this reasoning alongside the code): (1) *privacy*
— the domain is private by default and auto-saving eroded that; (2) *signal vs noise* — saving
everything forces later weight-sorting of noise, while saving only what the user deliberately
keeps yields a high-signal corpus for free. Bluntness is a feature: a clear save/don't-save line
keeps the contract and the code simple. This is why the deferred "file-content weighting"
refinement (below) largely **dissolves** — you don't over-collect, so you don't need to sort.

---

## What P2 shipped, what was right, what drifted

| Piece | Status |
|---|---|
| Owner-private `:ConversationSession`/`:ConversationTurn` store (§3), `ConversationService`, thin backend | ✅ **Correct — reused as the *saved* substrate** |
| Understanding wall (turns feed nothing) | ✅ **Correct — proven by `tests/integration/test_conversation_store_guards.py` (#636)** |
| `/journals/start` **auto-creates** a session on the first reply | ❌ **Drifted** — persistence must be opt-in. Revert to ephemeral default. |
| P2 **removed the typed door's client-side accumulator** | ❌ **Drifted** — the accumulator is the ephemeral-default substrate. Restore it. |
| File/audio door still ephemeral (accumulator) | ⚠️ Correct default, but has **no Save action** yet — add one (convergence, C6) |

So P3 is **not** "make the file door persist like the typed door" — it is "make **both** doors
ephemeral-by-default and give **both** an explicit Save."

---

## Load-bearing invariants (verified — do NOT break)

- **Understanding wall.** `:ConversationSession`/`:ConversationTurn` are NeoLabels only, never
  `EntityType`. Even a *saved* chat feeds no embedding / search / context / graph edge. (Guarded
  by `tests/unit/conversation/` + `tests/integration/test_conversation_store_guards.py`.)
- **Owner-private everywhere** — every session touch is `user_uid`-scoped, 404-not-403.
- **`append_exchange` is THE atomic turn-pair primitive** — no single `append_turn`. A saved
  transcript is a sequence of `(user, assistant)` pairs.
- **`source_selection` JSON** — `{"canon":[…], "canon_on": bool, "vault": bool}`.
- **Not-saved-by-default (NEW, ADR-078 §7 guard 7)** — an un-saved discussion creates **zero**
  `:ConversationSession`/`:ConversationTurn` nodes.

---

## Decisions

### 1. Ephemeral substrate — keep the client-side accumulator, on BOTH doors  *(confirmed)*

Unsaved conversation memory stays in the hidden-field accumulator (`original_entry` /
`ai_response`, grown via OOB swaps). It dies on reload — that is the definition of "not saved."
The typed door's accumulator (removed in P2) is **restored**; the file door keeps its own.

**Implementation design point (needs a decision in PR1):** to *save* faithfully as discrete
turn pairs, the ephemeral accumulator should carry a **structured** transcript (an ordered list
of `{role, content}` pairs in a hidden field), not just the current flattened `combined` blob.
Then *Save* ships clean pairs to the store. **Proposed:** a structured hidden field
(`transcript_json`) replaces/augments the flat accumulator; the rendered bubbles are unchanged.

### 2. The *Save this chat* gesture  *(the core new surface)*

A single explicit button in the discussion workspace (both doors). On click:

1. `create_session(user_uid, kind="discussion", title, source_selection)` — title = first ~60
   chars of the opening user turn (no LLM — the existing deterministic rule); `source_selection`
   = the current dials (decision 4).
2. For each `(user, assistant)` pair in the transcript: `append_exchange(...)`. (No new store
   primitive strictly required — a thin `ConversationService.save_transcript(pairs)` convenience
   wrapper is optional and recommended for atomicity/clarity.)
3. The workspace becomes **session-backed** from that point: the composer swaps to carry
   `session_id` (the P2 path), so further turns append to the saved session and it appears in the
   revisit list.

**Post-save semantics *(confirmed 2026-07-13)*:** after saving, the button becomes a "Saved ✓"
indicator; re-clicking is a no-op (the chat is already session-backed). Un-saving / deleting is
the existing per-session delete on the revisit list.

**File/audio door gets the same Save affordance *(confirmed 2026-07-13)*.** One converged
discussion experience (C6): the file's `je_out/` file remains the artifact, and *Save this chat*
additionally keeps the *conversation about it*. Both doors expose the identical Save gesture.

### 3. Opening turn pair (what a saved file/audio chat records)  *(Option A — confirmed)*

Confirmed by the founder: **source → output.** When a file/audio chat is saved, its opening pair
is `(source text as user turn, produced output as assistant turn)` — the text-file content or
transcript as the user turn, the compiled `_out.md` / Stage-3 output as the assistant turn.
Faithful to today's follow-up context; richest continuation; no new privacy class (the source
already lives in the user-owned `je_out/`). For the typed door, the saved pairs are simply the
ephemeral turns as-typed.

*Degenerate `transcribe_only` (raw transcript, no AI compile):* only matters **if saved**. Under
opt-in it needs no special-casing at processing time — it is ephemeral like everything else. If
the user saves it, the opening pair is `(synthetic "Transcribe: {title}" user turn, transcript
assistant turn)`. **(Was a live fork under auto-save; opt-in defuses it.)**

### 4. Remembered source selections  *(confirmed — store what the door collects)*

At save, persist `source_selection` from the current dials. Typed door: the shelf checkboxes +
vault toggle (`{"canon":[…books…], "canon_on":…, "vault":…}`). File door: its coarse booleans
(`{"canon":[], "canon_on": summon_canon, "vault": summon_vault}` — `canon=[]` = whole shelf, the
existing "empty scope = None" convention). *Continue* restores them, exactly as P2 does today.
**Not in P3:** a per-book shelf picker on the upload form (UI convergence, separate arc).

### 5. File-content prompt weighting  *(deferred — and largely dissolved)*

Deferred, per C6 — P3 changes **zero** prompt composition. And the signal-vs-noise realignment
weakens the original motivation: opt-in save means the corpus isn't flooded with auto-saved
noise, so heavy weighting is not the pressing problem it looked like. If tackled later, it is a
separate **measured** refinement, not a guess here.

### 6. Revert P2's typed-door auto-save  *(confirmed)*

`/journals/start` stops auto-creating a session. It returns the ephemeral fragment
(accumulator-backed) with a *Save this chat* button. Continue/revisit of *already-saved* sessions
(the P2 read paths — `/journals/discussion/{id}`, delete, export, rename) are **unchanged**; they
now simply operate only on chats the user chose to save.

---

## Proposed phasing (standard multi-PR arc — branch-first; app-code needs a real Codex verdict)

| PR | Delivers |
|---|---|
| **PR1 — ephemeral default + Save (typed door)** ✅ **SHIPPED** | Reverted `/journals/start` auto-save; the composer's ephemeral memory is now a **structured** `transcript_json` field (ordered `{role, content}` pairs, decision 1); added `POST /journals/save` → `ConversationService.save_transcript(pairs)` (create_session + append_exchange loop, decision 2); the composer gained a *Save this chat* button (→ "Saved ✓" once session-backed) and an OOB revisit-list refresh. Guard 7 landed as a **route-level** live-Neo4j test (`TestOptInPersistenceGuard`): opening + following-up create **zero** nodes; only save writes. Follow-up route now has three memory paths (session-backed / ephemeral-structured / flat-legacy — the flat path is the file/DNWF door until PR2). |
| **PR2 — file/audio door joins (ephemeral + Save)** ✅ **SHIPPED** | `FileOutputFragment` + `Stage3Fragment` now open on a structured `transcript_json` (source→output pair, decision 3 — transcribe_only uses a synthetic `Transcribe: {title}` user turn) and expose the same *Save this chat*; the door's coarse `summon_canon`/`summon_vault` ride the composer so a Save records `source_selection` (decision 4). One Path Forward: the flat `original_entry`/`ai_response` accumulator is **deleted** (composer, follow-up route, `FollowUpFragment.combined`); `/journals/follow-up` now has just two paths (session-backed / ephemeral-structured). Gate + upload tests migrated to the structured substrate. |
| **PR3 — reconcile & prove** ✅ **SHIPPED** | Added a live-Neo4j end-to-end route test: a saved chat round-trips — save → the revisit list shows it + continue rehydrates the stored turns → delete drops the whole subtree. (Unsaved-persists-nothing across both doors is already locked by guard 7 — the `/journals/follow-up` ephemeral path is door-agnostic.) The two-axis privacy contract (understanding: never; persistence: not by default) is documented next to the code in `JOURNALS_DOMAIN_ARCHITECTURE.md` §Persistence. **P3 arc COMPLETE.** |

No accumulator-deletion PR — the accumulator is retained by design. PR1 carries the most risk
(reverting shipped auto-save + restructuring the ephemeral field); keep it self-contained.

---

## Explicitly OUT OF SCOPE (this arc)

> The three follow-on refinements below are tracked with full pick-up context in
> **`docs/roadmap/journals-discussion-deferred.md`**.

- **Auto-saving anything** — persistence is opt-in, full stop.
- **File-content prompt weighting** — deferred + dissolved (decision 5).
- **A per-book shelf picker on the upload form** — UI convergence, separate (decision 4).
- **Batch/folder sessions** — multi-file processing has no single discussion surface; no chat, no save.
- **Any understanding wiring** — the wall holds; turns feed nothing (ADR-078 §2).
- **Touching Askesis** — its own consented migration arc, unchanged here.

---

## Residuals carried forward (known — not regressions)

> The encryption residual is tracked live in `../journals-discussion-deferred.md` § 3
> (at-rest encryption, ADR-042 — discussions prioritized); "unsaved = lost" is the intended
> contract, not open work.

- **Plaintext at rest:** *saved* turn content (including stored source text) is plaintext in
  Neo4j until ADR-042 field-level encryption — same residual class as typed-door turns and
  `je_out/` artifacts. Opt-in save means *less* is stored, which only helps.
- **Unsaved = lost on reload** — this is the intended contract, not a bug. "Not saved" means not
  saved.
