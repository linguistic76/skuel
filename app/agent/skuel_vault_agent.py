#!/usr/bin/env python3
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "cryptography>=48.0.0",
#     "websockets>=16.0",
# ]
# ///
# skuel-lint: disable-file=SKUEL015 -- interactive user-facing CLI: print() IS the UI (CLAUDE.md Logging Patterns)
"""
SKUEL Vault Agent — the user-side component (ADR-075 B3)
=========================================================

Runs on YOUR machine, next to your Obsidian vault. It holds the only
filesystem handle to the vault, enrolls once with a pairing code, then keeps
a single outbound WebSocket open to your SKUEL server and answers vault RPCs
(``describe_wall`` / ``list_changed_since`` / ``read_note`` /
``write_task_updates``). The server never learns the vault's absolute path,
and content outside the allowed folders never leaves this device — the
privacy wall is enforced HERE, before anything crosses the wire.

Commands:
    enroll --server URL --vault PATH [--name NAME]   pair this machine
    run                                              connect and serve RPCs
    status                                           show config + reachability

Invocation (from a SKUEL checkout):
    uv run agent/skuel_vault_agent.py enroll --server https://... --vault ~/vault
    uv run agent/skuel_vault_agent.py run

State (ADR-075 Decision 2 — the SSH threat model):
    ~/.config/skuel-agent/config.toml   server URL, vault root, allowed folders (dir 0700)
    ~/.config/skuel-agent/device.key    Ed25519 private key, PEM PKCS8 (file 0600,
                                        permission-checked at startup, never
                                        printed or logged, never leaves the device)

Wire protocol: docs/decisions/ADR-075-local-agent-vault-transport.md Decision 3.
Server half: adapters/inbound/device_routes.py (handshake) +
adapters/inbound/agent_channel_registry.py (RPC envelope).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import getpass
import hashlib
import json
import os
import platform
import random
import sys
import tempfile
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Repo-root bootstrap: when uv runs this file as a PEP 723 script, sys.path[0]
# is agent/, not the checkout root — insert the root so the shared vault-line
# contract imports. core/ports/vault_bridge_protocol.py is deliberately
# importable with a stdlib-only dependency chain (no structlog/pydantic/neo4j),
# so this works in the script's minimal env as well as in the repo venv.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.ports.vault_bridge_protocol import (  # noqa: E402
    TaskLineUpdate,
    apply_task_updates,
)

AGENT_VERSION = "0.2.0"  # 0.2.0: je_pro served (ADR-073 amendment)

# Must match adapters/inbound/device_routes.py PROTOCOL_VERSION — the agent
# hard-fails on mismatch (ADR-075 Consequences: version skew is a real category).
# The shared line-hash digest (core/ports/vault_bridge_protocol.py) is part of
# this protocol: the server sends ``source_line_hash`` values the agent must
# reproduce on the device to find the line to inject into, so a change to what
# the digest ignores is a protocol change — bump here AND on the server, never
# one side. So is the write-result frame's shape: v2 added ``updates_applied``
# (one bool per update, in order), which the server reads fail-closed.
PROTOCOL_VERSION = 2

# Must equal core.auth.device_signature.AGENT_SIGNATURE_DOMAIN. Duplicated here
# (and contract-tested in tests/unit/test_vault_agent.py) because importing
# core.auth pulls bcrypt into the PEP 723 minimal env; the byte string is the
# frozen ADR-075 Decision 3 wire constant either way.
AGENT_SIGNATURE_DOMAIN = b"skuel-vault-agent-v1"

# The doorway folders (ADR-070 Decision 8). Must stay in sync with
# core/services/ingestion/config.py _DEFAULT_SYNC_SUBDIRS — contract-tested,
# not imported (that module drags the full ingestion dependency chain).
DEFAULT_ALLOWED_FOLDERS: tuple[str, ...] = (
    "activity_notes",
    "je_pro",
    "knowledge",
    "periodic_notes",
    "personal_notes",
)

# The unconditional je_* staging floor (ADR-073): journal artifacts never cross
# the wire even inside an allowed folder. Mirror of ingestion config's
# STAGING_EXCLUDED_DIRS (contract-tested). je_pro left the floor with the
# 2026-07-11 ADR-073 amendment — it is a conditional doorway now; the
# per-file frontmatter consent gate is SERVER-side (ingestion), the agent
# just serves the folder.
STAGING_EXCLUDED_DIRS: frozenset[str] = frozenset({"je_in", "je_out", "je_raw"})

# What list_changed_since reports — mirrors the server-side collect discipline.
INGESTIBLE_SUFFIXES: frozenset[str] = frozenset({".md", ".yaml", ".yml"})

CONFIG_DIR = Path.home() / ".config" / "skuel-agent"
CONFIG_PATH = CONFIG_DIR / "config.toml"
KEY_PATH = CONFIG_DIR / "device.key"

# Reconnect backoff: capped exponential with jitter. The server rate-limits
# handshakes at 10/min/IP, so the floor stays above 6s and a reconnect storm
# can never trip it.
BACKOFF_INITIAL_S = 8.0
BACKOFF_CAP_S = 300.0
HANDSHAKE_TIMEOUT_S = 30.0

# Server-side close codes the agent must treat as fatal (do not reconnect):
# 4000 superseded (another agent took over), 4001 revoked, 4003 unauthorized.
_FATAL_CLOSE_CODES = {
    4000: "another agent connected for this account — this one stands down",
    4001: "this device was revoked in Settings → Devices",
    4003: "the server rejected this device — re-enroll with a fresh pairing code",
}


class AgentError(Exception):
    """Fatal agent-side condition — printed to the user, no traceback."""


class RPCError(Exception):
    """An RPC refusal carrying a stable error code (ADR-075 error frame)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class WallError(RPCError):
    """Containment/allowlist refusal — one uniform shape, no oracle."""

    def __init__(self) -> None:
        super().__init__("path_escapes_wall", "relative path is outside the allowed folders")


