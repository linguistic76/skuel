---
name: journals
description: >
  Implementation guide for SKUEL's Journals domain — STANDARD single-response and FOUNDER
  three-stage DNWF workflows. Use when building or extending journal stages, working with
  JournalService or instruction_loader, adding a JournalMode, or integrating journals with
  UserContext or Askesis. Keywords: journals, DNWF, Scribe, Thought Partner, What Is Related,
  JournalMode, JournalService, run_stage1, run_stage2, run_stage3, pipeline JOURNAL.
allowed-tools: Read, Grep, Glob
---

# Journals: Implementation Guide

> "Not a curriculum companion. A personal thinking partner that meets you where you are — no enrollment required."

The Journals domain provides AI-assisted reflection for any authenticated user. Two tiers,
one `JournalService`: STANDARD delivers a single motivating response; FOUNDER runs the
three-stage Daily Notes Workflow (DNWF) with user review between stages.

---

## Orientation

| Stage / Mode | Method | Prompt source | Max tokens |
|---|---|---|---|
| Stage 1 — Scribe | `run_stage1(raw_entry, user_uid)` | `data/instructions/dnwf 1.md` | 4000 |
| Stage 2 — Thought Partner | `run_stage2(raw_entry, scribe_output, review_notes, user_uid)` | 4 instruction files + context digest | 4000 |
| Stage 3 — What Is Related | `run_stage3(raw_entry, thought_partner_output, review_notes, user_uid)` | `dnwf 1.md` + context digest | 3000 |
| Compiled (file upload) | `run_compiled(raw_entry, user_uid, summon_canon=False, summon_vault=False)` | Chains stage1 → stage2 → stage3; returns single markdown doc. `summon_canon` / `summon_vault` carry the grounding dials (no review gate on this path) | — |
| Discussion (typed first message) | `run_discussion(raw_entry, user_uid, mode=None, summon_canon=False, summon_vault=False, canon_book_uids=None) -> Result[JournalFollowUp]` | `discussion_system_prompt()` — companion voice, user leads, no forced headings (same family as follow-up). The **typed door** for BOTH tiers (ruling: typed = discussion; DNWF staging lives on the file/audio door). UserContext always-on; `summon_canon`/`summon_vault` are FOUNDER dials the route gates server-side. Quote-on-demand (`to_discussion_block()`); `canon_book_uids` scopes the shelf draw to the composer's checked books (C3). Returns `JournalFollowUp(text, sources)`; `StandardResponseFragment` renders the sources block | 4000 |
| Follow-up (conversation continuation) | `run_follow_up(...) -> Result[JournalFollowUp]` (`…, mode, summon_canon=False, summon_vault=False, canon_book_uids=None`) | `follow_up_system_prompt()` — mode base + continuation directive. The **quote-on-demand** surface (ADR-076): each dial (FOUNDER-gated server-side) retrieves on `user_reply` and injects its `to_discussion_block()` (name + quote verbatim, faithfulness contract) — canon shelf and/or the user's vault-minus-private (canon P3). `canon_book_uids` carries the session's book scope forward. Returns `JournalFollowUp(text, sources)` with canon + vault sources concatenated; kind-aware clickable links in `FollowUpFragment` (Resource page / `/gradebook/{uid}`) | 4000 |
| Suggested activities (panel) | `suggest_activities(content, user_uid)` | LLM bridge (`transform_with_context`) → `@context()` lines re-rendered to checkbox DSL via `suggestion.py` (bridge tags preserved verbatim) | — |

FOUNDER stages run in sequence and are gated at the route layer (`journal_tier.is_founder()`).
`run_compiled()` is the batch path: file upload (`instructions_only` mode) chains all three stages
without interactive review, producing a single markdown document with all three sections.

---

## Core Principles

1. **Stage autonomy** — each FOUNDER stage is a self-contained LLM call. Stage 2 takes
   Stage 1's output as a user-message input, not as a system-prompt injection.

