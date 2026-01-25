"""
Knowledge UI Components (Phase 3.1)
==================================

Reusable UI components for surfacing knowledge insights to users
without overwhelming them. These components integrate with task creation,
prerequisite validation, learning opportunities, and knowledge visualization.
"""

from typing import Any

from fasthtml.common import Details, H3, H4, Li, P, Script, Summary, Ul

from core.ui.daisy_components import Button, Div, Input, Span


def knowledge_suggestion_card(
    suggestions: list[dict[str, Any]], suggestion_type: str = "suggested"
) -> Div:
    """
    Create a knowledge suggestion card for task forms.

    Args:
        suggestions: List of knowledge suggestions with uid, title, confidence, and reason
        suggestion_type: Type of suggestions (suggested, prerequisite, related)

    Returns:
        Div component with knowledge suggestions
    """
    if not suggestions:
        return Div()  # Return empty div if no suggestions

    # Icon and button class based on suggestion type (explicit DaisyUI classes)
    type_config = {
        "suggested": {
            "icon": "💡",
            "title": "Suggested Knowledge",
            "btn_cls": "btn btn-info btn-xs",
        },
        "prerequisite": {
            "icon": "📚",
            "title": "Prerequisites",
            "btn_cls": "btn btn-warning btn-xs",
        },
        "related": {
            "icon": "🔗",
            "title": "Related Knowledge",
            "btn_cls": "btn btn-success btn-xs",
        },
    }

    config = type_config.get(suggestion_type, type_config["suggested"])

    suggestion_items = []
    for suggestion in suggestions[:5]:  # Limit to 5 suggestions to avoid overwhelming
        confidence_cls = (
            "badge badge-success badge-sm"
            if suggestion.get("confidence", 0) > 0.7
            else "badge badge-warning badge-sm"
        )

        suggestion_items.append(
            Li(
                Div(
                    # Knowledge title and confidence
                    Div(
                        Span(
                            suggestion.get("title", suggestion.get("uid", "Unknown")),
                            cls="font-medium text-base-content",
                        ),
                        Span(
                            f"{suggestion.get('confidence', 0):.0%}",
                            cls=f"{confidence_cls} ml-2",
                        ),
                        cls="flex items-center justify-between",
                    ),
                    # Reason for suggestion
                    P(
                        suggestion.get("reason", "Detected from task content"),
                        cls="text-xs text-base-content/60 mt-1",
                    ),
                    # Add button
                    Button(
                        "Add",
                        cls=f"mt-2 {config['btn_cls']}",
                        onclick=f"addKnowledgeToTask('{suggestion.get('uid')}', '{suggestion_type}')",
                    ),
                    cls="p-3 border border-base-200 rounded-md hover:bg-base-200 transition-colors",
                ),
                cls="mb-2",
            )
        )

    return Details(
        Summary(
            Span(config["icon"], cls="mr-2"),
            Span(config["title"], cls="font-medium text-base-content/70"),
            Span(f"({len(suggestions)})", cls="text-base-content/50 ml-1"),
            cls="cursor-pointer flex items-center text-sm hover:text-base-content transition-colors",
        ),
        Div(Ul(*suggestion_items, cls="space-y-2"), cls="mt-3 p-3 bg-base-200 rounded-md"),
        cls="mt-4 border border-base-200 rounded-lg p-3 bg-base-100",
    )


