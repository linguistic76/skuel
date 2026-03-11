"""Learn UI Routes — Configuration-Driven Registration

Routes:
- GET /learn — Dashboard landing (no sidebar)
- GET /learn/study — Articles + KUs (with sidebar)
- GET /learn/practice — The learning loop (with sidebar)
- GET /learn/pathways — Learning Paths + Steps (with sidebar)
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div, Request

if TYPE_CHECKING:
    from services_bootstrap import Services

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from core.utils.logging import get_logger
from ui.layouts.base_page import BasePage
from ui.learn.layout import create_learn_page

logger = get_logger("skuel.routes.learn")


def create_learn_ui_routes(
    app: FastHTMLApp, rt: RouteDecorator, user_service: Any, **_kwargs: Any
) -> RouteList:
    """Create /learn UI routes.

    Args:
        app: FastHTML app instance
        rt: FastHTML route decorator
        user_service: UserService for context loading
    """

    async def _get_context(user_uid: str) -> Any:
        """Get UserContext or raise ValueError."""
        result = await user_service.get_rich_unified_context(user_uid)
        if result.is_error:
            raise ValueError(f"Failed to load context: {result.error}")
        return result.value

    @rt("/learn")
    async def learn_landing(request: Request) -> Any:
        """Learning dashboard — what to study, practice, and where you are in pathways."""
        user_uid = require_authenticated_user(request)

        try:
            context = await _get_context(user_uid)
        except ValueError as e:
            from fasthtml.common import H1, P

            return await BasePage(
                Div(
                    H1("Error", cls="text-3xl font-bold text-error mb-4"),
                    P(str(e), cls="text-lg text-base-content/70"),
                    cls="flex flex-col items-center justify-center min-h-[400px] p-8",
                ),
                title="Learn",
                request=request,
                active_page="learn",
            )

        from ui.learn.dashboard import LearnDashboardView

        content = LearnDashboardView(context)
        return await BasePage(
            content,
            title="Learn",
            request=request,
            active_page="learn",
        )

    @rt("/learn/study")
    async def learn_study(request: Request) -> Any:
        """Browse Articles and Knowledge Units."""
        user_uid = require_authenticated_user(request)

        try:
            context = await _get_context(user_uid)
        except ValueError as e:
            from fasthtml.common import H1, P

            return await BasePage(
                Div(
                    H1("Error", cls="text-3xl font-bold text-error mb-4"),
                    P(str(e), cls="text-lg text-base-content/70"),
                    cls="flex flex-col items-center justify-center min-h-[400px] p-8",
                ),
                title="Study",
                request=request,
                active_page="learn",
            )

        from ui.learn.study import StudyView

        content = StudyView(context)
        return await create_learn_page(
            content=content,
            active_section="study",
            request=request,
            title="Study - Learn",
        )

    @rt("/learn/practice")
    async def learn_practice(request: Request) -> Any:
        """The learning loop — exercises, submissions, reports, revisions."""
        user_uid = require_authenticated_user(request)

        try:
            context = await _get_context(user_uid)
        except ValueError as e:
            from fasthtml.common import H1, P

            return await BasePage(
                Div(
                    H1("Error", cls="text-3xl font-bold text-error mb-4"),
                    P(str(e), cls="text-lg text-base-content/70"),
                    cls="flex flex-col items-center justify-center min-h-[400px] p-8",
                ),
                title="Practice",
                request=request,
                active_page="learn",
            )

        from ui.learn.practice import PracticeView

        content = PracticeView(context)
        return await create_learn_page(
            content=content,
            active_section="practice",
            request=request,
            title="Practice - Learn",
        )

    @rt("/learn/pathways")
    async def learn_pathways(request: Request) -> Any:
        """Learning Paths and Steps — structured progression."""
        user_uid = require_authenticated_user(request)

        try:
            context = await _get_context(user_uid)
        except ValueError as e:
            from fasthtml.common import H1, P

            return await BasePage(
                Div(
                    H1("Error", cls="text-3xl font-bold text-error mb-4"),
                    P(str(e), cls="text-lg text-base-content/70"),
                    cls="flex flex-col items-center justify-center min-h-[400px] p-8",
                ),
                title="Pathways",
                request=request,
                active_page="learn",
            )

        from ui.learn.pathways import PathwaysView

        content = PathwaysView(context)
        return await create_learn_page(
            content=content,
            active_section="pathways",
            request=request,
            title="Pathways - Learn",
        )

    logger.info("Learn routes registered (/learn, /learn/study, /learn/practice, /learn/pathways)")
    return [learn_landing, learn_study, learn_practice, learn_pathways]


LEARN_CONFIG = DomainRouteConfig(
    domain_name="learn",
    primary_service_attr="user_service",
    api_factory=create_learn_ui_routes,
)


def create_learn_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services", _sync_service: Any = None
) -> RouteList:
    """Wire learn routes via DomainRouteConfig."""
    return register_domain_routes(app, rt, services, LEARN_CONFIG)
