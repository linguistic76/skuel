"""Choices UI view components.

Pure FastHTML components for rendering choice data. No service calls —
routes fetch data and pass it to these components.

Usage:
    from ui.activities.choices_views import ChoiceList, ChoiceFilterBar, ChoiceStatsBar
"""

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    H3,
    A,
    Button,
    Div,
    Form,
    Label,
    Li,
    Option,
    P,
    Select,
    Small,
    Span,
    Ul,
)

from ui.activities.nav import ActivityDomainNav
from ui.feedback import PriorityBadge, StatusBadge
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader
from ui.patterns.relationships.relationship_section import EntityRelationshipsSection
from ui.patterns.stats_grid import StatItem, StatsGrid

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.models.choice.choice import Choice
    from core.models.choice.choice_option import ChoiceOption


def ChoiceStatsBar(choices: list["Choice"]) -> "FT":
    """Quick stats bar showing choice counts."""
    total = len(choices)
    pending = sum(
        1 for c in choices if not c.decided_at and not (c.status and c.status.value == "completed")
    )
    decided = sum(
        1 for c in choices if c.decided_at or (c.status and c.status.value == "completed")
    )
    satisfaction_scores = [
        c.satisfaction_score
        for c in choices
        if c.satisfaction_score is not None and c.satisfaction_score > 0
    ]
    avg_satisfaction = (
        sum(satisfaction_scores) / len(satisfaction_scores) if satisfaction_scores else 0
    )

    stats = [
        StatItem(label="Total", value=total, href="/choices?status=all"),
        StatItem(
            label="Pending",
            value=pending,
            color="warning" if pending > 0 else None,
            href="/choices?status=pending",
        ),
        StatItem(label="Decided", value=decided, color="success", href="/choices?status=decided"),
        StatItem(
            label="Avg Satisfaction",
            value=f"{avg_satisfaction:.1f}/5" if avg_satisfaction > 0 else "-",
            color="primary" if avg_satisfaction >= 3.5 else None,
        ),
    ]
    return StatsGrid(stats, cols=4)


def ChoiceFilterBar(
    status_filter: str = "pending",
    sort_by: str = "deadline",
) -> "FT":
    """Filter and sort controls for the choice list. HTMX-powered."""
    return Form(
        Div(
            Div(
                Label("Status", cls="uk-form-label"),
                Select(
                    Option("Pending", value="pending", selected=status_filter == "pending"),
                    Option("Decided", value="decided", selected=status_filter == "decided"),
                    Option("All", value="all", selected=status_filter == "all"),
                    name="status",
                    cls="uk-select uk-form-small",
                ),
                cls="uk-form-controls",
            ),
            Div(
                Label("Sort", cls="uk-form-label"),
                Select(
                    Option("Deadline", value="deadline", selected=sort_by == "deadline"),
                    Option("Priority", value="priority", selected=sort_by == "priority"),
                    Option("Recently Created", value="created", selected=sort_by == "created"),
                    Option("Title", value="title", selected=sort_by == "title"),
                    name="sort_by",
                    cls="uk-select uk-form-small",
                ),
                cls="uk-form-controls",
            ),
            cls="uk-grid uk-grid-small uk-child-width-1-2@s uk-child-width-auto@m",
            **{"uk-grid": "true"},
        ),
        hx_get="/choices/list-fragment",
        hx_target="#choice-list",
        hx_trigger="change",
        hx_include="[name]",
        cls="uk-margin-bottom",
    )


def ChoiceList(
    choices: list["Choice"],
    connections_map: dict[str, list[dict[str, str]]] | None = None,
) -> "FT":
    """Render a list of choice cards. Returns a replaceable container for HTMX."""
    if not choices:
        return Div(
            EmptyState(
                title="No choices found",
                description="Upload YAML files to add choices, or adjust your filters.",
                action_text="Upload Choices",
                action_href="/upload",
            ),
            id="choice-list",
        )

    cards = [
        ChoiceCard(choice, connections_map.get(choice.uid, []) if connections_map else [])
        for choice in choices
    ]
    return Div(*cards, id="choice-list", cls="uk-margin-top")


