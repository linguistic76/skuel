"""
Submission Sharing UI Components
================================

Visibility controls, share modal, and shared users list.
"""

from typing import Any

from fasthtml.common import (
    H3,
    H4,
    Div,
    Form,
    Option,
    P,
)

from ui.buttons import Button
from ui.feedback import Badge, BadgeT
from ui.forms import Input, Label, Select
from ui.cards import Card


def render_visibility_dropdown(submission: Any) -> Any:
    """Render visibility level dropdown. Only shows for completed reports."""
    current_visibility = getattr(submission, "visibility", "private")
    is_shareable = getattr(submission, "status", "") == "completed"

    if not is_shareable:
        return Div(
            Badge("Private", variant=BadgeT.ghost),
            P(
                "Only completed reports can be shared",
                cls="text-xs text-muted-foreground mt-1 mb-0",
            ),
            cls="mb-4",
        )

    visibility_options = [
        ("private", "Private", "Only you can see"),
        ("shared", "Shared", "Specific users only"),
        ("public", "Public", "Portfolio showcase"),
    ]

    return Div(
        Label("Visibility:", cls="label label-text font-bold"),
        Select(
            *[
                Option(
                    label,
                    value=val,
                    selected=(val == current_visibility),
                )
                for val, label, _desc in visibility_options
            ],
            name="visibility",
            hx_post="/api/submissions/set-visibility",
            hx_trigger="change",
            hx_vals=f"js:{{report_uid: '{submission.uid}', visibility: event.target.value}}",
            hx_target="#visibility-status",
            hx_swap="innerHTML",
        ),
        Div(
            P(
                next(
                    (desc for val, _lbl, desc in visibility_options if val == current_visibility),
                    "",
                ),
                cls="text-xs text-muted-foreground mb-0",
            ),
            id="visibility-status",
            cls="mt-1",
        ),
        cls="form-control mb-4",
    )


def render_share_modal(report_uid: str) -> Any:
    """Render modal for sharing submission with a user."""
    return Div(
        Div(
            Div(
                Div(
                    Form(
                        Button(
                            "\u2715",
                            cls="btn btn-sm btn-circle btn-ghost absolute right-2 top-2",
                            **{"@click": "shareModal = false"},
                        ),
                        method="dialog",
                    ),
                    H3("Share Report", cls="font-bold text-lg mb-4"),
                    Form(
                        Div(
                            Label("User UID:", cls="label label-text"),
                            Input(
                                type="text",
                                name="recipient_uid",
                                placeholder="user_teacher",
                                required=True,
                            ),
                            cls="form-control mb-3",
                        ),
                        Div(
                            Label("Role:", cls="label label-text"),
                            Select(
                                Option("Viewer", value="viewer", selected=True),
                                Option("Teacher", value="teacher"),
                                Option("Peer", value="peer"),
                                Option("Mentor", value="mentor"),
                                name="role",
                            ),
                            cls="form-control mb-4",
                        ),
                        Div(
                            Button(
                                "Cancel",
                                type="button",
                                cls="btn btn-ghost",
                                **{"@click": "shareModal = false"},
                            ),
                            Button(
                                "Share",
                                type="submit",
                                cls="btn btn-primary",
                            ),
                            cls="flex gap-2 justify-end",
                        ),
                        hx_post="/api/submissions/share",
                        hx_vals=f"js:{{report_uid: '{report_uid}', recipient_uid: document.querySelector('input[name=recipient_uid]').value, role: document.querySelector('select[name=role]').value}}",
                        hx_target="#shared-users-list",
                        hx_swap="innerHTML",
                        **{
                            "@submit.prevent": "$el.dispatchEvent(new Event('htmx:trigger')); shareModal = false"
                        },
                    ),
                    cls="modal-box",
                ),
                cls="modal-backdrop",
                **{"@click": "shareModal = false"},
            ),
            cls="modal",
            **{"x-show": "shareModal", "x-cloak": ""},
        ),
        Button(
            "Share with User",
            cls="btn btn-primary btn-sm",
            **{"@click": "shareModal = true"},
        ),
    )


def render_shared_users_list(report_uid: str) -> Any:
    """Render list of users submission is shared with (loaded dynamically via HTMX)."""
    return Div(
        H4("Shared With", cls="font-bold mb-2"),
        Div(
            P("Loading shared users...", cls="text-muted-foreground text-sm"),
            id="shared-users-list",
            hx_get=f"/submissions/{report_uid}/shared-users",
            hx_trigger="load",
            hx_swap="innerHTML",
        ),
        cls="mt-4",
    )


def render_sharing_section(submission: Any) -> Any:
    """Render complete sharing section for submission detail page."""
    return Card(
        H4("Sharing & Visibility", cls="font-bold text-lg mb-4"),
        Div(
            render_visibility_dropdown(submission),
            Div(
                render_share_modal(submission.uid),
                cls="mb-4",
            ),
            render_shared_users_list(submission.uid),
            cls="space-y-2",
        ),
        id="sharing-section",
        cls="bg-muted p-4 rounded-lg mt-6",
        **{
            "x-data": "{ shareModal: false }",
        },
    )
