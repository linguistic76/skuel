"""
EntityPicker — Searchable dropdown for cross-domain UID fields
==============================================================

Renders a hidden input + visible search box + HTMX-driven dropdown for picking
a single entity (Goal, Habit, Task, Event, Choice, Principle) by title.
Designed for use as a ``custom_widgets`` entry in
:class:`ui.patterns.form_generator.FormGenerator`.

Pattern: the hidden input carries the picked UID (the form-submitted value);
the visible input is for human search and is **not** named, so it never
appears in the form POST body. Selection is driven by the ``entityPicker``
Alpine component in ``static/js/skuel.js``, which copies ``data-uid`` /
``data-title`` from the clicked dropdown item into the hidden + visible inputs.

The dropdown is populated by HTMX hits to ``GET /api/picker/search`` defined
in ``adapters/inbound/picker_routes.py``.

See: /home/mike/.claude/plans/entity_picker_component_plan.md
"""

from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import urlencode

from fasthtml.common import Button, Div, Ul
from fasthtml.common import Input as FTInput

from ui.forms import Input

__all__ = ["EntityPicker"]


_TARGET_TYPE_LABELS = {
    "goal": "goal",
    "habit": "habit",
    "task": "task",
    "event": "event",
    "choice": "choice",
    "principle": "principle",
}


def EntityPicker(
    name: str,
    target_type: str,
    *,
    value: str | None = None,
    display: str | None = None,
    exclude_uid: str | None = None,
    exclude_descendants_of: str | None = None,
    required: bool = False,
) -> Any:
    """Render a searchable single-entity picker for a cross-domain UID field.

    Args:
        name: The form-field name. The hidden input uses this as ``name``,
            so this is what the parent form receives on POST (e.g.
            ``"fulfills_goal_uid"``).
        target_type: One of ``"goal"``, ``"habit"``, ``"task"``, ``"event"``,
            ``"choice"``, ``"principle"``. Determines which entity collection
            the search endpoint queries.
        value: Pre-fill UID for edit mode. Becomes the hidden input's value.
        display: Pre-fill human-readable title shown in the visible input
            for edit mode. The caller is responsible for resolving
            ``value`` → title before render.
        exclude_uid: A single UID to filter out of search results. Used for
            self-referential pickers in edit mode (a Task's ``parent_uid``
            cannot point to itself).
        exclude_descendants_of: A UID whose descendants are filtered out of
            search results. Used to prevent cycles in self-referential
            hierarchies (a Task's ``parent_uid`` cannot point to one of
            its own subtasks).
        required: Whether the underlying form field is required. The hidden
            input gets ``required`` so HTML5 validation fires if no entity
            is picked.

    Returns:
        A FastTags ``Div`` element ready for use as a ``FormGenerator``
        ``custom_widgets`` value.
    """
    if target_type not in _TARGET_TYPE_LABELS:
        raise ValueError(
            f"EntityPicker: unsupported target_type {target_type!r}. "
            f"Expected one of: {sorted(_TARGET_TYPE_LABELS)}"
        )

    picker_id = f"picker-{name}-{secrets.token_hex(4)}"
    results_id = f"{picker_id}-results"

    qs: dict[str, str] = {"type": target_type}
    if exclude_uid:
        qs["exclude_uid"] = exclude_uid
    if exclude_descendants_of:
        qs["exclude_descendants_of"] = exclude_descendants_of
    base_url = f"/api/picker/search?{urlencode(qs)}"

    placeholder = f"Search for a {_TARGET_TYPE_LABELS[target_type]}..."

    hidden_attrs: dict[str, Any] = {
        "type": "hidden",
        "name": name,
        "value": value or "",
        "x-ref": "hidden",
    }
    if required:
        hidden_attrs["required"] = True

    search_input = Input(
        type="text",
        placeholder=placeholder,
        value=display or "",
        autocomplete="off",
        full_width=True,
        hx_get=base_url,
        hx_trigger="focus once, keyup changed delay:200ms",
        hx_target=f"#{results_id}",
        hx_vals="js:{q: this.value}",
        **{
            "x-ref": "search",
            "x-on:focus": "onFocus()",
            "x-on:keydown": "onKeydown($event)",
            "x-on:input": "onInput()",
            "aria-autocomplete": "list",
            "aria-controls": results_id,
            "aria-expanded": "false",
            ":aria-expanded": "open ? 'true' : 'false'",
            "role": "combobox",
        },
    )

    results_panel = Ul(
        id=results_id,
        role="listbox",
        cls=(
            "absolute z-20 mt-1 w-full bg-popover text-popover-foreground "
            "border border-border rounded-md shadow-lg max-h-60 overflow-auto"
        ),
        **{
            "x-show": "open",
            "x-on:click": "select($event)",
            "x-cloak": "",
            "style": "display:none;",  # initial state — Alpine flips via x-show
        },
    )

    clear_button = Button(
        "×",
        type="button",
        tabindex="-1",
        **{
            "aria-label": f"Clear {_TARGET_TYPE_LABELS[target_type]} selection",
            "x-show": "hasValue()",
            "x-on:click": "clear()",
            "x-cloak": "",
            "style": "display:none;",
            "cls": (
                "absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground "
                "hover:text-foreground text-lg leading-none px-1 cursor-pointer"
            ),
        },
    )

    return Div(
        FTInput(**hidden_attrs),
        search_input,
        clear_button,
        results_panel,
        cls="relative w-full",
        **{
            "x-data": "entityPicker",
            "x-on:click.outside": "open = false",
            "x-on:keydown.escape": "open = false",
        },
    )
