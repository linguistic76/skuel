"""
Every integration Neo4j container is sized for the test graphs and reaped.

Runs in the always-on unit tier, against a fake Ryuk on localhost: the
handshake ``tests/integration/_container_lifecycle.py`` performs is a socket
protocol (send the filter line, read ``ACK``), so its four outcomes — already
acknowledged, lost to the proxy and re-registered, Ryuk gone and recreated,
never acknowledged — are all reachable without a Docker daemon.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from testcontainers.core.container import DockerContainer, Reaper
from testcontainers.core.labels import LABEL_SESSION_ID, SESSION_ID

from tests.integration import _container_lifecycle as lifecycle
from tests.integration._container_lifecycle import (
    NEO4J_TESTCONTAINER_MEMORY,
    RYUK_ACK,
    bounded_neo4j_container,
    ensure_reaper_registered,
)
from tests.integration._neo4j_pin import NEO4J_IMAGE


class FakeRyuk:
    """A listener that behaves like Ryuk for one connection at a time."""

    def __init__(self, *, ack: bool = True) -> None:
        self.ack = ack
        self.received: list[bytes] = []
        self._server = socket.socket()
        self._server.bind(("127.0.0.1", 0))
        self._server.listen(4)
        self._accepted: list[socket.socket] = []
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    @property
    def port(self) -> int:
        return int(self._server.getsockname()[1])

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._server.accept()
            except OSError:
                return
            self._accepted.append(conn)
            conn.settimeout(2)
            try:
                line = conn.recv(256)
            except OSError:
                continue
            self.received.append(line)
            if self.ack:
                conn.sendall(RYUK_ACK)
            # Keep the connection open like Ryuk does; the test closes it.

    def close(self) -> None:
        for conn in self._accepted:
            conn.close()
        self._server.close()


@dataclass
class FakeWrapped:
    status: str = "running"
    gone: bool = False

    def reload(self) -> None:
        if self.gone:  # auto-remove already ran
            raise lifecycle.NotFound("No such container")


class FakeRyukContainer(DockerContainer):
    """A never-started ``DockerContainer`` whose reads point at a ``FakeRyuk``."""

    def __init__(self, port: int, *, gone: bool = False, logs: bytes = b"Started!\n") -> None:
        super().__init__("testcontainers/ryuk:fake")
        self.port = port
        self.wrapped = FakeWrapped(gone=gone)
        self.logs = logs

    def get_wrapped_container(self) -> FakeWrapped:  # type: ignore[override]
        return self.wrapped

    def get_logs(self) -> tuple[bytes, bytes]:
        return b"", self.logs

    def get_container_host_ip(self) -> str:
        return "127.0.0.1"

    def get_exposed_port(self, port: int) -> int:
        assert port == 8080
        return self.port


def _reset_socket() -> socket.socket:
    """A client socket whose peer is already gone — what docker-proxy leaves behind."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    client = socket.create_connection(server.getsockname())
    conn, _ = server.accept()
    conn.close()
    server.close()
    return client


