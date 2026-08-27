"""
Vault agent tests — ADR-075 B3 (the user-side component).

Covers, against a REAL tmp_path vault:
- agent-side wall enforcement (allowed folder served; sibling refused;
  ``../`` / absolute / symlink escapes refused; ``je_*`` staging floor),
- ``list_changed_since`` hashes + relative paths,
- ``read_note`` roundtrip,
- ``write_task_updates`` happy path + stale-sha refusal + idempotent re-apply,
- frame dispatch: unknown op → error frame; handler exception → error frame,
  the loop survives; absolute vault root never leaks in messages,
- the cross-half contract: the agent's challenge signature verifies with the
  SERVER's ``verify_agent_signature`` (both halves imported side by side),
- duplicated constants pinned to their server-side sources.

No live network: the WS is faked with scripted frames (same pattern as
tests/unit/test_agent_ws_handshake.py).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from agent import skuel_vault_agent as agent
from agent.skuel_vault_agent import (
    DEFAULT_ALLOWED_FOLDERS,
    AgentError,
    VaultRPCHandler,
    WallError,
    perform_handshake,
    public_key_b64url,
    resolve_in_wall,
    serve_rpcs,
    sign_challenge,
)
from core.ports.vault_bridge_protocol import normalize_vault_line_hash


def _sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """A realistic vault: two allowed folders, a walled sibling, je_* staging,
    and symlink escape attempts."""
    (tmp_path / "periodic_notes").mkdir()
    (tmp_path / "knowledge" / "nested").mkdir(parents=True)
    (tmp_path / "private_journal").mkdir()  # sibling folder — walled
    (tmp_path / "periodic_notes" / "je_out").mkdir()  # staging floor

    (tmp_path / "periodic_notes" / "2026-07-06.md").write_text(
        "- [ ] review ADR draft 🆔 sk_x1c9q2\n- [ ] plain task, no id\n"
    )
    (tmp_path / "knowledge" / "nested" / "spaced-repetition.md").write_text("# SR\n")
    (tmp_path / "knowledge" / "edges.yaml").write_text("type: edge\n")
    (tmp_path / "knowledge" / "image.png").write_text("not-markdown")
    (tmp_path / "private_journal" / "secret.md").write_text("never leaves the device")
    (tmp_path / "periodic_notes" / "je_out" / "transcript.md").write_text("walled")

    # Leaf symlink inside an allowed folder pointing OUTSIDE the wall.
    (tmp_path / "periodic_notes" / "sneaky-link.md").symlink_to(
        tmp_path / "private_journal" / "secret.md"
    )
    return tmp_path


@pytest.fixture
def handler(vault: Path) -> VaultRPCHandler:
    return VaultRPCHandler(vault, ("periodic_notes", "knowledge"))


# ============================================================================
# THE WALL
# ============================================================================


class TestWall:
    def test_allowed_folder_resolves(self, vault: Path) -> None:
        p = resolve_in_wall(vault, ("periodic_notes",), "periodic_notes/2026-07-06.md")
        assert p == vault / "periodic_notes" / "2026-07-06.md"

    @pytest.mark.parametrize(
        "relative_path",
        [
            "private_journal/secret.md",  # sibling folder outside the allowlist
            "../outside.md",  # parent escape
            "periodic_notes/../private_journal/secret.md",  # nested parent escape
            "periodic_notes/sneaky-link.md",  # leaf symlink out of the wall
            "periodic_notes/je_out/transcript.md",  # je_* staging floor
            "knowledge/image.png",  # non-ingestible suffix — outside the sync surface
            "",  # empty
            ".",  # the root itself
        ],
    )
    def test_escapes_refused(self, vault: Path, relative_path: str) -> None:
        with pytest.raises(WallError):
            resolve_in_wall(vault, ("periodic_notes", "knowledge"), relative_path)

    def test_absolute_path_refused_even_when_inside_the_vault(self, vault: Path) -> None:
        # Wire paths are vault-RELATIVE by contract; an absolute path is never
        # accepted (the server can't know the root, so this is always hostile).
        with pytest.raises(WallError):
            resolve_in_wall(
                vault,
                ("periodic_notes",),
                str(vault / "periodic_notes" / "2026-07-06.md"),
            )

    def test_wall_refusal_is_one_uniform_shape(self, handler: VaultRPCHandler) -> None:
        # No oracle: outside-root, walled-folder, and symlink all look identical.
        shapes = {
            json.dumps(
                handler.handle({"id": 1, "op": "read_note", "params": {"relative_path": p}})[
                    "error"
                ]
            )
            for p in ("../x.md", "private_journal/secret.md", "periodic_notes/sneaky-link.md")
        }
        assert shapes == {
            '{"code": "path_escapes_wall", "message": "relative path is outside the allowed folders"}'
        }


# ============================================================================
# RPC HANDLERS
# ============================================================================


class TestDescribeWall:
    def test_reports_configured_folders_and_version(self, handler: VaultRPCHandler) -> None:
        response = handler.handle({"id": 41, "op": "describe_wall", "params": {}})
        assert response == {
            "id": 41,
            "ok": True,
            "result": {
                "allowed_folders": ["knowledge", "periodic_notes"],
                "agent_version": agent.AGENT_VERSION,
            },
        }


class TestListChangedSince:
    def test_lists_only_allowed_ingestible_files(self, handler: VaultRPCHandler) -> None:
        response = handler.handle(
            {"id": 42, "op": "list_changed_since", "params": {"since_state": None}}
        )
        assert response["ok"] is True
        paths = [f["relative_path"] for f in response["result"]["files"]]
        assert paths == [
            "knowledge/edges.yaml",
            "knowledge/nested/spaced-repetition.md",
            "periodic_notes/2026-07-06.md",
        ]
        # Walled/irrelevant content is ABSENT (never listed = never fetched):
        assert not any("private_journal" in p or "je_out" in p or "sneaky" in p for p in paths)

    def test_rows_carry_prefixed_hash_mtime_size(
        self, vault: Path, handler: VaultRPCHandler
    ) -> None:
        response = handler.handle(
            {"id": 42, "op": "list_changed_since", "params": {"since_state": None}}
        )
        row = next(
            f
            for f in response["result"]["files"]
            if f["relative_path"] == "periodic_notes/2026-07-06.md"
        )
        content = (vault / "periodic_notes" / "2026-07-06.md").read_text()
        assert row["content_hash"] == f"sha256:{_sha(content)}"
        assert row["size"] == len(content.encode("utf-8"))
        assert row["mtime"].endswith("Z")
        assert response["result"]["state"].startswith("st_")

    def test_state_changes_when_content_changes(
        self, vault: Path, handler: VaultRPCHandler
    ) -> None:
        first = handler.handle({"id": 1, "op": "list_changed_since", "params": {}})
        (vault / "knowledge" / "new-note.md").write_text("# new\n")
        second = handler.handle({"id": 2, "op": "list_changed_since", "params": {}})
        assert first["result"]["state"] != second["result"]["state"]

    def test_symlinked_allowed_root_folder_lists_nothing(self, tmp_path: Path, vault: Path) -> None:
        # An allowed folder that IS a symlink would let os.walk leak metadata
        # for out-of-vault files (followlinks=False only guards below the top).
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        (outside / "leaked.md").write_text("outside the vault\n")
        (vault / "activity_notes").symlink_to(outside)

        handler = VaultRPCHandler(vault, ("activity_notes",))
        response = handler.handle({"id": 1, "op": "list_changed_since", "params": {}})
        assert response["ok"] is True
        assert response["result"]["files"] == []


class TestReadNote:
    def test_roundtrip_content_and_sha(self, vault: Path, handler: VaultRPCHandler) -> None:
        response = handler.handle(
            {
                "id": 43,
                "op": "read_note",
                "params": {"relative_path": "periodic_notes/2026-07-06.md"},
            }
        )
        content = (vault / "periodic_notes" / "2026-07-06.md").read_text()
        assert response == {
            "id": 43,
            "ok": True,
            "result": {"content": content, "sha256": _sha(content)},
        }

    def test_missing_file_error_never_leaks_the_absolute_root(
        self, vault: Path, handler: VaultRPCHandler
    ) -> None:
        response = handler.handle(
            {"id": 43, "op": "read_note", "params": {"relative_path": "periodic_notes/nope.md"}}
        )
        assert response["ok"] is False
        assert response["error"]["code"] == "read_failed"
        assert str(vault) not in json.dumps(response)

    def test_missing_param_is_invalid_params(self, handler: VaultRPCHandler) -> None:
        response = handler.handle({"id": 43, "op": "read_note", "params": {}})
        assert response["ok"] is False
        assert response["error"]["code"] == "invalid_params"


class TestWriteTaskUpdates:
    def _params(self, vault: Path, updates: list[dict[str, Any]]) -> dict[str, Any]:
        content = (vault / "periodic_notes" / "2026-07-06.md").read_text()
        return {
            "relative_path": "periodic_notes/2026-07-06.md",
            "expected_sha256": _sha(content),
            "updates": updates,
        }

    def test_mark_done_flips_checkbox_and_appends_date(
        self, vault: Path, handler: VaultRPCHandler
    ) -> None:
        params = self._params(
            vault, [{"vault_id": "sk_x1c9q2", "mark_done": True, "done_date": "2026-07-06"}]
        )
        response = handler.handle({"id": 44, "op": "write_task_updates", "params": params})
        new_content = (vault / "periodic_notes" / "2026-07-06.md").read_text()
        assert response["result"] == {
            "success": True,
            "new_sha256": _sha(new_content),
            "updates_applied": [True],
        }
        assert "- [x] review ADR draft 🆔 sk_x1c9q2 ✅ 2026-07-06" in new_content

    def test_inject_id_targets_the_hashed_line(self, vault: Path, handler: VaultRPCHandler) -> None:
        line_hash = normalize_vault_line_hash("- [ ] plain task, no id\n")
        params = self._params(
            vault,
            [{"vault_id": "sk_m3k8p1", "inject_vault_id": True, "source_line_hash": line_hash}],
        )
        response = handler.handle({"id": 44, "op": "write_task_updates", "params": params})
        assert response["result"]["success"] is True
        assert (
            "- [ ] plain task, no id 🆔 sk_m3k8p1"
            in (vault / "periodic_notes" / "2026-07-06.md").read_text()
        )

    def test_stale_sha_refused_and_file_untouched(
        self, vault: Path, handler: VaultRPCHandler
    ) -> None:
        before = (vault / "periodic_notes" / "2026-07-06.md").read_text()
        params = self._params(
            vault, [{"vault_id": "sk_x1c9q2", "mark_done": True, "done_date": "2026-07-06"}]
        )
        params["expected_sha256"] = _sha("something else entirely")
        response = handler.handle({"id": 44, "op": "write_task_updates", "params": params})
        assert response["ok"] is True  # write-level failure mirrors WriteResult
        assert response["result"]["success"] is False
        assert "Stale-read guard" in response["result"]["error"]
        assert (vault / "periodic_notes" / "2026-07-06.md").read_text() == before

    def test_idempotent_reapply_is_a_clean_noop(
        self, vault: Path, handler: VaultRPCHandler
    ) -> None:
        update = {"vault_id": "sk_x1c9q2", "mark_done": True, "done_date": "2026-07-06"}
        first = handler.handle(
            {"id": 1, "op": "write_task_updates", "params": self._params(vault, [update])}
        )
        after_first = (vault / "periodic_notes" / "2026-07-06.md").read_text()
        second = handler.handle(
            {"id": 2, "op": "write_task_updates", "params": self._params(vault, [update])}
        )
        assert second["result"] == {
            "success": True,
            "new_sha256": first["result"]["new_sha256"],
            # The re-apply is a per-update no-op, and says so — a file-level
            # "success" alone could not tell the server that (protocol v2).
            "updates_applied": [False],
        }
        assert (vault / "periodic_notes" / "2026-07-06.md").read_text() == after_first

    def test_per_update_outcomes_separate_the_hit_from_the_miss(
        self, vault: Path, handler: VaultRPCHandler
    ) -> None:
        """A batch where one update lands and one matches no line reports BOTH.

        The file-level answer is "success" either way; only ``updates_applied``
        tells the server which 🆔 it may persist (done/reopen-vault-surface.md § Phantom-🆔).
        """
        params = self._params(
            vault,
            [
                {"vault_id": "sk_nomatch", "mark_done": True, "done_date": "2026-07-06"},
                {"vault_id": "sk_x1c9q2", "mark_done": True, "done_date": "2026-07-06"},
            ],
        )
        response = handler.handle({"id": 44, "op": "write_task_updates", "params": params})
        assert response["result"]["success"] is True
        assert response["result"]["updates_applied"] == [False, True]

    def test_mark_undone_unchecks_the_line_and_strips_the_done_date(
        self, vault: Path, handler: VaultRPCHandler
    ) -> None:
        """Protocol v3's operation, applied ON THE DEVICE — byte-exact reverse.

        The agent shares ``apply_task_updates`` with the server precisely so
        the un-check behaves identically wherever the vault lives.
        """
        before = (vault / "periodic_notes" / "2026-07-06.md").read_text()
        done = handler.handle(
            {
                "id": 1,
                "op": "write_task_updates",
                "params": self._params(
                    vault,
                    [{"vault_id": "sk_x1c9q2", "mark_done": True, "done_date": "2026-07-06"}],
                ),
            }
        )
        assert done["result"]["updates_applied"] == [True]

        undone = handler.handle(
            {
                "id": 2,
                "op": "write_task_updates",
                "params": self._params(vault, [{"vault_id": "sk_x1c9q2", "mark_undone": True}]),
            }
        )
        assert undone["result"]["updates_applied"] == [True]
        assert (vault / "periodic_notes" / "2026-07-06.md").read_text() == before

    def test_mark_undone_on_an_open_line_is_a_reported_noop(
        self, vault: Path, handler: VaultRPCHandler
    ) -> None:
        """Nothing to undo — and the agent says so per-update, not just file-level."""
        before = (vault / "periodic_notes" / "2026-07-06.md").read_text()
        response = handler.handle(
            {
                "id": 3,
                "op": "write_task_updates",
                "params": self._params(vault, [{"vault_id": "sk_x1c9q2", "mark_undone": True}]),
            }
        )
        assert response["result"]["success"] is True
        assert response["result"]["updates_applied"] == [False]
        assert (vault / "periodic_notes" / "2026-07-06.md").read_text() == before

    @pytest.mark.parametrize(
        ("flag", "extra"),
        [
            # Each flag is aimed at a line state where COERCING it would
            # actually mutate the file — a truthy-string test against a line
            # the operation would no-op on anyway proves nothing.
            ("mark_done", {"done_date": "2026-07-06"}),  # the line is open → would be checked
            ("mark_undone", {}),  # the line is done by then → would be un-checked
            ("inject_vault_id", {"source_line_hash": None}),  # id-less line → would be injected
        ],
    )
    def test_operation_flags_must_be_real_booleans(
        self,
        vault: Path,
        handler: VaultRPCHandler,
        flag: str,
        # boundary: JSON-RPC frame fragment — heterogeneous by protocol (str
        # vault_id, bool flags, str|None dates), and this test deliberately puts
        # a WRONG-typed value in one slot, which a typed shape would forbid.
        extra: dict[str, Any],
    ) -> None:
        """``bool("false")`` is True — a truthy read would pick an operation
        the server never asked for (the inbound twin of the same rule on
        ``updates_applied``). Every flag is compared to ``True``.
        """
        note = vault / "periodic_notes" / "2026-07-06.md"
        if flag == "mark_undone":
            # Put the target line in a done state first, so a coerced
            # ``mark_undone`` would have something to strip.
            handler.handle(
                {
                    "id": 40,
                    "op": "write_task_updates",
                    "params": self._params(
                        vault,
                        [{"vault_id": "sk_x1c9q2", "mark_done": True, "done_date": "2026-07-06"}],
                    ),
                }
            )
            assert note.read_text().startswith("- [x]")

        if flag == "inject_vault_id":
            extra = {"source_line_hash": normalize_vault_line_hash("- [ ] plain task, no id\n")}

        before = note.read_text()
        # boundary: the malformed frame under test — the "false" STRING is the
        # subject of the assertion, so this cannot be a typed update shape.
        update: dict[str, Any] = {"vault_id": "sk_x1c9q2", flag: "false", **extra}
        response = handler.handle(
            {"id": 4, "op": "write_task_updates", "params": self._params(vault, [update])}
        )

        assert response["result"]["updates_applied"] == [False], flag
        assert note.read_text() == before, flag

    def test_write_outside_the_wall_refused(self, vault: Path, handler: VaultRPCHandler) -> None:
        response = handler.handle(
            {
                "id": 44,
                "op": "write_task_updates",
                "params": {
                    "relative_path": "private_journal/secret.md",
                    "expected_sha256": _sha("never leaves the device"),
                    "updates": [{"vault_id": "sk_x1c9q2", "mark_done": True}],
                },
            }
        )
        assert response["ok"] is False
        assert response["error"]["code"] == "path_escapes_wall"

    def test_malformed_updates_are_invalid_params(
        self, vault: Path, handler: VaultRPCHandler
    ) -> None:
        params = self._params(vault, [])
        params["updates"] = [{"mark_done": True}]  # no vault_id
        response = handler.handle({"id": 44, "op": "write_task_updates", "params": params})
        assert response["ok"] is False
        assert response["error"]["code"] == "invalid_params"


# ============================================================================
# FRAME DISPATCH — the loop must survive anything
# ============================================================================


class TestDispatch:
    def test_unknown_op_is_an_error_frame(self, handler: VaultRPCHandler) -> None:
        response = handler.handle({"id": 99, "op": "reboot_universe", "params": {}})
        assert response == {
            "id": 99,
            "ok": False,
            "error": {"code": "unknown_op", "message": "unknown op 'reboot_universe'"},
        }

    def test_handler_exception_becomes_an_error_frame_and_scrubs_the_root(
        self, vault: Path, handler: VaultRPCHandler, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(params: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError(f"disk exploded at {vault / 'periodic_notes'}")

        monkeypatch.setattr(handler, "_read_note", _boom)
        response = handler.handle(
            {"id": 7, "op": "read_note", "params": {"relative_path": "periodic_notes/x.md"}}
        )
        assert response["ok"] is False
        assert response["error"]["code"] == "internal_error"
        assert str(vault) not in json.dumps(response)
        assert "<vault>" in response["error"]["message"]
        # The handler is still alive afterwards:
        assert handler.handle({"id": 8, "op": "describe_wall", "params": {}})["ok"] is True

    def test_non_dict_params_tolerated(self, handler: VaultRPCHandler) -> None:
        response = handler.handle({"id": 5, "op": "describe_wall", "params": "garbage"})
        assert response["ok"] is True


class FakeConnection:
    """Scripted WS peer: async-iterates inbound messages, records sends."""

    def __init__(self, messages: list[str]) -> None:
        self.messages = list(messages)
        self.sent: list[str] = []

    def __aiter__(self) -> FakeConnection:
        return self

    async def __anext__(self) -> str:
        if not self.messages:
            raise StopAsyncIteration
        return self.messages.pop(0)

    async def recv(self) -> str:
        if not self.messages:
            raise ConnectionError("script exhausted")
        return self.messages.pop(0)

    async def send(self, message: str) -> None:
        self.sent.append(message)


class TestServeLoop:
    def test_survives_garbage_and_answers_valid_frames(self, handler: VaultRPCHandler) -> None:
        connection = FakeConnection(
            [
                "{{{not json",
                json.dumps(["a", "list", "frame"]),
                json.dumps({"id": 1, "op": "describe_wall", "params": {}}),
            ]
        )
        asyncio.run(serve_rpcs(connection, handler))
        assert len(connection.sent) == 1  # exactly one response: the valid frame's
        assert json.loads(connection.sent[0])["id"] == 1


# ============================================================================
# CROSS-HALF CONTRACTS — agent signatures must verify server-side
# ============================================================================


class TestChallengeSigningContract:
    def test_agent_signature_verifies_with_the_servers_verifier(self) -> None:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        from core.auth.device_signature import verify_agent_signature

        private_key = Ed25519PrivateKey.generate()
        nonce = "kQ9f2c-test-nonce"
        assert verify_agent_signature(
            public_key_b64url(private_key), nonce, sign_challenge(private_key, nonce)
        )
        # And it is nonce-bound (replay-proof):
        assert not verify_agent_signature(
            public_key_b64url(private_key), "other-nonce", sign_challenge(private_key, nonce)
        )

    def test_duplicated_domain_constant_matches_the_server(self) -> None:
        from core.auth.device_signature import AGENT_SIGNATURE_DOMAIN

        assert agent.AGENT_SIGNATURE_DOMAIN == AGENT_SIGNATURE_DOMAIN

    def test_protocol_version_matches_the_server(self) -> None:
        from adapters.inbound.device_routes import PROTOCOL_VERSION

        assert agent.PROTOCOL_VERSION == PROTOCOL_VERSION

    def test_default_wall_matches_the_ingestion_doorway_folders(self) -> None:
        from core.services.ingestion.config import (
            _DEFAULT_SYNC_SUBDIRS,
            STAGING_EXCLUDED_DIRS,
        )

        assert set(DEFAULT_ALLOWED_FOLDERS) == set(_DEFAULT_SYNC_SUBDIRS)
        assert agent.STAGING_EXCLUDED_DIRS == STAGING_EXCLUDED_DIRS

    def test_backoff_floor_respects_the_server_handshake_rate_limit(self) -> None:
        # 10 handshakes/min/IP server-side → the reconnect floor stays above 6s.
        assert agent.BACKOFF_INITIAL_S > 6.0


class TestHandshake:
    def _run(self, connection: FakeConnection) -> str:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        return asyncio.run(perform_handshake(connection, Ed25519PrivateKey.generate()))

    def test_happy_path_signs_the_nonce_and_returns_user_uid(self) -> None:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        from core.auth.device_signature import verify_agent_signature

        private_key = Ed25519PrivateKey.generate()
        connection = FakeConnection(
            [
                json.dumps(
                    {"type": "challenge", "nonce": "abc123", "protocol": agent.PROTOCOL_VERSION}
                ),
                json.dumps({"type": "session", "ok": True, "user_uid": "user_mike"}),
            ]
        )
        user_uid = asyncio.run(perform_handshake(connection, private_key))
        assert user_uid == "user_mike"

        auth = json.loads(connection.sent[0])
        assert auth["type"] == "auth"
        assert auth["agent_version"] == agent.AGENT_VERSION
        # The frame the agent actually sent verifies with the server's half:
        assert verify_agent_signature(auth["device_pubkey"], "abc123", auth["signature"])

    def test_protocol_mismatch_is_fatal(self) -> None:
        connection = FakeConnection(
            [
                json.dumps(
                    {"type": "challenge", "nonce": "abc123", "protocol": agent.PROTOCOL_VERSION + 1}
                )
            ]
        )
        with pytest.raises(AgentError, match="Protocol mismatch"):
            self._run(connection)

    def test_session_refusal_is_fatal(self) -> None:
        connection = FakeConnection(
            [
                json.dumps(
                    {"type": "challenge", "nonce": "abc123", "protocol": agent.PROTOCOL_VERSION}
                ),
                json.dumps({"type": "session", "ok": False, "error": "device_not_enrolled"}),
            ]
        )
        with pytest.raises(AgentError, match="device_not_enrolled"):
            self._run(connection)

    def test_missing_challenge_is_retryable_not_fatal(self) -> None:
        connection = FakeConnection([json.dumps({"type": "surprise"})])
        with pytest.raises(ConnectionError):
            self._run(connection)


# ============================================================================
# CONFIG + KEY HYGIENE
# ============================================================================


class TestConfigAndKey:
    def test_config_roundtrip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(agent, "CONFIG_DIR", tmp_path / "cfg")
        monkeypatch.setattr(agent, "CONFIG_PATH", tmp_path / "cfg" / "config.toml")
        config = agent.AgentConfig(
            server_url="https://skuel.example",
            vault_root=tmp_path / 'vault "quoted"',
            device_name="mike-laptop",
            allowed_folders=("periodic_notes", "knowledge"),
        )
        agent.save_config(config)
        assert agent.load_config() == config
        mode = (tmp_path / "cfg").stat().st_mode & 0o777
        assert mode == 0o700

    def test_missing_config_is_a_clear_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(agent, "CONFIG_PATH", tmp_path / "nope.toml")
        with pytest.raises(AgentError, match="run `enroll` first"):
            agent.load_config()

    def test_key_generated_at_0600_and_reused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(agent, "CONFIG_DIR", tmp_path / "cfg")
        monkeypatch.setattr(agent, "CONFIG_PATH", tmp_path / "cfg" / "config.toml")
        monkeypatch.setattr(agent, "KEY_PATH", tmp_path / "cfg" / "device.key")
        first = agent.generate_or_load_private_key()
        mode = (tmp_path / "cfg" / "device.key").stat().st_mode & 0o777
        assert mode == 0o600
        second = agent.generate_or_load_private_key()  # reuse, not regenerate
        assert public_key_b64url(first) == public_key_b64url(second)

    def test_world_readable_key_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        key_path = tmp_path / "device.key"
        key_path.write_bytes(b"whatever")
        key_path.chmod(0o644)
        monkeypatch.setattr(agent, "KEY_PATH", key_path)
        with pytest.raises(AgentError, match="too open"):
            agent.load_private_key()


class TestWsUrl:
    def test_https_becomes_wss(self) -> None:
        assert agent.derive_ws_url("https://skuel.example") == "wss://skuel.example/ws/agent"

    def test_http_becomes_ws(self) -> None:
        assert agent.derive_ws_url("http://localhost:8000") == "ws://localhost:8000/ws/agent"

    def test_path_prefix_is_preserved(self) -> None:
        # Reverse-proxy subpath deployments must reconnect to the same prefix.
        assert (
            agent.derive_ws_url("https://host.example/skuel/")
            == "wss://host.example/skuel/ws/agent"
        )


class TestServerScheme:
    def test_https_accepted(self) -> None:
        agent.check_server_scheme("https://skuel.example")

    @pytest.mark.parametrize("url", ["http://localhost:8000", "http://127.0.0.1:8000"])
    def test_http_localhost_accepted(self, url: str) -> None:
        agent.check_server_scheme(url)

    def test_http_off_localhost_refused(self) -> None:
        # The pairing code and vault RPCs must never cross the network
        # unencrypted — TLS is half the channel security (ADR-075 Decision 1).
        with pytest.raises(AgentError, match="non-HTTPS"):
            agent.check_server_scheme("http://skuel.example")
