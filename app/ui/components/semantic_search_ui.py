#!/usr/bin/env python3
"""
Semantic Search UI Components
=============================

DaisyUI components for semantic search interface.

Components:
- SemanticSearchBar: Advanced search with intent selection
- SearchResultCard: Display semantic search results
- KnowledgeGraph: Interactive knowledge graph visualization
- CrossDomainExplorer: Cross-domain discovery interface
- LearningPathBuilder: Semantic path generation UI
"""

from typing import Any

from fasthtml.common import (
    H1,
    H2,
    H3,
    Details,
    Form,
    Label,
    Option,
    P,
    Select,
    Summary,
)

from core.models.shared_enums import Domain
from core.ui.daisy_components import (
    Badge,
    Button,
    Card,
    CardBody,
    Div,
    Input,
    Progress,
    Span,
)
from core.ui.enum_helpers import get_bridge_color
from core.utils.logging import get_logger

logger = get_logger(__name__)


def SemanticSearchBar(
    query: str = "", intent: str | None = None, on_search: str | None = None
) -> Form:
    """
    Advanced semantic search bar with intent selection.

    Args:
        query: Initial search query,
        intent: Selected search intent,
        on_search: HTMX endpoint for search submission
    """
    return Form(
        cls="semantic-search-bar",
        hx_post=on_search or "/api/semantic/search",
        hx_target="#search-results",
        hx_swap="outerHTML",
    )(
        Div(cls="flex gap-4 items-end")(
            # Search input
            Div(cls="flex-1")(
                Label(_for="search-query", cls="block text-sm font-medium mb-1")(
                    "What would you like to learn?"
                ),
                Input(
                    type="text",
                    id="search-query",
                    name="query",
                    value=query,
                    placeholder="e.g., 'machine learning prerequisites' or 'similar to React'",
                    cls="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500",
                    required=True,
                ),
            ),
            # Intent selector
            Div(cls="w-48")(
                Label(_for="search-intent", cls="block text-sm font-medium mb-1")("Search Type"),
                Select(id="search-intent", name="intent", cls="w-full px-3 py-2 border rounded-lg")(
                    Option(value="", selected=not intent)("Auto-detect"),
                    Option(value="FIND_PREREQUISITES", selected=intent == "FIND_PREREQUISITES")(
                        "Prerequisites"
                    ),
                    Option(value="FIND_NEXT_STEPS", selected=intent == "FIND_NEXT_STEPS")(
                        "Next Steps"
                    ),
                    Option(value="FIND_SIMILAR", selected=intent == "FIND_SIMILAR")(
                        "Similar Topics"
                    ),
                    Option(value="FIND_APPLICATIONS", selected=intent == "FIND_APPLICATIONS")(
                        "Applications"
                    ),
                    Option(value="FIND_CROSS_DOMAIN", selected=intent == "FIND_CROSS_DOMAIN")(
                        "Cross-Domain"
                    ),
                    Option(value="EXPLORE_TOPIC", selected=intent == "EXPLORE_TOPIC")("Explore"),
                ),
            ),
            # Search button
            Button(
                "Search",
                type="submit",
                cls="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition",
            ),
        ),
        # Search hints
        Div(cls="mt-2 text-sm text-gray-600")(
            "Try: ",
            Span(
                cls="font-mono cursor-pointer hover:text-blue-600",
                onclick="document.getElementById('search-query').value=this.innerText",
            )("'prerequisites for deep learning'"),
            " or ",
            Span(
                cls="font-mono cursor-pointer hover:text-blue-600",
                onclick="document.getElementById('search-query').value=this.innerText",
            )("'concepts similar to recursion'"),
        ),
    )


