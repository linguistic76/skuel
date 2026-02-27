---
title: Assignments PIPELINE
updated: 2026-01-21
status: implemented
category: architecture
tags: [architecture, assignments, pipeline, transcription, journals, two-tier]
related: [ADR-019-transcription-service-standalone]
---

> **Note:** As of 2026-02-06, the Assignments domain has been renamed to Reports. See `/docs/domains/submissions.md`.
>
> **Note (2026-02-09):** Reports now includes PROGRESS (system-generated) and ASSESSMENT (teacher-authored) report types, plus `ReportScheduleService` for recurring progress generation. This document covers the original file submission pipeline only.

## Implementation Status (January 2026)

| Component | Status | Location |
|-----------|--------|----------|
| AssignmentsSubmissionService | ✅ Implemented | `/core/services/assignments/assignments_submission_service.py` |
| AssignmentsProcessingService | ✅ Implemented | `/core/services/assignments/assignments_processing_service.py` |
| AssignmentsCoreService | ✅ Implemented | `/core/services/assignments/assignments_core_service.py` |
| AssignmentsSearchService | ✅ Implemented | `/core/services/assignments/assignments_search_service.py` |
| AssignmentsRelationshipService | ✅ Implemented | `/core/services/assignments/assignments_relationship_service.py` |
| ContentEnrichmentService | ✅ Implemented | AI transcript formatting |
| `/assignments` UI | ✅ Implemented | Comprehensive dashboard |
| `/journals` UI | ✅ Implemented | Focused journal submission |
| Human review queue | 🔄 Planned | Future enhancement |

### Service Package Structure (January 2026)

All assignment services are now consolidated under `/core/services/assignments/`:

```
/core/services/assignments/
├── __init__.py                          # Package exports + documentation
├── assignments_core_service.py          # Content management (categories, tags, bulk ops)
├── assignments_processing_service.py    # Processing orchestration (audio, text)
├── assignments_relationship_service.py  # Graph relationship creation
├── assignments_search_service.py        # Query and search operations
└── assignments_submission_service.py    # File upload and storage
```

## Architecture: File Submission Pipeline

### Core Principle: "Assignments, Not Journals"

**Mental Model**:
- **Assignment**: Any file submitted for processing (audio, text, PDF, video, image, etc.)
- **Journal**: One TYPE of assignment (a daily diary entry)
- **Processing**: Human review OR LLM transformation OR both

### The Two-Part System

#### Part 1: File Submission & Processing Pipeline

```
User Uploads File (any type)
    ↓
AssignmentSubmissionService
    ├─ Store file (local/S3)
    ├─ Create Assignment record (status: SUBMITTED)
    └─ Route to appropriate processor
        ↓
ProcessingRouter
    ├─ Audio files → TranscriptionService → LLM formatting
    ├─ Text files → DirectProcessor (optional LLM)
    ├─ PDFs → OCRProcessor → LLM extraction
    ├─ Images → VisionProcessor → LLM analysis
    └─ Manual review → HumanProcessor (queue for user)
        ↓
ProcessingResult
    ├─ Update Assignment status (PROCESSING → COMPLETED)
    ├─ Store processed output
    └─ Notify user
        ↓
Return to User
```

#### Part 2: Dual-Route UI Structure (Implemented December 2025)

**Two UI entry points for different use cases:**

```
/assignments (comprehensive dashboard)
    ├─ File Upload Form
    │   ├─ All file types supported
    │   ├─ Type selector (journal, transcript, report, etc.)
    │   └─ Processor selector (automatic, LLM, human)
    │
    ├─ Assignments Grid
    │   ├─ Status badges (SUBMITTED, PROCESSING, COMPLETED, FAILED)
    │   ├─ Filter by type and status
    │   └─ View/download actions
    │
    └─ Detail View (/assignments/{uid})
        ├─ Metadata display
        └─ Processed content viewer

/journals (two-tier journal submission - December 2025)
    │
    ├── [Tab 1] Voice Journals (PJ1 - Ephemeral)
    │   ├─ Audio file upload only
    │   ├─ Max 3 stored (FIFO auto-cleanup)
    │   ├─ "Ephemeral" badge indicator
    │   └─ Recent voice journals (max 3)
    │
    └── [Tab 2] Curated Journals (PJ2 - Permanent)
        ├─ Text/Markdown upload (.txt, .md)
        ├─ Permanent storage (no limit)
        ├─ "Permanent" badge indicator
        └─ All curated journals list
```

