"""Unit tests for ui.components — the SKUEL-owned Tailwind component layer.

Each test verifies the component produces valid FT output without error.
Class-string content is checked structurally (substring / set membership),
not as exact string equality, so minor whitespace differences don't break tests.
"""

from __future__ import annotations

from fasthtml.common import Div, to_xml

from ui.components._util import _cls
from ui.components.accordion import Accordion, AccordionItem
from ui.components.button import _BTN_SIZES, Button, ButtonT
from ui.components.card import Card, CardBody, CardFooter, CardHeader, CardTitle
from ui.components.divider import Divider, DividerLine, DividerSplit, DividerT
from ui.components.feedback import Alert, AlertT, Loading
from ui.components.form import (
    Input,
    Label,
    LabelCheckbox,
    LabelInput,
    LabelSelect,
    LabelTextArea,
    Radio,
    Range,
    Select,
    Switch,
    TextArea,
)
from ui.components.icon import Icon
from ui.components.layout import Center, DivCentered, DivFullySpaced
from ui.components.nav import TabContainer
from ui.components.table import (
    Table,
    TableFromDicts,
    TableFromLists,
    TableT,
    Tbody,
    Td,
    Th,
    Thead,
    Tr,
)

# ============================================================================
# _cls utility
# ============================================================================


class TestCls:
    def test_str_only(self) -> None:
        assert _cls("foo bar") == "foo bar"

    def test_two_strings(self) -> None:
        assert _cls("a", "b") == "a b"

    def test_tuple_flattened(self) -> None:
        assert _cls("base", ("x", "y")) == "base x y"

    def test_list_flattened(self) -> None:
        assert _cls(["a", "b"], "c") == "a b c"

    def test_empty_string_skipped(self) -> None:
        assert _cls("a", "", "b") == "a b"

    def test_none_skipped(self) -> None:
        assert _cls("a", None, "b") == "a b"

    def test_all_empty(self) -> None:
        assert _cls("", None, ()) == ""

    def test_strips_trailing_space(self) -> None:
        result = _cls("a ")
        assert result == "a"

    def test_enum_value(self) -> None:
        result = _cls(ButtonT.primary)
        assert "bg-primary" in result

    def test_tuple_of_enums(self) -> None:
        result = _cls((ButtonT.primary, ButtonT.sm))
        assert "bg-primary" in result
        assert "h-8" in result


# ============================================================================
# ButtonT enum
# ============================================================================


class TestButtonT:
    def test_all_variants_non_empty(self) -> None:
        for variant in ButtonT:
            assert str(variant), f"ButtonT.{variant.name} has empty class string"

    def test_primary_contains_bg_primary(self) -> None:
        assert "bg-primary" in ButtonT.primary

    def test_destructive_contains_destructive(self) -> None:
        assert "destructive" in ButtonT.destructive

    def test_ghost_no_background(self) -> None:
        assert "bg-" not in ButtonT.ghost or "hover:bg-" in ButtonT.ghost

    def test_size_sm_has_h8(self) -> None:
        assert "h-8" in ButtonT.sm

    def test_size_lg_has_h11(self) -> None:
        assert "h-11" in ButtonT.lg

    def test_all_variants_are_strings(self) -> None:
        for variant in ButtonT:
            assert isinstance(str(variant), str)

    def test_distinct_style_variants(self) -> None:
        variants = [
            ButtonT.default,
            ButtonT.primary,
            ButtonT.secondary,
            ButtonT.ghost,
            ButtonT.destructive,
            ButtonT.link,
        ]
        unique = set(variants)
        assert len(unique) == len(variants), "ButtonT style variants must be distinct"


# ============================================================================
# Button component
# ============================================================================


