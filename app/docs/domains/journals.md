---
title: Journals Domain
created: 2025-12-04
updated: 2026-03-02
status: current
category: domains
tags: [journals, content-domain, submissions, multi-modal, ai-processing, lp-integration]
---

# Journals Domain

**Type:** Submission subtype (`EntityType.JOURNAL`, extends `Submission`)
**UID Prefix:** `journal_`
**Entity Label:** `:Entity:Journal`
**UI Route:** `/journals` (all authenticated users, registered via `submissions_routes.py`)
**API Route:** Reuses `/api/submissions/*` endpoints

## Domain Architecture (February 2026)

Journals are a **Submission subtype** — `Journal(Submission)` in the model hierarchy.

| EntityType | ProcessorType | Use Case |
|------------|---------------|----------|
| `JOURNAL` | `LLM` | User-uploaded AI-processed journal entries |
| `SUBMISSION` | `HUMAN` | User file uploads against an Exercise |

**Key insight:** Journal is NOT a separate domain. It is `EntityType.JOURNAL`, a distinct entity
type within the Submissions domain. The `/journals/*` UI is a domain-specific entry point;
route registration, services, and API all live inside submissions.

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
1. User uploads file → SubmissionsService.submit_file()
   ├─ entity_type: EntityType.JOURNAL
   └─ processor_type: ProcessorType.LLM

2. AI processing triggered → SubmissionsProcessingService.process_report()
   ├─ Audio: transcribe → process_journal()
   └─ Text: direct → process_journal()

3. Multi-modal pipeline → _process_journal()
   ├─ Read enrichment_mode from instructions (activity / articulation / exploration)
   ├─ JournalOutputGenerator.generate(content, enrichment_mode, journal_uid) → formatted content
   │  ├─ activity_formatter.md → structured DSL format
   │  ├─ articulation_formatter.md → verbatim preservation
   │  └─ exploration_formatter.md → question-organized
   ├─ Save je_output file → {SKUEL_JOURNAL_STORAGE}/{YYYY-MM}/journal_{uid}_output.md
   ├─ Extract activities (if enrichment_mode == 'activity_tracking') → DSL activity extractor
   └─ Store metadata → {enrichment_mode, je_output_path}

4. Human decomposition (post-processing)
   ├─ Download je_output file → /journals/{uid}/download
   ├─ Curate and refine content
   ├─ Ingest pieces into Neo4j via UnifiedIngestionService
   └─ Cleanup je_output files → /api/admin/journals/cleanup
```

## je_output Files

**Purpose:** Decomposable artifacts for human curation (analog coding philosophy)

**Storage:**
- Location: `SKUEL_JOURNAL_STORAGE` environment variable (default: `/tmp/skuel_journals`)
- Structure: `{storage}/{YYYY-MM}/report_{uid}_output.md`
- Format: Markdown with mode-specific formatting

**Lifecycle:**
1. Generated during AI processing
2. Downloaded by admin for curation
3. Cleaned up by admin after decomposition (by date range)

**Design Philosophy:** "Benefits gained via limiting scope—je_output is NOT the final destination, it's a waypoint for human decomposition."

## Three Formatters

### 1. Activity Tracking Formatter

**Purpose:** Extract actionable entities from journal content

**Format:**
```markdown
# Activity Journal - [Date]

## Tasks Identified
- [ ] [task description] @context(task) @priority(high) @when(2026-02-10)

## Habits
- [ ] [habit description] @context(habit) @frequency(daily)

## Goals
- [goal description] @context(goal) @target_date(2026-03-01)

## Events
- [event description] @context(event) @when(2026-02-15)

## Reflections
[Free-form reflection text]

## Extraction Summary
✅ Created X Tasks, Y Habits, Z Goals
```

**Behavior:**
- Preserves all `@context()`, `@priority()`, `@when()` tags EXACTLY
- Suggests tags for untagged actionable items
- Triggers `ActivityExtractorService` if weight > threshold (default: 0.2)

### 2. Idea Articulation Formatter

**Purpose:** Clean up verbatim thinking-out-loud transcripts

**Format:**
```markdown
# Ideas on [Topic] - [Date]

[Clean paragraphs with original ideas preserved]

---

[Natural section break when topic shifts]

---

## Key Concepts Mentioned
- [Concept 1]: [Brief note if helpful]
```

**Behavior:**
- **Minimal intervention:** Removes fillers ("um", "uh", "like"), fixes grammar
- **Preserves original:** Vocabulary choices, sentence structures, idea flow
- **No entity creation:** Just formatting—human curates later

### 3. Critical Thinking Formatter

**Purpose:** Organize exploratory questioning and alternatives

**Format:**
```markdown
# Critical Thinking Session - [Date]

