"""
Agent Channel Registry — Live Vault-Agent WebSocket Sessions (ADR-075)
======================================================================

In-process registry of authenticated ``WS /ws/agent`` connections, keyed by
``user_uid``. One live channel per user in v1 — a second connection for the
same user SUPERSEDES the first (ADR-075 Decision 3).

Role inversion: the WS *connection* is agent→server (outbound-only from the
user's machine), but the *RPC caller* is the server — ``AgentSession.call``
sends a JSON-RPC-ish request frame and awaits the response frame the WS
receive loop feeds back via ``resolve``. B4's ``LocalAgentVaultAdapter``
resolves channels from this registry at sync time; in B2 the consumers are
the handshake endpoint (register/unregister) and device revocation
(``close_for_device``).

Process-local by design, like the session itself: the session lives exactly
as long as the connection — nothing to steal, nothing to expire, nothing to
store (ADR-075 Decision 3).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

logger = get_logger("skuel.adapters.agent_channel")

# Close codes surfaced to the agent (4xxx = application-defined).
CLOSE_SUPERSEDED = 4000
CLOSE_REVOKED = 4001

DEFAULT_RPC_TIMEOUT_S = 60.0


class AgentSession:
    """One authenticated agent connection: RPC framing over a WebSocket."""

    def __init__(self, websocket: WebSocket, user_uid: str, device_uid: str) -> None:
        self.websocket = websocket
        self.user_uid = user_uid
        self.device_uid = device_uid
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._next_id = 0

    async def call(
        self, op: str, params: dict[str, Any], timeout_s: float = DEFAULT_RPC_TIMEOUT_S
    ) -> Result[dict[str, Any]]:
        """Send one RPC request frame and await its response frame (B4 surface).

        Envelope (ADR-075 Decision 3): request ``{id, op, params}``; response
        echoes ``id`` with ``ok`` + ``result`` or ``ok: false`` + ``error``.
        """
        self._next_id += 1
        request_id = self._next_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self.websocket.send_json({"id": request_id, "op": op, "params": params})
            frame = await asyncio.wait_for(future, timeout=timeout_s)
        except TimeoutError:
            return Result.fail(
                Errors.integration("vault_agent", f"agent did not answer '{op}' in {timeout_s}s")
            )
        except OSError as e:
            return Result.fail(Errors.integration("vault_agent", f"agent channel failed: {e}"))
        finally:
            self._pending.pop(request_id, None)

        if frame.get("ok"):
            result = frame.get("result")
            return Result.ok(result if isinstance(result, dict) else {})
        error = frame.get("error") or {}
        return Result.fail(
            Errors.integration(
                "vault_agent",
                f"agent error {error.get('code', 'unknown')}: {error.get('message', '')}",
            )
        )

    def resolve(self, frame: dict[str, Any]) -> bool:
        """Feed a received response frame to its awaiting ``call``.

        Returns False for frames with no matching pending request (unsolicited
        or late — dropped; the agent never initiates, ADR-075 Decision 7).
        """
        frame_id = frame.get("id")
        future = self._pending.get(frame_id) if isinstance(frame_id, int) else None
        if future is None or future.done():
            return False
        future.set_result(frame)
        return True

    def fail_pending(self, reason: str) -> None:
        """Fail every in-flight RPC (connection lost / session closed)."""
        for future in self._pending.values():
            if not future.done():
                future.set_exception(ConnectionError(reason))
        self._pending.clear()

    async def close(self, code: int, reason: str) -> None:
        """Close the underlying WebSocket; in-flight RPCs fail immediately."""
        self.fail_pending(reason)
        try:
            await self.websocket.close(code=code, reason=reason)
        except OSError, RuntimeError:  # already closed / transport gone
            logger.debug("Agent WS for %s already closed", self.user_uid)


class AgentChannelRegistry:
    """Per-user live agent channels (one per user; newest supersedes)."""

    def __init__(self) -> None:
        self._sessions: dict[str, AgentSession] = {}

    def register(self, session: AgentSession) -> AgentSession | None:
        """Bind a session to its user; returns the superseded session, if any.

        The caller closes the superseded session (``CLOSE_SUPERSEDED``) — the
        registry never awaits inside registration.
        """
        previous = self._sessions.get(session.user_uid)
        self._sessions[session.user_uid] = session
        logger.info(
            "Agent channel registered for %s (device %s)%s",
            session.user_uid,
            session.device_uid,
            " — superseding previous connection" if previous else "",
        )
        return previous

    def unregister(self, session: AgentSession) -> None:
        """Remove a session — only if it is still the user's CURRENT one.

        A superseded session's late disconnect must not evict its successor.
        """
        if self._sessions.get(session.user_uid) is session:
            del self._sessions[session.user_uid]
            logger.info("Agent channel unregistered for %s", session.user_uid)

    def get(self, user_uid: str) -> AgentSession | None:
        """The user's live channel, or None — B4's sync-time resolution point."""
        return self._sessions.get(user_uid)

    async def close_for_device(self, user_uid: str, device_uid: str) -> bool:
        """Close the user's live session IF it belongs to this device.

        Called at revocation time (ADR-075 Decision 2: "any live session for
        it is closed server-side at revocation time").
        """
        session = self._sessions.get(user_uid)
        if session is None or session.device_uid != device_uid:
            return False
        del self._sessions[user_uid]
        await session.close(CLOSE_REVOKED, "device revoked")
        logger.info("Agent channel closed for %s (device %s revoked)", user_uid, device_uid)
        return True


# Process-wide singleton — same lifecycle as the module-level WS connection
# stores in ingestion_api.py. B4's compose wiring imports this instance to
# hand the reconciler its channel-resolution dependency.
agent_channel_registry = AgentChannelRegistry()


__all__ = [
    "CLOSE_REVOKED",
    "CLOSE_SUPERSEDED",
    "AgentChannelRegistry",
    "AgentSession",
    "agent_channel_registry",
]
