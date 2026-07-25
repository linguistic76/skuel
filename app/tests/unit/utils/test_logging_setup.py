"""setup_logging() activation pins (core/utils/logging.py).

The file-logging half of the unified logging system: the ERROR-only handler
filter, and a full setup_logging() boot in a throwaway subprocess — files
created relative to cwd, JSON rendering with literal UTF-8, level filtering,
idempotent double-call, request-id bridging, and ERROR-only routing.

The boot test runs in a subprocess deliberately: setup_logging() mutates
process-global state (root handlers + structlog config), which must never
leak into the pytest process — see the module docstring warning in
core/utils/logging.py.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from core.utils.logging import ErrorRotatingFileHandler

APP_ROOT = Path(__file__).parents[3]


class TestErrorRotatingFileHandler:
    def test_only_error_and_above_are_written(self, tmp_path: Path) -> None:
        log_file = tmp_path / "errors.log"
        handler = ErrorRotatingFileHandler(log_file, when="midnight", backupCount=1)
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))

        # Isolated: propagate=False keeps records off the root logger, and the
        # handler is detached again before the test ends.
        test_logger = logging.getLogger("skuel.test.error_handler_pin")
        test_logger.setLevel(logging.DEBUG)
        test_logger.propagate = False
        test_logger.addHandler(handler)
        try:
            test_logger.debug("debug line")
            test_logger.info("info line")
            test_logger.warning("warning line")
            test_logger.error("error line")
            test_logger.critical("critical line")
        finally:
            test_logger.removeHandler(handler)
            handler.close()

        content = log_file.read_text()
        assert "error line" in content
        assert "critical line" in content
        assert "debug line" not in content
        assert "info line" not in content
        assert "warning line" not in content


_BOOT_SNIPPET = """
from core.utils.logging import get_logger, request_id_context, setup_logging

setup_logging(level="INFO", json_format=True)
setup_logging(level="DEBUG", json_format=False)  # must no-op (idempotent)

request_id_context.set("req-e2e-test")
logger = get_logger("skuel.test.boot")
logger.info("✅ boot info line — utf8 intact")
logger.debug("debug line below level")
logger.error("💥 induced error line")
"""


class TestSetupLoggingBoot:
    def test_files_json_levels_and_error_routing(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [sys.executable, "-c", _BOOT_SNIPPET],
            cwd=tmp_path,
            env={**os.environ, "PYTHONPATH": str(APP_ROOT)},
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr

        app_log = (tmp_path / "logs" / "skuel.log").read_text()
        err_log = (tmp_path / "logs" / "skuel_errors.log").read_text()

        # JSON rendering, with emoji/em-dash as literal UTF-8
        # (ensure_ascii=False) — documented grep contracts depend on it.
        assert '"event": "✅ boot info line — utf8 intact"' in app_log

        # add_request_context bridges the plain ContextVar into every event.
        assert '"request_id": "req-e2e-test"' in app_log

        # INFO level from the FIRST call holds; the second call no-opped
        # (no DEBUG passthrough, no ConsoleRenderer switch).
        assert "debug line below level" not in app_log

        # ERROR-only file: errors land there, INFO does not.
        assert "induced error line" in err_log
        assert "boot info line" not in err_log

        # Console handler mirrors the file — the docker-logs contract.
        assert "✅ boot info line" in result.stdout
        assert "induced error line" in result.stdout

        # Idempotency: a duplicated handler set would emit this line twice.
        assert app_log.count("boot info line") == 1
