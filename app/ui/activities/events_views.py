"""Events UI view components.

Pure FastHTML components for rendering event data. No service calls —
routes fetch data and pass it to these components.

Usage:
    from ui.activities.events_views import EventList, EventStatsBar
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    A,
    Div,
    P,
    Small,
    Span,
)

from core.models.relationship_names import RelationshipName
from ui.activities._shared import (
    ActivityList,
    ConnectionBadges,
    ConnectionsBlock,
    MetadataField,
    PriorityBadgeDropdown,
    TagsBlock,
    safe_id,
    tag_badges,
)
from ui.components import Button, ButtonT, Card, Icon
from ui.feedback import Badge, BadgeT, PriorityBadge, StatusBadge
from ui.layout import Container, DivHStacked
from ui.patterns.page_header import PageHeader
from ui.patterns.relationships.relationship_section import EntityRelationshipsSection
from ui.patterns.stats_grid import StatItem, StatsGrid
from ui.primitives import section_label

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.models.event.event import Event


def EventStatsBar(events: list["Event"]) -> "FT":
    """Quick stats bar showing event counts."""
    total = len(events)
    upcoming = sum(1 for e in events if e.is_upcoming())
    today = sum(1 for e in events if e.is_today())
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


def EventList(
    events: list["Event"],
    connections_map: dict[str, list[dict[str, str]]] | None = None,
) -> "FT":
    """Render a list of event cards. Returns a replaceable container for HTMX."""
    return ActivityList(events, "event", EventCard, connections_map)


def EventCard(
    event: "Event",
    connections: list[dict[str, str]] | None = None,
) -> "FT":
    """Single event card with date/time, location, and connections."""
    is_completed = event.status and event.status.value == "completed"
    is_past = event.is_past()

    # Status toggle button
    new_status = "active" if is_completed else "completed"
    toggle_icon = "check" if is_completed else "calendar"
    toggle_cls = "text-green-600" if is_completed else ""

    toggle_btn = Button(
        Icon(toggle_icon, size=16, cls=f"inline {toggle_cls}"),
        hx_post=f"/api/events/{event.uid}/status",
        hx_vals=f'{{"status": "{new_status}"}}',
        hx_target=f"#event-{safe_id(event.uid)}",
        hx_swap="outerHTML",
        cls=(ButtonT.default, "rounded"),
        size="sm",
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
    badges.append(
        PriorityBadgeDropdown(
            event.uid,
            str(event.priority) if event.priority else None,
            domain="events",
            singular="event",
        )
    )
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
        elif event.is_today():
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
        tags_el = Div(*tag_badges(event.tags, limit=5), cls="mt-2")

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
        header,
        id=f"event-{safe_id(event.uid)}",
        cls=f"mb-2 p-3 {opacity}",
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
        is_past = event.is_past()
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
            section_label("Schedule"),
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
            section_label("Location"),
            *loc_items,
            cls="my-4",
        )

    # Attendees section
    attendees_section = Div()
    if event.attendee_emails:
        count = len(event.attendee_emails)
        max_str = f" / {event.max_attendees}" if event.max_attendees else ""
        attendees_section = Div(
            section_label("Attendees"),
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
            section_label("Recurrence"),
            Div(
                *rec_items,
                cls="grid grid-cols-1 sm:grid-cols-2 gap-2",
            ),
            cls="my-4",
        )

    # Milestone section. The celebrated goal is read from graph-derived
    # connections ((Event)-[:CELEBRATES_GOAL]->(Goal)), not a property.
    milestone_section = Div()
    if event.is_milestone_event:
        ms_items: list[Any] = []
        if event.milestone_type:
            ms_items.append(P(f"Type: {event.milestone_type}"))
        celebrated = next(
            (c for c in connections if c.get("rel_type") == RelationshipName.CELEBRATES_GOAL), None
        )
        if celebrated:
            goal_uid = celebrated.get("connected_uid", "")
            goal_label = celebrated.get("title") or goal_uid
            ms_items.append(
                P(
                    A(
                        f"Celebrates goal: {goal_label}",
                        href=f"/goals/detail?uid={goal_uid}",
                        cls="hover:underline text-primary",
                    ),
                )
            )
        milestone_section = Div(
            section_label("Milestone"),
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
    tags_el = TagsBlock(event.tags)

    # Connections
    conn_section = Div()
    if connections:
        conn_section = ConnectionsBlock(ConnectionBadges(connections))

    # Lateral relationships
    relationships = EntityRelationshipsSection(
        entity_uid=event.uid,
        entity_type="events",
        authoring=True,
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


def _format_time_range(event: "Event") -> str:
    """Format start_time - end_time as a string."""
    parts = []
    if event.start_time:
        parts.append(str(event.start_time)[:5])
    if event.end_time:
        parts.append(str(event.end_time)[:5])
    return " - ".join(parts)
