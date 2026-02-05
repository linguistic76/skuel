"""
SEL UI Routes
=============

UI routes and presentation logic for SEL (Social Emotional Learning) domain.

SEL is the paramount feature of SKUEL, providing personalized learning
experiences across the 5 SEL competencies.

UI Routes:
- GET /sel - SEL journey overview (adaptive)
- GET /sel/self-awareness - Self Awareness curriculum
- GET /sel/self-management - Self Management curriculum
- GET /sel/social-awareness - Social Awareness curriculum
- GET /sel/relationship-skills - Relationship Skills curriculum
- GET /sel/decision-making - Decision Making curriculum

Architecture:
    - Layout: Profile-style sidebar (profile_sidebar.css / profile_sidebar.js)
    - Components: sel_components.py (SELJourneyOverview, AdaptiveKUCard)
    - CSS: profile_sidebar.css (included via BasePage extra_css)
    - JavaScript: profile_sidebar.js (loaded globally via base_page.py)
"""

from typing import Any

from fasthtml.common import H3, Button, Li, Main, NotStr, P, Request, Span, Ul
from fasthtml.common import A as Anchor

from core.auth import require_authenticated_user
from core.models.shared_enums import SELCategory
from core.ui.daisy_components import Card, CardBody, Div
from core.utils.logging import get_logger
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.breadcrumbs import Breadcrumbs
from ui.patterns.page_header import PageHeader
from ui.patterns.section_header import SectionHeader
from ui.utils.htmx_a11y import HTMXOperation, htmx_attrs

logger = get_logger("skuel.routes.sel.ui")

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


def _sel_sidebar(active_slug: str):
    """Build the SEL sidebar, mirroring the profile sidebar pattern."""
    chevron_svg = NotStr(
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
        '<path d="M15 18l-6-6 6-6"></path>'
        "</svg>"
    )

    menu_items = [
        Li(
            Anchor(
                title,
                href=href,
                cls=f"{'menu-active' if slug == active_slug else ''}",
                **{
                    "hx-boost": "false",
                    "onclick": "if(window.innerWidth<=1024)toggleProfileSidebar()",
                },
            )
        )
        for title, href, slug, _desc in SEL_MENU_ITEMS
    ]

    sidebar_nav = Ul(
        Li(
            Anchor(
                "SEL",
                href="/sel",
                cls="text-xl font-bold text-primary hover:text-primary-focus",
                id="sel-sidebar-heading",
                **{"hx-boost": "false"},
            ),
            P("Social Emotional Learning", cls="text-xs opacity-60 mt-1"),
            cls="px-4 py-4 sidebar-header-text",
        ),
        Li(cls="divider my-0"),
        *menu_items,
        cls="menu bg-white min-h-full w-full p-4 sidebar-nav",
        id="sel-sidebar-nav",
    )

    return Div(
        Div(
            Button(
                chevron_svg,
                onclick="toggleProfileSidebar()",
                cls="sidebar-toggle",
                title="Toggle Sidebar",
                type="button",
                aria_label="Toggle SEL sidebar",
                aria_expanded="false",
                aria_controls="sel-sidebar-nav",
            ),
            sidebar_nav,
            cls="sidebar-inner",
        ),
        cls="profile-sidebar",
        id="profile-sidebar",
        role="dialog",
        aria_modal="false",
        aria_labelledby="sel-sidebar-heading",
    )


def _sel_page_layout(active_slug: str, content: Any):
    """Assemble the full profile-container shell around SEL content."""
    return Div(
        Div(
            cls="profile-overlay",
            id="profile-overlay",
            onclick="toggleProfileSidebar()",
        ),
        _sel_sidebar(active_slug),
        Div(
            id="sidebar-sr-announcements",
            role="status",
            aria_live="polite",
            cls="sr-only",
        ),
        Div(
            Div(
                Span("☰", aria_hidden="true"),
                Span("Menu"),
                cls="btn btn-ghost mobile-menu-button mb-4",
                onclick="toggleProfileSidebar()",
                role="button",
                tabindex="0",
                aria_label="Open SEL navigation",
                aria_expanded="false",
                aria_controls="profile-sidebar",
            ),
            Main(
                Div(content, cls="max-w-6xl mx-auto"),
                cls="p-6 lg:p-8",
            ),
            cls="profile-content",
            id="profile-content",
        ),
        cls="profile-container",
    )


