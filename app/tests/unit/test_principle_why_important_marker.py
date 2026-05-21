"""
Unit Tests: Principle why_important marker round-trip
======================================================

``why_important`` is a request-only field — Principle's domain model has no
dedicated column, so the create/update flow folds it into ``description`` with
a fixed marker. These tests pin the marker shape and the
``merge_why_important`` / ``split_why_important`` round-trip so the constant
can't silently drift between the three consumers (model helper,
PrinciplesCoreService.create_principle, principles_ui edit submit).
"""

from __future__ import annotations

import pytest

from core.models.principle.principle import (
    WHY_IMPORTANT_MARKER,
    merge_why_important,
    split_why_important,
)


@pytest.mark.parametrize(
    ("description", "why_important", "expected"),
    [
        ("Prose", "matters", f"Prose{WHY_IMPORTANT_MARKER}matters"),
        (None, "matters", "matters"),
        ("Prose", None, "Prose"),
        (None, None, None),
        ("", "matters", "matters"),
        ("Prose", "", "Prose"),
    ],
)
def test_merge_why_important(
    description: str | None, why_important: str | None, expected: str | None
) -> None:
    assert merge_why_important(description, why_important) == expected


@pytest.mark.parametrize(
    ("merged", "expected"),
    [
        (f"Prose{WHY_IMPORTANT_MARKER}matters", ("Prose", "matters")),
        ("Prose only", ("Prose only", None)),
        (None, (None, None)),
        ("", (None, None)),
        # rpartition keeps the last marker as the boundary — earlier marker text
        # in the prose stays in the prose half.
        (
            f"First{WHY_IMPORTANT_MARKER}old{WHY_IMPORTANT_MARKER}new",
            (f"First{WHY_IMPORTANT_MARKER}old", "new"),
        ),
    ],
)
def test_split_why_important(merged: str | None, expected: tuple[str | None, str | None]) -> None:
    assert split_why_important(merged) == expected


@pytest.mark.parametrize(
    ("description", "why_important"),
    [
        ("Prose", "matters"),
        ("Multi\nline prose", "Multi\nline reason"),
        ("With trailing newline\n", "matters"),
    ],
)
def test_round_trip(description: str, why_important: str) -> None:
    """Merge then split returns the original parts."""
    merged = merge_why_important(description, why_important)
    assert split_why_important(merged) == (description, why_important)
