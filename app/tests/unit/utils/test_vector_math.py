"""Unit tests for the shared vector-math helpers (core/utils/vector_math.py).

Locks in the guard behavior every prior copy relied on: empty, length-mismatched,
and zero-norm inputs return 0.0, and the pre-normalized dot path agrees with the
full cosine_similarity kernel.
"""

from __future__ import annotations

import math

import pytest

from core.utils.vector_math import cosine_similarity, dot, l2_norm, l2_normalize


class TestCosineSimilarity:
    def test_identical_vectors_return_one(self) -> None:
        assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors_return_zero(self) -> None:
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors_return_negative_one(self) -> None:
        assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_scaled_vectors_are_direction_invariant(self) -> None:
        assert cosine_similarity([1.0, 2.0], [10.0, 20.0]) == pytest.approx(1.0)

    def test_empty_input_returns_zero(self) -> None:
        assert cosine_similarity([], []) == 0.0
        assert cosine_similarity([1.0], []) == 0.0

    def test_length_mismatch_returns_zero(self) -> None:
        assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0]) == 0.0

    def test_zero_vector_returns_zero(self) -> None:
        assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


class TestVectorPrimitives:
    def test_dot_product(self) -> None:
        assert dot([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]) == pytest.approx(32.0)

    def test_l2_norm(self) -> None:
        assert l2_norm([3.0, 4.0]) == pytest.approx(5.0)

    def test_l2_normalize_produces_unit_vector(self) -> None:
        normalized = l2_normalize([3.0, 4.0])
        assert l2_norm(normalized) == pytest.approx(1.0)

    def test_l2_normalize_zero_vector_maps_to_zeros(self) -> None:
        assert l2_normalize([0.0, 0.0, 0.0]) == [0.0, 0.0, 0.0]

    def test_l2_normalize_empty_vector(self) -> None:
        assert l2_normalize([]) == []

    def test_prenormalized_dot_matches_cosine(self) -> None:
        a = [1.0, 2.0, 3.0, 4.0]
        b = [4.0, 3.0, 2.0, 1.0]
        prenormalized = dot(l2_normalize(a), l2_normalize(b))
        assert prenormalized == pytest.approx(cosine_similarity(a, b))
        assert not math.isnan(prenormalized)
