# Journals: Domain Architecture

> "Not a curriculum companion. A personal thinking partner that meets you where you are — no enrollment required."

**Companion docs:** `ASKESIS_PEDAGOGICAL_ARCHITECTURE.md` (sibling AI system, §3.0 for the parallel comparison), `ENUM_ARCHITECTURE.md` (JournalTier + JournalMode enum definitions)

**This doc:** architecture and design intent of the Journals domain — what drives it, how the two tiers differ, and how it relates to Askesis.

---

## 1. Purpose and Access Model

The Journals domain is an AI companion for personal reflection, thinking-in-writing, and knowledge connection. It is SKUEL's second AI companion system alongside Askesis.

**Access:** Any authenticated user. No LearningPath enrollment required.

**Contrast with Askesis:** Askesis requires LP enrollment and is driven by the curriculum graph (PathStep + KU bundle + ZPD). Journals has no enrollment gate and is driven by UserContext + the entry itself.

**Persistence:** SKUEL does not automatically persist journal AI outputs. File-upload processing saves compiled output to `je_out/{stem}_out.md`; the user downloads and manages these files themselves (see §7). The uploaded file content is persisted as `UserEntry(pipeline=Pipeline.LLM_SUMMARY)` for pipeline tracking, but the AI response is never automatically saved to the user's profile or vault.

**Intelligence tier:** Journals requires `INTELLIGENCE_TIER=full`. All AI endpoints (`/journals/respond`, `/journals/stage1`, `/journals/stage2`, `/journals/stage3`) return an error fragment under `INTELLIGENCE_TIER=core`.

---

## 2. The Guidance Model

The two AI companion systems operate on structurally parallel but distinct guidance models:

```
Askesis:            LP enrollment → PsBundle (PathStep + KUs) → ZPDAssessment → GuidanceMode → response
Journals STANDARD:  (no gate)     → UserContext digest + entry → JournalMode                 → response
Journals FOUNDER:   (no gate)     → UserContext digest + entry + curriculum dev + biz dev     → 3-stage DNWF → outputs
```

**UserContext digest:** `JournalService._build_context_summary()` builds a lightweight text digest with four sections: up to 6 active titles each from Goals, Tasks, and Habits; plus a "Personal project notes" section of up to 8 vault-synced notes (title + 300-char snippet, newest first). Vault notes are `pipeline=journal` UserEntry nodes whose `metadata["vault_file_path"]` marks them as synced from `VAULT_ROOT` rather than created via the journals UI. This is NOT the full UserContext object; it is a targeted life-context snapshot. The three domain services (Goals, Tasks, Habits) are optional and degrade gracefully to empty; `UserEntryService` is required and always present.

**JournalMode vs GuidanceMode:** JournalMode selects the companion's *function* — what the AI does with the entry. Tone is uniform across all modes. This differs from GuidanceMode in Askesis, which selects both the pedagogical register and the interaction strategy.

---

## 3. JournalMode: Three Functions

JournalMode maps to the three stages of the DNWF process. In STANDARD tier, mode selects the inline system prompt (SCRIBE / THOUGHT_PARTNER / WHAT_IS_RELATED) — it is not exposed as a user-facing selector in the upload form. In FOUNDER tier, the stages run in fixed sequence (Scribe → Thought Partner → What Is Related); mode is not a user input at any stage.

| Mode | DNWF Stage | What it does | Default? |
|---|---|---|---|
| `SCRIBE` | Stage 1 | Faithful structural record — repairs transcription, reveals structure, preserves voice and metaphor | No |
| `THOUGHT_PARTNER` | Stage 2 | Identifies patterns, tensions, contradictions, unresolved questions, and what is emerging | Yes |
| `WHAT_IS_RELATED` | Stage 3 | Maps connections to knowledge, curriculum candidates, tasks, projects, principles | No |

`THOUGHT_PARTNER` is the default because the most common journaling need is "help me see what I'm actually saying." `SCRIBE` is a precondition for the other two in the FOUNDER workflow but stands alone in STANDARD.

`JournalMode.from_string()` normalizes form-submitted values and falls back to `THOUGHT_PARTNER` on unknown input. Defined in `core/models/enums/user_enums.py`.

---

## 4. Two Tiers: STANDARD and FOUNDER

`User.journal_tier` (type `JournalTier`) determines which workflow runs. The field lives on the `User` model and is stored on the `:User` Neo4j node. Default is `STANDARD`.

| | STANDARD | FOUNDER |
|---|---|---|
| Access | All authenticated users | `User.journal_tier = FOUNDER` |
| Workflow | Single-response (one-shot) | Three-stage sequential, gated by user review between stages |
| Mode selection | JournalMode shapes the inline system prompt; not user-selectable from UI | Stages run in fixed order (Scribe → TP → WIR); mode is not a user input |
| Instruction source | Inline strings in `instruction_loader.py` (no file dependency) | Files from `data/instructions/` |
| UserContext injection | All modes | Stage 2 and Stage 3 only (Stage 1 is context-free by design) |
| Gating enforcement | None | Route layer: `journal_tier.is_founder()` check before stage1/2/3 handlers |