def create_sel_ui_routes(
    _app: Any,
    rt: Any,
    adaptive_sel_service: Any,
    services: Any = None,
) -> list[Any]:
    """
    Create SEL UI routes.

    Args:
        _app: FastHTML app instance (unused)
        rt: FastHTML route decorator
        adaptive_sel_service: AdaptiveSEL service facade
        services: Services container (optional, for future use)

    Returns:
        List of registered route functions
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
        if adaptive_sel_service:
            await adaptive_sel_service.track_page_view(user_uid, None)

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

        page_layout = _sel_page_layout("overview", content)

        return await BasePage(
            page_layout,
            title="SEL - Social Emotional Learning",
            page_type=PageType.STANDARD,
            request=request,
            active_page="sel",
            extra_css=["/static/css/profile_sidebar.css"],
        )

    # ========================================================================
    # SELF AWARENESS PAGE
    # ========================================================================

    @rt("/sel/self-awareness")
    async def sel_self_awareness(request: Request) -> Any:
        """Self Awareness adaptive curriculum page"""
        user_uid = require_authenticated_user(request)

        # Track page view
        if adaptive_sel_service:
            await adaptive_sel_service.track_page_view(user_uid, SELCategory.SELF_AWARENESS)

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

        page_layout = _sel_page_layout("self-awareness", content)

        return await BasePage(
            page_layout,
            title="Self Awareness - SEL",
            page_type=PageType.STANDARD,
            request=request,
            active_page="sel",
            extra_css=["/static/css/profile_sidebar.css"],
        )

    # ========================================================================
    # SELF MANAGEMENT PAGE
    # ========================================================================

    @rt("/sel/self-management")
    async def sel_self_management(request: Request) -> Any:
        """Self Management adaptive curriculum page"""
        user_uid = require_authenticated_user(request)

        # Track page view
        if adaptive_sel_service:
            await adaptive_sel_service.track_page_view(user_uid, SELCategory.SELF_MANAGEMENT)

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

        page_layout = _sel_page_layout("self-management", content)

        return await BasePage(
            page_layout,
            title="Self Management - SEL",
            page_type=PageType.STANDARD,
            request=request,
            active_page="sel",
            extra_css=["/static/css/profile_sidebar.css"],
        )

    # ========================================================================
    # SOCIAL AWARENESS PAGE
    # ========================================================================

    @rt("/sel/social-awareness")
    async def sel_social_awareness(request: Request) -> Any:
        """Social Awareness adaptive curriculum page"""
        user_uid = require_authenticated_user(request)

        if adaptive_sel_service:
            await adaptive_sel_service.track_page_view(user_uid, SELCategory.SOCIAL_AWARENESS)

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

        page_layout = _sel_page_layout("social-awareness", content)

        return await BasePage(
            page_layout,
            title="Social Awareness - SEL",
            page_type=PageType.STANDARD,
            request=request,
            active_page="sel",
            extra_css=["/static/css/profile_sidebar.css"],
        )

    # ========================================================================
    # RELATIONSHIP SKILLS PAGE
    # ========================================================================

    @rt("/sel/relationship-skills")
    async def sel_relationship_skills(request: Request) -> Any:
        """Relationship Skills adaptive curriculum page"""
        user_uid = require_authenticated_user(request)

        if adaptive_sel_service:
            await adaptive_sel_service.track_page_view(user_uid, SELCategory.RELATIONSHIP_SKILLS)

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

        page_layout = _sel_page_layout("relationship-skills", content)

        return await BasePage(
            page_layout,
            title="Relationship Skills - SEL",
            page_type=PageType.STANDARD,
            request=request,
            active_page="sel",
            extra_css=["/static/css/profile_sidebar.css"],
        )

    # ========================================================================
    # DECISION MAKING PAGE
    # ========================================================================

    @rt("/sel/decision-making")
    async def sel_decision_making(request: Request) -> Any:
        """Decision Making adaptive curriculum page"""
        user_uid = require_authenticated_user(request)

        if adaptive_sel_service:
            await adaptive_sel_service.track_page_view(
                user_uid, SELCategory.RESPONSIBLE_DECISION_MAKING
            )

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
                hx_get="/api/sel/curriculum-html/responsible_decision_making?limit=10",
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

        page_layout = _sel_page_layout("decision-making", content)

        return await BasePage(
            page_layout,
            title="Decision Making - SEL",
            page_type=PageType.STANDARD,
            request=request,
            active_page="sel",
            extra_css=["/static/css/profile_sidebar.css"],
        )

    logger.info("SEL UI routes registered (6 pages)")

    return [
        sel_main,
        sel_self_awareness,
        sel_self_management,
        sel_social_awareness,
        sel_relationship_skills,
        sel_decision_making,
    ]


__all__ = ["create_sel_ui_routes"]