class TestButton:
    def test_renders_without_error(self) -> None:
        result = Button("Click me")
        assert result is not None

    def test_base_classes_present(self) -> None:
        xml = to_xml(Button("x"))
        assert "inline-flex" in xml

    def test_default_variant_applied(self) -> None:
        xml = to_xml(Button("x"))
        assert "bg-background" in xml or "border-input" in xml

    def test_primary_variant(self) -> None:
        xml = to_xml(Button("x", cls=ButtonT.primary))
        assert "bg-primary" in xml

    def test_tuple_cls_composition(self) -> None:
        xml = to_xml(Button("x", cls=(ButtonT.primary, ButtonT.sm)))
        assert "bg-primary" in xml
        assert "h-8" in xml

    def test_base_always_present(self) -> None:
        for variant in ButtonT:
            xml = to_xml(Button("x", cls=variant))
            assert "inline-flex" in xml, f"Base missing for {variant.name}"

    def test_kwargs_passthrough(self) -> None:
        xml = to_xml(Button("x", id="my-btn", type="submit"))
        assert 'id="my-btn"' in xml
        assert 'type="submit"' in xml

    def test_htmx_attrs_passthrough(self) -> None:
        xml = to_xml(Button("x", **{"hx_post": "/submit"}))
        assert "hx-post" in xml

    def test_custom_cls_added(self) -> None:
        xml = to_xml(Button("x", cls="my-extra-class"))
        assert "my-extra-class" in xml

    def test_default_size_md_applied(self) -> None:
        xml = to_xml(Button("x", cls=ButtonT.primary))
        assert "h-9" in xml

    def test_size_sm(self) -> None:
        xml = to_xml(Button("x", size="sm"))
        assert "h-8" in xml

    def test_size_lg(self) -> None:
        xml = to_xml(Button("x", size="lg"))
        assert "h-11" in xml

    def test_size_kwarg_and_style_cls_coexist(self) -> None:
        xml = to_xml(Button("x", cls=ButtonT.primary, size="sm"))
        assert "bg-primary" in xml
        assert "h-8" in xml

    def test_all_sizes_defined(self) -> None:
        for size_name in ("xs", "sm", "md", "lg", "xl"):
            assert size_name in _BTN_SIZES
            assert _BTN_SIZES[size_name]


# ============================================================================
# Card family
# ============================================================================


class TestCard:
    def test_card_renders(self) -> None:
        assert Card("content") is not None

    def test_card_has_rounded_border(self) -> None:
        xml = to_xml(Card("x"))
        assert "rounded-lg" in xml
        assert "border" in xml
        assert "bg-card" in xml

    def test_card_header_renders(self) -> None:
        xml = to_xml(CardHeader("title"))
        assert "p-6" in xml

    def test_card_title_renders(self) -> None:
        xml = to_xml(CardTitle("My Title"))
        assert "font-semibold" in xml

    def test_card_body_renders(self) -> None:
        xml = to_xml(CardBody("body"))
        assert "p-6" in xml

    def test_card_footer_renders(self) -> None:
        xml = to_xml(CardFooter("footer"))
        assert "flex" in xml

    def test_card_nesting(self) -> None:
        result = Card(
            CardHeader(CardTitle("Title")),
            CardBody("Body"),
            CardFooter("Footer"),
        )
        xml = to_xml(result)
        assert "bg-card" in xml
        assert "font-semibold" in xml

    def test_card_cls_merged(self) -> None:
        xml = to_xml(Card("x", cls="extra-cls"))
        assert "extra-cls" in xml
        assert "rounded-lg" in xml

    def test_card_kwargs_passthrough(self) -> None:
        xml = to_xml(Card("x", id="card-1"))
        assert 'id="card-1"' in xml


# ============================================================================
# Icon
# ============================================================================


class TestIcon:
    # Icon() returns an inline-SVG NotStr (a str); production nests it inside FT
    # trees, so assert on str(Icon(...)). See ui/components/icon.py.
    def test_renders_without_error(self) -> None:
        assert Icon("check") is not None

    def test_renders_inline_svg(self) -> None:
        # Server-rendered inline SVG — no lucide data-lucide attribute.
        markup = str(Icon("check"))
        assert "<svg" in markup
        assert "data-lucide" not in markup
        assert "<path" in markup  # check icon geometry

    def test_icon_name_x(self) -> None:
        markup = str(Icon("x"))
        assert "<svg" in markup
        assert "data-lucide" not in markup

    def test_unknown_name_falls_back(self) -> None:
        # Unknown names render the help-circle fallback, never blank / never error.
        markup = str(Icon("definitely-not-an-icon"))
        assert "<svg" in markup
        assert "<path" in markup

    def test_nests_in_ft_tree(self) -> None:
        # The real usage: Icon embedded in an FT element renders unescaped via to_xml.
        xml = to_xml(Div(Icon("check")))
        assert "<svg" in xml
        assert "&lt;svg" not in xml  # not HTML-escaped

    def test_size_emitted(self) -> None:
        assert "24px" in str(Icon("check", size=24))

    def test_cls_passthrough(self) -> None:
        assert "text-blue-600" in str(Icon("check", cls="text-blue-600"))

    def test_kwargs_passthrough(self) -> None:
        assert 'id="icon-1"' in str(Icon("check", id="icon-1"))

    def test_different_icons_differ(self) -> None:
        assert str(Icon("check")) != str(Icon("x"))


