"""
Local-agent vault transport, end to end in-process — ADR-075 B4.

The sub-arc's proof: the REAL agent RPC handler (``VaultRPCHandler`` from
``agent/skuel_vault_agent.py``, serving a real tmp source vault with the real
agent-side wall) is bridged to the REAL ``AgentChannelRegistry`` /
``AgentSession`` RPC machinery without sockets, and the REAL
``LocalAgentVaultAdapter`` + ``VaultMirrorPuller`` + ``VaultReconciler`` drive
a full sync against it. Only ingestion + user services are mocked.

Covers:
(a) sync pulls changed/new files into the server-side mirror and hands the
    EXISTING reconciler flow a correct mirror (ingest runs on the mirror root);
(b) a file deleted agent-side vanishes from the mirror — the existing deletion
    reconciliation's input;
(c) ``write_task_updates`` round-trips a 🆔 injection back into the AGENT-side
    source vault through the full reconciler outbound path;
(d) no connected agent → sync fails with the clear integration error and the
    mirror is untouched;
(e) walled/staging content never lands in the mirror (agent-side wall +
    server-side sweep scope);
plus VAULT_TRANSPORT validation and the adapter's path/frame edge cases.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from adapters.inbound.agent_channel_registry import AgentChannelRegistry, AgentSession
from adapters.vault.local_agent_adapter import AGENT_NOT_CONNECTED, LocalAgentVaultAdapter
from agent.skuel_vault_agent import VaultRPCHandler
from core.config.unified_config import VaultConfig
from core.models.type_hints import UserUID
from core.ports.vault_bridge_protocol import TaskLineUpdate, normalize_vault_line_hash
from core.services.ingestion.config import build_sync_allowlist
from core.services.ingestion.types import IngestionStats
from core.services.vault.mirror_sync import VaultMirrorPuller
from core.services.vault.vault_descriptor import VaultDescriptor, VaultKind, VaultRegistry
from core.services.vault.vault_reconciler import VaultReconciler
from core.utils.result_simplified import ErrorCategory, Result

OWNER = UserUID("user_owner")

TASK_LINE = "- [ ] water the plants\n"
NOTE_PATH = "periodic_notes/2026-07-06.md"


# ---------------------------------------------------------------------------
# In-process bridge: real agent handler ↔ real AgentSession, no sockets
# ---------------------------------------------------------------------------


class InProcessAgentWebSocket:
    """A 'WebSocket' whose far end IS the real agent RPC handler.

    ``AgentSession.call`` awaits a response future; the real agent would
    answer over the wire — here every request frame sent through
    ``send_json`` is dispatched to ``VaultRPCHandler.handle`` and the
    response frame fed straight back via ``session.resolve``, exactly what
    the WS receive loop does in production.
    """

    def __init__(self, handler: VaultRPCHandler) -> None:
        # Swappable so tests can wrap the real handler (e.g. torn-read races).
        self.handle_frame: Callable[[dict[str, Any]], dict[str, Any]] = handler.handle
        self.session: AgentSession | None = None
        self.closed: tuple[int, str | None] | None = None
        self.frames: list[dict[str, Any]] = []

    async def send_json(self, data: dict[str, Any]) -> None:
        # Round-trip through JSON: the frames must be wire-serializable.
        frame = json.loads(json.dumps(data))
        self.frames.append(frame)
        assert self.session is not None
        self.session.resolve(self.handle_frame(frame))

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed = (code, reason)


@dataclass
class AgentHarness:
    """One connected agent: source vault + registry + adapter-side plumbing."""

    source_vault: Path
    registry: AgentChannelRegistry
    session: AgentSession
    websocket: InProcessAgentWebSocket

    def disconnect(self) -> None:
        self.registry.unregister(self.session)


def _connect_agent(
    source_vault: Path,
    registry: AgentChannelRegistry,
    allowed_folders: tuple[str, ...] = ("periodic_notes", "knowledge"),
) -> AgentHarness:
    handler = VaultRPCHandler(source_vault, allowed_folders)
    websocket = InProcessAgentWebSocket(handler)
    session = AgentSession(websocket, user_uid=str(OWNER), device_uid="device_ab12cd34")  # type: ignore[arg-type]
    websocket.session = session
    registry.register(session)
    return AgentHarness(
        source_vault=source_vault, registry=registry, session=session, websocket=websocket
    )


# ---------------------------------------------------------------------------
# Fixtures: agent-side vault, server-side mirror descriptor, reconciler
# ---------------------------------------------------------------------------


@pytest.fixture
def source_vault(tmp_path: Path) -> Path:
    """The vault on the 'user's machine': allowed content + walled siblings."""
    vault = tmp_path / "device_vault"
    (vault / "periodic_notes").mkdir(parents=True)
    (vault / "knowledge").mkdir()
    (vault / "private_journal").mkdir()  # outside the agent's wall
    (vault / "periodic_notes" / "je_out").mkdir()  # staging floor

    (vault / NOTE_PATH).write_text(TASK_LINE)
    (vault / "knowledge" / "spaced-repetition.md").write_text("# Spaced repetition\n")
    (vault / "private_journal" / "secret.md").write_text("never leaves the device\n")
    (vault / "periodic_notes" / "je_out" / "transcript.md").write_text("staged artifact\n")
    return vault