def ChoiceCard(
    choice: "Choice",
    connections: list[dict[str, str]] | None = None,
) -> "FT":
    """Single choice card with type, deadline, decision status, and connections."""
    is_decided = bool(choice.decided_at) or (choice.status and choice.status.value == "completed")

    # Status toggle button
    new_status = "active" if is_decided else "completed"
    toggle_icon = "check" if is_decided else "git-branch"
    toggle_cls = "uk-text-success" if is_decided else ""

    toggle_btn = Button(
        Span(cls=f"uk-icon {toggle_cls}", **{"uk-icon": toggle_icon}),
        hx_post=f"/api/choices/{choice.uid}/status",
        hx_vals=f'{{"status": "{new_status}"}}',
        hx_target=f"#choice-{_safe_id(choice.uid)}",
        hx_swap="outerHTML",
        cls="uk-button uk-button-default uk-button-small uk-border-rounded",
        title=f"Mark as {new_status}",
    )

    # Title
    title_cls = "uk-text-muted" if is_decided else ""
    title_el = A(
        choice.title or "Untitled",
        href=f"/choices/detail?uid={choice.uid}",
        cls=f"uk-link-text {title_cls}",
    )

    # Badges
    badges: list[Any] = []
    if choice.choice_type:
        badges.append(Span(str(choice.choice_type.value).title(), cls="uk-badge"))
    if choice.priority:
        badges.append(PriorityBadge(str(choice.priority)))
    if choice.status:
        badges.append(StatusBadge(str(choice.status)))
    if choice.options:
        badges.append(Span(f"{len(choice.options)} options", cls="uk-badge uk-badge-secondary"))

    # Deadline
    deadline_el = Span()
    if choice.decision_deadline:
        overdue = _is_deadline_past(choice)
        dl_str = str(choice.decision_deadline)[:10]
        if overdue and not is_decided:
            dl_str += " (overdue)"
        dl_cls = "uk-text-danger uk-text-bold" if overdue and not is_decided else "uk-text-muted"
        deadline_el = Small(f"Deadline: {dl_str}", cls=dl_cls)

    # Satisfaction score for decided choices
    satisfaction_el = Span()
    if is_decided and choice.satisfaction_score and choice.satisfaction_score > 0:
        satisfaction_el = Small(
            f"Satisfaction: {choice.satisfaction_score}/5",
            cls="uk-text-muted uk-margin-small-left",
        )

    # Tags
    tags_el = Span()
    if choice.tags:
        tag_badges = [
            Span(tag, cls="uk-badge uk-badge-secondary uk-margin-small-right")
            for tag in choice.tags[:5]
        ]
        tags_el = Div(*tag_badges, cls="uk-margin-small-top")

    # Connection badges
    conn_el = _ConnectionBadges(connections or [])

    # Card assembly
    header = Div(
        toggle_btn,
        Div(
            Div(title_el, satisfaction_el, cls="uk-flex uk-flex-middle uk-flex-wrap"),
            Div(*badges, cls="uk-flex uk-flex-wrap uk-flex-middle uk-margin-small-top")
            if badges
            else "",
            deadline_el,
            tags_el,
            conn_el,
            cls="uk-margin-small-left uk-width-expand",
        ),
        cls="uk-flex uk-flex-top",
    )

    opacity = "uk-opacity-75" if is_decided else ""
    return Div(
        header,
        id=f"choice-{_safe_id(choice.uid)}",
        cls=f"uk-card uk-card-default uk-card-body uk-card-small uk-margin-small-bottom {opacity}",
    )


