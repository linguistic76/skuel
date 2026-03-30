"""
Upload Route Configuration - Per-User Bulk File Upload
======================================================

DomainRouteConfig-based route registration for user upload feature.
"""

from typing import TYPE_CHECKING

from adapters.inbound.upload_api import create_upload_api_routes
from adapters.inbound.upload_ui import create_upload_ui_routes
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
    from services_bootstrap._container import Services

logger = get_logger("skuel.routes.upload")


def create_upload_routes(
    app: "FastHTMLApp",
    rt: "RouteDecorator",
    services: "Services",
) -> "RouteList":
    """Register upload API and UI routes."""
    upload_service = services.user_upload_service
    if upload_service is None:
        logger.warning("UserUploadService not available — upload routes not registered")
        return []

    routes: list = []
    routes.extend(create_upload_api_routes(app, rt, upload_service))
    routes.extend(create_upload_ui_routes(app, rt, upload_service))

    logger.info("Upload routes registered")
    return routes


__all__ = ["create_upload_routes"]
