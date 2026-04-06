"""Events UI view components.

Pure FastHTML components for rendering event data. No service calls —
routes fetch data and pass it to these components.

Usage:
    from ui.activities.events_views import EventList, EVENT_FILTER_CONFIG, EventStatsBar
"""

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    A,
    Div,
    P,
    Small,
    Span,
)
from monsterui.franken import UkIcon  # type: ignore[import-untyped]

from ui.activities._shared import ConnectionBadges, MetadataField, safe_id
from ui.activities.filter_bar import FilterBarConfig, FilterSelect
from ui.buttons import Button, ButtonT
from ui.cards import Card, CardBody
from ui.feedback import Badge, BadgeT, PriorityBadge, StatusBadge
from ui.layout import Container, DivHStacked
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader
from ui.patterns.relationships.relationship_section import EntityRelationshipsSection
from ui.patterns.stats_grid import StatItem, StatsGrid
from ui.text import SectionTitle

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
        StatItem(label="Total", value=total, href="/events?status=all"),
        StatItem(label="Upcoming", value=upcoming, color="primary", href="/events?status=upcoming"),
        StatItem(
            label="Today",
            value=today,
            color="warning" if today > 0 else None,
            href="/events?status=today",
        ),
        StatItem(
            label="Completed", value=completed, color="success", href="/events?status=completed"
        ),
    ]
    return StatsGrid(stats, cols=4)


