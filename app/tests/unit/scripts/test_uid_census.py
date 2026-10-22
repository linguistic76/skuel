"""The tally behind ``./dev uid-census`` (scripts/uid_census.py), over fixture rows."""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from uid_census import label_of, render, take_census  # type: ignore[import-not-found]


def test_label_drops_entity() -> None:
    assert label_of(["Entity", "Task"]) == "Task"
    assert label_of(["Entity"]) == "Entity"


def test_each_uid_lands_in_one_verdict_per_label() -> None:
    census = take_census(
        [
            (["Entity", "Ku"], "ku.a.b"),
            (["Entity", "Ku"], "ku.Bad"),
            (["Entity", "Task"], "task_a1b2c3d4"),
            (["Entity", "Task"], "task_van-on-monday_5873a134"),
            (["ContentChunk"], "ku.a.b:chunk:0"),
            (["Group"], "group.x.y.z.w"),
        ]
    )
    ku, task = census.by_label["Ku"], census.by_label["Task"]
    assert (ku.fits, ku.outside, ku.shape) == (1, 1, 0)
    assert (task.fits, task.outside, task.shape) == (1, 0, 1)
    assert census.by_exemption[("Task", "named_generated")] == 1
    assert census.by_exemption[("ContentChunk", "chunk")] == 1
    assert census.by_exemption[("Ku", "UNREGISTERED")] == 1
    assert census.by_exemption[("Group", "UNREGISTERED")] == 1


def test_a_shape_two_exemptions_share_is_counted_under_both_names() -> None:
    census = take_census([(["User"], "user_foo_12345678")])
    assert census.by_exemption == {("User", "named_generated+user_from_username"): 1}
    text = render(census, {})
    assert "remaining generated shapes" in text and "username rule" in text
    assert "no exemption names this shape" not in text


def test_render_names_the_migrating_pr_and_flags_the_unregistered() -> None:
    text = render(
        take_census([(["UserEntry"], "ue:daily:user_a:2026-10-18"), (["Ku"], "ku.Bad")]),
        {"IngestionMetadata": 3},
    )
    assert "| UserEntry | 0 | 1 | 0 | 1 |" in text
    assert "periodic_note" in text and "PR 3" in text
    assert "UNREGISTERED" in text and "no exemption names this shape" in text
    assert "IngestionMetadata" in text