# ============================================================================
# Alert / AlertT
# ============================================================================


class TestAlertT:
    def test_all_variants_defined(self) -> None:
        assert AlertT.info == "info"
        assert AlertT.success == "success"
        assert AlertT.warning == "warning"
        assert AlertT.error == "error"


class TestAlert:
    def test_renders_without_error(self) -> None:
        assert Alert("message") is not None

    def test_role_alert(self) -> None:
        xml = to_xml(Alert("x"))
        assert 'role="alert"' in xml

    def test_default_info_variant(self) -> None:
        xml = to_xml(Alert("x"))
        assert "blue" in xml

    def test_success_variant(self) -> None:
        xml = to_xml(Alert("x", variant=AlertT.success))
        assert "green" in xml

    def test_warning_variant(self) -> None:
        xml = to_xml(Alert("x", variant=AlertT.warning))
        assert "yellow" in xml

    def test_error_variant(self) -> None:
        xml = to_xml(Alert("x", variant=AlertT.error))
        assert "red" in xml

    def test_variants_produce_distinct_classes(self) -> None:
        classes = {v: to_xml(Alert("x", variant=v)) for v in AlertT}
        xmls = list(classes.values())
        assert len(set(xmls)) == len(xmls), "Alert variants must produce distinct output"

    def test_cls_merged(self) -> None:
        xml = to_xml(Alert("x", cls="mt-4"))
        assert "mt-4" in xml

    def test_kwargs_passthrough(self) -> None:
        xml = to_xml(Alert("x", id="alert-1"))
        assert 'id="alert-1"' in xml


# ============================================================================
# Loading
# ============================================================================


class TestLoading:
    def test_renders_without_error(self) -> None:
        assert Loading() is not None

    def test_has_animate_spin(self) -> None:
        xml = to_xml(Loading())
        assert "animate-spin" in xml

    def test_role_status(self) -> None:
        xml = to_xml(Loading())
        assert 'role="status"' in xml

    def test_size_md(self) -> None:
        xml = to_xml(Loading(size="md"))
        assert "w-6" in xml

    def test_size_sm(self) -> None:
        xml = to_xml(Loading(size="sm"))
        assert "w-4" in xml

    def test_size_lg(self) -> None:
        xml = to_xml(Loading(size="lg"))
        assert "w-8" in xml

    def test_cls_merged(self) -> None:
        xml = to_xml(Loading(cls="text-blue-500"))
        assert "text-blue-500" in xml


# ============================================================================
# Divider
# ============================================================================


class TestDivider:
    def test_plain_divider(self) -> None:
        xml = to_xml(Divider())
        assert "border-t" in xml

    def test_divider_with_label(self) -> None:
        xml = to_xml(Divider("OR"))
        assert "OR" in xml
        assert "border-t" in xml

    def test_divider_line(self) -> None:
        xml = to_xml(DividerLine())
        assert "border-t" in xml

    def test_divider_split_is_alias(self) -> None:
        xml_d = to_xml(Divider("or"))
        xml_s = to_xml(DividerSplit("or"))
        assert xml_d == xml_s

    def test_divider_t_default_empty(self) -> None:
        assert str(DividerT.default) == ""


# ============================================================================
# Table family
# ============================================================================


class TestTable:
    def test_table_renders(self) -> None:
        assert Table() is not None

    def test_table_from_lists(self) -> None:
        xml = to_xml(TableFromLists(["Name", "Age"], [["Alice", "30"], ["Bob", "25"]]))
        assert "Name" in xml
        assert "Alice" in xml
        assert "Bob" in xml

    def test_table_from_dicts(self) -> None:
        data = [{"name": "Alice", "age": "30"}, {"name": "Bob", "age": "25"}]
        xml = to_xml(TableFromDicts(data))
        assert "name" in xml.lower()
        assert "Alice" in xml

    def test_table_from_dicts_empty(self) -> None:
        result = TableFromDicts([])
        assert result is not None

    def test_th_has_muted_foreground(self) -> None:
        xml = to_xml(Th("Header"))
        assert "muted-foreground" in xml

    def test_td_has_padding(self) -> None:
        xml = to_xml(Td("cell"))
        assert "p-4" in xml

    def test_tbody_renders(self) -> None:
        assert Tbody() is not None

    def test_thead_renders(self) -> None:
        assert Thead() is not None

    def test_tr_has_border(self) -> None:
        xml = to_xml(Tr("cell"))
        assert "border-b" in xml

    def test_table_t_striped_non_empty(self) -> None:
        assert str(TableT.striped) != ""


