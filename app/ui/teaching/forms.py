"""
Teaching UI Forms
=================

Exercise create/edit form component.
"""

from typing import Any

from fasthtml.common import Div, Form, Label, Option, P

from ui.buttons import Button, ButtonT
from ui.forms import Input, Select, Textarea


def render_exercise_form(groups: list[dict[str, Any]], exercise: Any = None) -> Div:
    """Render create/edit exercise form with Alpine.js scope toggle."""
    is_edit = exercise is not None
    uid = getattr(exercise, "uid", "") if exercise else ""
    post_url = f"/api/teaching/exercises/{uid}" if is_edit else "/api/teaching/exercises"

    name_val = getattr(exercise, "title", "") or ""
    instructions_val = getattr(exercise, "instructions", "") or ""
    model_val = getattr(exercise, "model", "claude-sonnet-4-6") or "claude-sonnet-4-6"

    scope_raw = getattr(exercise, "scope", None)
    _no_value = object()
    _scope_value = getattr(scope_raw, "value", _no_value) if scope_raw is not None else _no_value
    scope_str = str(_scope_value) if _scope_value is not _no_value else "personal"
    group_uid_val = getattr(exercise, "group_uid", "") or ""

    due_date_raw = getattr(exercise, "due_date", None)
    due_date_val = str(due_date_raw) if due_date_raw else ""

    context_notes_raw = getattr(exercise, "context_notes", ()) or ()
    context_notes_str = "\n".join(context_notes_raw)
    notes_open = "true" if context_notes_str else "false"

    group_options: list[Any] = [
        Option("-- Select group --", value="", disabled=True, selected=not group_uid_val)
    ]
    for group in groups:
        g_name = group.get("name") or group.get("uid", "Unknown")
        g_uid = group.get("uid", "")
        group_options.append(Option(g_name, value=g_uid, selected=(g_uid == group_uid_val)))

    model_choices = [
        ("claude-sonnet-4-6", "Claude Sonnet 4.6 (Recommended)"),
        ("claude-opus-4-6", "Claude Opus 4.6 (Most Capable)"),
        ("claude-haiku-4-5-20251001", "Claude Haiku 4.5 (Fastest)"),
        ("gpt-4o", "GPT-4o"),
        ("gpt-4o-mini", "GPT-4o Mini (Cheaper)"),
    ]
    model_options: list[Any] = [
        Option(label, value=val, selected=(val == model_val)) for val, label in model_choices
    ]

    after_request_js = (
        "if(event.detail.successful){"
        "window.location='/teaching/exercises';"
        "}else{"
        "try{"
        "var d=JSON.parse(event.detail.xhr.responseText);"
        "document.getElementById('form-result').innerHTML="
        "'<div class=\"alert alert-error mt-2\">'+(d.message||'Error saving exercise')+'</div>';"
        "}catch(e){}"
        "}"
    )

    return Div(
        Form(
            Div(
                Label("Name", cls="label-text font-medium"),
                Input(
                    type="text",
                    name="name",
                    value=name_val,
                    placeholder="e.g., Daily Reflection, Principle Mining",
                    required=True,
                ),
                cls="form-control mb-4",
            ),
            Div(
                Label("Instructions (visible to students & LLM)", cls="label-text font-medium"),
                Textarea(
                    instructions_val,
                    name="instructions",
                    placeholder="Write the instructions for students and the LLM...",
                    cls="h-40",
                    required=True,
                ),
                cls="form-control mb-4",
            ),
            Div(
                Label("LLM Model", cls="label-text font-medium"),
                Select(*model_options, name="model"),
                cls="form-control mb-4",
            ),
            Div(
                Label("Scope", cls="label-text font-medium"),
                Div(
                    Label(
                        Input(
                            type="radio",
                            name="scope",
                            value="personal",
                            cls="radio radio-sm mr-2",
                            **{"x-model": "scope"},
                        ),
                        "Personal",
                        cls="label cursor-pointer gap-2 justify-start",
                    ),
                    Label(
                        Input(
                            type="radio",
                            name="scope",
                            value="assigned",
                            cls="radio radio-sm mr-2",
                            **{"x-model": "scope"},
                        ),
                        "Assigned to group",
                        cls="label cursor-pointer gap-2 justify-start",
                    ),
                    cls="flex gap-6",
                ),
                cls="form-control mb-4",
            ),
            Div(
                Div(
                    Label("Group", cls="label-text font-medium"),
                    Select(*group_options, name="group_uid"),
                    cls="form-control mb-3",
                ),
                Div(
                    Label("Due Date", cls="label-text font-medium"),
                    Input(
                        type="date",
                        name="due_date",
                        value=due_date_val,
                    ),
                    cls="form-control mb-3",
                ),
                **{"x-show": "scope === 'assigned'"},
            ),
            Div(
                Div(
                    P(
                        "Context Notes (optional)",
                        cls="font-medium text-sm mb-1 cursor-pointer",
                        **{
                            "x-on:click": "notesOpen = !notesOpen",
                            "x-text": "notesOpen ? 'Context Notes (optional)' : 'Context Notes (optional)'",
                        },
                    ),
                ),
                Div(
                    P(
                        "One note per line — reference materials the LLM should consider.",
                        cls="text-xs text-muted-foreground mb-1",
                    ),
                    Textarea(
                        context_notes_str,
                        name="context_notes",
                        placeholder="Focus on self-awareness\nBe gentle and curious",
                        cls="h-24",
                    ),
                    **{"x-show": "notesOpen"},
                ),
                cls="form-control mb-4",
            ),
            Div(
                Button(
                    "Save Exercise" if is_edit else "Create Exercise",
                    variant=ButtonT.primary,
                    type="submit",
                ),
                cls="mt-2",
            ),
            Div(id="form-result", cls="mt-3"),
            **{
                "hx-post": post_url,
                "hx-target": "#form-result",
                "hx-swap": "innerHTML",
                "hx-on::after-request": after_request_js,
            },
        ),
        **{"x-data": f"{{ scope: '{scope_str}', notesOpen: {notes_open} }}"},
    )
