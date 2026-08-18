"""
Fulltext index naming — the creation/query drift guard.

``NeoLabel.fulltext_index_name`` is THE naming rule, shared by index creation
(``Neo4jSchemaManager.sync_fulltext_indexes``) and index querying
(``Neo4jVectorSearchService._fulltext_search``). Before the helper existed the
query side derived names as flat ``label.lower()``, which silently missed every
multi-word label (``PathStep`` → ``pathstep_fulltext_idx``, real name
``path_step_fulltext_idx``) — a lookup against a nonexistent index returns no
rows rather than erroring.

The 14 names below are pinned as literals ON PURPOSE: they are the indexes
already ONLINE in the live graph. Deriving the expected values from the helper
would make this test tautological — a renamed ``NeoLabel`` member would rename
the index and orphan the live one, with nothing failing.
"""

from __future__ import annotations

from dataclasses import fields

import pytest

from adapters.persistence.neo4j.neo4j_schema_manager import FULLTEXT_INDEX_DEFINITIONS
from core.models.choice.choice import Choice
from core.models.enums.neo_labels import NeoLabel
from core.models.event.event import Event
from core.models.exercises.exercise import Exercise
from core.models.exercises.revised_exercise import RevisedExercise
from core.models.forms.form_submission import FormSubmission
from core.models.forms.form_template import FormTemplate
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.ku.ku import Ku
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.path_step import PathStep
from core.models.principle.principle import Principle
from core.models.task.task import Task
from core.models.user_entry.user_entry import UserEntry

# The live-graph index names (AuraDB d2d160c4, verified 2026-08-16).
LIVE_FULLTEXT_INDEX_NAMES: dict[NeoLabel, str] = {
    # Activity Domains (6)
    NeoLabel.TASK: "task_fulltext_idx",
    NeoLabel.GOAL: "goal_fulltext_idx",
    NeoLabel.HABIT: "habit_fulltext_idx",
    NeoLabel.EVENT: "event_fulltext_idx",
    NeoLabel.CHOICE: "choice_fulltext_idx",
    NeoLabel.PRINCIPLE: "principle_fulltext_idx",
    # Curriculum Domains (4)
    NeoLabel.KU: "ku_fulltext_idx",
    NeoLabel.PATH_STEP: "path_step_fulltext_idx",
    NeoLabel.LEARNING_PATH: "learning_path_fulltext_idx",
    NeoLabel.EXERCISE: "exercise_fulltext_idx",
    # Learning Loop (2)
    NeoLabel.REVISED_EXERCISE: "revised_exercise_fulltext_idx",
    NeoLabel.USER_ENTRY: "user_entry_fulltext_idx",
    # Forms (2)
    NeoLabel.FORM_TEMPLATE: "form_template_fulltext_idx",
    NeoLabel.FORM_SUBMISSION: "form_submission_fulltext_idx",
}


class TestFulltextIndexName:
    @pytest.mark.parametrize(("label", "expected"), LIVE_FULLTEXT_INDEX_NAMES.items())
    def test_helper_reproduces_the_live_index_name(self, label: NeoLabel, expected: str) -> None:
        assert NeoLabel.fulltext_index_name(label) == expected

    def test_accepts_the_label_string(self) -> None:
        """The query side derives from a label string, not always an enum member."""
        assert NeoLabel.fulltext_index_name("PathStep") == "path_step_fulltext_idx"

    def test_multi_word_labels_are_snake_cased(self) -> None:
        """The bug this helper exists to prevent: flat lower() loses the separator."""
        assert NeoLabel.fulltext_index_name(NeoLabel.PATH_STEP) != "pathstep_fulltext_idx"

    def test_unknown_label_raises(self) -> None:
        with pytest.raises(ValueError, match="NotALabel"):
            NeoLabel.fulltext_index_name("NotALabel")


class TestFulltextIndexDefinitions:
    def test_definitions_cover_exactly_the_live_indexes(self) -> None:
        assert {label for label, _ in FULLTEXT_INDEX_DEFINITIONS} == set(LIVE_FULLTEXT_INDEX_NAMES)

    def test_created_names_match_the_live_indexes(self) -> None:
        """What sync_fulltext_indexes would create == what is already ONLINE."""
        created = {NeoLabel.fulltext_index_name(label) for label, _ in FULLTEXT_INDEX_DEFINITIONS}
        assert created == set(LIVE_FULLTEXT_INDEX_NAMES.values())

    def test_every_definition_indexes_at_least_one_field(self) -> None:
        for label, index_fields in FULLTEXT_INDEX_DEFINITIONS:
            assert index_fields, f"{label} has no indexed fields — the index would match nothing"


# The domain model behind each indexed label. Explicit rather than derived: the
# mapping is what makes the field check below non-tautological, and a wrong
# entry would quietly make it pass over the wrong model.
INDEXED_LABEL_MODELS: dict[NeoLabel, type] = {
    NeoLabel.TASK: Task,
    NeoLabel.GOAL: Goal,
    NeoLabel.HABIT: Habit,
    NeoLabel.EVENT: Event,
    NeoLabel.CHOICE: Choice,
    NeoLabel.PRINCIPLE: Principle,
    NeoLabel.KU: Ku,
    NeoLabel.PATH_STEP: PathStep,
    NeoLabel.LEARNING_PATH: LearningPath,
    NeoLabel.EXERCISE: Exercise,
    NeoLabel.REVISED_EXERCISE: RevisedExercise,
    NeoLabel.USER_ENTRY: UserEntry,
    NeoLabel.FORM_TEMPLATE: FormTemplate,
    NeoLabel.FORM_SUBMISSION: FormSubmission,
}


class TestFulltextIndexFieldsExist:
    """
    A fulltext index on a property no node carries indexes nothing — silently.

    Neo4j accepts ``ON EACH [n.whatever]`` for any name, so a typo or a field
    that was renamed away costs no error, no warning, and no rows. Three such
    phantoms lived here undetected: ``Choice.context`` (never existed),
    ``LearningPath.name`` (lost to the domain-wide name→title rename), and
    ``LearningPath.goal`` (a read-only Python property aliasing ``description``,
    so it is never written to the graph).

    That last one is why this checks ``dataclasses.fields`` and not ``hasattr``:
    a property answers ``hasattr`` happily while persisting nothing. Same guard
    shape as SKUEL030 for labels and edge names.
    """

    def test_every_indexed_label_has_a_model(self) -> None:
        assert {label for label, _ in FULLTEXT_INDEX_DEFINITIONS} == set(INDEXED_LABEL_MODELS)

    @pytest.mark.parametrize(("label", "index_fields"), FULLTEXT_INDEX_DEFINITIONS)
    def test_indexed_fields_are_persisted_model_fields(
        self, label: NeoLabel, index_fields: list[str]
    ) -> None:
        model = INDEXED_LABEL_MODELS[label]
        persisted = {f.name for f in fields(model)}
        for field_name in index_fields:
            assert field_name in persisted, (
                f"{label.value}: fulltext index field {field_name!r} is not a persisted "
                f"field of {model.__name__} — the index would silently match nothing. "
                f"If it is a @property, it is computed, not stored."
            )