def SearchResultCard(
    result: dict[str, Any], show_relationships: bool = True, expandable: bool = True
) -> Any:
    """
    Display a semantic search result.

    Args:
        result: Search result data,
        show_relationships: Show semantic relationships,
        expandable: Make card expandable for details
    """
    relevance = result.get("relevance", 0)
    relevance_color = (
        "bg-green-100 text-green-800"
        if relevance > 0.8
        else "bg-yellow-100 text-yellow-800"
        if relevance > 0.6
        else "bg-gray-100 text-gray-800"
    )

    card_content = [
        # Header with title and relevance
        Div(cls="flex justify-between items-start mb-2")(
            H3(cls="text-lg font-semibold text-gray-900")(result.get("title", "Untitled")),
            Badge(f"{relevance:.0%} match", cls=f"px-2 py-1 rounded text-sm {relevance_color}"),
        ),
        # Summary
        P(cls="text-gray-700 mb-3")(result.get("summary", "")),
        # Domain and tags
        Div(cls="flex flex-wrap gap-2 mb-3")(
            Badge(f"📚 {result.get('domain', 'Unknown')}", cls="bg-blue-100 text-blue-800"),
            *[Badge(tag, cls="bg-gray-100 text-gray-700") for tag in result.get("tags", [])[:3]],
        ),
        # Explanation if present
        result.get("explanation")
        and P(cls="text-sm text-gray-600 italic mb-3")(f"💡 {result['explanation']}"),
    ]

    # Semantic relationships
    if show_relationships and result.get("relationships"):
        relationships_section = Details(cls="mt-3 p-3 bg-gray-50 rounded", open=not expandable)(
            Summary(cls="cursor-pointer font-medium text-gray-700")("Semantic Connections"),
            Div(cls="mt-2 space-y-1")(
                *[
                    Div(cls="text-sm")(
                        Span(cls="font-medium")(rel["type"].replace("_", " ").title()),
                        ": ",
                        Span(cls="text-gray-600")(rel["target"]),
                        Span(cls="ml-2 text-xs text-gray-500")(
                            f"({rel['confidence']:.0%} confidence)"
                        ),
                    )
                    for rel in result.get("relationships", [])
                ]
            ),
        )
        card_content.append(relationships_section)

    # Action buttons
    card_content.append(
        Div(cls="mt-4 flex gap-2")(
            Button(
                "View Details",
                cls="text-sm px-3 py-1 border border-blue-600 text-blue-600 rounded hover:bg-blue-50",
                hx_get=f"/api/knowledge/{result.get('uid')}",
                hx_target="#detail-view",
            ),
            Button(
                "Create Learning Path",
                cls="text-sm px-3 py-1 border border-green-600 text-green-600 rounded hover:bg-green-50",
                hx_post="/api/semantic/path/generate",
                hx_vals=f'{{"target_uid": "{result.get("uid")}"}}',
                hx_target="#path-builder",
            ),
            Button(
                "Explore Graph",
                cls="text-sm px-3 py-1 border border-purple-600 text-purple-600 rounded hover:bg-purple-50",
                hx_get=f"/api/semantic/neighborhood/{result.get('uid')}",
                hx_target="#graph-view",
            ),
        )
    )

    return Card(
        CardBody(*card_content),
        cls="hover:shadow-lg transition",
        id=f"result-{result.get('uid', '')}",
    )


def CrossDomainExplorer(opportunities: list[dict[str, Any]] | None = None) -> Div:
    """
    Interface for exploring cross-domain learning opportunities.

    Args:
        opportunities: List of cross-domain opportunities
    """
    if not opportunities:
        return Div(cls="cross-domain-explorer p-6 bg-gray-50 rounded-lg")(
            H2(cls="text-xl font-bold mb-4")("🌐 Cross-Domain Learning Opportunities"),
            P(cls="text-gray-600")(
                "Discover how your existing knowledge can accelerate learning in new domains."
            ),
            Form(
                cls="mt-4",
                hx_post="/api/semantic/cross-domain/discover",
                hx_target="#cross-domain-results",
            )(
                Label(cls="block text-sm font-medium mb-2")("Select target domains to explore:"),
                Div(cls="grid grid-cols-3 gap-2 mb-4")(
                    *[
                        Label(cls="flex items-center")(
                            Input(
                                type="checkbox",
                                name="target_domains",
                                value=domain.value,
                                cls="mr-2",
                            ),
                            domain.value.replace("_", " ").title(),
                        )
                        for domain in Domain
                    ]
                ),
                Button(
                    "Discover Opportunities",
                    type="submit",
                    cls="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700",
                ),
            ),
            Div(id="cross-domain-results"),
        )

    # Display opportunities
    opportunity_cards = []
    for opp in opportunities:
        # Dynamic enum method - updates when shared_enums.py changes
        bridge_type = opp.get("bridge_type", "")
        bridge_color = get_bridge_color(bridge_type) if bridge_type else "gray"

        opportunity_cards.append(
            Card(
                CardBody(
                    # Source to target
                    Div(cls="flex items-center justify-between mb-3")(
                        Div(cls="flex-1")(
                            H3(cls="font-semibold")(opp["source_concept"]["title"]),
                            P(cls="text-sm text-gray-600")(
                                f"From {opp['source_concept']['domain']}"
                            ),
                        ),
                        Div(cls="px-3 text-2xl")("->"),
                        Div(cls="flex-1 text-right")(
                            H3(cls="font-semibold")(opp["target_concept"]["title"]),
                            P(cls="text-sm text-gray-600")(f"To {opp['target_concept']['domain']}"),
                        ),
                    ),
                    # Bridge type and transferability
                    Div(cls="flex gap-2 mb-3")(
                        Badge(
                            opp["bridge_type"].replace("_", " ").title(),
                            cls=f"bg-{bridge_color}-100 text-{bridge_color}-800",
                        ),
                        Badge(
                            f"Transferability: {opp['transferability']:.0%}",
                            cls="bg-gray-100 text-gray-800",
                        ),
                        Badge(f"Effort: {opp['effort_required']}", cls="bg-gray-100 text-gray-800"),
                    ),
                    # Reasoning
                    P(cls="text-sm text-gray-700 mb-3")(opp["reasoning"]),
                    # Learning path preview
                    opp.get("learning_path")
                    and Details(cls="mt-3")(
                        Summary(cls="cursor-pointer text-sm font-medium")(
                            f"Suggested Path ({len(opp['learning_path'])} steps)"
                        ),
                        Div(cls="mt-2 pl-4 border-l-2 border-gray-300")(
                            *[
                                Div(cls="text-sm py-1")(f"{i + 1}. {step['title']}")
                                for i, step in enumerate(opp["learning_path"])
                            ]
                        ),
                    ),
                    # Action button
                    Button(
                        "Start This Learning Journey",
                        cls="mt-3 text-sm px-3 py-1 bg-purple-600 text-white rounded hover:bg-purple-700",
                        hx_post="/api/semantic/path/generate",
                        hx_vals=f'{{"target_uid": "{opp["target_concept"]["uid"]}"}}',
                    ),
                ),
                cls="mb-3",
            )
        )

    return Div(cls="cross-domain-results")(
        H3(cls="text-lg font-semibold mb-3")(
            f"Found {len(opportunities)} Cross-Domain Opportunities"
        ),
        *opportunity_cards,
    )