2. **Mode-invariance of stage logic** — the three FOUNDER stage functions (`stage1_system_prompt`,
   `stage2_system_prompt`, `stage3_system_prompt`) are not parameterized by JournalMode.
   `JournalMode` nudges the discussion/follow-up voice; it is not exposed as a user
   choice in the composer (no mode selector). The FOUNDER stages are always Scribe → Thought
   Partner → What Is Related regardless of mode.

3. **File-driven FOUNDER prompts** — `instruction_loader.py` loads from `data/instructions/`.
   If `dnwf 1.md` is missing, stages degrade gracefully (warning logged, empty prompt).
   STANDARD prompts are inline strings — no file dependency.

4. **Context digest, not full UserContext** — `_build_context_summary()` extracts up to 6
   active titles each from Goals, Tasks, and Habits, plus up to 8 vault-synced personal notes
   (title + 300-char snippet via `UserEntryService.get_vault_notes_for_context()`; notes
   marked `private: true` are excluded). Stage 1 receives no context (sparse by design —
   fidelity requires restraint). Stages 2 and 3 receive the digest. **Vault-dial de-dup
   (canon P3):** when the vault dial's semantic block actually lands (`vault.has_passages`),
   the digest drops the shallow note snippets — never both reads of one corpus; a retrieval
   miss keeps them (fail-soft floor: dial-on never grounds below dial-off).

