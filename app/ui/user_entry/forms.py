"""
The Submit page's form (Submit & Share arc PR 7, ADR-054)
==========================================================

The upload form at ``/submissions/submit`` asks two questions:

- **Ask for feedback?** Teacher (the default — works with or without an
  exercise: ``teachers`` files the request with every class the student
  studies in, or one class when they pick it, ``teacher:<group_uid>``), AI
  (only with an exercise, because the reviewer grades against it — after
  submitting, the entry page's "Request AI feedback" button is the next step;
  submit never summons the reviewer), or No.
- **Share with** (optional, collapsed): the student's groups and co-members
  as ``group:<uid>`` / ``user:<username>`` checkboxes — the same rows as the
  Share panel — plus the Portfolio row ("Coming soon" until the public reader
  exists).

The title is the student's (the PR 7 ruling): the Title field is optional,
and a turn-in left untitled is titled "<exercise> v<N>" by the writer; any
other untitled upload takes its file name. Pipeline and the feedback half of
the audience are derived client-side (the ``submit`` Alpine component,
``static/js/skuel.js``) and posted as hidden fields; the share checkboxes add
their values to the same repeated ``audience`` field.

Submits via HTMX POST to ``/api/user-entries/upload`` (multipart/form-data).
CSRF is injected automatically by the global ``htmx:configRequest`` handler in
``skuel.js``. The success toast is driven by Alpine's ``sent`` state, triggered
by ``htmx:afterRequest`` on the form container.

See: /docs/decisions/ADR-088-submit-and-share.md
See: /docs/decisions/ADR-054-user-entry-unified-submissions.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlencode

from fasthtml.common import Button, Div, Form, Input, Option, P, Select, Span

from core.models.user_entry.audience import GROUP_PREFIX, PUBLIC, USER_PREFIX
from ui.components import Icon
from ui.gradebook.share_panel import AudienceCheckbox
from ui.primitives import (
    SelectableOptionRow,
    SelectedFileCard,
    UploadDropzone,
    section_label,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fasthtml.common import FT

    from core.ports.query_types import ShareTargets

SUBMIT_PAGE_PATH = "/submissions/submit"
"""The one Submit page — every "Submit →" link in the app points here."""

FEEDBACK_TEACHER = "teacher"
FEEDBACK_AI = "ai"
FEEDBACK_NONE = "none"
"""The three answers to "Ask for feedback?" — the ``submit`` component's ``feedback`` state."""

ALL_MY_TEACHERS = ""
"""The class select's value for ``teachers`` (every class the student studies in)."""

_NOBODY_TO_SHARE_WITH = (
    "No groups or classmates to share with yet — join a group, or ask a teacher to add you."
)


def submit_page_href(exercise_uid: str | None = None, *, from_ps: str | None = None) -> str:
    """The Submit page URL, preselecting ``exercise_uid`` (and carrying ``from_ps``) when given."""
    params: dict[str, str] = {}
    if exercise_uid:
        params["exercise_uid"] = exercise_uid
    if from_ps:
        params["from_ps"] = from_ps
    return f"{SUBMIT_PAGE_PATH}?{urlencode(params)}" if params else SUBMIT_PAGE_PATH


def _feedback_option(
    key: str,
    *,
    icon: str,
    tile_bg: str,
    icon_cls: str,
    title: str,
    desc: str,
    disabled: bool = False,
) -> FT:
    """One answer to "Ask for feedback?" as a selectable row bound to ``feedback``."""
    return SelectableOptionRow(
        icon=icon,
        tile_bg=tile_bg,
        icon_cls=icon_cls,
        title=title,
        subtitle=desc,
        selected_expr=f"feedback === '{key}'",
        click_handler=f"selectFeedback('{key}')",
        disabled=disabled,
        title_extra=(
            Span(
                "Needs an exercise",
                cls=(
                    "text-10 font-bold uppercase tracking-wider "
                    "text-amber-800 bg-amber-100 px-[7px] py-[2px] rounded-full"
                ),
            )
            if disabled
            else None
        ),
    )


