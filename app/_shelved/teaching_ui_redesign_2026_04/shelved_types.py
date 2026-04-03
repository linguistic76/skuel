"""Shelved teaching type definitions — removed 2026-04-03.

TeachingDashboardStats and ExerciseSummary were removed when the
Teaching UI overview dashboard and exercise management were eliminated.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TeachingDashboardStats:
    """Overview dashboard statistics."""

    pending_count: int = 0
    total_students: int = 0
    total_exercises: int = 0
    total_groups: int = 0


@dataclass(frozen=True)
class ExerciseSummary:
    """Exercise card with submission counts."""

    uid: str = ""
    title: str = "Untitled Exercise"
    scope: str | None = None
    total_count: int = 0
    reviewed_count: int = 0
    pending_count: int = 0