4a. **Two grounding dials (FOUNDER, both off by default)** — `summon_canon` (curated shelf,
   ADR-076) and `summon_vault` (the user's own vault-minus-private, canon P3 / ADR-077) are
   independent flags on `run_stage2`/`run_stage3`/`run_compiled`/`run_follow_up`. Both ride
   `_maybe_summon_canon` / `_maybe_summon_vault` (fail-soft → `CanonContext.empty()`); vault
   retrieval is `CanonRetrievalService.retrieve_vault(query_text, user_uid)` — owner-scoped
   (OWNS + hard private WHERE), Stages 2/3 keyed on the raw entry, follow-up on `user_reply`.
   Both dials on → ONE merged "Drawing on" footer (`merged_attribution_footer`); follow-up
   `sources` concatenate canon + vault (`CanonSource.source_kind` drives the kind-aware link:
   Resource page vs `/gradebook/{uid}` in the shared `CanonSourcesBlock`). Routes force both
   flags off server-side for non-FOUNDERs (forgeable-flag gate, one user resolve).

5. **Privacy-first** — `Pipeline.JOURNAL.allows_sharing()` returns `False`. No audience
   picker, no sharing, no teacher visibility. Enforced at the ingestion layer too
   (`build_user_entry_request()` coerces `audience=private`).

6. **FULL tier only** — all AI journal endpoints require `INTELLIGENCE_TIER=full`. Routes
   check this; under CORE they return an error fragment.

---

## Common Patterns

### Adding a new stage response handler in a route

```python
# adapters/inbound/journals_routes.py
@rt("/journals/stage1")
async def journal_stage1(request: Request) -> FT:
    user_uid = require_authenticated_user(request)
    if not (await _get_user(user_uid)).journal_tier.is_founder():
        return error_fragment("FOUNDER tier required")
    form = await request.form()
    raw = str(form.get("raw_entry", ""))
    result = await services.journal.run_stage1(raw, user_uid)
    if result.is_error:
        return error_fragment(result)
    return stage1_output_fragment(result.value)
```

### Extending the discussion / follow-up voice with a new JournalMode

1. Add the value to `JournalMode` in `core/models/enums/user_enums.py`.
2. Add a `from_string()` alias if needed.
3. Add a branch in `_discussion_base()` (first message) and/or `_follow_up_base()`
   (continuation) in `instruction_loader.py`.
4. Optionally add a `journal_mode_addendum()` branch for upload-pipeline hints.

### Modifying Stage 2 prompt

Stage 2 composes four files via `stage2_system_prompt(context_summary)` in
`instruction_loader.py`. To change composition: add/remove a `_load(key)` call inside
`stage2_system_prompt`. To add a new file, add an entry to `_FILES` and populate
`data/instructions/` with the file.

### Wiring a new context domain into `_build_context_summary()`

`_build_context_summary()` lives in `JournalService` (`core/services/journal/journal_service.py`).
It accepts optional `GoalsService`, `TasksService`, and `HabitsService`. To add a fourth:

1. Add the service as an optional constructor parameter.
2. Add a `search()` call with `limit=6` inside `_build_context_summary()`.
3. Inject the service from `services_bootstrap/compose.py` when constructing `JournalService`.

---

## Anti-Patterns

**Don't hardcode prompts in routes.** All prompt logic belongs in `instruction_loader.py`.
Routes pass raw entry text and user UID to the service, nothing else.

**Don't pass full UserContext.** `_build_context_summary()` distills a focused digest.
Passing a 250-field `UserContext` object into the journal prompt would dilute focus and
expose data the journal companion doesn't need.

**Don't share journal entries.** `Pipeline.JOURNAL.allows_sharing()` is `False` by design.
Never add a sharing picker to journal UI; never pass a non-private audience for journal
entries in ingestion code.

**Don't confuse EnrichmentMode templates with Journal stages.** The three templates
`journal_articulation.md`, `journal_exploration.md`, `journal_activity.md` in
`core/prompts/templates/` belong to the `EnrichmentMode` system for background
`LLM_SUMMARY` / `TRANSCRIBE_AND_STRUCTURE` processing — they are not part of
`JournalService` or `instruction_loader.py`.

---

## Cross-References

| Resource | What it covers |
|---|---|
| `docs/architecture/JOURNALS_DOMAIN_ARCHITECTURE.md` | Full domain architecture, tier comparison, privacy contract, roadmap |
| `docs/architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md §3` | Journals → Askesis ZPD signal pipeline (Phase 2 deferred) |
| `docs/user-guides/journal-privacy.md` | Privacy policy and enforcement commitments |
| `core/services/journal/journal_service.py` | `JournalService` — orchestrator for both tiers; `suggest_activities()` powers the panel |
| `core/services/journal/instruction_loader.py` | Prompt composition — FOUNDER file-driven, STANDARD inline |
| `core/services/journal/suggestion.py` | `SuggestedActivity` + bridge-line → checkbox DSL re-render, preserving the bridge's tags verbatim (deadlines/priorities not normalised, so nothing is lost). Inert; user copies into a Periodic Note / extraction folder, never auto-created |
| `adapters/inbound/journals_routes.py` | FOUNDER tier enforcement lives here; discussions are **ephemeral by default** (ADR-078 §5) — `/journals/start` persists nothing (the transcript rides the composer client-side), and an explicit `POST /journals/save` folds it into an owner-private `:ConversationSession` + turns (ONE atomic `save_transcript` txn) for revisit/continue but **no UserEntry** (understanding-agnostic — ADR-073's wall holds); `/journals/follow-up` picks session-backed (saved) vs ephemeral-structured (`transcript_json`, every unsaved chat — both doors); the file/audio + DNWF doors share the same substrate (composer opens on the source→output pair); the file-upload path itself is fully zero-persistence (ADR-073), processing to the user's own flat `je_out/` folder via one shared batch engine; `GET /journals/{entry_uid}` is **periodic-notes-only**; `POST /journals/suggest-activities` takes reflection content in the body and returns the lazy-loaded suggestions panel; `GET /journals/je-out/{filename}` serves flat `je_out/` outputs |
| `core/models/enums/user_enums.py` | `JournalTier`, `JournalMode` enum definitions |
| `core/models/enums/pipeline.py` | `Pipeline.LLM_SUMMARY` (LLM summarisation for ingestion/EXTRACT; journal upload no longer persists); `Pipeline.JOURNAL` (privacy contract; no new entries created after save_entry deletion) |
| `core/services/output/instruction_resolver.py` | EnrichmentMode system (separate from Journals) |
