"""
Device Routes — Vault-Agent Enrollment, Revocation, WS Handshake (ADR-075 B2)
=============================================================================

Routes:
    GET  /settings/devices                — Settings → Devices page (list + pair + revoke).
    POST /settings/devices/pairing-code   — HTMX: mint a one-time pairing code (shown once).
    POST /settings/devices/revoke         — HTMX: revoke a device, return refreshed list.
    POST /api/devices/pairing-code        — JSON API: mint a pairing code (authed).
    POST /api/devices/enroll              — JSON API: agent enrollment. UNAUTHENTICATED by
                                            design — the one-time pairing code IS the
                                            credential (hashed storage, 10-min TTL,
                                            single-use atomic burn). IP rate-limited.
    POST /api/devices/{uid}/revoke        — JSON API: revoke a device (authed).
    WS   /ws/agent                        — challenge-signature handshake (Ed25519 over
                                            the domain-separated nonce), then the live
                                            per-user agent channel.

Security (ADR-075 Decisions 2-3):
- Nonces: 32 bytes from ``secrets``, minted per connection, never reused.
- No oracle: unknown pubkey, bad signature, and revoked device all yield ONE
  uniform ``device_not_enrolled`` failure; wrong and expired pairing codes
  share one not-found shape.
- Sessions live exactly as long as the connection (no bearer token exists
  outside it); a second connection for the same user SUPERSEDES the first;
  revocation closes the live session server-side.

See: docs/decisions/ADR-075-local-agent-vault-transport.md
"""

from __future__ import annotations

import asyncio
import base64
import json
import secrets
from typing import TYPE_CHECKING, Any

from fasthtml.common import H3, Div, Form, Input, P, Span
from pydantic import ValidationError
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocketDisconnect

from adapters.inbound.agent_channel_registry import (
    CLOSE_SUPERSEDED,
    AgentSession,
    agent_channel_registry,
)
from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from adapters.inbound.rate_limit import allow_key, rate_limited_ip
from core.auth.device_signature import verify_agent_signature
from core.models.auth.device import Device, PairingCodeIssued
from core.models.auth.device_request import DeviceEnrollRequest
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from ui.components import Button, ButtonT
from ui.patterns import PageHeader

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

    from adapters.inbound.agent_channel_registry import AgentChannelRegistry
    from core.services.user_service import UserService

logger = get_logger("skuel.routes.devices")

# Agent must answer the challenge within this window or the socket closes.
HANDSHAKE_TIMEOUT_S = 30.0
PROTOCOL_VERSION = 1

# Application close code for a failed handshake (4003 = unauthorized, app-level convention).
_CLOSE_UNAUTHORIZED = 4003
# Policy-violation close code (RFC 6455 private range) for pre-auth throttling.
_CLOSE_RATE_LIMITED = 4008

# Pre-auth abuse posture (Kody #529): an unauthenticated client can hold a
# socket open for up to HANDSHAKE_TIMEOUT_S before any device check runs, so
# both axes are capped BEFORE accept — handshake attempts per IP per minute,
# and concurrently-open unauthenticated handshakes process-wide. A real agent
# handshakes once per connection; these bounds are invisible to it.
_HANDSHAKE_RATE_LIMIT = 10  # attempts per IP per 60s sliding window
_HANDSHAKE_CONCURRENCY_CAP = 8


class _HandshakeGate:
    """Non-blocking cap on concurrently-open unauthenticated handshakes.

    Synchronous acquire/release — atomic on the single-threaded event loop, so
    no lock is needed (unlike asyncio.Semaphore, which cannot try-acquire).
    """

    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._active = 0

    def try_acquire(self) -> bool:
        if self._active >= self._capacity:
            return False
        self._active += 1
        return True

    def release(self) -> None:
        self._active = max(0, self._active - 1)


_pending_handshakes = _HandshakeGate(_HANDSHAKE_CONCURRENCY_CAP)


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------


def _fmt(ts: Any) -> str:
    """Render an optional datetime for the device table."""
    return ts.strftime("%Y-%m-%d %H:%M UTC") if ts is not None else "never"


def _pairing_button(label: str = "Generate pairing code") -> Form:
    """HTMX form that mints a pairing code and swaps it into the pairing area."""
    return Form(
        Button(label, type="submit"),
        hx_post="/settings/devices/pairing-code",
        hx_target="#pairing-code-area",
        hx_swap="innerHTML",
    )