def ChoiceDetailView(
    choice: "Choice",
    connections: list[dict[str, str]],
) -> "FT":
    """Full detail page for a single choice."""
    is_decided = bool(choice.decided_at) or (choice.status and choice.status.value == "completed")

    # Subtitle
    subtitle_parts: list[str] = []
    if choice.status:
        subtitle_parts.append(str(choice.status).replace("_", " ").title())
    if choice.choice_type:
        subtitle_parts.append(str(choice.choice_type.value).title())
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else None

    header = PageHeader(choice.title or "Untitled Choice", subtitle=subtitle)

    # Badges
    badges: list[Any] = []
    if choice.choice_type:
        badges.append(Span(str(choice.choice_type.value).title(), cls="uk-badge"))
    if choice.priority:
        badges.append(PriorityBadge(str(choice.priority)))
    if choice.status:
        badges.append(StatusBadge(str(choice.status)))

    # Description
    desc_el = Div()
    if choice.description:
        desc_el = Div(P(choice.description, cls="uk-text-default"), cls="uk-margin")

    # Options section
    options_section = Div()
    if choice.options:
        options_section = OptionsSection(choice.options, choice.selected_option_uid)

    # Decision section (criteria, constraints, rationale)
    decision_items: list[Any] = []
    if choice.decision_rationale:
        decision_items.append(
            Div(
                Small("Rationale", cls="uk-text-muted uk-display-block"),
                P(choice.decision_rationale, cls="uk-text-default"),
            )
        )
    if choice.decision_criteria:
        criteria_list = Ul(
            *[Li(c) for c in choice.decision_criteria],
            cls="uk-list uk-list-disc",
        )
        decision_items.append(
            Div(
                Small("Criteria", cls="uk-text-muted uk-display-block"),
                criteria_list,
            )
        )
    if choice.constraints:
        constraints_list = Ul(
            *[Li(c) for c in choice.constraints],
            cls="uk-list uk-list-disc",
        )
        decision_items.append(
            Div(
                Small("Constraints", cls="uk-text-muted uk-display-block"),
                constraints_list,
            )
        )
    if choice.stakeholders:
        decision_items.append(
            Div(
                Small("Stakeholders", cls="uk-text-muted uk-display-block"),
                P(", ".join(choice.stakeholders), cls="uk-text-default"),
            )
        )
    decision_section = Div()
    if decision_items:
        decision_section = Div(
            H3("Decision Framework", cls="uk-heading-small"),
            *decision_items,
            cls="uk-margin",
        )

    # Outcome section (only if decided)
    outcome_section = Div()
    if is_decided:
        outcome_items: list[Any] = []
        if choice.satisfaction_score and choice.satisfaction_score > 0:
            filled = int(choice.satisfaction_score)
            stars = "★" * filled + "☆" * (5 - filled)
            outcome_items.append(
                Div(
                    Small("Satisfaction", cls="uk-text-muted uk-display-block"),
                    Span(stars, cls="uk-text-warning", style="font-size: 1.2rem;"),
                    Span(f" {choice.satisfaction_score}/5", cls="uk-text-muted uk-text-small"),
                )
            )
        if choice.actual_outcome:
            outcome_items.append(
                Div(
                    Small("Actual Outcome", cls="uk-text-muted uk-display-block"),
                    P(choice.actual_outcome, cls="uk-text-default"),
                )
            )
        if choice.lessons_learned:
            lessons_list = Ul(
                *[Li(lesson) for lesson in choice.lessons_learned],
                cls="uk-list uk-list-disc",
            )
            outcome_items.append(
                Div(
                    Small("Lessons Learned", cls="uk-text-muted uk-display-block"),
                    lessons_list,
                )
            )
        if outcome_items:
            outcome_section = Div(
                H3("Outcome", cls="uk-heading-small"),
                *outcome_items,
                cls="uk-margin",
            )

    # Timing
    timing_items: list[Any] = []
    if choice.decision_deadline:
        overdue = _is_deadline_past(choice) and not is_decided
        dl_cls = "uk-text-danger uk-text-bold" if overdue else ""
        timing_items.append(
            Div(
                Small("Deadline", cls="uk-text-muted uk-display-block"),
                Span(str(choice.decision_deadline)[:10], cls=dl_cls),
            )
        )
    if choice.decided_at:
        timing_items.append(
            Div(
                Small("Decided", cls="uk-text-muted uk-display-block"),
                Span(str(choice.decided_at)[:10]),
            )
        )
    if choice.created_at:
        timing_items.append(
            Div(
                Small("Created", cls="uk-text-muted uk-display-block"),
                Span(str(choice.created_at)[:10]),
            )
        )
    timing_grid = Div()
    if timing_items:
        timing_grid = Div(
            *timing_items,
            cls="uk-grid uk-grid-small uk-child-width-1-3@s uk-child-width-auto@m uk-margin",
            **{"uk-grid": "true"},
        )

    # Tags
    tags_el = Div()
    if choice.tags:
        tag_badges = [
            Span(tag, cls="uk-badge uk-badge-secondary uk-margin-small-right")
            for tag in choice.tags
        ]
        tags_el = Div(
            Small("Tags", cls="uk-text-muted uk-display-block uk-margin-small-bottom"),
            *tag_badges,
            cls="uk-margin",
        )

    # Connections
    conn_section = Div()
    if connections:
        conn_section = Div(
            H3("Connections", cls="uk-heading-small"),
            _ConnectionBadges(connections),
            cls="uk-margin",
        )

    # Lateral relationships
    relationships = EntityRelationshipsSection(
        entity_uid=choice.uid,
        entity_type="choices",
    )

    return Div(
        ActivityDomainNav("choices"),
        header,
        Div(*badges, cls="uk-flex uk-flex-wrap uk-flex-middle uk-margin-small-bottom")
        if badges
        else "",
        desc_el,
        options_section,
        decision_section,
        outcome_section,
        timing_grid,
        tags_el,
        conn_section,
        relationships,
        cls="uk-container uk-container-small",
    )


