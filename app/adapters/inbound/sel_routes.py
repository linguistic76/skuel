"""
SEL Routes - Adaptive SEL Curriculum
=====================================

Routes for the SEL (Social Emotional Learning) adaptive curriculum.

SEL is the paramount feature of SKUEL, providing personalized
learning experiences across the 5 SEL competencies.

Architecture:
    - UI Components: /components/drawer_layout.py (DaisyUI drawer)
    - CSS: DaisyUI built-in (no custom CSS needed)
    - JavaScript: DaisyUI checkbox-based toggle (no custom JS needed)

Routes:
- /sel - SEL journey overview (adaptive)
- /sel/{category} - Adaptive curriculum for one category (enhanced)
- /api/sel/journey - API: Get SEL journey for authenticated user
- /api/sel/curriculum/{category} - API: Get curriculum for authenticated user

Version: 3.0-refactored (DaisyUI drawer)
"""

from typing import Any

from fasthtml.common import H1, H2, H3, A, Li, P, Request, Ul

from components.drawer_layout import create_drawer_layout
from core.auth import require_authenticated_user
from core.errors import NotFoundError
from core.models.ku.ku import Ku
from core.models.sel.sel_progress import SELJourney
from core.models.shared_enums import SELCategory
from core.ui.daisy_components import Card, CardBody, Div
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.services_bootstrap import Services
from ui.layouts.navbar import create_navbar_for_request

logger = get_logger("skuel.routes.sel")


# SEL menu items - (title, href, slug, description)
SEL_MENU_ITEMS = [
    ("Overview", "/sel", "overview", "Introduction to SEL"),
    (
        "Self Awareness",
        "/sel/self-awareness",
        "self-awareness",
        "Understanding your thoughts, emotions, and values",
    ),
    (
        "Self Management",
        "/sel/self-management",
        "self-management",
        "Managing emotions and achieving goals",
    ),
    (
        "Social Awareness",
        "/sel/social-awareness",
        "social-awareness",
        "Understanding others and social contexts",
    ),
    (
        "Relationship Skills",
        "/sel/relationship-skills",
        "relationship-skills",
        "Building healthy relationships",
    ),
    ("Decision Making", "/sel/decision-making", "decision-making", "Making responsible choices"),
]


def create_sel_sidebar_layout(active_page: str, content: Any):
    """
    Create DaisyUI drawer layout for SEL section.

    Uses the reusable DrawerLayout component from components/drawer_layout.py.
    This replaces ~280 lines of custom CSS/JS with DaisyUI's CSS-only drawer.

    Args:
        active_page: Slug of the currently active page
        content: Main content to render

    Returns:
        Complete drawer layout with SEL navigation
    """
    return create_drawer_layout(
        drawer_id="sel-drawer",
        title="SEL Navigation",
        menu_items=SEL_MENU_ITEMS,
        active_page=active_page,
        content=content,
        subtitle="Social Emotional Learning",
    )