@pytest.fixture
def mirror_root(tmp_path: Path) -> Path:
    """The server-side member-vault path = the staging mirror (#521 layout)."""
    mirror = tmp_path / "user_vaults" / str(OWNER)
    mirror.mkdir(parents=True)
    return mirror


@dataclass
class TransportRig:
    """Everything a scenario needs, wired the way compose wires it."""

    registry: AgentChannelRegistry
    descriptor: VaultDescriptor
    reconciler: VaultReconciler
    ingestion: SimpleNamespace
    user_entry: SimpleNamespace
    tasks: SimpleNamespace


def _local_agent_descriptor(mirror_root: Path, registry: AgentChannelRegistry) -> VaultDescriptor:
    """Mirror compose.py's local_agent branch of _build_personal_descriptor."""
    allowlist = build_sync_allowlist(mirror_root)
    bridge = LocalAgentVaultAdapter(registry=registry, mirror_root=mirror_root)
    resolved = mirror_root.resolve()
    allowed_folders = frozenset(
        d.relative_to(resolved).parts[0]
        for d in allowlist.allowed_dirs
        if d != resolved and d.is_relative_to(resolved)
    )
    return VaultDescriptor(
        kind=VaultKind.PERSONAL,
        root=mirror_root,
        owner_uid=OWNER,
        allowlist=allowlist,
        bridge=bridge,
        supports_task_round_trip=True,
        mirror_pull=VaultMirrorPuller(
            transport=bridge, mirror_root=mirror_root, allowed_folders=allowed_folders
        ),
    )


@pytest.fixture
def rig(mirror_root: Path) -> TransportRig:
    registry = AgentChannelRegistry()
    descriptor = _local_agent_descriptor(mirror_root, registry)

    ingestion = SimpleNamespace(
        ingest_directory=AsyncMock(return_value=Result.ok(IngestionStats(successful=1))),
        ingestion_backend=None,
    )
    user_entry = SimpleNamespace(
        list_for_user=AsyncMock(return_value=Result.ok([])),
        get_extracted_entities=AsyncMock(return_value=Result.ok([])),
        update_extracted_vault_id=AsyncMock(return_value=Result.ok(None)),
        update_entry=AsyncMock(return_value=Result.ok(None)),
    )
    tasks = SimpleNamespace(get_task=AsyncMock(return_value=Result.ok(None)))
    consented_user = SimpleNamespace(preferences=SimpleNamespace(vault_write_consent=True))
    user_service = SimpleNamespace(get_user=AsyncMock(return_value=Result.ok(consented_user)))

    reconciler = VaultReconciler(
        registry=VaultRegistry(content=None, personal=descriptor),
        unified_ingestion=ingestion,  # type: ignore[arg-type]
        user_entry_service=user_entry,  # type: ignore[arg-type]
        tasks_service=tasks,  # type: ignore[arg-type]
        user_service=user_service,  # type: ignore[arg-type]
    )
    return TransportRig(
        registry=registry,
        descriptor=descriptor,
        reconciler=reconciler,
        ingestion=ingestion,
        user_entry=user_entry,
        tasks=tasks,
    )


# ---------------------------------------------------------------------------
# (a) inbound: sync pulls the agent's files into the mirror, then ingests it
# ---------------------------------------------------------------------------


