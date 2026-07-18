"""
System Service
==============

Simple system service for health checks and system operations.
Aligned with SKUEL patterns for consistency.
"""

__version__ = "2.0"


from collections.abc import Callable
from datetime import datetime
from typing import Any

from core.ports.query_types import (
    AlertCheckResult,
    HealthCheckValidation,
    HealthSummaryResult,
    SystemHealthStatus,
    SystemInfoResult,
)
from core.services.performance_types import AlertThresholds
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class SystemService:
    """
    Service for system-level operations like health checks.
    """

    def __init__(self) -> None:
        """Initialize system service."""
        self._component_checkers: dict[str, Callable] = {}
        self._alert_thresholds = {
            "min_health_ratio": 0.8,  # Alert if less than 80% healthy
            "max_unhealthy_components": 2,  # Alert if more than 2 components unhealthy
        }
        logger.info("SystemService initialized with basic alerting")

    def register_component_checker(self, name: str, checker: Callable) -> None:
        """
        Register a health checker for a component.

        Args:
            name: Component name
            checker: Async function that returns bool for health status
        """
        self._component_checkers[name] = checker
        logger.debug(f"Registered health checker for {name}")

    def unregister_component_checker(self, name: str) -> bool:
        """
        Unregister a health checker for a component.

        Args:
            name: Component name to unregister

        Returns:
            True if component was found and removed, False otherwise
        """
        if name in self._component_checkers:
            del self._component_checkers[name]
            logger.debug(f"Unregistered health checker for {name}")
            return True
        return False

    def list_registered_components(self) -> list[str]:
        """
        Get list of registered component names.

        Returns:
            List of component names
        """
        return list(self._component_checkers.keys())

    def is_component_registered(self, name: str) -> bool:
        """
        Check if a component is registered.

        Args:
            name: Component name to check

        Returns:
            True if component is registered
        """
        return name in self._component_checkers

    async def get_health_status(self) -> Result[SystemHealthStatus]:
        """
        Get overall system health status.

        Returns:
            Result containing typed health status information
        """
        try:
            status: SystemHealthStatus = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "components": {},
                "healthy": True,  # Will be updated based on component checks
            }

            overall_healthy = True

            # Check all registered components
            for name, checker in self._component_checkers.items():
                try:
                    is_healthy = await checker()
                    status["components"][name] = {
                        "status": "healthy" if is_healthy else "unhealthy",
                        "healthy": is_healthy,
                    }
                    if not is_healthy:
                        overall_healthy = False
                except Exception as e:  # safety-net: checkers are external callables
                    logger.error(f"Health check failed for {name}: {e}")
                    status["components"][name] = {
                        "status": "error",
                        "healthy": False,
                        "error": str(e),
                    }
                    overall_healthy = False

            status["status"] = "healthy" if overall_healthy else "unhealthy"
            status["healthy"] = overall_healthy

            return Result.ok(status)

        except (
            Exception
        ) as e:  # safety-net: catch unexpected errors from health check orchestration
            logger.error(f"Failed to get health status: {e}")
            return Result.fail(Errors.system(message=str(e), operation="get_health_status"))

    @with_error_handling("get_system_info", error_type="system")
    async def get_system_info(
        self,
    ) -> Result[
        SystemInfoResult
    ]:  # skuel-lint: disable=SKUEL029 -- awaited via asyncio.gather in system_api
        """
        Get general system information.

        Returns:
            Result containing system information
        """
        info: SystemInfoResult = {
            "service": "SKUEL",
            "version": "2.0.0",
            "timestamp": datetime.now().isoformat(),
            "components_registered": len(self._component_checkers),
        }
        return Result.ok(info)

    @with_error_handling("get_health_summary", error_type="system")
    async def get_health_summary(self) -> Result[HealthSummaryResult]:
        """
        Get a simple health summary useful for monitoring.

        Returns:
            Result containing health summary
        """
        result = await self.get_health_status()
        if not result.is_ok:
            return Result.fail(result)

        health_data = result.value
        components = health_data.get("components", {})

        # Calculate summary
        total = len(components)
        healthy = sum(1 for c in components.values() if c.get("healthy", False))
        unhealthy_names = [
            name for name, comp in components.items() if not comp.get("healthy", False)
        ]

        summary: HealthSummaryResult = {
            "healthy": health_data["healthy"],
            "status": health_data["status"],
            "components_total": total,
            "components_healthy": healthy,
            "components_unhealthy": total - healthy,
            "unhealthy_components": unhealthy_names,
            "timestamp": health_data["timestamp"],
        }

        return Result.ok(summary)

    async def validate_health_checkers(self) -> Result[HealthCheckValidation]:
        """
        Validate that all registered health checkers are working properly.

        Returns:
            Result containing typed validation results
        """
        try:
            validation: HealthCheckValidation = {
                "timestamp": datetime.now().isoformat(),
                "total_checkers": len(self._component_checkers),
                "valid_checkers": 0,
                "invalid_checkers": 0,
                "results": {},
                "all_valid": True,  # Will be updated based on validation
            }

            for name, checker in self._component_checkers.items():
                try:
                    # Test the health checker
                    start = datetime.now()
                    result = await checker()
                    duration = (datetime.now() - start).total_seconds() * 1000

                    validation["results"][name] = {
                        "valid": True,
                        "response_time_ms": int(duration),
                        "returned_type": type(result).__name__,
                        "returned_value": result,
                    }
                    validation["valid_checkers"] += 1

                except Exception as e:  # safety-net: checkers are external callables
                    validation["results"][name] = {
                        "valid": False,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                    validation["invalid_checkers"] += 1

            validation["all_valid"] = validation["invalid_checkers"] == 0

            return Result.ok(validation)

        except Exception as e:  # safety-net: catch unexpected errors from validation orchestration
            logger.error(f"Failed to validate health checkers: {e}")
            return Result.fail(Errors.system(message=str(e), operation="validate_health_checkers"))

    @with_error_handling("check_alerts", error_type="system")
    async def check_alerts(self) -> Result[AlertCheckResult]:
        """
        Check if any alert conditions are triggered.

        Returns:
            Result containing alert status and triggered alerts
        """
        summary_result = await self.get_health_summary()
        if not summary_result.is_ok:
            return Result.fail(summary_result)

        summary = summary_result.value
        alerts: AlertCheckResult = {
            "timestamp": datetime.now().isoformat(),
            "alerts_triggered": [],
            "alert_count": 0,
            "system_healthy": summary["healthy"],
        }

        # Check health ratio threshold
        if summary["components_total"] > 0:
            health_ratio = summary["components_healthy"] / summary["components_total"]
            if health_ratio < self._alert_thresholds["min_health_ratio"]:
                alerts["alerts_triggered"].append(
                    {
                        "type": "low_health_ratio",
                        "severity": "warning",
                        "message": f"Health ratio {health_ratio:.1%} below threshold {self._alert_thresholds['min_health_ratio']:.1%}",
                        "current_value": health_ratio,
                        "threshold": self._alert_thresholds["min_health_ratio"],
                    }
                )

        # Check unhealthy components threshold
        unhealthy_count = summary["components_unhealthy"]
        if unhealthy_count > self._alert_thresholds["max_unhealthy_components"]:
            alerts["alerts_triggered"].append(
                {
                    "type": "too_many_unhealthy",
                    "severity": "critical",
                    "message": f"{unhealthy_count} unhealthy components exceeds threshold of {self._alert_thresholds['max_unhealthy_components']}",
                    "current_value": unhealthy_count,
                    "threshold": self._alert_thresholds["max_unhealthy_components"],
                    "unhealthy_components": summary["unhealthy_components"],
                }
            )

        alerts["alert_count"] = len(alerts["alerts_triggered"])
        alerts["has_alerts"] = alerts["alert_count"] > 0

        # Log alerts
        if alerts["has_alerts"]:
            for alert in alerts["alerts_triggered"]:
                logger.warning(f"ALERT: {alert['message']}")

        return Result.ok(alerts)

    def update_alert_thresholds(self, thresholds: dict[str, Any]) -> None:
        """
        Update alert thresholds.

        Args:
            thresholds: Dictionary of threshold values to update
        """
        for key, value in thresholds.items():
            if key in self._alert_thresholds:
                self._alert_thresholds[key] = value
                logger.info(f"Updated alert threshold {key} to {value}")

    def get_alert_thresholds(self) -> AlertThresholds:
        """
        Get current alert thresholds.

        Returns:
            AlertThresholds frozen dataclass with current thresholds
        """
        return AlertThresholds(
            min_health_ratio=self._alert_thresholds["min_health_ratio"],
            max_unhealthy_components=int(self._alert_thresholds["max_unhealthy_components"]),
        )
