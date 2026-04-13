---
title: Journals Domain
created: 2025-12-04
updated: 2026-03-22
status: current
category: domains
tags: [journals, standalone-domain, multi-modal, ai-processing]
---

# Journals Domain

**Type:** Standalone domain (NOT under submissions/reports)
**Entity Types:** `EntityType.JE_INPUT` (`JeInput`), `EntityType.JE_OUTPUT` (`JeOutput`)
**UID Prefixes:** `ji_` (JeInput), `jo_` (JeOutput)
**Neo4j Labels:** `:Entity:JeInput`, `:Entity:JeOutput`
**Models:** `core/models/journal/`
**Services:** `core/services/journal/` (JournalInputService + JournalOutputService)

## Domain Architecture (March 2026)

Journal is a **standalone domain** — `JeInput(UserOwnedEntity)` and `JeOutput(UserOwnedEntity)` in the model hierarchy. Neither inherits from `Submission` or `ExerciseReport`.

| EntityType | Class | ContentOrigin | Description |
|------------|-------|---------------|-------------|
| `JE_INPUT` | `JeInput(UserOwnedEntity)` | `USER_CREATED` | User-uploaded journal entry (voice/text) |
| `JE_OUTPUT` | `JeOutput(UserOwnedEntity)` | `USER_CREATED` | LLM-transformed journal output |

**Key insight:** Journal is NOT a submission subtype. It is a standalone domain with its own models in `core/models/journal/` and its own service. The relationship between input and output is `(JeOutput)-[:TRANSFORMS]->(JeInput)` (not `REPORT_FOR`).

**Pipeline:** JE_INPUT(audio) → Deepgram → JE_INPUT(text) → LLM → JE_OUTPUT

## Multi-Modal Journal Processing

Journals support **three modes** with weighted distribution:

| Mode | Weight Field | Purpose | Output Format |
|------|--------------|---------|---------------|
| **Activity Tracking** | `activity` | Extract tasks, habits, goals via DSL | Structured with `@context()` tags preserved |
| **Idea Articulation** | `articulation` | Verbatim preservation, minimal editing | Clean paragraphs with original voice |
| **Critical Thinking** | `exploration` | Question-organized exploration | Question threads with alternatives |

**Weight Distribution:**
- Each journal has weights (0.0-1.0) for all three modes
- Weights sum to 1.0 (e.g., 0.8 activity + 0.1 articulation + 0.1 exploration)
- Primary mode (highest weight) determines formatter
- LLM infers weights from content (or user declares mode explicitly)

## Processing Pipeline

```
1. JeInput created (voice or text upload)
   ├─ Audio: Deepgram transcription → text stored on JeInput
   └─ Text: stored directly on JeInput

2. LLM processing via JournalOutputService
   ├─ Read enrichment_mode: EnrichmentMode from instructions (ACTIVITY_TRACKING / IDEA_ARTICULATION / CRITICAL_THINKING)
   ├─ JournalOutputService.process_je_input(content, enrichment_mode, input_uid) → formatted content
   │  ├─ activity_formatter.md → structured DSL format
   │  ├─ articulation_formatter.md → verbatim preservation
   │  └─ exploration_formatter.md → question-organized
   ├─ Save je_output file → {SKUEL_JOURNAL_STORAGE}/{YYYY-MM}/journal_{uid}_output.md
   ├─ Extract activities (if enrichment_mode == EnrichmentMode.ACTIVITY_TRACKING) → DSL activity extractor
   └─ Create JeOutput entity with TRANSFORMS relationship to JeInput

3. Human decomposition (post-processing)
   ├─ Download je_output file
   ├─ Curate and refine content
   ├─ Ingest pieces into Neo4j via UnifiedIngestionService
   └─ Cleanup je_output files
```

## Graph Relationships

```cypher
// Journal pipeline
(user:User)-[:OWNS]->(input:Entity:JeInput {entity_type: 'je_input'})
(user:User)-[:OWNS]->(output:Entity:JeOutput {entity_type: 'je_output'})
(output)-[:TRANSFORMS]->(input)
```

## Service Architecture

### JournalInputService

**Location:** `/core/services/journal/journal_input_service.py`
**Protocol:** `JournalInputOperations` in `/core/ports/journal_protocols.py`

Standalone facade for JeInput CRUD and file upload. Handles text entries and file uploads (audio/text), saves files to `{SKUEL_JOURNAL_STORAGE}/{YYYY-MM}/je_input_{uid}.{ext}`, auto-generates sequential titles, and publishes `JeInputCreated`/`JeInputDeleted` events.

**8 methods:** `create_journal_entry()`, `submit_journal_file()`, `get_je_input()`, `list_je_inputs()`, `get_je_inputs_by_date_range()`, `make_permanent()`, `delete_je_input()`, `generate_journal_title()`

Always available (no LLM dependency). Wired as `journal_input` in Services.

### JournalOutputService

**Location:** `/core/services/journal/journal_output_service.py`
**Protocol:** `JournalOutputOperations` in `/core/ports/journal_protocols.py`