class TestMirrorPullInbound:
    @pytest.mark.asyncio
    async def test_sync_pulls_agent_files_into_mirror_and_ingests_the_mirror(
        self, rig: TransportRig, source_vault: Path, mirror_root: Path
    ) -> None:
        _connect_agent(source_vault, rig.registry)

        result = await rig.reconciler.sync(VaultKind.PERSONAL, OWNER)

        assert result.is_ok, result
        # The mirror is now faithful to the agent's allowed subtree.
        assert (mirror_root / NOTE_PATH).read_text() == TASK_LINE
        assert (mirror_root / "knowledge" / "spaced-repetition.md").is_file()
        # The EXISTING engine ran on the mirror root, smart mode, owner-scoped.
        rig.ingestion.ingest_directory.assert_awaited_once()
        call = rig.ingestion.ingest_directory.await_args
        assert call.args[0] == mirror_root
        assert call.kwargs["ingestion_mode"] == "smart"
        assert call.kwargs["user_uid"] == OWNER

    @pytest.mark.asyncio
    async def test_second_sync_skips_unchanged_and_fetches_changed(
        self, rig: TransportRig, source_vault: Path, mirror_root: Path
    ) -> None:
        harness = _connect_agent(source_vault, rig.registry)
        assert (await rig.reconciler.sync(VaultKind.PERSONAL, OWNER)).is_ok

        # Change one file on the 'device'; leave the other untouched.
        (source_vault / NOTE_PATH).write_text(TASK_LINE + "- [ ] new line\n")
        read_ops_before = [f for f in harness.websocket.frames if f.get("op") == "read_note"]

        assert (await rig.reconciler.sync(VaultKind.PERSONAL, OWNER)).is_ok

        read_ops = [f for f in harness.websocket.frames if f.get("op") == "read_note"]
        fetched = [f["params"]["relative_path"] for f in read_ops[len(read_ops_before) :]]
        assert fetched == [NOTE_PATH]  # bandwidth layer: only the changed file crossed
        assert (mirror_root / NOTE_PATH).read_text().endswith("- [ ] new line\n")

    # -----------------------------------------------------------------
    # (b) deletion: absent from the agent's listing → gone from the mirror
    # -----------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_agent_side_deletion_vanishes_from_mirror(
        self, rig: TransportRig, source_vault: Path, mirror_root: Path
    ) -> None:
        _connect_agent(source_vault, rig.registry)
        assert (await rig.reconciler.sync(VaultKind.PERSONAL, OWNER)).is_ok
        assert (mirror_root / NOTE_PATH).is_file()

        (source_vault / NOTE_PATH).unlink()
        assert (await rig.reconciler.sync(VaultKind.PERSONAL, OWNER)).is_ok

        # The mirror file is gone — exactly what the existing deletion
        # reconciliation (tracked row, file missing) keys on downstream.
        assert not (mirror_root / NOTE_PATH).exists()
        assert (mirror_root / "knowledge" / "spaced-repetition.md").is_file()

    # -----------------------------------------------------------------
    # (d) no agent → clear integration failure, mirror untouched
    # -----------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_agent_not_connected_fails_clearly_and_leaves_mirror_alone(
        self, rig: TransportRig, mirror_root: Path
    ) -> None:
        stale = mirror_root / "periodic_notes"
        stale.mkdir()
        (stale / "already-mirrored.md").write_text("previous sync\n")

        result = await rig.reconciler.sync(VaultKind.PERSONAL, OWNER)

        assert result.is_error
        error = result.expect_error()
        assert error.category is ErrorCategory.INTEGRATION
        assert AGENT_NOT_CONNECTED in error.message
        # Mirror untouched: no deletion sweep ran against a missing agent.
        assert (stale / "already-mirrored.md").is_file()
        rig.ingestion.ingest_directory.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disconnected_agent_fails_like_never_connected(
        self, rig: TransportRig, source_vault: Path
    ) -> None:
        harness = _connect_agent(source_vault, rig.registry)
        harness.disconnect()

        result = await rig.reconciler.sync(VaultKind.PERSONAL, OWNER)

        assert result.is_error
        assert AGENT_NOT_CONNECTED in result.expect_error().message

    # -----------------------------------------------------------------
    # (e) the wall: walled + staging content never lands in the mirror
    # -----------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_walled_and_staging_content_never_lands_in_the_mirror(
        self, rig: TransportRig, source_vault: Path, mirror_root: Path
    ) -> None:
        _connect_agent(source_vault, rig.registry)

        assert (await rig.reconciler.sync(VaultKind.PERSONAL, OWNER)).is_ok

        mirrored = sorted(p.relative_to(mirror_root).as_posix() for p in mirror_root.rglob("*.md"))
        assert mirrored == ["knowledge/spaced-repetition.md", NOTE_PATH]
        assert not (mirror_root / "private_journal").exists()  # agent-side wall
        assert not (mirror_root / "periodic_notes" / "je_out").exists()  # je_* floor

    @pytest.mark.asyncio
    async def test_agent_folder_outside_server_wall_is_refused_with_warning(
        self, rig: TransportRig, source_vault: Path, mirror_root: Path
    ) -> None:
        """Decision 5 defense in depth: a widened AGENT wall cannot widen the
        effective wall alone — the server-side folder scope still applies."""
        (source_vault / "everything").mkdir()
        (source_vault / "everything" / "leak.md").write_text("outside the doorway set\n")
        _connect_agent(source_vault, rig.registry, allowed_folders=("periodic_notes", "everything"))

        result = await rig.reconciler.sync(VaultKind.PERSONAL, OWNER)

        assert result.is_ok
        assert not (mirror_root / "everything").exists()
        assert any("everything/leak.md" in w for w in result.value.warnings)

    @pytest.mark.asyncio
    async def test_agent_hidden_folder_is_binding_and_retracts(
        self, rig: TransportRig, source_vault: Path, mirror_root: Path
    ) -> None:
        """Kody #531: describe_wall is BINDING, not decorative. A lying agent
        whose wall reports fewer folders than its listing ships must not have
        the hidden folder mirrored (populate scope = agent ∩ server), and a
        previously-mirrored file in the newly-hidden folder is swept —
        retroactive retraction, same as the server wall."""
        harness = _connect_agent(source_vault, rig.registry)
        # Pre-seed the mirror as if 'knowledge' had synced before the agent
        # narrowed its wall.
        (mirror_root / "knowledge").mkdir()
        stale = mirror_root / "knowledge" / "spaced-repetition.md"
        stale.write_text("# Spaced repetition\n")

        real = harness.websocket.handle_frame

        def lying(frame: dict[str, Any]) -> dict[str, Any]:
            response = real(frame)
            if frame.get("op") == "describe_wall" and response.get("ok"):
                response["result"]["allowed_folders"] = ["periodic_notes"]
            return response

        harness.websocket.handle_frame = lying

        result = await rig.reconciler.sync(VaultKind.PERSONAL, OWNER)

        assert result.is_ok
        # The listing still shipped knowledge rows — refused, not mirrored…
        assert any("knowledge/spaced-repetition.md" in w for w in result.value.warnings)
        # …and the previously-mirrored copy retracted via the wider sweep.
        assert not stale.exists()
        assert (mirror_root / NOTE_PATH).exists()  # the honest folder still syncs