**Route Relationship:**
| Route | Focus | Assignment Type |
|-------|-------|-----------------|
| `/assignments` | All file types | User selects |
| `/journals` (Voice tab) | Audio journals | `JOURNAL_VOICE` (ephemeral) |
| `/journals` (Curated tab) | Text/MD journals | `JOURNAL_CURATED` (permanent) |

**Implementation Files:**
- `/adapters/inbound/assignments_ui.py` - Comprehensive dashboard
- `/adapters/inbound/journals_ui.py` - Focused journal interface
- Both use same backend: `AssignmentsSubmissionService` (from `/core/services/assignments/`)

## Service Architecture (Implemented)

### 1. AssignmentsSubmissionService

**Responsibility**: Handle file uploads and initial storage

```python
class AssignmentsSubmissionService:
    """
    Generic file submission handler.
    Location: /core/services/assignments/assignments_submission_service.py

    Supports:
    - Audio files (.mp3, .wav, .m4a)
    - Text files (.txt, .md)
    - PDFs (.pdf)
    - Images (.jpg, .png)
    - Videos (.mp4)
    """

    async def submit_file(
        self,
        file: UploadFile,
        user_uid: str,
        assignment_type: AssignmentType,  # JOURNAL, TRANSCRIPT, REPORT, etc.
        metadata: dict[str, Any] | None = None
    ) -> Result[Assignment]:
        """Store file and create assignment record"""
        pass

    async def get_assignment(self, uid: str) -> Result[Assignment]:
        """Retrieve assignment by UID"""
        pass

    async def list_assignments(
        self,
        user_uid: str,
        status: AssignmentStatus | None = None,
        assignment_type: AssignmentType | None = None
    ) -> Result[list[Assignment]]:
        """List user's assignments with filters"""
        pass
```

**Domain Model** (`/core/models/assignment/assignment.py`):

```python
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

class AssignmentType(str, Enum):
    # Legacy
    JOURNAL = "journal"           # Daily diary entry (legacy)

    # Two-tier journal system (December 2025)
    JOURNAL_VOICE = "journal_voice"       # PJ1: Ephemeral, max 3, audio
    JOURNAL_CURATED = "journal_curated"   # PJ2: Permanent, text/markdown

    # Standard types
    TRANSCRIPT = "transcript"     # Audio transcription
    REPORT = "report"             # Document processing
    IMAGE_ANALYSIS = "image_analysis"
    VIDEO_SUMMARY = "video_summary"

class AssignmentStatus(str, Enum):
    SUBMITTED = "submitted"       # File uploaded, not yet processed
    QUEUED = "queued"             # In processing queue
    PROCESSING = "processing"     # Currently being processed
    COMPLETED = "completed"       # Processing finished
    FAILED = "failed"             # Processing error
    MANUAL_REVIEW = "manual_review"  # Awaiting human review

class ProcessorType(str, Enum):
    LLM = "llm"                   # AI/LLM processing
    HUMAN = "human"               # Manual human review
    HYBRID = "hybrid"             # LLM + human review

@dataclass(frozen=True)
class Assignment:
    uid: str
    user_uid: str
    assignment_type: AssignmentType
    status: AssignmentStatus

    # File info
    original_filename: str
    file_path: str                # Storage location
    file_size: int
    file_type: str                # MIME type

    # Processing info
    processor_type: ProcessorType
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None
    processing_error: str | None = None

    # Output
    processed_content: str | None = None
    processed_file_path: str | None = None

    # Metadata
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] | None = None
```

### 2. AssignmentsProcessingService

**Responsibility**: Route assignments to appropriate processors

```python
class AssignmentsProcessingService:
    """
    Orchestrates processing of submitted files.
    Location: /core/services/assignments/assignments_processing_service.py

    Routes assignments to:
    - LLM processors (OpenAI, Anthropic)
    - Human review queues
    - Specialized processors (OCR, transcription, vision)
    """

    def __init__(
        self,
        transcription_service: TranscriptionService,  # Simplified Dec 2025
        llm_processor: LLMFormattingProcessor,
        human_processor: HumanReviewProcessor,
        ocr_processor: OCRProcessor | None = None,
        vision_processor: VisionProcessor | None = None
    ):
        self.processors = {
            "audio": transcription_service,  # TranscriptionService handles audio → text
            "llm": llm_processor,
            "human": human_processor,
            "ocr": ocr_processor,
            "vision": vision_processor
        }

    async def process_assignment(
        self,
        assignment_uid: str,
        processor_type: ProcessorType,
        instructions: dict[str, Any] | None = None
    ) -> Result[Assignment]:
        """
        Process an assignment using specified processor.

        Updates assignment status throughout:
        SUBMITTED → PROCESSING → COMPLETED (or FAILED)
        """
        pass

    async def reprocess_assignment(
        self,
        assignment_uid: str,
        new_instructions: dict[str, Any]
    ) -> Result[Assignment]:
        """Reprocess with different instructions/processor"""
        pass
```

