---
updated: 2026-07-23
---

# ADR-082: Askesis instruction home — authored pedagogy floors + grounding projection

**Status:** Accepted — founder-confirmed 2026-07-23 (D1=B with stance, D2=B both branches + per-turn rich, D3=B authoring-parity-only, D4=PLANNED all four with ku_bridge first; PR1 instruction-home → PR2 grounding)
**Arc:** LLM-root convergence — the Askesis slice ADR-081 named as next ("reuses the authoring approach and the grounding seam — not the content")
**Related:** ADR-081 (Journals instruction home + grounding projection — the two reused seams), ADR-077 (Askesis canon scoped retrieval), ADR-076 (canon quote-and-cite), ADR-078 (sessions stored-not-understood), ADR-073 (privacy wall), `ASKESIS_PEDAGOGICAL_ARCHITECTURE.md`.

This is a **choices-doc**: each Decision lists Options → a Recommendation. Founder confirmation turns it into the contract (status → Accepted); disagreement redirects it before any branch or code.

---

## The elicited workflow (founder, 2026-07-23)

- **Askesis is a study buddy** — an intelligent tutor helping the user progress **toward their LifePath and within their LearningPaths**. The LifePath↔LearningPath distinction exists in *idea* form, not operational form; the articulated LifePath and much of the curriculum are skeletons today. Askesis must meet the skeleton where it is and stimulate conversations that move the user forward.
- **Expert in SKUEL's content.** Its authority comes from the curriculum (Resources), **the shelf** ("an important part of Askesis" — its access shape differs from the Journals founder dial), and the **nous topic + subtopic selection** ("significant and fit to establish a foundation... of knowledge to learn, understand, communicate").
- **Citation is a CORE capability.** "Referencing to xyz from the Askesis chat is essential" — Askesis cites what its response draws on. Partly built today (canon sources + Ku-evidence citations).
- Future grounding channel: files the user deliberately shares via their `/skuel` folder (the personal vault).
- **Frugality:** build only inside the long-term vision (hosted trained **Qwen + BGE**); no architecture outside that grain.
- **Durable sessions: explicitly deferred** — "plan this as a future discussion."
- The four unrendered registry templates **may fit the workflow** — check for value; `askesis_ku_bridge` flagged as the likeliest ("referencing to a Ku from Askesis is an essential part of the workflow").

## Current state (verified against code, 2026-07-23)

