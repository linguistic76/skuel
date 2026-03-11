#!/usr/bin/env python3
"""
SKUEL Server Manager
===================
Utility script to properly start/stop/restart the SKUEL server with proper cleanup.
Now using secure command execution to prevent command injection attacks.
"""

import os
import signal
import sys
import time

__version__ = "1.0"

# Import secure command execution
try:
    from utils.secure_command_execution import (
        get_secure_executor,
        safe_kill_process,
        safe_lsof_port,
    )

    SECURE_EXECUTION_AVAILABLE = True
except ImportError:
    # Fallback to subprocess if secure execution not available
    import subprocess

    SECURE_EXECUTION_AVAILABLE = False
    print("⚠️  Secure command execution not available. Install utils/secure_command_execution.py")


def get_server_pid():
    """Get the PID of the running SKUEL server using secure command execution"""
    try:
        if SECURE_EXECUTION_AVAILABLE:
            # Use secure command execution
            result = safe_lsof_port(8000)
            if result.is_ok() and result.value.success and result.value.stdout.strip():
                return int(result.value.stdout.strip())
        else:
            # Fallback to subprocess (less secure)
            result = subprocess.run(["lsof", "-t", "-i:8000"], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip())
    except Exception as e:
        print(f"⚠️  Error getting server PID: {e}")
    return None


def stop_server(pid=None):
    """Stop the SKUEL server gracefully using secure process termination"""
    if pid is None:
        pid = get_server_pid()

    if not pid:
        print("🟢 Server is not running")
        return True

    print(f"🛑 Stopping server (PID: {pid})...")

    try:
        # Validate PID is reasonable
        if not (1 <= pid <= 65535):
            print(f"❌ Invalid PID: {pid}")
            return False

        if SECURE_EXECUTION_AVAILABLE:
            # Use secure process termination
            print("🔐 Using secure process termination...")

            # Try graceful shutdown first
            result = safe_kill_process(pid, force=False)
            if result.is_error():
                print(f"⚠️  Graceful termination failed: {result.error}")

            # Wait up to 10 seconds for graceful shutdown
            for _ in range(10):
                time.sleep(1)
                if get_server_pid() is None:
                    print("✅ Server stopped gracefully")
                    return True

            # If still running, force kill
            print("⚠️  Forcing server shutdown...")
            result = safe_kill_process(pid, force=True)
            if result.is_error():
                print(f"❌ Force termination failed: {result.error}")
                return False

            time.sleep(2)
            if get_server_pid() is None:
                print("✅ Server stopped (forced)")
                return True
            else:
                print("❌ Failed to stop server")
                return False

        else:
            # Fallback to os.kill (less secure but functional)
            print("⚠️  Using fallback process termination...")

            # Send TERM signal first (graceful shutdown)
            os.kill(pid, signal.SIGTERM)

            # Wait up to 10 seconds for graceful shutdown
            for _ in range(10):
                time.sleep(1)
                if get_server_pid() is None:
                    print("✅ Server stopped gracefully")
                    return True

            # If still running, force kill
            print("⚠️  Forcing server shutdown...")
            os.kill(pid, signal.SIGKILL)
            time.sleep(2)

            if get_server_pid() is None:
                print("✅ Server stopped (forced)")
                return True
            else:
                print("❌ Failed to stop server")
                return False

    except ProcessLookupError:
        print("✅ Server already stopped")
        return True
    except Exception as e:
        print(f"❌ Error stopping server: {e}")
        return False


def start_server():
    """Start the SKUEL server using secure command execution"""
    if get_server_pid():
        print("⚠️  Server is already running")
        return False

    print("🚀 Starting SKUEL server...")

    try:
        if SECURE_EXECUTION_AVAILABLE:
            # Use secure command execution
            print("🔐 Using secure command execution...")
            executor = get_secure_executor()

            # Set up environment variables securely
            env_vars = {"PYTHONPATH": "/home/mike/skuel/app"}

            # Execute via uv
            result = executor.execute_safe_command(
                "uv",
                ["run", "python", "main.py"],
                working_dir="/home/mike/skuel/app",
                timeout=10,  # Short timeout just to start the process
                env_vars=env_vars,
            )

            if result.is_error():
                print(f"❌ Failed to start server: {result.error}")
                return False

        else:
            # Fallback to subprocess
            print("⚠️  Using fallback command execution...")
            env = os.environ.copy()
            env["PYTHONPATH"] = "/home/mike/skuel/app"

            subprocess.Popen(
                ["uv", "run", "python", "main.py"],
                cwd="/home/mike/skuel/app",
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,  # This helps with signal handling
            )

        # Give the server a moment to start
        time.sleep(3)

        # Check if server started successfully
        server_pid = get_server_pid()
        if server_pid:
            print(f"✅ Server started successfully (PID: {server_pid})")
            print("🌐 Access at: http://localhost:8000")
            return True
        else:
            print("❌ Failed to start server - no process found on port 8000")
            return False

    except Exception as e:
        print(f"❌ Error starting server: {e}")
        return False


def restart_server():
    """Restart the SKUEL server"""
    print("🔄 Restarting SKUEL server...")
    stop_server()
    time.sleep(2)  # Brief pause between stop and start
    return start_server()


def status():
    """Show server status"""
    pid = get_server_pid()
    if pid:
        print(f"🟢 Server is running (PID: {pid})")
        print("🌐 Access at: http://localhost:8000")
    else:
        print("🔴 Server is not running")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python server_manager.py [start|stop|restart|status]")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "start":
        start_server()
    elif command == "stop":
        stop_server()
    elif command == "restart":
        restart_server()
    elif command == "status":
        status()
    else:
        print("Unknown command. Use: start, stop, restart, or status")
