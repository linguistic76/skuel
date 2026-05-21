"""Unit tests for ``_terminal_status_rules`` — pure-function engagement-terminal classifier."""

from __future__ import annotations

import pytest

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.services.ps_engagement._terminal_status_rules import (
    GATES_AUTO_COMPLETION,
    is_engagement_terminal,
)


class TestPrincipleNeverBlocks:
    """Principle is exposure-only — every status counts as engagement-terminal."""

    @pytest.mark.parametrize(
        "status",
        [EntityStatus.ACTIVE, EntityStatus.PAUSED, EntityStatus.ARCHIVED],
    )
    def test_principle_any_valid_status_is_terminal(self, status: EntityStatus) -> None:
        assert is_engagement_terminal(EntityType.PRINCIPLE, status) is True


class TestTaskTerminal:
    @pytest.mark.parametrize(
        "status",
        [
            EntityStatus.COMPLETED,
            EntityStatus.CANCELLED,
            EntityStatus.FAILED,
            EntityStatus.ARCHIVED,
        ],
    )
    def test_terminal_statuses(self, status: EntityStatus) -> None:
        assert is_engagement_terminal(EntityType.TASK, status) is True

    @pytest.mark.parametrize(
        "status",
        [
            EntityStatus.DRAFT,
            EntityStatus.SCHEDULED,
            EntityStatus.ACTIVE,
            EntityStatus.PAUSED,
            EntityStatus.BLOCKED,
        ],
    )
    def test_non_terminal_statuses(self, status: EntityStatus) -> None:
        assert is_engagement_terminal(EntityType.TASK, status) is False


class TestGoalTerminal:
    @pytest.mark.parametrize(
        "status",
        [
            EntityStatus.COMPLETED,
            EntityStatus.CANCELLED,
            EntityStatus.FAILED,
            EntityStatus.ARCHIVED,
        ],
    )
    def test_terminal_statuses(self, status: EntityStatus) -> None:
        assert is_engagement_terminal(EntityType.GOAL, status) is True

    @pytest.mark.parametrize(
        "status", [EntityStatus.DRAFT, EntityStatus.ACTIVE, EntityStatus.PAUSED]
    )
    def test_non_terminal_statuses(self, status: EntityStatus) -> None:
        assert is_engagement_terminal(EntityType.GOAL, status) is False


class TestHabitTerminal:
    """Habit PAUSED is intentionally NOT engagement-terminal — student may resume."""

    @pytest.mark.parametrize(
        "status",
        [EntityStatus.COMPLETED, EntityStatus.CANCELLED, EntityStatus.ARCHIVED],
    )
    def test_terminal_statuses(self, status: EntityStatus) -> None:
        assert is_engagement_terminal(EntityType.HABIT, status) is True

    @pytest.mark.parametrize("status", [EntityStatus.ACTIVE, EntityStatus.PAUSED])
    def test_active_and_paused_are_not_terminal(self, status: EntityStatus) -> None:
        assert is_engagement_terminal(EntityType.HABIT, status) is False


class TestEventTerminal:
    @pytest.mark.parametrize("status", [EntityStatus.COMPLETED, EntityStatus.CANCELLED])
    def test_terminal_statuses(self, status: EntityStatus) -> None:
        assert is_engagement_terminal(EntityType.EVENT, status) is True

    @pytest.mark.parametrize("status", [EntityStatus.SCHEDULED, EntityStatus.ACTIVE])
    def test_non_terminal_statuses(self, status: EntityStatus) -> None:
        assert is_engagement_terminal(EntityType.EVENT, status) is False


class TestChoiceTerminal:
    @pytest.mark.parametrize("status", [EntityStatus.COMPLETED, EntityStatus.ARCHIVED])
    def test_terminal_statuses(self, status: EntityStatus) -> None:
        assert is_engagement_terminal(EntityType.CHOICE, status) is True

    @pytest.mark.parametrize("status", [EntityStatus.DRAFT, EntityStatus.ACTIVE])
    def test_non_terminal_statuses(self, status: EntityStatus) -> None:
        assert is_engagement_terminal(EntityType.CHOICE, status) is False


class TestGatesAutoCompletion:
    """Domains whose entity-terminal events fire the auto-complete check."""

    def test_gating_domains_match_expected_four(self) -> None:
        expected = frozenset(
            {EntityType.TASK, EntityType.GOAL, EntityType.EVENT, EntityType.CHOICE}
        )
        assert expected == GATES_AUTO_COMPLETION

    def test_habit_and_principle_do_not_gate(self) -> None:
        # Habits run on per-occurrence events (not entity-terminal); Principles
        # have no terminal state — neither fires the auto-complete check.
        assert EntityType.HABIT not in GATES_AUTO_COMPLETION
        assert EntityType.PRINCIPLE not in GATES_AUTO_COMPLETION