The STANDARD tier uses self-contained inline prompts — this makes it fully operational with no file setup and suitable for general use. The FOUNDER tier is file-driven because its orientation is proprietary and lives outside the codebase.

---

## 5. FOUNDER Tier: The DNWF Process

The Daily Notes Workflow (DNWF) is a three-stage process where the user reviews each stage's output before proceeding to the next.

### 5.1 Stage Prompt Composition

Each stage uses a different prompt composition:

**Stage 1 — Scribe** (`stage1_system_prompt()`):
- Loads: `dnwf 1.md` only
- Sparse by design — fidelity requires restraint. No stance, no roles, no context.

**Stage 2 — Thought Partner** (`stage2_system_prompt(context_summary)`):
- Loads: `dnwf 1.md` + `Stance + Direction.md` + `roles interventions.md` + `inline_metadata_ie_short_codes.md` + UserContext digest
- The richest stage. Stance and roles encode specific ways of engaging with what is emerging. The shortcodes file enables structured inline metadata in the output.

**Stage 3 — What Is Related** (`stage3_system_prompt(context_summary)`):
- Loads: `dnwf 1.md` + UserContext digest
- Lean by design — connection mapping needs context, not engagement stance.

The instruction files live in `data/instructions/` and are copyrighted. The loader degrades gracefully: if the primary file (`dnwf 1.md`) is missing, stages run with a reduced prompt and log a warning. No stage fails hard on missing instruction files.

### 5.2 The FOUNDER Conceptual Expansion

FOUNDER adds two dimensions that STANDARD does not have:

1. **Curriculum development awareness** — the Thought Partner and What Is Related stages operate with the awareness that insights may become KUs, PathSteps, or LearningPaths. Not every insight will; the stage exercises judgment about what has structure-bearing potential.

2. **Business development awareness** — the same stages surface business insights alongside personal ones, treating the founder's daily thinking as a source of organizational intelligence.

These two dimensions are encoded in the DNWF instruction files, not in application code. This is why FOUNDER is file-driven and STANDARD is inline-driven: the orientation is proprietary and evolves independently of the application.

The three-tier comparison:

```
Journals STANDARD:  entry + UserContext digest → JournalMode selects function → single response
Journals FOUNDER:   entry + UserContext digest + curriculum dev + biz dev → Scribe → Thought Partner → What Is Related
```

---

## 6. Service Architecture

| Component | File | Responsibility |
|---|---|---|
| `JournalService` | `core/services/journal/journal_service.py` | Orchestrates both tiers. Six AI methods: `run_stage1/2/3`, `run_compiled`, `run_standard`, `run_follow_up`. `run_compiled()` is the file-upload batch path: chains all three stages without review gates. Does not persist entries — persistence and file output are handled by the calling route. |
| `instruction_loader` | `core/services/journal/instruction_loader.py` | Prompt composition. STANDARD prompts are inline; FOUNDER stages load from `data/instructions/`. |
| Routes | `adapters/inbound/journals_routes.py` | 9 routes. FOUNDER enforcement (`journal_tier.is_founder()`) lives at the route layer. File-upload path saves compiled output to `je_out/{stem}_out.md` and returns a download fragment. `GET /journals/je-out/{filename}` serves `je_out/` files with a path-containment guard. |
| `JournalTier`, `JournalMode` | `core/models/enums/user_enums.py` | Tier and mode enum definitions. |
| `Pipeline.LLM_SUMMARY` | `core/models/enums/pipeline.py` | Pipeline used when persisting uploaded file content as a UserEntry (input tracking only; the AI output is not persisted). |

`JournalService` takes `LLMCallerProtocol` + `UserEntryService` (required) and `GoalsService` / `TasksService` / `HabitsService` (all optional — omitting them degrades `_build_context_summary()` to empty string).

---

## 7. Vault Sync Boundary: The `je_*` Folders

The personal vault (`VAULT_ROOT`, `/home/mike/0bsidian/skuel/`) contains four pipeline staging folders that are **never ingested by vault sync**. They are excluded from `_VAULT_EXCLUDED_DIRS` in `vault_reconciler.py`.

| Folder | Role | Flow direction |
|--------|------|----------------|
| `je_in/` | Batch-transcription audio input | `POST /journals/folder-process` (backend-only; not surfaced in capture UI since the "Watch folder" tab was removed) |
| `je_out/` | Batch-transcription transcript output | `.txt`/`.md` written by `BatchTranscriptionService` |
| `je_raw/` | Reference archive input (`Pipeline.REFERENCE`) | Stored as-is, no processing |
| `je_pro/` | Reference archive processed output | Counterpart to `je_raw/` |

