"""Events UI view components.

Pure FastHTML components for rendering event data. No service calls —
routes fetch data and pass it to these components.

Usage:
    from ui.activities.events_views import EventList, EventFilterBar, EventStatsBar
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
    Option,
    P,
    Select,
    Small,
    Span,
)

from ui.feedback import PriorityBadge, StatusBadge
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader
from ui.patterns.relationships.relationship_section import EntityRelationshipsSection
from ui.patterns.stats_grid import StatItem, StatsGrid

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.models.event.event import Event


def EventStatsBar(events: list["Event"]) -> "FT":
    """Quick stats bar showing event counts."""
    total = len(events)
    upcoming = sum(1 for e in events if _is_upcoming(e))
    today = sum(1 for e in events if _is_today(e))
    completed = sum(1 for e in events if e.status and e.status.value == "completed")

    stats = [
        StatItem(label="Total", value=total),
        StatItem(label="Upcoming", value=upcoming, color="primary"),
        StatItem(label="Today", value=today, color="warning" if today > 0 else None),
        StatItem(label="Completed", value=completed, color="success"),
    ]
    return StatsGrid(stats, cols=4)


def EventFilterBar(
    status_filter: str = "upcoming",
    sort_by: str = "date",
) -> "FT":
    """Filter and sort controls for the event list. HTMX-powered."""
    return Form(
        Div(
            Div(
                Label("Status", cls="uk-form-label"),
                Select(
                    Option("Upcoming", value="upcoming", selected=status_filter == "upcoming"),
                    Option("Completed", value="completed", selected=status_filter == "completed"),
                    Option("All", value="all", selected=status_filter == "all"),
                    name="status",
                    cls="uk-select uk-form-small",
                ),
                cls="uk-form-controls",
            ),
            Div(
                Label("Sort", cls="uk-form-label"),
                Select(
                    Option("Date", value="date", selected=sort_by == "date"),
                    Option("Title", value="title", selected=sort_by == "title"),
                    Option("Recently Created", value="created", selected=sort_by == "created"),
                    name="sort_by",
                    cls="uk-select uk-form-small",
                ),
                cls="uk-form-controls",
            ),
            cls="uk-grid uk-grid-small uk-child-width-1-2@s uk-child-width-auto@m",
            **{"uk-grid": "true"},
        ),
        hx_get="/events/list-fragment",
        hx_target="#event-list",
        hx_trigger="change",
        hx_include="[name]",
        cls="uk-margin-bottom",
    )


def EventList(
    events: list["Event"],
    connections_map: dict[str, list[dict[str, str]]] | None = None,
) -> "FT":
    """Render a list of event cards. Returns a replaceable container for HTMX."""
    if not events:
        return Div(
            EmptyState(
                title="No events found",
                description="Upload YAML files to add events, or adjust your filters.",
                action_text="Upload Events",
                action_href="/upload",
            ),
            id="event-list",
        )

    cards = [
        EventCard(event, connections_map.get(event.uid, []) if connections_map else [])
        for event in events
    ]
    return Div(*cards, id="event-list", cls="uk-margin-top")


def EventCard(
    event: "Event",
    connections: list[dict[str, str]] | None = None,
) -> "FT":
    """Single event card with date/time, location, and connections."""
    is_completed = event.status and event.status.value == "completed"
    is_past = _is_past(event)

    # Status toggle button
    new_status = "active" if is_completed else "completed"
    toggle_icon = "check" if is_completed else "calendar"
    toggle_cls = "uk-text-success" if is_completed else ""

    toggle_btn = Button(
        Span(cls=f"uk-icon {toggle_cls}", **{"uk-icon": toggle_icon}),
        hx_post=f"/api/events/{event.uid}/status",
        hx_vals=f'{{"status": "{new_status}"}}',
        hx_target=f"#event-{_safe_id(event.uid)}",
        hx_swap="outerHTML",
        cls="uk-button uk-button-default uk-button-small uk-border-rounded",
        title=f"Mark as {new_status}",
    )

    # Title
    title_cls = "uk-text-muted uk-text-line-through" if is_completed else ""
    title_el = A(
        event.title or "Untitled",
        href=f"/events/detail?uid={event.uid}",
        cls=f"uk-link-text {title_cls}",
    )

    # Badges
    badges: list[Any] = []
    if event.event_type:
        badges.append(Span(str(event.event_type).title(), cls="uk-badge"))
    if event.is_milestone_event:
        badges.append(Span("Milestone", cls="uk-badge uk-badge-warning"))
    if event.is_online:
        badges.append(Span("Online", cls="uk-badge uk-badge-primary"))
    if event.priority:
        badges.append(PriorityBadge(str(event.priority)))
    if event.status:
        badges.append(StatusBadge(str(event.status)))

    # Date and time
    date_el = Span()
    if event.event_date:
        time_str = _format_time_range(event)
        date_str = str(event.event_date)
        if time_str:
            date_str += f" {time_str}"
        date_cls = "uk-text-muted"
        if is_past and not is_completed:
            date_cls = "uk-text-danger"
        elif _is_today(event):
            date_cls = "uk-text-warning uk-text-bold"
        date_el = Small(date_str, cls=date_cls)

    # Location
    loc_el = Span()
    if event.location:
        loc_el = Small(event.location, cls="uk-text-muted uk-margin-small-left")
    elif event.is_online and event.meeting_url:
        loc_el = Small("Online", cls="uk-text-primary uk-margin-small-left")

    # Tags
    tags_el = Span()
    if event.tags:
        tag_badges = [
            Span(tag, cls="uk-badge uk-badge-secondary uk-margin-small-right")
            for tag in event.tags[:5]
        ]
        tags_el = Div(*tag_badges, cls="uk-margin-small-top")

    # Connection badges
    conn_el = _ConnectionBadges(connections or [])

    # Card assembly
    header = Div(
        toggle_btn,
        Div(
            Div(title_el, loc_el, cls="uk-flex uk-flex-middle uk-flex-wrap"),
            Div(*badges, cls="uk-flex uk-flex-wrap uk-flex-middle uk-margin-small-top")
            if badges
            else "",
            date_el,
            tags_el,
            conn_el,
            cls="uk-margin-small-left uk-width-expand",
        ),
        cls="uk-flex uk-flex-top",
    )

    opacity = "uk-opacity-75" if is_completed else ""
    return Div(
        header,
        id=f"event-{_safe_id(event.uid)}",
        cls=f"uk-card uk-card-default uk-card-body uk-card-small uk-margin-small-bottom {opacity}",
    )


def EventDetailView(
    event: "Event",
    connections: list[dict[str, str]],
) -> "FT":
    """Full detail page for a single event."""
    # Subtitle
    subtitle_parts: list[str] = []
    if event.status:
        subtitle_parts.append(str(event.status).replace("_", " ").title())
    if event.event_type:
        subtitle_parts.append(str(event.event_type).title())
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else None

    header = PageHeader(event.title or "Untitled Event", subtitle=subtitle)

    # Badges
    badges: list[Any] = []
    if event.event_type:
        badges.append(Span(str(event.event_type).title(), cls="uk-badge"))
    if event.is_milestone_event:
        badges.append(Span("Milestone", cls="uk-badge uk-badge-warning"))
    if event.is_online:
        badges.append(Span("Online", cls="uk-badge uk-badge-primary"))
    if event.priority:
        badges.append(PriorityBadge(str(event.priority)))
    if event.status:
        badges.append(StatusBadge(str(event.status)))

    # Description
    desc_el = Div()
    if event.description:
        desc_el = Div(P(event.description, cls="uk-text-default"), cls="uk-margin")

    # Schedule section
    sched_items: list[Any] = []
    if event.event_date:
        is_past = _is_past(event)
        date_cls = (
            "uk-text-danger"
            if is_past and not (event.status and event.status.value == "completed")
            else ""
        )
        sched_items.append(
            Div(
                Small("Date", cls="uk-text-muted uk-display-block"),
                Span(str(event.event_date), cls=date_cls),
            )
        )
    time_str = _format_time_range(event)
    if time_str:
        sched_items.append(
            Div(
                Small("Time", cls="uk-text-muted uk-display-block"),
                Span(time_str),
            )
        )
    if event.duration_minutes:
        sched_items.append(
            Div(
                Small("Duration", cls="uk-text-muted uk-display-block"),
                Span(f"{event.duration_minutes} min"),
            )
        )
    sched_section = Div()
    if sched_items:
        sched_section = Div(
            H3("Schedule", cls="uk-heading-small"),
            Div(
                *sched_items,
                cls="uk-grid uk-grid-small uk-child-width-1-3@s uk-child-width-auto@m",
                **{"uk-grid": "true"},
            ),
            cls="uk-margin",
        )

    # Location section
    loc_items: list[Any] = []
    if event.location:
        loc_items.append(
            Div(
                Small("Location", cls="uk-text-muted uk-display-block"),
                Span(event.location),
            )
        )
    if event.meeting_url:
        loc_items.append(
            Div(
                Small("Meeting URL", cls="uk-text-muted uk-display-block"),
                A(
                    event.meeting_url,
                    href=event.meeting_url,
                    cls="uk-link",
                    target="_blank",
                    rel="noopener",
                ),
            )
        )
    if event.is_online and not event.location:
        loc_items.append(
            Div(
                Small("Format", cls="uk-text-muted uk-display-block"),
                Span("Online", cls="uk-text-primary"),
            )
        )
    loc_section = Div()
    if loc_items:
        loc_section = Div(
            H3("Location", cls="uk-heading-small"),
            *loc_items,
            cls="uk-margin",
        )

    # Attendees section
    attendees_section = Div()
    if event.attendee_emails:
        count = len(event.attendee_emails)
        max_str = f" / {event.max_attendees}" if event.max_attendees else ""
        attendees_section = Div(
            H3("Attendees", cls="uk-heading-small"),
            P(f"{count} attendee{'s' if count != 1 else ''}{max_str}", cls="uk-text-default"),
            cls="uk-margin",
        )

    # Recurrence section
    recurrence_section = Div()
    if event.recurrence_pattern:
        rec_items: list[Any] = [
            Div(
                Small("Pattern", cls="uk-text-muted uk-display-block"),
                Span(str(event.recurrence_pattern)),
            )
        ]
        if event.recurrence_end_date:
            rec_items.append(
                Div(
                    Small("Ends", cls="uk-text-muted uk-display-block"),
                    Span(str(event.recurrence_end_date)),
                )
            )
        recurrence_section = Div(
            H3("Recurrence", cls="uk-heading-small"),
            Div(
                *rec_items,
                cls="uk-grid uk-grid-small uk-child-width-1-2@s",
                **{"uk-grid": "true"},
            ),
            cls="uk-margin",
        )

    # Milestone section
    milestone_section = Div()
    if event.is_milestone_event:
        ms_items: list[Any] = []
        if event.milestone_type:
            ms_items.append(P(f"Type: {event.milestone_type}", cls="uk-text-default"))
        if event.milestone_celebration_for_goal:
            ms_items.append(
                P(
                    A(
                        f"Celebrates goal: {event.milestone_celebration_for_goal}",
                        href=f"/goals/detail?uid={event.milestone_celebration_for_goal}",
                        cls="uk-link",
                    ),
                    cls="uk-text-default",
                )
            )
        milestone_section = Div(
            H3("Milestone", cls="uk-heading-small"),
            *ms_items,
            cls="uk-margin",
        )

    # Metadata grid
    meta_items: list[Any] = []
    if event.created_at:
        meta_items.append(
            Div(
                Small("Created", cls="uk-text-muted uk-display-block"),
                Span(str(event.created_at)[:10]),
            )
        )
    meta_grid = Div()
    if meta_items:
        meta_grid = Div(
            *meta_items,
            cls="uk-grid uk-grid-small uk-child-width-1-2@s uk-child-width-1-4@m uk-margin",
            **{"uk-grid": "true"},
        )

    # Tags
    tags_el = Div()
    if event.tags:
        tag_badges = [
            Span(tag, cls="uk-badge uk-badge-secondary uk-margin-small-right") for tag in event.tags
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
        entity_uid=event.uid,
        entity_type="events",
    )

    return Div(
        header,
        Div(*badges, cls="uk-flex uk-flex-wrap uk-flex-middle uk-margin-small-bottom")
        if badges
        else "",
        desc_el,
        sched_section,
        loc_section,
        attendees_section,
        recurrence_section,
        milestone_section,
        meta_grid,
        tags_el,
        conn_section,
        relationships,
        cls="uk-container uk-container-small",
    )


def _ConnectionBadges(connections: list[dict[str, str]]) -> "FT":
    """Render typed connection badges for an event's cross-domain links."""
    if not connections:
        return Span()

    conn_icons = {
        "goal": ("target", "/goals/detail?uid="),
        "habit": ("repeat", "/habits/detail?uid="),
        "ku": ("atom", "/ku/get?uid="),
        "principle": ("compass", "/principles/detail?uid="),
        "path_step": ("list", "#"),
        "learning_path": ("map", "#"),
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


def _is_upcoming(event: "Event") -> bool:
    """Check if an event is in the future and not completed."""
    if event.status and event.status.value == "completed":
        return False
    if not event.event_date:
        return True  # No date = treat as upcoming
    try:
        if isinstance(event.event_date, date):
            return event.event_date >= date.today()
        d = datetime.fromisoformat(str(event.event_date)).date()
        return d >= date.today()
    except (ValueError, TypeError):
        return True


def _is_today(event: "Event") -> bool:
    """Check if an event is scheduled for today."""
    if not event.event_date:
        return False
    try:
        if isinstance(event.event_date, date):
            return event.event_date == date.today()
        d = datetime.fromisoformat(str(event.event_date)).date()
        return d == date.today()
    except (ValueError, TypeError):
        return False


def _is_past(event: "Event") -> bool:
    """Check if an event date is in the past."""
    if not event.event_date:
        return False
    try:
        if isinstance(event.event_date, date):
            return event.event_date < date.today()
        d = datetime.fromisoformat(str(event.event_date)).date()
        return d < date.today()
    except (ValueError, TypeError):
        return False


def _format_time_range(event: "Event") -> str:
    """Format start_time - end_time as a string."""
    parts = []
    if event.start_time:
        parts.append(str(event.start_time)[:5])
    if event.end_time:
        parts.append(str(event.end_time)[:5])
    return " - ".join(parts)


def _safe_id(uid: str) -> str:
    """Convert a UID to a safe HTML id attribute value."""
    return uid.replace(".", "-").replace(":", "-")


def filter_events(
    events: list["Event"],
    status_filter: str = "upcoming",
    sort_by: str = "date",
) -> list["Event"]:
    """Apply filters and sorting to an event list."""
    filtered = list(events)

    # Status filter
    if status_filter == "upcoming":
        filtered = [e for e in filtered if _is_upcoming(e)]
    elif status_filter == "completed":
        filtered = [e for e in filtered if e.status and e.status.value == "completed"]

    # Sort
    if sort_by == "date":
        filtered.sort(key=lambda e: str(e.event_date or "9999-12-31"))
    elif sort_by == "title":
        filtered.sort(key=lambda e: (e.title or "").lower())
    elif sort_by == "created":
        filtered.sort(key=lambda e: str(e.created_at or ""), reverse=True)

    return filtered
