#!/usr/bin/env python3
"""Start, stop, restart, and inspect the local SKUEL development server."""

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

__version__ = "1.1"

APP_DIR = Path(__file__).resolve().parents[2]
SERVER_PORT = 8000
STARTUP_WAIT_SECONDS = 3
SHUTDOWN_WAIT_SECONDS = 10
FORCE_KILL_WAIT_SECONDS = 2
MAX_PID = 4_194_304  # Linux pid_max upper bound.


def _pythonpath_env() -> dict[str, str]:
    """Return an environment with the app directory available on PYTHONPATH."""
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{APP_DIR}{os.pathsep}{existing}" if existing else str(APP_DIR)
    return env


def _valid_pid(pid: int) -> bool:
    """Validate a process id before sending a signal."""
    return 1 <= pid <= MAX_PID


def get_server_pid() -> int | None:
    """Return the PID listening on the development server port, if any."""
    if shutil.which("lsof") is None:
        print("⚠️  lsof is not installed; cannot inspect the server port")
        return None

    result = subprocess.run(
        ["lsof", "-t", f"-iTCP:{SERVER_PORT}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None

    first_pid = result.stdout.splitlines()[0].strip()
    try:
        return int(first_pid)
    except ValueError:
        print(f"⚠️  Ignoring unexpected lsof output: {first_pid}")
        return None


def _wait_until_stopped() -> bool:
    """Wait for the server port to become free."""
    for _ in range(SHUTDOWN_WAIT_SECONDS):
        time.sleep(1)
        if get_server_pid() is None:
            return True
    return False


def stop_server(pid: int | None = None) -> bool:
    """Stop the SKUEL server gracefully, then force it only if necessary."""
    pid = get_server_pid() if pid is None else pid

    if not pid:
        print("🟢 Server is not running")
        return True
    if not _valid_pid(pid):
        print(f"❌ Invalid PID: {pid}")
        return False

    print(f"🛑 Stopping server (PID: {pid})...")

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print("✅ Server already stopped")
        return True
    except PermissionError as exc:
        print(f"❌ Permission denied stopping server: {exc}")
        return False

    if _wait_until_stopped():
        print("✅ Server stopped gracefully")
        return True

    print("⚠️  Forcing server shutdown...")
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        print("✅ Server already stopped")
        return True
    except PermissionError as exc:
        print(f"❌ Permission denied forcing server shutdown: {exc}")
        return False

    time.sleep(FORCE_KILL_WAIT_SECONDS)
    if get_server_pid() is None:
        print("✅ Server stopped (forced)")
        return True

    print("❌ Failed to stop server")
    return False


def start_server() -> bool:
    """Start the SKUEL development server."""
    if get_server_pid():
        print("⚠️  Server is already running")
        return False

    print("🚀 Starting SKUEL server...")
    try:
        subprocess.Popen(
            ["uv", "run", "python", "main.py"],
            cwd=APP_DIR,
            env=_pythonpath_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        print(f"❌ Failed to launch server: {exc}")
        return False

    time.sleep(STARTUP_WAIT_SECONDS)
    server_pid = get_server_pid()
    if server_pid:
        print(f"✅ Server started successfully (PID: {server_pid})")
        print(f"🌐 Access at: http://localhost:{SERVER_PORT}")
        return True

    print(f"❌ Failed to start server - no process found on port {SERVER_PORT}")
    return False


def restart_server() -> bool:
    """Restart the SKUEL development server."""
    print("🔄 Restarting SKUEL server...")
    stop_server()
    time.sleep(2)
    return start_server()


def status() -> None:
    """Show server status."""
    pid = get_server_pid()
    if pid:
        print(f"🟢 Server is running (PID: {pid})")
        print(f"🌐 Access at: http://localhost:{SERVER_PORT}")
    else:
        print("🔴 Server is not running")


def main(argv: list[str]) -> int:
    """Run the server manager CLI."""
    if len(argv) < 2:
        print("Usage: python server_manager.py [start|stop|restart|status]")
        return 1

    command = argv[1].lower()
    if command == "start":
        return 0 if start_server() else 1
    if command == "stop":
        return 0 if stop_server() else 1
    if command == "restart":
        return 0 if restart_server() else 1
    if command == "status":
        status()
        return 0

    print("Unknown command. Use: start, stop, restart, or status")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
