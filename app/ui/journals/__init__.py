"""Journals UI — DNWF workflow page and HTMX stage fragments."""

from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    Button,
    Div,
    Form,
    Input,
    Label,
    P,
    Small,
    Span,
    Textarea,
)
from monsterui.franken import ButtonT, CardBody, CardHeader, CardTitle
from monsterui.franken import CardContainer as Card

if TYPE_CHECKING:
    from core.models.enums.user_enums import JournalMode
    from core.models.user.user import User

# ------------------------------------------------------------------
# Page (GET /journals)
# ------------------------------------------------------------------


def JournalsPage(user: "User") -> Any:
    """Tier-aware journal landing page inside the Tasks+ sidebar."""
    if user.journal_tier.is_founder():
        return _FounderPage()
    return _StandardPage()


def _FounderPage() -> Any:
    from ui.journals.forms import render_upload_form, upload_form_script

    return Div(
        render_upload_form(),
        upload_form_script(),
        id="journal-workspace",
        cls="p-6 max-w-2xl",
    )


def _StandardPage() -> Any:
    from ui.journals.forms import render_upload_form, upload_form_script

    return Div(
        render_upload_form(),
        upload_form_script(),
        id="journal-workspace",
        cls="p-6 max-w-2xl",
    )


def _LoadingIndicator() -> Any:
    return Div(
        P("Processing…", cls="text-sm text-muted-foreground mt-3"),
        id="journal-loading",
        cls="htmx-indicator",
    )


# ------------------------------------------------------------------
# Stage fragments (returned as HTMX swaps to #journal-workspace)
# ------------------------------------------------------------------


def TranscriptReviewFragment(transcript: str, title: str) -> Any:
    """FOUNDER tier: transcript review card shown after audio transcription.

    The user reviews the transcript, then clicks "Scribe →" to begin the
    DNWF interactive workflow (Stage 1 → review → Stage 2 → review → Stage 3).
    """
    return Div(
        Card(
            CardHeader(CardTitle("Transcript")),
            CardBody(
                P(
                    transcript or "(empty transcript)",
                    cls="text-sm whitespace-pre-wrap leading-relaxed font-mono",
                ),
            ),
            cls="mb-6",
        ),
        Form(
            Input(type="hidden", name="raw_entry", value=transcript),
            Input(type="hidden", name="title", value=title),
            Button(
                "Scribe →",
                cls=ButtonT.default,
                hx_post="/journals/stage1",
                hx_target="#journal-workspace",
                hx_swap="outerHTML",
                hx_include="closest form",
                hx_indicator="#journal-loading",
            ),
            _LoadingIndicator(),
        ),
        id="journal-workspace",
        cls="p-6",
    )


def Stage1Fragment(raw_entry: str, title: str, scribe_output: str) -> Any:
    """Fragment returned after Stage 1 — Scribe completes."""
    return Div(
        Card(
            CardHeader(CardTitle("Stage 1 — Scribe")),
            CardBody(
                P(
                    scribe_output,
                    cls="text-sm whitespace-pre-wrap leading-relaxed",
                ),
            ),
            cls="mb-6",
        ),
        _ReviewGate(
            stage_target=2,
            hidden_fields={
                "raw_entry": raw_entry,
                "title": title,
                "scribe_output": scribe_output,
            },
            post_url="/journals/stage2",
            next_label="Thought Partner →",
            review_placeholder="Add notes for the Thought Partner (optional)…",
        ),
        id="journal-workspace",
        cls="p-6",
    )


def Stage2Fragment(
    raw_entry: str,
    title: str,
    scribe_output: str,
    thought_partner_output: str,
) -> Any:
    """Fragment returned after Stage 2 — Thought Partner completes."""
    return Div(
        Card(
            CardHeader(CardTitle("Stage 2 — Thought Partner")),
            CardBody(
                P(
                    thought_partner_output,
                    cls="text-sm whitespace-pre-wrap leading-relaxed",
                ),
            ),
            cls="mb-6",
        ),
        _ReviewGate(
            stage_target=3,
            hidden_fields={
                "raw_entry": raw_entry,
                "title": title,
                "scribe_output": scribe_output,
                "thought_partner_output": thought_partner_output,
            },
            post_url="/journals/stage3",
            next_label="What Is Related →",
            review_placeholder="Reactions or corrections before Stage 3 (optional)…",
        ),
        _SaveBar(raw_entry=raw_entry, title=title),
        id="journal-workspace",
        cls="p-6",
    )


