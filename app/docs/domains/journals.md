---
title: Journals Domain
created: 2025-12-04
updated: 2026-01-21
status: current
category: domains
tags: [journals, content-domain, domain, voice, curated, two-tier, domain-separation]
---

# Journals Domain

**Type:** Content/Organization Domain (1 of 3)
**UID Prefix:** `journal:`
**Entity Label:** `Journal` (standalone domain)
**UI Route:** `/journals`
**API Route:** `/api/journals/*`

## Domain Separation (January 2026)

Journals are now a **separate domain** from Reports:

| Domain | Entity | Purpose |
|--------|--------|---------|
| **Journals** | `:Journal` | Personal reflections, metacognition, LLM feedback |
| **Reports** | `:Report` | File submission, processing, transcripts, reports |

This separation provides:
- Clean graph model (no type discriminator needed)
- Independent FIFO cleanup for voice journals
- Dedicated JournalsCoreService for journal operations
- Clear domain boundaries

## Purpose

Journals handle **personal reflections and metacognition** through a **two-tier system**:

| Tier | Name | Input | Retention | Type |
|------|------|-------|-----------|------|
| **PJ1** | Voice Journals | Audio → transcript | Ephemeral (max 3, FIFO) | `JournalType.VOICE` |
| **PJ2** | Curated Journals | Text/Markdown | Permanent | `JournalType.CURATED` |

**Design Philosophy:**
- **PJ1 (Voice)**: Quick capture, auto-cleaned to prevent Neo4j clutter
- **PJ2 (Curated)**: Intentional, refined content worth preserving permanently

## Routes

### UI Routes

| Route | Type | Purpose |
|-------|------|---------|
| `/journals` | UI | Two-tier dashboard with tabs |
| `/journals/upload/voice` | HTMX | Voice journal upload (PJ1) |
| `/journals/upload/curated` | HTMX | Curated journal upload (PJ2) |
| `/journals/recent/voice` | HTMX | Voice journals list (max 3) |
| `/journals/recent/curated` | HTMX | Curated journals list |

### API Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/journals/voice` | POST | Create voice journal |
| `/api/journals/curated` | POST | Create curated journal |
| `/api/journals` | GET | List all journals |
| `/api/journals/voice` | GET | List voice journals (max 3) |
| `/api/journals/curated` | GET | List curated journals |
| `/api/journals/{uid}` | GET | Get specific journal |
| `/api/journals/{uid}` | PUT | Update journal |
| `/api/journals/{uid}` | DELETE | Delete journal |
| `/api/journals/search` | POST | Search journals |
| `/api/journals/date-range` | GET | Get journals by date range |
| `/api/journals/{uid}/promote` | POST | Promote voice to curated |

## Two-Tier System

### PJ1: Voice Journals (Ephemeral)

- **Input:** Audio files transcribed to text
- **Storage:** `:Journal` node with `journal_type=voice`
- **Retention:** Max 3 per user
- **Cleanup:** FIFO auto-delete via `enforce_voice_journal_fifo()`
- **Cleanup scope:** Neo4j node only (no file storage)

**Use case:** Quick voice capture, brainstorming, raw thoughts.

### PJ2: Curated Journals (Permanent)

- **Input:** Text/Markdown content
- **Storage:** `:Journal` node with `journal_type=curated`
- **Retention:** Permanent (no limit)
- **Cleanup:** None (manual delete only)

**Use case:** Intentional reflection, edited content, permanent entries.

## Data Model

```python
from core.models.report.report import Report
from core.models.enums.report_enums import JournalType

class JournalType(str, Enum):
    VOICE = "voice"      # PJ1: Ephemeral
    CURATED = "curated"  # PJ2: Permanent

# Note: JournalPure merged into Report (February 2026)
# Report is a frozen dataclass
@dataclass(frozen=True)
class Report:
    uid: str
    user_uid: str
    title: str
    content: str
    journal_type: JournalType
    entry_date: date
    mood: str | None
    energy_level: int | None
    key_topics: list[str]
    # ... additional fields
```

## FIFO Cleanup Implementation

Location: `JournalsCoreService.create_journal()`

```python
# Create with FIFO enforcement for voice journals
result = await journals_core.create_journal(journal, enforce_fifo=True)

# enforce_fifo=True triggers:
await self.enforce_voice_journal_fifo(user_uid, max_count=3)
```

