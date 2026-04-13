# Shelved: Lesson Guide Documents

**Date shelved:** 2026-04-12

## What these files described

Two developer guides about the former `Lesson` entity type:

- `LESSON_ACTIVITY_WIRING.md` — how `Lesson` entities wired into the 6 Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles) via per-domain edges and `HAS_LESSON` relationships.
- `LESSON_CONTENT_AND_RESOURCES.md` — the content model for `Lesson` (title, content body, summary, Ku composition via `USES_KU`) and how it related to the curated `Resource` entity.

Both guides treated `Lesson` as a live, first-class curriculum entity with its own service, backend, routes, and UI.

## Why they were shelved

The 2026-04 **Lesson -> PathStep merge** eliminated `Lesson` as a distinct entity type. `PathStep` now IS the curriculum content entity — it absorbed Lesson's content fields, `USES_KU` composition role, and activity-domain wiring. There is no `LessonService`, `LessonBackend`, `LessonOperations`, `lesson_*_service.py`, `lesson_ui.py`, `lesson_api.py`, `lesson_routes.py`, `HAS_LESSON` relationship, or `/lessons` / `/api/lesson/*` route in the live codebase.

These files described a mental model that no longer exists. Rewriting them would duplicate content that is now captured in the ground-truth sources.

## Where the current material lives

- `/home/mike/skuel/app/docs/architecture/PATHSTEP_CONTENT_ARCHITECTURE.md` — the PathStep content model (what the old `LESSON_CONTENT_AND_RESOURCES.md` covered).
- `/home/mike/skuel/app/core/services/ps_service.py` — the live PsService facade.
- `/home/mike/skuel/app/core/services/ps/__init__.py` — the real PS sub-services.
- `/home/mike/skuel/app/core/models/pathways/path_step.py` — the PathStep frozen dataclass, including all activity-wiring fields (`habit_uids`, `task_uids`, `choice_uids`, `event_template_uids`, `principle_uids`) that the old `LESSON_ACTIVITY_WIRING.md` documented.
- `/home/mike/skuel/app/CLAUDE.md` — canonical historical note for the merge (search for "Lesson merged into PathStep").

## How to recover history

`git log --follow _shelved/docs_lesson_guides/LESSON_ACTIVITY_WIRING.md` and `git log --follow _shelved/docs_lesson_guides/LESSON_CONTENT_AND_RESOURCES.md` show the full authoring history of both files.