def Stage3Fragment(
    raw_entry: str,
    title: str,
    related_output: str,
) -> Any:
    """Fragment returned after Stage 3 — What Is Related completes."""
    return Div(
        Card(
            CardHeader(CardTitle("Stage 3 — What Is Related")),
            CardBody(
                P(
                    related_output,
                    cls="text-sm whitespace-pre-wrap leading-relaxed",
                ),
            ),
            cls="mb-6",
        ),
        _SaveBar(raw_entry=raw_entry, title=title),
        id="journal-workspace",
        cls="p-6",
    )


def StandardResponseFragment(
    raw_entry: str,
    title: str,
    response_output: str,
    mode: "JournalMode | None" = None,
    already_saved: bool = False,
) -> Any:
    """Askesis-style response: avatar header, prose body, Copy icon, inline reply composer.

    The reply form posts original_entry + ai_response + user_reply as separate named
    fields to /journals/follow-up — no client-side combining needed, HTMX reads
    static values reliably.

    already_saved: set True when the entry was persisted before this fragment is
    returned (e.g. the instructions_only upload path) to suppress the duplicate-save
    "Add to Journal" button.
    """
    import json as _json

    from core.models.enums.user_enums import JournalMode
    from monsterui.franken import UkIcon

    resolved = mode or JournalMode.default()
    label = "Daily Notes Workflow" if mode is None else f"Journal Response — {resolved.display_label()}"

    # Alpine state: clipboard only — form fields are plain inputs, no reactive binding.
    alpine_data = (
        "{ copied: false,"
        f" responseText: {_json.dumps(response_output)},"
        "  copy() { navigator.clipboard.writeText(this.responseText)"
        "    .then(() => { this.copied = true;"
        "      setTimeout(() => this.copied = false, 2000); }); } }"
    )

    return Div(
        # ── Avatar + mode label ──────────────────────────────────────────
        Div(
            Div(
                "J",
                cls=(
                    "w-[30px] h-[30px] rounded-full bg-foreground text-background"
                    " flex items-center justify-center text-sm font-bold flex-shrink-0"
                ),
            ),
            Span(label, cls="text-[13px] font-semibold text-muted-foreground"),
            cls="flex items-center gap-3 mb-4",
        ),
        # ── Response prose ───────────────────────────────────────────────
        P(
            response_output,
            cls="text-[15px] leading-[1.75] text-foreground whitespace-pre-wrap mb-4",
        ),
        # ── Action bar: Copy · Add to Journal ───────────────────────────
        Div(
            Button(
                UkIcon("copy", height=15, width=15),
                type="button",
                aria_label="Copy response",
                cls=(
                    "w-[30px] h-[30px] flex items-center justify-center rounded-[7px]"
                    " text-muted-foreground hover:bg-muted hover:text-foreground"
                    " transition-colors"
                ),
                **{"@click": "copy()"},  # boundary: fasthtml-elements
            ),
            Span(
                "Copied!",
                cls="text-xs text-green-600",
                **{"x-show": "copied", "x-cloak": True},  # boundary: fasthtml-elements
            ),
            Div(cls="flex-1"),
            *(
                [Span("Saved", cls="text-xs text-muted-foreground")]
                if already_saved
                else [
                    Button(
                        "Add to Journal",
                        type="button",
                        cls="text-xs text-muted-foreground hover:text-foreground cursor-pointer",
                        hx_post="/journals/save",
                        hx_target="#journal-workspace",
                        hx_swap="outerHTML",
                        hx_vals=_json.dumps({"raw_entry": raw_entry, "title": title}),
                    )
                ]
            ),
            cls="flex items-center gap-2 pb-4 mb-6 border-b border-border",
        ),
        # ── Reply composer — server combines context, no Alpine binding ──
        Form(
            Input(type="hidden", name="original_entry", value=raw_entry),
            Input(type="hidden", name="ai_response", value=response_output),
            Input(type="hidden", name="title", value=title),
            Input(type="hidden", name="journal_mode", value=resolved.value),
            Div(
                Textarea(
                    placeholder="Follow up on this response…",
                    name="user_reply",
                    rows="3",
                    required=True,
                    cls=(
                        "w-full border-none outline-none bg-transparent resize-none"
                        " text-[15px] leading-[1.6] text-foreground"
                        " placeholder:text-muted-foreground"
                    ),
                ),
                Div(
                    P(
                        "Thinking…",
                        id="journal-reply-loading",
                        cls="text-sm text-muted-foreground htmx-indicator",
                    ),
                    Button(
                        UkIcon("arrow-up", height=16, width=16, cls="text-white"),
                        type="submit",
                        aria_label="Send follow-up",
                        cls=(
                            "w-[34px] h-[34px] rounded-full flex items-center justify-center"
                            " bg-foreground hover:bg-foreground/80 transition-colors"
                        ),
                    ),
                    cls="flex items-center justify-end gap-3 mt-2",
                ),
                cls=(
                    "border border-border rounded-[25px]"
                    " px-[18px] pt-3 pb-3 bg-background shadow-sm"
                ),
            ),
            hx_post="/journals/follow-up",
            hx_target="#journal-workspace",
            hx_swap="outerHTML",
            hx_indicator="#journal-reply-loading",
        ),
        id="journal-workspace",
        cls="p-6",
        **{"x-data": alpine_data},
    )


