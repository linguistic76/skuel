"""
Tests for UI Layout Components
================================

Verifies class strings contain expected Tailwind classes.
"""

from ui.layout import (
    Container,
    DivHStacked,
    DivVStacked,
    FlexItem,
    Grid,
    Row,
    Size,
    Stack,
)

# ============================================================================
# Size enum
# ============================================================================


class TestSize:
    def test_values(self) -> None:
        assert Size.xs == "xs"
        assert Size.sm == "sm"
        assert Size.md == "md"
        assert Size.lg == "lg"
        assert Size.xl == "xl"


# ============================================================================
# DivHStacked
# ============================================================================


class TestDivHStacked:
    def test_default_classes(self) -> None:
        result = DivHStacked("child")
        rendered = str(result)
        assert "flex" in rendered
        assert "flex-row" in rendered
        assert "gap-2" in rendered
        assert "items-center" in rendered

    def test_custom_gap(self) -> None:
        result = DivHStacked("child", gap=6)
        assert "gap-6" in str(result)

    def test_custom_align(self) -> None:
        result = DivHStacked("child", align="start")
        assert "items-start" in str(result)

    def test_additional_cls(self) -> None:
        result = DivHStacked("child", cls="mt-4")
        assert "mt-4" in str(result)


# ============================================================================
# DivVStacked
# ============================================================================


class TestDivVStacked:
    def test_default_classes(self) -> None:
        result = DivVStacked("child")
        rendered = str(result)
        assert "flex" in rendered
        assert "flex-col" in rendered
        assert "gap-2" in rendered
        assert "items-stretch" in rendered

    def test_custom_gap(self) -> None:
        result = DivVStacked("child", gap=8)
        assert "gap-8" in str(result)

    def test_custom_align(self) -> None:
        result = DivVStacked("child", align="center")
        assert "items-center" in str(result)


# ============================================================================
# Grid
# ============================================================================


class TestGrid:
    def test_default_responsive(self) -> None:
        result = Grid("item1", "item2", cols=2)
        rendered = str(result)
        assert "grid" in rendered
        assert "sm:grid-cols-2" in rendered

    def test_3_col_responsive(self) -> None:
        result = Grid("a", "b", "c", cols=3)
        rendered = str(result)
        assert "lg:grid-cols-3" in rendered

    def test_4_col_responsive(self) -> None:
        result = Grid("a", "b", "c", "d", cols=4)
        rendered = str(result)
        assert "lg:grid-cols-4" in rendered

    def test_non_responsive(self) -> None:
        result = Grid("a", "b", cols=3, responsive=False)
        rendered = str(result)
        assert "grid-cols-3" in rendered

    def test_custom_gap(self) -> None:
        result = Grid("a", cols=1, gap=8)
        assert "gap-8" in str(result)

    def test_5_col_responsive(self) -> None:
        result = Grid("a", "b", "c", "d", "e", cols=5, responsive=True)
        assert "xl:grid-cols-5" in str(result)


# ============================================================================
# Container
# ============================================================================


class TestContainer:
    def test_default_size(self) -> None:
        result = Container("content")
        rendered = str(result)
        assert "container" in rendered
        assert "mx-auto" in rendered
        assert "max-w-7xl" in rendered

    def test_custom_size(self) -> None:
        result = Container("content", size="3xl")
        assert "max-w-3xl" in str(result)


# ============================================================================
# Stack
# ============================================================================


class TestStack:
    def test_default(self) -> None:
        result = Stack("child")
        rendered = str(result)
        assert "flex" in rendered
        assert "flex-col" in rendered
        assert "gap-4" in rendered

    def test_custom_gap(self) -> None:
        result = Stack("child", gap=2)
        assert "gap-2" in str(result)


# ============================================================================
# Row
# ============================================================================


class TestRow:
    def test_default(self) -> None:
        result = Row("child")
        rendered = str(result)
        assert "flex" in rendered
        assert "items-center" in rendered
        assert "gap-4" in rendered
        assert "min-w-0" in rendered

    def test_custom_align(self) -> None:
        result = Row("child", align="items-start")
        assert "items-start" in str(result)


# ============================================================================
# FlexItem
# ============================================================================


class TestFlexItem:
    def test_default(self) -> None:
        result = FlexItem("child")
        rendered = str(result)
        assert "shrink" in rendered
        assert "min-w-0" in rendered
        assert "overflow-hidden" in rendered

    def test_grow(self) -> None:
        result = FlexItem("child", grow=True)
        assert "grow" in str(result)

    def test_no_shrink(self) -> None:
        result = FlexItem("child", shrink=False)
        assert "shrink-0" in str(result)