def prerequisite_validation_panel(
    missing_prerequisites: list[dict[str, Any]], available_prerequisites: list[dict[str, Any]]
) -> Div:
    """
    Create a prerequisite validation panel with helpful guidance.

    Args:
        missing_prerequisites: List of missing prerequisite knowledge,
        available_prerequisites: List of available prerequisites that could be added

    Returns:
        Div component with prerequisite validation
    """
    if not missing_prerequisites and not available_prerequisites:
        return Div()

    content = []

    # Missing prerequisites warning
    if missing_prerequisites:
        missing_items = [
            Li(
                Div(
                    Span("⚠️", cls="mr-2"),
                    Span(
                        prereq.get("title", prereq.get("uid", "Unknown")),
                        cls="font-medium text-error",
                    ),
                    P(
                        prereq.get(
                            "description", "This knowledge is required before starting this task"
                        ),
                        cls="text-sm text-error/80 mt-1",
                    ),
                    cls="flex items-start",
                ),
                cls="mb-3 p-3 bg-error/10 border border-error/20 rounded-md",
            )
            for prereq in missing_prerequisites
        ]

        content.append(
            Div(
                H4("Missing Prerequisites", cls="text-lg font-semibold text-error mb-3"),
                P(
                    "The following knowledge is recommended before starting this task:",
                    cls="text-sm text-error/80 mb-3",
                ),
                Ul(*missing_items),
                cls="mb-6",
            )
        )

    # Available prerequisites suggestion
    if available_prerequisites:
        available_items = [
            Li(
                Div(
                    Div(
                        Span("📖", cls="mr-2"),
                        Span(
                            prereq.get("title", prereq.get("uid", "Unknown")),
                            cls="font-medium text-warning",
                        ),
                        cls="flex items-center",
                    ),
                    P(
                        prereq.get("reason", "Recommended preparation for this task"),
                        cls="text-sm text-warning/80 mt-1",
                    ),
                    Button(
                        "Add as Prerequisite",
                        cls="btn btn-warning btn-xs mt-2",
                        onclick=f"addPrerequisite('{prereq.get('uid')}')",
                    ),
                    cls="p-3 border border-warning/20 rounded-md",
                ),
                cls="mb-2",
            )
            for prereq in available_prerequisites
        ]

        content.append(
            Details(
                Summary(
                    Span("💡", cls="mr-2"),
                    Span("Suggested Prerequisites", cls="font-medium text-warning"),
                    Span(f"({len(available_prerequisites)})", cls="text-warning/60 ml-1"),
                    cls="cursor-pointer flex items-center text-sm hover:text-warning transition-colors",
                ),
                Div(
                    P(
                        "Consider adding these as prerequisites to ensure you're prepared:",
                        cls="text-sm text-warning/80 mb-3",
                    ),
                    Ul(*available_items, cls="space-y-2"),
                    cls="mt-3 p-3 bg-warning/10 rounded-md",
                ),
                cls="mt-4",
            )
        )

    if not content:
        return Div()

    return Div(*content, cls="mt-6 p-4 border border-warning/20 bg-warning/10 rounded-lg")


def learning_opportunity_card(_task: dict[str, Any], opportunities: list[dict[str, Any]]) -> Div:
    """
    Create a learning opportunity card for task lists.

    Args:
        task: Task data with title, uid, etc.
        opportunities: List of learning opportunities for this task

    Returns:
        Div component showing learning opportunities
    """
    if not opportunities:
        return Div()

    opportunity_badges = []
    for opp in opportunities[:3]:  # Show top 3 opportunities
        badge_cls = {
            "high": "badge badge-success",
            "medium": "badge badge-warning",
            "low": "badge badge-info",
        }.get(opp.get("level", "medium"), "badge badge-info")

        opportunity_badges.append(
            Span(
                opp.get("title", "Learning Opportunity"),
                cls=f"{badge_cls} mr-2 mb-1",
            )
        )

    # Calculate total learning value
    total_value = sum(opp.get("value", 1) for opp in opportunities)
    value_stars = "⭐" * min(5, int(total_value))

    return Div(
        Div(
            Span("🎯", cls="mr-2"),
            Span("Learning Opportunities", cls="font-medium text-success"),
            Span(value_stars, cls="ml-2"),
            cls="flex items-center mb-2",
        ),
        Div(*opportunity_badges, cls="mb-2"),
        P(
            f"This task offers {len(opportunities)} learning opportunities with {total_value} learning value points.",
            cls="text-sm text-success/80",
        ),
        cls="mt-3 p-3 bg-success/10 border border-success/20 rounded-md",
    )