# ============================================================================
# Form components
# ============================================================================


class TestLabel:
    def test_renders(self) -> None:
        xml = to_xml(Label("Name"))
        assert "Name" in xml

    def test_has_label_base_class(self) -> None:
        xml = to_xml(Label("Name"))
        assert "text-sm" in xml

    def test_fr_attribute(self) -> None:
        xml = to_xml(Label("Name", fr="name-input"))
        assert "name-input" in xml


class TestInput:
    def test_renders(self) -> None:
        assert Input() is not None

    def test_border_present(self) -> None:
        xml = to_xml(Input())
        assert "border" in xml

    def test_error_adds_destructive(self) -> None:
        xml = to_xml(Input(error_text="Required"))
        assert "destructive" in xml

    def test_help_text_rendered(self) -> None:
        xml = to_xml(Input(name="email", help_text="Your email"))
        assert "Your email" in xml

    def test_kwargs_passthrough(self) -> None:
        xml = to_xml(Input(type="email", name="email", placeholder="you@example.com"))
        assert "email" in xml

    def test_cls_merged(self) -> None:
        xml = to_xml(Input(cls="mt-2"))
        assert "mt-2" in xml


class TestTextArea:
    def test_renders(self) -> None:
        assert TextArea() is not None

    def test_has_min_height(self) -> None:
        xml = to_xml(TextArea())
        assert "min-h" in xml

    def test_error_text(self) -> None:
        xml = to_xml(TextArea(name="bio", error_text="Required"))
        assert "destructive" in xml


class TestSelect:
    def test_renders(self) -> None:
        from fasthtml.common import Option

        result = Select(Option("A", value="a"), Option("B", value="b"), name="choice")
        assert result is not None

    def test_native_select_element(self) -> None:
        xml = to_xml(Select(name="x"))
        assert "<select" in xml


class TestLabelInput:
    def test_renders(self) -> None:
        xml = to_xml(LabelInput("Name", name="name"))
        assert "Name" in xml

    def test_label_for_wired(self) -> None:
        xml = to_xml(LabelInput("Email", name="email"))
        assert "email" in xml

    def test_help_text(self) -> None:
        xml = to_xml(LabelInput("Age", name="age", help_text="In years"))
        assert "In years" in xml


class TestLabelTextArea:
    def test_renders(self) -> None:
        xml = to_xml(LabelTextArea("Bio", name="bio"))
        assert "Bio" in xml


class TestLabelSelect:
    def test_renders(self) -> None:
        from fasthtml.common import Option

        xml = to_xml(LabelSelect(Option("A"), label="Choice", name="choice"))
        assert "Choice" in xml


class TestLabelCheckbox:
    def test_renders(self) -> None:
        xml = to_xml(LabelCheckbox("Accept terms", name="accept"))
        assert "Accept terms" in xml

    def test_has_checkbox_type(self) -> None:
        xml = to_xml(LabelCheckbox("Accept", name="accept"))
        assert 'type="checkbox"' in xml


class TestSwitch:
    def test_renders(self) -> None:
        xml = to_xml(Switch(name="dark_mode"))
        assert 'type="checkbox"' in xml

    def test_role_switch(self) -> None:
        xml = to_xml(Switch(name="x"))
        assert 'role="switch"' in xml


class TestRadio:
    def test_renders(self) -> None:
        xml = to_xml(Radio(name="option", value="a"))
        assert 'type="radio"' in xml


class TestRange:
    def test_renders(self) -> None:
        xml = to_xml(Range(name="volume"))
        assert 'type="range"' in xml


# ============================================================================
# Layout components
# ============================================================================


class TestLayoutComponents:
    def test_div_fully_spaced(self) -> None:
        xml = to_xml(DivFullySpaced("a", "b"))
        assert "justify-between" in xml

    def test_div_centered(self) -> None:
        xml = to_xml(DivCentered("content"))
        assert "justify-center" in xml

    def test_center(self) -> None:
        xml = to_xml(Center("content"))
        assert "mx-auto" in xml
        assert "text-center" in xml

    def test_kwargs_passthrough_layout(self) -> None:
        xml = to_xml(DivFullySpaced("a", id="row-1"))
        assert 'id="row-1"' in xml


# ============================================================================
# TabContainer
# ============================================================================


