"""
LessonDTO - Learning Unit DTO (Tier 2 - Transfer)
===================================================

Mutable DTO for learning unit entities (EntityType.LESSON).
Inherits all 39 fields from CurriculumDTO — no additional fields needed.
The Lesson is the primary curriculum entity: a unit for learning.

Hierarchy:
    EntityDTO (~18 common fields)
    └── CurriculumDTO(EntityDTO) +21 curriculum-specific fields
        └── LessonDTO(CurriculumDTO)  ← this file (EntityType.LESSON)

See: /docs/patterns/three_tier_type_system.md
See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models.curriculum_dto import CurriculumDTO


@dataclass
class LessonDTO(CurriculumDTO):
    """Mutable DTO for learning unit entities (EntityType.LESSON).

    All 39 fields inherited from CurriculumDTO. No additional fields needed —
    the Lesson inherits the full curriculum field set for learning content.
    """

    pass
