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

import pytest

from adapters.persistence.neo4j.neo4j_schema_manager import FULLTEXT_INDEX_DEFINITIONS
from core.models.enums.neo_labels import NeoLabel

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
