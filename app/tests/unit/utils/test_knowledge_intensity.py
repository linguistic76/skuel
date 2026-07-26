"""Unit tests for the shared knowledge-intensity kernel.

Locks in the single formula the six *Relationships containers now delegate to
(core/ports/knowledge_pattern_protocol.py), including the property the collapse
depended on: with an empty secondary tier the superset formula reproduces the
primary-only curve exactly, bit for bit.
"""

from __future__ import annotations

import pytest

from core.constants import KnowledgeIntensityWeight
from core.ports.knowledge_pattern_protocol import compute_knowledge_intensity


def uids(n: int) -> list[str]:
    return [f"ku_{i}" for i in range(n)]


class TestComputeKnowledgeIntensity:
    def test_no_links_scores_zero(self) -> None:
        assert compute_knowledge_intensity([], []) == 0.0

    def test_primary_edge_is_weighted(self) -> None:
        assert compute_knowledge_intensity(uids(1), []) == pytest.approx(0.15)

    def test_secondary_edge_is_weighted_lower(self) -> None:
        assert compute_knowledge_intensity([], uids(1)) == pytest.approx(0.05)

    def test_tiers_are_additive(self) -> None:
        assert compute_knowledge_intensity(uids(2), uids(3)) == pytest.approx(0.45)

    def test_score_is_clamped_at_one(self) -> None:
        assert compute_knowledge_intensity(uids(7), []) == 1.0
        assert compute_knowledge_intensity(uids(100), uids(100)) == 1.0

    def test_clamp_boundary_is_seven_primary_edges(self) -> None:
        assert compute_knowledge_intensity(uids(6), []) < 1.0
        assert compute_knowledge_intensity(uids(7), []) == 1.0

    @pytest.mark.parametrize("count", [0, 1, 2, 3, 5, 6, 7, 8, 20])
    def test_empty_secondary_matches_primary_only_formula_bitwise(self, count: int) -> None:
        """The secondary-less domains' original formula, reproduced exactly.

        Habits/Goals/Events/Principles previously computed
        ``min(1.0, len(primary) * 0.15)``; they now pass an empty secondary
        list into the superset. Adding ``0 * 0.05`` must not perturb a single bit.
        """
        legacy = min(1.0, count * KnowledgeIntensityWeight.PRIMARY)
        assert compute_knowledge_intensity(uids(count), []).hex() == legacy.hex()

    def test_accepts_any_sequence_not_just_list(self) -> None:
        assert compute_knowledge_intensity(("a", "b"), ("c",)) == pytest.approx(0.35)
