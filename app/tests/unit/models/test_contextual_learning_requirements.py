"""Consolidated mastery-aware learning-requirements lens on the Contextual* models.

After the consolidation, ``ContextualGoal`` and ``ContextualTask`` source readiness,
``learning_gaps`` and ``blocking_reasons`` from the SINGLE
``PrerequisiteChecker.check_prerequisites`` split, and carry the richer
``learning_requirements`` display payload built by ``build_learning_requirements``
(which delegates to the same split). These tests prove that single source tells the
truth against the user's ``knowledge_mastery`` — gaps close when a required KU is
mastered — and that the flat fields agree with the rich payload (no parallel systems).
"""

import pytest

from core.models.context_types import ContextualGoal, ContextualTask
from core.services.user.unified_user_context import UserContext

REQUIRED = ["ku_a", "ku_b"]


def _context(mastery: dict[str, float]) -> UserContext:
    """Minimal UserContext carrying a knowledge-mastery map + one active goal."""
    return UserContext(
        user_uid="user_test",
        active_goal_uids={"goal_test"},
        knowledge_mastery=mastery,
    )


class TestContextualGoalLearningRequirements:
    def test_gap_open_when_unmastered(self):
        """No mastery → every requirement is an open gap, not ready to start."""
        goal = ContextualGoal.from_entity_and_context(
            uid="goal_test",
            title="Learn Rust",
            context=_context({}),
            required_knowledge_uids=REQUIRED,
        )
        reqs = goal.learning_requirements
        assert reqs is not None
        knowledge = reqs["knowledge_requirements"]
        assert knowledge["total_required"] == 2
        assert knowledge["total_mastered"] == 0
        assert {g["uid"] for g in knowledge["knowledge_gaps"]} == set(REQUIRED)
        assert reqs["learning_analysis"]["ready_to_start"] is False

    def test_gap_closes_when_mastered(self):
        """Mastering the required KUs closes the gap and flips ready_to_start."""
        ctx = _context({"ku_a": 0.9, "ku_b": 0.8})
        goal = ContextualGoal.from_entity_and_context(
            uid="goal_test",
            title="Learn Rust",
            context=ctx,
            required_knowledge_uids=REQUIRED,
        )
        reqs = goal.learning_requirements
        assert reqs is not None
        knowledge = reqs["knowledge_requirements"]
        assert knowledge["total_mastered"] == 2
        assert knowledge["knowledge_gaps"] == []
        assert reqs["learning_analysis"]["ready_to_start"] is True
        # Below-threshold mastery (0.7) does NOT count as mastered.
        partial = ContextualGoal.from_entity_and_context(
            uid="goal_test",
            title="Learn Rust",
            context=_context({"ku_a": 0.9, "ku_b": 0.5}),
            required_knowledge_uids=REQUIRED,
        )
        partial_reqs = partial.learning_requirements
        assert partial_reqs is not None
        assert partial_reqs["knowledge_requirements"]["total_mastered"] == 1

    def test_flat_gaps_agree_with_rich_payload(self):
        """learning_gaps (flat field) is the SAME split as the rich payload — one source."""
        ctx = _context({"ku_a": 0.9})  # ku_b is the only gap
        goal = ContextualGoal.from_entity_and_context(
            uid="goal_test",
            title="Learn Rust",
            context=ctx,
            required_knowledge_uids=REQUIRED,
        )
        reqs = goal.learning_requirements
        assert reqs is not None
        rich_gaps = {g["uid"] for g in reqs["knowledge_requirements"]["knowledge_gaps"]}
        assert set(goal.learning_gaps) == rich_gaps == {"ku_b"}
        # readiness score == mastered fraction (knowledge-only goal)
        assert goal.readiness_score == pytest.approx(0.5)

    def test_no_requirements_means_ready(self):
        """A goal with no required knowledge is ready (no prerequisites)."""
        goal = ContextualGoal.from_entity_and_context(
            uid="goal_test",
            title="Stretch",
            context=_context({}),
            required_knowledge_uids=[],
        )
        reqs = goal.learning_requirements
        assert reqs is not None
        assert reqs["knowledge_requirements"]["total_required"] == 0
        assert reqs["learning_analysis"]["ready_to_start"] is True
        assert goal.learning_gaps == ()


class TestContextualTaskLearningRequirements:
    def test_task_gap_closes_with_mastery(self):
        """Task prerequisite knowledge gaps close when mastered; can_start flips."""
        unmastered = ContextualTask.from_entity_and_context(
            uid="task_test",
            title="Ship feature",
            context=_context({}),
            prerequisite_knowledge=REQUIRED,
        )
        assert unmastered.can_start is False
        assert set(unmastered.learning_gaps) == set(REQUIRED)
        unmastered_reqs = unmastered.learning_requirements
        assert unmastered_reqs is not None
        assert unmastered_reqs["learning_analysis"]["ready_to_start"] is False
        assert len(unmastered.blocking_reasons) >= 1

        mastered = ContextualTask.from_entity_and_context(
            uid="task_test",
            title="Ship feature",
            context=_context({"ku_a": 0.9, "ku_b": 0.9}),
            prerequisite_knowledge=REQUIRED,
        )
        assert mastered.can_start is True
        assert mastered.learning_gaps == ()
        mastered_reqs = mastered.learning_requirements
        assert mastered_reqs is not None
        assert mastered_reqs["learning_analysis"]["ready_to_start"] is True
        assert mastered.blocking_reasons == ()

    def test_blocking_reasons_from_single_source(self):
        """blocking_reasons come from the same check — gap KUs surface as reasons."""
        task = ContextualTask.from_entity_and_context(
            uid="task_test",
            title="Ship feature",
            context=_context({"ku_a": 0.9}),  # ku_b missing
            prerequisite_knowledge=REQUIRED,
        )
        assert set(task.learning_gaps) == {"ku_b"}
        assert any("ku_b" in reason for reason in task.blocking_reasons)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
