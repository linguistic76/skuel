"""Journal entry card rendering components."""

from typing import Any

from fasthtml.common import Div, P, Span
from monsterui.franken import ButtonT

from core.models.enums.entity_enums import EntityStatus
from core.models.exercises.exercise import Exercise
from core.models.user_entry.user_entry import UserEntry
from ui.patterns.card_generator import CardGenerator
from ui.patterns.empty_state import EmptyState
from ui.primitives import ButtonLink


def render_journal_card(je_input: UserEntry) -> Any:
    """Render a single journal entry card for the browse grid using CardGenerator."""
    from ui.feedback import StatusBadge

    file_size = je_input.file_size or 0
    file_size_mb = file_size / 1024 / 1024 if file_size else 0

    status = je_input.status
    status_str = (
        status.value if isinstance(status, EntityStatus) else str(status) if status else None
    )

    # Build metadata line
    meta_parts: list[str] = []
    if je_input.original_filename:
        meta_parts.append(je_input.original_filename)
    if file_size_mb > 0:
        meta_parts.append(f"{file_size_mb:.2f} MB")
    if je_input.file_type:
        meta_parts.append(je_input.file_type)

    # Download button for completed entries
    action_buttons: list[Any] = []
    if status == EntityStatus.COMPLETED:
        action_buttons.append(
            ButtonLink(
                "Download",
                href=f"/submit/journals/{je_input.uid}/download",
                cls=(ButtonT.primary, ButtonT.sm),
            )
        )

    return CardGenerator.from_dataclass(
        {"title": je_input.title or "Untitled"},
        display_fields=[],
        header_badges=[
            StatusBadge(status_str) if status_str else None,
        ],
        show_labels=False,
        metadata=[" \u2022 ".join(meta_parts)] if meta_parts else None,
        actions=Div(*action_buttons, cls="flex gap-2") if action_buttons else None,
        card_attrs={"cls": "mb-2"},
    )


def render_journals_grid(je_inputs: list[UserEntry]) -> Any:
    """Render journal entries grid as HTML fragment for HTMX swap."""
    if not je_inputs:
        return Div(
            EmptyState(title="No journals found"),
            id="journals-grid-container",
        )

    return Div(
        *[render_journal_card(ji) for ji in je_inputs],
        id="journals-grid-container",
    )


def render_instruction_card(ex: Exercise, is_first: bool = False) -> Any:
    """Render one saved instruction file as a selectable card."""
    uid = ex.uid
    title = ex.title or "Unnamed"
    created_at = ex.created_at

    date_str = created_at.strftime("%b %d, %Y") if created_at else ""

    selected_cls = "ring-2 ring-primary bg-muted" if is_first else ""
    return Div(
        Div(
            Span(title, cls="text-sm font-semibold truncate"),
            Span(date_str, cls="text-xs text-muted-foreground shrink-0 ml-2"),
            cls="flex items-center justify-between",
        ),
        cls=f"instruction-card border border-border rounded-lg p-3 cursor-pointer hover:bg-muted transition-colors {selected_cls}",
        **{
            "data-uid": uid,
            "onclick": f"selectInstruction('{uid}', this)",
        },
    )


def _exercise_created_at_sort_key(ex: Exercise) -> str:
    """Sort key for exercises by created_at (descending-friendly)."""
    return ex.created_at.isoformat() if ex.created_at else ""


def render_instruction_list(exercises: list[Exercise], error: str | None = None) -> Any:
    """Return the #instruction-file-list fragment (initial render or HTMX swap)."""
    exercises_sorted = sorted(
        exercises,
        key=_exercise_created_at_sort_key,
        reverse=True,
    )[:5]

    parts: list[Any] = []
    if error:
        parts.append(P(f"Error: {error}", cls="text-sm text-error mb-2"))

    if exercises_sorted:
        parts.extend(
            render_instruction_card(ex, is_first=(i == 0)) for i, ex in enumerate(exercises_sorted)
        )
    else:
        parts.append(EmptyState(title="No saved instruction files yet"))

    return Div(*parts, id="instruction-file-list", cls="space-y-2")