# ============================================================================
# CONFIG
# ============================================================================


@dataclass(frozen=True)
class AgentConfig:
    """Agent-side configuration persisted at ~/.config/skuel-agent/config.toml."""

    server_url: str
    vault_root: Path
    device_name: str
    allowed_folders: tuple[str, ...]


def _toml_string(value: str) -> str:
    """Serialize one TOML basic string (JSON string escaping is valid TOML)."""
    return json.dumps(value)


def save_config(config: AgentConfig) -> None:
    """Write config.toml (config dir created 0700)."""
    ensure_config_dir()
    lines = [
        "# SKUEL vault agent — written by `skuel-vault-agent enroll`",
        f"server_url = {_toml_string(config.server_url)}",
        f"vault_root = {_toml_string(str(config.vault_root))}",
        f"device_name = {_toml_string(config.device_name)}",
        "allowed_folders = ["
        + ", ".join(_toml_string(folder) for folder in config.allowed_folders)
        + "]",
        "",
    ]
    CONFIG_PATH.write_text("\n".join(lines), encoding="utf-8")


def load_config() -> AgentConfig:
    """Load and validate config.toml; AgentError if missing or malformed."""
    if not CONFIG_PATH.exists():
        raise AgentError(f"No config at {CONFIG_PATH} — run `enroll` first.")
    try:
        data = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise AgentError(f"Cannot read {CONFIG_PATH}: {exc}") from exc

    server_url = data.get("server_url")
    vault_root = data.get("vault_root")
    device_name = data.get("device_name")
    allowed = data.get("allowed_folders", list(DEFAULT_ALLOWED_FOLDERS))
    if not isinstance(server_url, str) or not isinstance(vault_root, str):
        raise AgentError(f"{CONFIG_PATH} is missing server_url/vault_root — re-run `enroll`.")
    if not isinstance(device_name, str):
        device_name = _default_device_name()
    if not isinstance(allowed, list) or not all(isinstance(f, str) for f in allowed):
        raise AgentError(f"{CONFIG_PATH} has a malformed allowed_folders list.")
    return AgentConfig(
        server_url=server_url.rstrip("/"),
        vault_root=Path(vault_root),
        device_name=device_name,
        allowed_folders=tuple(allowed),
    )


