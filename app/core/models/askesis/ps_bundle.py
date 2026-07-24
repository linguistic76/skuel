"""
PS Bundle - Complete PathStep Context for Socratic Tutoring
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
    from core.models.event.event import Event
    from core.models.habit.habit import Habit
    from core.models.ku.ku import Ku
    from core.models.pathways.learning_path import LearningPath
    from core.models.pathways.path_step import PathStep
    from core.models.principle.principle import Principle
    from core.models.resource.resource import Resource
    from core.models.task.task import Task
    from core.services.ps_engagement.engagement import Engagement


@dataclass(frozen=True)
class PsBundle:
    """Complete context for a user's active Learning Step.

    Contains the PathStep itself plus all entities reachable through its graph
    relationships: related PathSteps, trained KUs, linked Habits,
    Tasks, Events, Principles, and semantic edges between bundle entities.

    Also carries the lifecycle ``engagement`` snapshot when an
    ``ENGAGED_WITH`` edge exists for (user, PathStep) — None when the PS is
    merely published but not engaged.

    All collection fields are tuples (immutable). The bundle is built once
    per Socratic turn and passed through the pipeline — never mutated.
    """

    path_step: PathStep
    learning_path: LearningPath | None = None

    # Lifecycle state — None when PS is published but not engaged
    engagement: Engagement | None = None

    # Curriculum content
    related_steps: tuple[PathStep, ...] = ()  # supporting PathSteps in context
    kus: tuple[Ku, ...] = ()  # via trains_ku_uids on PS

    # Reference material cited by curriculum in this PS
    resources: tuple[Resource, ...] = ()  # via CITES_RESOURCE on PathSteps/KUs

    # Activity entities linked to this PS
    principles: tuple[Principle, ...] = ()  # via EMBODIES_PRINCIPLE
    habits: tuple[Habit, ...] = ()  # via BUILDS_HABIT
    tasks: tuple[Task, ...] = ()  # via ASSIGNS_TASK
    events: tuple[Event, ...] = ()  # via event templates

    # Real Ku↔Ku lateral edges touching bundle KUs (either endpoint), shaped
    # {source_uid, source_title, target_uid, target_title, relationship_type,
    #  evidence} — evidence is "" for edges authored without it
    edges: tuple[dict, ...] = ()

    # Learning objectives extracted from PathSteps in the bundle
    learning_objectives: tuple[str, ...] = ()

    def contains_ku(self, ku_uid: str) -> bool:
        """Check if a KU is part of this bundle."""
        return any(ku.uid == ku_uid for ku in self.kus)

    def get_step_for_ku(self, ku_uid: str) -> PathStep | None:
        """Find the PathStep that USES_KU for the given KU UID.

        Searches step content fields for KU references. Returns the first
        match — checks the primary path_step first, then related_steps.
        """
        if ku_uid in (self.path_step.semantic_links or ()):
            return self.path_step
        for step in self.related_steps:
            if ku_uid in (step.semantic_links or ()):
                return step
        return None

    def get_all_entity_uids(self) -> set[str]:
        """All entity UIDs in the bundle — for scoping retrieval and matching."""
        uids: set[str] = set()
        uids.add(self.path_step.uid)
        if self.learning_path:
            uids.add(self.learning_path.uid)
        for collection in (
            self.related_steps,
            self.kus,
            self.resources,
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
        titles[self.path_step.uid] = self.path_step.title or ""
        if self.learning_path:
            titles[self.learning_path.uid] = self.learning_path.title or ""
        for collection in (
            self.related_steps,
            self.kus,
            self.resources,
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
        """Concatenated PathStep content + Resource references for LLM context.

        Used by ResponseGenerator when the pedagogical move needs the curriculum
        as reference (e.g., SCAFFOLD, REDIRECT_TO_CURRICULUM).

        Includes resource summaries after step content so Askesis can
        reference cited material (books, talks, films) in conversations.

        Truncated to AskesisTokenBudget.MAX_CURRICULUM_CHARS to prevent
        exceeding LLM context windows when the bundle has many PathSteps.
        """
        from core.constants import AskesisTokenBudget
        from core.utils.text_truncation import truncate_to_budget

        # Primary step content first
        parts: list[str] = []
        if self.path_step.content:
            parts.append(f"## {self.path_step.title}\n\n{self.path_step.content}")
        # Then related steps
        parts.extend(
            f"## {step.title}\n\n{step.content}" for step in self.related_steps if step.content
        )

        # Append resource references — compact summaries, not full content
        if self.resources:
            resource_parts = []
            for resource in self.resources:
                entry = resource.explain_existence()
                if resource.description:
                    entry += f" — {resource.get_summary(150)}"
                resource_parts.append(f"- {entry}")
            parts.append("## Referenced Resources\n\n" + "\n".join(resource_parts))

        raw = "\n\n---\n\n".join(parts)
        return truncate_to_budget(raw, AskesisTokenBudget.MAX_CURRICULUM_CHARS)

    def __str__(self) -> str:
        lp_uid = self.learning_path.uid if self.learning_path else None
        return (
            f"PsBundle(ps={self.path_step.uid}, "
            f"learning_path={lp_uid}, "
            f"related_steps={len(self.related_steps)}, kus={len(self.kus)}, "
            f"resources={len(self.resources)}, "
            f"habits={len(self.habits)}, tasks={len(self.tasks)})"
        )