EVENT_FILTER_CONFIG = FilterBarConfig(
    fragment_url="/events/list-fragment",
    list_target_id="event-list",
    filters=[
        FilterSelect(
            name="status",
            label="Status",
            options=[
                ("Upcoming", "upcoming"),
                ("Today", "today"),
                ("Completed", "completed"),
                ("All", "all"),
            ],
            default="upcoming",
        ),
    ],
    sort_options=[
        ("Date", "date"),
        ("Title", "title"),
        ("Recently Created", "created"),
    ],
    sort_default="date",
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
    return Div(*cards, id="event-list", cls="mt-4 space-y-3")


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
    toggle_cls = "text-green-600" if is_completed else ""

    toggle_btn = Button(
        UkIcon(toggle_icon, height=16, width=16, cls=f"inline {toggle_cls}"),
        hx_post=f"/api/events/{event.uid}/status",
        hx_vals=f'{{"status": "{new_status}"}}',
        hx_target=f"#event-{safe_id(event.uid)}",
        hx_swap="outerHTML",
        variant=ButtonT.neutral,
        size="sm",
        cls="rounded",
        title=f"Mark as {new_status}",
    )

    # Title
    title_cls = "text-muted-foreground line-through" if is_completed else ""
    title_el = A(
        event.title or "Untitled",
        href=f"/events/detail?uid={event.uid}",
        cls=f"hover:underline {title_cls}",
    )

    # Badges
    badges: list[Any] = []
    if event.event_type:
        badges.append(Badge(str(event.event_type).title(), variant=BadgeT.primary))
    if event.is_milestone_event:
        badges.append(Badge("Milestone", variant=BadgeT.warning))
    if event.is_online:
        badges.append(Badge("Online", variant=BadgeT.primary))
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
        date_cls = "text-muted-foreground"
        if is_past and not is_completed:
            date_cls = "text-destructive"
        elif _is_today(event):
            date_cls = "text-yellow-600 font-bold"
        date_el = Small(date_str, cls=date_cls)

    # Location
    loc_el = Span()
    if event.location:
        loc_el = Small(event.location, cls="text-muted-foreground ml-2")
    elif event.is_online and event.meeting_url:
        loc_el = Small("Online", cls="text-primary ml-2")

    # Tags
    tags_el = Span()
    if event.tags:
        tag_badges = [Badge(tag, variant=BadgeT.secondary, cls="mr-2") for tag in event.tags[:5]]
        tags_el = Div(*tag_badges, cls="mt-2")

    # Connection badges
    conn_el = ConnectionBadges(connections or [])

    # Card assembly
    header = Div(
        toggle_btn,
        Div(
            DivHStacked(title_el, loc_el, cls="flex-wrap"),
            DivHStacked(*badges, cls="flex-wrap mt-2") if badges else "",
            date_el,
            tags_el,
            conn_el,
            cls="ml-2 flex-1 min-w-0",
        ),
        cls="flex items-start",
    )

    opacity = "opacity-75" if is_completed else ""
    return Card(
        CardBody(header, cls="p-3"),
        id=f"event-{safe_id(event.uid)}",
        cls=f"mb-2 {opacity}",
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
        badges.append(Badge(str(event.event_type).title(), variant=BadgeT.primary))
    if event.is_milestone_event:
        badges.append(Badge("Milestone", variant=BadgeT.warning))
    if event.is_online:
        badges.append(Badge("Online", variant=BadgeT.primary))
    if event.priority:
        badges.append(PriorityBadge(str(event.priority)))
    if event.status:
        badges.append(StatusBadge(str(event.status)))

    # Description
    desc_el = Div()
    if event.description:
        desc_el = Div(P(event.description), cls="my-4")

    # Schedule section
    sched_items: list[Any] = []
    if event.event_date:
        is_past = _is_past(event)
        date_cls = (
            "text-destructive"
            if is_past and not (event.status and event.status.value == "completed")
            else ""
        )
        sched_items.append(MetadataField("Date", Span(str(event.event_date), cls=date_cls)))
    time_str = _format_time_range(event)
    if time_str:
        sched_items.append(MetadataField("Time", Span(time_str)))
    if event.duration_minutes:
        sched_items.append(MetadataField("Duration", Span(f"{event.duration_minutes} min")))
    sched_section = Div()
    if sched_items:
        sched_section = Div(
            SectionTitle("Schedule"),
            Div(
                *sched_items,
                cls="grid grid-cols-1 sm:grid-cols-3 gap-2",
            ),
            cls="my-4",
        )

    # Location section
    loc_items: list[Any] = []
    if event.location:
        loc_items.append(MetadataField("Location", Span(event.location)))
    if event.meeting_url:
        loc_items.append(
            MetadataField(
                "Meeting URL",
                A(
                    event.meeting_url,
                    href=event.meeting_url,
                    cls="hover:underline text-primary",
                    target="_blank",
                    rel="noopener",
                ),
            )
        )
    if event.is_online and not event.location:
        loc_items.append(MetadataField("Format", Span("Online", cls="text-primary")))
    loc_section = Div()
    if loc_items:
        loc_section = Div(
            SectionTitle("Location"),
            *loc_items,
            cls="my-4",
        )

    # Attendees section
    attendees_section = Div()
    if event.attendee_emails:
        count = len(event.attendee_emails)
        max_str = f" / {event.max_attendees}" if event.max_attendees else ""
        attendees_section = Div(
            SectionTitle("Attendees"),
            P(f"{count} attendee{'s' if count != 1 else ''}{max_str}"),
            cls="my-4",
        )

    # Recurrence section
    recurrence_section = Div()
    if event.recurrence_pattern:
        rec_items: list[Any] = [MetadataField("Pattern", Span(str(event.recurrence_pattern)))]
        if event.recurrence_end_date:
            rec_items.append(MetadataField("Ends", Span(str(event.recurrence_end_date))))
        recurrence_section = Div(
            SectionTitle("Recurrence"),
            Div(
                *rec_items,
                cls="grid grid-cols-1 sm:grid-cols-2 gap-2",
            ),
            cls="my-4",
        )

    # Milestone section
    milestone_section = Div()
    if event.is_milestone_event:
        ms_items: list[Any] = []
        if event.milestone_type:
            ms_items.append(P(f"Type: {event.milestone_type}"))
        if event.milestone_celebration_for_goal:
            ms_items.append(
                P(
                    A(
                        f"Celebrates goal: {event.milestone_celebration_for_goal}",
                        href=f"/goals/detail?uid={event.milestone_celebration_for_goal}",
                        cls="hover:underline text-primary",
                    ),
                )
            )
        milestone_section = Div(
            SectionTitle("Milestone"),
            *ms_items,
            cls="my-4",
        )

    # Metadata grid
    meta_items: list[Any] = []
    if event.created_at:
        meta_items.append(MetadataField("Created", Span(str(event.created_at)[:10])))
    meta_grid = Div()
    if meta_items:
        meta_grid = Div(
            *meta_items,
            cls="grid grid-cols-2 sm:grid-cols-4 gap-2 my-4",
        )

    # Tags
    tags_el = Div()
    if event.tags:
        tag_badges = [Badge(tag, variant=BadgeT.secondary, cls="mr-2") for tag in event.tags]
        tags_el = Div(
            Small("Tags", cls="text-muted-foreground block mb-2"),
            *tag_badges,
            cls="my-4",
        )

    # Connections
    conn_section = Div()
    if connections:
        conn_section = Div(
            SectionTitle("Connections"),
            ConnectionBadges(connections),
            cls="my-4",
        )

    # Lateral relationships
    relationships = EntityRelationshipsSection(
        entity_uid=event.uid,
        entity_type="events",
    )

    return Container(
        header,
        DivHStacked(*badges, cls="flex-wrap mb-2") if badges else "",
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
        size="3xl",
    )


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
    elif status_filter == "today":
        filtered = [e for e in filtered if _is_today(e)]
    elif status_filter == "completed":
        filtered = [e for e in filtered if e.status and e.status.value == "completed"]

    # Sort
    def by_date(e: Any) -> str:
        return str(e.event_date or "9999-12-31")

    def by_title(e: Any) -> str:
        return (e.title or "").lower()

    def by_created(e: Any) -> str:
        return str(e.created_at or "")

    if sort_by == "date":
        filtered.sort(key=by_date)
    elif sort_by == "title":
        filtered.sort(key=by_title)
    elif sort_by == "created":
        filtered.sort(key=by_created, reverse=True)

    return filtered
