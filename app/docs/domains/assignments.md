---
title: Assignments Domain
created: 2025-12-04
updated: 2026-01-21
status: current
category: domains
tags: [assignments, processing-domain, domain]
---

# Assignments Domain

**Type:** Content/Organization Domain (2 of 3)
**UID Prefix:** `assignment:`
**Entity Label:** `Assignment`
**UI Route:** `/assignments`

## Purpose

Assignments provide the user-facing interface for file uploads and AI processing. They orchestrate the Journal processing pipeline and present results to users.

## Routes

| Route | Type | Purpose |
|-------|------|---------|
| `/assignments` | UI | Comprehensive file upload dashboard (all types) |
| `/journals` | UI | Two-tier journal submission (voice + curated) |
| `/api/assignments/upload` | API | File upload endpoint |
| `/api/assignments` | API | List assignments |

## Key Commitment

**Assignments is the primary user-facing interface for file processing.** The `/journals` route provides a focused two-tier alternative for journal-type entries.

**Relationship between routes:**
- `/assignments` = All file types (comprehensive)
- `/journals` = Two-tier journal system (voice: ephemeral, curated: permanent)

## Key Files

| Component | Location |
|-----------|----------|
| **Service Package** | `/core/services/assignments/` |
| Submission Service | `/core/services/assignments/assignments_submission_service.py` |
| Processing Service | `/core/services/assignments/assignments_processing_service.py` |
| Core Service | `/core/services/assignments/assignments_core_service.py` |
| Search Service | `/core/services/assignments/assignments_search_service.py` |
| Relationship Service | `/core/services/assignments/assignments_relationship_service.py` |
| **Model** | `/core/models/assignment/assignment.py` |
| **Routes** | |
| Assignments UI | `/adapters/inbound/assignments_ui.py` |
| Journals UI | `/adapters/inbound/journals_ui.py` |
| API Routes | `/adapters/inbound/assignments_api.py` |

## Model Fields

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Unique identifier |
| `user_uid` | `str` | Owner user |
| `title` | `str` | Assignment title |
| `description` | `str?` | Assignment description |
| `file_paths` | `list[str]` | Uploaded file paths |
| `status` | `AssignmentStatus` | Draft, Submitted, Processing, Complete |
| `processing_results` | `dict?` | Results from Journal processing |
| `created_entities` | `list[str]` | UIDs of created entities |
| `created_at` | `datetime` | Creation timestamp |
| `submitted_at` | `datetime?` | Submission timestamp |
| `completed_at` | `datetime?` | Completion timestamp |

## Processing Flow

```
User → Uploads Files → Assignment
                          ↓
              JournalCoreService (AI processing)
                          ↓
              JournalAIInsights returned
                          ↓
              Assignment creates entities
                          ↓
              User sees results
```

## Entity Creation

Assignments can create entities in any domain based on AI insights:

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
| `CREATED` | Outgoing | Any Entity | Entities created from assignment |
| `PROCESSED_BY` | Outgoing | Journal | Journal that processed |
| `SUBMITTED_BY` | Incoming | User | User who submitted |

## See Also

- [Journals Domain](journals.md) - Backend processor
- [Assignments Pipeline](../architecture/assignments_PIPELINE.md)
