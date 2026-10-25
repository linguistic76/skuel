"""Life Path page bodies take their side gutters from the sidebar shell.

``lifepath_sidebar_page`` hands every body to ``SidebarPage``, whose content
column is already padded (``px-4 sm:px-6 lg:px-8``). A body that pads its own
sides as well doubles the gutter: at 375px two ``px-4`` put 64px of gutter
before the first card.
"""

import re
from collections.abc import Callable

import pytest
from fasthtml.common import FT

from core.models.type_hints import UserUID
from ui.lifepath.alignment import render_alignment_dashboard
from ui.lifepath.dashboard import render_dashboard_content
from ui.lifepath.vision import render_recommendations_page, render_vision_form

USER = UserUID("user_learner")

# A class that pads an element's left or right side, at any breakpoint.
SIDE_PADDING = re.compile(r"^(?:[a-z0-9]+:)*(?:p|px|pl|pr|ps|pe)-")


def _dashboard_before_a_vision() -> FT:
    return render_dashboard_content({"has_vision": False}, USER)


def _dashboard() -> FT:
    return render_dashboard_content({"has_vision": True}, USER)


def _recommendations() -> FT:
    return render_recommendations_page({}, USER)


def _alignment() -> FT:
    return render_alignment_dashboard({"alignment": {}}, USER)


BODIES: dict[str, Callable[[], FT]] = {
    "dashboard, no vision yet": _dashboard_before_a_vision,
    "dashboard": _dashboard,
    "vision form": render_vision_form,
    "recommendations": _recommendations,
    "alignment": _alignment,
}


@pytest.mark.parametrize("name", list(BODIES))
def test_a_body_does_not_pad_its_own_sides(name: str) -> None:
    classes = str(BODIES[name]().attrs.get("class", "")).split()

    assert [c for c in classes if SIDE_PADDING.match(c)] == []
