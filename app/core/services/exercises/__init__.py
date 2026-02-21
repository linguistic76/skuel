"""
Exercise Services Package
===========================

CRUD operations for Exercises (instruction templates).

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from core.services.exercises.exercise_service import ExerciseService

__all__ = [
    "ExerciseService",
]
