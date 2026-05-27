"""Unit tests for the activity → curriculum origin surfacing (Gap #3).

Spawned activities carry ``source_path_step_uid``; the detail page resolves it
to the source PathStep's title and renders a breadcrumb link
(``CurriculumOriginField``) back to ``/explore/ps/{uid}``.

The resolution query (``fetch_source_pathstep``) was relocated below the
hexagonal boundary (ADR-044); its behavior is covered by
``tests/unit/test_connection_fetch_backend.py``. This module keeps the
presentation-layer assertions for the breadcrumb field itself.
"""

from ui.activities._shared import CONNECTION_ICONS, CurriculumOriginField


class TestCurriculumOriginField:
    def test_renders_link_to_pathstep_detail(self):
        html = str(CurriculumOriginField("ps:demo:step-1", "Intro to Patterns"))
        assert "/explore/ps/ps:demo:step-1" in html
        assert "Intro to Patterns" in html

    def test_falls_back_to_uid_when_title_empty(self):
        html = str(CurriculumOriginField("ps:demo:step-1", ""))
        assert "ps:demo:step-1" in html

    def test_path_step_icon_links_to_explore_ps(self):
        # The dead "#" href was replaced so path_step badges navigate.
        assert CONNECTION_ICONS["path_step"][1] == "/explore/ps/"
