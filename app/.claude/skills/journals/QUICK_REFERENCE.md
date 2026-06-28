# Journals: Quick Reference

## Stage → Method → Prompt Source → Token Limit

| Stage | Method | Prompt source | Max tokens |
|---|---|---|---|
| Stage 1 — Scribe | `run_stage1(raw_entry, user_uid)` | `data/instructions/dnwf 1.md` | 4000 |
| Stage 2 — Thought Partner | `run_stage2(raw_entry, scribe_output, review_notes, user_uid)` | `dnwf 1.md` + `Stance + Direction.md` + `roles interventions.md` + `inline_metadata_ie_short_codes.md` + context digest | 4000 |
| Stage 3 — What Is Related | `run_stage3(raw_entry, thought_partner_output, review_notes, user_uid)` | `dnwf 1.md` + context digest | 3000 |
| Compiled (file upload) | `run_compiled(raw_entry, user_uid)` | Chains stage1→stage2→stage3; single markdown output | — |
| Standard | `run_standard(raw_entry, user_uid, mode=None)` | Inline strings in `instruction_loader.py` (no file dependency) | 4000 |
| Follow-up | `run_follow_up(original_entry, ai_response, user_reply, user_uid, mode=None)` | `follow_up_system_prompt()` — mode base + continuation directive (no re-analysis) | 4000 |

Stage 1 receives no UserContext (sparse by design). Stages 2 and 3 receive `build_context_summary()` digest.

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
| `core/services/journal/journal_service.py` | `JournalService` — 4 AI methods + `save_entry` |
| `core/services/journal/instruction_loader.py` | Prompt composition functions + STANDARD inline prompts |
| `adapters/inbound/journals_routes.py` | 10 routes — `/journals/respond`, `/journals/follow-up`, `/journals/stage1/2/3`, save, etc. |
| `core/models/enums/user_enums.py` | `JournalMode`, `JournalTier` |
| `core/models/enums/pipeline.py` | `Pipeline.JOURNAL` |
| `data/instructions/` | FOUNDER instruction files (not in git — proprietary) |

---

## Pipeline

```python
Pipeline.JOURNAL               # All journal UserEntries use this discriminator
Pipeline.JOURNAL.allows_sharing()  # → False (enforced at ingestion + UI layer)
```

---

## UserContext Digest

`JournalService.build_context_summary(user_uid)` builds a lightweight text block:

- Up to 6 active **Goal** titles
- Up to 6 active **Task** titles
- Up to 6 active **Habit** titles
- Up to 8 **Personal project notes** (vault-synced, title + 300-char snippet, newest-first)

Goals/Tasks/Habits services are optional — those sections degrade to empty if `None`.
Vault notes come from `self._user_entry` (always present) via `get_vault_notes_for_context()`.
Discriminator: `pipeline=journal` + `"vault_file_path"` in metadata (stamps set at ingestion).
Injected into Stage 2 + Stage 3 system prompts and STANDARD prompts.
Stage 1 deliberately receives no context.
