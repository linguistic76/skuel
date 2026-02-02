"""
AccordionHierarchy - DaisyUI Collapse-Based Tree
=================================================

Features:
- Uses DaisyUI collapse components
- Better for nodes with descriptions/metadata
- Radio mode (single open) or checkbox mode (multiple open)
- HTMX lazy loading
- Drag-drop between accordion items

Usage:
    AccordionHierarchy(
        root_nodes=[
            {"uid": "goal1", "title": "Master Python", "description": "...", "has_children": True},
        ],
        entity_type="goal",
        mode="checkbox",  # or "radio"
        lazy_load=True,
    )

See: /docs/patterns/HIERARCHY_COMPONENTS_GUIDE.md
"""

from typing import Any

from fasthtml.common import Div, Input, Span


def AccordionHierarchy(
    root_nodes: list[dict[str, Any]],
    entity_type: str,
    children_endpoint: str,
    mode: str = "checkbox",  # "checkbox" or "radio"
    lazy_load: bool = True,
    show_metadata: bool = True,
    **kwargs: Any,
) -> Div:
    """
    Render DaisyUI collapse-based hierarchy.

    Args:
        root_nodes: List of root node dicts with {uid, title, description, has_children, child_count}
        entity_type: Entity type for icon selection
        children_endpoint: API endpoint template for lazy loading
        mode: "checkbox" (multiple open) or "radio" (single open)
        lazy_load: Enable HTMX lazy loading on expand
        show_metadata: Show description/metadata in title row

    Returns:
        Accordion hierarchy container
    """
    accordion_items = [
        _render_accordion_node(
            node=node,
            entity_type=entity_type,
            children_endpoint=children_endpoint,
            depth=0,
            mode=mode,
            lazy_load=lazy_load,
            show_metadata=show_metadata,
        )
        for node in root_nodes
    ]

    return Div(
        *accordion_items,
        cls="accordion-hierarchy space-y-2",
        **kwargs,
    )


def _render_accordion_node(
    node: dict[str, Any],
    entity_type: str,
    children_endpoint: str,
    depth: int,
    mode: str,
    lazy_load: bool,
    show_metadata: bool,
) -> Div:
    """
    Render single accordion item.

    Args:
        node: Node dict with uid, title, description, has_children, child_count
        entity_type: For icon selection
        children_endpoint: Endpoint template for lazy loading
        depth: Nesting depth (0 = root)
        mode: "checkbox" or "radio"
        lazy_load: Enable HTMX lazy loading
        show_metadata: Show description in title

    Returns:
        DaisyUI collapse structure:
        <div class="collapse collapse-arrow bg-base-100 border">
            <input type="checkbox" />
            <div class="collapse-title">
                <icon> Title <badge>
                <metadata if show_metadata>
            </div>
            <div class="collapse-content">
                <!-- Children (lazy or pre-rendered) -->
            </div>
        </div>
    """
    uid = node["uid"]
    title = node.get("title", "Untitled")
    description = node.get("description", "")
    has_children = node.get("has_children", False)
    child_count = node.get("child_count", 0)

    # Indent based on depth
    margin_left = depth * 16  # 16px per level

    # Collapse input (checkbox or radio)
    input_type = mode  # "checkbox" or "radio"
    input_name = f"accordion-{entity_type}" if mode == "radio" else None

    collapse_input_attrs = {"type": input_type}
    if input_name:
        collapse_input_attrs["name"] = input_name
    if lazy_load:
        collapse_input_attrs["x-on:change"] = f"onExpand('{uid}')"

    collapse_input = Input(**collapse_input_attrs)

    # Title row
    entity_icons = {
        "goal": "🎯",
        "habit": "🔄",
        "event": "📅",
        "choice": "🤔",
        "principle": "⚖️",
        "lp": "🛤️",
    }
    icon = Span(entity_icons.get(entity_type, "📄"), cls="text-lg mr-2")

    badge_element = None
    if has_children and child_count > 0:
        badge_element = Span(str(child_count), cls="badge badge-sm badge-ghost ml-2")

    title_elements = [icon, Span(title, cls="font-medium")]
    if badge_element:
        title_elements.append(badge_element)

    title_row = Div(*title_elements, cls="flex items-center")

    # Metadata (if enabled)
    metadata_row = None
    if show_metadata and description:
        metadata_row = Div(
            Span(description, cls="text-sm text-base-content/70 line-clamp-2"),
            cls="mt-1",
        )

    collapse_title_elements = [title_row]
    if metadata_row:
        collapse_title_elements.append(metadata_row)

    collapse_title = Div(*collapse_title_elements, cls="collapse-title")

    # Children content (lazy or static)
    if lazy_load and has_children:
        children_content = Div(
            **{
                "hx-get": children_endpoint.replace("{uid}", uid),
                "hx-trigger": f"expand-{uid} from:body",
                "hx-swap": "innerHTML",
            },
            cls="space-y-2",
        )
    else:
        children_content = Div(cls="space-y-2")  # Pre-render if needed

    collapse_content = Div(children_content, cls="collapse-content px-2")

    return Div(
        collapse_input,
        collapse_title,
        collapse_content,
        cls="collapse collapse-arrow bg-base-100 border border-base-300",
        style=f"margin-left: {margin_left}px",
    )


def AccordionNodeList(
    nodes: list[dict[str, Any]],
    entity_type: str,
    children_endpoint: str,
    parent_depth: int = 0,
    mode: str = "checkbox",
    lazy_load: bool = True,
    show_metadata: bool = True,
    **kwargs: Any,
) -> Div:
    """
    Render list of accordion nodes (used by HTMX lazy loading).

    Args:
        nodes: List of node dicts
        entity_type: Entity type for icons
        children_endpoint: Endpoint template
        parent_depth: Depth of parent (children are +1)
        mode: "checkbox" or "radio"
        lazy_load: Enable lazy loading
        show_metadata: Show descriptions

    Returns:
        Container with multiple accordion nodes
    """
    child_depth = parent_depth + 1

    if not nodes:
        return Div(
            Span("No items", cls="text-base-content/60 text-sm italic text-center py-4"),
            cls="block",
        )

    node_elements = [
        _render_accordion_node(
            node=node,
            entity_type=entity_type,
            children_endpoint=children_endpoint,
            depth=child_depth,
            mode=mode,
            lazy_load=lazy_load,
            show_metadata=show_metadata,
        )
        for node in nodes
    ]

    return Div(*node_elements, cls="space-y-2", **kwargs)
