"""The ``.md`` download of a UserEntry — what it carries and how it is named."""

from __future__ import annotations

from adapters.outbound.user_entry_renderer import entry_download_filename, render_user_entry_md
from core.models.user_entry.user_entry import UserEntry


def _entry(**overrides: object) -> UserEntry:
    fields: dict[str, object] = {
        "uid": "ue_render_1",
        "title": "Breath awareness, week one",
        "user_uid": "user_alice",
        "description": "What changed after five days.",
        "content": "Day one felt forced.",
        "processed_content": "PROCESSED",
    }
    fields.update(overrides)
    return UserEntry(**fields)  # type: ignore[arg-type]


def test_the_file_carries_title_description_and_body_only() -> None:
    text = render_user_entry_md(_entry())
    assert (
        text
        == "# Breath awareness, week one\n\nWhat changed after five days.\n\nDay one felt forced.\n"
    )
    assert "PROCESSED" not in text


def test_an_empty_body_is_said_not_hidden() -> None:
    assert render_user_entry_md(_entry(content=None, description=None)).endswith("_No content._\n")


def test_the_filename_is_an_ascii_slug_of_the_title() -> None:
    assert entry_download_filename(_entry()) == "entry-breath-awareness--week-one.md"


def test_a_non_latin_title_falls_back_to_the_uid() -> None:
    """A response header is Latin-1 on the wire: nothing outside ASCII may reach it."""
    name = entry_download_filename(_entry(title="呼吸の気づき"))
    assert name == "entry-ue_render_1.md"
    assert name.isascii()
    mixed = entry_download_filename(_entry(title="Дыхание week one"))
    assert mixed == "entry-week-one.md"


def test_a_non_latin_uid_falls_back_to_the_constant_name() -> None:
    """The uid is caller-supplied on the JSON door — it is slugged, never trusted."""
    name = entry_download_filename(_entry(uid="ue_呼吸", title="呼吸"))
    assert name == "entry-ue.md"
    bare = entry_download_filename(_entry(uid="呼吸", title="呼吸"))
    assert bare == "entry.md"
    assert bare.isascii()