def _pairing_code_fragment(issued: PairingCodeIssued) -> Div:
    """The one-time reveal: the raw code exists only in this response."""
    return Div(
        Div(
            H3("Pairing code", cls="text-base font-semibold mb-2"),
            P(
                Span(issued.code, cls="font-mono text-2xl tracking-widest select-all"),
                cls="mb-2",
            ),
            P(
                f"Valid until {_fmt(issued.expires_at)}, single-use. "
                "Shown once — it is stored hashed and cannot be recovered. "
                "Run `skuel-vault-agent enroll` on your machine and paste it.",
                cls="text-sm text-base-content/70",
            ),
            cls="bg-base-200 border border-base-300 rounded-lg p-5 mb-4",
        ),
        _pairing_button("Generate a new code"),
    )


def _device_row(device: Device) -> Div:
    """One device: name, timestamps, revoked badge or revoke button."""
    if device.is_revoked:
        action: Any = Span(
            f"Revoked {_fmt(device.revoked_at)}",
            cls="text-xs font-semibold text-error",
        )
    else:
        action = Form(
            Input(type="hidden", name="device_uid", value=device.uid),
            Button("Revoke", type="submit", cls=ButtonT.secondary),
            hx_post="/settings/devices/revoke",
            hx_target="#devices-list",
            hx_swap="outerHTML",
            hx_confirm=f"Revoke '{device.name}'? Its agent loses access immediately.",
        )
    return Div(
        Div(
            P(device.name, cls="font-semibold"),
            P(
                f"Enrolled {_fmt(device.enrolled_at)} · last seen {_fmt(device.last_seen_at)}",
                cls="text-xs text-base-content/60",
            ),
        ),
        action,
        cls="flex items-center justify-between gap-4 py-3 border-b border-base-300 last:border-b-0",
    )


def _devices_list(devices: list[Device]) -> Div:
    """The device table fragment — swap target for revocation."""
    if not devices:
        body: tuple[Any, ...] = (P("No devices enrolled yet.", cls="text-sm text-base-content/70"),)
    else:
        body = tuple(_device_row(device) for device in devices)
    return Div(
        H3("Enrolled devices", cls="text-base font-semibold mb-2"),
        *body,
        id="devices-list",
        cls="bg-base-200 border border-base-300 rounded-lg p-5",
    )


def _devices_error(message: str) -> Div:
    """Error fragment for the devices list swap target."""
    return Div(P(message, cls="text-error text-sm"), id="devices-list")


# ---------------------------------------------------------------------------
# WS handshake (module-level for direct unit testing)
# ---------------------------------------------------------------------------


