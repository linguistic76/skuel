"""
Tests for UI Button Components
================================

Verifies ButtonT enum, variant/size mapping, and component builders.
"""

from ui.buttons import _SIZE_MAP, _VARIANT_MAP, Button, ButtonLink, ButtonT, IconButton
from ui.layout import Size

# ============================================================================
# ButtonT enum
# ============================================================================


class TestButtonT:
    def test_all_variants_exist(self) -> None:
        expected = {
            "primary",
            "secondary",
            "accent",
            "neutral",
            "ghost",
            "link",
            "info",
            "success",
            "warning",
            "error",
            "outline",
        }
        assert {v.value for v in ButtonT} == expected


# ============================================================================
# Mapping logic
# ============================================================================


class TestVariantMap:
    def test_all_variants_mapped(self) -> None:
        for variant in ButtonT:
            assert variant.value in _VARIANT_MAP, f"{variant.value} missing from _VARIANT_MAP"

    def test_error_maps_to_destructive(self) -> None:
        from monsterui.franken import ButtonT as MButtonT

        assert _VARIANT_MAP["error"] == MButtonT.destructive


class TestSizeMap:
    def test_all_sizes_mapped(self) -> None:
        for size in Size:
            assert size.value in _SIZE_MAP, f"{size.value} missing from _SIZE_MAP"

    def test_md_maps_to_empty(self) -> None:
        assert _SIZE_MAP["md"] == ""


# ============================================================================
# Button
# ============================================================================


class TestButton:
    def test_default_variant(self) -> None:
        result = Button("Click me")
        assert result is not None

    def test_secondary_variant(self) -> None:
        result = Button("Cancel", variant=ButtonT.secondary)
        assert result is not None

    def test_with_size(self) -> None:
        result = Button("Small", size=Size.sm)
        assert result is not None

    def test_disabled(self) -> None:
        result = Button("Disabled", disabled=True)
        assert result is not None

    def test_loading(self) -> None:
        result = Button("Loading", loading=True)
        assert result is not None


# ============================================================================
# ButtonLink
# ============================================================================


class TestButtonLink:
    def test_basic(self) -> None:
        result = ButtonLink("Go", href="/dashboard")
        rendered = str(result)
        assert "/dashboard" in rendered
        assert "Go" in rendered

    def test_variant(self) -> None:
        result = ButtonLink("Nav", href="/page", variant=ButtonT.ghost)
        assert result is not None

    def test_with_size(self) -> None:
        result = ButtonLink("Small link", href="/x", size=Size.sm)
        assert result is not None


# ============================================================================
# IconButton
# ============================================================================


class TestIconButton:
    def test_basic(self) -> None:
        result = IconButton("✏️")
        assert result is not None

    def test_with_label(self) -> None:
        result = IconButton("🗑️", label="Delete item")
        assert result is not None

    def test_variant(self) -> None:
        result = IconButton("+", variant=ButtonT.primary)
        assert result is not None

    def test_with_size(self) -> None:
        result = IconButton("✅", size=Size.xs)
        assert result is not None