The `enforce_voice_journal_fifo()` method:
1. Counts current voice journals for user
2. If count > max, deletes oldest (by created_at)
3. Deletes Neo4j node (journals don't store files)

## Key Files

| Component | Location |
|-----------|----------|
| **Services** | `/core/services/journals/` |
| Core Service | `/core/services/journals/journals_core_service.py` |
| Feedback Service | `/core/services/journals/journal_feedback_service.py` |
| Project Service | `/core/services/reports/report_project_service.py` (migrated to Reports) |
| Relationship Service | `/core/services/journals/journal_relationship_service.py` |
| Types | `/core/services/journals/journals_types.py` |
| **Models** | `/core/models/report/` |
| Domain Model | `/core/models/report/report.py` |
| DTOs | `/core/models/report/report_dto.py` |
| Converters | `/core/models/report/report_converters.py` |
| **Routes** | |
| API Routes | `/adapters/inbound/journals_api.py` |
| UI Routes | `/adapters/inbound/journals_ui.py` |
| **Enums** | `/core/models/enums/journal_enums.py` |

## Model Fields (Report)

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Unique identifier (journal:{user}:{timestamp}) |
| `user_uid` | `str` | Owner user |
| `title` | `str` | Journal title |
| `content` | `str` | Journal content |
| `journal_type` | `JournalType` | VOICE or CURATED |
| `entry_date` | `date` | Date of entry |
| `mood` | `str?` | Mood indicator |
| `energy_level` | `int?` | Energy level (1-10) |
| `key_topics` | `list[str]` | Extracted topics |
| `category` | `str?` | Journal category |
| `tags` | `list[str]` | User-defined tags |
| `created_at` | `datetime` | Creation timestamp |
| `updated_at` | `datetime` | Last update |

## Service Architecture

**Package:** `/core/services/journals/`

```
/core/services/journals/
├── __init__.py                      # Package exports
├── journals_core_service.py         # CRUD, FIFO cleanup, search
├── journal_feedback_service.py      # AI feedback generation
├── (deleted)                        # Project CRUD → core/services/reports/report_project_service.py
├── journal_relationship_service.py  # Graph relationships
└── journals_types.py                # AI processing types
```

### JournalsCoreService

```
JournalsCoreService (BaseService)
├── create_journal(journal, enforce_fifo)
├── get_journal(uid)
├── update_journal(uid, updates)
├── delete_journal(uid)
├── get_voice_journals(user_uid, limit)
├── get_curated_journals(user_uid, limit)
├── get_journals_by_type(user_uid, type, limit)
├── get_journals_by_date_range(user_uid, start, end, type, limit)
├── search_journals(query, user_uid, type, limit)
├── promote_to_curated(uid)
└── _enforce_voice_journal_fifo(user_uid)
```

### JournalFeedbackService

Generates AI feedback using transparent, user-controlled projects.

```
JournalFeedbackService
├── generate_feedback(entry, project, temperature, max_tokens)
├── get_supported_models() -> dict[provider, models]
└── is_model_supported(model) -> bool
```

### ReportProjectService (migrated to Reports domain)

CRUD for Report Projects (Claude/ChatGPT-style instruction sets).
Now lives at `core/services/reports/report_project_service.py`.

```
ReportProjectService (BaseService)
├── create_project(user_uid, name, instructions, model, ...)
├── get_project(uid)
├── list_user_projects(user_uid, active_only)
├── update_project(uid, ...)
├── delete_project(uid)
├── deactivate_project(uid)
├── load_project_from_file(file_path, user_uid, ...)
├── list_group_assignments(group_uid)
└── get_student_assignments(user_uid)
```

### JournalRelationshipService

Direct driver pattern for graph relationships.

```
JournalRelationshipService
├── get_related_journals(journal_uid)
├── get_supported_goals(journal_uid)
├── has_related_journals(journal_uid)
├── supports_goals(journal_uid)
├── count_related_journals(journal_uid)
├── count_supported_goals(journal_uid)
├── get_journal_summary(journal_uid)
├── get_journals_related_to(journal_uid)
├── get_journals_supporting_goal(goal_uid)
└── create_journal_relationships(journal_uid, related_uids, goal_uids)
```

## UI Layout

Tab-based interface:

```
/journals
├── [Tab] Voice Journals
│   ├── Upload Form (audio → transcript)
│   ├── "Ephemeral" badge
│   └── Recent (max 3)
│
└── [Tab] Curated Journals
    ├── Create Form (text/markdown)
    ├── "Permanent" badge
    └── All Curated Journals
```

## Migration from Report-Based Storage

Prior to January 2026, journals were stored as Report nodes with type discriminator.
Now journals are standalone `:Journal` nodes.

**Changes:**
- No more `ReportType.JOURNAL`, `JOURNAL_VOICE`, `JOURNAL_CURATED`
- `JournalsCoreService` replaces journal methods in `ReportsCoreService`
- Graph queries use `:Journal` label instead of `:Report` with type filter
- FIFO cleanup moved from `ReportSubmissionService` to `JournalsCoreService`

## See Also

- [Reports Domain](reports.md) - File submission and processing (separate domain)
- [Domain Separation ADR](/docs/decisions/) - Architecture decision record