def _mint_nonce() -> str:
    """32 cryptographically random bytes as unpadded base64url (per connection)."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")


async def _reject_handshake(websocket: WebSocket) -> None:
    """One uniform failure shape — no oracle across unknown/bad-sig/revoked."""
    await websocket.send_json({"type": "session", "ok": False, "error": "device_not_enrolled"})
    await websocket.close(code=_CLOSE_UNAUTHORIZED, reason="device_not_enrolled")


async def handle_agent_ws(
    websocket: WebSocket,
    user_service: UserService,
    registry: AgentChannelRegistry,
) -> None:
    """Run the ADR-075 Decision 3 handshake, then hold the agent channel.

    1. Send ``{type: challenge, nonce, protocol}`` immediately on accept.
    2. Expect ``{type: auth, device_pubkey, signature}`` — Ed25519 over
       ``"skuel-vault-agent-v1" || nonce`` (domain-separated, replay-proof:
       the nonce is bound to THIS connection and never reused).
    3. Verify against enrolled UNREVOKED devices; stamp ``last_seen_at``;
       register the channel (superseding any previous one for this user).
    4. Feed subsequent frames to the session's pending RPCs until disconnect.

    Pre-auth abuse posture (Kody #529): before accept, the client IP is
    checked against a sliding-window rate limit AND a global cap on
    concurrently-open unauthenticated handshakes — an anonymous client cannot
    hold sockets open (HANDSHAKE_TIMEOUT_S each) faster than it earns them.
    """
    client_ip = websocket.client.host if websocket.client else "unknown"
    if not allow_key(f"ws-handshake:{client_ip}", _HANDSHAKE_RATE_LIMIT, 60.0):
        # Not yet accepted: closing here rejects the upgrade outright.
        await websocket.close(code=_CLOSE_RATE_LIMITED, reason="rate_limited")
        return
    if not _pending_handshakes.try_acquire():
        await websocket.close(code=_CLOSE_RATE_LIMITED, reason="handshake_capacity")
        return

    try:
        await websocket.accept()
        nonce = _mint_nonce()
        await websocket.send_json(
            {"type": "challenge", "nonce": nonce, "protocol": PROTOCOL_VERSION}
        )

        try:
            frame = await asyncio.wait_for(websocket.receive_json(), timeout=HANDSHAKE_TIMEOUT_S)
        except TimeoutError, json.JSONDecodeError:
            await _reject_handshake(websocket)
            return
        except WebSocketDisconnect:
            return
    finally:
        # The cap covers the UNAUTHENTICATED window only — released as soon as
        # the auth frame arrived (or the slot timed out), before verification.
        _pending_handshakes.release()

    if not isinstance(frame, dict) or frame.get("type") != "auth":
        await _reject_handshake(websocket)
        return
    pubkey = frame.get("device_pubkey")
    signature = frame.get("signature")
    if not isinstance(pubkey, str) or not isinstance(signature, str):
        await _reject_handshake(websocket)
        return

    # Verify the signature UNCONDITIONALLY (pure crypto, no DB branch), then
    # resolve the device — failure modes stay indistinguishable.
    signature_ok = verify_agent_signature(pubkey, nonce, signature)
    device_result = await user_service.get_device_by_pubkey(pubkey)
    device = device_result.value if device_result.is_ok else None
    if not signature_ok or device is None:
        await _reject_handshake(websocket)
        return

    touch = await user_service.touch_device(device.uid)
    if touch.is_error:  # non-fatal — last_seen is telemetry, not auth state
        logger.warning("Failed to stamp last_seen_at for %s", device.uid)

    session = AgentSession(websocket, user_uid=device.user_uid, device_uid=device.uid)
    superseded = registry.register(session)
    if superseded is not None:
        await superseded.close(CLOSE_SUPERSEDED, "superseded by a newer connection")

    await websocket.send_json({"type": "session", "ok": True, "user_uid": device.user_uid})
    logger.info("Agent session established for %s (device %s)", device.user_uid, device.uid)

    try:
        while True:
            try:
                response = await websocket.receive_json()
            except json.JSONDecodeError:
                logger.warning("Non-JSON frame from agent %s — dropped", device.uid)
                continue
            if isinstance(response, dict):
                session.resolve(response)
    except WebSocketDisconnect:
        logger.info("Agent disconnected for %s (device %s)", device.user_uid, device.uid)
    finally:
        session.fail_pending("agent disconnected")
        registry.unregister(session)


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def create_device_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    user_service: UserService,
) -> None:
    """Register device enrollment/revocation routes + the agent WS endpoint."""

    # ------------------------------------------------------------------
    # UI routes
    # ------------------------------------------------------------------

    @rt("/settings/devices")
    async def devices_page(request: Request) -> Any:
        """Settings → Devices: list, pair, revoke (ADR-075 Decision 2)."""
        user_uid = require_authenticated_user(request)
        from ui.layouts.base_page import BasePage

        devices_result = await user_service.list_devices(user_uid)
        devices_area = (
            _devices_list(devices_result.value)
            if devices_result.is_ok
            else _devices_error("Failed to load devices.")
        )

        content = Div(
            PageHeader(
                "Devices",
                subtitle="Machines enrolled to sync your vault through the SKUEL agent.",
            ),
            P(
                "Pair a device by generating a one-time code and running "
                "`skuel-vault-agent enroll` on that machine. Revoking a device "
                "immediately closes its live connection.",
                cls="text-base-content/70 mb-6",
            ),
            Div(_pairing_button(), id="pairing-code-area", cls="mb-6"),
            devices_area,
            cls="max-w-2xl",
        )
        return BasePage(
            content=content,
            title="Devices",
            request=request,
            active_page="settings",
        )

    @rt("/settings/devices/pairing-code", methods=["POST"])
    @csrf_protected
    async def pairing_code_htmx(request: Request) -> Any:
        """HTMX: mint a one-time pairing code and show it ONCE."""
        user_uid = require_authenticated_user(request)
        result = await user_service.create_device_pairing_code(user_uid)
        if result.is_error:
            return Div(
                P("Failed to generate a pairing code.", cls="text-error text-sm"),
                _pairing_button("Try again"),
            )
        return _pairing_code_fragment(result.value)

    @rt("/settings/devices/revoke", methods=["POST"])
    @csrf_protected
    async def revoke_device_htmx(request: Request) -> Any:
        """HTMX: revoke a device, close its live session, refresh the list."""
        user_uid = require_authenticated_user(request)
        form_data = await request.form()
        device_uid_raw = form_data.get("device_uid")
        device_uid = device_uid_raw if isinstance(device_uid_raw, str) else ""
        if not device_uid:
            return _devices_error("Missing device.")

        revoked = await user_service.revoke_device(user_uid, device_uid)
        if revoked.is_error:
            return _devices_error("Failed to revoke device.")
        if revoked.value:
            await agent_channel_registry.close_for_device(user_uid, device_uid)

        refreshed = await user_service.list_devices(user_uid)
        if refreshed.is_error:
            return _devices_error("Device revoked, but the list failed to refresh.")
        return _devices_list(refreshed.value)

    # ------------------------------------------------------------------
    # JSON API routes (ADR-075 B2 plan)
    # ------------------------------------------------------------------

    @rt("/api/devices/pairing-code", methods=["POST"])
    @csrf_protected
    @boundary_handler(success_status=200)
    async def pairing_code_api(request: Request) -> Result[dict[str, Any]]:
        """Mint a one-time pairing code for the authenticated user.

        Returns the raw code EXACTLY ONCE — the server stores only its hash.
        """
        user_uid = require_authenticated_user(request)
        result = await user_service.create_device_pairing_code(user_uid)
        if result.is_error:
            return Result.fail(result)
        issued = result.value
        return Result.ok({"code": issued.code, "expires_at": issued.expires_at.isoformat()})

    @rt("/api/devices/enroll", methods=["POST"])
    @rate_limited_ip(bucket="device_enroll", per_ip=10, window_s=600)
    @boundary_handler(success_status=201)
    async def enroll_device_api(request: Request) -> Result[dict[str, Any]]:
        """Enroll a vault-agent device — the pairing code IS the credential.

        UNAUTHENTICATED + no CSRF by design: the agent has no session and no
        cookies, so there is nothing for a cross-site request to ride on. The
        one-time code (hashed at rest, 10-min TTL, atomic single-use burn)
        authenticates this one call; the route is IP rate-limited
        (ADR-075 Decision 2). Wrong and expired codes return one 404 shape.
        """
        try:
            raw = await request.body()
            payload = json.loads(raw) if raw else {}
            body = DeviceEnrollRequest.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as e:
            return Result.fail(Errors.validation(f"Invalid request body: {e}", field="body"))

        result = await user_service.enroll_device(body.code, body.device_pubkey, body.device_name)
        if result.is_error:
            return Result.fail(result)
        device = result.value
        return Result.ok({"device_uid": device.uid, "name": device.name})

    @rt("/api/devices/{uid}/revoke", methods=["POST"])
    @csrf_protected
    @boundary_handler(success_status=200)
    async def revoke_device_api(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Revoke an owned device; closes any live agent session for it."""
        user_uid = require_authenticated_user(request)
        revoked = await user_service.revoke_device(user_uid, uid)
        if revoked.is_error:
            return Result.fail(revoked)
        if not revoked.value:
            # Not owned and nonexistent share one shape (404-not-403 posture).
            return Result.fail(Errors.not_found("Device", uid))
        await agent_channel_registry.close_for_device(user_uid, uid)
        return Result.ok({"revoked": True, "device_uid": uid})

    # ------------------------------------------------------------------
    # WS /ws/agent — raw starlette WebSocketRoute. FastHTML's @rt registers
    # HTTP routes only (a websocket scope never matches them), so the agent
    # channel mounts directly on the starlette router.
    # ------------------------------------------------------------------

    async def agent_ws_endpoint(websocket: WebSocket) -> None:
        await handle_agent_ws(websocket, user_service, agent_channel_registry)

    if app is not None:
        app.router.routes.append(WebSocketRoute("/ws/agent", endpoint=agent_ws_endpoint))

    logger.info("Device routes registered (settings UI, JSON API, /ws/agent)")


__all__ = ["create_device_routes", "handle_agent_ws"]