def _feedback_question(*, has_exercise: bool, teacher_groups: Sequence[tuple[str, str]]) -> FT:
    """ "Ask for feedback?" — Teacher / AI / No, plus the class select when it is a choice."""
    options = Div(
        _feedback_option(
            FEEDBACK_TEACHER,
            icon="user-round",
            tile_bg="bg-blue-50",
            icon_cls="text-blue-600",
            title="Teacher",
            desc="Your teacher reads it and replies in your GradeBook.",
        ),
        _feedback_option(
            FEEDBACK_AI,
            icon="sparkles",
            tile_bg="bg-violet-50",
            icon_cls="text-violet-700",
            title="AI",
            desc=(
                "Graded against the exercise. After submitting, ask for it with "
                "“Request AI feedback” on the entry's page."
                if has_exercise
                else "Graded against an exercise — open one and submit from there."
            ),
            disabled=not has_exercise,
        ),
        _feedback_option(
            FEEDBACK_NONE,
            icon="bookmark",
            tile_bg="bg-slate-100",
            icon_cls="text-slate-500",
            title="No",
            desc="Just keep it. You can still share it below.",
        ),
        cls="border border-border rounded-[11px] bg-card p-[6px] flex flex-col gap-[3px]",
    )

    # Which class? Only a choice without an exercise (an exercise names its
    # own classes) and only when the student studies in more than one.
    class_select: FT | None = None
    if not has_exercise and len(teacher_groups) > 1:
        class_select = Div(
            Span("Which class?", cls="block text-xs font-medium text-muted-foreground mb-1"),
            Select(
                Option("All my teachers", value=ALL_MY_TEACHERS),
                *[Option(name, value=uid) for uid, name in teacher_groups],
                name="teacher_group",
                cls=(
                    "w-full px-3 py-2 border border-border rounded-[9px] bg-card text-sm "
                    "text-foreground"
                ),
                **{"x-model": "teacherGroup"},
            ),
            cls="mt-3",
            **{"x-show": f"feedback === '{FEEDBACK_TEACHER}'"},
        )

    return Div(
        section_label("Ask for feedback?"),
        options,
        class_select,
        cls="mb-6",
    )


def _share_group(title: str, rows: list[FT]) -> FT:
    return Div(
        P(title, cls="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1"),
        *rows,
        cls="mb-4",
    )


def _share_question(targets: ShareTargets | None, *, portfolio_mode: str) -> FT:
    """ "Share with" — collapsed; the student's groups and co-members, plus Portfolio."""
    rows: list[FT] = []
    if targets:
        group_rows = [
            AudienceCheckbox(f"{GROUP_PREFIX}{g['uid']}", g["name"], shared=False)
            for g in targets["groups"]
        ]
        people_rows = [
            AudienceCheckbox(
                f"{USER_PREFIX}{p['username']}",
                p["display_name"] or p["username"] or p["uid"],
                shared=False,
                hint=p["username"],
            )
            for p in targets["people"]
            if p["username"]
        ]
        if group_rows:
            rows.append(_share_group("Groups", group_rows))
        if people_rows:
            rows.append(_share_group("People", people_rows))
    if not rows:
        rows.append(P(_NOBODY_TO_SHARE_WITH, cls="text-sm text-muted-foreground mb-4"))

    portfolio_attrs: dict[str, object] = {
        "type": "checkbox",
        "name": "audience",
        "value": PUBLIC,
        "id": "share-public",
        "cls": "h-4 w-4 rounded-sm border-input",
    }
    if portfolio_mode != "active":
        portfolio_attrs["disabled"] = True
    portfolio_row = Div(
        Input(**portfolio_attrs),
        Span(
            Span("Portfolio", cls="text-sm ml-2"),
            Span(" — appears on your public profile", cls="text-sm text-muted-foreground"),
        ),
        Span(
            "Coming soon",
            cls=(
                "ml-2 text-10 font-bold uppercase tracking-wider "
                "text-amber-800 bg-amber-100 px-[7px] py-[2px] rounded-full"
            ),
        )
        if portfolio_mode != "active"
        else "",
        cls="flex items-center py-1",
    )
    rows.append(_share_group("Portfolio", [portfolio_row]))

    return Div(
        Button(
            section_label("Share with", tag=Span, cls="mb-0"),
            Span("(optional)", cls="text-xs text-muted-foreground ml-2"),
            Span(
                Icon("chevron-down", cls="w-4 h-4 text-slate-400"),
                cls="ml-auto flex transition-transform",
                **{":class": "shareOpen ? 'rotate-180' : ''"},
            ),
            type="button",
            cls="w-full flex items-center text-left bg-transparent border-0 p-0 cursor-pointer",
            **{"@click": "shareOpen = !shareOpen", ":aria-expanded": "shareOpen"},
        ),
        Div(
            *rows,
            cls="mt-3 border border-border rounded-[11px] bg-card p-4",
            **{"x-show": "shareOpen"},
            **{"x-cloak": True},
        ),
        cls="mb-6",
    )


