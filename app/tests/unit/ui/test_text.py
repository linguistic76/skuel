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


class TestSectionTitle:
    def test_basic(self) -> None:
        result = SectionTitle("My Section")
        assert "text-2xl" in str(result)
        assert "My Section" in str(result)


class TestSubtitle:
    def test_basic(self) -> None:
        result = Subtitle("Sub Header")
        assert "text-base" in str(result)
        assert "Sub Header" in str(result)


class TestBodyText:
    def test_default_color(self) -> None:
        result = BodyText("Hello world")
        rendered = str(result)
        assert "text-foreground" in rendered
        assert "Hello world" in rendered

    def test_muted(self) -> None:
        result = BodyText("Muted text", muted=True)
        assert "text-muted-foreground" in str(result)


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


class TestCaption:
    def test_basic(self) -> None:
        result = Caption("LABEL")
        rendered = str(result)
        assert "text-xs" in rendered
        assert "uppercase" in rendered
        assert "LABEL" in rendered


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