def ensure_config_dir() -> None:
    """Create ~/.config/skuel-agent with 0700 (chmod explicitly — mkdir obeys umask)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.chmod(0o700)


def _default_device_name() -> str:
    return platform.node() or "my-device"


# ============================================================================
# DEVICE KEY (Ed25519 — private key never leaves this machine)
# ============================================================================


def check_key_permissions(path: Path) -> None:
    """Refuse a key readable by group/other — same posture as OpenSSH."""
    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        raise AgentError(
            f"Refusing to use {path}: permissions {mode:03o} are too open "
            f"(must be 0600). Fix with: chmod 600 {path}"
        )


def load_private_key() -> Ed25519PrivateKey:
    """Load the device key; AgentError if absent, malformed, or too open."""
    if not KEY_PATH.exists():
        raise AgentError(f"No device key at {KEY_PATH} — run `enroll` first.")
    check_key_permissions(KEY_PATH)
    try:
        key = serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)
    except (ValueError, TypeError) as exc:
        raise AgentError(f"Device key at {KEY_PATH} is not a valid private key.") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise AgentError(f"Device key at {KEY_PATH} is not an Ed25519 key.")
    return key


def generate_or_load_private_key() -> Ed25519PrivateKey:
    """Enrollment key source: reuse an existing key, else generate at 0600."""
    if KEY_PATH.exists():
        return load_private_key()
    ensure_config_dir()
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    # O_EXCL + explicit 0600 at creation: never a window where the key is open.
    fd = os.open(KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(pem)
    return key


def public_key_b64url(private_key: Ed25519PrivateKey) -> str:
    """base64url (unpadded) DER SubjectPublicKeyInfo — the enrollment/auth wire shape."""
    der = private_key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return base64.urlsafe_b64encode(der).decode("ascii").rstrip("=")


def sign_challenge(private_key: Ed25519PrivateKey, nonce: str) -> str:
    """Ed25519 over ``AGENT_SIGNATURE_DOMAIN || nonce`` — exactly what
    core.auth.device_signature.verify_agent_signature checks."""
    signature = private_key.sign(AGENT_SIGNATURE_DOMAIN + nonce.encode("ascii"))
    return base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")


# ============================================================================
# THE WALL (agent-side containment — walled content never leaves the device)
# ============================================================================


def resolve_in_wall(vault_root: Path, allowed_folders: tuple[str, ...], relative_path: str) -> Path:
    """Resolve a wire path against the vault root; WallError on any escape.

    Mirrors FilesystemVaultAdapter._resolve (resolve + is_relative_to) and adds
    the agent-side allowlist + je_* staging floor + no-symlink rule
    (is_ingestible_path discipline): a path outside the allowed folders is
    REFUSED here, not just outside the root. One uniform refusal — no oracle
    distinguishing outside-root / walled-folder / symlink.
    """
    if not relative_path or Path(relative_path).is_absolute():
        raise WallError()
    root = vault_root.resolve()
    candidate = root / relative_path
    if candidate.is_symlink():  # leaf symlink: target may be outside the vault
        raise WallError()
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):  # collapses ../ and dir-symlink escapes
        raise WallError()
    rel_parts = resolved.relative_to(root).parts
    if not rel_parts or rel_parts[0] not in allowed_folders:
        raise WallError()
    if any(part in STAGING_EXCLUDED_DIRS for part in rel_parts):
        raise WallError()
    if resolved.suffix.lower() not in INGESTIBLE_SUFFIXES:
        # The sync surface is ingestible files only — read/write RPCs may not
        # touch anything list_changed_since would never report (Kody #530).
        raise WallError()
    return resolved


# ============================================================================
# RPC HANDLERS (ADR-075 Decision 3 — the four operations)
# ============================================================================


class VaultRPCHandler:
    """Serves the four vault RPCs against the local vault, wall-first.

    ``handle`` never raises: every failure becomes an error frame so a bad
    request can never kill the channel. Error messages carry vault-RELATIVE
    paths only — the server must never learn the absolute root.
    """

    def __init__(self, vault_root: Path, allowed_folders: tuple[str, ...]) -> None:
        self._root = vault_root.resolve()
        self._allowed_folders = allowed_folders

    def handle(self, frame: dict[str, Any]) -> dict[str, Any]:
        """Dispatch one request frame → one response frame (never raises)."""
        frame_id = frame.get("id")
        op = frame.get("op")
        params_raw = frame.get("params")
        params: dict[str, Any] = params_raw if isinstance(params_raw, dict) else {}
        try:
            if op == "describe_wall":
                result = self._describe_wall()
            elif op == "list_changed_since":
                result = self._list_changed_since()
            elif op == "read_note":
                result = self._read_note(params)
            elif op == "write_task_updates":
                result = self._write_task_updates(params)
            else:
                return self._error(frame_id, "unknown_op", f"unknown op {op!r}")
            return {"id": frame_id, "ok": True, "result": result}
        except RPCError as exc:
            return self._error(frame_id, exc.code, exc.message)
        except (
            Exception
        ) as exc:  # safety-net: a handler bug must become an error frame, not a dead channel
            return self._error(
                frame_id, "internal_error", self._scrub(f"{type(exc).__name__}: {exc}")
            )

    @staticmethod
    def _error(frame_id: Any, code: str, message: str) -> dict[str, Any]:
        return {"id": frame_id, "ok": False, "error": {"code": code, "message": message}}

    def _scrub(self, message: str) -> str:
        """Strip the device-side absolute root from any outbound message."""
        return message.replace(str(self._root), "<vault>")

    def _resolve(self, relative_path: str) -> Path:
        return resolve_in_wall(self._root, self._allowed_folders, relative_path)

    @staticmethod
    def _require_str(params: dict[str, Any], key: str) -> str:
        value = params.get(key)
        if not isinstance(value, str):
            raise RPCError("invalid_params", f"missing or non-string param {key!r}")
        return value

    # -- describe_wall -------------------------------------------------------

    def _describe_wall(self) -> dict[str, Any]:
        """Self-report the allowed folders — keeps the server's privacy-wall UI honest."""
        return {
            "allowed_folders": sorted(self._allowed_folders),
            "agent_version": AGENT_VERSION,
        }

    # -- list_changed_since --------------------------------------------------

    def _list_changed_since(self) -> dict[str, Any]:
        """Full listing of allowed files (v1: ``since_state`` is always null — ADR-075).

        Walks ONLY the allowed folders, never follows symlinks, skips je_*
        staging dirs and non-ingestible suffixes. Absence from this listing is
        the server's deletion signal, so the listing must be complete.
        """
        files: list[dict[str, Any]] = []
        for folder in sorted(self._allowed_folders):
            folder_path = self._root / folder
            # A symlinked allowed-root folder would make os.walk leak metadata
            # for files outside the vault (followlinks=False only guards BELOW
            # the top) — refuse it like any other symlink (Kody #530).
            if folder_path.is_symlink() or not folder_path.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(folder_path, followlinks=False):
                dirnames[:] = sorted(d for d in dirnames if d not in STAGING_EXCLUDED_DIRS)
                for filename in sorted(filenames):
                    path = Path(dirpath) / filename
                    if path.suffix.lower() not in INGESTIBLE_SUFFIXES or path.is_symlink():
                        continue
                    if not path.resolve().is_relative_to(self._root):
                        continue  # belt-and-braces: resolved location must stay in-vault
                    try:
                        content = path.read_text(encoding="utf-8")
                        stat_result = path.stat()
                    except OSError, UnicodeDecodeError:
                        continue  # unreadable/undecodable: not listable, keep walking
                    sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
                    files.append(
                        {
                            "relative_path": path.relative_to(self._root).as_posix(),
                            "content_hash": f"sha256:{sha}",
                            "mtime": datetime.fromtimestamp(stat_result.st_mtime, tz=UTC).strftime(
                                "%Y-%m-%dT%H:%M:%SZ"
                            ),
                            "size": stat_result.st_size,
                        }
                    )
        digest = hashlib.sha256(
            "\n".join(f"{f['relative_path']}:{f['content_hash']}" for f in files).encode("utf-8")
        ).hexdigest()
        return {"state": f"st_{digest[:12]}", "files": files}

    # -- read_note -----------------------------------------------------------

    def _read_note(self, params: dict[str, Any]) -> dict[str, Any]:
        relative_path = self._require_str(params, "relative_path")
        path = self._resolve(relative_path)
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise RPCError(
                "read_failed", f"cannot read {relative_path!r}: {type(exc).__name__}"
            ) from exc
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return {"content": content, "sha256": sha}

    # -- write_task_updates --------------------------------------------------

    def _write_task_updates(self, params: dict[str, Any]) -> dict[str, Any]:
        """Apply task-line writes with the same guard + mechanics as Stage 1:
        shared pure mutations (``apply_task_updates``), SHA-256 stale-read
        guard, atomic temp-file + ``rename()``. Write-level failures mirror
        ``WriteResult`` (``success: false`` + ``error``); only wall/param
        refusals become error frames.

        A successful reply carries ``updates_applied`` — one bool per update,
        in the order received (protocol v2). The server gates per-update state
        on it: file-level success is not proof that a given update found its
        line.
        """
        relative_path = self._require_str(params, "relative_path")
        expected_sha256 = self._require_str(params, "expected_sha256")
        updates = self._parse_updates(params)
        path = self._resolve(relative_path)

        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return {
                "success": False,
                "error": f"cannot read {relative_path!r}: {type(exc).__name__}",
            }

        current_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if current_sha256 != expected_sha256:
            return {
                "success": False,
                "error": (
                    f"Stale-read guard: file changed since last sync "
                    f"(expected {expected_sha256[:8]}, got {current_sha256[:8]}). "
                    "Re-queue for re-sync."
                ),
            }

        new_content, applied = apply_task_updates(content, updates)
        if not any(applied):
            return {
                "success": True,
                "new_sha256": current_sha256,
                "updates_applied": list(applied),
            }

        new_sha256 = hashlib.sha256(new_content.encode("utf-8")).hexdigest()
        try:
            fd, tmp_path_str = tempfile.mkstemp(dir=path.parent, suffix=".skuel_tmp")
            tmp_path = Path(tmp_path_str)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(new_content)
                tmp_path.rename(path)
            except OSError:
                tmp_path.unlink(missing_ok=True)
                raise
        except OSError as exc:
            return {"success": False, "error": self._scrub(f"write failed: {exc}")}
        return {
            "success": True,
            "new_sha256": new_sha256,
            "updates_applied": list(applied),
        }

    @staticmethod
    def _parse_updates(params: dict[str, Any]) -> list[TaskLineUpdate]:
        raw_updates = params.get("updates")
        if not isinstance(raw_updates, list):
            raise RPCError("invalid_params", "missing or non-list param 'updates'")
        updates: list[TaskLineUpdate] = []
        for raw in raw_updates:
            if not isinstance(raw, dict) or not isinstance(raw.get("vault_id"), str):
                raise RPCError("invalid_params", "each update needs a string 'vault_id'")
            done_date = raw.get("done_date")
            source_line_hash = raw.get("source_line_hash")
            updates.append(
                TaskLineUpdate(
                    vault_id=raw["vault_id"],
                    mark_done=bool(raw.get("mark_done", False)),
                    done_date=done_date if isinstance(done_date, str) else None,
                    inject_vault_id=bool(raw.get("inject_vault_id", False)),
                    source_line_hash=(
                        source_line_hash if isinstance(source_line_hash, str) else None
                    ),
                )
            )
        return updates


