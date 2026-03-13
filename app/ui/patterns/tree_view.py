"""
TreeView - Expandable Hierarchy Component
==========================================

Features:
- Indented multi-level tree visualization
- HTMX lazy loading on expand
- Drag-and-drop reordering
- Inline title editing
- Keyboard navigation (↑↓←→ keys)
- Multi-select with checkboxes
- Customizable icons per entity type

Usage:
    TreeView(
        root_uid="goal_abc123",
        entity_type="goal",
        children_endpoint="/api/goals/{uid}/children",
        move_endpoint="/api/goals/{uid}/move",
        show_checkboxes=True,
        keyboard_nav=True,
    )

See: /docs/patterns/HIERARCHY_COMPONENTS_GUIDE.md
"""

from typing import Any

from fasthtml.common import Button, Div, Input, Span


def TreeView(
    root_uid: str,
    entity_type: str,
    children_endpoint: str,
    move_endpoint: str | None = None,
    show_checkboxes: bool = False,
    keyboard_nav: bool = True,
    draggable: bool = True,
    **kwargs: Any,
) -> Div:
    """
    Render root of tree view.

    Args:
        root_uid: Root node UID
        entity_type: "goal" | "habit" | "event" | "choice" | "principle" | "lp"
        children_endpoint: API endpoint template (use {uid} placeholder)
        move_endpoint: Optional drag-drop move endpoint
        show_checkboxes: Enable multi-select
        keyboard_nav: Enable arrow key navigation
        draggable: Enable drag-and-drop

    Returns:
        Tree view container with Alpine.js initialization
    """
    alpine_config = {
        "entityType": entity_type,
        "childrenEndpoint": children_endpoint,
        "moveEndpoint": move_endpoint or "",
        "showCheckboxes": show_checkboxes,
        "keyboardNav": keyboard_nav,
        "draggable": draggable,
    }

    # Convert Python dict to JavaScript object literal
    config_str = (
        str(alpine_config).replace("True", "true").replace("False", "false").replace("'", '"')
    )

    return Div(
        # Root node container
        Div(
            # Initial loading state - will be replaced by HTMX
            # Note: parent_depth=-1 so root nodes render at depth 0
            Div(
                Span("Loading...", cls="text-muted-foreground text-sm italic"),
                cls="px-2 py-1",
                **{
                    "hx-get": f"{children_endpoint.replace('{uid}', root_uid)}?parent_depth=-1",
                    "hx-trigger": "load",
                    "hx-swap": "outerHTML",
                },
            ),
            id=f"tree-root-{root_uid}",
            cls="tree-view",
        ),
        cls="tree-container focus:outline-none",
        tabindex="0",  # Make focusable for keyboard nav
        **{
            "x-data": f"hierarchyTree({config_str})",
            "x-on:keydown": "handleKeydown" if keyboard_nav else None,
        },
        **kwargs,
    )