def knowledge_connection_graph(connections: list[dict[str, Any]], center_knowledge: str) -> Div:
    """
    Create a simple knowledge connection visualization.

    Args:
        connections: List of knowledge connections
        center_knowledge: The central knowledge UID

    Returns:
        Div component with knowledge graph visualization
    """
    if not connections:
        return Div()

    # Group connections by relationship type
    connection_groups = {}
    for conn in connections:
        rel_type = conn.get("relationship_type", "related")
        if rel_type not in connection_groups:
            connection_groups[rel_type] = []
        connection_groups[rel_type].append(conn)

    # Create visual representation
    graph_elements = []

    # Center node
    graph_elements.append(
        Div(
            Span(center_knowledge.split(".")[-1].title(), cls="font-semibold text-info"),
            cls="text-center p-3 bg-info/10 border-2 border-info/30 rounded-lg mb-4",
        )
    )

    # Connection groups (explicit DaisyUI classes - no dynamic interpolation)
    for rel_type, conns in connection_groups.items():
        rel_config = {
            "prerequisite": {
                "icon": "⬆️",
                "label": "Prerequisites",
                "item_cls": "bg-error/10 border border-error/20",
            },
            "enables": {
                "icon": "⬇️",
                "label": "Enables",
                "item_cls": "bg-success/10 border border-success/20",
            },
            "related": {
                "icon": "↔️",
                "label": "Related",
                "item_cls": "bg-info/10 border border-info/20",
            },
            "applies_to": {
                "icon": "🎯",
                "label": "Applies To",
                "item_cls": "bg-secondary/10 border border-secondary/20",
            },
        }.get(
            rel_type,
            {"icon": "🔗", "label": "Connected", "item_cls": "bg-base-200 border border-base-300"},
        )

        conn_items = [
            Div(
                Span(
                    conn.get("target_title", conn.get("target_uid", "Unknown")),
                    cls="text-sm text-base-content/70",
                ),
                cls=f"p-2 {rel_config['item_cls']} rounded-md text-center",
            )
            for conn in conns[:4]  # Show up to 4 connections per type
        ]

        if conn_items:
            graph_elements.append(
                Div(
                    Div(
                        Span(rel_config["icon"], cls="mr-2"),
                        Span(rel_config["label"], cls="font-medium text-base-content/70"),
                        cls="text-sm mb-2 flex items-center",
                    ),
                    Div(*conn_items, cls="grid grid-cols-2 gap-2"),
                    cls="mb-4",
                )
            )

    return Details(
        Summary(
            Span("🕸️", cls="mr-2"),
            Span("Knowledge Connections", cls="font-medium text-base-content/70"),
            Span(f"({len(connections)})", cls="text-base-content/50 ml-1"),
            cls="cursor-pointer flex items-center text-sm hover:text-base-content transition-colors",
        ),
        Div(*graph_elements, cls="mt-3 p-4 bg-base-200 rounded-md"),
        cls="mt-4 border border-base-200 rounded-lg p-3 bg-base-100",
    )


def knowledge_insights_summary(insights: list[dict[str, Any]]) -> Div:
    """
    Create a summary card of knowledge insights.

    Args:
        insights: List of knowledge insights

    Returns:
        Div component with insights summary
    """
    if not insights:
        return Div()

    insight_items = []
    for insight in insights[:3]:  # Show top 3 insights
        insight_type = insight.get("type", "general")
        # Explicit DaisyUI classes - no dynamic interpolation
        type_config = {
            "knowledge_focus": {"icon": "🎯", "card_cls": "bg-info/10 border border-info/20"},
            "learning_velocity": {
                "icon": "🚀",
                "card_cls": "bg-success/10 border border-success/20",
            },
            "knowledge_gap": {"icon": "⚠️", "card_cls": "bg-warning/10 border border-warning/20"},
            "mastery_validation": {
                "icon": "✅",
                "card_cls": "bg-success/10 border border-success/20",
            },
            "cross_domain_integration": {
                "icon": "🔗",
                "card_cls": "bg-secondary/10 border border-secondary/20",
            },
        }.get(insight_type, {"icon": "💡", "card_cls": "bg-info/10 border border-info/20"})

        insight_items.append(
            Div(
                Div(
                    Span(type_config["icon"], cls="mr-2"),
                    Span(insight.get("title", "Insight"), cls="font-medium text-base-content"),
                    cls="flex items-center mb-1",
                ),
                P(
                    insight.get("description", "Knowledge insight detected"),
                    cls="text-sm text-base-content/60",
                ),
                cls=f"p-3 {type_config['card_cls']} rounded-md",
            )
        )

    return Details(
        Summary(
            Span("📊", cls="mr-2"),
            Span("Knowledge Insights", cls="font-medium text-base-content/70"),
            Span(f"({len(insights)})", cls="text-base-content/50 ml-1"),
            cls="cursor-pointer flex items-center text-sm hover:text-base-content transition-colors",
        ),
        Div(Div(*insight_items, cls="space-y-3"), cls="mt-3 p-3 bg-base-200 rounded-md"),
        cls="mt-4 border border-base-200 rounded-lg p-3 bg-base-100",
    )