# ---------------------------------------------------------------------------
# (c) outbound: 🆔 injection round-trips into the AGENT-side source vault
# ---------------------------------------------------------------------------


class TestOutboundRoundTrip:
    @pytest.mark.asyncio
    async def test_id_injection_round_trips_to_the_device_vault(
        self, rig: TransportRig, source_vault: Path, mirror_root: Path
    ) -> None:
        _connect_agent(source_vault, rig.registry)

        entry = SimpleNamespace(
            uid="ue_test0001",
            metadata={"vault_file_path": str(mirror_root / NOTE_PATH)},
        )
        pages = [Result.ok([entry]), Result.ok([])]
        rig.user_entry.list_for_user = AsyncMock(side_effect=pages)
        rig.user_entry.get_extracted_entities = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "entity_uid": "task_water_plants",
                        "vault_id": None,
                        "source_line_hash": normalize_vault_line_hash(TASK_LINE),
                    }
                ]
            )
        )

        result = await rig.reconciler.sync(VaultKind.PERSONAL, OWNER)

        assert result.is_ok, result
        stats = result.value
        assert stats.ids_injected == 1
        # The 🆔 landed in the DEVICE-side file, applied by the real agent
        # handler with the shared line mutations.
        device_line = (source_vault / NOTE_PATH).read_text()
        assert "water the plants" in device_line
        assert "🆔 sk_" in device_line
        # And Neo4j got told the new vault_id for the EXTRACTED_FROM edge.
        rig.user_entry.update_extracted_vault_id.assert_awaited_once()
        injected_id = rig.user_entry.update_extracted_vault_id.await_args.args[2]
        assert injected_id in device_line

    @pytest.mark.asyncio
    async def test_mark_done_round_trips_to_the_device_vault(
        self, rig: TransportRig, source_vault: Path, mirror_root: Path
    ) -> None:
        from datetime import date, datetime

        from core.models.enums.entity_enums import EntityStatus

        (source_vault / NOTE_PATH).write_text("- [ ] water the plants 🆔 sk_ab12cd\n")
        _connect_agent(source_vault, rig.registry)

        entry = SimpleNamespace(
            uid="ue_test0002",
            metadata={"vault_file_path": str(mirror_root / NOTE_PATH)},
        )
        rig.user_entry.list_for_user = AsyncMock(side_effect=[Result.ok([entry]), Result.ok([])])
        rig.user_entry.get_extracted_entities = AsyncMock(
            return_value=Result.ok([{"entity_uid": "task_water_plants", "vault_id": "sk_ab12cd"}])
        )
        # Mirrors a real completed task: the ✅ date comes from the completion
        # stamp, and updated_at is deliberately later so a regression to the old
        # mutable-proxy reader would write 2026-08-20 and fail below.
        rig.tasks.get_task = AsyncMock(
            return_value=Result.ok(
                SimpleNamespace(
                    status=EntityStatus.COMPLETED,
                    completion_date=date(2026, 7, 6),
                    updated_at=datetime(2026, 8, 20, 12, 0),
                )
            )
        )

        result = await rig.reconciler.sync(VaultKind.PERSONAL, OWNER)

        assert result.is_ok, result
        assert result.value.tasks_marked_done == 1
        device_line = (source_vault / NOTE_PATH).read_text()
        assert device_line.startswith("- [x]")
        assert "✅ 2026-07-06" in device_line