# ============================================================================
# WS CLIENT (outbound-only; the server is the RPC caller — role inversion)
# ============================================================================


def derive_ws_url(server_url: str) -> str:
    """http(s)://host[/prefix] → ws(s)://host[/prefix]/ws/agent.

    A path prefix in the server URL (reverse-proxy subpath deployments) is
    preserved — dropping it would enroll fine and then never reconnect.
    """
    parsed = urllib.parse.urlparse(server_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    prefix = parsed.path.rstrip("/")
    return f"{scheme}://{parsed.netloc}{prefix}/ws/agent"


def check_server_scheme(server_url: str) -> None:
    """Refuse plaintext transport off localhost (AgentError).

    The pairing code, the device pubkey, and every vault RPC would otherwise
    cross the network unencrypted — ADR-075 Decision 1 makes TLS half of the
    channel security. ``http://`` stays allowed for localhost-only dev.
    """
    parsed = urllib.parse.urlparse(server_url)
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1"):
        return
    raise AgentError(
        f"Refusing non-HTTPS server URL {server_url!r} — the pairing code and "
        "vault content would cross the network unencrypted. Use https:// "
        "(plain http is allowed for localhost only)."
    )


async def perform_handshake(connection: Any, private_key: Ed25519PrivateKey) -> str:
    """Answer the challenge (ADR-075 Decision 3); return the session user_uid.

    Raises AgentError on any fatal refusal (protocol mismatch, not enrolled).
    ``connection`` is any object with async ``recv``/``send`` (websockets
    ClientConnection in production; a scripted fake in tests).
    """
    challenge = json.loads(await asyncio.wait_for(connection.recv(), HANDSHAKE_TIMEOUT_S))
    if not isinstance(challenge, dict) or challenge.get("type") != "challenge":
        raise ConnectionError("server did not send a challenge frame")
    if challenge.get("protocol") != PROTOCOL_VERSION:
        raise AgentError(
            f"Protocol mismatch: server speaks v{challenge.get('protocol')}, "
            f"this agent speaks v{PROTOCOL_VERSION}. Update the agent."
        )
    nonce = challenge.get("nonce")
    if not isinstance(nonce, str):
        raise ConnectionError("challenge frame carried no nonce")

    await connection.send(
        json.dumps(
            {
                "type": "auth",
                "device_pubkey": public_key_b64url(private_key),
                "signature": sign_challenge(private_key, nonce),
                "agent_version": AGENT_VERSION,
            }
        )
    )

    session = json.loads(await asyncio.wait_for(connection.recv(), HANDSHAKE_TIMEOUT_S))
    if not isinstance(session, dict) or session.get("type") != "session":
        raise ConnectionError("server did not send a session frame")
    if not session.get("ok"):
        raise AgentError(
            f"Server refused this device ({session.get('error', 'unknown')}). "
            "Re-enroll with a fresh pairing code from Settings → Devices."
        )
    user_uid = session.get("user_uid")
    return user_uid if isinstance(user_uid, str) else "unknown"


async def serve_rpcs(connection: Any, handler: VaultRPCHandler) -> None:
    """Answer request frames until the connection closes.

    Malformed inbound frames are dropped (the loop survives anything); every
    well-formed request gets exactly one response frame.
    """
    async for message in connection:
        try:
            frame = json.loads(message)
        except json.JSONDecodeError:
            print("  ! dropped a non-JSON frame from the server")
            continue
        if not isinstance(frame, dict):
            continue
        response = handler.handle(frame)
        await connection.send(json.dumps(response))


async def run_agent(config: AgentConfig, private_key: Ed25519PrivateKey) -> int:
    """Connect, serve, reconnect with capped exponential backoff. Runs until
    interrupted or a fatal condition (revoked / superseded / not enrolled)."""
    import websockets.asyncio.client
    import websockets.exceptions

    ws_url = derive_ws_url(config.server_url)
    handler = VaultRPCHandler(config.vault_root, config.allowed_folders)
    backoff = BACKOFF_INITIAL_S

    while True:
        close_code: int | None = None
        try:
            async with websockets.asyncio.client.connect(ws_url) as connection:
                user_uid = await perform_handshake(connection, private_key)
                print(f"Connected to {config.server_url} as {user_uid} — serving vault RPCs.")
                backoff = BACKOFF_INITIAL_S
                try:
                    await serve_rpcs(connection, handler)
                finally:
                    close_code = connection.close_code
        except AgentError as exc:
            print(f"Fatal: {exc}")
            return 1
        except websockets.exceptions.ConnectionClosed as exc:
            close_code = exc.rcvd.code if exc.rcvd is not None else None
        except (OSError, TimeoutError, json.JSONDecodeError, ConnectionError) as exc:
            print(f"Connection failed: {type(exc).__name__}: {exc}")

        if close_code in _FATAL_CLOSE_CODES:
            print(f"Fatal: {_FATAL_CLOSE_CODES[close_code]}.")
            return 1

        delay = min(backoff, BACKOFF_CAP_S) * random.uniform(1.0, 1.25)  # jitter, not crypto
        print(f"Reconnecting in {delay:.0f}s …")
        await asyncio.sleep(delay)
        backoff = min(backoff * 2, BACKOFF_CAP_S)


# ============================================================================
# COMMANDS
# ============================================================================


def cmd_enroll(server: str, vault: str, name: str | None) -> int:
    """Generate/reuse the device key, redeem a pairing code, save config."""
    server_url = server.rstrip("/")
    vault_root = Path(vault).expanduser().resolve()
    if not vault_root.is_dir():
        print(f"Vault path is not a directory: {vault_root}")
        return 1
    parsed = urllib.parse.urlparse(server_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        print(f"--server must be an http(s) URL, got: {server}")
        return 1
    check_server_scheme(server_url)  # refuse plaintext off localhost (AgentError)

    device_name = name or _default_device_name()
    private_key = generate_or_load_private_key()

    # Pairing code via getpass, never argv: no shoulder-surfing, no shell history.
    code = getpass.getpass("Pairing code (from Settings → Devices): ").strip()
    if not code:
        print("No code entered — aborting.")
        return 1

    body = json.dumps(
        {"code": code, "device_pubkey": public_key_b64url(private_key), "device_name": device_name}
    ).encode("utf-8")
    request = urllib.request.Request(  # scheme validated as http(s) above
        f"{server_url}/api/devices/enroll",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            print("Enrollment failed: pairing code invalid, expired, or already used.")
        elif exc.code == 429:
            print("Enrollment failed: rate-limited — wait a few minutes and try again.")
        else:
            print(f"Enrollment failed: server returned HTTP {exc.code}.")
        return 1
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Enrollment failed: cannot reach {server_url} ({exc}).")
        return 1

    config = AgentConfig(
        server_url=server_url,
        vault_root=vault_root,
        device_name=device_name,
        allowed_folders=DEFAULT_ALLOWED_FOLDERS,
    )
    save_config(config)
    print(f"Enrolled as {payload.get('name', device_name)} (device {payload.get('device_uid')}).")
    print(f"Config: {CONFIG_PATH}")
    print(f"Vault:  {vault_root}")
    print(
        f"Wall:   only {', '.join(DEFAULT_ALLOWED_FOLDERS)}/ are served — nothing else leaves this machine."
    )
    print("Next:   skuel-vault-agent run   (keep it running, then sync from SKUEL)")
    return 0


def cmd_run() -> int:
    """Connect to the server and serve vault RPCs until interrupted."""
    config = load_config()
    check_server_scheme(config.server_url)  # a hand-edited config gets the same TLS floor
    private_key = load_private_key()
    if not config.vault_root.is_dir():
        print(f"Vault root {config.vault_root} does not exist — fix {CONFIG_PATH}.")
        return 1
    try:
        return asyncio.run(run_agent(config, private_key))
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


def cmd_status() -> int:
    """Show config, key presence, and server reachability."""
    try:
        config = load_config()
    except AgentError as exc:
        print(f"Config:  {exc}")
        config = None
    if config is not None:
        print(f"Config:  {CONFIG_PATH}")
        print(f"Server:  {config.server_url}")
        print(f"Vault:   {config.vault_root} ({'ok' if config.vault_root.is_dir() else 'MISSING'})")
        print(f"Device:  {config.device_name}")
        print(f"Wall:    {', '.join(config.allowed_folders)}")

    if KEY_PATH.exists():
        try:
            check_key_permissions(KEY_PATH)
            print(f"Key:     {KEY_PATH} (0600 ok)")
        except AgentError as exc:
            print(f"Key:     {exc}")
    else:
        print(f"Key:     missing ({KEY_PATH}) — run `enroll`")

    if config is not None:
        try:
            request = urllib.request.Request(config.server_url, method="GET")
            with urllib.request.urlopen(request, timeout=5) as response:
                print(f"Reach:   {config.server_url} → HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            print(f"Reach:   {config.server_url} → HTTP {exc.code}")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"Reach:   {config.server_url} unreachable ({exc})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skuel-vault-agent",
        description="SKUEL vault agent — serves your Obsidian vault to your SKUEL server "
        "over one outbound WebSocket (ADR-075).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    enroll_parser = subparsers.add_parser("enroll", help="pair this machine with a one-time code")
    enroll_parser.add_argument("--server", required=True, help="SKUEL server URL (https://…)")
    enroll_parser.add_argument("--vault", required=True, help="path to your Obsidian vault root")
    enroll_parser.add_argument("--name", default=None, help="device label (default: hostname)")

    subparsers.add_parser("run", help="connect and serve vault RPCs until stopped")
    subparsers.add_parser("status", help="show config, key, and server reachability")

    args = parser.parse_args(argv)
    if args.command == "enroll":
        return cmd_enroll(args.server, args.vault, args.name)
    if args.command == "run":
        return cmd_run()
    return cmd_status()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AgentError as exc:
        print(f"Error: {exc}")
        sys.exit(1)
