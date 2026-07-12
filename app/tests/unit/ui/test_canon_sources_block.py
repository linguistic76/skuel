"""Kind-aware links in the shared CanonSourcesBlock (ADR-076 + canon P3).

One renderer, two destinations: a CANON book links to its Resource page, a
VAULT note to its owner-verified /gradebook/{uid} detail — each kind's
"point to the raw" target, with its own icon.
"""

from fasthtml.common import to_xml

from core.services.canon import CanonSource, SourceKind
from ui.canon.sources_block import CanonSourcesBlock


def _canon_source() -> CanonSource:
    return CanonSource(
        book_title="Hypermedia Systems",
        resource_uid="resource.hms",
        locators=("Hypermedia Concepts",),
    )


def _vault_source() -> CanonSource:
    return CanonSource(
        book_title="My Stoicism Notes",
        resource_uid="ue_note_1",
        locators=("knowledge/stoicism.md",),
        source_kind=SourceKind.VAULT,
    )


def _icon_svg(name: str) -> str:
    """The inline SVG Icon(name) renders — icons carry no name in the markup,
    so the kind-aware glyph is asserted by its rendered SVG text."""
    from ui.components import Icon

    return str(Icon(name, size=13, cls="inline-block mr-1 align-[-2px]"))


def test_canon_source_links_to_resource_page() -> None:
    html = to_xml(CanonSourcesBlock((_canon_source(),)))
    assert "/library/resources/get?uid=resource.hms" in html
    assert "Hypermedia Systems" in html
    assert _icon_svg("book-open") in html
    assert "/gradebook/" not in html


def test_vault_source_links_to_gradebook_detail() -> None:
    html = to_xml(CanonSourcesBlock((_vault_source(),)))
    assert "/gradebook/ue_note_1" in html
    assert "My Stoicism Notes" in html
    assert _icon_svg("file-text") in html
    assert "knowledge/stoicism.md" in html
    assert "/library/resources/get" not in html


def test_mixed_sources_render_each_kind_correctly() -> None:
    html = to_xml(CanonSourcesBlock((_canon_source(), _vault_source())))
    assert "/library/resources/get?uid=resource.hms" in html
    assert "/gradebook/ue_note_1" in html