### 3. JournalsService (Simplified)

**New Responsibility**: ONLY manage journal content (a specific assignment type)

```python
class JournalsService:
    """
    Content management for journal-type assignments.

    Does NOT handle:
    - File uploads (AssignmentSubmissionService)
    - Processing (ProcessingPipelineService)
    - Transcription (TranscriptionService)

    ONLY handles:
    - Journal-specific queries (by date, mood, category)
    - Journal-specific operations (tagging, categorization)
    - Journal-specific analytics
    """

    async def get_journal_for_date(
        self,
        user_uid: str,
        date: date
    ) -> Result[Assignment | None]:
        """Get journal entry for specific date"""
        pass

    async def get_journals_by_mood(
        self,
        user_uid: str,
        mood: str,
        start_date: date | None = None,
        end_date: date | None = None
    ) -> Result[list[Assignment]]:
        """Query journals by mood"""
        pass

    async def get_writing_statistics(
        self,
        user_uid: str,
        start_date: date,
        end_date: date
    ) -> Result[dict[str, Any]]:
        """Analytics for journaling habits"""
        pass
```

## UI Restructuring


### After (Clean `/assignments` dashboard)

```
┌─────────────────────────────────────────────┐
│  Assignments Dashboard                      │
├─────────────────────────────────────────────┤
│  Tabs: [Submitted] [Processing] [Completed] │
├─────────────────────────────────────────────┤
│  Quick Actions:                             │
│  [Upload File ▼]                            │  ← Dropdown for all file types
│    ├─ Audio (journal/transcript)           │
│    ├─ Text (journal/notes)                  │
│    ├─ PDF (report/document)                 │
│    ├─ Image (analysis)                      │
│    └─ Video (summary)                       │
├─────────────────────────────────────────────┤
│  Submitted Tab:                             │
│  ┌─────────────────────────────────────┐   │
│  │ File Name     Type      Status      │   │
│  │ ───────────────────────────────────│   │
│  │ diary.mp3     JOURNAL   PROCESSING  │   │
│  │ notes.txt     JOURNAL   COMPLETED   │   │
│  │ report.pdf    REPORT    SUBMITTED   │   │
│  │ photo.jpg     IMAGE     QUEUED      │   │
│  └─────────────────────────────────────┘   │
├─────────────────────────────────────────────┤
│  Filter by: [All Types ▼] [All Status ▼]  │
└─────────────────────────────────────────────┘

Expanded Row View:
┌─────────────────────────────────────────────┐
│  File: diary.mp3 (JOURNAL, PROCESSING)      │
├─────────────────────────────────────────────┤
│  Uploaded: 2025-11-03 14:30                 │
│  Size: 2.4 MB                               │
│  Processor: LLM (Anthropic Claude)          │
│  Instructions: jp.transcript_default        │
├─────────────────────────────────────────────┤
│  Actions:                                   │
│  [View Original] [Download] [Reprocess]     │
│  [Change Instructions] [Delete]             │
└─────────────────────────────────────────────┘
```





All follow the same pattern: submit → process → retrieve.

## Questions for Consideration

1. **Human Review Workflow**: How should the "manual review queue" work?

A/ The assignment is submitted via a user and is then sent via a `post` function to a dashboard accessible by a user with a status such as admin or educator. The admin receives the sumbmitted files for manual review. When ready the admin submits the marked_assigmnment. The user has a dashboard of their Assignments where they can filter between marked_assignments and assignments (such as works in progress)
In my mind this provides us a robust space that serve an infrastructure designed to provide educational support services.

2. **Processing Instructions Storage**: Instructions are:

   - Per-assignment-type (journal uses X, transcript uses Y)

3. **File Storage**: Where should original files live?
   A/ Local filesystem (`/data/assignments/`)

4. **Backward Compatibility**:
A/ Do not maintain Backwards Compatibility

5. **Permission Model**: Who can process assignments?

   - Team collaboration (shared assignments)