def _render_tree_node(
    uid: str,
    entity_type: str,
    title: str,
    depth: int,
    has_children: bool,
    children_endpoint: str,
    is_expanded: bool = False,
    show_checkbox: bool = False,
    draggable: bool = True,
) -> Div:
    """
    Render a single tree node with all features.

    Args:
        uid: Node unique identifier
        entity_type: Entity type for icon selection
        title: Node title text
        depth: Nesting depth (0 = root)
        has_children: Whether node has children to load
        children_endpoint: API endpoint for lazy loading children
        is_expanded: Initial expanded state
        show_checkbox: Show multi-select checkbox
        draggable: Enable drag-and-drop

    Returns:
        HTML structure:
        <div class="tree-node" data-uid="{uid}" data-depth="{depth}">
            <div class="node-content">
                [checkbox] [expand-icon] [entity-icon] [title] [actions]
            </div>
            <div class="node-children" x-show="isExpanded(uid)">
                <!-- Children loaded via HTMX -->
            </div>
        </div>
    """
    indent = depth * 24  # 24px per level

    # Expand/collapse icon (only if has children)
    expand_icon_element = None
    if has_children:
        expand_icon_element = Button(
            Span("▶", **{"x-show": f"!isExpanded('{uid}')", "x-cloak": True}),  # Right chevron
            Span("▼", **{"x-show": f"isExpanded('{uid}')", "x-cloak": True}),  # Down chevron
            **{
                "x-on:click.stop": f"toggleExpand('{uid}')",
            },
            cls="btn btn-ghost btn-xs p-0 min-h-0 h-6 w-6 text-muted-foreground hover:text-foreground",
            type="button",
        )
    else:
        # Spacer for alignment
        expand_icon_element = Span(cls="inline-block w-6")

    # Entity type icon
    entity_icons = {
        "goal": "🎯",
        "habit": "🔄",
        "event": "📅",
        "choice": "🤔",
        "principle": "⚖️",
        "lp": "🛤️",
    }
    entity_icon = Span(entity_icons.get(entity_type, "📄"), cls="text-lg")

    # Checkbox (if enabled)
    checkbox_element = None
    if show_checkbox:
        checkbox_element = Input(
            type="checkbox",
            **{
                "x-model": "selected",
                ":value": f"'{uid}'",
            },
            cls="checkbox checkbox-sm mr-2",
        )

    # Title (inline editable)
    title_element = Span(
        title,
        **{
            "x-on:dblclick": f"startEdit('{uid}')",
        },
        cls="flex-grow text-sm cursor-text hover:bg-muted px-1 rounded node-title",
        **{"data-uid": uid},
    )

    # Actions menu (edit, delete, add child)
    actions = Div(
        Button("⋮", cls="btn btn-ghost btn-xs", type="button"),
        cls="dropdown dropdown-end opacity-0 group-hover:opacity-100",
    )

    # Drag-and-drop attributes
    drag_attrs = {}
    if draggable:
        drag_attrs = {
            "draggable": "true",
            "x-on:dragstart": f"handleDragStart($event, '{uid}')",
            "x-on:dragover.prevent": "handleDragOver",
            "x-on:drop": f"handleDrop($event, '{uid}')",
        }

    # Build content row elements
    content_elements = [expand_icon_element, entity_icon, title_element, actions]
    if checkbox_element:
        content_elements.insert(0, checkbox_element)

    # Node content row
    node_content = Div(
        *content_elements,
        cls="flex items-center gap-2 py-1 px-2 rounded hover:bg-muted group",
        style=f"padding-left: {indent}px",
        **drag_attrs,
    )

    # Children container (lazy loaded via HTMX)
    children_container = Div(
        **{
            "x-show": f"isExpanded('{uid}')",
            "x-cloak": True,
            "hx-get": f"{children_endpoint.replace('{uid}', uid)}?parent_depth={depth}",
            "hx-trigger": f"expand-{uid} from:body",  # Triggered by Alpine
            "hx-target": "this",
            "hx-swap": "innerHTML",
        },
        cls="node-children",
        id=f"children-{uid}",
    )

    return Div(
        node_content,
        children_container,
        cls="tree-node",
        **{
            "data-uid": uid,
            "data-depth": str(depth),
            "data-has-children": str(has_children).lower(),
        },
    )


def TreeNodeList(
    nodes: list[dict[str, Any]],
    entity_type: str,
    children_endpoint: str,
    parent_depth: int = 0,
    show_checkboxes: bool = False,
    draggable: bool = True,
    **kwargs: Any,
) -> Div:
    """
    Render a list of tree nodes (used by HTMX lazy loading).

    Args:
        nodes: List of dicts with {uid, title, has_children, ...}
        entity_type: Entity type for icons
        children_endpoint: Endpoint template for child loading
        parent_depth: Depth of parent (children are +1)
        show_checkboxes: Enable multi-select checkboxes
        draggable: Enable drag-and-drop

    Returns:
        Container with multiple tree nodes
    """
    child_depth = parent_depth + 1

    if not nodes:
        return Div(
            Span("No items", cls="text-muted-foreground text-sm italic"),
            cls="px-2 py-1",
            style=f"padding-left: {(child_depth * 24) + 8}px",
        )

    node_elements = [
        _render_tree_node(
            uid=node["uid"],
            entity_type=entity_type,
            title=node.get("title", "Untitled"),
            depth=child_depth,
            has_children=node.get("has_children", False),
            children_endpoint=children_endpoint,
            show_checkbox=show_checkboxes,
            draggable=draggable,
        )
        for node in nodes
    ]

    return Div(*node_elements, **kwargs)
