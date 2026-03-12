"""
LS Bundle - Complete Learning Step Context for Socratic Tutoring
=================================================================

Frozen dataclass containing all entities referenced by the user's current
Learning Step. This is the scoped context window for the Socratic pipeline —
every retrieval and pedagogical decision operates within the bundle.

The bundle is loaded once per Socratic turn by ContextRetriever and consumed by:
- IntentClassifier.classify_pedagogical_intent() — scoped question matching
- ResponseGenerator.build_guided_system_prompt() — curriculum context for LLM prompts
- EntityExtractor.extract_from_bundle() — scoped entity linking

See: /docs/architecture/ASKESIS_SOCRATIC_ARCHITECTURE.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.article.article import Article
    from core.models.event.event import Event
    from core.models.habit.habit import Habit
    from core.models.ku.ku import Ku
    from core.models.pathways.learning_path import LearningPath
    from core.models.pathways.learning_step import LearningStep
    from core.models.principle.principle import Principle
    from core.models.task.task import Task


@dataclass(frozen=True)
class LSBundle:
    """Complete context for a user's active Learning Step.

    Contains the LS itself plus all entities reachable through its graph
    relationships: primary/supporting Articles, trained KUs, linked Habits,
    Tasks, Events, Principles, and semantic edges between bundle entities.

    All collection fields are tuples (immutable). The bundle is built once
    per Socratic turn and passed through the pipeline — never mutated.
    """

    learning_step: LearningStep
    learning_path: LearningPath | None = None

    # Curriculum content
    articles: tuple[Article, ...] = ()  # primary + supporting knowledge
    kus: tuple[Ku, ...] = ()  # via trains_ku_uids on LS

    # Activity entities linked to this LS
    principles: tuple[Principle, ...] = ()  # via EMBODIES_PRINCIPLE
    habits: tuple[Habit, ...] = ()  # via BUILDS_HABIT
    tasks: tuple[Task, ...] = ()  # via ASSIGNS_TASK
    events: tuple[Event, ...] = ()  # via event templates

    # Semantic relationships between bundle entities
    edges: tuple[dict, ...] = ()

    # Learning objectives extracted from Articles in the bundle
    learning_objectives: tuple[str, ...] = ()

    def contains_ku(self, ku_uid: str) -> bool:
        """Check if a KU is part of this bundle."""
        return any(ku.uid == ku_uid for ku in self.kus)

    def get_article_for_ku(self, ku_uid: str) -> Article | None:
        """Find the Article that USES_KU for the given KU UID.

        Searches article content fields for KU references. Returns the first
        match — in practice, one Article covers one KU within a single LS.
        """
        for article in self.articles:
            # Articles reference KUs via semantic_links (from Curriculum base)
            if ku_uid in (article.semantic_links or ()):
                return article
        return None

    def get_all_entity_uids(self) -> set[str]:
        """All entity UIDs in the bundle — for scoping retrieval and matching."""
        uids: set[str] = set()
        uids.add(self.learning_step.uid)
        if self.learning_path:
            uids.add(self.learning_path.uid)
        for collection in (
            self.articles,
            self.kus,
            self.principles,
            self.habits,
            self.tasks,
            self.events,
        ):
            for entity in collection:
                uids.add(entity.uid)
        return uids

    def get_all_titles(self) -> dict[str, str]:
        """Map of uid -> title for all bundle entities. Used for fuzzy matching."""
        titles: dict[str, str] = {}
        titles[self.learning_step.uid] = self.learning_step.title or ""
        if self.learning_path:
            titles[self.learning_path.uid] = self.learning_path.title or ""
        for collection in (
            self.articles,
            self.kus,
            self.principles,
            self.habits,
            self.tasks,
            self.events,
        ):
            for entity in collection:
                titles[entity.uid] = entity.title or ""
                # Include KU aliases for matching
                aliases = getattr(entity, "aliases", ())
                for alias in aliases:
                    titles[f"{entity.uid}::{alias}"] = alias
        return titles

    def get_ku_uids(self) -> list[str]:
        """KU UIDs in this bundle — convenience for ZPD targeted assessment."""
        return [ku.uid for ku in self.kus]

    @property
    def curriculum_context_text(self) -> str:
        """Concatenated Article content for LLM context injection.

        Used by ResponseGenerator when the pedagogical move needs the curriculum
        as reference (e.g., SCAFFOLD, REDIRECT_TO_CURRICULUM).
        """
        parts = [
            f"## {article.title}\n\n{article.content}"
            for article in self.articles
            if article.content
        ]
        return "\n\n---\n\n".join(parts)

    def __str__(self) -> str:
        return (
            f"LSBundle(ls={self.learning_step.uid}, "
            f"articles={len(self.articles)}, kus={len(self.kus)}, "
            f"habits={len(self.habits)}, tasks={len(self.tasks)})"
        )
