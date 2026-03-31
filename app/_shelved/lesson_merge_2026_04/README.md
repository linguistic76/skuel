# Shelved: Lesson → PathStep Merge (2026-04)

Lesson entity merged INTO PathStep. 4-level hierarchy (LP→PS→Lesson→Ku) collapsed to 3-level (LP→PS→Ku).

PathStep is now THE curriculum content entity — it composes Kus, carries body content, has activity domain wiring, ORGANIZES relationships, and learning state tracking.

## Shelved Files

- `models/` — Lesson, LessonDTO, LessonCreateRequest frozen dataclasses
- `services/` — LessonService facade + 12 sub-services (to be added as phases progress)
- `routes/` — lesson_routes.py, lesson_api.py, lesson_ui.py (to be added)
- `backend/` — LessonBackend class (to be added)
- `events/` — lesson_events.py (to be added)

## Migration

Neo4j: `scripts/migrations/merge_lesson_into_pathstep_2026_04.cypher`