# ---------------------------------------------------------------------------
# Adapter edges: path translation, torn reads, malformed frames
# ---------------------------------------------------------------------------


class TestAdapterEdges:
    @pytest.mark.asyncio
    async def test_read_note_translates_mirror_absolute_paths(
        self, source_vault: Path, mirror_root: Path
    ) -> None:
        registry = AgentChannelRegistry()
        _connect_agent(source_vault, registry)
        adapter = LocalAgentVaultAdapter(registry=registry, mirror_root=mirror_root)

        snapshot = await adapter.read_note(str(OWNER), str(mirror_root / NOTE_PATH))

        assert snapshot.content == TASK_LINE
        assert snapshot.path == NOTE_PATH  # vault-relative, never mirror-absolute

    @pytest.mark.asyncio
    async def test_path_escaping_the_mirror_root_is_refused(
        self, source_vault: Path, mirror_root: Path
    ) -> None:
        registry = AgentChannelRegistry()
        _connect_agent(source_vault, registry)
        adapter = LocalAgentVaultAdapter(registry=registry, mirror_root=mirror_root)

        with pytest.raises(ValueError, match="escapes"):
            await adapter.read_note(str(OWNER), "../outside.md")

    @pytest.mark.asyncio
    async def test_write_task_updates_without_agent_reports_not_connected(
        self, mirror_root: Path
    ) -> None:
        adapter = LocalAgentVaultAdapter(registry=AgentChannelRegistry(), mirror_root=mirror_root)

        write = await adapter.write_task_updates(
            user_uid=str(OWNER),
            path=str(mirror_root / NOTE_PATH),
            updates=[TaskLineUpdate(vault_id="sk_ab12cd", mark_done=True, done_date="2026-07-06")],
            expected_sha256="0" * 64,
        )

        assert write.success is False
        assert write.error is not None and AGENT_NOT_CONNECTED in write.error

    @pytest.mark.asyncio
    async def test_stale_sha_refusal_travels_back_as_write_failure(
        self, source_vault: Path, mirror_root: Path
    ) -> None:
        registry = AgentChannelRegistry()
        _connect_agent(source_vault, registry)
        adapter = LocalAgentVaultAdapter(registry=registry, mirror_root=mirror_root)

        write = await adapter.write_task_updates(
            user_uid=str(OWNER),
            path=NOTE_PATH,
            updates=[TaskLineUpdate(vault_id="sk_ab12cd", mark_done=True, done_date="2026-07-06")],
            expected_sha256="0" * 64,  # deliberately stale
        )

        assert write.success is False
        assert write.error is not None and "Stale-read guard" in write.error

    @pytest.mark.asyncio
    async def test_torn_read_is_skipped_with_warning_not_mirrored(
        self, source_vault: Path, mirror_root: Path
    ) -> None:
        """A file that changes between listing and fetch must not land in the
        mirror with a hash the listing never vouched for."""
        registry = AgentChannelRegistry()
        harness = _connect_agent(source_vault, registry)

        real_handle = harness.websocket.handle_frame

        def tearing_handle(frame: dict[str, Any]) -> dict[str, Any]:
            if frame.get("op") == "read_note":
                # Mutate the device file AFTER the listing, BEFORE the read.
                (source_vault / NOTE_PATH).write_text("changed mid-sync\n")
            return real_handle(frame)

        harness.websocket.handle_frame = tearing_handle

        puller = VaultMirrorPuller(
            transport=LocalAgentVaultAdapter(registry=registry, mirror_root=mirror_root),
            mirror_root=mirror_root,
            allowed_folders=frozenset({"periodic_notes", "knowledge"}),
        )
        result = await puller.refresh(str(OWNER))

        assert result.is_ok
        assert not (mirror_root / NOTE_PATH).exists()
        assert any("changed mid-sync" in w or NOTE_PATH in w for w in result.value.warnings)

    @pytest.mark.asyncio
    async def test_per_update_outcomes_cross_the_wire(
        self, source_vault: Path, mirror_root: Path
    ) -> None:
        """Protocol v2: the agent's per-update ``changed`` reaches the server.

        A batch whose first update matches no line and whose second lands is a
        file-level success either way — ``updates_applied`` is the only thing
        that tells the reconciler which 🆔 it may persist (deferred-work
        § Phantom-🆔). Real agent handler, real frames.
        """
        (source_vault / NOTE_PATH).write_text(TASK_LINE)
        registry = AgentChannelRegistry()
        _connect_agent(source_vault, registry)
        adapter = LocalAgentVaultAdapter(registry=registry, mirror_root=mirror_root)
        snapshot = await adapter.read_note(str(OWNER), NOTE_PATH)

        write = await adapter.write_task_updates(
            user_uid=str(OWNER),
            path=NOTE_PATH,
            updates=[
                TaskLineUpdate(
                    vault_id="sk_miss11",
                    inject_vault_id=True,
                    source_line_hash=normalize_vault_line_hash("- [ ] not in this file\n"),
                ),
                TaskLineUpdate(
                    vault_id="sk_hit222",
                    inject_vault_id=True,
                    source_line_hash=normalize_vault_line_hash(TASK_LINE),
                ),
            ],
            expected_sha256=snapshot.sha256,
        )

        assert write.success is True
        assert write.updates_applied == (False, True)
        device_line = (source_vault / NOTE_PATH).read_text()
        assert "🆔 sk_hit222" in device_line and "sk_miss11" not in device_line

    @pytest.mark.asyncio
    async def test_an_empty_batch_is_guard_only_on_the_wire(
        self, source_vault: Path, mirror_root: Path
    ) -> None:
        """The agent answers an empty batch with the guard and no mutation.

        The reconciler uses that as "re-validate the snapshot" when a pass has
        nothing to write but a recovery 🆔 to persist.
        """
        registry = AgentChannelRegistry()
        _connect_agent(source_vault, registry)
        adapter = LocalAgentVaultAdapter(registry=registry, mirror_root=mirror_root)
        snapshot = await adapter.read_note(str(OWNER), NOTE_PATH)

        ok = await adapter.write_task_updates(
            user_uid=str(OWNER), path=NOTE_PATH, updates=[], expected_sha256=snapshot.sha256
        )
        assert ok.success is True and ok.new_sha256 == snapshot.sha256

        (source_vault / NOTE_PATH).write_text("- [ ] edited by the user\n")
        stale = await adapter.write_task_updates(
            user_uid=str(OWNER), path=NOTE_PATH, updates=[], expected_sha256=snapshot.sha256
        )
        assert stale.success is False
        assert "Stale-read guard" in str(stale.error)
        assert (source_vault / NOTE_PATH).read_text() == "- [ ] edited by the user\n"

    @pytest.mark.asyncio
    async def test_a_frame_without_outcomes_reads_fail_closed(
        self, source_vault: Path, mirror_root: Path
    ) -> None:
        """A reply that drops ``updates_applied`` must not read as "it landed"."""
        registry = AgentChannelRegistry()
        harness = _connect_agent(source_vault, registry)
        adapter = LocalAgentVaultAdapter(registry=registry, mirror_root=mirror_root)
        snapshot = await adapter.read_note(str(OWNER), NOTE_PATH)

        real_handle = harness.websocket.handle_frame

        def stripping_handle(frame: dict[str, Any]) -> dict[str, Any]:
            response = real_handle(frame)
            if frame.get("op") == "write_task_updates" and response.get("ok"):
                response["result"].pop("updates_applied", None)
            return response

        harness.websocket.handle_frame = stripping_handle

        write = await adapter.write_task_updates(
            user_uid=str(OWNER),
            path=NOTE_PATH,
            updates=[
                TaskLineUpdate(
                    vault_id="sk_hit222",
                    inject_vault_id=True,
                    source_line_hash=normalize_vault_line_hash(TASK_LINE),
                )
            ],
            expected_sha256=snapshot.sha256,
        )

        assert write.success is True  # the file-level answer is unchanged…
        assert write.updates_applied == ()  # …and nothing is asserted per update
        assert write.was_applied(0) is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "malformed",
        [
            pytest.param(["false"], id="truthy-string-false"),
            pytest.param([1], id="json-number"),
            pytest.param([True, "true"], id="partially-typed"),
            pytest.param("true", id="not-a-list"),
        ],
    )
    async def test_a_non_boolean_outcome_is_never_read_as_confirmation(
        self, source_vault: Path, mirror_root: Path, malformed: Any
    ) -> None:
        """``bool("false")`` is True — coercion would forge the confirmation.

        A malformed frame must not be able to re-create the phantom-🆔 these
        outcomes exist to report away, so only a real JSON boolean counts and a
        partially-typed list is discarded whole (its positions are not
        trustworthy either).
        """
        registry = AgentChannelRegistry()
        harness = _connect_agent(source_vault, registry)
        adapter = LocalAgentVaultAdapter(registry=registry, mirror_root=mirror_root)
        snapshot = await adapter.read_note(str(OWNER), NOTE_PATH)

        real_handle = harness.websocket.handle_frame

        def lying_handle(frame: dict[str, Any]) -> dict[str, Any]:
            response = real_handle(frame)
            if frame.get("op") == "write_task_updates" and response.get("ok"):
                response["result"]["updates_applied"] = malformed
            return response

        harness.websocket.handle_frame = lying_handle

        write = await adapter.write_task_updates(
            user_uid=str(OWNER),
            path=NOTE_PATH,
            updates=[
                TaskLineUpdate(
                    vault_id="sk_hit222",
                    inject_vault_id=True,
                    source_line_hash=normalize_vault_line_hash(TASK_LINE),
                )
            ],
            expected_sha256=snapshot.sha256,
        )

        assert write.updates_applied == ()
        assert write.was_applied(0) is False

    @pytest.mark.asyncio
    async def test_a_non_boolean_success_is_never_read_as_success(
        self, source_vault: Path, mirror_root: Path
    ) -> None:
        """The other half of the same frame: truthy is not the same as True."""
        registry = AgentChannelRegistry()
        harness = _connect_agent(source_vault, registry)
        adapter = LocalAgentVaultAdapter(registry=registry, mirror_root=mirror_root)
        snapshot = await adapter.read_note(str(OWNER), NOTE_PATH)

        real_handle = harness.websocket.handle_frame

        def lying_handle(frame: dict[str, Any]) -> dict[str, Any]:
            response = real_handle(frame)
            if frame.get("op") == "write_task_updates" and response.get("ok"):
                response["result"]["success"] = "false"
            return response

        harness.websocket.handle_frame = lying_handle

        write = await adapter.write_task_updates(
            user_uid=str(OWNER),
            path=NOTE_PATH,
            updates=[
                TaskLineUpdate(
                    vault_id="sk_hit222",
                    inject_vault_id=True,
                    source_line_hash=normalize_vault_line_hash(TASK_LINE),
                )
            ],
            expected_sha256=snapshot.sha256,
        )

        assert write.success is False

    @pytest.mark.asyncio
    async def test_list_vault_notes_returns_vault_relative_paths(
        self, source_vault: Path, mirror_root: Path
    ) -> None:
        registry = AgentChannelRegistry()
        _connect_agent(source_vault, registry)
        adapter = LocalAgentVaultAdapter(registry=registry, mirror_root=mirror_root)

        notes = await adapter.list_vault_notes(str(OWNER), "", "**/*.md")

        assert notes == ["knowledge/spaced-repetition.md", NOTE_PATH]

    @pytest.mark.asyncio
    async def test_malicious_listing_row_escaping_upward_is_never_written(
        self, mirror_root: Path, tmp_path: Path
    ) -> None:
        """A hostile/buggy agent listing a ``../`` path must not write outside
        the mirror — the row is refused with a warning (fail closed)."""

        class EvilTransport:
            async def describe_wall(self, user_uid: str) -> Result[Any]:
                from core.ports.vault_bridge_protocol import AgentWall

                return Result.ok(AgentWall(allowed_folders=("periodic_notes",), agent_version="0"))

            async def list_changed_since(
                self, user_uid: str, since_state: str | None = None
            ) -> Result[Any]:
                from core.ports.vault_bridge_protocol import VaultFileStat, VaultListing

                return Result.ok(
                    VaultListing(
                        files=(VaultFileStat(relative_path="../escaped.md", sha256="f" * 64),),
                        state="st_evil",
                    )
                )

            async def read_note(self, user_uid: str, path: str) -> Any:
                raise AssertionError("a refused row must never be fetched")

        puller = VaultMirrorPuller(
            transport=EvilTransport(),  # type: ignore[arg-type]
            mirror_root=mirror_root,
            allowed_folders=frozenset({"periodic_notes"}),
        )
        result = await puller.refresh(str(OWNER))

        assert result.is_ok
        assert not (tmp_path / "user_vaults" / "escaped.md").exists()
        assert any("escaped.md" in w for w in result.value.warnings)