- **Askesis already has half an instruction home.** Its 8 guided prompts are committed, authored `.md` files (`core/prompts/templates/askesis_guided_{assess,probe,scaffold,connection,practice,redirect,out_of_scope,direct}.md`), rendered via `PROMPT_REGISTRY` (`response_generator.py:267–369`). What it lacks is ADR-081's other half: **no founder-local override layer, and no composition** — each template is a bare leaf ("You are a Socratic tutor…") with no shared stance/voice fragment.
- **Selection is computed, not authored.** A deterministic tree (`intent_classifier.py:234–333`) maps question + per-KU ZPD evidence → `PedagogicalIntent` (7) → `GuidanceMode` (4) → template. The natural authoring key is the **template id** (the leaf), not the mode.
- **The guided prompt carries zero user grounding.** `build_guided_system_prompt(user_context=…)` ignores `user_context` in every builder; `_generate_guided_answer` never receives it. ZPD shapes *which move* is made; the words the model sees carry nothing of who the learner is or where their LifePath points.
- **The nous-facet path is the least-instructed path.** An explicit scope facet skips the guided pipeline AND canon entirely (Codex #544 override semantics, `query_processor.py` step 7) and answers via `build_llm_context()` — a hardcoded, implicit UserContext dump with intent-selected sections, no explicit-field-list projection, no authored instruction.
- **Grounding cost:** `get_rich_unified_context()` (full `build_rich()`, ~250 fields + ZPD capstone) on EVERY turn (`query_processor.py:246, 455`), plus a per-turn targeted `zpd_service.assess_ku_readiness()` for the question's KUs (line 599).
- **Canon (ADR-077) access already rides curriculum linkage, not founder identity** — `canon_service` is wired for all users (FULL tier), retrieval is PS-scoped via `ps_bundle.resources`, keyed on the learner's question; `canon_sources` surface in the UI. The "different access rights" the founder sensed is the built shape.
- **Citations partly built:** canon sources (guided path) + `_retrieve_citations_for_knowledge_units` (PREREQUISITE/HIERARCHICAL intents only).
- **No durable session** — in-memory `ConversationContext` (`core/models/user/conversation.py:122`); the main UI never passes `session_id`; the ADR-078 durable node (`core/models/conversation/models.py:44`) is Journals-only. A fire-and-forget `add_conversation_message` Neo4j write exists, unread by anything user-facing.
- **Four registry templates have zero render sites** (`askesis_journal_reflection`, `askesis_ku_bridge`, `askesis_scaffold_entry`, `askesis_socratic_turn`) — listed in the registry docstring; `zpd_assessment.py:14` stale-claims two are populated.

---

## Decision 1 — Askesis's instruction home: registry override + an authored stance

The Journals approach was *committed floor + founder-local override + containment guard*. Askesis's floors already exist as registry files — so the question is where the override mechanism lives, and what composition is added.

- **Option A — status quo.** Templates stay committed-only. *Rejected: the founder cannot refine the pedagogy without a commit cycle — the whole point of the authoring approach.*
- **Option B — override at the registry chokepoint (RECOMMENDED).** `PromptRegistry.render()` checks an optional founder-local override `data/instructions/{template_id}.md` before the committed template; silent miss (absence is normal); blank degrades to floor; the ADR-081 containment guard is **lifted to one shared home** (it currently lives in `journal/instruction_loader.py` — wrong import direction for the registry) and both consumers use it. One mechanism, every registry template overridable, Askesis the first beneficiary — One Path Forward.
  **Plus composition:** a new authored **`askesis_stance`** template (committed floor + override, like any other) — the study-buddy voice and identity (LifePath-facing, citation-forward: *cite what you draw on*) — **prepended to the system prompt on both answer branches** (guided and facet/context-aware). Stance (shared, authored) + pedagogy leaf (per move, authored) + selection (computed) — the tree stays mechanism; the words become refinable.
- **Option C — a per-surface `askesis_instruction_loader.py` with Python-string floors (Journals' literal mechanism).** *Rejected: Askesis's floors already live as registry files; copying them into Python strings walks backwards.*

**Recommendation: B.** Sub-decision 1a: the authoring key is the **template id** (8 leaves + stance) — per-LP/per-PS framing variation is NOT keyed into files in this slice (the curriculum is a skeleton; PsBundle already injects per-step content computationally; revisit if authored-per-path pedagogy proves wanted).

## Decision 2 — Grounding: a named Askesis projection, both branches, per-turn rich cadence kept

- **Option A — status quo.** Guided prompt: no user grounding. Facet path: implicit dump. *Rejected: "the study buddy knows you" is the elicited point.*
- **Option B — named projection, reusing the ADR-081 seam pattern (RECOMMENDED).** A new `render_askesis_grounding` (own module, Askesis-specific content — never shared with Journals' projection per the two-companions ruling) with an explicit **`ASKESIS_GROUNDING_FIELDS`** list enforced by a recording-context test. Content (Askesis-natural, distinct from Journals'): identity; **LifePath framing (skeleton-tolerant — degrades to nothing, never to filler)**; learning-journey position (enrolled paths, current path steps, mastered/in-progress counts); light activity relevance where it serves study. Injected on **both** branches: into guided prompts (between stance and pedagogy leaf) and **replacing the hand-assembled user sections of `build_llm_context`** on the facet/context-aware branch (curriculum/PsBundle text and workload mechanics untouched). Exact field list + title-join mechanics settled at implementation against what `build_rich()` actually carries at rich depth.
- **Option C — also restructure `build_llm_context`'s intent-section machinery.** *Rejected: scope creep; the projection replaces only the user-grounding sections.*

**Cadence sub-decision:** keep **`build_rich()` per turn** (status quo). ZPD is Askesis's gravity well (durable ruling); the targeted per-question KU assessment must be per-turn anyway; and with durable sessions deferred there is **no session substrate to cache against**. Session-open caching becomes a real option only after the future sessions discussion — noted as a lever, not built.

**Privacy wall, restated:** the projection reads structural UserContext only — never chat transcripts, never Journals content; the ADR-078 wall guard extends to cover the Askesis grounding path. Nothing writes to any understanding channel.

## Decision 3 — The shelf + nous foundation: author the expertise, add no retrieval

- **Option A — leave the facet path uninstructed.** *Rejected: the founder named nous selection the foundation; it is currently the least-instructed path.*
- **Option B — parity through authoring only (RECOMMENDED).** The facet branch gains the same `askesis_stance` + grounding projection as the guided branch (D1/D2 already deliver this). The stance authors the citation discipline (canon sources, Ku references — the core capability). **No new retrieval machinery**: no facet-scoped canon retrieval, no shelf access-rights change. Askesis's existing shelf shape — access via curriculum linkage (ADR-077 PS-scoped) — stands as-is this slice.
- **Option C — extend canon retrieval to facet scope in-slice.** *Rejected: retrieval design + shelf access-rights is its own elicit-first discussion (frugality; the founder wants "clean access… hopefully achieved" — that deserves a real design, not a rider).*

## Decision 4 — The four unrendered templates: staged, not dead

**Recommendation:** register all four in the bloat detector's **PLANNED tier** (visible completion backlog — "abandoned ≠ staged", and the founder says they may fit the workflow), and fix the stale `zpd_assessment.py:14` claim. Candidate order for future slices: **`askesis_ku_bridge` first** (aligns with citation-as-core); `askesis_journal_reflection` only ever via the je_pro/UserEntry **shared-entry doorway** (deliberately shared entries — never discussions; the wall is absolute); `askesis_socratic_turn` / `askesis_scaffold_entry` re-evaluated at the alternative-modes discussion. **None wired in this slice.**

## Decision 5 — North-star banking (Qwen + BGE)

Same shape as ADR-081 D3. **Banked free by D1–D3:** the Askesis pedagogy corpus becomes authored, versionable artifacts (future system-prompt / SFT material); grounding becomes a legible, provenance-clean projection (training-grade signal); the wall keeps the corpus consented and high-signal. **Not now, don't foreclose:** training pipeline, BGE swap, Qwen serving — no code, and D1–D3 don't design against them.

---

## Scope

**In:** registry-level override mechanism + shared containment guard home (D1); `askesis_stance` authored floor + composition on both branches (D1/D3); `render_askesis_grounding` projection + recording test + wall-guard extension (D2); PLANNED registration + stale-docstring fix (D4). FULL tier (Askesis is FULL-only already).

**Out:** durable/resumable Askesis sessions (founder: future discussion); any decision-tree or enrollment-gate change; the model switcher; shelf access-rights redesign / facet-scoped canon retrieval; LifePath↔LearningPath operationalization (its own arc — this slice is skeleton-tolerant); wiring any of the four PLANNED templates; any training/serving code; every shipped Journals surface.

## Consequences

- Askesis's pedagogy becomes **authored + refinable** (floor never breaks, override never commits), and its prompts finally **know the learner** — identity + LifePath direction + path position — making "study buddy toward your LifePath" real at the prompt level while the operational LifePath work stays its own arc.
- The registry-level override makes the ADR-081 authoring approach **the** mechanism (one guard, one convention) rather than a Journals-local pattern.
- Risk: the stance fragment could drift into behavior-sharing with Journals. Mitigation: distinct files, distinct floors, distinct projections — the shared thing is mechanism only (the confirmed two-companions ruling).
- Risk: projection scope creep — same mitigation as ADR-081: explicit field list + recording test.

## Proposed PR sequencing (pending confirmation)

- **PR1 — instruction home (D1 + D3's authoring half + D4).** Registry override + lifted shared guard; `askesis_stance` floor + composition into both branches; PLANNED registration + docstring fix. Unit tests: override resolution, floor coverage, guard, stance composition on both branches.
- **PR2 — grounding projection (D2).** `render_askesis_grounding` + `ASKESIS_GROUNDING_FIELDS` + recording test; injection on both branches; wall-guard extension; live verify a real guided turn and a real facet turn show the grounding.

Each PR: `ruff format` + `ruff check` + `mypy` (0) + `lint_skuel.py`; targeted unit tests; integration route/store tests before pushing any signature change; `./dev smoke`; Codex after final push; standing-auth merge once CI green + Codex considered.

## Founder decisions (confirmed 2026-07-23)

1. **Decision 1 → B** — registry-chokepoint override + `askesis_stance` fragment composed on both branches; guard lifted to one shared home.
2. **Decision 2 → B** — named `render_askesis_grounding` projection on both branches; per-turn `build_rich()` cadence kept.
3. **Decision 3 → B** — authoring parity only for the facet path; no new retrieval; shelf access-rights gets its own future elicitation.
4. **Decision 4 → PLANNED all four**, `askesis_ku_bridge` first candidate; none wired this slice.
5. **PR split → sequential** — PR1 instruction-home first, then PR2 grounding.