class TestTabContainer:
    def test_renders_with_tabs(self) -> None:
        result = TabContainer(("Tab A", "Content A"), ("Tab B", "Content B"))
        assert result is not None

    def test_tab_labels_present(self) -> None:
        xml = to_xml(TabContainer(("Overview", "ov"), ("Details", "det")))
        assert "Overview" in xml
        assert "Details" in xml

    def test_tab_content_present(self) -> None:
        xml = to_xml(TabContainer(("T1", "content-one"), ("T2", "content-two")))
        assert "content-one" in xml
        assert "content-two" in xml

    def test_alpine_x_data_present(self) -> None:
        xml = to_xml(TabContainer(("A", "a")))
        assert "x-data" in xml
        assert "activeTab" in xml

    def test_active_tab_default_zero(self) -> None:
        xml = to_xml(TabContainer(("A", "a"), ("B", "b")))
        assert "activeTab: 0" in xml

    def test_active_tab_custom(self) -> None:
        xml = to_xml(TabContainer(("A", "a"), ("B", "b"), active_tab=1))
        assert "activeTab: 1" in xml

    def test_kwargs_passthrough(self) -> None:
        xml = to_xml(TabContainer(("A", "a"), id="tabs-1"))
        assert 'id="tabs-1"' in xml

    def test_cls_merged(self) -> None:
        xml = to_xml(TabContainer(("A", "a"), cls="my-tabs"))
        assert "my-tabs" in xml


# ============================================================================
# Accordion
# ============================================================================


class TestAccordion:
    def test_renders(self) -> None:
        assert Accordion() is not None

    def test_has_divide_y(self) -> None:
        xml = to_xml(Accordion())
        assert "divide-y" in xml

    def test_multiple_param_accepted(self) -> None:
        result = Accordion(multiple=True)
        assert result is not None


class TestAccordionItem:
    def test_renders(self) -> None:
        result = AccordionItem("Section title", "Body content")
        assert result is not None

    def test_title_present(self) -> None:
        xml = to_xml(AccordionItem("My Section", "body"))
        assert "My Section" in xml

    def test_body_present(self) -> None:
        xml = to_xml(AccordionItem("Title", "body content here"))
        assert "body content here" in xml

    def test_alpine_x_data(self) -> None:
        xml = to_xml(AccordionItem("T", "b"))
        assert "x-data" in xml
        assert "open" in xml

    def test_closed_by_default(self) -> None:
        xml = to_xml(AccordionItem("T", "b"))
        assert "open: false" in xml

    def test_open_param(self) -> None:
        xml = to_xml(AccordionItem("T", "b", open=True))
        assert "open: true" in xml

    def test_title_cls_applied(self) -> None:
        xml = to_xml(AccordionItem("T", "b", title_cls="text-lg font-semibold"))
        assert "text-lg" in xml
        assert "font-semibold" in xml

    def test_click_handler(self) -> None:
        xml = to_xml(AccordionItem("T", "b"))
        assert "@click" in xml

    def test_x_show_on_body(self) -> None:
        xml = to_xml(AccordionItem("T", "b"))
        assert "x-show" in xml

    def test_accordion_wraps_items(self) -> None:
        xml = to_xml(
            Accordion(
                AccordionItem("Section 1", "Content 1"),
                AccordionItem("Section 2", "Content 2"),
            )
        )
        assert "Section 1" in xml
        assert "Section 2" in xml
        assert "divide-y" in xml


# ============================================================================
# __init__ re-exports
# ============================================================================


class TestPackageExports:
    def test_all_components_importable(self) -> None:
        import ui.components as comp

        expected = [
            "Accordion",
            "AccordionItem",
            "Button",
            "ButtonT",
            "Card",
            "CardBody",
            "CardFooter",
            "CardHeader",
            "CardTitle",
            "Divider",
            "DividerLine",
            "DividerSplit",
            "DividerT",
            "Alert",
            "AlertT",
            "Loading",
            "Input",
            "Label",
            "LabelCheckbox",
            "LabelInput",
            "LabelSelect",
            "LabelTextArea",
            "Radio",
            "Range",
            "Select",
            "Switch",
            "TextArea",
            "Icon",
            "Center",
            "DivCentered",
            "DivFullySpaced",
            "TabContainer",
            "Table",
            "TableFromDicts",
            "TableFromLists",
            "TableT",
            "Tbody",
            "Td",
            "Th",
            "Thead",
            "Tr",
        ]
        for name in expected:
            assert hasattr(comp, name), f"ui.components missing export: {name}"
