"""Principles UI view components.

Pure FastHTML components for rendering principle data. No service calls —
routes fetch data and pass it to these components.

Principles are a gravity well like Goals — they show incoming relationships
from tasks, habits, choices, and events that embody/express them.

Usage:
    from ui.activities.principles_views import PrincipleList, PrincipleStatsBar
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    A,
    Div,
    Li,
    P,
    Small,
    Span,
    Ul,
)

from core.models.enums.principle_enums import AlignmentLevel
from ui.activities._shared import (
    ActivityList,
    ConnectionsSection,
    ConnectionSummary,
    MetadataField,
    PriorityBadgeDropdown,
    TagsBlock,
    safe_id,
)
from ui.components import Button, ButtonT, Card, Icon
from ui.dual_track_card import DualTrackSection
from ui.feedback import Badge, BadgeT, StatusBadge
from ui.layout import Container, DivHStacked
from ui.palette import StrengthColor
from ui.patterns.page_header import PageHeader
from ui.patterns.relationships.relationship_section import EntityRelationshipsSection
from ui.patterns.stats_grid import StatItem, StatsGrid
from ui.primitives import section_label

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.models.principle.principle import Principle

# Strength ordering: Core is strongest (0), Exploring is weakest (4)
_STRENGTH_ORDER = {"core": 0, "strong": 1, "moderate": 2, "developing": 3, "exploring": 4}

_ALIGNMENT_COLORS = {
    "flourishing": "text-green-600",
    "aligned": "text-green-600",
    "mostly_aligned": "text-green-600",
    "exploring": "text-yellow-600",
    "partial": "text-yellow-600",
    "drifting": "text-destructive",
    "misaligned": "text-destructive",
    "unknown": "text-muted-foreground",
}


def PrincipleStatsBar(principles: list["Principle"]) -> "FT":
    """Quick stats bar showing principle counts."""
    total = len(principles)
    core = sum(
        1 for p in principles if p.strength and _STRENGTH_ORDER.get(p.strength.value, 5) <= 1
    )
    active = sum(
        1
        for p in principles
        if p.is_active is None or p.is_active  # Default to active
    )
    well_aligned = sum(
        1
        for p in principles
        if p.current_alignment
        and p.current_alignment.value in ("flourishing", "aligned", "mostly_aligned")
    )

    stats = [
        StatItem(label="Total", value=total, href="/principles?status=all"),
        StatItem(
            label="Core",
            value=core,
            color="primary" if core > 0 else None,
            href="/principles?strength=core",
        ),
        StatItem(label="Active", value=active, color="success", href="/principles?status=active"),
        StatItem(
            label="Well-Aligned", value=well_aligned, color="success" if well_aligned > 0 else None
        ),
    ]
    return StatsGrid(stats, cols=4)


def PrincipleList(
    principles: list["Principle"],
    connections_map: dict[str, list[dict[str, str]]] | None = None,
) -> "FT":
    """Render a list of principle cards. Returns a replaceable container for HTMX."""
    return ActivityList(principles, "principle", PrincipleCard, connections_map)


def PrincipleCard(
    principle: "Principle",
    connections: list[dict[str, str]] | None = None,
) -> "FT":
    """Single principle card with strength, category, alignment, and connections."""
    is_inactive = principle.is_active is not None and not principle.is_active

    # Toggle button (active/inactive)
    new_status = "active" if is_inactive else "archived"
    toggle_icon = "compass" if not is_inactive else "archive"
    toggle_cls = "" if not is_inactive else "text-muted-foreground"

    toggle_btn = Button(
        Icon(toggle_icon, size=16, cls=f"inline {toggle_cls}"),
        hx_post=f"/api/principles/{principle.uid}/status",
        hx_vals=f'{{"status": "{new_status}"}}',
        hx_target=f"#principle-{safe_id(principle.uid)}",
        hx_swap="outerHTML",
        cls=(ButtonT.default, "rounded"),
        size="sm",
        title=f"Mark as {new_status}",
    )

    # Title
    title_cls = "text-muted-foreground" if is_inactive else ""
    title_el = A(
        principle.title or "Untitled",
        href=f"/principles/detail?uid={principle.uid}",
        cls=f"hover:underline {title_cls}",
    )

    # Badges
    badges: list[Any] = []
    badges.append(
        PriorityBadgeDropdown(
            principle.uid,
            str(principle.priority) if principle.priority else None,
            domain="principles",
            singular="principle",
        )
    )
    if principle.strength:
        badges.append(StrengthBadge(principle.strength.value))
    if principle.principle_category:
        badges.append(
            Badge(str(principle.principle_category.value).title(), variant=BadgeT.primary)
        )
    if principle.status:
        badges.append(StatusBadge(str(principle.status)))

    # Alignment indicator
    alignment_el = Span()
    if principle.current_alignment:
        al_value = principle.current_alignment.value
        al_cls = _ALIGNMENT_COLORS.get(al_value, "text-muted-foreground")
        alignment_el = Small(
            al_value.replace("_", " ").title(),
            cls=f"{al_cls} ml-2",
        )

    # Statement preview
    statement_el = Span()
    if principle.statement:
        preview = principle.statement[:100]
        if len(principle.statement) > 100:
            preview += "..."
        statement_el = Div(
            Small(preview, cls="text-muted-foreground"),
            cls="mt-2",
        )

    # Connection count summary
    conn_summary = ConnectionSummary(connections or [])

    # Card assembly
    header = Div(
        toggle_btn,
        Div(
            DivHStacked(title_el, alignment_el, cls="flex-wrap"),
            DivHStacked(*badges, cls="flex-wrap mt-2") if badges else "",
            statement_el,
            conn_summary,
            cls="ml-2 flex-1 min-w-0",
        ),
        cls="flex items-start",
    )

    opacity = "opacity-75" if is_inactive else ""
    return Card(
        header,
        id=f"principle-{safe_id(principle.uid)}",
        cls=f"mb-2 p-3 {opacity}",
    )


def PrincipleDetailView(
    principle: "Principle",
    connections: list[dict[str, str]],
) -> "FT":
    """Full detail page for a single principle."""
    # Subtitle
    subtitle_parts: list[str] = []
    if principle.status:
        subtitle_parts.append(str(principle.status).replace("_", " ").title())
    if principle.strength:
        subtitle_parts.append(str(principle.strength.value).title())
    if principle.principle_category:
        subtitle_parts.append(str(principle.principle_category.value).title())
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else None

    header = PageHeader(principle.title or "Untitled Principle", subtitle=subtitle)

    # Badges
    badges: list[Any] = []
    if principle.strength:
        badges.append(StrengthBadge(principle.strength.value))
    if principle.principle_category:
        badges.append(
            Badge(str(principle.principle_category.value).title(), variant=BadgeT.primary)
        )
    if principle.current_alignment:
        al_value = principle.current_alignment.value
        al_cls = _ALIGNMENT_COLORS.get(al_value, "text-muted-foreground")
        badges.append(Badge(al_value.replace("_", " ").title(), variant=BadgeT.primary, cls=al_cls))
    if principle.status:
        badges.append(StatusBadge(str(principle.status)))

    # Statement (prominent)
    statement_section = Div()
    if principle.statement:
        statement_section = Div(
            P(
                principle.statement,
                cls="text-lg",
                style="font-style: italic; border-left: 3px solid hsl(var(--primary)); padding-left: 1rem;",
            ),
            cls="my-4",
        )

    # Description
    desc_el = Div()
    if principle.description:
        desc_el = Div(P(principle.description), cls="my-4")

    # Philosophical context
    philo_items: list[Any] = []
    if principle.tradition:
        philo_items.append(MetadataField("Tradition", P(principle.tradition)))
    if principle.original_source:
        philo_items.append(MetadataField("Original Source", P(principle.original_source)))
    if principle.personal_interpretation:
        philo_items.append(
            MetadataField(
                "Personal Interpretation",
                P(principle.personal_interpretation),
            )
        )
    philo_section = Div()
    if philo_items:
        philo_section = Div(
            section_label("Philosophical Context"),
            *philo_items,
            cls="my-4",
        )

    # Expressions & Key Behaviors
    expressions_section = Div()
    expr_items: list[Any] = []
    if principle.expressions:
        for expr in principle.expressions:
            expr_text = getattr(expr, "text", None) or str(expr)
            expr_items.append(Li(expr_text))
    if expr_items:
        expressions_section = Div(
            section_label("Expressions"),
            Ul(*expr_items, cls="list-disc pl-6"),
            cls="my-4",
        )

    behaviors_section = Div()
    if principle.key_behaviors:
        behavior_items = [Li(b) for b in principle.key_behaviors]
        behaviors_section = Div(
            section_label("Key Behaviors"),
            Ul(*behavior_items, cls="list-disc pl-6"),
            cls="my-4",
        )

    # Alignment section
    alignment_section = Div()
    if principle.current_alignment:
        al_value = principle.current_alignment.value
        al_cls = _ALIGNMENT_COLORS.get(al_value, "text-muted-foreground")
        al_items: list[Any] = [
            MetadataField(
                "Current Alignment",
                Span(al_value.replace("_", " ").title(), cls=f"font-bold {al_cls}"),
            )
        ]
        if principle.last_review_date:
            al_items.append(MetadataField("Last Reviewed", Span(str(principle.last_review_date))))
        # Alignment history
        if principle.alignment_history:
            history_items = []
            for assessment in principle.alignment_history[-5:]:  # Show last 5
                al_level = getattr(assessment, "alignment_level", None) or str(assessment)
                assessed_at = getattr(assessment, "assessed_date", "")
                h_cls = _ALIGNMENT_COLORS.get(str(al_level), "text-muted-foreground")
                history_items.append(
                    Li(
                        Span(str(al_level).replace("_", " ").title(), cls=h_cls),
                        Small(f" — {assessed_at}", cls="text-muted-foreground")
                        if assessed_at
                        else "",
                    )
                )
            if history_items:
                al_items.append(MetadataField("History", Ul(*history_items, cls="space-y-1")))
        alignment_section = Div(
            section_label("Alignment"),
            *al_items,
            cls="my-4",
        )

    # Conflicts & Tensions
    conflicts_section = Div()
    conflict_items: list[Any] = []
    if principle.potential_conflicts:
        conflict_items.append(
            MetadataField(
                "Potential Conflicts",
                Ul(*[Li(c) for c in principle.potential_conflicts], cls="list-disc pl-6"),
            )
        )
    if principle.resolution_strategies:
        conflict_items.append(
            MetadataField(
                "Resolution Strategies",
                Ul(*[Li(s) for s in principle.resolution_strategies], cls="list-disc pl-6"),
            )
        )
    if conflict_items:
        conflicts_section = Div(
            section_label("Conflicts & Tensions"),
            *conflict_items,
            cls="my-4",
        )

    # Personal reflection
    reflection_items: list[Any] = []
    if principle.origin_story:
        reflection_items.append(MetadataField("Origin Story", P(principle.origin_story)))
    if principle.evolution_notes:
        reflection_items.append(MetadataField("Evolution Notes", P(principle.evolution_notes)))
    reflection_section = Div()
    if reflection_items:
        reflection_section = Div(
            section_label("Personal Reflection"),
            *reflection_items,
            cls="my-4",
        )

    # Metadata grid
    meta_items: list[Any] = []
    if principle.adopted_date:
        meta_items.append(MetadataField("Adopted", Span(str(principle.adopted_date))))
    if principle.principle_source:
        meta_items.append(
            MetadataField("Source", Span(str(principle.principle_source.value).title()))
        )
    if principle.created_at:
        meta_items.append(MetadataField("Created", Span(str(principle.created_at)[:10])))
    meta_grid = Div()
    if meta_items:
        meta_grid = Div(
            *meta_items,
            cls="grid grid-cols-1 sm:grid-cols-3 gap-2 my-4",
        )

    # Tags
    tags_el = TagsBlock(principle.tags)

    # Connections — gravity well (incoming relationships)
    conn_section = Div()
    if connections:
        conn_section = ConnectionsSection(connections, _CONNECTION_LABELS)

    # Dual-track self-assessment (perception gap + trend) — ADR-030
    dual_track_section = DualTrackSection(
        domain="principles",
        entity_uid=principle.uid,
        level_enum=AlignmentLevel,
        label="Alignment",
        prompt="How well do you feel you're living by this principle?",
        checkins=principle.dual_track_checkins,
    )

    # Lateral relationships
    relationships = EntityRelationshipsSection(
        entity_uid=principle.uid,
        entity_type="principles",
        authoring=True,
    )

    return Container(
        header,
        DivHStacked(*badges, cls="flex-wrap mb-2") if badges else "",
        statement_section,
        desc_el,
        philo_section,
        expressions_section,
        behaviors_section,
        alignment_section,
        conflicts_section,
        reflection_section,
        meta_grid,
        tags_el,
        conn_section,
        dual_track_section,
        relationships,
        size="3xl",
    )


# ConnectionsSection labels (gravity well view): connected_type -> (label, icon, href prefix).
_CONNECTION_LABELS: dict[str, tuple[str, str, str]] = {
    "task": ("Tasks embodying this principle", "check-square", "/tasks/detail?uid="),
    "habit": ("Habits reinforcing this principle", "repeat", "/habits/detail?uid="),
    "goal": ("Goals aligned with this principle", "target", "/goals/detail?uid="),
    "event": ("Events demonstrating this principle", "calendar", "/events/detail?uid="),
    "choice": ("Choices expressing this principle", "git-branch", "/choices/detail?uid="),
    "ku": ("Knowledge connected", "atom", "/explore/ku/"),
}


def StrengthBadge(strength: str) -> "FT":
    """Color-coded badge for PrincipleStrength."""
    hex_color = StrengthColor.for_level(strength)
    style = f"background-color: {hex_color}; color: white;"
    return Badge(strength.title(), variant=BadgeT.primary, style=style)
