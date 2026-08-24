"""
WS /ws/agent handshake tests — ADR-075 Decision 3 accept/reject matrix.

Real Ed25519 keys sign the exact domain-separated payload
(``"skuel-vault-agent-v1" || nonce``); the WebSocket and UserService are
fakes. Covers: happy path, unknown pubkey, wrong-key signature, revoked
device, malformed frames, supersession, and revocation closing the live
session.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from starlette.websockets import WebSocketDisconnect

from adapters.inbound.agent_channel_registry import (
    CLOSE_REVOKED,
    CLOSE_SUPERSEDED,
    AgentChannelRegistry,
    AgentSession,
)
from adapters.inbound.device_routes import PROTOCOL_VERSION, handle_agent_ws
from core.auth.device_signature import (
    AGENT_SIGNATURE_DOMAIN,
    build_signed_payload,
    verify_agent_signature,
)
from core.models.auth.device import Device
from core.utils.result_simplified import Result


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _keypair() -> tuple[Ed25519PrivateKey, str]:
    private = Ed25519PrivateKey.generate()
    der = private.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private, _b64url(der)


def _sign(private: Ed25519PrivateKey, nonce: str) -> str:
    return _b64url(private.sign(build_signed_payload(nonce)))


def _device(pubkey: str, user_uid: str = "user_mike") -> Device:
    return Device(
        uid="device_ab12cd34",
        user_uid=user_uid,
        pubkey=pubkey,
        name="mike-laptop",
        enrolled_at=datetime.now(UTC),
    )


class FakeWebSocket:
    """Scripted WebSocket: frames may be dicts, exceptions, or callables.

    A callable frame receives this fake (AFTER the challenge was sent) and
    returns the next frame — how tests sign the real random nonce.
    """

    def __init__(self, frames: list[Any], *, host: str = "203.0.113.7") -> None:
        self.frames = list(frames)
        self.sent: list[dict[str, Any]] = []
        self.accepted = False
        self.closed: tuple[int, str | None] | None = None
        # Pre-auth throttle reads websocket.client.host (Kody #529 guard).
        self.client = SimpleNamespace(host=host)

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: dict[str, Any]) -> None:
        self.sent.append(data)

    async def receive_json(self) -> Any:
        if not self.frames:
            raise WebSocketDisconnect(code=1000)
        item = self.frames.pop(0)
        if callable(item):
            item = item(self)
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed = (code, reason)

    @property
    def challenge_nonce(self) -> str:
        assert self.sent and self.sent[0]["type"] == "challenge"
        return self.sent[0]["nonce"]

    @property
    def session_frame(self) -> dict[str, Any]:
        frames = [f for f in self.sent if f.get("type") == "session"]
        assert frames, f"no session frame sent: {self.sent}"
        return frames[-1]


def _user_service(device: Device | None) -> SimpleNamespace:
    return SimpleNamespace(
        get_device_by_pubkey=AsyncMock(return_value=Result.ok(device)),
        touch_device=AsyncMock(return_value=Result.ok(None)),
    )


class TestSignatureVerification:
    def test_valid_signature_over_domain_separated_nonce(self) -> None:
        private, pubkey = _keypair()
        assert verify_agent_signature(pubkey, "nonce123", _sign(private, "nonce123"))

    def test_wrong_key_rejected(self) -> None:
        private, _ = _keypair()
        _, other_pubkey = _keypair()
        assert not verify_agent_signature(other_pubkey, "nonce123", _sign(private, "nonce123"))

    def test_signature_over_different_nonce_rejected(self) -> None:
        private, pubkey = _keypair()
        assert not verify_agent_signature(pubkey, "nonce123", _sign(private, "nonce456"))

    def test_domain_prefix_is_required(self) -> None:
        # A signature over the bare nonce (no domain separation) must fail —
        # this is the cross-protocol-reuse guard.
        private, pubkey = _keypair()
        bare = _b64url(private.sign(b"nonce123"))
        assert not verify_agent_signature(pubkey, "nonce123", bare)
        assert build_signed_payload("nonce123") == AGENT_SIGNATURE_DOMAIN + b"nonce123"

    def test_malformed_inputs_rejected_not_raised(self) -> None:
        private, pubkey = _keypair()
        assert not verify_agent_signature("!!!not-b64!!!", "n", _sign(private, "n"))
        assert not verify_agent_signature(pubkey, "n", "!!!not-b64!!!")
        # Valid b64 but not a DER Ed25519 key.
        assert not verify_agent_signature(_b64url(b"just-bytes"), "n", _sign(private, "n"))


@pytest.fixture(autouse=True)
def _fresh_preauth_guards():
    """Each test gets clean rate buckets and an empty handshake gate —
    otherwise the shared per-IP bucket trips across the suite."""
    from adapters.inbound import device_routes
    from adapters.inbound.rate_limit import reset_buckets_for_testing

    reset_buckets_for_testing()
    device_routes._pending_handshakes._active = 0
    yield
    reset_buckets_for_testing()
    device_routes._pending_handshakes._active = 0


class TestPreAuthGuards:
    """Kody #529: the pre-accept throttle — an anonymous client cannot hold
    handshake sockets open faster than it earns them."""

    @pytest.mark.asyncio
    async def test_per_ip_rate_limit_rejects_before_accept(self) -> None:
        from adapters.inbound.device_routes import _CLOSE_RATE_LIMITED, _HANDSHAKE_RATE_LIMIT

        registry = AgentChannelRegistry()
        service = _user_service(None)
        for _ in range(_HANDSHAKE_RATE_LIMIT):
            await handle_agent_ws(FakeWebSocket([]), service, registry)  # type: ignore[arg-type]

        over = FakeWebSocket([])
        await handle_agent_ws(over, service, registry)  # type: ignore[arg-type]
        assert not over.accepted  # rejected at the upgrade, never accepted
        assert over.closed == (_CLOSE_RATE_LIMITED, "rate_limited")

    @pytest.mark.asyncio
    async def test_other_ip_unaffected_by_a_limited_ip(self) -> None:
        from adapters.inbound.device_routes import _HANDSHAKE_RATE_LIMIT

        registry = AgentChannelRegistry()
        service = _user_service(None)
        for _ in range(_HANDSHAKE_RATE_LIMIT + 1):
            await handle_agent_ws(FakeWebSocket([]), service, registry)  # type: ignore[arg-type]

        other = FakeWebSocket([], host="198.51.100.9")
        await handle_agent_ws(other, service, registry)  # type: ignore[arg-type]
        assert other.accepted

    @pytest.mark.asyncio
    async def test_concurrency_cap_rejects_and_gate_releases_after_reject(self) -> None:
        from adapters.inbound import device_routes
        from adapters.inbound.device_routes import _CLOSE_RATE_LIMITED

        registry = AgentChannelRegistry()
        service = _user_service(None)
        device_routes._pending_handshakes._active = device_routes._HANDSHAKE_CONCURRENCY_CAP
        capped = FakeWebSocket([])
        await handle_agent_ws(capped, service, registry)  # type: ignore[arg-type]
        assert not capped.accepted
        assert capped.closed == (_CLOSE_RATE_LIMITED, "handshake_capacity")

        # A failed-auth handshake must release its slot (finally-path guard).
        device_routes._pending_handshakes._active = 0
        rejected = FakeWebSocket([{"type": "auth", "device_pubkey": 1, "signature": 2}])
        await handle_agent_ws(rejected, service, registry)  # type: ignore[arg-type]
        assert device_routes._pending_handshakes._active == 0


class TestHandshake:
    @pytest.mark.asyncio
    async def test_happy_path_establishes_and_registers_the_session(self) -> None:
        private, pubkey = _keypair()
        registry = AgentChannelRegistry()
        seen_during_life: dict[str, Any] = {}

        def auth_frame(ws: FakeWebSocket) -> dict[str, Any]:
            return {
                "type": "auth",
                "device_pubkey": pubkey,
                "signature": _sign(private, ws.challenge_nonce),
                "agent_version": "0.1.0",
            }

        def probe_registry(ws: FakeWebSocket) -> Exception:
            seen_during_life["session"] = registry.get("user_mike")
            return WebSocketDisconnect(code=1000)

        ws = FakeWebSocket([auth_frame, probe_registry])
        user_service = _user_service(_device(pubkey))

        await handle_agent_ws(ws, user_service, registry)  # type: ignore[arg-type]

        assert ws.sent[0]["type"] == "challenge"
        assert ws.sent[0]["protocol"] == PROTOCOL_VERSION
        assert ws.session_frame == {"type": "session", "ok": True, "user_uid": "user_mike"}
        user_service.touch_device.assert_awaited_once_with("device_ab12cd34")
        # Registered while alive; unregistered after disconnect.
        assert seen_during_life["session"] is not None
        assert seen_during_life["session"].device_uid == "device_ab12cd34"
        assert registry.get("user_mike") is None

    @pytest.mark.asyncio
    async def test_unknown_pubkey_rejected_uniformly(self) -> None:
        private, pubkey = _keypair()

        def auth_frame(ws: FakeWebSocket) -> dict[str, Any]:
            return {
                "type": "auth",
                "device_pubkey": pubkey,
                "signature": _sign(private, ws.challenge_nonce),
            }

        ws = FakeWebSocket([auth_frame])
        registry = AgentChannelRegistry()

        await handle_agent_ws(ws, _user_service(None), registry)  # type: ignore[arg-type]

        assert ws.session_frame == {
            "type": "session",
            "ok": False,
            "error": "device_not_enrolled",
        }
        assert ws.closed is not None and ws.closed[0] == 4003
        assert registry.get("user_mike") is None

    @pytest.mark.asyncio
    async def test_wrong_key_signature_rejected_with_the_same_shape(self) -> None:
        # Device IS enrolled, but the signature comes from a different key —
        # the failure must be indistinguishable from unknown-pubkey.
        _, pubkey = _keypair()
        imposter, _ = _keypair()

        def auth_frame(ws: FakeWebSocket) -> dict[str, Any]:
            return {
                "type": "auth",
                "device_pubkey": pubkey,
                "signature": _sign(imposter, ws.challenge_nonce),
            }

        ws = FakeWebSocket([auth_frame])
        user_service = _user_service(_device(pubkey))

        await handle_agent_ws(ws, user_service, AgentChannelRegistry())  # type: ignore[arg-type]

        assert ws.session_frame["ok"] is False
        assert ws.session_frame["error"] == "device_not_enrolled"
        user_service.touch_device.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_revoked_device_rejected(self) -> None:
        # The lookup contract returns None for revoked devices (unrevoked-only
        # query) — a revoked device fails exactly like an unknown one.
        private, pubkey = _keypair()

        def auth_frame(ws: FakeWebSocket) -> dict[str, Any]:
            return {
                "type": "auth",
                "device_pubkey": pubkey,
                "signature": _sign(private, ws.challenge_nonce),
            }

        ws = FakeWebSocket([auth_frame])

        await handle_agent_ws(ws, _user_service(None), AgentChannelRegistry())  # type: ignore[arg-type]

        assert ws.session_frame["error"] == "device_not_enrolled"

    @pytest.mark.asyncio
    async def test_malformed_auth_frame_rejected(self) -> None:
        ws = FakeWebSocket([{"type": "hello", "junk": True}])

        await handle_agent_ws(ws, _user_service(None), AgentChannelRegistry())  # type: ignore[arg-type]

        assert ws.session_frame["ok"] is False
        assert ws.closed is not None and ws.closed[0] == 4003

    @pytest.mark.asyncio
    async def test_second_connection_supersedes_the_first(self) -> None:
        private, pubkey = _keypair()
        registry = AgentChannelRegistry()

        old_ws = FakeWebSocket([])
        old_session = AgentSession(old_ws, user_uid="user_mike", device_uid="device_old00000")  # type: ignore[arg-type]
        registry.register(old_session)

        def auth_frame(ws: FakeWebSocket) -> dict[str, Any]:
            return {
                "type": "auth",
                "device_pubkey": pubkey,
                "signature": _sign(private, ws.challenge_nonce),
            }

        ws = FakeWebSocket([auth_frame])

        await handle_agent_ws(ws, _user_service(_device(pubkey)), registry)  # type: ignore[arg-type]

        assert old_ws.closed is not None
        assert old_ws.closed[0] == CLOSE_SUPERSEDED
        assert ws.session_frame["ok"] is True


class TestRegistry:
    @pytest.mark.asyncio
    async def test_revocation_closes_the_live_session(self) -> None:
        registry = AgentChannelRegistry()
        ws = FakeWebSocket([])
        session = AgentSession(ws, user_uid="user_mike", device_uid="device_ab12cd34")  # type: ignore[arg-type]
        registry.register(session)

        closed = await registry.close_for_device("user_mike", "device_ab12cd34")

        assert closed is True
        assert ws.closed is not None and ws.closed[0] == CLOSE_REVOKED
        assert registry.get("user_mike") is None

    @pytest.mark.asyncio
    async def test_revoking_a_different_device_leaves_the_session_alone(self) -> None:
        registry = AgentChannelRegistry()
        ws = FakeWebSocket([])
        session = AgentSession(ws, user_uid="user_mike", device_uid="device_ab12cd34")  # type: ignore[arg-type]
        registry.register(session)

        closed = await registry.close_for_device("user_mike", "device_other000")

        assert closed is False
        assert ws.closed is None
        assert registry.get("user_mike") is session

    def test_superseded_sessions_late_disconnect_does_not_evict_successor(self) -> None:
        registry = AgentChannelRegistry()
        first = AgentSession(FakeWebSocket([]), "user_mike", "device_a0000000")  # type: ignore[arg-type]
        second = AgentSession(FakeWebSocket([]), "user_mike", "device_b0000000")  # type: ignore[arg-type]
        registry.register(first)
        registry.register(second)

        registry.unregister(first)  # the superseded connection's finally-block

        assert registry.get("user_mike") is second

    @pytest.mark.asyncio
    async def test_rpc_call_resolves_matching_response_frame(self) -> None:
        # The B4-facing surface: one in-flight request, response by id.
        import asyncio

        ws = FakeWebSocket([])
        session = AgentSession(ws, "user_mike", "device_ab12cd34")  # type: ignore[arg-type]

        task = asyncio.create_task(session.call("describe_wall", {}, timeout_s=2))
        await asyncio.sleep(0)  # let the request frame go out
        request = ws.sent[-1]
        assert request["op"] == "describe_wall"
        assert session.resolve({"id": request["id"], "ok": True, "result": {"x": 1}})

        result = await task
        assert result.is_ok
        assert result.value == {"x": 1}
        # Unmatched frames are dropped, not crashed on.
        assert not session.resolve({"id": 999, "ok": True})
