"""The PathStep page's hero card: which state each reader's learning edges seed.

Completed is mastered, the learner's MASTERED edge. A step only marked as read seeds
``read``, a state short of completion, so the card never calls a step Completed while it
still blocks the step that requires it. ``tests/js/ps-hero-states.test.js`` runs
``static/js/ps-detail.js`` on the fixture this module pins, to check the same words in
the markup and the bundle's getters.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fasthtml.common import FT, Div, to_xml

from ui.explore.ps_detail import _action_bar, _progress_state

_FIXTURE = Path(__file__).resolve().parents[2] / "js" / "fixtures" / "ps-hero-states.html"


@pytest.mark.parametrize(
    ("is_mastered", "is_marked_read", "is_in_progress", "state"),
    [
        (True, False, False, "mastered"),
        (True, True, False, "mastered"),
        (True, True, True, "mastered"),
        (False, True, False, "read"),
        (False, True, True, "read"),
        (False, False, True, "learning"),
        (False, False, False, "not_started"),
    ],
)
def test_only_mastery_seeds_the_completed_state(
    is_mastered: bool, is_marked_read: bool, is_in_progress: bool, state: str
) -> None:
    assert (
        _progress_state(
            is_mastered=is_mastered, is_marked_read=is_marked_read, is_in_progress=is_in_progress
        )
        == state
    )


def _hero() -> FT:
    seed = {
        "uid": "ps.test.hero",
        "progress_state": _progress_state(
            is_mastered=True, is_marked_read=True, is_in_progress=False
        ),
    }
    return Div(_action_bar("ps.test.hero"), **{"x-data": f"pathstep({json.dumps(seed)})"})


def test_js_fixture_matches_the_rendered_action_bar() -> None:
    """``tests/js/ps-hero-states.test.js`` runs ``static/js/ps-detail.js`` on this markup."""
    rendered = to_xml(_hero())
    if os.environ.get("SKUEL_WRITE_JS_FIXTURES") == "1":
        _FIXTURE.write_text(rendered)
    assert _FIXTURE.read_text() == rendered, (
        f"{_FIXTURE} is stale — regenerate with SKUEL_WRITE_JS_FIXTURES=1 "
        "uv run pytest tests/unit/ui/test_ps_hero_states.py"
    )
