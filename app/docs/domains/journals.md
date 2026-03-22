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
**Service:** `core/services/journal/journal_output_service.py`

## Domain Architecture (March 2026)

Journal is a **standalone domain** — `JeInput(UserOwnedEntity)` and `JeOutput(UserOwnedEntity)` in the model hierarchy. Neither inherits from `Submission` or `SubmissionReport`.

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
   ├─ Read enrichment_mode from instructions (activity / articulation / exploration)
   ├─ JournalOutputService.generate(content, enrichment_mode, input_uid) → formatted content
   │  ├─ activity_formatter.md → structured DSL format
   │  ├─ articulation_formatter.md → verbatim preservation
   │  └─ exploration_formatter.md → question-organized
   ├─ Save je_output file → {SKUEL_JOURNAL_STORAGE}/{YYYY-MM}/journal_{uid}_output.md
   ├─ Extract activities (if enrichment_mode == 'activity_tracking') → DSL activity extractor
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

### JournalOutputService

**Location:** `/core/services/journal/journal_output_service.py`

Replaces the former `JournalOutputGenerator` (which lived under submissions). Handles LLM-based formatting of journal content.

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
| Output Service | `/core/services/journal/journal_output_service.py` |
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

## Migration History

### March 2026: Journal Domain Extraction

- **Before:** Journals were `JournalSubmission(Submission)` and `JournalReport(SubmissionReport)` — subtypes under the submissions/reports hierarchy
- **After:** Journals are a standalone domain with `JeInput(UserOwnedEntity)` and `JeOutput(UserOwnedEntity)`
- **Reason:** Journals have a fundamentally different lifecycle (input → transform → output) compared to the exercise submission pipeline (submit → evaluate → report)
- **Service renamed:** `JournalOutputGenerator` → `JournalOutputService`; `JournalsCoreService` removed (journal delegation removed from SubmissionsCoreService)
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
