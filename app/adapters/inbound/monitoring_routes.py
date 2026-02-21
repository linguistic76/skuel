"""
Monitoring Routes
=================

System health and metrics endpoints for monitoring SKUEL infrastructure.

Phase 3 - January 2026:
- Background worker metrics
- System health checks
- Performance statistics
"""

from typing import Any

from fasthtml.common import JSONResponse
from starlette.requests import Request

from adapters.inbound.auth import require_admin
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.monitoring")


def create_monitoring_routes(app: Any, rt: Any, services: Any) -> list[Any]:
    """
    Create monitoring routes for system health and metrics.

    Args:
        app: FastHTML app instance
        rt: FastHTML router
        services: Services container

    Returns:
        List of routes created
    """

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

    def get_user_service():
        return services.user_service

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
        if not services.embedding_worker:
            return JSONResponse(
                {
                    "status": "unavailable",
                    "message": "Embedding worker not initialized (embeddings service unavailable)",
                },
                status_code=503,
            )

        try:
            metrics = services.embedding_worker.get_metrics()

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
                    "embedding_worker": services.embedding_worker is not None,
                    "embeddings_service": services.embeddings_service is not None,
                    "vector_search": services.vector_search_service is not None,
                },
                "database": {
                    "neo4j_connected": services.neo4j_driver is not None,
                },
            }

            # Add worker metrics if available
            if services.embedding_worker:
                worker_metrics = services.embedding_worker.get_metrics()
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

    logger.info("✅ Monitoring routes created (3 endpoints)")
    return [health_check, embedding_worker_metrics, system_metrics]
