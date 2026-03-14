"""
Lesson - Teaching Composition (Curriculum Leaf Class)
=====================================================

A Lesson is a teaching composition — essay-like narrative content that
composes atomic knowledge units into a coherent educational artifact.

Part of the 4-part educational loop:
    Lesson → Exercise → Submission → Report

Hierarchy:
    Entity (~29 fields)
    └── Curriculum(Entity) +21 fields  ← BASE CLASS
        └── Lesson(Curriculum)         ← EntityType.LESSON (this file)

Grouping patterns (Lesson is the point, LS is the edge, LP is the path):
    Lesson  → teaching composition (narrative content)
    LS      → a step in a learning path (ordered sequence of Lessons)
    LP      → a learning path (ordered sequence of steps)

See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.lesson.lesson_dto import LessonDTO
    from core.models.curriculum_dto import CurriculumDTO
    from core.models.entity_dto import EntityDTO

from core.models.curriculum import Curriculum
from core.models.enums.entity_enums import EntityType


@dataclass(frozen=True)
class Lesson(Curriculum):
    """
    Teaching Composition — essay-like narrative content for SKUEL's curriculum.

    A Lesson composes atomic Kus (concepts, states, principles) into coherent
    narrative. It is the main content unit in the curriculum hierarchy — it can
    organize other Lessons via ORGANIZES relationships (emergent MOC identity).

    The 4-part educational loop:
        Lesson (teaching composition) → Exercise (instruction template)
          → Submission (student work) → SubmissionReport (teacher/AI response)

    See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
    """

    def __post_init__(self) -> None:
        object.__setattr__(self, "entity_type", EntityType.LESSON)
        super().__post_init__()

    @classmethod
    def from_dto(cls, dto: EntityDTO | CurriculumDTO | LessonDTO) -> Lesson:
        """Create Lesson from an EntityDTO, CurriculumDTO, or LessonDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> LessonDTO:  # type: ignore[override]
        """Convert Lesson to domain-specific LessonDTO."""
        from core.models.lesson.lesson_dto import LessonDTO

        dto_field_names = {f.name for f in dataclasses.fields(LessonDTO)}
        kwargs: dict[str, Any] = {}
        for f in dataclasses.fields(self):
            if f.name.startswith("_") or f.name not in dto_field_names:
                continue
            value = getattr(self, f.name)
            if isinstance(value, tuple):
                value = list(value)
            kwargs[f.name] = value
        return LessonDTO(**kwargs)

    def __str__(self) -> str:
        return f"Lesson(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"Lesson(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, domain={self.domain}, "
            f"complexity={self.complexity})"
        )