## Core Questions

### 1. [First major question]?
[User's exploration of this question]
[Related thoughts, alternatives considered]

### 2. [Second major question]?
[User's exploration of this question]

---

## Tensions & Tradeoffs
- [Tension 1]: [Description]

## Alternatives Considered
- [Alternative A]: [Brief description]

## Open Questions
- [Question still unresolved]
```

**Behavior:**
- Extracts explicit and implicit questions
- Preserves uncertainty and open-endedness
- No forced conclusions—exploration stays exploratory

## Service Architecture

### JournalOutputGenerator

**Location:** `/core/services/submissions/journal_output_generator.py`

```python
class JournalOutputGenerator:
    async def generate(
        content: str,
        enrichment_mode: str,       # "activity_tracking" | "articulation" | "exploration"
        report_uid: str,
        custom_instructions: str | None = None
    ) -> Result[str]:
        # Selects formatter based on enrichment_mode
        # Saves to disk with date subdirectory
        # Returns file path

    def cleanup_date_range(
        start_date: datetime,
        end_date: datetime
    ) -> Result[dict[str, int]]:
        # Deletes je_output files from date range
        # Returns {files_deleted, bytes_freed}
```

**Formatter Prompts:**
- `/core/services/submissions/journal_prompts/activity_formatter.md`
- `/core/services/submissions/journal_prompts/articulation_formatter.md`
- `/core/services/submissions/journal_prompts/exploration_formatter.md`

### ActivityExtractorService

**Location:** `/core/services/dsl/activity_extractor.py`

```python
class ActivityExtractorService:
    async def extract_and_create(
        content: str,
        report_uid: str,
        user_uid: str
    ) -> Result[ExtractionSummary]:
        # Parses @context() tags
        # Creates entities: Tasks, Habits, Goals, Events, etc.
        # Returns summary: {tasks_created, habits_created, ...}
```

**Only triggered when:** `weights.activity > threshold` (default: 0.2)

## Routes

### UI Routes

| Route | Purpose |
|-------|---------|
| `/journals` | Landing page (redirects to `/journals/submit`) |
| `/journals/submit` | Upload form with Assignment selector |
| `/journals/browse` | AI-processed reports grid with filters |
| `/journals/{uid}/download` | Download je_output markdown file |

### API Routes

Journals reuse existing `/api/submissions/*` endpoints:

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/submissions/submit` | POST | Submit journal file (with report_type=JOURNAL) |
| `/api/submissions/{uid}` | GET | Get journal report |
| `/api/reports` | GET | List reports (filter by processor_type=LLM) |
| `/api/admin/journals/cleanup` | GET | Cleanup je_output files by date range |

### HTMX Endpoints

| Route | Purpose |
|-------|---------|
| `/journals/upload` | File upload with AI processing |
| `/journals/grid` | Reports grid with status filtering |

## Instruction Modes

Three ways to specify processing instructions:

| Mode | Selector Value | Behavior |
|------|----------------|----------|
| **Default** | `__default__` | Uses built-in `DEFAULT_INSTRUCTIONS` constant |
| **Existing project** | `{project_uid}` | Fetches Assignment from Neo4j |
| **Upload new** | `__upload__` | Uploads `.md` file → creates new Assignment |

**Assignment fields:**
- `instructions` (text): LLM processing instructions
- `scope` (PERSONAL/ASSIGNED): Personal AI templates or teacher assignments (ADR-040)
- `processor_type` (LLM/HUMAN): Processing mode
- `mode_threshold` (float): Activity extraction threshold (default: 0.2)

## Data Model

```python
from core.models.submissions.journal import Journal
from core.models.enums.entity_enums import EntityType, ProcessorType
from core.services.submissions.journal_output_generator import JournalOutputGenerator

@dataclass(frozen=True)
class Report:
    uid: str                          # report_{random}
    user_uid: str                     # Owner
    report_type: ReportType           # JOURNAL
    processor_type: ProcessorType     # LLM
    original_filename: str            # Uploaded file name
    file_size: int                    # File size in bytes
    status: str                       # submitted, processing, completed, failed
    metadata: dict[str, Any]          # {identifier, project_uid, journal_weights, je_output_path}
    content: str                      # Processed content
    created_at: datetime
    updated_at: datetime

@dataclass(frozen=True)
class JournalWeights:
    activity: float       # 0.0-1.0
    articulation: float   # 0.0-1.0
    exploration: float    # 0.0-1.0

    def get_primary_mode(self) -> JournalMode
    def should_extract_activities(self, threshold: float) -> bool
```

## Metadata Fields

When a journal is processed, these fields are stored in `report.metadata`:

| Field | Type | Description |
|-------|------|-------------|
| `identifier` | `str` | Knowledge Unit link (e.g., "meditation-basics") |
| `project_uid` | `str` | Assignment UID (or "__default__") |
| `journal_weights` | `dict` | `{activity: 0.7, articulation: 0.2, exploration: 0.1}` |
| `je_output_path` | `str` | Full path to generated je_output file |
| `mode_threshold` | `float` | Threshold used for activity extraction (default: 0.2) |

## User Workflows

### Workflow 1: Submit and Process

```
1. User → /journals/submit (or via "New Entry" in profile sidebar)
2. Select instructions mode (default, or upload custom instruction file)
3. Optionally enter a custom title (auto-generated if blank: "Journal — {user_id} — {Mar 02, 2026} — #1")
4. Upload file (audio, text, PDF, images, video)
5. System processes:
   - Transcribes if audio
   - Infers journal weights via LLM
   - Generates je_output file
   - Extracts activities if threshold met
6. User → /journals/browse ("My Journals") → sees completed entry with download button
```

### Workflow 2: Download and Curate

```
1. User → /journals/browse
2. Click "Download" on completed journal
3. Receives je_output markdown file
4. Curate and decompose content:
   - Extract specific KUs
   - Refine tasks/habits/goals
   - Create markdown files for ingestion
5. Ingest curated pieces via UnifiedIngestionService
```

### Workflow 3: Cleanup (Admin only)

```
1. Admin decides date range to clean (e.g., December 2025)
2. API call: POST /api/admin/journals/cleanup?start_date=2025-12-01&end_date=2025-12-31
3. System deletes je_output files from December 2025
4. Returns: {files_deleted: 45, bytes_freed: 2457600}
```

## Key Files

| Component | Location |
|-----------|----------|
| **Models** | |
| Domain Model | `/core/models/submissions/journal.py` |
| DTO | `/core/models/submissions/journal_dto.py` |
| Base (Submission) | `/core/models/submissions/submission.py` |
| EntityType | `EntityType.JOURNAL` in `/core/models/enums/entity_enums.py` |
| **Services** | |
| Output Generator | `/core/services/submissions/journal_output_generator.py` |
| Processing Service | `/core/services/submissions/submissions_processing_service.py` |
| Core CRUD | `/core/services/submissions/submissions_core_service.py` |
| **Prompts** | |
| Activity Formatter | `/core/services/submissions/journal_prompts/activity_formatter.md` |
| Articulation Formatter | `/core/services/submissions/journal_prompts/articulation_formatter.md` |
| Exploration Formatter | `/core/services/submissions/journal_prompts/exploration_formatter.md` |
| **Routes** | |
| UI Implementation | `/adapters/inbound/journals_ui.py` |
| Route Registration | `JOURNALS_CONFIG` in `/adapters/inbound/submissions_routes.py` |

## Environment Configuration

```bash
# Journal storage location (default: /tmp/skuel_journals)
SKUEL_JOURNAL_STORAGE=/path/to/journal/storage

# OpenAI API key (required for LLM processing)
OPENAI_API_KEY=sk-...
```

## Design Principles

1. **Analog Coding:** je_output files are waypoints, not destinations
2. **Human Curation:** AI formats, human curates and decomposes
3. **Multi-Modal Flexibility:** One journal can mix all three modes
4. **Threshold-Based Extraction:** Only extract activities when weight is significant
5. **Transparent Processing:** LLM prompts visible in `/prompts/` directory
6. **Separation of Concerns:** Journals generate files, Askesis handles discussion

## Migration History

### February 2026: Journal → Reports Merge

- **Before:** Journals were separate `:Journal` nodes
- **After:** Journals are `:Report` nodes with `report_type=JOURNAL`
- **Reason:** Unified processing pipeline (LLM vs HUMAN) more important than entity type

### January 2026: Two-Tier System (Voice/Curated)

- Temporary architecture with FIFO cleanup for voice journals
- Deprecated in February merge

## See Also

- [Reports Domain](reports.md) - Parent domain for all submissions
- [Activity DSL](/docs/dsl/DSL_SPECIFICATION.md) - `@context()` tag specification
- [ADR-040: Teacher Assignment Workflow](/docs/decisions/ADR-040-teacher-assignment-workflow.md) - Assignment dual purpose
- [UnifiedIngestionService](/docs/patterns/UNIFIED_INGESTION_GUIDE.md) - Post-curation ingestion