def knowledge_enhancement_scripts() -> Script:
    """
    JavaScript functions for knowledge enhancement interactions.

    Returns:
        Script component with JavaScript functions
    """
    return Script("""
        // Knowledge suggestion functions
        function addKnowledgeToTask(knowledgeUid, suggestionType) {
            console.log('Adding knowledge:', knowledgeUid, 'type:', suggestionType);

            // Get or create the hidden input for this type
            let inputId = suggestionType === 'prerequisite' ? 'prerequisite_knowledge_uids' : 'applies_knowledge_uids';
            let input = document.getElementById(inputId);

            if (!input) {
                input = document.createElement('input');
                input.type = 'hidden';
                input.id = inputId;
                input.name = inputId;
                input.value = '';
                document.querySelector('form').appendChild(input);
            }

            // Add the knowledge UID
            let currentValues = input.value ? input.value.split(',') : [];
            if (!currentValues.includes(knowledgeUid)) {
                currentValues.push(knowledgeUid);
                input.value = currentValues.join(',');

                // Update UI to show selection
                updateKnowledgeSelectionUI(knowledgeUid, suggestionType, true);
            }
        }

        function addPrerequisite(knowledgeUid) {
            addKnowledgeToTask(knowledgeUid, 'prerequisite');
        }

        function updateKnowledgeSelectionUI(knowledgeUid, type, added) {
            // Find the suggestion button and update its appearance
            const buttons = document.querySelectorAll(`button[onclick*="${knowledgeUid}"]`);
            buttons.forEach(button => {
                if (added) {
                    button.textContent = '✓ Added';
                    // Remove existing DaisyUI btn-* color classes and add btn-success
                    button.classList.remove('btn-info', 'btn-warning', 'btn-success', 'btn-error', 'btn-primary', 'btn-secondary');
                    button.classList.add('btn-success');
                    button.disabled = true;
                } else {
                    button.textContent = 'Add';
                    button.disabled = false;
                }
            });
        }

        // Knowledge suggestion loading
        async function loadKnowledgeSuggestions(taskTitle) {
            if (!taskTitle || taskTitle.length < 3) return;

            try {
                const response = await fetch('/api/knowledge/suggestions', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        content: taskTitle,
                        entity_type: 'task'
                    })
                });

                if (response.ok) {
                    const suggestions = await response.json();
                    updateKnowledgeSuggestionsUI(suggestions.data || []);
                }
            } catch (error) {
                console.log('Knowledge suggestions not available:', error);
            }
        }

        function updateKnowledgeSuggestionsUI(suggestions) {
            const container = document.getElementById('knowledge-suggestions-container');
            if (!container || !suggestions.length) return;

            // Group suggestions by type
            const grouped = {
                suggested: suggestions.filter(s => s.type === 'suggested'),
                prerequisite: suggestions.filter(s => s.type === 'prerequisite'),
                related: suggestions.filter(s => s.type === 'related')
            };

            // Update the UI (this would be enhanced with actual server-side rendering)
            console.log('Knowledge suggestions loaded:', grouped);
        }

        // Auto-suggestion on title change
        let suggestionTimeout;
        function onTaskTitleChange(event) {
            clearTimeout(suggestionTimeout);
            suggestionTimeout = setTimeout(() => {
                loadKnowledgeSuggestions(event.target.value);
            }, 500); // Debounce for 500ms
        }

        // Initialize on page load
        document.addEventListener('DOMContentLoaded', function() {
            const titleInput = document.querySelector('input[name="title"]');
            if (titleInput) {
                titleInput.addEventListener('input', onTaskTitleChange);
            }
        });
    """)


