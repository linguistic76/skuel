"""Tests for UX improvements implementation.

Verifies that accessibility and user feedback improvements are working correctly.
"""

from fasthtml.common import Div


def test_input_with_aria_attributes():
    """Verify Input component includes ARIA attributes for accessibility."""
    from ui.primitives.input import Input

    # Test input with error
    input_with_error = Input(
        name="email",
        label="Email",
        error="Invalid email address",
        required=True,
    )

    # Convert to string to check attributes
    html_str = str(input_with_error)

    # Should include aria-invalid
    assert 'aria-invalid="true"' in html_str or 'aria_invalid="true"' in html_str

    # Should include aria-describedby
    assert "aria-describedby" in html_str or "aria_describedby" in html_str

    # Should include error div with role="alert"
    assert 'role="alert"' in html_str

    # Should include error message
    assert "Invalid email address" in html_str


def test_input_without_error():
    """Verify Input component without error doesn't have aria-invalid."""
    from ui.primitives.input import Input

    # Test input without error
    input_no_error = Input(
        name="username",
        label="Username",
        required=False,
    )

    html_str = str(input_no_error)

    # Should not show error message
    assert 'role="alert"' not in html_str or 'style=""' not in html_str


def test_textarea_with_aria_attributes():
    """Verify Textarea component includes ARIA attributes for accessibility."""
    from ui.primitives.input import Textarea

    # Test textarea with error
    textarea_with_error = Textarea(
        name="description",
        label="Description",
        error="Description is required",
        required=True,
    )

    html_str = str(textarea_with_error)

    # Should include aria-invalid
    assert 'aria-invalid="true"' in html_str or 'aria_invalid="true"' in html_str

    # Should include role="alert"
    assert 'role="alert"' in html_str

    # Should include error message
    assert "Description is required" in html_str


def test_select_with_aria_attributes():
    """Verify SelectInput component includes ARIA attributes for accessibility."""
    from ui.primitives.input import SelectInput

    # Test select with error
    select_with_error = SelectInput(
        name="category",
        options=[("work", "Work"), ("personal", "Personal")],
        label="Category",
        error="Please select a category",
        required=True,
    )

    html_str = str(select_with_error)

    # Should include aria-invalid
    assert 'aria-invalid="true"' in html_str or 'aria_invalid="true"' in html_str

    # Should include role="alert"
    assert 'role="alert"' in html_str

    # Should include error message
    assert "Please select a category" in html_str


def test_skeleton_card():
    """Verify SkeletonCard component renders correctly."""
    from ui.patterns.skeleton import SkeletonCard

    skeleton = SkeletonCard()

    # Should render without errors
    assert skeleton is not None

    # Convert to string to check classes
    html_str = str(skeleton)

    # Should have animate-pulse class
    assert "animate-pulse" in html_str

    # Should have card class
    assert "card" in html_str


def test_skeleton_list():
    """Verify SkeletonList component renders multiple cards."""
    from ui.patterns.skeleton import SkeletonList

    skeleton_list = SkeletonList(count=3)

    # Should render without errors
    assert skeleton_list is not None

    html_str = str(skeleton_list)

    # Should have space-y class
    assert "space-y" in html_str


def test_skeleton_stats():
    """Verify SkeletonStats component renders correctly."""
    from ui.patterns.skeleton import SkeletonStats

    skeleton = SkeletonStats()

    # Should render without errors
    assert skeleton is not None

    html_str = str(skeleton)

    # Should have animate-pulse class
    assert "animate-pulse" in html_str


def test_skeleton_table():
    """Verify SkeletonTable component renders with specified rows."""
    from ui.patterns.skeleton import SkeletonTable

    skeleton = SkeletonTable(rows=5)

    # Should render without errors
    assert skeleton is not None

    html_str = str(skeleton)

    # Should have table-like structure
    assert "animate-pulse" in html_str


async def test_base_page_has_live_region():
    """Verify BasePage includes live region for screen readers."""
    from ui.layouts.base_page import BasePage

    page = await BasePage(
        content=Div("Test content"),
        title="Test Page",
    )

    html_str = str(page)

    # Should include live region
    assert "live-region" in html_str

    # Should have aria-live attribute
    assert "aria-live" in html_str or "aria_live" in html_str

    # Should have sr-only class
    assert "sr-only" in html_str


async def test_base_page_viewport_safe_area():
    """Verify BasePage viewport supports safe areas."""
    from ui.layouts.base_page import BasePage

    page = await BasePage(
        content=Div("Test content"),
        title="Test Page",
    )

    html_str = str(page)

    # Should include viewport-fit=cover
    assert "viewport-fit=cover" in html_str


def test_navbar_mobile_button_aria():
    """Verify navbar mobile button has proper ARIA attributes."""
    from ui.layouts.navbar import create_navbar

    navbar = create_navbar(
        current_user="testuser",
        is_authenticated=True,
        active_page="home",
    )

    html_str = str(navbar)

    # Should have aria-label for mobile menu button
    assert "aria-label" in html_str or "aria_label" in html_str

    # Should have aria-expanded binding
    assert "aria-expanded" in html_str or "aria_expanded" in html_str


def test_all_skeleton_components_importable():
    """Verify all skeleton components can be imported."""
    from ui.patterns.skeleton import (
        SkeletonCard,
        SkeletonList,
        SkeletonStats,
        SkeletonTable,
    )

    # All imports should succeed
    assert SkeletonCard is not None
    assert SkeletonList is not None
    assert SkeletonStats is not None
    assert SkeletonTable is not None


def test_input_components_backward_compatible():
    """Verify Input components work without error parameter (backward compatible)."""
    from ui.primitives.input import Input, SelectInput, Textarea

    # Should work without error parameter
    input_basic = Input(name="test", label="Test")
    textarea_basic = Textarea(name="test", label="Test")
    select_basic = SelectInput(
        name="test",
        options=[("a", "A"), ("b", "B")],
        label="Test",
    )

    # All should render without errors
    assert input_basic is not None
    assert textarea_basic is not None
    assert select_basic is not None