def OptionsSection(options: tuple["ChoiceOption", ...], selected_uid: str | None) -> "FT":
    """Render choice options as a visual list with selected indicator."""
    items: list[Any] = []
    for opt in options:
        is_selected = selected_uid and opt.uid == selected_uid
        icon = "check-circle" if is_selected else "circle"
        icon_cls = "uk-text-success" if is_selected else "uk-text-muted"
        text_cls = "uk-text-bold" if is_selected else ""

        opt_content: list[Any] = [
            Span(cls=f"uk-icon {icon_cls} uk-margin-small-right", **{"uk-icon": icon}),
            Span(opt.title or opt.uid, cls=text_cls),
        ]
        if is_selected:
            opt_content.append(Small(" (selected)", cls="uk-text-success"))
        if opt.description:
            opt_content.append(Small(f" — {opt.description}", cls="uk-text-muted"))

        items.append(Li(*opt_content, cls="uk-margin-small-bottom"))

    return Div(
        H3("Options", cls="uk-heading-small"),
        Ul(*items, cls="uk-list"),
        cls="uk-margin",
    )


def _ConnectionBadges(connections: list[dict[str, str]]) -> "FT":
    """Render typed connection badges for a choice's cross-domain links."""
    if not connections:
        return Span()

    conn_icons = {
        "goal": ("target", "/goals/detail?uid="),
        "habit": ("repeat", "/habits/detail?uid="),
        "principle": ("compass", "/principles/detail?uid="),
        "ku": ("atom", "/ku/get?uid="),
    }

    badges: list[Any] = []
    for conn in connections:
        target_type = conn.get("target_type", "")
        title = conn.get("title", conn.get("target_uid", "?"))
        target_uid = conn.get("target_uid", "")
        icon, base_href = conn_icons.get(target_type, ("link", "#"))
        href = f"{base_href}{target_uid}" if base_href != "#" else "#"

        badges.append(
            A(
                Span(
                    cls="uk-icon uk-margin-small-right", **{"uk-icon": f"icon: {icon}; ratio: 0.75"}
                ),
                title,
                href=href,
                cls="uk-badge uk-margin-small-right",
                style="text-decoration: none;",
            )
        )

    return Div(*badges, cls="uk-margin-small-top")


def _is_deadline_past(choice: "Choice") -> bool:
    """Check if decision deadline has passed."""
    if not choice.decision_deadline:
        return False
    try:
        if isinstance(choice.decision_deadline, (date, datetime)):
            dl = (
                choice.decision_deadline
                if isinstance(choice.decision_deadline, date)
                else choice.decision_deadline.date()
            )
            return dl < date.today()
        d = datetime.fromisoformat(str(choice.decision_deadline)).date()
        return d < date.today()
    except (ValueError, TypeError):
        return False


def _safe_id(uid: str) -> str:
    """Convert a UID to a safe HTML id attribute value."""
    return uid.replace(".", "-").replace(":", "-")


_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def filter_choices(
    choices: list["Choice"],
    status_filter: str = "pending",
    sort_by: str = "deadline",
) -> list["Choice"]:
    """Apply filters and sorting to a choice list."""
    filtered = list(choices)

    # Status filter
    if status_filter == "pending":
        filtered = [
            c
            for c in filtered
            if not c.decided_at and not (c.status and c.status.value == "completed")
        ]
    elif status_filter == "decided":
        filtered = [
            c for c in filtered if c.decided_at or (c.status and c.status.value == "completed")
        ]

    # Sort
    def by_deadline(c: Any) -> str:
        return str(c.decision_deadline or "9999-12-31")[:10]

    def by_priority(c: Any) -> int:
        return _PRIORITY_ORDER.get(str(c.priority) if c.priority else "", 4)

    def by_title(c: Any) -> str:
        return (c.title or "").lower()

    def by_created(c: Any) -> str:
        return str(c.created_at or "")

    if sort_by == "deadline":
        filtered.sort(key=by_deadline)
    elif sort_by == "priority":
        filtered.sort(key=by_priority)
    elif sort_by == "title":
        filtered.sort(key=by_title)
    elif sort_by == "created":
        filtered.sort(key=by_created, reverse=True)

    return filtered
