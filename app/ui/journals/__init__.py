"""Journals UI — DNWF workflow page and HTMX stage fragments."""

from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    A,
    Button,
    Div,
    Form,
    Input,
    Label,
    P,
    Span,
    Textarea,
)
from monsterui.franken import ButtonT, CardBody, CardHeader, CardTitle
from monsterui.franken import CardContainer as Card

if TYPE_CHECKING:
    from core.models.enums.user_enums import JournalMode

# ------------------------------------------------------------------
# Page (GET /journals)
# ------------------------------------------------------------------


def _LoadingIndicator() -> Any:
    return Div(
        P("Processing…", cls="text-sm text-muted-foreground mt-3"),
        id="journal-loading",
        cls="htmx-indicator",
    )


# ------------------------------------------------------------------
# Private chat helpers
# ------------------------------------------------------------------


def _UserBubble(text: str) -> Any:
    """Right-aligned user message bubble appended to #journal-thread."""
    return Div(
        Div(
            text,
            cls=(
                "max-w-[80%] bg-muted rounded-[20px] px-[18px] py-3"
                " text-[15px] leading-[1.6] text-foreground whitespace-pre-wrap"
            ),
        ),
        cls="flex justify-end py-2",
    )


def _AiBubble(label: str, text: str) -> Any:
    """Left-aligned AI response bubble with avatar, prose, and copy action.

    Each bubble carries its own Alpine copy-state scope — multiple bubbles
    in the same thread each manage their own clipboard toggle independently.
    """
    import json as _json

    from monsterui.franken import UkIcon

    alpine_data = (
        "{ copied: false,"
        f" responseText: {_json.dumps(text)},"
        "  copy() { navigator.clipboard.writeText(this.responseText)"
        "    .then(() => { this.copied = true;"
        "      setTimeout(() => this.copied = false, 2000); }); } }"
    )

    return Div(
        # Avatar
        Div(
            "J",
            cls=(
                "w-[30px] h-[30px] rounded-full bg-foreground text-background"
                " flex items-center justify-center text-sm font-bold flex-shrink-0"
            ),
        ),
        # Content
        Div(
            Span(label, cls="text-[13px] font-semibold text-muted-foreground"),
            P(
                text,
                cls="text-[15px] leading-[1.75] text-foreground whitespace-pre-wrap mt-1",
            ),
            # Copy action
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
                cls="flex items-center gap-2 mt-3",
            ),
            cls="flex-1 min-w-0",
        ),
        cls="flex gap-4 py-4",
        **{"x-data": alpine_data},
    )


def _Composer(
    original_entry: str,
    ai_response: str,
    title: str,
    mode_value: str,
) -> Any:
    """Sticky follow-up form pinned at the bottom of #journal-workspace.

    Hidden inputs carry IDs so the follow-up route can update them via
    HTMX out-of-band swaps without resetting the textarea.
    """
    from monsterui.franken import UkIcon

    return Form(
        Input(
            id="journal-original-entry",
            type="hidden",
            name="original_entry",
            value=original_entry,
        ),
        Input(
            id="journal-ai-response",
            type="hidden",
            name="ai_response",
            value=ai_response,
        ),
        Input(type="hidden", name="title", value=title),
        Input(type="hidden", name="journal_mode", value=mode_value),
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
            cls=("border border-border rounded-[25px] px-[18px] pt-3 pb-3 bg-background shadow-sm"),
        ),
        id="journal-composer",
        hx_post="/journals/follow-up",
        hx_target="#journal-thread",
        hx_swap="beforeend",
        hx_indicator="#journal-reply-loading",
        # Clear textarea and scroll thread to bottom after each exchange.
        # Do NOT call form.reset() — that would clobber the OOB-updated hidden inputs.
        hx_on__after_request=(
            "this.querySelector('textarea').value='';"
            "var s=document.getElementById('journal-thread');"
            "if(s){s.scrollTop=s.scrollHeight;}"
        ),
        cls="border-t border-border px-6 py-4 bg-background flex-shrink-0",
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
        id="journal-workspace",
        cls="p-6",
    )


def Stage3Fragment(
    raw_entry: str,
    title: str,
    related_output: str,
) -> Any:
    """Fragment returned after Stage 3 — What Is Related completes.

    Now includes a follow-up composer so the user can continue the conversation
    after the DNWF completes. Context: original entry + Stage 3 output.
    """
    from core.models.enums.user_enums import JournalMode

    resolved = JournalMode.default()

    return Div(
        Div(
            _AiBubble("Stage 3 — What Is Related", related_output),
            id="journal-thread",
            cls="flex-1 overflow-y-auto p-6 space-y-6",
        ),
        Div(
            A(
                "Process another file",
                href="/journals",
                cls=(
                    "text-[13px] text-muted-foreground hover:text-foreground"
                    " transition-colors no-underline"
                ),
            ),
            _Composer(raw_entry, related_output, title, resolved.value),
            cls="flex-shrink-0",
        ),
        id="journal-workspace",
        cls="flex flex-col h-full",
    )


