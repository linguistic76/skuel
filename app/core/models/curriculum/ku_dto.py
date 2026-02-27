"""
KuDTO - Atomic Knowledge Unit DTO (Tier 2 - Transfer)
======================================================

Mutable DTO for atomic knowledge unit entities (EntityType.KU).
Inherits all 39 fields from CurriculumDTO — no additional fields needed.
The Ku is the simplest curriculum entity: pure knowledge, no structure.

Hierarchy:
    EntityDTO (~18 common fields)
    └── CurriculumDTO(EntityDTO) +21 curriculum-specific fields
        └── KuDTO(CurriculumDTO)  ← this file (EntityType.KU)

See: /docs/patterns/three_tier_type_system.md
See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models.curriculum.curriculum_dto import CurriculumDTO


@dataclass
class KuDTO(CurriculumDTO):
    """Mutable DTO for atomic knowledge unit entities (EntityType.KU).

    All 39 fields inherited from CurriculumDTO. No additional fields needed —
    the Ku is the atomic base: pure knowledge without structural additions.
    """

    pass
