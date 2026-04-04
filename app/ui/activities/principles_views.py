"""Principles UI view components.

Pure FastHTML components for rendering principle data. No service calls —
routes fetch data and pass it to these components.

Principles are a gravity well like Goals — they show incoming relationships
from tasks, habits, choices, and events that embody/express them.

Usage:
    from ui.activities.principles_views import PrincipleList, PrincipleFilterBar, PrincipleStatsBar
"""

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

from ui.activities._shared import ConnectionSummary, safe_id
from ui.feedback import StatusBadge
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader
from ui.patterns.relationships.relationship_section import EntityRelationshipsSection
from ui.patterns.stats_grid import StatItem, StatsGrid

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.models.principle.principle import Principle

# Strength ordering: Core is strongest (0), Exploring is weakest (4)
_STRENGTH_ORDER = {"core": 0, "strong": 1, "moderate": 2, "developing": 3, "exploring": 4}

_STRENGTH_COLORS = {
    "core": "background-color: #7C3AED; color: white;",
    "strong": "background-color: #2563EB; color: white;",
    "moderate": "background-color: #0891B2; color: white;",
    "developing": "background-color: #059669; color: white;",
    "exploring": "background-color: #6B7280; color: white;",
}

_ALIGNMENT_COLORS = {
    "flourishing": "uk-text-success",
    "aligned": "uk-text-success",
    "mostly_aligned": "uk-text-success",
    "exploring": "uk-text-warning",
    "partial": "uk-text-warning",
    "drifting": "uk-text-danger",
    "misaligned": "uk-text-danger",
    "unknown": "uk-text-muted",
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


def PrincipleFilterBar(
    status_filter: str = "active",
    category_filter: str = "all",
    strength_filter: str = "all",
    sort_by: str = "strength",
) -> "FT":
    """Filter and sort controls for the principle list. HTMX-powered."""
    return Form(
        Div(
            Div(
                Label("Status", cls="uk-form-label"),
                Select(
                    Option("Active", value="active", selected=status_filter == "active"),
                    Option("All", value="all", selected=status_filter == "all"),
                    name="status",
                    cls="uk-select uk-form-small",
                ),
                cls="uk-form-controls",
            ),
            Div(
                Label("Category", cls="uk-form-label"),
                Select(
                    Option("All", value="all", selected=category_filter == "all"),
                    Option("Spiritual", value="spiritual", selected=category_filter == "spiritual"),
                    Option("Ethical", value="ethical", selected=category_filter == "ethical"),
                    Option(
                        "Relational", value="relational", selected=category_filter == "relational"
                    ),
                    Option("Personal", value="personal", selected=category_filter == "personal"),
                    Option(
                        "Professional",
                        value="professional",
                        selected=category_filter == "professional",
                    ),
                    Option(
                        "Intellectual",
                        value="intellectual",
                        selected=category_filter == "intellectual",
                    ),
                    Option("Health", value="health", selected=category_filter == "health"),
                    Option("Creative", value="creative", selected=category_filter == "creative"),
                    name="category",
                    cls="uk-select uk-form-small",
                ),
                cls="uk-form-controls",
            ),
            Div(
                Label("Strength", cls="uk-form-label"),
                Select(
                    Option("All", value="all", selected=strength_filter == "all"),
                    Option("Core", value="core", selected=strength_filter == "core"),
                    Option("Strong", value="strong", selected=strength_filter == "strong"),
                    Option("Moderate", value="moderate", selected=strength_filter == "moderate"),
                    Option(
                        "Developing", value="developing", selected=strength_filter == "developing"
                    ),
                    Option("Exploring", value="exploring", selected=strength_filter == "exploring"),
                    name="strength",
                    cls="uk-select uk-form-small",
                ),
                cls="uk-form-controls",
            ),
            Div(
                Label("Sort", cls="uk-form-label"),
                Select(
                    Option("Strength", value="strength", selected=sort_by == "strength"),
                    Option("Name", value="name", selected=sort_by == "name"),
                    Option("Recently Created", value="created", selected=sort_by == "created"),
                    name="sort_by",
                    cls="uk-select uk-form-small",
                ),
                cls="uk-form-controls",
            ),
            cls="uk-grid uk-grid-small uk-child-width-1-4@s uk-child-width-auto@m",
            **{"uk-grid": "true"},
        ),
        hx_get="/principles/list-fragment",
        hx_target="#principle-list",
        hx_trigger="change",
        hx_include="[name]",
        cls="uk-margin-bottom",
    )


def PrincipleList(
    principles: list["Principle"],
    connections_map: dict[str, list[dict[str, str]]] | None = None,
) -> "FT":
    """Render a list of principle cards. Returns a replaceable container for HTMX."""
    if not principles:
        return Div(
            EmptyState(
                title="No principles found",
                description="Upload YAML files to add principles, or adjust your filters.",
                action_text="Upload Principles",
                action_href="/upload",
            ),
            id="principle-list",
        )

    cards = [
        PrincipleCard(principle, connections_map.get(principle.uid, []) if connections_map else [])
        for principle in principles
    ]
    return Div(*cards, id="principle-list", cls="uk-margin-top")


def PrincipleCard(
    principle: "Principle",
    connections: list[dict[str, str]] | None = None,
) -> "FT":
    """Single principle card with strength, category, alignment, and connections."""
    is_inactive = principle.is_active is not None and not principle.is_active

    # Toggle button (active/inactive)
    new_status = "active" if is_inactive else "archived"
    toggle_icon = "compass" if not is_inactive else "archive"
    toggle_cls = "" if not is_inactive else "uk-text-muted"

    toggle_btn = Button(
        Span(cls=f"uk-icon {toggle_cls}", **{"uk-icon": toggle_icon}),
        hx_post=f"/api/principles/{principle.uid}/status",
        hx_vals=f'{{"status": "{new_status}"}}',
        hx_target=f"#principle-{safe_id(principle.uid)}",
        hx_swap="outerHTML",
        cls="uk-button uk-button-default uk-button-small uk-border-rounded",
        title=f"Mark as {new_status}",
    )

    # Title
    title_cls = "uk-text-muted" if is_inactive else ""
    title_el = A(
        principle.title or "Untitled",
        href=f"/principles/detail?uid={principle.uid}",
        cls=f"uk-link-text {title_cls}",
    )

    # Badges
    badges: list[Any] = []
    if principle.strength:
        badges.append(StrengthBadge(principle.strength.value))
    if principle.principle_category:
        badges.append(Span(str(principle.principle_category.value).title(), cls="uk-badge"))
    if principle.status:
        badges.append(StatusBadge(str(principle.status)))

    # Alignment indicator
    alignment_el = Span()
    if principle.current_alignment:
        al_value = principle.current_alignment.value
        al_cls = _ALIGNMENT_COLORS.get(al_value, "uk-text-muted")
        alignment_el = Small(
            al_value.replace("_", " ").title(),
            cls=f"{al_cls} uk-margin-small-left",
        )

    # Statement preview
    statement_el = Span()
    if principle.statement:
        preview = principle.statement[:100]
        if len(principle.statement) > 100:
            preview += "..."
        statement_el = Div(
            Small(preview, cls="uk-text-muted"),
            cls="uk-margin-small-top",
        )

    # Connection count summary
    conn_summary = ConnectionSummary(connections or [])

    # Card assembly
    header = Div(
        toggle_btn,
        Div(
            Div(title_el, alignment_el, cls="uk-flex uk-flex-middle uk-flex-wrap"),
            Div(*badges, cls="uk-flex uk-flex-wrap uk-flex-middle uk-margin-small-top")
            if badges
            else "",
            statement_el,
            conn_summary,
            cls="uk-margin-small-left uk-width-expand",
        ),
        cls="uk-flex uk-flex-top",
    )

    opacity = "uk-opacity-75" if is_inactive else ""
    return Div(
        header,
        id=f"principle-{safe_id(principle.uid)}",
        cls=f"uk-card uk-card-default uk-card-body uk-card-small uk-margin-small-bottom {opacity}",
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
        badges.append(Span(str(principle.principle_category.value).title(), cls="uk-badge"))
    if principle.current_alignment:
        al_value = principle.current_alignment.value
        al_cls = _ALIGNMENT_COLORS.get(al_value, "uk-text-muted")
        badges.append(Span(al_value.replace("_", " ").title(), cls=f"uk-badge {al_cls}"))
    if principle.status:
        badges.append(StatusBadge(str(principle.status)))

    # Statement (prominent)
    statement_section = Div()
    if principle.statement:
        statement_section = Div(
            P(
                principle.statement,
                cls="uk-text-lead",
                style="font-style: italic; border-left: 3px solid var(--uk-primary); padding-left: 1rem;",
            ),
            cls="uk-margin",
        )

    # Description
    desc_el = Div()
    if principle.description:
        desc_el = Div(P(principle.description, cls="uk-text-default"), cls="uk-margin")

    # Philosophical context
    philo_items: list[Any] = []
    if principle.tradition:
        philo_items.append(
            Div(
                Small("Tradition", cls="uk-text-muted uk-display-block"),
                P(principle.tradition, cls="uk-text-default"),
            )
        )
    if principle.original_source:
        philo_items.append(
            Div(
                Small("Original Source", cls="uk-text-muted uk-display-block"),
                P(principle.original_source, cls="uk-text-default"),
            )
        )
    if principle.personal_interpretation:
        philo_items.append(
            Div(
                Small("Personal Interpretation", cls="uk-text-muted uk-display-block"),
                P(principle.personal_interpretation, cls="uk-text-default"),
            )
        )
    philo_section = Div()
    if philo_items:
        philo_section = Div(
            H3("Philosophical Context", cls="uk-heading-small"),
            *philo_items,
            cls="uk-margin",
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
            H3("Expressions", cls="uk-heading-small"),
            Ul(*expr_items, cls="uk-list uk-list-disc"),
            cls="uk-margin",
        )

    behaviors_section = Div()
    if principle.key_behaviors:
        behavior_items = [Li(b) for b in principle.key_behaviors]
        behaviors_section = Div(
            H3("Key Behaviors", cls="uk-heading-small"),
            Ul(*behavior_items, cls="uk-list uk-list-disc"),
            cls="uk-margin",
        )

    # Alignment section
    alignment_section = Div()
    if principle.current_alignment:
        al_value = principle.current_alignment.value
        al_cls = _ALIGNMENT_COLORS.get(al_value, "uk-text-muted")
        al_items: list[Any] = [
            Div(
                Small("Current Alignment", cls="uk-text-muted uk-display-block"),
                Span(al_value.replace("_", " ").title(), cls=f"uk-text-bold {al_cls}"),
            )
        ]
        if principle.last_review_date:
            al_items.append(
                Div(
                    Small("Last Reviewed", cls="uk-text-muted uk-display-block"),
                    Span(str(principle.last_review_date)),
                )
            )
        # Alignment history
        if principle.alignment_history:
            history_items = []
            for assessment in principle.alignment_history[-5:]:  # Show last 5
                al_level = getattr(assessment, "alignment_level", None) or str(assessment)
                assessed_at = getattr(assessment, "assessed_date", "")
                h_cls = _ALIGNMENT_COLORS.get(str(al_level), "uk-text-muted")
                history_items.append(
                    Li(
                        Span(str(al_level).replace("_", " ").title(), cls=h_cls),
                        Small(f" — {assessed_at}", cls="uk-text-muted") if assessed_at else "",
                    )
                )
            if history_items:
                al_items.append(
                    Div(
                        Small("History", cls="uk-text-muted uk-display-block"),
                        Ul(*history_items, cls="uk-list"),
                    )
                )
        alignment_section = Div(
            H3("Alignment", cls="uk-heading-small"),
            *al_items,
            cls="uk-margin",
        )

    # Conflicts & Tensions
    conflicts_section = Div()
    conflict_items: list[Any] = []
    if principle.potential_conflicts:
        conflict_items.append(
            Div(
                Small("Potential Conflicts", cls="uk-text-muted uk-display-block"),
                Ul(*[Li(c) for c in principle.potential_conflicts], cls="uk-list uk-list-disc"),
            )
        )
    if principle.resolution_strategies:
        conflict_items.append(
            Div(
                Small("Resolution Strategies", cls="uk-text-muted uk-display-block"),
                Ul(*[Li(s) for s in principle.resolution_strategies], cls="uk-list uk-list-disc"),
            )
        )
    if conflict_items:
        conflicts_section = Div(
            H3("Conflicts & Tensions", cls="uk-heading-small"),
            *conflict_items,
            cls="uk-margin",
        )

    # Personal reflection
    reflection_items: list[Any] = []
    if principle.origin_story:
        reflection_items.append(
            Div(
                Small("Origin Story", cls="uk-text-muted uk-display-block"),
                P(principle.origin_story, cls="uk-text-default"),
            )
        )
    if principle.evolution_notes:
        reflection_items.append(
            Div(
                Small("Evolution Notes", cls="uk-text-muted uk-display-block"),
                P(principle.evolution_notes, cls="uk-text-default"),
            )
        )
    reflection_section = Div()
    if reflection_items:
        reflection_section = Div(
            H3("Personal Reflection", cls="uk-heading-small"),
            *reflection_items,
            cls="uk-margin",
        )

    # Metadata grid
    meta_items: list[Any] = []
    if principle.adopted_date:
        meta_items.append(
            Div(
                Small("Adopted", cls="uk-text-muted uk-display-block"),
                Span(str(principle.adopted_date)),
            )
        )
    if principle.principle_source:
        meta_items.append(
            Div(
                Small("Source", cls="uk-text-muted uk-display-block"),
                Span(str(principle.principle_source.value).title()),
            )
        )
    if principle.created_at:
        meta_items.append(
            Div(
                Small("Created", cls="uk-text-muted uk-display-block"),
                Span(str(principle.created_at)[:10]),
            )
        )
    meta_grid = Div()
    if meta_items:
        meta_grid = Div(
            *meta_items,
            cls="uk-grid uk-grid-small uk-child-width-1-3@s uk-child-width-auto@m uk-margin",
            **{"uk-grid": "true"},
        )

    # Tags
    tags_el = Div()
    if principle.tags:
        tag_badges = [
            Span(tag, cls="uk-badge uk-badge-secondary uk-margin-small-right")
            for tag in principle.tags
        ]
        tags_el = Div(
            Small("Tags", cls="uk-text-muted uk-display-block uk-margin-small-bottom"),
            *tag_badges,
            cls="uk-margin",
        )

    # Connections — gravity well (incoming relationships)
    conn_section = Div()
    if connections:
        conn_section = PrincipleConnectionsSection(connections)

    # Lateral relationships
    relationships = EntityRelationshipsSection(
        entity_uid=principle.uid,
        entity_type="principles",
    )

    return Div(
        header,
        Div(*badges, cls="uk-flex uk-flex-wrap uk-flex-middle uk-margin-small-bottom")
        if badges
        else "",
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
        relationships,
        cls="uk-container uk-container-small",
    )


def PrincipleConnectionsSection(connections: list[dict[str, str]]) -> "FT":
    """Display incoming connections grouped by domain (gravity well view)."""
    # Group by source_type
    groups: dict[str, list[dict[str, str]]] = {}
    for conn in connections:
        source_type = conn.get("source_type", "unknown")
        if source_type not in groups:
            groups[source_type] = []
        groups[source_type].append(conn)

    domain_labels = {
        "task": ("Tasks embodying this principle", "check-square", "/tasks/detail?uid="),
        "habit": ("Habits reinforcing this principle", "repeat", "/habits/detail?uid="),
        "goal": ("Goals aligned with this principle", "target", "/goals/detail?uid="),
        "event": ("Events demonstrating this principle", "calendar", "/events/detail?uid="),
        "choice": ("Choices expressing this principle", "git-branch", "/choices/detail?uid="),
        "ku": ("Knowledge connected", "atom", "/ku/get?uid="),
    }

    sections: list[Any] = []
    for domain, conns in groups.items():
        label, icon, base_href = domain_labels.get(
            domain, (f"{domain.title()} connections", "link", "#")
        )
        links = [
            Li(
                Span(
                    cls="uk-icon uk-margin-small-right", **{"uk-icon": f"icon: {icon}; ratio: 0.75"}
                ),
                A(
                    conn.get("title", conn.get("source_uid", "?")),
                    href=f"{base_href}{conn.get('source_uid', '')}" if base_href != "#" else "#",
                    cls="uk-link-muted",
                ),
            )
            for conn in conns
        ]
        sections.append(
            Div(
                Small(
                    label,
                    cls="uk-text-muted uk-text-uppercase uk-text-small uk-display-block uk-margin-small-bottom",
                ),
                Ul(*links, cls="uk-list uk-list-divider"),
                cls="uk-margin-small-bottom",
            )
        )

    return Div(
        H3("Connections", cls="uk-heading-small"),
        *sections,
        cls="uk-margin",
    )


def StrengthBadge(strength: str) -> "FT":
    """Color-coded badge for PrincipleStrength."""
    style = _STRENGTH_COLORS.get(strength, "")
    return Span(
        strength.title(),
        cls="uk-badge",
        style=style,
    )




def filter_principles(
    principles: list["Principle"],
    status_filter: str = "active",
    category_filter: str = "all",
    strength_filter: str = "all",
    sort_by: str = "strength",
) -> list["Principle"]:
    """Apply filters and sorting to a principle list."""
    filtered = list(principles)

    # Status filter
    if status_filter == "active":
        filtered = [p for p in filtered if p.is_active is None or p.is_active]

    # Category filter
    if category_filter != "all":
        filtered = [
            p
            for p in filtered
            if p.principle_category and p.principle_category.value == category_filter
        ]

    # Strength filter
    if strength_filter != "all":
        filtered = [p for p in filtered if p.strength and p.strength.value == strength_filter]

    # Sort
    def by_strength(p: Any) -> int:
        return _STRENGTH_ORDER.get(p.strength.value if p.strength else "", 5)

    def by_name(p: Any) -> str:
        return (p.title or "").lower()

    def by_created(p: Any) -> str:
        return str(p.created_at or "")

    if sort_by == "strength":
        filtered.sort(key=by_strength)
    elif sort_by == "name":
        filtered.sort(key=by_name)
    elif sort_by == "created":
        filtered.sort(key=by_created, reverse=True)

    return filtered
