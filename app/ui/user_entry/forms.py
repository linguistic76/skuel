"""
UserEntry Submit Form (ADR-054)
================================

Destination-driven upload form for ``/submit``. The student picks where they
want to send their work (Teacher, AI Feedback, or Portfolio) and attaches a
single file. Pipeline and audience are derived server-side from the destination.

Destination → pipeline / audience mapping:
- Teacher  → TEACHER_REVIEW / teachers
- AI       → LLM_SUMMARY   / private
- Portfolio → NONE          / public  (coming-soon by default)

Submits via HTMX POST to ``/api/user-entries/upload`` (multipart/form-data).
CSRF is injected automatically by the global ``htmx:configRequest`` handler in
``skuel.js``. The success toast is driven by Alpine's ``sent`` state, triggered
by ``htmx:afterRequest`` on the form container.

See: /docs/decisions/ADR-054-user-entry-unified-submissions.md
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import Button, Div, Form, Input, P, Span

from ui.components import Icon
from ui.primitives import (
    SelectableOptionRow,
    SelectedFileCard,
    UploadDropzone,
    dropdown_menu,
    dropdown_separator,
    icon_tile,
)


def _dest_trigger(dest_configs: dict[str, dict[str, str]]) -> Any:
    """Full-width trigger button showing the currently selected destination."""
    options = []
    for dest, cfg in dest_configs.items():
        options.append(
            Span(
                icon_tile(cfg["icon"], cfg["tile_bg"], cfg["icon_cls"]),
                Span(
                    Span(cfg["title"], cls="block text-[14.5px] font-semibold text-foreground"),
                    Span(cfg["desc"], cls="block text-[12.5px] text-muted-foreground mt-[3px]"),
                    cls="flex-1 min-w-0",
                ),
                cls="flex items-center gap-[13px] w-full",
                **{"x-show": f"dest === '{dest}'"},
                **{"x-cloak": True} if dest != "teacher" else {},
            )
        )

    return Button(
        *options,
        Icon("chevron-down", cls="w-[18px] h-[18px] text-slate-400 flex-none"),
        type="button",
        cls=(
            "w-full flex items-center gap-[13px] px-[14px] py-3 "
            "border border-border rounded-[11px] bg-card cursor-pointer "
            "text-left font-[inherit] hover:border-slate-300 transition-colors"
        ),
        **{"@click": "menuOpen = !menuOpen"},
    )


def render_upload_form(
    assigned_exercises: list[Any] | None = None,
    selected_exercise_uid: str | None = None,
    from_ps: str | None = None,
    user_groups: list[Any] | None = None,
    force_pipeline: Any | None = None,
    *,
    default_destination: str = "teacher",
    portfolio_mode: str = "coming_soon",
) -> Any:
    """Render the submit form with destination dropdown and file uploader.

    Args:
        assigned_exercises: Unused in new design (kept for call-site compat).
        selected_exercise_uid: If set, passed as a hidden field so the entry
            links to the exercise. Also locks default_destination to "teacher".
        from_ps: PathStep UID passed as ``about_path_step_uid`` hidden field.
        user_groups: Unused in new design (kept for call-site compat).
        force_pipeline: Unused in new design (kept for call-site compat).
        default_destination: Initial dropdown selection ("teacher" or "ai").
        portfolio_mode: "coming_soon" (disabled) or "active" (selectable).
    """
    # Teacher is only valid when an exercise is linked (validator requires
    # fulfills_exercise_uid / share_with_groups / share_with_users for
    # TEACHER_REVIEW; auto_share_to_exercise_groups alone is not counted).
    has_teacher_context = bool(selected_exercise_uid)
    if selected_exercise_uid:
        default_destination = "teacher"
    elif not has_teacher_context and default_destination == "teacher":
        default_destination = "ai"

    dest_configs: dict[str, dict[str, str]] = {
        "teacher": {
            "icon": "user-round",
            "tile_bg": "bg-blue-50",
            "icon_cls": "text-blue-600",
            "title": "Teacher",
            "desc": "Send to your teacher for feedback",
        },
        "ai": {
            "icon": "sparkles",
            "tile_bg": "bg-violet-50",
            "icon_cls": "text-violet-700",
            "title": "AI Feedback",
            "desc": "An AI reads and responds to your entry",
        },
        "portfolio": {
            "icon": "globe",
            "tile_bg": "bg-slate-100",
            "icon_cls": "text-slate-400",
            "title": "Portfolio",
            "desc": "Appears on your public profile",
        },
    }

    # Optional context fields (silent hidden inputs)
    hidden_fields: list[Any] = []
    if selected_exercise_uid:
        # The exercise link persists on EVERY destination (ruled 2026-07-03,
        # systems review R1): a submission fulfills its exercise regardless of
        # who responds — responder (teacher/LLM) and visibility are orthogonal
        # axes. "Submitted" means work exists against the exercise, which is
        # true for AI-destined turn-ins too. Supersedes the #392 cure that
        # disabled this input for non-teacher destinations and thereby made
        # self-serve exercise submission impossible.
        hidden_fields.append(
            Input(
                type="hidden",
                name="fulfills_exercise_uid",
                value=selected_exercise_uid,
            )
        )
    if from_ps:
        hidden_fields.append(Input(type="hidden", name="about_path_step_uid", value=from_ps))

    # Destination menu
    destination_dropdown = Div(
        # Trigger
        _dest_trigger(dest_configs),
        # Menu (absolute dropdown)
        dropdown_menu(
            SelectableOptionRow(
                icon=dest_configs["teacher"]["icon"],
                tile_bg=dest_configs["teacher"]["tile_bg"],
                icon_cls=dest_configs["teacher"]["icon_cls"],
                title=dest_configs["teacher"]["title"],
                subtitle=dest_configs["teacher"]["desc"],
                selected_expr="dest === 'teacher'",
                click_handler="selectDest('teacher')",
                disabled=not has_teacher_context,
            ),
            SelectableOptionRow(
                icon=dest_configs["ai"]["icon"],
                tile_bg=dest_configs["ai"]["tile_bg"],
                icon_cls=dest_configs["ai"]["icon_cls"],
                title=dest_configs["ai"]["title"],
                subtitle=dest_configs["ai"]["desc"],
                selected_expr="dest === 'ai'",
                click_handler="selectDest('ai')",
            ),
            dropdown_separator(),
            SelectableOptionRow(
                icon=dest_configs["portfolio"]["icon"],
                tile_bg=dest_configs["portfolio"]["tile_bg"],
                icon_cls=dest_configs["portfolio"]["icon_cls"],
                title=dest_configs["portfolio"]["title"],
                subtitle=dest_configs["portfolio"]["desc"],
                selected_expr="dest === 'portfolio'",
                click_handler="selectDest('portfolio')",
                disabled=(portfolio_mode != "active"),
                title_extra=Span(
                    "Coming soon",
                    cls=(
                        "text-[10px] font-bold uppercase tracking-[0.05em] "
                        "text-amber-800 bg-amber-100 px-[7px] py-[2px] rounded-full"
                    ),
                )
                if portfolio_mode == "coming_soon"
                else None,
            ),
            **{"x-show": "menuOpen"},
            **{"x-cloak": True},  # type: ignore[arg-type]  # boundary: fasthtml-elements
            **{"x-ref": "dropdown"},
        ),
        cls="relative",
    )

    # File uploader — dropzone (empty state)
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
        cls="py-[38px] transition-[border-color,background-color] duration-[160ms] ease-linear",
    )

    # File card (filled state)
    file_card = SelectedFileCard(
        file_name_expr="file ? file.name : ''",
        meta_expr="file ? fmtSize(file.size) : ''",
        show_expr="!!file",
        replace_handler="browse()",
        remove_handler="removeFile()",
    )

    # Card footer: file size limit hint + send button
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
        Span("Up to 100 MB per file.", cls="text-[12.5px] text-slate-400"),
        Div(send_btn_enabled, send_btn_disabled),
        cls=(
            "mt-[26px] pt-[22px] border-t border-slate-100 flex items-center justify-between gap-4"
        ),
    )

    # Success toast (fixed bottom-center)
    toast = Div(
        Span(
            Icon("check", cls="w-[18px] h-[18px]"),
            cls="text-green-400 flex",
        ),
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
        # Form card
        Div(
            Form(
                *hidden_fields,
                # Pipeline + audience resolved from Alpine dest state
                Input(type="hidden", name="pipeline", **{"x-bind:value": "pipeline"}),
                Input(type="hidden", name="audience", **{"x-bind:value": "audience"}),
                # Hidden file input (programmatically triggered)
                Input(
                    type="file",
                    name="file",
                    accept="audio/*,text/*,.pdf,application/pdf,image/*,video/*",
                    cls="hidden",
                    **{"x-ref": "fileInput", "@change": "onFileChange($event)"},
                ),
                # 1. SEND TO
                Div(
                    P(
                        "Send to",
                        cls="block text-xs font-semibold uppercase tracking-[0.05em] text-muted-foreground mb-[9px]",
                    ),
                    destination_dropdown,
                    cls="mb-6",
                ),
                # 2. YOUR FILE
                Div(
                    P(
                        "Your file",
                        cls="block text-xs font-semibold uppercase tracking-[0.05em] text-muted-foreground mb-[9px]",
                    ),
                    dropzone,
                    file_card,
                ),
                # 3. Footer
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
        **{
            "x-data": f"submit('{default_destination}', '{portfolio_mode}', {str(not has_teacher_context).lower()})",
        },
    )
