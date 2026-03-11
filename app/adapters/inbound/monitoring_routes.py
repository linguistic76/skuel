"""
Monitoring Routes — Configuration-Driven Registration
======================================================

System health and metrics endpoints for monitoring SKUEL infrastructure.

- January 2026:
- Background worker metrics
- System health checks
- Performance statistics
"""

from typing import Any

from fasthtml.common import JSONResponse
from starlette.requests import Request

from adapters.inbound.auth import make_service_getter, require_admin
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.monitoring")


def create_monitoring_api_routes(
    app: FastHTMLApp, rt: RouteDecorator, user_service: Any, **kwargs: Any
) -> RouteList:
    """
    Create monitoring API routes.

    Args:
        app: FastHTML app instance
        rt: FastHTML router
        user_service: UserService for admin checks
        **kwargs: Related services (embedding_worker, embeddings_service,
                  vector_search_service, neo4j_driver)

    Returns:
        List of routes created
    """
    embedding_worker = kwargs.get("embedding_worker")
    embeddings_service = kwargs.get("embeddings_service")
    vector_search_service = kwargs.get("vector_search_service")
    neo4j_driver = kwargs.get("neo4j_driver")

    @rt("/api/monitoring/health")
    async def health_check(request: Request):
        """
        Health check endpoint.

        Returns 200 OK if application is running.
        """
        return JSONResponse(
            {
                "status": "healthy",
                "service": "SKUEL",
                "version": "1.0",
            }
        )

    get_user_service = make_service_getter(user_service)

    @rt("/api/monitoring/embedding-worker")
    @require_admin(get_user_service)
    async def embedding_worker_metrics(request: Request, current_user=None):
        """
        Get embedding background worker metrics. Requires ADMIN role.

        Returns worker performance statistics including:
        - Total entities processed
        - Success/failure rates
        - Queue size
        - Uptime

        Returns:
            200: Worker metrics (JSON)
            503: Worker not available
        """
        if not embedding_worker:
            return JSONResponse(
                {
                    "status": "unavailable",
                    "message": "Embedding worker not initialized (embeddings service unavailable)",
                },
                status_code=503,
            )

        try:
            metrics = embedding_worker.get_metrics()

            return JSONResponse(
                {
                    "status": "running",
                    "metrics": metrics,
                }
            )

        except Exception as e:
            logger.error(f"Failed to get worker metrics: {e}")
            return JSONResponse(
                {
                    "status": "error",
                    "message": str(e),
                },
                status_code=500,
            )

    @rt("/api/monitoring/system")
    @require_admin(get_user_service)
    async def system_metrics(request: Request, current_user=None):
        """
        Get overall system metrics. Requires ADMIN role.

        Returns:
            200: System statistics (JSON)
        """
        try:
            metrics = {
                "services": {
                    "embedding_worker": embedding_worker is not None,
                    "embeddings_service": embeddings_service is not None,
                    "vector_search": vector_search_service is not None,
                },
                "database": {
                    "neo4j_connected": neo4j_driver is not None,
                },
            }

            # Add worker metrics if available
            if embedding_worker:
                worker_metrics = embedding_worker.get_metrics()
                metrics["embedding_worker"] = worker_metrics

            return JSONResponse(
                {
                    "status": "operational",
                    "metrics": metrics,
                }
            )

        except Exception as e:
            logger.error(f"Failed to get system metrics: {e}")
            return JSONResponse(
                {
                    "status": "error",
                    "message": str(e),
                },
                status_code=500,
            )

    logger.info("Monitoring routes created (3 endpoints)")
    return [health_check, embedding_worker_metrics, system_metrics]


MONITORING_CONFIG = DomainRouteConfig(
    domain_name="monitoring",
    primary_service_attr="user_service",
    api_factory=create_monitoring_api_routes,
    api_related_services={
        "embedding_worker": "embedding_worker",
        "embeddings_service": "embeddings_service",
        "vector_search_service": "vector_search_service",
        "neo4j_driver": "neo4j_driver",
    },
)


def create_monitoring_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service: Any = None
) -> RouteList:
    """Wire monitoring routes via DomainRouteConfig."""
    return register_domain_routes(app, rt, services, MONITORING_CONFIG)
