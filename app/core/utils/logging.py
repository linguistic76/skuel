"""
SKUEL Unified Logging System
============================

Modern unified logging with structured output, request correlation, and performance tracking.
Consolidates logging functionality across all SKUEL applications.
"""

__version__ = "1.0"


import json
import logging
import sys
import threading
import time
import uuid
from collections.abc import MutableMapping
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# Define HasURL protocol locally for logging purposes
from typing import Any, ClassVar, Protocol, runtime_checkable

import structlog


@runtime_checkable
class HasURL(Protocol):
    """Protocol for objects with a URL attribute (e.g., FastAPI/Starlette requests)"""

    url: Any


# ============================================================================
# CONTEXT VARIABLES
# ============================================================================

# Request correlation context
request_id_context: ContextVar[str] = ContextVar("request_id", default="")
user_id_context: ContextVar[str] = ContextVar("user_id", default="")
service_context: ContextVar[str] = ContextVar("service", default="")
route_context: ContextVar[str] = ContextVar("route", default="")

# Global configuration state
_logging_lock = threading.Lock()
_logging_configured = False


# ============================================================================
# CONFIGURATION
# ============================================================================


class SKUELLogConfig:
    """Centralized logging configuration"""

    # Log levels
    DEFAULT_LEVEL = logging.INFO
    DEBUG_LEVEL = logging.DEBUG

    # Log file paths
    LOG_DIR = Path("logs")
    APP_LOG_FILE = LOG_DIR / "skuel.log"
    ERROR_LOG_FILE = LOG_DIR / "skuel_errors.log"
    SYNC_LOG_FILE = LOG_DIR / "sync_operations.log"

    # Component loggers
    COMPONENT_LOGGERS: ClassVar[dict[str, int]] = {
        "skuel.main": logging.INFO,
        "skuel.sync": logging.INFO,
        "skuel.search": logging.INFO,
        "skuel.chat": logging.INFO,
        "skuel.documents": logging.INFO,
        "skuel.tasks": logging.INFO,
        "skuel.finance": logging.INFO,
        "skuel.neo4j": logging.INFO,
        "skuel.routes": logging.INFO,
        "uvicorn": logging.WARNING,
        "fasthtml": logging.WARNING,
        "neo4j.notifications": logging.ERROR,
        "neo4j.bolt": logging.WARNING,
    }


def setup_logging(debug: bool = False) -> None:
    """
    Configure unified logging for entire SKUEL application.
    Call once in main.py startup.
    """
    global _logging_configured

    with _logging_lock:
        if _logging_configured:
            return

        # Create log directory
        SKUELLogConfig.LOG_DIR.mkdir(exist_ok=True)

        # Set up log level
        level = SKUELLogConfig.DEBUG_LEVEL if debug else SKUELLogConfig.DEFAULT_LEVEL

        # Create standard formatter with UTC timestamps
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
        )
        formatter.converter = time.gmtime  # Use UTC timestamps

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)

        # Main application log with rotation
        app_file_handler = TimedRotatingFileHandler(
            SKUELLogConfig.APP_LOG_FILE, when="midnight", interval=1, backupCount=7
        )
        app_file_handler.setLevel(level)
        app_file_handler.setFormatter(formatter)

        # Error-only log with rotation
        error_file_handler = ErrorRotatingFileHandler(
            SKUELLogConfig.ERROR_LOG_FILE, when="midnight", interval=1, backupCount=14
        )
        error_file_handler.setLevel(logging.ERROR)
        error_file_handler.setFormatter(formatter)

        # Configure root logger
        logging.basicConfig(
            level=level, handlers=[console_handler, app_file_handler, error_file_handler]
        )

        # Dedicated sync logger with its own file handler
        sync_file_handler = TimedRotatingFileHandler(
            SKUELLogConfig.SYNC_LOG_FILE, when="midnight", interval=1, backupCount=14
        )
        sync_file_handler.setLevel(level)
        sync_file_handler.setFormatter(formatter)

        sync_logger = logging.getLogger("skuel.sync.file")
        sync_logger.addHandler(sync_file_handler)
        sync_logger.propagate = False  # Don't propagate to root logger
        sync_logger.setLevel(level)

        # Set component-specific log levels
        for logger_name, comp_level in SKUELLogConfig.COMPONENT_LOGGERS.items():
            logging.getLogger(logger_name).setLevel(comp_level)

        # Configure structlog with stdlib factory
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                add_request_context,
                structlog.dev.ConsoleRenderer() if debug else structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(level),
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        _logging_configured = True

        # Log startup
        logger = get_logger("skuel.platform.logging")
        logger.info(
            "🔧 SKUEL unified logging initialized", debug=debug, log_dir=str(SKUELLogConfig.LOG_DIR)
        )