def StandardResponseFragment(
    raw_entry: str,
    title: str,
    response_output: str,
    mode: "JournalMode | None" = None,
) -> Any:
    """Growing chat thread — initial AI response with sticky composer.

    Replaces the single-swap pattern: the workspace is now a flex column with
    a scrollable #journal-thread and a sticky #journal-composer. Follow-ups
    append new bubbles via hx-swap="beforeend" on #journal-thread.
    """
    from core.models.enums.user_enums import JournalMode

    resolved = mode or JournalMode.default()
    label = (
        "Daily Notes Workflow" if mode is None else f"Journal Response — {resolved.display_label()}"
    )

    return Div(
        Div(
            _AiBubble(label, response_output),
            id="journal-thread",
            cls="flex-1 overflow-y-auto p-6 space-y-6",
        ),
        _Composer(raw_entry, response_output, title, resolved.value),
        id="journal-workspace",
        cls="flex flex-col h-full",
    )


def FileOutputFragment(
    title: str,
    output_filename: str,
    response_output: str,
) -> Any:
    """Shown after a compiled journal file is processed and saved to je_out/.

    The user downloads the file and opens it in Obsidian. The prose is NOT
    displayed inline (it can be very long). The copy button copies to clipboard.
    je_out/ is excluded from vault sync — users decide what enters their vault.

    Includes a follow-up composer for in-session questions about the output.
    """
    import json as _json
    import urllib.parse

    from monsterui.franken import UkIcon

    from core.models.enums.user_enums import JournalMode

    safe_href = urllib.parse.quote(output_filename, safe="")
    resolved_mode = JournalMode.default()

    alpine_data = (
        "{ copied: false,"
        f" responseText: {_json.dumps(response_output)},"
        "  copy() { navigator.clipboard.writeText(this.responseText)"
        "    .then(() => { this.copied = true;"
        "      setTimeout(() => this.copied = false, 2000); }); } }"
    )

    return Div(
        Div(
            # Saved banner + download
            Div(
                Div(
                    UkIcon("file-check", height=18, width=18, cls="text-green-600 flex-shrink-0"),
                    Div(
                        P(
                            "Your file is automatically saved in your Journal Output folder.",
                            cls="text-sm font-semibold",
                        ),
                        cls="flex-1 min-w-0",
                    ),
                    Button(
                        UkIcon("download", height=14, width=14),
                        Span("Download"),
                        type="button",
                        cls=(
                            "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[8px]"
                            " text-sm font-medium bg-foreground text-background"
                            " hover:bg-foreground/85 transition-colors border-0 cursor-pointer"
                        ),
                        **{
                            "@click": f"window.location.href='/journals/je-out/{safe_href}'"
                        },  # boundary: fasthtml-elements
                    ),
                    cls="flex items-center gap-3",
                ),
                cls="rounded-xl border border-border bg-muted/40 px-4 py-3 mb-5",
            ),
            # Avatar + mode label + copy action (no prose — file is the artifact)
            Div(
                Div(
                    "J",
                    cls=(
                        "w-[30px] h-[30px] rounded-full bg-foreground text-background"
                        " flex items-center justify-center text-sm font-bold flex-shrink-0"
                    ),
                ),
                Div(
                    Span(
                        "Daily Notes Workflow",
                        cls="text-[13px] font-semibold text-muted-foreground",
                    ),
                    Div(
                        Button(
                            UkIcon("copy", height=15, width=15),
                            type="button",
                            aria_label="Copy output",
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
                        cls="flex items-center gap-2 mt-2",
                    ),
                    cls="flex-1 min-w-0",
                ),
                cls="flex gap-4 py-2",
                **{"x-data": alpine_data},
            ),
            id="journal-thread",
            cls="flex-1 overflow-y-auto p-6",
        ),
        _Composer(title, response_output, title, resolved_mode.value),
        id="journal-workspace",
        cls="flex flex-col h-full",
    )


def FollowUpFragment(
    user_reply: str,
    ai_text: str,
    combined: str,
    title: str,
    mode: "JournalMode",
) -> Any:
    """Returned by the follow-up route — appended to #journal-thread via beforeend.

    Returns a tuple: two chat bubbles (main swap) plus two OOB inputs that update
    the hidden context fields in #journal-composer without a full replacement.
    """
    label = f"Journal Response — {mode.display_label()}"
    return (
        _UserBubble(user_reply),
        _AiBubble(label, ai_text),
        # OOB: update accumulated conversation context in the sticky composer
        Input(
            id="journal-original-entry",
            type="hidden",
            name="original_entry",
            value=combined,
            hx_swap_oob="true",
        ),
        Input(
            id="journal-ai-response",
            type="hidden",
            name="ai_response",
            value=ai_text,
            hx_swap_oob="true",
        ),
    )


def FollowUpErrorFragment(message: str) -> Any:
    """Error notification appended to #journal-thread when a follow-up call fails.

    Unlike ErrorFragment, this carries no id and no workspace-level swap — it is
    appended via hx-swap="beforeend" and sits inline in the conversation thread.
    """
    from monsterui.franken import UkIcon

    return Div(
        UkIcon("alert-circle", height=15, width=15, cls="text-destructive flex-shrink-0"),
        P(message, cls="text-sm text-destructive"),
        cls="flex items-center gap-2 py-3 px-1 text-destructive",
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
