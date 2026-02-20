"""
CurriculumKu - Curriculum Domain Model
========================================

Frozen dataclass for shared knowledge entities (KuType.CURRICULUM, KuType.RESOURCE).

Inherits ~48 common fields from KuBase. Adds zero extra fields — CURRICULUM is
pure shared knowledge where all data lives in KuBase fields (title, content,
description, tags, complexity, learning_level, substance tracking, etc.).

Curriculum-specific structure (organization, aggregation, sequencing) lives in
Neo4j relationships: ORGANIZES, PRIMARY_KNOWLEDGE, SUPPORTING_KNOWLEDGE, HAS_STEP.

Curriculum-specific methods: get_summary, explain_existence, from_dto.

See: /.claude/plans/ku-decomposition-domain-types.md (Phase 7)
See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.ku.ku_dto import KuDTO

from core.models.enums.ku_enums import KuType
from core.models.ku.ku_base import KuBase


@dataclass(frozen=True)
class CurriculumKu(KuBase):
    """
    Immutable domain model for shared knowledge (KuType.CURRICULUM, KuType.RESOURCE).

    Inherits ~48 common fields from KuBase (identity, content, status,
    learning, sharing, substance, meta, embedding).

    Zero extra fields — CURRICULUM is the base knowledge carrier. All
    curriculum-specific structure lives in Neo4j graph relationships.
    """

    def __post_init__(self) -> None:
        """Force ku_type=CURRICULUM if not already set, then delegate to KuBase."""
        if self.ku_type not in (KuType.CURRICULUM, KuType.RESOURCE):
            object.__setattr__(self, "ku_type", KuType.CURRICULUM)
        super().__post_init__()

    # =========================================================================
    # CURRICULUM-SPECIFIC METHODS
    # =========================================================================

    def get_summary(self, max_length: int = 200) -> str:
        """Get a summary of the curriculum content."""
        text = self.description or self.content or self.summary or ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    def explain_existence(self) -> str:
        """Explain why this curriculum exists."""
        return (
            self.description
            or self.summary
            or f"curriculum: {self.title}"
        )

    # =========================================================================
    # CONVERSION (generic -- uses KuBase._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "KuDTO") -> "CurriculumKu":
        """Create CurriculumKu from a KuDTO."""
        return cls._from_dto(dto)

    def __str__(self) -> str:
        return f"CurriculumKu(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"CurriculumKu(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, domain={self.domain}, "
            f"complexity={self.complexity}, user_uid={self.user_uid})"
        )
