"""Unit tests for the shared ``build_learning_requirements`` helper.

Covers the mastery-aware split (the depth fix that replaced the goal/task stub) and the
context-free fallback that preserves the prior "every requirement is an open gap" behaviour.
The helper reads only ``UserContext.knowledge_mastery`` (via PrerequisiteChecker), so a
lightweight namespace stands in for the full context.
"""

from __future__ import annotations

from types import SimpleNamespace

from core.services.infrastructure.prerequisite_checker import (
    LEARNING_HOURS_PER_KNOWLEDGE_AREA,
    build_learning_requirements,
)


def _ctx(**mastery: float) -> SimpleNamespace:
    """Minimal UserContext stand-in carrying only knowledge_mastery."""
    return SimpleNamespace(knowledge_mastery=dict(mastery), completed_task_uids=set())


# ---------------------------------------------------------------------------
# Context-free fallback — reproduces the pre-mastery stub behaviour exactly.
# ---------------------------------------------------------------------------


def test_no_context_treats_every_requirement_as_a_gap() -> None:
    result = build_learning_requirements(
        required_knowledge_uids=["ku_a", "ku_b"],
        learning_path_uids=[],
        context=None,
    )
    kr = result["knowledge_requirements"]
    assert [k["uid"] for k in kr["required_knowledge"]] == ["ku_a", "ku_b"]
    assert kr["mastered_knowledge"] == []
    assert [g["uid"] for g in kr["knowledge_gaps"]] == ["ku_a", "ku_b"]
    assert kr["total_required"] == 2
    assert kr["total_mastered"] == 0
    assert kr["mastery_percentage"] == 0.0

    la = result["learning_analysis"]
    assert la["ready_to_start"] is False
    assert la["has_prerequisites"] is True
    assert la["knowledge_complete"] is False
    assert (
        result["learning_paths"]["estimated_learning_time"] == 2 * LEARNING_HOURS_PER_KNOWLEDGE_AREA
    )


def test_no_requirements_is_ready_and_complete() -> None:
    result = build_learning_requirements(
        required_knowledge_uids=[], learning_path_uids=[], context=None
    )
    assert result["knowledge_requirements"]["mastery_percentage"] == 100.0
    assert result["learning_analysis"]["ready_to_start"] is True
    assert result["learning_analysis"]["has_prerequisites"] is False
    assert result["learning_analysis"]["knowledge_complete"] is True
    assert result["learning_paths"]["estimated_learning_time"] == 0


# ---------------------------------------------------------------------------
# Mastery-aware split — the depth fix telling the truth.
# ---------------------------------------------------------------------------


def test_partial_mastery_splits_mastered_from_gaps() -> None:
    # ku_a mastered (>= 0.7), ku_b below threshold, ku_c absent (treated as 0.0).
    ctx = _ctx(ku_a=0.9, ku_b=0.6)
    result = build_learning_requirements(
        required_knowledge_uids=["ku_a", "ku_b", "ku_c"],
        learning_path_uids=[],
        context=ctx,
    )
    kr = result["knowledge_requirements"]
    assert [k["uid"] for k in kr["mastered_knowledge"]] == ["ku_a"]
    assert [g["uid"] for g in kr["knowledge_gaps"]] == ["ku_b", "ku_c"]
    assert kr["total_mastered"] == 1
    assert round(kr["mastery_percentage"], 1) == round(1 / 3 * 100, 1)
    assert result["learning_analysis"]["ready_to_start"] is False
    # Estimated time scales with the *gaps*, not the total — the truth-telling payoff.
    assert (
        result["learning_paths"]["estimated_learning_time"] == 2 * LEARNING_HOURS_PER_KNOWLEDGE_AREA
    )


def test_threshold_boundary_counts_as_mastered() -> None:
    ctx = _ctx(ku_a=0.7)  # exactly at DEFAULT_MASTERY_THRESHOLD
    result = build_learning_requirements(
        required_knowledge_uids=["ku_a"], learning_path_uids=[], context=ctx
    )
    assert [k["uid"] for k in result["knowledge_requirements"]["mastered_knowledge"]] == ["ku_a"]
    assert result["learning_analysis"]["ready_to_start"] is True


def test_full_mastery_is_ready_and_complete() -> None:
    ctx = _ctx(ku_a=0.95, ku_b=0.8)
    result = build_learning_requirements(
        required_knowledge_uids=["ku_a", "ku_b"], learning_path_uids=[], context=ctx
    )
    kr = result["knowledge_requirements"]
    assert kr["knowledge_gaps"] == []
    assert kr["mastery_percentage"] == 100.0
    la = result["learning_analysis"]
    assert la["ready_to_start"] is True
    assert la["knowledge_complete"] is True
    assert result["learning_paths"]["estimated_learning_time"] == 0


# ---------------------------------------------------------------------------
# Learning paths block.
# ---------------------------------------------------------------------------


def test_learning_paths_surface_and_recommend_first() -> None:
    result = build_learning_requirements(
        required_knowledge_uids=["ku_a"],
        learning_path_uids=["lp_1", "lp_2"],
        context=None,
    )
    lp = result["learning_paths"]
    assert [p["uid"] for p in lp["available_paths"]] == ["lp_1", "lp_2"]
    assert lp["recommended_path"] == {"uid": "lp_1"}
    assert result["learning_analysis"]["learning_in_progress"] is True


def test_no_learning_paths_means_no_recommendation() -> None:
    result = build_learning_requirements(
        required_knowledge_uids=["ku_a"], learning_path_uids=[], context=None
    )
    assert result["learning_paths"]["recommended_path"] is None
    assert result["learning_analysis"]["learning_in_progress"] is False
