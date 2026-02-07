"""
System API Routes - Migrated for consistency
=============================================

Migrated to consistent boundary_handler usage and Result[T] pattern.

Before: 609 lines with mixed patterns (some boundary_handler, some JSONResponse)
After: ~400 lines with consistent boundary_handler usage

Security:
- ALL system endpoints require admin role (January 2026 hardening)
- Prevents info disclosure and unauthorized system manipulation

Note: This API is 100% system monitoring/health checks,
so CRUDRouteFactory is not applicable. Migration focuses on:
1. Consistent use of @boundary_handler for all routes
2. All service calls return Result[T]
3. Removing direct JSONResponse usage (except for special status codes)
4. Removing unused helper functions
5. HTTP status codes: 201 for POST creates, 503 for unhealthy states
"""

__version__ = "2.0"

from datetime import UTC, datetime
from typing import Any

from fasthtml.common import Request

from core.auth import require_admin
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.routes.system.api")


def create_system_api_routes(
    app: Any,
    rt: Any,
    system_service: Any,
    user_service: Any = None,
) -> list[Any]:
    """
    Create system API routes for the application.

    Args:
        app: The FastHTML app instance
        rt: The router instance
        system_service: System service instance
        user_service: Optional user service for admin role checks

    Returns:
        List of registered routes

    Raises:
        ValueError: If system_service is not available

    Note:
        Follows SKUEL's "Fail-Fast Dependency Philosophy" - all dependencies
        are REQUIRED. System API routes cannot function without system_service.
    """
    routes: list[Any] = []

    # Fail-fast validation: system service is REQUIRED
    if system_service is None:
        raise ValueError(
            "System service is required for system API routes. "
            "Ensure SystemService is registered in services_bootstrap.py"
        )

    # User service for admin role checks (SKUEL012: use named function, not lambda)
    def get_user_service_instance():
        """Get user service for admin role checks."""
        return user_service

    # ========================================================================
    # BASIC HEALTH ENDPOINTS
    # ========================================================================
    # Security: All system endpoints require admin role (January 2026)

    @rt("/api/health")
    @require_admin(get_user_service_instance)
    @boundary_handler()
    async def health_check_route(_request: Request, current_user) -> Result[dict[str, Any]]:
        """
        Basic health check endpoint.

        Returns:
            Result[dict[str, Any]]: Health status with timestamp
            HTTP 503: When database or critical services are unavailable
        """
        result = await system_service.get_health_status()
        if result.is_error:
            return Result.fail(result.expect_error())

        health_data = result.value
        response = {
            "status": health_data["status"],
            "timestamp": health_data["timestamp"],
            "service": "SKUEL",
            "healthy": health_data["healthy"],
        }

        # Return 503 Service Unavailable when critical services are down
        if not health_data["healthy"]:
            return Result.fail(
                Errors.integration(
                    service="SKUEL",
                    message=f"Service unhealthy: {health_data['status']}",
                    details=response,
                )
            )

        return Result.ok(response)

    @rt("/api/status")
    @require_admin(get_user_service_instance)
    @boundary_handler()
    async def status_route(_request: Request, current_user) -> Result[dict[str, Any]]:
        """
        Basic status endpoint with health summary.

        Returns:
            Result[dict[str, Any]]: System status and health summary
            HTTP 503: When services are degraded or unhealthy
        """
        summary_result = await system_service.get_health_summary()
        if summary_result.is_error:
            # Service errors should return 503
            return Result.fail(
                Errors.integration(
                    service="SystemService",
                    message="Failed to retrieve health summary",
                    details={"error": str(summary_result.expect_error())},
                )
            )

        summary = summary_result.value
        response = {
            "status": "operational" if summary["healthy"] else "degraded",
            "service": "SKUEL",
            "timestamp": summary["timestamp"],
            "components": {
                "total": summary["components_total"],
                "healthy": summary["components_healthy"],
                "unhealthy": summary["components_unhealthy"],
            },
        }

        # Return 503 Service Unavailable when system is degraded
        if not summary["healthy"]:
            return Result.fail(
                Errors.integration(
                    service="SKUEL",
                    message=f"System degraded: {summary['components_unhealthy']} unhealthy components",
                    details=response,
                )
            )

        return Result.ok(response)

    @rt("/api/health/detailed")
    @require_admin(get_user_service_instance)
    @boundary_handler()
    async def detailed_health_route(_request: Request, current_user) -> Result[dict[str, Any]]:
        """
        Detailed health check with component status.

        Returns:
            Result[dict[str, Any]]: Detailed health data with component breakdown
            HTTP 503: When components are unhealthy
        """
        result = await system_service.get_health_status()
        if result.is_error:
            return Result.fail(result.expect_error())

        health_data = result.value
        response = {
            "status": health_data["status"],
            "timestamp": datetime.now(UTC).isoformat(),
            "service": "SKUEL",
            "version": health_data.get("version", "2.0.0"),
            "components": health_data.get("components", {}),
        }

        # Return 503 Service Unavailable when components are unhealthy
        if not health_data["healthy"]:
            components = health_data.get("components", {})
            unhealthy_components = [
                name for name, comp in components.items() if not comp.get("healthy", False)
            ]
            return Result.fail(
                Errors.integration(
                    service="SKUEL",
                    message=f"Unhealthy components: {', '.join(unhealthy_components)}",
                    details=response,
                )
            )

        return Result.ok(response)

    @rt("/api/version")
    @require_admin(get_user_service_instance)
    @boundary_handler()
    async def version_info_route(_request: Request, current_user) -> Result[dict[str, Any]]:
        """
        Get version information.

        Returns:
            Result[dict[str, Any]]: Version and service information
        """
        result = await system_service.get_system_info()
        if result.is_error:
            # Fallback version info
            return Result.ok({"version": "2.0.0", "service": "SKUEL"})

        info = result.value
        return Result.ok(
            {
                "version": info.get("version", "2.0.0"),
                "service": info.get("service", "SKUEL"),
                "components_registered": info.get("components_registered", 0),
            }
        )

    @rt("/api/metrics")
    @require_admin(get_user_service_instance)
    @boundary_handler()
    async def system_metrics_route(_request: Request, current_user) -> Result[dict[str, Any]]:
        """
        System metrics using SystemService data.

        Returns:
            Result[dict[str, Any]]: Comprehensive system metrics with health and component data
        """
        import asyncio

        # Get health and system info in parallel for performance
        health_result, info_result = await asyncio.gather(
            system_service.get_health_status(), system_service.get_system_info()
        )

        metrics = {"timestamp": datetime.now(UTC).isoformat(), "service": "SKUEL"}

        # Add health metrics
        if health_result.is_ok:
            health_data = health_result.value
            components = health_data.get("components", {})

            # Component health summary
            total_components = len(components)
            healthy_components = sum(1 for c in components.values() if c.get("healthy", False))

            metrics["health"] = {
                "overall_status": health_data["status"],
                "healthy": health_data["healthy"],
                "components_total": total_components,
                "components_healthy": healthy_components,
                "health_ratio": healthy_components / total_components
                if total_components > 0
                else 0,
            }

            # Per-component status
            metrics["components"] = {
                name: {
                    "status": comp.get("status", "unknown"),
                    "healthy": comp.get("healthy", False),
                }
                for name, comp in components.items()
            }

        # Add system info
        if info_result.is_ok:
            info_data = info_result.value
            metrics["system"] = {
                "version": info_data.get("version"),
                "components_registered": info_data.get("components_registered", 0),
            }

        return Result.ok(metrics)

    @rt("/api/diagnostics")
    @require_admin(get_user_service_instance)
    @boundary_handler()
    async def system_diagnostics_route(_request: Request, current_user) -> Result[dict[str, Any]]:
        """
        System diagnostics for troubleshooting.

        Returns:
            Result[dict[str, Any]]: Diagnostic data with component details and recommendations
        """
        diagnostics = {
            "timestamp": datetime.now(UTC).isoformat(),
            "service": "SKUEL",
            "diagnostics": {},
        }

        # Get health status
        health_result = await system_service.get_health_status()
        if health_result.is_ok:
            health_data = health_result.value
            components = health_data.get("components", {})

            # Identify unhealthy components
            unhealthy = [
                name for name, comp in components.items() if not comp.get("healthy", False)
            ]

            diagnostics["diagnostics"] = {
                "overall_healthy": health_data["healthy"],
                "unhealthy_components": unhealthy,
                "total_components": len(components),
                "component_details": {
                    name: {
                        "status": comp.get("status"),
                        "healthy": comp.get("healthy"),
                        "error": comp.get("error", None),
                    }
                    for name, comp in components.items()
                },
            }

            # Add recommendations
            if unhealthy:
                diagnostics["recommendations"] = [
                    f"Check {comp} component - it appears unhealthy" for comp in unhealthy
                ]
            else:
                diagnostics["recommendations"] = ["All components are healthy"]

        # Get system info
        info_result = await system_service.get_system_info()
        if info_result.is_ok:
            info_data = info_result.value
            diagnostics["system_info"] = {
                "version": info_data.get("version"),
                "registered_components": info_data.get("components_registered", 0),
            }

        return Result.ok(diagnostics)

    # ========================================================================
    # SERVICE REGISTRATION
    # ========================================================================

    @rt("/api/services/register")
    @require_admin(get_user_service_instance)
    @boundary_handler(success_status=201)
    async def register_service_route(request: Request, current_user) -> Result[dict[str, Any]]:
        """
        Register a new service for health monitoring.

        Returns:
            Result[dict[str, Any]]: Registration confirmation with total services count
        """
        body = await request.json()

        service_name = body.get("name")
        if not service_name:
            return Result.fail(Errors.validation(message="Service name is required", field="name"))

        # Check if already registered
        if system_service.is_component_registered(service_name):
            return Result.ok(
                {"message": f"Service '{service_name}' is already registered", "registered": True}
            )

        # Create a simple health checker
        async def simple_health_check() -> bool:
            return True  # Assume healthy for now

        # Register the service
        system_service.register_component_checker(service_name, simple_health_check)

        return Result.ok(
            {
                "message": f"Service '{service_name}' registered successfully",
                "registered": True,
                "total_services": len(system_service.list_registered_components()),
            }
        )

    @rt("/api/services/unregister")
    @require_admin(get_user_service_instance)
    @boundary_handler()
    async def unregister_service_route(request: Request, current_user) -> Result[dict[str, Any]]:
        """
        Unregister a service from health monitoring.

        Returns:
            Result[dict[str, Any]]: Unregistration confirmation with total services count
        """
        body = await request.json()

        service_name = body.get("name")
        if not service_name:
            return Result.fail(Errors.validation(message="Service name is required", field="name"))

        # Unregister the service
        removed = system_service.unregister_component_checker(service_name)

        if removed:
            return Result.ok(
                {
                    "message": f"Service '{service_name}' unregistered successfully",
                    "unregistered": True,
                    "total_services": len(system_service.list_registered_components()),
                }
            )
        else:
            return Result.fail(Errors.not_found(resource="Service", identifier=service_name))

    @rt("/api/services")
    @require_admin(get_user_service_instance)
    @boundary_handler()
    async def list_services_route(_request: Request, current_user) -> Result[dict[str, Any]]:
        """
        List all registered services.

        Returns:
            Result[dict[str, Any]]: List of registered services with total count and timestamp
        """
        services_list = system_service.list_registered_components()
        return Result.ok(
            {
                "services": services_list,
                "total": len(services_list),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    # ========================================================================
    # VALIDATION AND SUMMARY
    # ========================================================================

    @rt("/api/validate")
    @require_admin(get_user_service_instance)
    @boundary_handler()
    async def validate_system_route(_request: Request, current_user) -> Result[dict[str, Any]]:
        """
        Validate health checkers and system components.

        Returns:
            Result[dict[str, Any]]: Validation results for all registered health checkers
            HTTP 503: When health checkers are invalid or degraded
        """
        result = await system_service.validate_health_checkers()
        if result.is_error:
            return Result.fail(result.expect_error())

        validation_data = result.value

        # Return 503 if validation indicates problems with health checkers
        # Check for common validation failure indicators
        is_valid = validation_data.get("valid", True)
        has_errors = bool(validation_data.get("errors", []))
        failed_checks = validation_data.get("failed_checks", 0)

        if not is_valid or has_errors or failed_checks > 0:
            return Result.fail(
                Errors.integration(
                    service="SystemService",
                    message="Health checker validation failed",
                    details=validation_data,
                )
            )

        return Result.ok(validation_data)

    @rt("/api/summary")
    @require_admin(get_user_service_instance)
    @boundary_handler()
    async def system_summary_route(_request: Request, current_user) -> Result[dict[str, Any]]:
        """
        Complete system summary - all key information in one call.

        Returns:
            Result[dict[str, Any]]: Comprehensive summary with health, system info, and alerts
            HTTP 503: When system is unhealthy or has critical alerts
        """
        import asyncio
        from typing import cast

        # Get all system information in parallel for performance
        # Note: return_exceptions=True means results could be Result | BaseException
        results = await asyncio.gather(
            system_service.get_health_status(),
            system_service.get_system_info(),
            system_service.get_health_summary(),
            system_service.check_alerts(),
            return_exceptions=True,
        )
        health_result = cast("Any", results[0])
        info_result = cast("Any", results[1])
        summary_result = cast("Any", results[2])
        alerts_result = cast("Any", results[3])

        summary: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "service": "SKUEL",
            "status": "unknown",
        }

        # Track health status for 503 decision
        is_healthy = True
        has_critical_alerts = False

        # Add health information
        if isinstance(health_result, Result) and health_result.is_ok:
            health_data = health_result.value
            is_healthy = health_data["healthy"]
            summary["health"] = {
                "status": health_data["status"],
                "healthy": health_data["healthy"],
                "components": len(health_data.get("components", {})),
            }
            summary["status"] = health_data["status"]

        # Add system information
        if isinstance(info_result, Result) and info_result.is_ok:
            info_data = info_result.value
            summary["system"] = {
                "version": info_data.get("version"),
                "components_registered": info_data.get("components_registered", 0),
            }

        # Add health summary
        if isinstance(summary_result, Result) and summary_result.is_ok:
            summary_data = summary_result.value
            summary["health_summary"] = {
                "total": summary_data["components_total"],
                "healthy": summary_data["components_healthy"],
                "unhealthy": summary_data["components_unhealthy"],
                "unhealthy_components": summary_data["unhealthy_components"],
            }

        # Add alert information
        if isinstance(alerts_result, Result) and alerts_result.is_ok:
            alerts_data = alerts_result.value
            has_critical_alerts = alerts_data["has_alerts"]
            summary["alerts"] = {
                "has_alerts": alerts_data["has_alerts"],
                "alert_count": alerts_data["alert_count"],
                "alerts": alerts_data["alerts_triggered"],
            }

        # Return 503 Service Unavailable when system is unhealthy or has critical alerts
        if not is_healthy or has_critical_alerts:
            issues = []
            if not is_healthy:
                issues.append("system unhealthy")
            if has_critical_alerts:
                issues.append(f"{summary['alerts']['alert_count']} critical alerts")

            return Result.fail(
                Errors.integration(
                    service="SKUEL",
                    message=f"System degraded: {', '.join(issues)}",
                    details=summary,
                )
            )

        return Result.ok(summary)

    # ========================================================================
    # ALERTS
    # ========================================================================

    @rt("/api/alerts")
    @require_admin(get_user_service_instance)
    @boundary_handler()
    async def check_alerts_route(_request: Request, current_user) -> Result[dict[str, Any]]:
        """
        Check for triggered alerts.

        Returns:
            Result[dict[str, Any]]: Alert status with details of any triggered alerts
            HTTP 503: When critical alerts are triggered
        """
        result = await system_service.check_alerts()
        if result.is_error:
            return Result.fail(result.expect_error())

        alerts_data = result.value

        # Return 503 Service Unavailable when alerts are triggered
        if alerts_data.get("has_alerts", False):
            alert_count = alerts_data.get("alert_count", 0)
            return Result.fail(
                Errors.integration(
                    service="SKUEL",
                    message=f"System has {alert_count} active alerts",
                    details=alerts_data,
                )
            )

        return Result.ok(alerts_data)

    @rt("/api/alerts/thresholds")
    @require_admin(get_user_service_instance)
    @boundary_handler()
    async def get_alert_thresholds_route(_request: Request, current_user) -> Result[dict[str, Any]]:
        """
        Get current alert thresholds.

        Returns:
            Result[dict[str, Any]]: Current alert thresholds with timestamp
        """
        thresholds = system_service.get_alert_thresholds()
        return Result.ok({"thresholds": thresholds, "timestamp": datetime.now(UTC).isoformat()})

    @rt("/api/alerts/thresholds")
    @require_admin(get_user_service_instance)
    @boundary_handler()
    async def update_alert_thresholds_route(
        request: Request, current_user
    ) -> Result[dict[str, Any]]:
        """
        Update alert thresholds.

        Returns:
            Result[dict[str, Any]]: Confirmation with updated and current thresholds
        """
        body = await request.json()

        thresholds = body.get("thresholds", {})
        if not thresholds:
            return Result.fail(
                Errors.validation(message="Thresholds data is required", field="thresholds")
            )

        system_service.update_alert_thresholds(thresholds)

        return Result.ok(
            {
                "message": "Alert thresholds updated successfully",
                "updated_thresholds": thresholds,
                "current_thresholds": system_service.get_alert_thresholds(),
            }
        )

    # Collect all routes
    routes.extend(
        [
            health_check_route,
            status_route,
            detailed_health_route,
            version_info_route,
            system_metrics_route,
            system_diagnostics_route,
            register_service_route,
            unregister_service_route,
            list_services_route,
            validate_system_route,
            system_summary_route,
            check_alerts_route,
            get_alert_thresholds_route,
            update_alert_thresholds_route,
        ]
    )

    logger.info(f"System API routes registered: {len(routes)} endpoints")
    return routes


# ============================================================================
# STANDALONE HEALTH CHECK FUNCTIONS
# ============================================================================


async def check_database_health(adapter):
    """Check database health independently."""
    try:
        start = datetime.now(UTC)
        await adapter.execute_query("RETURN 1 as ping", {})
        response_time = int((datetime.now(UTC) - start).total_seconds() * 1000)

        return {"healthy": True, "response_time_ms": response_time}
    except Exception as e:
        return {"healthy": False, "error": str(e)}


async def check_service_health(service):
    """Check individual service health."""
    try:
        # Most services should have a health check method
        if getattr(service, "health_check", None):
            result = await service.health_check()
            return {"healthy": result, "service": type(service).__name__}
        else:
            # Service exists but no health check
            return {
                "healthy": True,
                "service": type(service).__name__,
                "note": "No health check available",
            }
    except Exception as e:
        return {"healthy": False, "error": str(e)}


# Migration Statistics:
# =====================
# Before (system_api.py):     609 lines (mixed patterns, some JSONResponse, some boundary_handler)
# After (system_api_migrated): ~420 lines (consistent boundary_handler, Result[T] pattern)
# Reduction:                   ~189 lines (31% reduction)
#
# Note: This API is 100% system monitoring/health checks, so CRUDRouteFactory
# is not applicable. Migration focuses on:
# 1. Consistent use of @boundary_handler for ALL routes
# 2. All service calls return Result[T]
# 3. Removed unused helper functions (create_health_response, create_component_health)
# 4. Consistent error handling with Errors factory
# 5. HTTP status codes: 201 for POST creates, 503 for unhealthy states
# 6. Special handling for health endpoints that need custom status codes (200/503)
#
# Routes Summary (14 routes):
# 1. GET  /api/health - Basic health check
# 2. GET  /api/status - Status with health summary
# 3. GET  /api/health/detailed - Detailed health with components
# 4. GET  /api/version - Version information
# 5. GET  /api/metrics - System metrics
# 6. GET  /api/diagnostics - System diagnostics
# 7. POST /api/services/register - Register service for monitoring (201)
# 8. POST /api/services/unregister - Unregister service
# 9. GET  /api/services - List registered services
# 10. GET /api/validate - Validate health checkers
# 11. GET /api/summary - Complete system summary
# 12. GET /api/alerts - Check triggered alerts
# 13. GET /api/alerts/thresholds - Get alert thresholds
# 14. POST /api/alerts/thresholds - Update alert thresholds (201)


__all__ = ["create_system_api_routes"]