def create_sel_routes(_app, rt, services: Services, _sync_service):
    """
    Create SEL documentation routes

    Args:
        app: The FastHTML app instance
        rt: The router instance
        services: The services container
        sync_service: The sync service instance
    """

    # ========================================================================
    # SEL MAIN PAGE
    # ========================================================================

    @rt("/sel")
    async def sel_main(request: Request) -> Any:
        """SEL main page - Simplified without async operations"""
        logger.info("📚 SEL Overview route accessed")

        # Create navbar (session-aware for admin detection)
        navbar = create_navbar_for_request(request, active_page="sel")

        # Display static SEL overview content (no user-specific data needed)
        logger.info("Using simplified static content for SEL overview")
        content = Div(
            H1("SEL - Social Emotional Learning", cls="text-3xl font-bold mb-4"),
            P(
                "SEL is your comprehensive knowledge documentation system, organizing knowledge units "
                "based on social-emotional learning competencies. This framework helps you develop "
                "personal growth through structured reflection and practice.",
                cls="text-lg text-base-content mb-6",
            ),
            H2("Core Competencies", cls="text-2xl font-semibold mb-4"),
            Div(
                A(
                    Card(
                        CardBody(
                            H3("Self Awareness", cls="text-xl font-semibold mb-2"),
                            P(
                                "Understanding your thoughts, emotions, values, and how they influence behavior.",
                                cls="text-sm",
                            ),
                        ),
                        cls="hover:shadow-lg cursor-pointer",
                    ),
                    href="/sel/self-awareness",
                    cls="block no-underline",
                ),
                A(
                    Card(
                        CardBody(
                            H3("Self Management", cls="text-xl font-semibold mb-2"),
                            P(
                                "Effectively managing emotions, thoughts, and behaviors in different situations.",
                                cls="text-sm",
                            ),
                        ),
                        cls="hover:shadow-lg cursor-pointer",
                    ),
                    href="/sel/self-management",
                    cls="block no-underline",
                ),
                A(
                    Card(
                        CardBody(
                            H3("Social Awareness", cls="text-xl font-semibold mb-2"),
                            P(
                                "Understanding the perspectives of others and empathizing with diverse backgrounds.",
                                cls="text-sm",
                            ),
                        ),
                        cls="hover:shadow-lg cursor-pointer",
                    ),
                    href="/sel/social-awareness",
                    cls="block no-underline",
                ),
                A(
                    Card(
                        CardBody(
                            H3("Relationship Skills", cls="text-xl font-semibold mb-2"),
                            P(
                                "Establishing and maintaining healthy relationships through communication and cooperation.",
                                cls="text-sm",
                            ),
                        ),
                        cls="hover:shadow-lg cursor-pointer",
                    ),
                    href="/sel/relationship-skills",
                    cls="block no-underline",
                ),
                A(
                    Card(
                        CardBody(
                            H3("Responsible Decision Making", cls="text-xl font-semibold mb-2"),
                            P(
                                "Making constructive choices based on ethical standards, safety, and social norms.",
                                cls="text-sm",
                            ),
                        ),
                        cls="hover:shadow-lg cursor-pointer",
                    ),
                    href="/sel/decision-making",
                    cls="block no-underline",
                ),
                cls="grid grid-cols-1 md:grid-cols-2 gap-4",
            ),
            P(
                "Select a competency from the sidebar to explore specific knowledge units and practices.",
                cls="text-base-content/70 mt-6 italic",
            ),
        )

        # Use sidebar layout for consistency with other SEL pages
        page_content = create_sel_sidebar_layout("overview", content)

        return Div(navbar, page_content)

    # ========================================================================
    # SELF AWARENESS PAGE
    # ========================================================================

    @rt("/sel/self-awareness")
    async def sel_self_awareness(request: Request) -> Any:
        """Self Awareness knowledge units page"""
        navbar = create_navbar_for_request(request, active_page="sel")

        content = Div(
            H1("Self Awareness", cls="text-3xl font-bold mb-4"),
            P(
                "Self-awareness is the ability to accurately recognize your emotions, thoughts, and values "
                "and how they influence your behavior. It involves understanding your strengths, limitations, "
                "and having a well-grounded sense of confidence and optimism.",
                cls="text-lg text-base-content mb-6",
            ),
            H2("Key Knowledge Units", cls="text-2xl font-semibold mb-4"),
            Ul(
                Li("Identifying emotions and their triggers", cls="mb-2"),
                Li("Recognizing personal strengths and areas for growth", cls="mb-2"),
                Li("Understanding values and belief systems", cls="mb-2"),
                Li("Developing accurate self-perception", cls="mb-2"),
                Li("Building self-confidence and self-efficacy", cls="mb-2"),
                cls="list-disc pl-6 text-base-content",
            ),
            H2("Practical Exercises", cls="text-2xl font-semibold mt-6 mb-4"),
            Div(
                Card(
                    CardBody(
                        H3("Daily Emotion Check-In", cls="text-lg font-semibold mb-2"),
                        P("Take 5 minutes each day to identify and name your current emotions."),
                    ),
                    cls="mb-3",
                ),
                Card(
                    CardBody(
                        H3("Strengths Journal", cls="text-lg font-semibold mb-2"),
                        P("Document instances where you successfully used your strengths."),
                    ),
                    cls="mb-3",
                ),
                Card(
                    CardBody(
                        H3("Values Reflection", cls="text-lg font-semibold mb-2"),
                        P("Weekly reflection on how your actions aligned with your core values."),
                    ),
                    cls="mb-3",
                ),
            ),
        )

        page_content = create_sel_sidebar_layout("self-awareness", content)

        return Div(navbar, page_content)

    # ========================================================================
    # SELF MANAGEMENT PAGE
    # ========================================================================

    @rt("/sel/self-management")
    async def sel_self_management(request: Request) -> Any:
        """Self Management knowledge units page"""
        navbar = create_navbar_for_request(request, active_page="sel")

        content = Div(
            H1("Self Management", cls="text-3xl font-bold mb-4"),
            P(
                "Self-management is the ability to successfully regulate your emotions, thoughts, and behaviors "
                "in different situations. This includes managing stress, controlling impulses, motivating yourself, "
                "and setting and working toward personal and academic goals.",
                cls="text-lg text-base-content mb-6",
            ),
            H2("Key Knowledge Units", cls="text-2xl font-semibold mb-4"),
            Ul(
                Li("Impulse control and delayed gratification", cls="mb-2"),
                Li("Stress management techniques", cls="mb-2"),
                Li("Self-motivation and discipline", cls="mb-2"),
                Li("Goal-setting and achievement strategies", cls="mb-2"),
                Li("Organizational skills and time management", cls="mb-2"),
                cls="list-disc pl-6 text-base-content",
            ),
            H2("Practical Exercises", cls="text-2xl font-semibold mt-6 mb-4"),
            Div(
                Card(
                    CardBody(
                        H3("SMART Goals Workshop", cls="text-lg font-semibold mb-2"),
                        P(
                            "Create specific, measurable, achievable, relevant, and time-bound goals."
                        ),
                    ),
                    cls="mb-3",
                ),
                Card(
                    CardBody(
                        H3("Stress Response Tracking", cls="text-lg font-semibold mb-2"),
                        P("Monitor your stress triggers and effective coping strategies."),
                    ),
                    cls="mb-3",
                ),
                Card(
                    CardBody(
                        H3("Time Blocking Practice", cls="text-lg font-semibold mb-2"),
                        P("Schedule focused work blocks and track your productivity patterns."),
                    ),
                    cls="mb-3",
                ),
            ),
        )

        page_content = create_sel_sidebar_layout("self-management", content)

        return Div(navbar, page_content)

    # ========================================================================
    # SOCIAL AWARENESS PAGE
    # ========================================================================

    @rt("/sel/social-awareness")
    async def sel_social_awareness(request: Request) -> Any:
        """Social Awareness knowledge units page"""
        navbar = create_navbar_for_request(request, active_page="sel")

        content = Div(
            H1("Social Awareness", cls="text-3xl font-bold mb-4"),
            P(
                "Social awareness is the ability to take the perspective of and empathize with others, "
                "including those from diverse backgrounds and cultures. It involves understanding social "
                "and ethical norms for behavior and recognizing family, school, and community resources and supports.",
                cls="text-lg text-base-content mb-6",
            ),
            H2("Key Knowledge Units", cls="text-2xl font-semibold mb-4"),
            Ul(
                Li("Perspective-taking and empathy development", cls="mb-2"),
                Li("Appreciating diversity and respecting others", cls="mb-2"),
                Li("Understanding social cues and norms", cls="mb-2"),
                Li("Recognizing group dynamics", cls="mb-2"),
                Li("Cultural competence and sensitivity", cls="mb-2"),
                cls="list-disc pl-6 text-base-content",
            ),
            H2("Practical Exercises", cls="text-2xl font-semibold mt-6 mb-4"),
            Div(
                Card(
                    CardBody(
                        H3("Perspective Journal", cls="text-lg font-semibold mb-2"),
                        P("Write about situations from multiple viewpoints to build empathy."),
                    ),
                    cls="mb-3",
                ),
                Card(
                    CardBody(
                        H3("Cultural Exploration", cls="text-lg font-semibold mb-2"),
                        P(
                            "Learn about different cultures through books, films, and conversations."
                        ),
                    ),
                    cls="mb-3",
                ),
                Card(
                    CardBody(
                        H3("Active Listening Practice", cls="text-lg font-semibold mb-2"),
                        P("Focus on truly understanding others without judgment or interruption."),
                    ),
                    cls="mb-3",
                ),
            ),
        )

        page_content = create_sel_sidebar_layout("social-awareness", content)

        return Div(navbar, page_content)

    # ========================================================================
    # RELATIONSHIP SKILLS PAGE
    # ========================================================================

    @rt("/sel/relationship-skills")
    async def sel_relationship_skills(request: Request) -> Any:
        """Relationship Skills knowledge units page"""
        navbar = create_navbar_for_request(request, active_page="sel")

        content = Div(
            H1("Relationship Skills", cls="text-3xl font-bold mb-4"),
            P(
                "Relationship skills involve establishing and maintaining healthy and rewarding relationships "
                "with diverse individuals and groups. This includes communicating clearly, listening actively, "
                "cooperating, resisting inappropriate social pressure, negotiating conflict constructively, "
                "and seeking help when needed.",
                cls="text-lg text-base-content mb-6",
            ),
            H2("Key Knowledge Units", cls="text-2xl font-semibold mb-4"),
            Ul(
                Li("Effective communication strategies", cls="mb-2"),
                Li("Active listening and validation", cls="mb-2"),
                Li("Conflict resolution techniques", cls="mb-2"),
                Li("Teamwork and collaboration", cls="mb-2"),
                Li("Building and maintaining trust", cls="mb-2"),
                cls="list-disc pl-6 text-base-content",
            ),
            H2("Practical Exercises", cls="text-2xl font-semibold mt-6 mb-4"),
            Div(
                Card(
                    CardBody(
                        H3("Communication Role-Play", cls="text-lg font-semibold mb-2"),
                        P("Practice difficult conversations with clear, assertive communication."),
                    ),
                    cls="mb-3",
                ),
                Card(
                    CardBody(
                        H3("Conflict Resolution Scenarios", cls="text-lg font-semibold mb-2"),
                        P("Work through conflict scenarios using win-win problem-solving."),
                    ),
                    cls="mb-3",
                ),
                Card(
                    CardBody(
                        H3("Gratitude Expression", cls="text-lg font-semibold mb-2"),
                        P("Regularly express appreciation to strengthen relationships."),
                    ),
                    cls="mb-3",
                ),
            ),
        )

        page_content = create_sel_sidebar_layout("relationship-skills", content)

        return Div(navbar, page_content)

    # ========================================================================
    # DECISION MAKING PAGE
    # ========================================================================

    @rt("/sel/decision-making")
    async def sel_decision_making(request: Request) -> Any:
        """Decision Making knowledge units page"""
        navbar = create_navbar_for_request(request, active_page="sel")

        content = Div(
            H1("Decision Making", cls="text-3xl font-bold mb-4"),
            P(
                "Responsible decision-making is the ability to make constructive choices about personal behavior "
                "and social interactions based on ethical standards, safety concerns, and social norms. "
                "It includes the realistic evaluation of consequences of various actions and consideration "
                "of the well-being of oneself and others.",
                cls="text-lg text-base-content mb-6",
            ),
            H2("Key Knowledge Units", cls="text-2xl font-semibold mb-4"),
            Ul(
                Li("Ethical reasoning and moral development", cls="mb-2"),
                Li("Analyzing situations and evaluating options", cls="mb-2"),
                Li("Understanding consequences and trade-offs", cls="mb-2"),
                Li("Problem-solving frameworks", cls="mb-2"),
                Li("Reflecting on decisions and learning from outcomes", cls="mb-2"),
                cls="list-disc pl-6 text-base-content",
            ),
            H2("Practical Exercises", cls="text-2xl font-semibold mt-6 mb-4"),
            Div(
                Card(
                    CardBody(
                        H3("Decision Matrix Tool", cls="text-lg font-semibold mb-2"),
                        P("Use weighted criteria to evaluate complex decisions objectively."),
                    ),
                    cls="mb-3",
                ),
                Card(
                    CardBody(
                        H3("Ethical Dilemma Analysis", cls="text-lg font-semibold mb-2"),
                        P("Explore ethical scenarios and practice principled decision-making."),
                    ),
                    cls="mb-3",
                ),
                Card(
                    CardBody(
                        H3("Decision Journal", cls="text-lg font-semibold mb-2"),
                        P("Track important decisions and reflect on their outcomes over time."),
                    ),
                    cls="mb-3",
                ),
            ),
        )

        page_content = create_sel_sidebar_layout("decision-making", content)

        return Div(navbar, page_content)

    # ========================================================================
    # API ROUTES - Adaptive SEL
    # ========================================================================

    @rt("/api/sel/journey")
    @boundary_handler()
    async def get_sel_journey_api(request: Request) -> Result[SELJourney]:
        """
        API: Get authenticated user's complete SEL journey.
        Requires authentication.

        Returns:
            Result[SELJourney]: Journey with progress in all categories
        """
        if not services or not services.adaptive_sel:
            return Result.fail(
                Errors.system("AdaptiveSELService not available", service="AdaptiveSELService")
            )

        # Get authenticated user from session (raises 401 if not authenticated)
        user_uid = require_authenticated_user(request)

        return await services.adaptive_sel.get_sel_journey(user_uid)

    @rt("/api/sel/curriculum/{category}")
    @boundary_handler()
    async def get_personalized_curriculum_api(
        request: Request, category: str, limit: int = 10
    ) -> Result[list[Ku]]:
        """
        API: Get personalized curriculum for authenticated user in SEL category.
        Requires authentication.

        Args:
            category: SEL category (e.g., "self_awareness")
            limit: Maximum number of KUs to return

        Returns:
            Result[List[Ku]]: Personalized curriculum
        """
        if not services or not services.adaptive_sel:
            return Result.fail(
                Errors.system("AdaptiveSELService not available", service="AdaptiveSELService")
            )

        # Get authenticated user from session (raises 401 if not authenticated)
        user_uid = require_authenticated_user(request)

        # Parse category
        try:
            sel_category = SELCategory(category)
        except ValueError:
            return Result.fail(NotFoundError(f"Invalid SEL category: {category}"))

        return await services.adaptive_sel.get_personalized_curriculum(
            user_uid=user_uid, sel_category=sel_category, limit=limit
        )

    logger.info("✅ SEL routes registered (adaptive SEL enabled)")
