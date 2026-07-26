"""Journals upload form ↔ ProcessingMode coverage.

``_MODE_CONFIGS`` is keyed by the enum, so a new member cannot ship without a
card. The Alpine default lives in a JS literal (a plain string full of braces,
not an f-string), so it is pinned here against the rendered output rather than
by construction.
"""

from __future__ import annotations

import pytest
from fasthtml.common import to_xml

from core.models.enums.pipeline import ProcessingMode
from ui.journals.forms import _MODE_CONFIGS, render_right_panel, render_upload_form


class TestModeConfigCoverage:
    @pytest.mark.parametrize("mode", list(ProcessingMode))
    def test_every_member_has_a_card(self, mode: ProcessingMode) -> None:
        assert mode in _MODE_CONFIGS

    def test_no_extra_keys(self) -> None:
        assert set(_MODE_CONFIGS) == set(ProcessingMode)

    @pytest.mark.parametrize("mode", list(ProcessingMode))
    def test_card_is_fully_populated(self, mode: ProcessingMode) -> None:
        cfg = _MODE_CONFIGS[mode]
        assert cfg.keys() == {"icon", "title", "desc"}
        assert all(v.strip() for v in cfg.values())

    def test_titles_are_distinct(self) -> None:
        titles = [cfg["title"] for cfg in _MODE_CONFIGS.values()]
        assert len(set(titles)) == len(ProcessingMode)


@pytest.mark.parametrize("render", [render_upload_form, render_right_panel])
class TestRenderedForm:
    """Both forms — the full ``/submissions/journal`` one and the compact
    ``/journals`` right panel — carry the same wire contract."""

    def test_emits_every_mode_value(self, render: object) -> None:
        html = to_xml(render(is_founder=True))  # type: ignore[operator]
        for mode in ProcessingMode:
            assert f"processingMode === '{mode.value}'" in html

    def test_alpine_default_matches_enum_default(self, render: object) -> None:
        # The JS literal and ProcessingMode.default() must not drift: the server
        # treats an absent field as default(), so the client must preselect it.
        html = to_xml(render(is_founder=True))  # type: ignore[operator]
        assert f"processingMode: '{ProcessingMode.default().value}'" in html

    def test_posts_the_mode_as_a_hidden_field(self, render: object) -> None:
        html = to_xml(render(is_founder=True))  # type: ignore[operator]
        assert 'name="processing_mode"' in html
