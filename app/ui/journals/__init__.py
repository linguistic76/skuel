"""Journals UI — DNWF workflow page and HTMX stage fragments."""

from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    H3,
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
    return Div(
        Div(
            H3("Daily Notes Workflow", cls="text-lg font-semibold mb-1"),
            P(
                "Scribe → Thought Partner → What Is Related",
                cls="text-sm text-muted-foreground mb-6",
            ),
            _EntryForm(),
            cls="max-w-2xl",
        ),
        id="journal-workspace",
        cls="p-6",
    )


def _StandardPage() -> Any:
    return Div(
        Div(
            H3("Journal", cls="text-lg font-semibold mb-1"),
            P(
                "Write a note and get a response connecting it to your active goals, tasks, and habits.",
                cls="text-sm text-muted-foreground mb-6",
            ),
            _StandardEntryForm(),
            cls="max-w-2xl",
        ),
        id="journal-workspace",
        cls="p-6",
    )


def _StandardEntryForm() -> Any:
    return Form(
        Div(
            Label("Title (optional)", cls="text-sm font-medium"),
            Input(
                name="title",
                placeholder="What is today's note about?",
                cls="w-full mt-1",
            ),
            cls="mb-4",
        ),
        Div(
            Label("Daily note", cls="text-sm font-medium"),
            Textarea(
                name="raw_entry",
                placeholder="Write your thoughts here…",
                rows="12",
                required=True,
                cls="w-full mt-1 font-mono text-sm resize-y",
            ),
            cls="mb-5",
        ),
        _ModeSelector(),
        Button(
            "Respond →",
            cls=ButtonT.default,
            hx_post="/journals/respond",
            hx_target="#journal-workspace",
            hx_swap="outerHTML",
            hx_include="closest form",
            hx_indicator="#journal-loading",
        ),
        _LoadingIndicator(),
        **{"x-data": "{ journalMode: 'reflective' }"},
    )


def _EntryForm() -> Any:
    return Form(
        Div(
            Label("Title (optional)", cls="text-sm font-medium"),
            Input(
                name="title",
                placeholder="What is today's note about?",
                cls="w-full mt-1",
            ),
            cls="mb-4",
        ),
        Div(
            Label("Daily note", cls="text-sm font-medium"),
            Textarea(
                name="raw_entry",
                placeholder="Write your daily note here…",
                rows="14",
                required=True,
                cls="w-full mt-1 font-mono text-sm resize-y",
            ),
            cls="mb-5",
        ),
        _ModeSelector(),
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
        **{"x-data": "{ journalMode: 'reflective' }"},
    )


def _LoadingIndicator() -> Any:
    return Div(
        P("Processing…", cls="text-sm text-muted-foreground mt-3"),
        id="journal-loading",
        cls="htmx-indicator",
    )


def _ModeSelector() -> Any:
    """Three-button mode toggle bound to Alpine journalMode state.

    Renders a hidden input (name=journal_mode) so the selected mode is
    submitted with the form. No wrapper x-data — caller form provides it.
    """
    modes = [
        ("reflective", "Reflective"),
        ("direct", "Direct"),
        ("jester", "Jester"),
    ]
    buttons = []
    for value, label in modes:
        buttons.append(
            Button(
                label,
                type="button",
                cls="px-3 py-1 text-xs font-medium rounded-md transition-colors border-0",
                **{
                    "@click": f"journalMode = '{value}'",
                    ":class": (
                        f"journalMode === '{value}' "
                        "? 'bg-foreground text-background' "
                        ": 'bg-transparent text-muted-foreground hover:text-foreground'"
                    ),
                },
            )
        )
    return Div(
        Div(
            Span("Mode", cls="text-xs font-medium text-muted-foreground mr-2"),
            Div(
                *buttons,
                cls="flex border border-border rounded-lg p-0.5 gap-0.5",
            ),
            cls="flex items-center mb-4",
        ),
        Input(
            type="hidden",
            name="journal_mode",
            **{"x-bind:value": "journalMode"},  # boundary: fasthtml-elements
        ),
    )


# ------------------------------------------------------------------
# Stage fragments (returned as HTMX swaps to #journal-workspace)
# ------------------------------------------------------------------


def Stage1Fragment(
    raw_entry: str, title: str, scribe_output: str, mode: "JournalMode | None" = None
) -> Any:
    """Fragment returned after Stage 1 — Scribe completes."""
    from core.models.enums.user_enums import JournalMode

    resolved_mode = (mode or JournalMode.default()).value
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
                "journal_mode": resolved_mode,
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
    mode: "JournalMode | None" = None,
) -> Any:
    """Fragment returned after Stage 2 — Thought Partner completes."""
    from core.models.enums.user_enums import JournalMode

    resolved_mode = (mode or JournalMode.default()).value
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
                "journal_mode": resolved_mode,
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
    raw_entry: str, title: str, response_output: str, mode: "JournalMode | None" = None
) -> Any:
    """Fragment returned after a STANDARD tier journal response."""
    from core.models.enums.user_enums import JournalMode

    resolved = mode or JournalMode.default()
    card_title = f"Journal Response — {resolved.display_label()}"
    return Div(
        Card(
            CardHeader(CardTitle(card_title)),
            CardBody(
                P(
                    response_output,
                    cls="text-sm whitespace-pre-wrap leading-relaxed",
                ),
            ),
            cls="mb-6",
        ),
        _SaveBar(raw_entry=raw_entry, title=title),
        id="journal-workspace",
        cls="p-6",
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
