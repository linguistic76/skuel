"""``Visibility`` is public-or-not (ADR-088 §4).

The share links are the one record of who else may open an entity; the
property says only whether it is published. A third member would reintroduce
a second access record beside the edges, so the member set is pinned.
"""

from core.models.enums.metadata_enums import Visibility


def test_visibility_is_public_or_not() -> None:
    assert {member.value for member in Visibility} == {"private", "public"}


def test_only_public_is_public() -> None:
    assert Visibility.PUBLIC.is_public() is True
    assert Visibility.PRIVATE.is_public() is False


def test_retired_values_do_not_parse() -> None:
    for retired in ("shared", "team"):
        try:
            Visibility(retired)
        except ValueError:
            continue
        raise AssertionError(f"Visibility({retired!r}) parsed; the value is retired")
