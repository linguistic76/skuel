"""HXML element builders — composable XML generation for Hyperview.

Mirrors FastHTML's FT pattern: functions that return markup strings.
Each function produces valid HXML that a Hyperview client can render.

HXML key differences from HTML:
- All text must be wrapped in <text> elements (no bare text nodes)
- <view> instead of <div> for containers
- Styles don't cascade — applied explicitly via style attribute
- Navigation via <behavior> elements, not <a> tags
- Screens are top-level containers (like HTML pages)

See: https://hyperview.org/
See: /docs/decisions/ADR-039-hyperview-mobile-strategy.md
"""

from xml.sax.saxutils import escape


def _attrs_str(**attrs: str) -> str:
    """Build XML attribute string from keyword arguments."""
    parts = []
    for key, value in attrs.items():
        if value:
            safe_key = key.replace("_", "-")
            parts.append(f' {safe_key}="{escape(str(value))}"')
    return "".join(parts)


def Doc(*children: str, xmlns: str = "https://hyperview.org/hyperview") -> str:  # noqa: N802
    """Root HXML document element.

    Every Hyperview response must be wrapped in a <doc> element.
    Contains one or more <screen> elements.
    """
    inner = "".join(children)
    return f'<doc xmlns="{xmlns}">{inner}</doc>'


def Screen(*children: str, id: str = "") -> str:  # noqa: N802
    """Screen element — equivalent to an HTML page.

    Each screen represents a full-screen view in the mobile app.
    """
    id_attr = f' id="{escape(id)}"' if id else ""
    inner = "".join(children)
    return f"<screen{id_attr}>{inner}</screen>"


def View(*children: str, style: str = "", **attrs: str) -> str:  # noqa: N802
    """View container — equivalent to HTML div.

    Primary layout container in HXML. Use for grouping and positioning.
    """
    style_attr = f' style="{escape(style)}"' if style else ""
    extra = _attrs_str(**attrs)
    inner = "".join(children)
    return f"<view{style_attr}{extra}>{inner}</view>"


def Text(content: str, style: str = "", **attrs: str) -> str:  # noqa: N802
    """Text element — all visible text must be wrapped in <text>.

    Unlike HTML where text can appear anywhere, HXML requires explicit
    text elements. This maps to React Native's <Text> component.
    """
    style_attr = f' style="{escape(style)}"' if style else ""
    extra = _attrs_str(**attrs)
    return f"<text{style_attr}{extra}>{escape(content)}</text>"


def Style(id: str, **props: str) -> str:  # noqa: N802
    """Style definition — no cascade, explicit application only.

    HXML styles are referenced by ID. They don't cascade to children
    like CSS. Each element must explicitly reference its style.
    """
    prop_elements = []
    for key, value in props.items():
        safe_key = key.replace("_", "-")
        prop_elements.append(f' {safe_key}="{escape(str(value))}"')
    props_str = "".join(prop_elements)
    return f'<style id="{escape(id)}"{props_str} />'


def Behavior(  # noqa: N802
    trigger: str = "press",
    action: str = "push",
    href: str = "",
    **attrs: str,
) -> str:
    """Interaction behavior — navigation, updates, etc.

    Defines what happens when a user interacts with an element.

    Triggers: press, longPress, load, visible, refresh
    Actions: push (stack), new (modal), back, close, replace, replace-inner
    """
    parts = [f'<behavior trigger="{escape(trigger)}" action="{escape(action)}"']
    if href:
        parts.append(f' href="{escape(href)}"')
    extra = _attrs_str(**attrs)
    parts.append(f"{extra} />")
    return "".join(parts)