def SavedFragment(entry_uid: str) -> Any:
    """Confirmation fragment after saving the journal entry."""
    return Div(
        Card(
            CardBody(
                P("Journal entry added.", cls="text-sm font-medium mb-1"),
                Small(f"ID: {entry_uid}", cls="text-xs text-muted-foreground"),
            ),
        ),
        Button(
            "Write another",
            cls=ButtonT.ghost,
            hx_get="/journals",
            hx_target="#journal-workspace",
            hx_swap="outerHTML",
            cls_="mt-4",
        ),
        id="journal-workspace",
        cls="p-6",
    )


def ErrorFragment(message: str) -> Any:
    """Error state fragment for any stage failure."""
    return Div(
        Card(
            CardBody(
                P("Something went wrong.", cls="text-sm font-semibold text-destructive mb-1"),
                P(message, cls="text-xs text-muted-foreground"),
            ),
        ),
        Button(
            "Start over",
            cls=ButtonT.ghost,
            hx_get="/journals",
            hx_target="#journal-workspace",
            hx_swap="outerHTML",
            cls_="mt-4",
        ),
        id="journal-workspace",
        cls="p-6",
    )


# ------------------------------------------------------------------
# Shared helpers
# ------------------------------------------------------------------


def _ReviewGate(
    stage_target: int,
    hidden_fields: dict[str, str],
    post_url: str,
    next_label: str,
    review_placeholder: str,
) -> Any:
    hidden_inputs = [Input(type="hidden", name=k, value=v) for k, v in hidden_fields.items()]
    return Form(
        *hidden_inputs,
        Div(
            Label("Review notes", cls="text-sm font-medium"),
            Textarea(
                name="review_notes",
                placeholder=review_placeholder,
                rows="4",
                cls="w-full mt-1 text-sm resize-y",
            ),
            cls="mb-4",
        ),
        Button(
            next_label,
            cls=ButtonT.default,
            hx_post=post_url,
            hx_target="#journal-workspace",
            hx_swap="outerHTML",
            hx_include="closest form",
            hx_indicator="#journal-loading",
        ),
        _LoadingIndicator(),
        cls="mb-4",
    )


def _SaveBar(raw_entry: str, title: str) -> Any:
    return Form(
        Input(type="hidden", name="raw_entry", value=raw_entry),
        Input(type="hidden", name="title", value=title),
        Button(
            "Add to Journal",
            cls=ButtonT.primary,
            hx_post="/journals/save",
            hx_target="#journal-workspace",
            hx_swap="outerHTML",
            hx_include="closest form",
        ),
        cls="mt-2",
    )