def enhanced_task_form_with_knowledge(
    existing_form_content: Div,
    knowledge_suggestions: dict[str, Any] | None = None,
    prerequisite_data: dict[str, Any] | None = None,
) -> Div:
    """
    Enhance an existing task form with knowledge components.

    Args:
        existing_form_content: The existing form content,
        knowledge_suggestions: Knowledge suggestions to display,
        prerequisite_data: Prerequisite validation data

    Returns:
        Enhanced form with knowledge components
    """
    enhanced_content = [existing_form_content]

    # Add knowledge suggestions after title field
    if knowledge_suggestions:
        enhanced_content.append(
            Div(
                knowledge_suggestion_card(knowledge_suggestions.get("suggested", []), "suggested"),
                knowledge_suggestion_card(
                    knowledge_suggestions.get("prerequisite", []), "prerequisite"
                ),
                knowledge_suggestion_card(knowledge_suggestions.get("related", []), "related"),
                id="knowledge-suggestions-container",
                cls="mt-4",
            )
        )

    # Add prerequisite validation panel
    if prerequisite_data:
        enhanced_content.append(
            prerequisite_validation_panel(
                prerequisite_data.get("missing", []), prerequisite_data.get("available", [])
            )
        )

    # Add hidden inputs for knowledge tracking
    enhanced_content.extend(
        [
            Input(type="hidden", name="applies_knowledge_uids", id="applies_knowledge_uids"),
            Input(
                type="hidden", name="prerequisite_knowledge_uids", id="prerequisite_knowledge_uids"
            ),
            Input(type="hidden", name="inferred_knowledge_uids", id="inferred_knowledge_uids"),
        ]
    )

    # Add JavaScript for interactions
    enhanced_content.append(knowledge_enhancement_scripts())

    return Div(*enhanced_content)


def task_list_with_learning_opportunities(
    tasks: list[dict[str, Any]], learning_data: dict[str, Any] | None = None
) -> Div:
    """
    Enhance a task list with learning opportunity cards.

    Args:
        tasks: List of tasks,
        learning_data: Learning opportunities data by task UID

    Returns:
        Enhanced task list with learning opportunities
    """
    if not tasks:
        return Div(
            P(
                "No tasks found. Create your first task to get started!",
                cls="text-base-content/50 text-center py-8",
            ),
            cls="bg-base-100 rounded-lg border border-base-200 p-6",
        )

    task_items = []
    for task in tasks:
        task_uid = task.get("uid", "")
        task_opportunities = learning_data.get(task_uid, []) if learning_data else []

        # Priority badge mapping (explicit DaisyUI classes)
        priority_badge = {
            "high": "badge badge-error",
            "medium": "badge badge-warning",
            "low": "badge badge-success",
        }.get(task.get("priority", "medium"), "badge badge-warning")

        # Base task card
        task_card = Div(
            # Task header
            Div(
                H3(
                    task.get("title", "Untitled Task"),
                    cls="text-lg font-semibold text-base-content",
                ),
                Span(
                    task.get("priority", "medium").upper(),
                    cls=priority_badge,
                ),
                cls="flex items-center justify-between mb-2",
            ),
            # Task description
            P(task.get("description", ""), cls="text-base-content/60 text-sm mb-3")
            if task.get("description")
            else Div(),
            # Learning opportunity card
            learning_opportunity_card(task, task_opportunities),
            # Task actions
            Div(
                Button(
                    "View Details",
                    cls="btn btn-primary btn-sm",
                ),
                Button(
                    "Start Task",
                    cls="btn btn-success btn-sm ml-2",
                ),
                cls="flex justify-end mt-4",
            ),
            cls="bg-base-100 p-6 rounded-lg border border-base-200 mb-4 hover:shadow-md transition-shadow",
        )

        task_items.append(task_card)

    return Div(*task_items, cls="space-y-4")