def add_request_context(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Add request and user context to all log entries"""
    # Add request ID
    request_id = request_id_context.get("")
    if request_id:
        event_dict["request_id"] = request_id

    # Add user ID
    user_id = user_id_context.get("")
    if user_id:
        event_dict["user_id"] = user_id

    # Add service context
    service = service_context.get("")
    if service:
        event_dict["service"] = service

    # Add route context
    route = route_context.get("")
    if route:
        event_dict["route"] = route

    return event_dict


class ErrorRotatingFileHandler(TimedRotatingFileHandler):
    """Rotating file handler that only logs ERROR and CRITICAL messages"""

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno >= logging.ERROR:
            super().emit(record)


# ============================================================================
# CONTEXT MANAGEMENT
# ============================================================================


def set_request_context(
    *,
    request_id: str | None = None,
    user_id: str | None = None,
    route: str | None = None,
    service: str | None = None,
) -> None:
    """Set request context for structured logging"""
    if request_id:
        request_id_context.set(request_id)
    if user_id:
        user_id_context.set(user_id)
    if route:
        route_context.set(route)
    if service:
        service_context.set(service)


def generate_request_id() -> str:
    """Generate a unique request ID"""
    return str(uuid.uuid4())[:8]


def get_current_request_id() -> str:
    """Get current request ID for manual correlation"""
    return request_id_context.get("no-request-id")


def get_request_context() -> dict[str, str]:
    """Get current request context as dictionary"""
    return {
        "request_id": request_id_context.get(""),
        "user_id": user_id_context.get(""),
        "service": service_context.get(""),
        "route": route_context.get(""),
    }


# ============================================================================
# MIDDLEWARE
# ============================================================================


class RequestIDMiddleware:
    """FastHTML middleware to inject request IDs for log correlation"""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            # Generate unique request ID
            request_id = generate_request_id()

            # Set in context for this request
            token = request_id_context.set(request_id)

            # Add to response headers for debugging
            async def send_wrapper(message) -> None:
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append([b"x-request-id", request_id.encode()])
                    message["headers"] = headers
                await send(message)

            try:
                (await self.app(scope, receive, send_wrapper),)
            finally:
                request_id_context.reset(token)
        else:
            await self.app(scope, receive, send)


def log_middleware_factory(app: Any) -> Any:
    """Create logging middleware for FastHTML applications"""
    return RequestIDMiddleware(app)


# ============================================================================
# LOGGING HELPERS
# ============================================================================


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Get a properly configured logger for any SKUEL component.
    Use this instead of logging.getLogger() everywhere.
    """
    return structlog.get_logger(name)


def log_route_entry(route_name: str, method: str, **kwargs: Any) -> None:
    """Log route entry with standardized format"""
    logger = get_logger(f"skuel.routes.{route_name}")
    logger.info("→ Route entered", route=route_name, method=method, **kwargs)


def log_route_exit(route_name: str, status: str, duration_ms: float, **kwargs: Any) -> None:
    """Log route exit with performance data"""
    logger = get_logger(f"skuel.routes.{route_name}")
    logger.info(
        "← Route completed", route=route_name, status=status, duration_ms=duration_ms, **kwargs
    )


def log_service_operation(service: str, operation: str, **kwargs: Any) -> None:
    """Log service operations with consistent format"""
    logger = get_logger(f"skuel.services.{service}")
    logger.info(
        f"🔧 Service operation: {operation}", service=service, operation=operation, **kwargs
    )


def log_sync_operation(operation_id: str, operation_type: str, status: str, **kwargs: Any) -> None:
    """Specialized logging for sync operations"""
    # Log to main sync logger
    logger = get_logger("skuel.sync.operations")
    logger.info(
        f"🔄 Sync {status}: {operation_type}",
        operation_id=operation_id,
        operation_type=operation_type,
        status=status,
        **kwargs,
    )

    # Also log to dedicated sync file logger
    sync_file_logger = logging.getLogger("skuel.sync.file")
    sync_file_logger.info(
        json.dumps(
            {
                "operation_id": operation_id,
                "operation_type": operation_type,
                "status": status,
                "timestamp": datetime.now().isoformat(),
                **kwargs,
            }
        )
    )


def log_error_with_context(component: str, error: Exception, **context: Any) -> None:
    """Log errors with full context for better debugging"""
    logger = get_logger(f"skuel.{component}")

    error_data = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        "component": component,
        **context,
    }

    logger.error(f"❌ {component} error: {error}", **error_data)


