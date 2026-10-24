"""The tally behind ``./dev uid-census`` (scripts/uid_census.py), over fixture rows."""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from uid_census import (  # type: ignore[import-not-found]
    exit_code,
    failures,
    label_of,
    render,
    take_census,
)


def test_label_drops_entity() -> None:
    assert label_of(["Entity", "Task"]) == "Task"
    assert label_of(["Entity"]) == "Entity"


def test_each_uid_lands_in_one_verdict_per_label() -> None:
    census = take_census(
        [
            (["Entity", "Ku"], "ku.a.b"),
            (["Entity", "Ku"], "ku.Bad"),
            (["Entity", "Task"], "task_3f9a0c41d2e87b65"),
            (["Entity", "Task"], "task_a1b2c3d4"),
            (["ContentChunk"], "chunk_0123456789abcdef"),
            (["ReferenceChunk"], "resource.x:chunk:0"),
            (["Group"], "group.x.y.z.w"),
            (["User"], "user_admin"),
        ]
    )
    ku, task = census.by_label["Ku"], census.by_label["Task"]
    assert (ku.fits, ku.outside, ku.shape) == (1, 1, 0)
    assert (task.fits, task.outside, task.shape) == (1, 0, 1)
    assert census.by_label["ContentChunk"].fits == 1
    assert census.by_exemption[("Task", "UNREGISTERED")] == 1
    assert census.by_exemption[("User", "UNREGISTERED")] == 1
    assert census.by_exemption[("Ku", "UNREGISTERED")] == 1
    assert census.by_exemption[("ReferenceChunk", "UNREGISTERED")] == 1
    assert census.by_exemption[("Group", "UNREGISTERED")] == 1


def test_a_uid_two_nodes_hold_is_reported_with_both_labels() -> None:
    census = take_census(
        [
            (["Entity", "Ku"], "ku.a.b"),
            (["Content"], "ku.a.b"),
            (["Entity", "Task"], "task_3f9a0c41d2e87b65"),
        ]
    )
    assert census.shared == {"ku.a.b": ["Content", "Ku"]}
    text = render(census, {})
    assert "Uids held by more than one node:" in text
    assert "ku.a.b" in text and "Content, Ku" in text


def test_no_shared_uid_renders_none() -> None:
    census = take_census(
        [(["Entity", "Ku"], "ku.a.b"), (["ContentChunk"], "chunk_0123456789abcdef")]
    )
    assert census.shared == {}
    assert "Uids held by more than one node:\n  (none)" in render(census, {})


def test_a_census_that_fits_passes() -> None:
    census = take_census(
        [(["Entity", "Ku"], "ku.a.b"), (["Entity", "Task"], "task_3f9a0c41d2e87b65")]
    )
    assert failures(census) == []
    assert exit_code(census) == 0


def test_a_shared_uid_fails_the_census() -> None:
    census = take_census([(["Entity", "Ku"], "ku.a.b"), (["Group"], "ku.a.b")])
    assert failures(census) == ["1 uid(s) held by more than one node"]
    assert exit_code(census) == 1


def test_a_uid_outside_the_grammar_fails_the_census() -> None:
    census = take_census([(["Entity", "Ku"], "ku.Bad"), (["Group"], "group.x.y.z.w")])
    assert failures(census) == ["2 uid(s) outside the grammar (0 in a shape an exemption names)"]
    assert exit_code(census) == 1


def test_an_exempt_uid_fails_the_census_too() -> None:
    """An exemption names the writer that mints a shape; it never admits the uid."""
    census = take_census([(["Invoice"], "invoice:01234567-89ab-cdef-0123-456789abcdef")])
    assert census.by_exemption == {("Invoice", "invoice"): 1}
    assert failures(census) == ["1 uid(s) outside the grammar (1 in a shape an exemption names)"]
    assert exit_code(census) == 1


def test_render_names_what_retires_an_exemption_and_flags_the_unregistered() -> None:
    """A colon-form periodic uid left in the graph is unregistered — no writer mints it."""
    text = render(
        take_census(
            [
                (["Invoice"], "invoice:01234567-89ab-cdef-0123-456789abcdef"),
                (["UserEntry"], "ue:daily:user_a:2026-10-18"),
            ]
        ),
        {"IngestionMetadata": 3},
    )
    assert "| Invoice | 0 | 1 | 0 | 1 |" in text
    assert "invoice" in text and "ChargeKeep" in text
    assert "| UserEntry | 0 | 1 | 0 | 1 |" in text
    assert "UNREGISTERED" in text and "no exemption names this shape" in text
    assert "IngestionMetadata" in text
