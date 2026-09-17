"""
How this suite starts a Neo4j testcontainer: sized for the test graphs, and reaped.

Two guarantees, one builder. Every integration Neo4j container
(``conftest``'s shared one, the app fixture's own, the APOC-lockdown suite's)
goes through ``bounded_neo4j_container``, so both hold by construction:

1. **The JVM is sized for the graphs it will hold, not for the host.** Left
   unset, the Neo4j image sizes heap and page cache from the machine's RAM,
   and three containers per session grow to ~3 GiB on a 16 GB laptop. The
   test graphs are a few hundred nodes; ``NEO4J_TESTCONTAINER_MEMORY`` is a
   code-side ceiling, deliberately not derived from the host — a larger
   machine is not a licence to size from it again
   (``docs/roadmap/development-machine-capacity.md``).

2. **Ryuk holds this session's filter.** testcontainers-python sends the
   filter the moment the Ryuk container is *running*, without waiting for the
   process inside to *listen* (its ``waiting_for`` is set after ``start()``,
   so it never runs), and never reads the reply. On a Linux daemon
   docker-proxy accepts that early connection on Ryuk's behalf and resets it,
   so the library reports a reaper that holds nothing; Ryuk then exits on its
   own 60 s first-connection timer, and a session killed after that leaves
   every container running until the daemon stops
   (testcontainers-python#1114). ``ensure_reaper_registered`` does the
   handshake the library skips — read the ``ACK`` — and re-registers when it
   is missing. Delete it when that issue closes upstream.
"""

import contextlib
import socket
import time

from docker.errors import NotFound  # type: ignore[import-untyped]
from testcontainers.community.neo4j import Neo4jContainer  # type: ignore[import-untyped]
from testcontainers.core.config import testcontainers_config
from testcontainers.core.container import DockerContainer, Reaper
from testcontainers.core.labels import LABEL_SESSION_ID, SESSION_ID

from tests.integration._neo4j_pin import NEO4J_IMAGE

# The ceiling is the MAX heap; the initial heap stays small on purpose. The
# image's vendor JVM flags include AlwaysPreTouch, which commits the initial
# heap at boot — so an initial size is a container's resting footprint, paid
# by the two containers that stay mostly idle, while max is what the busy one
# may grow into. The page cache holds the store files: a few MB for these
# graphs plus seven 1024-dim vector indexes on a few hundred nodes.
NEO4J_TESTCONTAINER_MEMORY: dict[str, str] = {
    "NEO4J_server_memory_heap_initial__size": "128m",
    "NEO4J_server_memory_heap_max__size": "512m",
    "NEO4J_server_memory_pagecache_size": "128m",
}

# What Ryuk writes back for every filter line it accepts.
RYUK_ACK = b"ACK\n"
RYUK_HANDSHAKE_TIMEOUT_S = 5.0
RYUK_REGISTER_ATTEMPTS = 3

_reaper_registered = False


def bounded_neo4j_container() -> Neo4jContainer:
    """The pinned image, auth off, JVM sized for the test graphs, reaper registered.

    Not started — callers add their own env (APOC profile, plugins) and call
    ``start()`` themselves.
    """
    ensure_reaper_registered()
    container = Neo4jContainer(NEO4J_IMAGE)
    container.with_env("NEO4J_dbms_security_auth__enabled", "false")
    for key, value in NEO4J_TESTCONTAINER_MEMORY.items():
        container.with_env(key, value)
    return container


def ensure_reaper_registered() -> None:
    """Make sure Ryuk acknowledged this session's filter; register it if not.

    Idempotent per process. A no-op when Ryuk is disabled by configuration.
    Raises rather than run a session no reaper will clean up.
    """
    global _reaper_registered
    if _reaper_registered or testcontainers_config.ryuk_disabled:
        return
    for _ in range(RYUK_REGISTER_ATTEMPTS):
        Reaper.get_instance()
        if _ack_received(Reaper._socket):
            _reaper_registered = True
            return
        ryuk = Reaper._container
        if ryuk is not None and _is_running(ryuk):
            # Ryuk is alive and, by now, listening: the filter was lost to the
            # proxy, not to Ryuk. Open the new connection BEFORE closing the
            # old one, so Ryuk's client count never drops to zero in between.
            registered = _connect_and_register(ryuk)
            if registered is not None:
                _replace_reaper_socket(registered)
                _reaper_registered = True
                return
        # Ryuk timed out (or is deaf): start over with a fresh one.
        Reaper.delete_instance()
    raise RuntimeError(
        "Ryuk never acknowledged this session's filter after "
        f"{RYUK_REGISTER_ATTEMPTS} attempts — refusing to run a session whose "
        "containers nothing will reap (testcontainers-python#1114)."
    )


def _ack_received(sock: socket.socket | None) -> bool:
    if sock is None:
        return False
    sock.settimeout(RYUK_HANDSHAKE_TIMEOUT_S)
    try:
        return sock.recv(len(RYUK_ACK)) == RYUK_ACK
    except OSError:  # reset by docker-proxy, or nothing within the timeout
        return False


def _is_running(ryuk: DockerContainer) -> bool:
    wrapped = ryuk.get_wrapped_container()
    try:
        wrapped.reload()
    except NotFound:  # auto-remove already ran: Ryuk exited on its timer
        return False
    return str(wrapped.status) == "running"


def _wait_for_listener(ryuk: DockerContainer) -> bool:
    """True once Ryuk's log says it listens — the wait the library configures too late."""
    deadline = time.monotonic() + RYUK_HANDSHAKE_TIMEOUT_S
    while time.monotonic() < deadline:
        stdout, stderr = ryuk.get_logs()
        if b"Started!" in stdout or b"Started!" in stderr:
            return True
        time.sleep(0.1)
    return False


def _connect_and_register(ryuk: DockerContainer) -> socket.socket | None:
    if not _wait_for_listener(ryuk):
        return None
    host = ryuk.get_container_host_ip()
    port = int(ryuk.get_exposed_port(8080))
    try:
        sock = socket.create_connection((host, port), timeout=RYUK_HANDSHAKE_TIMEOUT_S)
    except OSError:
        return None
    sock.sendall(f"label={LABEL_SESSION_ID}={SESSION_ID}\r\n".encode())
    if _ack_received(sock):
        return sock
    sock.close()
    return None


def _replace_reaper_socket(sock: socket.socket) -> None:
    old = Reaper._socket
    Reaper._socket = sock
    if old is not None:
        with contextlib.suppress(OSError):
            old.close()
