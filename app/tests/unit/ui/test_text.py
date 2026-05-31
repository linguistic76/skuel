"""
Tests for UI Typography Components
====================================

Verifies tag types and Tailwind classes for all 7 typography helpers.
"""

from ui.text import (
    BodyText,
    Caption,
    PageTitle,
    SectionTitle,
    SmallText,
    Subtitle,
    TruncatedText,
)


class TestPageTitle:
    def test_basic(self) -> None:
        result = PageTitle("Dashboard")
        assert "text-4xl" in str(result)
        assert "Dashboard" in str(result)

    def test_with_subtitle(self) -> None:
        result = PageTitle("Dashboard", subtitle="Welcome back")
        rendered = str(result)
        assert "Dashboard" in rendered
        assert "Welcome back" in rendered
        assert "text-lg" in rendered

    def test_without_subtitle(self) -> None:
        result = PageTitle("Solo title")
        rendered = str(result)
        assert "Solo title" in rendered

    def test_cls_merges(self) -> None:
        # cls must merge with the base classes, not collide with them (regression).
        rendered = str(PageTitle("Dashboard", cls="border-b"))
        assert "mb-8" in rendered
        assert "border-b" in rendered


class TestSectionTitle:
    def test_basic(self) -> None:
        result = SectionTitle("My Section")
        assert "text-2xl" in str(result)
        assert "My Section" in str(result)

    def test_cls_merges(self) -> None:
        rendered = str(SectionTitle("My Section", cls="text-center"))
        assert "text-2xl" in rendered
        assert "text-center" in rendered


class TestSubtitle:
    def test_basic(self) -> None:
        result = Subtitle("Sub Header")
        assert "text-base" in str(result)
        assert "Sub Header" in str(result)

    def test_cls_merges(self) -> None:
        rendered = str(Subtitle("Sub Header", cls="italic"))
        assert "text-base" in rendered
        assert "italic" in rendered


class TestBodyText:
    def test_default_color(self) -> None:
        result = BodyText("Hello world")
        rendered = str(result)
        assert "text-foreground" in rendered
        assert "Hello world" in rendered

    def test_muted(self) -> None:
        result = BodyText("Muted text", muted=True)
        assert "text-muted-foreground" in str(result)

    def test_cls_merges(self) -> None:
        rendered = str(BodyText("Hello world", cls="max-w-prose"))
        assert "text-base" in rendered
        assert "max-w-prose" in rendered


class TestSmallText:
    def test_default_muted(self) -> None:
        result = SmallText("Small note")
        rendered = str(result)
        assert "text-sm" in rendered
        assert "text-muted-foreground" in rendered

    def test_not_muted(self) -> None:
        result = SmallText("Small emphasis", muted=False)
        rendered = str(result)
        assert "text-foreground" in rendered

    def test_cls_merges(self) -> None:
        # The exact call site that 500'd /insights (insight_card.py:89).
        rendered = str(SmallText("Recommended Actions:", cls="font-semibold mb-1"))
        assert "text-sm" in rendered
        assert "font-semibold" in rendered
        assert "mb-1" in rendered


class TestCaption:
    def test_basic(self) -> None:
        result = Caption("LABEL")
        rendered = str(result)
        assert "text-xs" in rendered
        assert "uppercase" in rendered
        assert "LABEL" in rendered

    def test_cls_merges(self) -> None:
        rendered = str(Caption("LABEL", cls="text-red-500"))
        assert "text-xs" in rendered
        assert "text-red-500" in rendered


class TestTruncatedText:
    def test_single_line(self) -> None:
        result = TruncatedText("Long text...", lines=1)
        assert "line-clamp-1" in str(result)

    def test_multi_line(self) -> None:
        result = TruncatedText("Long text...", lines=3)
        assert "line-clamp-3" in str(result)

    def test_clamped_to_range(self) -> None:
        result = TruncatedText("text", lines=0)
        assert "line-clamp-1" in str(result)  # min 1

        result = TruncatedText("text", lines=10)
        assert "line-clamp-3" in str(result)  # max 3

    def test_extra_cls(self) -> None:
        result = TruncatedText("text", cls="text-red-500")
        assert "text-red-500" in str(result)
