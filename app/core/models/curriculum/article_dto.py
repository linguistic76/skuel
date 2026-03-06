"""
ArticleDTO - Teaching Composition DTO (Tier 2 - Transfer)
=========================================================

Mutable DTO for teaching composition entities (EntityType.ARTICLE).
Inherits all 39 fields from CurriculumDTO — no additional fields needed.
The Article is the narrative curriculum entity: composed teaching content.

Hierarchy:
    EntityDTO (~18 common fields)
    └── CurriculumDTO(EntityDTO) +21 curriculum-specific fields
        └── ArticleDTO(CurriculumDTO)  ← this file (EntityType.ARTICLE)

See: /docs/patterns/three_tier_type_system.md
See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models.curriculum.curriculum_dto import CurriculumDTO


@dataclass
class ArticleDTO(CurriculumDTO):
    """Mutable DTO for teaching composition entities (EntityType.ARTICLE).

    All 39 fields inherited from CurriculumDTO. No additional fields needed —
    the Article inherits the full curriculum field set for narrative content.
    """

    pass