LLM processing pipeline: JeInput(text) → InstructionResolver → LLM → file on disk → JeOutput in Neo4j. Conditional on `INTELLIGENCE_TIER=full` (requires LLM). Wired as `journal_output_service` in `SubmissionsProcessingService` and as `journal_generator` in `Services` dataclass.

**Formatter Prompts:**
- `/core/prompts/templates/journal_activity.md`
- `/core/prompts/templates/journal_articulation.md`
- `/core/prompts/templates/journal_exploration.md`

### Batch Transcription Pipeline

Two-tier batch pipeline for processing multiple audio files:

**Tier 1 — BatchTranscriptionService:** Audio folder → .txt transcripts via Deepgram.
**Tier 2 — BatchProcessingService:** .txt transcripts → .md via LLM.

## Key Files

| Component | Location |
|-----------|----------|
| **Models** | |
| JeInput Model | `/core/models/journal/je_input.py` |
| JeOutput Model | `/core/models/journal/je_output.py` |
| EntityType | `EntityType.JE_INPUT`, `EntityType.JE_OUTPUT` in `/core/models/enums/entity_enums.py` |
| **Services** | |
| Input Service | `/core/services/journal/journal_input_service.py` |
| Output Service | `/core/services/journal/journal_output_service.py` |
| Protocols | `/core/ports/journal_protocols.py` |
| Events | `/core/events/journal_events.py` |
| Batch Transcription (Tier 1) | `/core/services/transcription/batch_transcription_service.py` |
| Batch Processing (Tier 2) | `/core/services/transcription/batch_processing_service.py` |
| **Prompts** | |
| Activity Formatter | `/core/prompts/templates/journal_activity.md` |
| Articulation Formatter | `/core/prompts/templates/journal_articulation.md` |
| Exploration Formatter | `/core/prompts/templates/journal_exploration.md` |

## Design Principles

1. **Analog Coding:** je_output files are waypoints, not destinations
2. **Human Curation:** AI formats, human curates and decomposes
3. **Multi-Modal Flexibility:** One journal can mix all three modes
4. **Threshold-Based Extraction:** Only extract activities when weight is significant
5. **Transparent Processing:** LLM prompts visible in `/prompts/` directory
6. **Separation of Concerns:** Journals generate files, Askesis handles discussion

## Search Exclusion — Pedagogical Philosophy

JE_INPUT and JE_OUTPUT are **intentionally excluded** from SKUEL's unified search infrastructure (`SEARCH_FIELD_CONFIG`). This is not a gap — it is a deliberate design decision rooted in SKUEL's pedagogy.

**The journal is the user's private reflective space.** Unlike exercises (teacher-assigned, externally evaluated) or KUs (curated, shared knowledge), journals are self-initiated and self-interpreted. The user — not the system — is the authority on what their journal means. Making journals searchable would shift the locus of interpretation from the user to the system, undermining the pedagogical intent of self-directed learning and self-assessment.

**Journal outputs are waypoints, not destinations.** After the user downloads and reviews their je_output files, they curate and decompose the valuable pieces manually. Those refined pieces are then ingested into Neo4j via `UnifiedIngestionService` — at which point they become searchable as Kus, PathSteps, or other entity types. The journal itself remains raw material for the user's own reflective practice.

This design supports SKUEL's core belief that **the ability to assess oneself is a skill worth developing**, and that skill is undermined when the system pre-processes or indexes private reflection on the user's behalf.

## Migration History

### March 2026: Journal Domain Extraction

- **Before:** Journals were `JournalSubmission(Submission)` and `JournalReport(ExerciseReport)` — subtypes under the submissions/reports hierarchy
- **After:** Journals are a standalone domain with `JeInput(UserOwnedEntity)` and `JeOutput(UserOwnedEntity)`
- **Reason:** Journals have a fundamentally different lifecycle (input → transform → output) compared to the exercise submission pipeline (submit → evaluate → report)
- **Service renamed:** `JournalOutputGenerator` → `JournalOutputService`; `JournalsCoreService` removed (journal delegation removed from SubmissionsCoreService)
- **JournalInputService** built to implement `JournalInputOperations` protocol — CRUD + file upload for JeInput entities, replacing broken `submissions_core_service.submit_journal_file()` call path
- **Models moved:** `core/models/submissions/` → `core/models/journal/`
- **Relationship:** `REPORT_FOR` → `TRANSFORMS`

### February 2026: Journal → Reports Merge (superseded)

- Journals were merged into the submission/report hierarchy as `:Report` nodes
- This was superseded by the March 2026 standalone extraction

## Deepgram Configuration

All Deepgram transcription options are controlled via `config/deepgram.toml`.

**See:** [Deepgram Configuration Guide](/docs/configuration/DEEPGRAM_CONFIG.md)
**See:** [Audio Transcription Architecture](/docs/architecture/AUDIO_TRANSCRIPTION_ARCHITECTURE.md)

## See Also

- [Entity Type Architecture](/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md) - JeInput + JeOutput standalone domain section
- [Activity DSL](/docs/dsl/DSL_SPECIFICATION.md) - `@context()` tag specification
- [UnifiedIngestionService](/docs/patterns/UNIFIED_INGESTION_GUIDE.md) - Post-curation ingestion