def render_upload_form(
    *,
    selected_exercise_uid: str | None = None,
    exercise_title: str | None = None,
    from_ps: str | None = None,
    teacher_groups: Sequence[tuple[str, str]] = (),
    targets: ShareTargets | None = None,
    portfolio_mode: str = "coming_soon",
) -> FT:
    """Render the Submit form: Title, the two questions, the file, the send button.

    Args:
        selected_exercise_uid: The exercise this turn-in answers (``?exercise_uid=``);
            carried as a hidden field so the entry links to it. Enables AI.
        exercise_title: That exercise's title, named above the form and in the
            Title field's hint (the writer's default title is "<title> v<N>").
        from_ps: PathStep UID passed as ``about_path_step_uid`` hidden field.
        teacher_groups: ``(uid, name)`` of the classes the student studies in — with
            more than one and no exercise, the Teacher answer offers "Which class?".
        targets: Whom the student may share with (``EntrySharingService.targets``);
            ``None`` renders the "nobody yet" note.
        portfolio_mode: "coming_soon" (Portfolio disabled) or "active" (selectable).
    """
    has_exercise = bool(selected_exercise_uid)

    hidden_fields: list[FT] = []
    if selected_exercise_uid:
        # The exercise link persists on EVERY answer (ruled 2026-07-03,
        # systems review R1): a submission fulfills its exercise regardless of
        # who responds — responder (teacher/LLM/nobody) and audience are
        # orthogonal axes.
        hidden_fields.append(
            Input(type="hidden", name="fulfills_exercise_uid", value=selected_exercise_uid)
        )
    if from_ps:
        hidden_fields.append(Input(type="hidden", name="about_path_step_uid", value=from_ps))

    exercise_note: FT | None = None
    if has_exercise:
        exercise_note = P(
            Span("Answering: ", cls="text-muted-foreground"),
            Span(exercise_title or selected_exercise_uid, cls="font-medium text-foreground"),
            cls="text-sm mb-5",
        )

    title_field = Div(
        section_label("Title"),
        Input(
            type="text",
            name="title",
            maxlength="200",
            placeholder=(
                f"Leave empty to use “{exercise_title} v<N>”"
                if has_exercise and exercise_title
                else "Leave empty to use the file name"
            ),
            cls=(
                "w-full px-3 py-2 border border-border rounded-[9px] bg-card text-sm "
                "text-foreground placeholder:text-slate-400"
            ),
        ),
        cls="mb-6",
    )

    dropzone = UploadDropzone(
        "Drag & drop your file here",
        (
            "or ",
            Span("browse", cls="text-blue-600 font-semibold"),
            " — audio, text, PDF, images, video",
        ),
        icon="upload-cloud",
        show_expr="!file",
        click_handler="browse()",
        drop_handler="onDrop($event)",
        dragover_handler="onDragOver($event)",
        dragleave_handler="onDragLeave($event)",
        active_expr="dragOver",
        cls="py-[38px] transition-[border-color,background-color] duration-160 ease-linear",
    )
    file_card = SelectedFileCard(
        file_name_expr="file ? file.name : ''",
        meta_expr="file ? fmtSize(file.size) : ''",
        show_expr="!!file",
        replace_handler="browse()",
        remove_handler="removeFile()",
    )

    send_btn_enabled = Button(
        Icon("send", cls="w-4 h-4"),
        Span(**{"x-text": "sendLabel"}),
        type="submit",
        cls=(
            "inline-flex items-center gap-[9px] px-[18px] py-[11px] rounded-[9px] "
            "border-0 bg-foreground text-background text-sm font-semibold cursor-pointer "
            "shadow-[0_1px_2px_rgba(15,23,42,0.12)] hover:opacity-90 transition-opacity"
        ),
        **{"x-show": "canSend"},
        **{"x-cloak": True},
    )
    send_btn_disabled = Span(
        Icon("send", cls="w-4 h-4"),
        Span(**{"x-text": "sendLabel"}),
        cls=(
            "inline-flex items-center gap-[9px] px-[18px] py-[11px] rounded-[9px] "
            "bg-border text-slate-400 text-sm font-semibold cursor-not-allowed"
        ),
        **{"x-show": "!canSend"},
    )
    card_footer = Div(
        Span("Up to 100 MB per file.", cls="text-xs text-slate-400"),
        Div(send_btn_enabled, send_btn_disabled),
        cls=(
            "mt-[26px] pt-[22px] border-t border-slate-100 flex items-center justify-between gap-4"
        ),
    )

    toast = Div(
        Span(Icon("check", cls="w-[18px] h-[18px]"), cls="text-green-400 flex"),
        Span("Submission sent", cls="text-sm font-semibold"),
        cls=(
            "fixed bottom-7 left-1/2 -translate-x-1/2 z-50 "
            "flex items-center gap-[10px] px-[18px] py-3 rounded-[11px] "
            "bg-foreground text-background "
            "shadow-[0_12px_30px_rgba(15,23,42,0.28)]"
        ),
        **{"x-show": "sent"},
        **{"x-cloak": True},
        **{"x-transition:enter": "transition ease-out duration-200"},
        **{"x-transition:enter-start": "opacity-0 translate-y-2"},
        **{"x-transition:enter-end": "opacity-100 translate-y-0"},
        **{"x-transition:leave": "transition ease-in duration-150"},
        **{"x-transition:leave-start": "opacity-100 translate-y-0"},
        **{"x-transition:leave-end": "opacity-0 translate-y-2"},
    )

    return Div(
        Div(
            Form(
                *hidden_fields,
                # Pipeline + the feedback half of the audience, from the
                # Alpine feedback state; the share checkboxes add their own
                # ``audience`` values. Disabled when no teacher is asked, so
                # the field is absent rather than empty.
                Input(type="hidden", name="pipeline", **{"x-bind:value": "pipeline"}),
                Input(
                    type="hidden",
                    name="audience",
                    **{"x-bind:value": "feedbackAudience", "x-bind:disabled": "!feedbackAudience"},
                ),
                Input(
                    type="file",
                    name="file",
                    accept="audio/*,text/*,.pdf,application/pdf,image/*,video/*",
                    cls="hidden",
                    **{"x-ref": "fileInput", "@change": "onFileChange($event)"},
                ),
                exercise_note,
                title_field,
                _feedback_question(has_exercise=has_exercise, teacher_groups=teacher_groups),
                _share_question(targets, portfolio_mode=portfolio_mode),
                Div(section_label("Your file"), dropzone, file_card),
                card_footer,
                hx_post="/api/user-entries/upload",
                hx_encoding="multipart/form-data",
                hx_swap="none",
            ),
            cls=(
                "border border-border rounded-2xl bg-card p-[26px] "
                "shadow-[0_1px_2px_rgba(15,23,42,0.04)]"
            ),
        ),
        toast,
        **{"x-data": f"submit('{FEEDBACK_TEACHER}', {str(not has_exercise).lower()})"},
    )


__all__ = [
    "ALL_MY_TEACHERS",
    "FEEDBACK_AI",
    "FEEDBACK_NONE",
    "FEEDBACK_TEACHER",
    "SUBMIT_PAGE_PATH",
    "render_upload_form",
    "submit_page_href",
]
