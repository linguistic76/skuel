"""
Ingestion UI Routes - Ingestion Dashboard
==========================================

UI dashboard for the UnifiedIngestionService.

Security:
- Dashboard requires admin role
"""

from adapters.inbound.auth import make_service_getter, require_admin
from adapters.inbound.fasthtml_types import Request
from core.config.settings import get_settings
from core.utils.logging import get_logger
from ui.ingestion import build_ingestion_dashboard
from ui.layouts.base_page import BasePage

logger = get_logger("skuel.routes.ingestion_ui")


def create_ingestion_ui_routes(
    app,
    rt,
    unified_ingestion,
    user_service=None,
):
    """
    Create ingestion UI routes (admin dashboard).

    Args:
        app: FastHTML app instance
        rt: Router instance
        unified_ingestion: The UnifiedIngestionService instance
        user_service: UserService instance for admin role checks

    Returns:
        List of created routes
    """
    routes = []

    get_user_service = make_service_getter(user_service)

    @rt("/ingest")
    @require_admin(get_user_service)
    def ingest_dashboard(request: Request, current_user):
        """Unified ingestion dashboard UI. Requires ADMIN role."""
        return BasePage(
            build_ingestion_dashboard(vault_path=str(get_settings().vault.ingestion_path)),
            title="Content Ingestion",
            request=request,
            active_page="ingest",
        )

    routes.extend([ingest_dashboard])

    logger.info(f"Ingestion UI routes registered: {len(routes)} endpoints")
    return routes


__all__ = ["create_ingestion_ui_routes"]