These folders are **pipeline artifacts**, not vault content. The vault sync path (`/settings/vault`) skips all four unconditionally.

The main upload path (`/journals` → "Upload files" tab, FOUNDER tier) **writes the compiled AI output directly to `je_out/{stem}_out.md`** and returns a download fragment — the AI response is a file, not a profile record. The user opens the `_out` file in Obsidian and manually extracts what matters into their personal vault. SKUEL never auto-syncs `je_out/` content into the vault.

The `_out` suffix convention (`{stem}_out.md`) distinguishes processed output from raw input at a glance. All three write paths (single file upload, `transcribe_and_instructions`, `instructions_only` folder batch) use this convention.

The `je_out/` exclusion is the load-bearing one: without it, output files would be ingested as plain-text UserEntries on every vault sync.

## 8. Privacy Contract

- All journal entries are persisted with `pipeline=Pipeline.JOURNAL`.
- `Pipeline.JOURNAL.allows_sharing()` returns `False`. No audience picker is offered in the UI; sharing cannot be unlocked through the API.
- Journal entries are user-owned only. No teacher visibility, no group sharing, no admin read access through normal domain APIs.
- The ingestion audience coercion in `build_user_entry_request()` enforces `audience=private` for all non-shareable pipelines, so vault-ingested journal entries cannot carry a non-private audience even if the YAML frontmatter requests one.

Full policy: `docs/user-guides/journal-privacy.md`

---

## 9. Journals as ZPD Signal (Phase 2, Deferred)

The Journals domain produces the richest signal of where the user actually is — what clicked, what remains unresolved, what questions are still open. This signal is intended to feed Askesis, but the extraction pipeline is deferred.

**What is deferred:** After a journal entry is processed, a second LLM pass would extract pedagogical signals into a `JournalInsight` object:

```python
# core/models/submissions/journal_insight.py — shape defined, extraction deferred
@dataclass(frozen=True)
class JournalInsight:
    journal_uid: str
    open_questions: list[str]        # Prime Askesis conversation starters
    concepts_mentioned: list[str]    # Concepts to link to KUs via semantic search
    struggles: list[str]             # Expressed uncertainty — scaffolding targets
    insights_crystallized: list[str] # Things that clicked — mastery signals
    related_ku_uids: list[str]       # KU links via semantic search (Phase 3)
```

**How it would surface:** `UserContext.journal_insights` — a list of recent insights read by Askesis when a conversation opens. The signal is passive, not push.

**What this is not:** Journals does not query the curriculum graph in its own processing. The connection is one-directional — journals produce signals; Askesis consumes them. The WHAT_IS_RELATED stage can surface curriculum candidates from its context-based reasoning, but it does not run a graph query to do so.

**See:** `ASKESIS_PEDAGOGICAL_ARCHITECTURE.md §3` for the Askesis side of this pipeline.

---

## 10. Roadmap

- **Richer UserContext injection** — `_build_context_summary()` pulls titles from Goals/Tasks/Habits (up to 6 each) and vault note snippets (up to 8). A future version could include habit completion rates, task priorities, goal timeframes, and recent activity for richer context.
- **WHAT_IS_RELATED + curriculum graph** — Stage 3 currently has no graph query capability. A future enhancement could let it query Neo4j for related KUs and PathSteps, making connection suggestions concrete rather than inferred.
- **ZPD signal loop** — `JournalInsight` extraction → `UserContext.journal_insights` → Askesis reads on session open. See `ASKESIS_PEDAGOGICAL_ARCHITECTURE.md §3` for the full Phase 2/3 design.
- **Per-user journal tier configuration** — `JournalTier` is designed to be extensible. The FOUNDER pilot paves the path for user-configurable journal workflow depth without code changes.

---

## 11. Cross-References

| Resource | What it covers |
|---|---|
| `ASKESIS_PEDAGOGICAL_ARCHITECTURE.md` | Askesis as sibling AI system; §3 for journals as ZPD signal source |
| `ASKESIS_HOW_IT_WORKS.md` | Askesis 10-step pipeline (contrast with journals two-step: prompt → response) |
| `ENUM_ARCHITECTURE.md` | `JournalTier` and `JournalMode` enum definitions and methods |
| `docs/user-guides/journal-privacy.md` | Full privacy policy and enforcement commitments |
| `core/services/journal/journal_service.py` | Service implementation, context summary building |
| `core/services/journal/instruction_loader.py` | Prompt composition, file loading, STANDARD inline prompts |
| `adapters/inbound/journals_routes.py` | Route layer, FOUNDER tier enforcement |
| `core/models/submissions/journal_insight.py` | `JournalInsight` dataclass stub (Phase 2) |
