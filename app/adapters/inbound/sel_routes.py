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

from fasthtml.common import H3, P, Request

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
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.breadcrumbs import Breadcrumbs
from ui.patterns.page_header import PageHeader
from ui.patterns.section_header import SectionHeader
from ui.utils.htmx_a11y import HTMXOperation, htmx_attrs

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
        """SEL main page - personalized journey overview"""
        logger.info("📚 SEL Overview route accessed")
        user_uid = require_authenticated_user(request)

        # Track page view (non-blocking)
        if services and services.adaptive_sel:
            await services.adaptive_sel.track_page_view(user_uid, None)

        content = Div(
            PageHeader(
                "Your SEL Journey", subtitle="Social Emotional Learning across 5 competencies"
            ),
            # Overall progress - loaded via HTMX
            Div(
                Div(
                    P(
                        "Loading your personalized journey...",
                        cls="text-center py-8 text-base-content/70",
                    ),
                    cls="animate-pulse",
                ),
                hx_get="/api/sel/journey-html",
                hx_trigger="load",
                hx_swap="innerHTML",
                **htmx_attrs(
                    operation=HTMXOperation.LOAD,
                    announce="SEL journey loaded",
                    announce_loading="Loading your personalized journey",
                ),
                id="sel-journey",
            ),
        )

        page_layout = create_sel_sidebar_layout("overview", content)

        return await BasePage(
            page_layout,
            title="SEL - Social Emotional Learning",
            page_type=PageType.STANDARD,
            request=request,
            active_page="sel",
        )

    # ========================================================================
    # SELF AWARENESS PAGE
    # ========================================================================

    @rt("/sel/self-awareness")
    async def sel_self_awareness(request: Request) -> Any:
        """Self Awareness adaptive curriculum page"""
        user_uid = require_authenticated_user(request)

        # Track page view
        if services and services.adaptive_sel:
            await services.adaptive_sel.track_page_view(user_uid, SELCategory.SELF_AWARENESS)

        # Breadcrumbs
        breadcrumbs = Breadcrumbs(
            path=[
                {"uid": "sel", "title": "SEL", "url": "/sel"},
                {"uid": "self-awareness", "title": "Self Awareness", "url": None},
            ]
        )

        content = Div(
            breadcrumbs,
            PageHeader(
                "Self Awareness",
                subtitle="Understanding your thoughts, emotions, and values",
            ),
            # Static description section
            SectionHeader("About This Competency"),
            P(
                "Self-awareness is the ability to accurately recognize your emotions, thoughts, and values "
                "and how they influence your behavior. It involves understanding your strengths, limitations, "
                "and having a well-grounded sense of confidence and optimism.",
                cls="text-base-content/70 mb-6",
            ),
            # Personalized curriculum - loaded via HTMX
            SectionHeader("Your Personalized Curriculum"),
            Div(
                Div(
                    P("Loading personalized curriculum...", cls="text-center py-8"),
                    cls="animate-pulse",
                ),
                hx_get="/api/sel/curriculum-html/self_awareness?limit=10",
                hx_trigger="load",
                hx_swap="innerHTML",
                **htmx_attrs(
                    operation=HTMXOperation.LOAD,
                    announce="Curriculum loaded",
                    announce_loading="Loading personalized curriculum",
                ),
                id="curriculum-list",
                cls="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6",
            ),
            # Static practice exercises
            SectionHeader("Practical Exercises", cls="mt-8"),
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

        page_layout = create_sel_sidebar_layout("self-awareness", content)

        return await BasePage(
            page_layout,
            title="Self Awareness - SEL",
            page_type=PageType.STANDARD,
            request=request,
            active_page="sel",
        )

    # ========================================================================
    # SELF MANAGEMENT PAGE
    # ========================================================================

    @rt("/sel/self-management")
    async def sel_self_management(request: Request) -> Any:
        """Self Management adaptive curriculum page"""
        user_uid = require_authenticated_user(request)

        # Track page view
        if services and services.adaptive_sel:
            await services.adaptive_sel.track_page_view(user_uid, SELCategory.SELF_MANAGEMENT)

        breadcrumbs = Breadcrumbs(
            path=[
                {"uid": "sel", "title": "SEL", "url": "/sel"},
                {"uid": "self-management", "title": "Self Management", "url": None},
            ]
        )

        content = Div(
            breadcrumbs,
            PageHeader("Self Management", subtitle="Managing emotions and achieving goals"),
            SectionHeader("About This Competency"),
            P(
                "Self-management is the ability to successfully regulate your emotions, thoughts, and behaviors "
                "in different situations. This includes managing stress, controlling impulses, motivating yourself, "
                "and setting and working toward personal and academic goals.",
                cls="text-base-content/70 mb-6",
            ),
            SectionHeader("Your Personalized Curriculum"),
            Div(
                Div(
                    P("Loading personalized curriculum...", cls="text-center py-8"),
                    cls="animate-pulse",
                ),
                hx_get="/api/sel/curriculum-html/self_management?limit=10",
                hx_trigger="load",
                hx_swap="innerHTML",
                **htmx_attrs(
                    operation=HTMXOperation.LOAD,
                    announce="Curriculum loaded",
                    announce_loading="Loading personalized curriculum",
                ),
                id="curriculum-list",
                cls="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6",
            ),
            SectionHeader("Practical Exercises", cls="mt-8"),
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

        page_layout = create_sel_sidebar_layout("self-management", content)

        return await BasePage(
            page_layout,
            title="Self Management - SEL",
            page_type=PageType.STANDARD,
            request=request,
            active_page="sel",
        )

    # ========================================================================
    # SOCIAL AWARENESS PAGE
    # ========================================================================

    @rt("/sel/social-awareness")
    async def sel_social_awareness(request: Request) -> Any:
        """Social Awareness adaptive curriculum page"""
        user_uid = require_authenticated_user(request)

        if services and services.adaptive_sel:
            await services.adaptive_sel.track_page_view(user_uid, SELCategory.SOCIAL_AWARENESS)

        breadcrumbs = Breadcrumbs(
            path=[
                {"uid": "sel", "title": "SEL", "url": "/sel"},
                {"uid": "social-awareness", "title": "Social Awareness", "url": None},
            ]
        )

        content = Div(
            breadcrumbs,
            PageHeader("Social Awareness", subtitle="Understanding others and social contexts"),
            SectionHeader("About This Competency"),
            P(
                "Social awareness is the ability to take the perspective of and empathize with others, "
                "including those from diverse backgrounds and cultures. It involves understanding social "
                "and ethical norms for behavior and recognizing family, school, and community resources and supports.",
                cls="text-base-content/70 mb-6",
            ),
            SectionHeader("Your Personalized Curriculum"),
            Div(
                Div(
                    P("Loading personalized curriculum...", cls="text-center py-8"),
                    cls="animate-pulse",
                ),
                hx_get="/api/sel/curriculum-html/social_awareness?limit=10",
                hx_trigger="load",
                hx_swap="innerHTML",
                **htmx_attrs(
                    operation=HTMXOperation.LOAD,
                    announce="Curriculum loaded",
                    announce_loading="Loading personalized curriculum",
                ),
                id="curriculum-list",
                cls="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6",
            ),
            SectionHeader("Practical Exercises", cls="mt-8"),
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

        page_layout = create_sel_sidebar_layout("social-awareness", content)

        return await BasePage(
            page_layout,
            title="Social Awareness - SEL",
            page_type=PageType.STANDARD,
            request=request,
            active_page="sel",
        )

    # ========================================================================
    # RELATIONSHIP SKILLS PAGE
    # ========================================================================

    @rt("/sel/relationship-skills")
    async def sel_relationship_skills(request: Request) -> Any:
        """Relationship Skills adaptive curriculum page"""
        user_uid = require_authenticated_user(request)

        if services and services.adaptive_sel:
            await services.adaptive_sel.track_page_view(user_uid, SELCategory.RELATIONSHIP_SKILLS)

        breadcrumbs = Breadcrumbs(
            path=[
                {"uid": "sel", "title": "SEL", "url": "/sel"},
                {"uid": "relationship-skills", "title": "Relationship Skills", "url": None},
            ]
        )

        content = Div(
            breadcrumbs,
            PageHeader("Relationship Skills", subtitle="Building healthy relationships"),
            SectionHeader("About This Competency"),
            P(
                "Relationship skills involve establishing and maintaining healthy and rewarding relationships "
                "with diverse individuals and groups. This includes communicating clearly, listening actively, "
                "cooperating, resisting inappropriate social pressure, negotiating conflict constructively, "
                "and seeking help when needed.",
                cls="text-base-content/70 mb-6",
            ),
            SectionHeader("Your Personalized Curriculum"),
            Div(
                Div(
                    P("Loading personalized curriculum...", cls="text-center py-8"),
                    cls="animate-pulse",
                ),
                hx_get="/api/sel/curriculum-html/relationship_skills?limit=10",
                hx_trigger="load",
                hx_swap="innerHTML",
                **htmx_attrs(
                    operation=HTMXOperation.LOAD,
                    announce="Curriculum loaded",
                    announce_loading="Loading personalized curriculum",
                ),
                id="curriculum-list",
                cls="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6",
            ),
            SectionHeader("Practical Exercises", cls="mt-8"),
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

        page_layout = create_sel_sidebar_layout("relationship-skills", content)

        return await BasePage(
            page_layout,
            title="Relationship Skills - SEL",
            page_type=PageType.STANDARD,
            request=request,
            active_page="sel",
        )

    # ========================================================================
    # DECISION MAKING PAGE
    # ========================================================================

    @rt("/sel/decision-making")
    async def sel_decision_making(request: Request) -> Any:
        """Decision Making adaptive curriculum page"""
        user_uid = require_authenticated_user(request)

        if services and services.adaptive_sel:
            await services.adaptive_sel.track_page_view(user_uid, SELCategory.DECISION_MAKING)

        breadcrumbs = Breadcrumbs(
            path=[
                {"uid": "sel", "title": "SEL", "url": "/sel"},
                {"uid": "decision-making", "title": "Decision Making", "url": None},
            ]
        )

        content = Div(
            breadcrumbs,
            PageHeader("Decision Making", subtitle="Making responsible choices"),
            SectionHeader("About This Competency"),
            P(
                "Responsible decision-making is the ability to make constructive choices about personal behavior "
                "and social interactions based on ethical standards, safety concerns, and social norms. "
                "It includes the realistic evaluation of consequences of various actions and consideration "
                "of the well-being of oneself and others.",
                cls="text-base-content/70 mb-6",
            ),
            SectionHeader("Your Personalized Curriculum"),
            Div(
                Div(
                    P("Loading personalized curriculum...", cls="text-center py-8"),
                    cls="animate-pulse",
                ),
                hx_get="/api/sel/curriculum-html/decision_making?limit=10",
                hx_trigger="load",
                hx_swap="innerHTML",
                **htmx_attrs(
                    operation=HTMXOperation.LOAD,
                    announce="Curriculum loaded",
                    announce_loading="Loading personalized curriculum",
                ),
                id="curriculum-list",
                cls="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6",
            ),
            SectionHeader("Practical Exercises", cls="mt-8"),
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

        page_layout = create_sel_sidebar_layout("decision-making", content)

        return await BasePage(
            page_layout,
            title="Decision Making - SEL",
            page_type=PageType.STANDARD,
            request=request,
            active_page="sel",
        )

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

    # ========================================================================
    # HTMX API ROUTES - HTML Fragments
    # ========================================================================

    @rt("/api/sel/journey-html")
    async def get_sel_journey_html(request: Request) -> Any:
        """HTMX: Render SEL journey as HTML fragment"""
        user_uid = require_authenticated_user(request)

        if not services or not services.adaptive_sel:
            return Div(
                P(
                    "SEL service unavailable. Please try again later.",
                    cls="text-error text-center py-8",
                ),
                cls="alert alert-error",
            )

        result = await services.adaptive_sel.get_sel_journey(user_uid)

        if result.is_error:
            return Div(
                P(
                    "Unable to load your SEL journey. Please try again.",
                    cls="text-error text-center py-8",
                ),
                cls="alert alert-error",
            )

        journey = result.value

        # Render journey overview with category cards
        from adapters.inbound.sel_components import SELJourneyOverview

        return SELJourneyOverview(journey)

    @rt("/api/sel/curriculum-html/{category}")
    async def get_curriculum_html(request: Request, category: str, limit: int = 10) -> Any:
        """HTMX: Render personalized curriculum as HTML fragment"""
        user_uid = require_authenticated_user(request)

        if not services or not services.adaptive_sel:
            return Div(
                P("SEL service unavailable. Please try again later.", cls="text-error"),
                cls="alert alert-error",
            )

        # Parse category
        try:
            sel_category = SELCategory(category)
        except ValueError:
            return Div(
                P(f"Invalid category: {category}", cls="text-error"), cls="alert alert-error"
            )

        result = await services.adaptive_sel.get_personalized_curriculum(
            user_uid=user_uid, sel_category=sel_category, limit=limit
        )

        if result.is_error:
            return Div(
                P("Unable to load curriculum. Please try again.", cls="text-error"),
                cls="alert alert-error",
            )

        curriculum = result.value

        if not curriculum:
            from ui.patterns.empty_state import EmptyState

            return EmptyState(
                title="No curriculum available yet",
                description="Complete prerequisite knowledge units to unlock content in this area.",
                icon="📚",
            )

        from adapters.inbound.sel_components import AdaptiveKUCard

        return Div(
            *[AdaptiveKUCard(ku) for ku in curriculum],
            cls="grid grid-cols-1 md:grid-cols-2 gap-4",
        )

    logger.info("✅ SEL routes registered (adaptive SEL enabled)")
