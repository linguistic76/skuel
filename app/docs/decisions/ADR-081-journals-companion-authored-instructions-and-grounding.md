# ADR-081: Journals companion — authored instruction home + UserContext grounding

**Status:** Accepted — founder-confirmed 2026-07-23 (D1=B, D2=B, PR1 instruction-home → PR2 grounding; D3 to author discernment)
**Arc:** LLM-root convergence, **Phase 3** (the "sequencing to unify" bloom — reframed by founder elicitation 2026-07-23)
**Related:** ADR-073 (journals zero-persistence + vault memory), ADR-078 (discussion sessions stored-not-understood), ADR-076 (canon quote-and-cite), ADR-077 (Askesis canon scoped retrieval), Phase-2 model switcher (#781/#782), `JOURNALS_DOMAIN_ARCHITECTURE.md`.

This is a **choices-doc**: each Decision lists Options → a Recommendation. Founder confirmation turns it into the contract (status → Accepted); disagreement redirects it before any branch or code.

---

## Reframe — what Phase 3 actually is

The arc named Phase 3 *"the sequencing to unify — shared instruction set + shared conversation memory."* Founder elicitation (2026-07-23) corrected that frame:

- **Two DISTINCT authored instruction sets, one per surface.** Journals and Askesis are different companions for different purposes. They may share an *authoring approach*; never behavior or content.
- **No cross-chat memory, ever.** Askesis never sees a Journals discussion and vice versa. What they *share* is the **common substrate** — UserContext (SKUEL's memory of *you*) + the shelf (SKUEL's private proprietary knowledge). That substrate **plus the privacy wall is the structural moat** over a ChatGPT/Claude project.
- **The DNWF triad is a SPIRIT, not stages** — reflect back / partner / connect. The typed discussion stays free-form (the 2026-07-12 ruling that removed staging from typed chat **stands**). "Make it robust" = better authored instructions + better grounding, *not* re-staging.
- **"Understand you better" lives inside the privacy wall** — richer grounding on live UserContext + whatever you deliberately promote through the je_pro/vault doorway; **never** silent learning from the chats.
- **North star:** lay foundations today for a future trained LLM (**Qwen + BGE**); don't build against that grain.

## The MVP slice (this ADR) — Journals only, two threads

1. Give the **typed Journals companion a real authored instruction home** (parity with the file-door DNWF stages).
2. Ground the typed companion on the **real UserContext substrate**, not the six-titles digest.

**Askesis's instruction home is the *next* slice, not this one.** Its workflow is genuinely different (ZPD / PS-progression-guided, guided from turn one). It reuses the *authoring approach* and the grounding seam this slice establishes — not the content.

## Current state (verified against code, 2026-07-23)

- **Typed discussion** (`run_discussion` / `run_follow_up`) → `discussion_system_prompt` / `follow_up_system_prompt` in `core/services/journal/instruction_loader.py`. Their base voice is **hardcoded Python strings** (`_discussion_base` / `_follow_up_base`), `JournalMode`-flavored (3 variants each: scribe / thought-partner / what-is-related). Committed → guaranteed present.
- **File-door stages** (`stage1/2/3_system_prompt`) compose **authored files** from `data/instructions/` (`dnwf 1.md`, `Stance + Direction.md`, `roles interventions.md`, `dnwf style guide.md`, `inline_metadata_ie_short_codes.md`). **`data/instructions/` is gitignored — founder-local, not committed.** A missing file degrades to `""` (the stage "runs uninstructed").
- **Grounding** (`_build_context_summary`, used by discussion + every follow-up): top-6 *titles* each of goals / tasks / habits + shallow vault-note snippets, or (canon P3, #615/#616) the semantic "Draw on my vault" retrieval when that dial lands. It does **not** touch `UnifiedUserContext.build()` / `build_rich()`. **JournalService has no UserContext dependency** — it hand-rolls its own shallow view, a mild break from "UserContext = the single source of truth."
- **Model resolution:** the Phase-2 seam (`resolve_chat_model`, `core/services/chat/`) is solid and per-conversation. **This ADR does not touch it.**

---

## Decision 1 — Where the typed companion's instructions live, and how they degrade

The tension: authored files are **founder-local (gitignored) and may be absent**, but a companion with an empty system prompt is *broken* (a stage can degrade to `""`; a live chat cannot).

- **Option A — Files-only home (strict parity with stages).** The typed base moves entirely to `data/instructions/`. Absent file → no real fallback (can't be `""`). *Rejected: makes a working companion depend on local files a fresh deployment won't have.*
- **Option B — Committed default + local override (RECOMMENDED).** The current hardcoded strings become the committed **default floor** (guaranteed, per mode); an optional `data/instructions/` file **overrides** it when present. Founder refines by dropping/editing the file; any deployment still works. Same absence-tolerance `_load` already has, but with a real fallback instead of `""`.
- **Option C — Split dirs.** Committed defaults under a tracked `data/instructions/defaults/`, local overrides in `data/instructions/`. More moving parts than B for the same behavior.

**Recommendation: B.** Serves *robust* (never broken), *refinable* (author the override), and the *private/proprietary* framing (the refined instructions are local content; the floor is public mechanism).

**Sub-decision 1a — one composable home per surface.** Structure the home so the typed discussion **and** the file-door stages draw from ONE per-surface Journals home: shared fragments (stance / voice) + surface-specific bases. A **future Journals workflow becomes a new composition, not new plumbing** — which is the "room for future workflows" you asked for.

## Decision 2 — How rich the UserContext grounding, and at what per-turn cost

A chat turn can't pay a heavy build every message.

- **Option A — `build_rich()` per turn** (~250 fields + ZPD capstone). Richest, but a mega-query + ZPD every message is latency + cost, and ZPD is *Askesis's* gravity well, not Journals'. *Rejected for a per-turn path.*
- **Option B — `build()` per turn, render a curated projection (RECOMMENDED).** Adopt the real `UnifiedUserContext.build()` (~150 fields — the object the rest of the app already trusts), inject `UserContextService` into `JournalService`, and render only a **high-signal projection** into the prompt (identity / life-path framing, active goals·tasks·habits with light relevance, recent grounded entries). Cheaper than rich, far richer than six titles, and it stops Journals hand-rolling a parallel view.
- **Option C — Keep hand-rolling, just add more services.** Bolt life-path / entries onto `_build_context_summary` without adopting UserContext. *Rejected: doubles down on reinventing the single source of truth.*

**Recommendation: B.** It makes "SKUEL reflects *you* back" real (identity + what you're working toward), keeps the prompt a legible, tunable projection, and realigns Journals with the canonical UserContext object. The projection — not the raw mega-object — is what renders, so cost and signal stay controlled.

**Sub-decision 2a — the privacy wall, restated.** Grounding reads only **structural UserContext + non-private vault** (already gated). It **never** reads the discussion transcript, and nothing here writes to the understanding channel. ADR-073/078 walls intact; add a guard test that proves the projection touches no transcript data.

## Decision 3 — What north-star foundation to bank now (vs. merely not-foreclose)

- **Bank now** (falls out of Decisions 1–2 at no extra cost): (a) instructions as **authored, versionable artifacts** — a growing corpus of *how the companion should behave* is exactly future system-prompt / SFT material; (b) grounding as a **legible high-signal projection** — clean provenance now is clean training signal later; (c) **keep the privacy wall** — "save only what you keep" already yields a high-signal, consented corpus rather than noise.
- **Not now, don't foreclose:** the actual training pipeline, the BGE embedding swap (ADR-068, already staged), Qwen serving. **No code for these in this slice** — the test is only that Decisions 1–2 don't design *against* them. They don't.

---

## Scope

**In:** Journals typed-discussion instruction home (D1) + richer grounding (D2), both threads, FULL tier (fail-soft on CORE).
**Out:** Askesis instruction home (next slice); re-staging the typed chat (rejected — spirit not stages); any change to the Phase-2 switcher; any persistence or understanding-channel change (walls untouched).

## Consequences

- The typed companion becomes **authored + refinable + genuinely grounded** — the "structural benefit over a ChatGPT project" stops being aspirational: SKUEL knows your specifics *and* its private corpus, walled.
- **One composable per-surface instruction home** + **a grounding projection** are the two seams Askesis's later slice reuses.
- Risk: the grounding projection invites scope creep. Mitigation: keep it a **named, tested projection** with an explicit field list, not an open-ended dump.

## Proposed PR sequencing (pending confirmation)

- **PR1 — instruction home (D1).** Committed default floor + optional local override; one composable per-surface home; typed discussion + follow-up draw from it. No grounding change. Unit tests on composition + absence-degradation.
- **PR2 — grounding projection (D2).** Inject `UserContextService`; the journal grounding projection replaces the six-titles digest; privacy-wall guard test; live verify the richer grounding shows up in a real discussion turn.

Each PR: `ruff format` + `ruff check` + `mypy` (0) + `lint_skuel.py`; targeted unit tests; **integration route/store tests before pushing any backend-signature change**; `./dev smoke`; Codex after final push; standing-auth merge once CI green + Codex considered.

## Founder decisions (confirmed 2026-07-23)

1. **Decision 1 → B** — committed default floor + optional local override.
2. **Decision 2 → B** — inject `UserContextService`, `build()` + curated projection.
3. **Decision 3 → author discernment** — bank the three foundations as written; no over-reach flagged.
4. **PR split → sequential** — PR1 instruction-home first, *then* PR2 grounding.

## Shipped

- **PR1 — instruction home (D1): merged #783** (2026-07-23). Committed default floors
  (`_DISCUSSION_BASE_DEFAULTS` / `_FOLLOW_UP_BASE_DEFAULTS`, keyed by mode) + silent
  founder-local overrides (`data/instructions/journals.discussion.{mode}.md` /
  `journals.follow_up.{mode}.md`) with one shared containment guard. Floor coverage
  per mode is unit-enforced.
- **PR2 — grounding projection (D2)** (2026-07-23, this PR). `JournalService` gains an
  optional `context_builder` and grounds every typed turn on the canonical
  `UnifiedUserContext.build()`; the six-titles digest body is replaced by the **named
  projection** `render_journal_grounding` (`core/services/journal/grounding_projection.py`),
  whose `JOURNAL_GROUNDING_FIELDS` is the explicit field list — identity, active
  goals·tasks·habits with light relevance (progress %, overdue/due-today, streaks),
  and learning-journey framing (current path steps, mastery counts). Domain services
  keep supplying titles (standard `build()` is UID-depth); UserContext supplies the
  relevance lens. Fail-soft: unwired builder or failed build degrades to the
  pre-ADR-081 title digest; the canon-P3 vault-notes half and its de-dup rules are
  untouched. Privacy wall: a recording-context test pins renders to the explicit
  field list, and the ADR-078 wall guard now covers the whole grounding path
  (journal service + projection + the UserContext query module).
  *Implementation precision on D2's wording:* the injected seam is
  **`UserContextBuilder`** — the object that actually owns `build()` and the one every
  existing consumer injects (`UserContextService` is Context-Aware-API view-shaping
  and exposes no raw context).