# ---------------------------------------------------------------------------
# VAULT_TRANSPORT validation (ADR-075 Decision 6)
# ---------------------------------------------------------------------------


class TestVaultTransportConfig:
    def test_default_is_filesystem(self) -> None:
        assert VaultConfig().validated_transport() in ("filesystem", "local_agent")
        assert VaultConfig(vault_transport="filesystem").validated_transport() == "filesystem"

    def test_local_agent_is_valid(self) -> None:
        assert VaultConfig(vault_transport="local_agent").validated_transport() == "local_agent"

    def test_unknown_transport_fails_fast(self) -> None:
        with pytest.raises(ValueError, match="VAULT_TRANSPORT"):
            VaultConfig(vault_transport="carrier_pigeon").validated_transport()

    def test_local_agent_refuses_overlapping_mirror_roots(self, tmp_path: Path) -> None:
        # Kody #531: the mirror's deletion sweep treats its root as a
        # pull-managed cache — a combined/nested content layout would let a
        # personal sync delete curriculum files. Both directions, both roots.
        combined = VaultConfig(
            vault_transport="local_agent",
            vault_root=str(tmp_path / "vault"),
            ingestion_root=str(tmp_path / "vault"),  # coincident
            user_vaults_root=str(tmp_path / "user_vaults"),
        )
        with pytest.raises(ValueError, match="overlap"):
            combined.validated_transport()

        nested_content = VaultConfig(
            vault_transport="local_agent",
            vault_root=str(tmp_path / "vault"),
            ingestion_root=str(tmp_path / "vault" / "curriculum"),  # content inside personal
            user_vaults_root=str(tmp_path / "user_vaults"),
        )
        with pytest.raises(ValueError, match="overlap"):
            nested_content.validated_transport()

        members_inside_content = VaultConfig(
            vault_transport="local_agent",
            vault_root=str(tmp_path / "vault"),
            ingestion_root=str(tmp_path / "content"),
            user_vaults_root=str(tmp_path / "content" / "user_vaults"),
        )
        with pytest.raises(ValueError, match="overlap"):
            members_inside_content.validated_transport()

        disjoint = VaultConfig(
            vault_transport="local_agent",
            vault_root=str(tmp_path / "vault"),
            ingestion_root=str(tmp_path / "content"),
            user_vaults_root=str(tmp_path / "user_vaults"),
        )
        assert disjoint.validated_transport() == "local_agent"

        # Filesystem transport never runs the mirror sweep — combined roots
        # stay legal there (Stage 1 unchanged).
        stage1_combined = VaultConfig(
            vault_transport="filesystem",
            vault_root=str(tmp_path / "vault"),
            ingestion_root=str(tmp_path / "vault"),
        )
        assert stage1_combined.validated_transport() == "filesystem"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