@pytest.fixture
def reaper_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Isolate the module flag and the Reaper class attributes; record calls."""
    calls: list[str] = []
    monkeypatch.setattr(lifecycle, "_reaper_registered", False)
    monkeypatch.setattr(lifecycle, "RYUK_HANDSHAKE_TIMEOUT_S", 1.0)
    monkeypatch.setattr(Reaper, "_socket", None)
    monkeypatch.setattr(Reaper, "_container", None)
    monkeypatch.setattr(lifecycle.testcontainers_config, "ryuk_disabled", False)

    def get_instance() -> None:
        calls.append("get_instance")

    def delete_instance() -> None:
        calls.append("delete_instance")
        if Reaper._socket is not None:
            Reaper._socket.close()
        Reaper._socket = None
        Reaper._container = None

    monkeypatch.setattr(Reaper, "get_instance", get_instance)
    monkeypatch.setattr(Reaper, "delete_instance", delete_instance)
    yield calls
    if Reaper._socket is not None:
        Reaper._socket.close()


def _mib(size: str) -> int:
    assert size.endswith("m"), size
    return int(size[:-1])


class TestSizedBuilder:
    def test_every_container_carries_the_memory_ceiling(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def registered() -> None:
            pass

        monkeypatch.setattr(lifecycle, "ensure_reaper_registered", registered)
        container = bounded_neo4j_container()
        assert container.image == NEO4J_IMAGE
        assert container.env["NEO4J_dbms_security_auth__enabled"] == "false"
        for key, value in NEO4J_TESTCONTAINER_MEMORY.items():
            assert container.env[key] == value

    def test_the_ceiling_is_heap_and_page_cache(self) -> None:
        assert set(NEO4J_TESTCONTAINER_MEMORY) == {
            "NEO4J_server_memory_heap_initial__size",
            "NEO4J_server_memory_heap_max__size",
            "NEO4J_server_memory_pagecache_size",
        }
        heap_initial = _mib(NEO4J_TESTCONTAINER_MEMORY["NEO4J_server_memory_heap_initial__size"])
        heap_max = _mib(NEO4J_TESTCONTAINER_MEMORY["NEO4J_server_memory_heap_max__size"])
        assert heap_initial < heap_max, (
            "the initial heap is committed at boot (AlwaysPreTouch) and is every "
            "container's resting footprint; only max is the ceiling"
        )


class TestReaperHandshake:
    def test_an_acknowledged_filter_is_left_alone(self, reaper_state: list[str]) -> None:
        ryuk = FakeRyuk()
        sock = socket.create_connection(("127.0.0.1", ryuk.port))
        sock.sendall(b"label=x\r\n")  # the library's own send; ACK is now in the buffer
        Reaper._socket = sock
        Reaper._container = FakeRyukContainer(port=ryuk.port)

        ensure_reaper_registered()

        assert Reaper._socket is sock
        assert reaper_state == ["get_instance"]
        assert lifecycle._reaper_registered is True
        ryuk.close()

    def test_a_filter_lost_to_the_proxy_is_sent_again(self, reaper_state: list[str]) -> None:
        """The #1114 shape: connect() and send() succeeded, nobody was listening."""
        ryuk = FakeRyuk()
        dead = _reset_socket()
        Reaper._socket = dead
        Reaper._container = FakeRyukContainer(port=ryuk.port)

        ensure_reaper_registered()

        assert Reaper._socket is not dead
        assert dead.fileno() == -1, "the dead socket is closed once the new one is registered"
        assert ryuk.received == [f"label={LABEL_SESSION_ID}={SESSION_ID}\r\n".encode()]
        assert reaper_state == ["get_instance"], "Ryuk was alive: no recreate"
        ryuk.close()

    def test_a_ryuk_that_already_timed_out_is_recreated(
        self, reaper_state: list[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ryuk = FakeRyuk()
        gone = FakeRyukContainer(port=ryuk.port, gone=True)
        Reaper._socket = _reset_socket()
        Reaper._container = gone

        def get_instance_second_time() -> None:
            reaper_state.append("get_instance")
            if Reaper._container is None:  # the recreate: a live Ryuk that ACKs
                sock = socket.create_connection(("127.0.0.1", ryuk.port))
                sock.sendall(b"label=x\r\n")
                Reaper._socket = sock
                Reaper._container = FakeRyukContainer(port=ryuk.port)

        monkeypatch.setattr(Reaper, "get_instance", get_instance_second_time)

        ensure_reaper_registered()

        assert reaper_state == ["get_instance", "delete_instance", "get_instance"]
        assert lifecycle._reaper_registered is True
        ryuk.close()

    def test_a_reaper_that_never_answers_fails_the_session(self, reaper_state: list[str]) -> None:
        deaf = FakeRyuk(ack=False)
        Reaper._socket = _reset_socket()
        Reaper._container = FakeRyukContainer(port=deaf.port)

        with pytest.raises(RuntimeError, match="never acknowledged"):
            ensure_reaper_registered()

        assert reaper_state.count("delete_instance") == lifecycle.RYUK_REGISTER_ATTEMPTS
        assert lifecycle._reaper_registered is False
        deaf.close()

    def test_disabled_ryuk_is_a_no_op(
        self, reaper_state: list[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(lifecycle.testcontainers_config, "ryuk_disabled", True)
        ensure_reaper_registered()
        assert reaper_state == []

    def test_registration_is_once_per_process(self, reaper_state: list[str]) -> None:
        lifecycle._reaper_registered = True
        ensure_reaper_registered()
        assert reaper_state == []
