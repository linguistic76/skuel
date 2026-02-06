---
title: Reports Domain
created: 2025-12-04
updated: 2026-02-06
status: current
category: domains
tags: [reports, processing-domain, domain]
---

# Reports Domain

**Type:** Content/Organization Domain (2 of 3)
**UID Prefix:** `report:`
**Entity Label:** `Report`
**UI Route:** `/reports`

## Purpose

Reports provide the user-facing interface for file uploads and AI processing. They orchestrate the Journal processing pipeline and present results to users.

## Routes

| Route | Type | Purpose |
|-------|------|---------|
| `/reports` | UI | Comprehensive file upload dashboard (all types) |
| `/journals` | UI | Two-tier journal submission (voice + curated) |
| `/api/reports/upload` | API | File upload endpoint |
| `/api/reports` | API | List reports |

## Key Commitment

**Reports is the primary user-facing interface for file processing.** The `/journals` route provides a focused two-tier alternative for journal-type entries.

**Relationship between routes:**
- `/reports` = All file types (comprehensive)
- `/journals` = Two-tier journal system (voice: ephemeral, curated: permanent)

## Key Files

| Component | Location |
|-----------|----------|
| **Service Package** | `/core/services/reports/` |
| Submission Service | `/core/services/reports/reports_submission_service.py` |
| Processing Service | `/core/services/reports/reports_processing_service.py` |
| Core Service | `/core/services/reports/reports_core_service.py` |
| Search Service | `/core/services/reports/reports_search_service.py` |
| Relationship Service | `/core/services/reports/reports_relationship_service.py` |
| **Model** | `/core/models/report/report.py` |
| **Routes** | |
| Reports UI | `/adapters/inbound/reports_ui.py` |
| Journals UI | `/adapters/inbound/journals_ui.py` |
| API Routes | `/adapters/inbound/reports_api.py` |

## Model Fields

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Unique identifier |
| `user_uid` | `str` | Owner user |
| `title` | `str` | Report title |
| `description` | `str?` | Report description |
| `file_paths` | `list[str]` | Uploaded file paths |
| `status` | `ReportStatus` | Draft, Submitted, Processing, Complete |
| `processing_results` | `dict?` | Results from Journal processing |
| `created_entities` | `list[str]` | UIDs of created entities |
| `created_at` | `datetime` | Creation timestamp |
| `submitted_at` | `datetime?` | Submission timestamp |
| `completed_at` | `datetime?` | Completion timestamp |

## Processing Flow

```
User → Uploads Files → Report
                          ↓
              JournalCoreService (AI processing)
                          ↓
              JournalAIInsights returned
                          ↓
              Report creates entities
                          ↓
              User sees results
```

## Entity Creation

Reports can create entities in any domain based on AI insights:

- Tasks
- Goals
- Habits
- Events
- Choices
- Principles
- KUs

## Relationships

| Relationship | Direction | Target | Description |
|--------------|-----------|--------|-------------|
| `CREATED` | Outgoing | Any Entity | Entities created from report |
| `PROCESSED_BY` | Outgoing | Journal | Journal that processed |
| `SUBMITTED_BY` | Incoming | User | User who submitted |

## See Also

- [Journals Domain](journals.md) - Backend processor
- [Reports Pipeline](../architecture/reports_PIPELINE.md)
