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
    Textarea,
)
from monsterui.franken import ButtonT, CardBody, CardHeader, CardTitle
from monsterui.franken import CardContainer as Card

from ui.patterns.empty_state import EmptyState

if TYPE_CHECKING:
    from core.models.user.user import User

# ------------------------------------------------------------------
# Page (GET /journals)
# ------------------------------------------------------------------


def JournalsPage(user: "User") -> Any:
    """Tier-aware journal landing page inside the Tasks+ sidebar."""
    if user.journal_tier.is_founder():
        return _FounderPage()
    return _StandardPlaceholderPage()


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


def _StandardPlaceholderPage() -> Any:
    return Div(
        EmptyState(
            title="Journal",
            description=(
                "Write a journal entry and the app will connect it to your "
                "active goals, tasks, and habits. Coming soon."
            ),
            icon="book-open",
        ),
        cls="p-6",
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
            hidden_fields={"raw_entry": raw_entry, "title": title, "scribe_output": scribe_output},
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
    hidden_inputs = [
        Input(type="hidden", name=k, value=v) for k, v in hidden_fields.items()
    ]
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
