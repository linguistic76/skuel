"""
Article - Teaching Composition (Curriculum Leaf Class)
=====================================================

An Article is a teaching composition — essay-like narrative content that
composes atomic knowledge units into a coherent educational artifact.
Formerly called "Ku" (which now refers to the atomic knowledge unit).

Part of the 4-part educational loop:
    Article → Exercise → Submission → Feedback

Hierarchy:
    Entity (~29 fields)
    └── Curriculum(Entity) +21 fields  ← BASE CLASS
        └── Article(Curriculum)         ← EntityType.ARTICLE (this file)

Grouping patterns (Article is the point, LS is the edge, LP is the path):
    Article → teaching composition (narrative content)
    LS      → a step in a learning path (ordered sequence of Articles)
    LP      → a learning path (ordered sequence of steps)

See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.article.article_dto import ArticleDTO
    from core.models.curriculum_dto import CurriculumDTO
    from core.models.entity_dto import EntityDTO

from core.models.curriculum import Curriculum
from core.models.enums.entity_enums import EntityType


@dataclass(frozen=True)
class Article(Curriculum):
    """
    Teaching Composition — essay-like narrative content for SKUEL's curriculum.

    An Article composes atomic Kus (concepts, states, principles) into coherent
    narrative. It is the main content unit in the curriculum hierarchy — it can
    organize other Articles via ORGANIZES relationships (emergent MOC identity).

    The 4-part educational loop:
        Article (teaching composition) → Exercise (instruction template)
          → Submission (student work) → SubmissionReport (teacher/AI response)

    See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
    """

    def __post_init__(self) -> None:
        object.__setattr__(self, "entity_type", EntityType.ARTICLE)
        super().__post_init__()

    @classmethod
    def from_dto(cls, dto: EntityDTO | CurriculumDTO | ArticleDTO) -> Article:
        """Create Article from an EntityDTO, CurriculumDTO, or ArticleDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> ArticleDTO:  # type: ignore[override]
        """Convert Article to domain-specific ArticleDTO."""
        from core.models.article.article_dto import ArticleDTO

        dto_field_names = {f.name for f in dataclasses.fields(ArticleDTO)}
        kwargs: dict[str, Any] = {}
        for f in dataclasses.fields(self):
            if f.name.startswith("_") or f.name not in dto_field_names:
                continue
            value = getattr(self, f.name)
            if isinstance(value, tuple):
                value = list(value)
            kwargs[f.name] = value
        return ArticleDTO(**kwargs)

    def __str__(self) -> str:
        return f"Article(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"Article(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, domain={self.domain}, "
            f"complexity={self.complexity})"
        )
