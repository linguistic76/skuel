"""
SKUEL Unified Logging System
============================

Structured logging with request correlation. App code gets loggers via
get_logger(); main.py calls setup_logging() once at startup, which routes
all structlog output through stdlib handlers: console (stdout),
logs/skuel.log (daily rotation, 7 backups), and logs/skuel_errors.log
(ERROR-only, 14 backups).
"""

__version__ = "1.0"


import logging
import sys
import threading
import time
import uuid
from collections.abc import MutableMapping
from contextvars import ContextVar
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar

import structlog
from structlog.typing import Processor

# ============================================================================
# CONTEXT VARIABLES
# ============================================================================

# Per-request correlation ID — written by RequestIDMiddleware
# (adapters/inbound/middleware.py), surfaced into every structlog event by
# the add_request_context processor below.
request_id_context: ContextVar[str] = ContextVar("request_id", default="")

# Global configuration state
_logging_lock = threading.Lock()
_logging_configured = False


# ============================================================================
# CONFIGURATION
# ============================================================================


class SKUELLogConfig:
    """Centralized logging configuration"""

    # Log file paths — cwd-relative: /app inside containers (bind-mounted to
    # ./logs on the droplet, chowned to UID 10001 by deploy.sh), repo root
    # for local runs (gitignored). Only main.py triggers creation.
    LOG_DIR = Path("logs")
    APP_LOG_FILE = LOG_DIR / "skuel.log"
    ERROR_LOG_FILE = LOG_DIR / "skuel_errors.log"

    # Third-party quieting only. First-party skuel.* loggers follow the root
    # level — a per-component pin would suppress them in DEBUG runs.
    # "neo4j" covers the driver's real logger names in 5.26 (neo4j.io,
    # neo4j.pool, neo4j.auth_management); notifications get their own pin.
    COMPONENT_LOGGERS: ClassVar[dict[str, int]] = {
        "fasthtml": logging.WARNING,
        "neo4j": logging.WARNING,
        "neo4j.notifications": logging.ERROR,
    }


def setup_logging(level: str = "INFO", json_format: bool = True) -> None:
    """
    Configure unified logging for the entire SKUEL application.

    Called once from main.py, first thing inside main() — before
    bootstrap_skuel(), so bootstrap's log lines land in the files. Never
    call from scripts, tests, or import-time code: LOG_DIR is cwd-relative
    and the config is process-global.

    Args:
        level: Root log level name, from config.application.log_level
            (validated against the five stdlib names in
            core/config/validation.py).
        json_format: True renders events as JSON (production/staging);
            False renders human-readable text (local/development), from
            config.application.log_format.
    """
    global _logging_configured

    with _logging_lock:
        if _logging_configured:
            return

        # Create log directory
        SKUELLogConfig.LOG_DIR.mkdir(exist_ok=True)

        numeric_level = logging.getLevelNamesMapping()[level]

        # Create standard formatter with UTC timestamps
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
        )
        formatter.converter = time.gmtime  # Use UTC timestamps

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(formatter)

        # Main application log with rotation
        app_file_handler = TimedRotatingFileHandler(
            SKUELLogConfig.APP_LOG_FILE, when="midnight", interval=1, backupCount=7
        )
        app_file_handler.setLevel(numeric_level)
        app_file_handler.setFormatter(formatter)

        # Error-only log with rotation
        error_file_handler = ErrorRotatingFileHandler(
            SKUELLogConfig.ERROR_LOG_FILE, when="midnight", interval=1, backupCount=14
        )
        error_file_handler.setLevel(logging.ERROR)
        error_file_handler.setFormatter(formatter)

        # Configure root logger
        logging.basicConfig(
            level=numeric_level,
            handlers=[console_handler, app_file_handler, error_file_handler],
        )

        # Set component-specific log levels
        for logger_name, comp_level in SKUELLogConfig.COMPONENT_LOGGERS.items():
            logging.getLogger(logger_name).setLevel(comp_level)

        # ensure_ascii=False keeps emoji/em-dashes literal in JSON output —
        # documented grep contracts (e.g. "✅.*service created") depend on it.
        # format_exc_info renders exc_info=True tracebacks into an "exception"
        # field for JSON; ConsoleRenderer consumes raw exc_info itself (the two
        # must not be combined). colors=False keeps ANSI escapes out of the log
        # files, which share the rendered string with the console (single chain).
        rendering: list[Processor] = (
            [
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(ensure_ascii=False),
            ]
            if json_format
            else [structlog.dev.ConsoleRenderer(colors=False)]
        )

        # Configure structlog with stdlib factory
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                add_request_context,
                *rendering,
            ],
            wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        _logging_configured = True

        # Log startup
        logger = get_logger("skuel.platform.logging")
        # "level" as a kwarg would be clobbered by the add_log_level processor
        logger.info(
            "🔧 SKUEL unified logging initialized",
            log_level=level,
            json_format=json_format,
            log_dir=str(SKUELLogConfig.LOG_DIR),
        )


def add_request_context(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Copy the per-request correlation ID into every log entry.

    RequestIDMiddleware sets a plain ContextVar, which
    structlog.contextvars.merge_contextvars cannot see (it reads only
    structlog-bound contextvars) — this processor is the sole bridge.
    """
    request_id = request_id_context.get("")
    if request_id:
        event_dict["request_id"] = request_id

    return event_dict


class ErrorRotatingFileHandler(TimedRotatingFileHandler):
    """Rotating file handler that only logs ERROR and CRITICAL messages"""

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno >= logging.ERROR:
            super().emit(record)


# ============================================================================
# LOGGING HELPERS
# ============================================================================


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Get a properly configured logger for any SKUEL component.
    Use this instead of logging.getLogger() everywhere.
    """
    return structlog.get_logger(name)


def generate_request_id() -> str:
    """Generate a unique request ID"""
    return str(uuid.uuid4())[:8]


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "generate_request_id",
    "get_logger",
    "request_id_context",
    "setup_logging",
]
