# Journals: Quick Reference

## Stage → Method → Prompt Source → Token Limit

| Stage | Method | Prompt source | Max tokens |
|---|---|---|---|
| Stage 1 — Scribe | `run_stage1(raw_entry, user_uid)` | `data/instructions/dnwf 1.md` | 4000 |
| Stage 2 — Thought Partner | `run_stage2(raw_entry, scribe_output, review_notes, user_uid)` | `dnwf 1.md` + `Stance + Direction.md` + `roles interventions.md` + `inline_metadata_ie_short_codes.md` + context digest | 4000 |
| Stage 3 — What Is Related | `run_stage3(raw_entry, thought_partner_output, review_notes, user_uid)` | `dnwf 1.md` + context digest | 3000 |
| Compiled (file upload) | `run_compiled(raw_entry, user_uid, summon_canon=False, summon_vault=False)` | Chains stage1→stage2→stage3; single markdown output. `summon_canon` / `summon_vault` = grounding dials (no review gate here) | — |
| Discussion (typed first message) | `run_discussion(raw_entry, user_uid, mode=None, summon_canon=False, summon_vault=False, canon_book_uids=None) -> Result[JournalFollowUp]` | `discussion_system_prompt()` — companion voice, user leads, no forced headings. Typed door for BOTH tiers (`/journals/start`); UserContext always-on, canon/vault FOUNDER dials gated server-side. `canon_book_uids` scopes the shelf draw (C3). Returns `JournalFollowUp(text, sources)`; `StandardResponseFragment` renders the sources block | 4000 |
| Follow-up | `run_follow_up(...) -> Result[JournalFollowUp]` (`original_entry, ai_response, user_reply, user_uid, mode=None, summon_canon=False, summon_vault=False, canon_book_uids=None`) | `follow_up_system_prompt()` — mode base + continuation directive (no re-analysis). **Quote-on-demand surface (ADR-076):** each dial (FOUNDER-gated in the route) retrieves on `user_reply`, injects its `to_discussion_block()` (may name + quote verbatim) — canon shelf and/or vault-minus-private (canon P3, `retrieve_vault`). `canon_book_uids` carries the session's book scope forward. Returns `JournalFollowUp(text, sources)` — canon + vault sources concatenated, kind-aware clickable links in `FollowUpFragment` (Resource page / `/gradebook/{uid}`), not a markdown footer | 4000 |
| Suggested activities | `suggest_activities(content, user_uid)` | LLM bridge → canonical `@context()` lines (inert; panel only) | — |

Stage 1 receives no UserContext (sparse by design). Stages 2 and 3 receive `_build_context_summary()` digest.

---

## JournalMode Enum

```python
# core/models/enums/user_enums.py
class JournalMode(str, Enum):
    SCRIBE          = "scribe"           # Faithful structural record
    THOUGHT_PARTNER = "thought_partner"  # Patterns, tensions, what is emerging (default)
    WHAT_IS_RELATED = "what_is_related"  # Knowledge connections and candidates

    @classmethod
    def default(cls) -> "JournalMode": ...          # → THOUGHT_PARTNER
    @classmethod
    def from_string(cls, value: str) -> "JournalMode": ...  # normalizes, falls back to default
    def display_label(self) -> str: ...             # → "Scribe" / "Thought Partner" / "What Is Related"
```

---

## JournalTier Enum

```python
# core/models/enums/user_enums.py
class JournalTier(str, Enum):
    STANDARD = "standard"   # All authenticated users — single-response
    FOUNDER  = "founder"    # User.journal_tier = FOUNDER — three-stage DNWF

    def is_founder(self) -> bool: ...  # Tier gate check used in routes
```

---

## Key File Paths

| File | Purpose |
|---|---|
| `core/services/journal/journal_service.py` | `JournalService` — AI methods: `run_stage1/2/3`, `run_compiled`, `run_discussion`, `run_follow_up`, `suggest_activities`, `list_canon_shelf`. Entry persistence handled by the ingestion path in the calling route. |
| `core/services/journal/suggestion.py` | `SuggestedActivity` + bridge-line → checkbox DSL re-render (bridge tags preserved verbatim) for the "Suggested activities" panel (inert; user copies into their own notes) |
| `core/services/journal/instruction_loader.py` | Prompt composition functions + STANDARD inline prompts |
| `adapters/inbound/journals_routes.py` | `POST /journals/start` (text entry → runs AI → returns response **inline**, `HX-Retarget` `#journal-workspace`; **zero-persistence**, no UserEntry, ADR-073); `POST /journals/upload` + `POST /journals/folder-process` process to the user's own `je_out/` folder via one shared stateless batch engine (no UserEntry); `GET /journals/{entry_uid}` is **periodic-notes-only**; `GET /journals/je-out/{filename}` downloads a flat `je_out/` file |
| `core/models/enums/user_enums.py` | `JournalMode`, `JournalTier` |
| `core/models/enums/pipeline.py` | `Pipeline.LLM_SUMMARY` (LLM summarisation for ingestion/EXTRACT paths); journal upload no longer creates a UserEntry (ADR-073) |
| `data/instructions/` | FOUNDER instruction files (not in git — proprietary) |

---

## Pipeline

```python
# File-upload path (ADR-073): zero-persistence. The uploaded file is transcribed / LLM-compiled
# in-memory and the result is written to the user's own je_out/{stem}_out.md (or {stem}.txt for a
# raw transcript) — flat, never synced, no UserEntry. The user downloads/opens it in Obsidian.
Pipeline.JOURNAL.allows_sharing()  # → False; Pipeline.JOURNAL still enforces privacy
                                   # for any legacy entries; new entries use LLM_SUMMARY
```

---

## UserContext Digest

`JournalService._build_context_summary(user_uid, include_vault_notes=True)` builds a
lightweight text block:

- Up to 6 active **Goal** titles
- Up to 6 active **Task** titles
- Up to 6 active **Habit** titles
- Up to 8 **Personal project notes** (vault-synced, title + 300-char snippet, newest-first;
  `private: true` notes excluded)

Goals/Tasks/Habits services are optional — those sections degrade to empty if `None`.
Vault notes come from `self._user_entry` (always present) via `get_vault_notes_for_context()`.
Discriminator: `pipeline IN [journal, knowledge]` + `"vault_file_path"` in metadata (stamps set at ingestion). `knowledge` = developed files in the `knowledge/` doorway, shared to teach SKUEL.
Injected into Stage 2 + Stage 3 system prompts and STANDARD prompts.
Stage 1 deliberately receives no context.
**Vault dial de-dup (canon P3):** when the semantic vault block (`retrieve_vault`,
owner-scoped + private-excluded) actually lands, the digest is built with
`include_vault_notes=False` — never both reads of the same corpus in one prompt. A
retrieval miss (fail-soft) keeps the shallow snippets, so the dial never grounds below
its off state.