def LearningPathBuilder(path: dict[str, Any] | None = None, editable: bool = True) -> Div:
    """
    Interface for building and viewing semantic learning paths.

    Args:
        path: Learning path data,
        editable: Allow path editing
    """
    if not path:
        # Path creation form
        return Div(cls="path-builder p-6 bg-blue-50 rounded-lg")(
            H2(cls="text-xl font-bold mb-4")("🎯 Semantic Learning Path Generator"),
            P(cls="text-gray-600 mb-4")(
                "Create an optimized learning path using semantic relationships."
            ),
            Form(hx_post="/api/semantic/path/generate", hx_target="#path-display")(
                Div(cls="grid grid-cols-2 gap-4")(
                    Div()(
                        Label(cls="block text-sm font-medium mb-1")("Target Knowledge"),
                        Input(
                            type="text",
                            name="target_uid",
                            placeholder="e.g., machine_learning",
                            cls="w-full px-3 py-2 border rounded",
                            required=True,
                        ),
                    ),
                    Div()(
                        Label(cls="block text-sm font-medium mb-1")("Learning Style"),
                        Select(name="learning_style", cls="w-full px-3 py-2 border rounded")(
                            Option(value="balanced")("Balanced"),
                            Option(value="theoretical")("Theory First"),
                            Option(value="practical")("Practice First"),
                            Option(value="exploratory")("Exploratory"),
                        ),
                    ),
                    Div()(
                        Label(cls="block text-sm font-medium mb-1")("Maximum Steps"),
                        Input(
                            type="number",
                            name="max_steps",
                            value="20",
                            min="5",
                            max="50",
                            cls="w-full px-3 py-2 border rounded",
                        ),
                    ),
                    Div()(
                        Label(cls="block text-sm font-medium mb-1")("Time Available (hours)"),
                        Input(
                            type="number",
                            name="time_constraint",
                            placeholder="Optional",
                            cls="w-full px-3 py-2 border rounded",
                        ),
                    ),
                ),
                Button(
                    "Generate Path",
                    type="submit",
                    cls="mt-4 px-6 py-2 bg-green-600 text-white rounded hover:bg-green-700",
                ),
            ),
            Div(id="path-display"),
        )

    # Display generated path
    steps_html = []
    for i, step in enumerate(path.get("steps", [])):
        is_complete = step.get("completed", False)
        step_class = "bg-green-50 border-green-300" if is_complete else "bg-white"

        steps_html.append(
            Div(cls=f"step-item p-4 border rounded-lg mb-3 {step_class}")(
                Div(cls="flex justify-between items-start mb-2")(
                    Div(cls="flex items-center")(
                        Span(cls="text-2xl font-bold text-gray-400 mr-3")(f"{i + 1}"),
                        Div()(
                            H3(cls="font-semibold")(step["title"]),
                            P(cls="text-sm text-gray-600")(step.get("description", "")),
                        ),
                    ),
                    Div(cls="text-right")(
                        Badge(
                            f"{step.get('estimated_time', 0)} hours",
                            cls="bg-blue-100 text-blue-800 mb-1",
                        ),
                        Div(cls="text-sm text-gray-500")(
                            f"Mastery: {step.get('mastery_threshold', 0.8):.0%}"
                        ),
                    ),
                ),
                # Semantic reasoning
                step.get("reasoning")
                and P(cls="text-sm text-gray-600 italic ml-10 mb-2")(f"💭 {step['reasoning']}"),
                # Progress bar
                editable
                and Div(cls="ml-10 mt-2")(
                    Progress(
                        value=step.get("progress", 0), max_val=100, cls="h-2 bg-gray-200 rounded"
                    ),
                    Div(cls="flex justify-between text-xs text-gray-500 mt-1")(
                        Span(f"Progress: {step.get('progress', 0)}%"),
                        Button(
                            "Mark Complete",
                            cls="text-blue-600 hover:text-blue-800",
                            hx_post=f"/api/learning/step/{step.get('uid')}/complete",
                            hx_target=f"#step-{i}",
                        ),
                    ),
                ),
                id=f"step-{i}",
            )
        )

    return Div(cls="path-display")(
        # Path header
        Div(cls="mb-6")(
            H2(cls="text-2xl font-bold mb-2")(path.get("name", "Learning Path")),
            P(cls="text-gray-600")(path.get("goal", "")),
            Div(cls="flex gap-4 mt-3")(
                Badge(f"📚 {path.get('total_steps', 0)} steps", cls="bg-gray-100 text-gray-800"),
                Badge(f"⏱️ {path.get('estimated_hours', 0)} hours", cls="bg-gray-100 text-gray-800"),
                Badge(
                    f"💪 {path.get('difficulty', 'medium').title()}",
                    cls="bg-gray-100 text-gray-800",
                ),
            ),
        ),
        # Prerequisites
        path.get("prerequisites")
        and Div(cls="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded")(
            H3(cls="font-semibold text-yellow-800 mb-2")("Prerequisites"),
            Div(cls="text-sm text-yellow-700")(
                *[P(f"• {prereq}") for prereq in path["prerequisites"]]
            ),
        ),
        # Path steps
        Div(cls="path-steps")(*steps_html),
        # Expected outcomes
        path.get("outcomes")
        and Div(cls="mt-6 p-4 bg-green-50 border border-green-200 rounded")(
            H3(cls="font-semibold text-green-800 mb-2")("Expected Outcomes"),
            Div(cls="text-sm text-green-700")(*[P(f"✓ {outcome}") for outcome in path["outcomes"]]),
        ),
        # Action buttons
        editable
        and Div(cls="mt-6 flex gap-3")(
            Button(
                "Start Learning",
                cls="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700",
                hx_post="/api/learning/path/start",
                hx_vals=f'{{"path_uid": "{path.get("uid")}"}}',
            ),
            Button(
                "Export Path",
                cls="px-4 py-2 border border-gray-300 text-gray-700 rounded hover:bg-gray-50",
                hx_get=f"/api/semantic/path/{path.get('uid')}/export",
            ),
            Button(
                "Print",
                cls="px-4 py-2 border border-gray-300 text-gray-700 rounded hover:bg-gray-50",
                onclick="window.print()",
            ),
        ),
    )


def SemanticDashboard() -> Div:
    """
    Main dashboard for semantic search features.
    """
    return Div(cls="semantic-dashboard container mx-auto p-6")(
        # Header
        Div(cls="mb-8")(
            H1(cls="text-3xl font-bold mb-2")("🧠 Semantic Knowledge Explorer"),
            P(cls="text-gray-600")(
                "Discover knowledge connections and generate intelligent learning paths."
            ),
        ),
        # Search section
        Div(cls="mb-8")(SemanticSearchBar()),
        # Results area
        Div(id="search-results", cls="mb-8"),
        # Feature sections
        Div(cls="grid grid-cols-1 lg:grid-cols-2 gap-6")(
            # Cross-domain explorer
            CrossDomainExplorer(),
            # Path builder
            LearningPathBuilder(),
        ),
        # Graph view area
        Div(id="graph-view", cls="mt-8"),
        # Detail view area
        Div(id="detail-view", cls="mt-8"),
    )


# Export components
__all__ = [
    "CrossDomainExplorer",
    "LearningPathBuilder",
    "SearchResultCard",
    "SemanticDashboard",
    "SemanticSearchBar",
]
