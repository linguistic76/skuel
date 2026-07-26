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

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fasthtml.common import Request

from adapters.inbound.auth import make_service_getter, require_admin
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from core.ports.query_types import AlertCheckResult, HealthCheckValidation
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import SystemServiceOperations

logger = get_logger("skuel.routes.system.api")


def create_system_api_routes(
    app: Any,
    rt: Any,
    system_service: "SystemServiceOperations",
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

    get_user_service = make_service_getter(user_service)

    # ========================================================================
    # PUBLIC HEALTH PROBES (no auth — for load-balancers and k8s probes)
    # ========================================================================

    @rt("/health")
    @boundary_handler()
    async def liveness_probe(
        request: Request,
    ) -> Result[
        dict[str, Any]
    ]:  # skuel-lint: disable=SKUEL029 -- wrapped by @boundary_handler() which awaits the handler unconditionally (boundary.py)
        """Liveness probe: returns 200 if the process is running.

        Always succeeds — failure here means the process should be restarted.
        Safe for load-balancers, Kubernetes liveness probes, and uptime monitors.
        """
        return Result.ok({"status": "ok", "service": "SKUEL"})

    @rt("/health/ready")
    @boundary_handler()
    async def readiness_probe(request: Request) -> Result[dict[str, Any]]:
        """Readiness probe: returns 200 only when the database is reachable.

        Returns 503 when Neo4j is unreachable so the load-balancer can shed
        traffic rather than routing to a degraded instance.
        """
        result = await system_service.get_health_status()
        if result.is_error:
            return Result.fail(
                Errors.integration(
                    service="SKUEL",
                    message="Health check failed",
                )
            )
        health = result.value
        if not health.get("healthy", False):
            return Result.fail(
                Errors.integration(
                    service="SKUEL",
                    message=f"Service not ready: {health.get('status', 'unknown')}",
                )
            )
        return Result.ok({"status": "ready", "service": "SKUEL"})

    routes.extend([liveness_probe, readiness_probe])

    # ========================================================================
    # BASIC HEALTH ENDPOINTS
    # ========================================================================
    # Security: All system endpoints require admin role (January 2026)

    @rt("/api/health")
    @require_admin(get_user_service)
    @boundary_handler()
    async def health_check_route(request: Request, current_user) -> Result[dict[str, Any]]:
        """
        Basic health check endpoint.

        Returns:
            Result[dict[str, Any]]: Health status with timestamp
            HTTP 503: When database or critical services are unavailable
        """
        result = await system_service.get_health_status()
        if result.is_error:
            return Result.fail(result)

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
    @require_admin(get_user_service)
    @boundary_handler()
    async def status_route(request: Request, current_user) -> Result[dict[str, Any]]:
        """
        Basic status endpoint with health summary.

        Returns:
            Result[dict[str, Any]]: System status and health summary
            HTTP 503: When services are degraded or unhealthy
        """
        summary_result = await system_service.get_health_summary()
        if summary_result.is_error:
            # Service errors should return 503
            return Result.fail(summary_result)

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
    @require_admin(get_user_service)
    @boundary_handler()
    async def detailed_health_route(request: Request, current_user) -> Result[dict[str, Any]]:
        """
        Detailed health check with component status.

        Returns:
            Result[dict[str, Any]]: Detailed health data with component breakdown
            HTTP 503: When components are unhealthy
        """
        result = await system_service.get_health_status()
        if result.is_error:
            return Result.fail(result)

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
    @require_admin(get_user_service)
    @boundary_handler()
    async def version_info_route(request: Request, current_user) -> Result[dict[str, Any]]:
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

    @rt("/api/diagnostics")
    @require_admin(get_user_service)
    @boundary_handler()
    async def system_diagnostics_route(request: Request, current_user) -> Result[dict[str, Any]]:
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
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler(success_status=201)
    async def register_service_route(request: Request, current_user) -> Result[dict[str, Any]]:
        """
        Register a new service for health monitoring.

        Returns:
            Result[dict[str, Any]]: Registration confirmation with total services count
        """
        body = await request.json()

        service_name = body.get("name")
        if not service_name or not isinstance(service_name, str):
            return Result.fail(Errors.validation(message="Service name is required", field="name"))
        if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", service_name):
            return Result.fail(
                Errors.validation(
                    "Service name must be 1-64 alphanumeric, underscore, or hyphen characters",
                    field="name",
                    value=service_name,
                )
            )

        # Check if already registered
        if system_service.is_component_registered(service_name):
            return Result.ok(
                {"message": f"Service '{service_name}' is already registered", "registered": True}
            )

        # Create a simple health checker
        async def simple_health_check() -> (
            bool
        ):  # skuel-lint: disable=SKUEL029 -- registered as an awaited health-checker (system_service awaits checkers unconditionally)
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
    @csrf_protected
    @require_admin(get_user_service)
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
    @require_admin(get_user_service)
    @boundary_handler()
    async def list_services_route(
        request: Request, current_user
    ) -> Result[
        dict[str, Any]
    ]:  # skuel-lint: disable=SKUEL029 -- wrapped by @boundary_handler() which awaits the handler unconditionally (boundary.py)
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
    @require_admin(get_user_service)
    @boundary_handler()
    async def validate_system_route(
        request: Request, current_user
    ) -> Result[HealthCheckValidation]:
        """
        Validate health checkers and system components.

        Returns:
            Result[HealthCheckValidation]: Validation results for all registered health checkers
            HTTP 503: When health checkers are invalid or degraded
        """
        result = await system_service.validate_health_checkers()
        if result.is_error:
            return Result.fail(result)

        validation_data = result.value

        # Return 503 if validation indicates problems with health checkers
        if not validation_data["all_valid"] or validation_data["invalid_checkers"] > 0:
            return Result.fail(
                Errors.integration(
                    service="SystemService",
                    message="Health checker validation failed",
                    details=validation_data,
                )
            )

        return Result.ok(validation_data)

    @rt("/api/summary")
    @require_admin(get_user_service)
    @boundary_handler()
    async def system_summary_route(request: Request, current_user) -> Result[dict[str, Any]]:
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
    @require_admin(get_user_service)
    @boundary_handler()
    async def check_alerts_route(request: Request, current_user) -> Result[AlertCheckResult]:
        """
        Check for triggered alerts.

        Returns:
            Result[AlertCheckResult]: Alert status with details of any triggered alerts
            HTTP 503: When critical alerts are triggered
        """
        result = await system_service.check_alerts()
        if result.is_error:
            return Result.fail(result)

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

    @rt("/api/alerts/thresholds", methods=["GET"])
    @require_admin(get_user_service)
    @boundary_handler()
    async def get_alert_thresholds_route(
        request: Request, current_user
    ) -> Result[
        dict[str, Any]
    ]:  # skuel-lint: disable=SKUEL029 -- wrapped by @boundary_handler() which awaits the handler unconditionally (boundary.py)
        """
        Get current alert thresholds.

        Returns:
            Result[dict[str, Any]]: Current alert thresholds with timestamp
        """
        thresholds = system_service.get_alert_thresholds()
        return Result.ok({"thresholds": thresholds, "timestamp": datetime.now(UTC).isoformat()})

    @rt("/api/alerts/thresholds")
    @csrf_protected
    @require_admin(get_user_service)
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


__all__ = ["create_system_api_routes"]