# ============================================================================
# PERFORMANCE LOGGING
# ============================================================================


@dataclass(frozen=True)
class PerformanceContext:
    """
    Immutable performance measurement context.

    This design eliminates temporal coupling by ensuring all required state
    (including start_time) is initialized at construction. No Optional types,
    no assertions, no state lifecycle issues.
    """

    operation: str
    component: str
    start_time: datetime
    context: dict[str, Any]
    logger: structlog.BoundLogger

    @classmethod
    def start(cls, operation: str, component: str, **context: Any) -> "PerformanceContext":
        """
        Create a new performance measurement context.

        Returns:
            Immutable context with start_time guaranteed to be set
        """
        return cls(
            operation=operation,
            component=component,
            start_time=datetime.now(),
            context=context,
            logger=get_logger(f"skuel.{component}"),
        )

    def finish(self, exc_type=None, exc_val=None) -> None:
        """
        Log completion with duration.

        Args:
            exc_type: Exception type if failed
            exc_val: Exception value if failed
        """
        duration_ms = (datetime.now() - self.start_time).total_seconds() * 1000

        if exc_type is None:
            self.logger.info(
                f"✅ Completed {self.operation}",
                operation=self.operation,
                duration_ms=duration_ms,
                **self.context,
            )
        else:
            self.logger.error(
                f"❌ Failed {self.operation}",
                operation=self.operation,
                duration_ms=duration_ms,
                error=str(exc_val),
                **self.context,
            )


class PerformanceLogger:
    """
    Context manager for performance logging.

    Now a thin wrapper around immutable PerformanceContext. This design:
    - Eliminates Optional types (start_time always set in PerformanceContext)
    - Removes need for assertions (type system guarantees correctness)
    - Separates concerns (lifecycle vs data)
    - Follows SKUEL's frozen dataclass pattern
    """

    def __init__(self, operation: str, component: str, **context: Any) -> None:
        self.operation = operation
        self.component = component
        self.context = context
        self._perf_context: PerformanceContext | None = None

    def __enter__(self) -> "PerformanceLogger":
        self._perf_context = PerformanceContext.start(
            self.operation, self.component, **self.context
        )
        self._perf_context.logger.info(
            f"⏱️ Starting {self.operation}", operation=self.operation, **self.context
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._perf_context is not None:
            self._perf_context.finish(exc_type, exc_val)


# ============================================================================
# ROUTE UTILITIES
# ============================================================================


def create_route_logger(route_path: str) -> structlog.BoundLogger:
    """Create route-specific logger with consistent naming"""
    route_name = route_path.strip("/").replace("/", "_") or "root"
    return get_logger(f"skuel.routes.{route_name}")


def dump_request_context(request: Any) -> dict[str, Any]:
    """Extract request context for logging"""
    return {
        "method": getattr(request, "method", "unknown"),
        "path": request.url.path if isinstance(request, HasURL) else "unknown",
        "user_agent": getattr(request, "headers", {}).get("user-agent", "unknown"),
        "request_id": request_id_context.get("unknown"),
    }


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "PerformanceContext",
    "PerformanceLogger",
    "RequestIDMiddleware",
    "create_route_logger",
    "dump_request_context",
    "generate_request_id",
    "get_current_request_id",
    "get_logger",
    "get_request_context",
    "log_error_with_context",
    "log_middleware_factory",
    "log_route_entry",
    "log_route_exit",
    "log_service_operation",
    "log_sync_operation",
    "set_request_context",
    "setup_logging",
]
