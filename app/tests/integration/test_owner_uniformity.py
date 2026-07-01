"""Owner uniformity — the same content-vault file gets the same owner everywhere.

The whole point of resolving ingest ownership from the vault descriptor of the
target path (ADR-070) is *surface-independence*: whoever triggers the ingest, a
USER_OWNED entity that lives in the content vault is owned by the content acts-as
account, and a curriculum entity is owned by no one. These tests drive one
registry-wired ingestion service through three surfaces and assert the graph
agrees.

Requires: Docker running with Neo4j testcontainer.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.ingestion_backend import IngestionBackend
from adapters.persistence.neo4j.ingestion_service_factory import make_unified_ingestion_service
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.type_hints import UserUID
from core.ports.vault_bridge_protocol import VaultBridgePort
from core.services.ingestion.config import build_sync_allowlist
from core.services.vault.vault_descriptor import (
    VaultDescriptor,
    VaultKind,
    VaultRegistry,
)
from core.services.vault.vault_reconciler import VaultReconciler

pytestmark = pytest.mark.asyncio

_CONTENT_OWNER = UserUID("user_content_admin")
_ALICE = UserUID("user_alice_owner")
_ALL_USERS = (_CONTENT_OWNER, _ALICE, "user_alpha", "user_beta", "user_gamma")


def _bridge() -> VaultBridgePort:
    from typing import cast

    return cast("VaultBridgePort", object())


def _task_file(path: Path, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntype: task\ntitle: {title}\n---\n\nBody for {title}.\n")


def _ku_file(path: Path, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntype: ku\ntitle: {title}\nnamespace: test\n---\n\nAtomic fact.\n")


@pytest_asyncio.fixture
async def owner_env(neo4j_driver, tmp_path: Path):
    """Registry-wired ingestion service + reconciler over two temp vaults."""
    content_root = tmp_path / "content"
    personal_root = tmp_path / "personal"
    content_root.mkdir()
    personal_root.mkdir()

    # Ensure the acting/owning User nodes exist so OWNS edges resolve cleanly.
    async with neo4j_driver.session() as session:
        for uid in _ALL_USERS:
            await session.run("MERGE (u:User {uid: $uid}) ON CREATE SET u.title = $uid", uid=uid)

    executor = Neo4jQueryExecutor(neo4j_driver)
    service = make_unified_ingestion_service(
        driver=neo4j_driver,
        default_user_uid=UserUID("user_default"),
        ingestion_backend=IngestionBackend(executor=executor),
    )

    content_desc = VaultDescriptor(
        kind=VaultKind.CONTENT,
        root=content_root,
        owner_uid=_CONTENT_OWNER,
        allowlist=build_sync_allowlist(content_root, content_root=content_root),
        bridge=_bridge(),
        supports_task_round_trip=False,
    )
    personal_desc = VaultDescriptor(
        kind=VaultKind.PERSONAL,
        root=personal_root,
        owner_uid=UserUID("user_placeholder"),
        allowlist=build_sync_allowlist(personal_root, content_root=content_root),
        bridge=_bridge(),
        supports_task_round_trip=True,
    )
    registry = VaultRegistry(content=content_desc, personal=personal_desc)
    service.vault_registry = registry
    service.sync_allowlist = personal_desc.allowlist

    # Reconciler for the CONTENT surface (round-trip off → user_service unused).
    reconciler = VaultReconciler(
        registry=registry,
        unified_ingestion=service,
        user_entry_service=Mock(),
        tasks_service=Mock(),
        user_service=Mock(),
    )

    created_uids: list[str] = []
    yield {
        "service": service,
        "reconciler": reconciler,
        "content_root": content_root,
        "personal_root": personal_root,
        "driver": neo4j_driver,
        "created_uids": created_uids,
    }

    async with neo4j_driver.session() as session:
        if created_uids:
            await session.run(
                "MATCH (n:Entity) WHERE n.uid IN $uids DETACH DELETE n",
                uids=created_uids,
            )


async def _owner_of(driver, uid: str) -> str | None:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (n:Entity {uid: $uid}) RETURN n.user_uid AS owner", uid=uid
        )
        record = await result.single()
        return record["owner"] if record else None


async def test_content_task_owner_uniform_across_surfaces(owner_env) -> None:
    """A task file in the content vault → content owner, whoever ingests it."""
    service = owner_env["service"]
    reconciler = owner_env["reconciler"]
    content_root: Path = owner_env["content_root"]
    driver = owner_env["driver"]

    # Surface 1 — dashboard/directory door acting as user_alpha.
    _task_file(content_root / "alpha-task.md", "Alpha Task")
    r1 = await service.ingest_directory(content_root, user_uid="user_alpha")
    assert r1.is_ok, r1

    # Surface 2 — directory door acting as user_beta (new file; alpha skipped).
    _task_file(content_root / "beta-task.md", "Beta Task")
    r2 = await service.ingest_directory(content_root, user_uid="user_beta")
    assert r2.is_ok, r2

    # Surface 3 — descriptor-driven reconciler as user_gamma.
    _task_file(content_root / "gamma-task.md", "Gamma Task")
    r3 = await reconciler.sync(VaultKind.CONTENT, "user_gamma")
    assert r3.is_ok, r3

    owner_env["created_uids"].extend(["task.alpha-task", "task.beta-task", "task.gamma-task"])

    assert await _owner_of(driver, "task.alpha-task") == _CONTENT_OWNER
    assert await _owner_of(driver, "task.beta-task") == _CONTENT_OWNER
    assert await _owner_of(driver, "task.gamma-task") == _CONTENT_OWNER


async def test_content_curriculum_has_no_owner(owner_env) -> None:
    """A curriculum entity (ku) in the content vault is SHARED — no owner stamped."""
    service = owner_env["service"]
    content_root: Path = owner_env["content_root"]
    driver = owner_env["driver"]

    _ku_file(content_root / "atom.md", "Shared Atom")
    result = await service.ingest_directory(content_root, user_uid="user_alpha")
    assert result.is_ok, result

    owner_env["created_uids"].append("ku.atom")
    # Curriculum drops its owner regardless of the acting user.
    assert await _owner_of(driver, "ku.atom") is None


async def test_personal_task_owned_by_acting_user(owner_env) -> None:
    """A task in the personal vault → the acting user (per-tenant ownership)."""
    service = owner_env["service"]
    personal_root: Path = owner_env["personal_root"]
    driver = owner_env["driver"]

    # Personal wall permits only doorway folders (knowledge/ is one).
    _task_file(personal_root / "knowledge" / "alice-task.md", "Alice Task")
    result = await service.ingest_directory(personal_root, user_uid=_ALICE)
    assert result.is_ok, result

    owner_env["created_uids"].append("task.alice-task")
    assert await _owner_of(driver, "task.alice-task") == _ALICE


async def test_file_supplied_user_uid_cannot_spoof_owner(owner_env) -> None:
    """A file claiming ``user_uid: victim`` is overridden by the vault descriptor.

    Under descriptor-governed ingestion the resolved owner is authoritative, so a
    personal-vault task file cannot spoof ownership onto another user.
    """
    service = owner_env["service"]
    personal_root: Path = owner_env["personal_root"]
    driver = owner_env["driver"]

    spoof = personal_root / "knowledge" / "spoof-task.md"
    spoof.parent.mkdir(parents=True, exist_ok=True)
    spoof.write_text("---\ntype: task\ntitle: Spoof\nuser_uid: user_victim\n---\n\nBody.\n")
    result = await service.ingest_directory(personal_root, user_uid=_ALICE)
    assert result.is_ok, result

    owner_env["created_uids"].append("task.spoof-task")
    # Descriptor owner (alice) wins over the file's claimed user_victim.
    assert await _owner_of(driver, "task.spoof-task") == _ALICE


async def test_multi_vault_span_scan_rejected(owner_env) -> None:
    """Scanning an ancestor that nests both vault roots is rejected fail-closed.

    The fixture's content/personal roots are siblings under ``tmp_path``; scanning
    ``tmp_path`` would sweep both vaults and mis-attribute one. The guard rejects
    it rather than stamping the wrong owner or opening a fail-closed wall.
    """
    service = owner_env["service"]
    parent = owner_env["content_root"].parent  # nests both content + personal

    result = await service.ingest_directory(parent, user_uid="user_alpha")

    assert result.is_error
    assert "different owner" in result.expect_error().message.lower()


async def test_content_staging_file_rejected_by_descriptor_wall(owner_env) -> None:
    """A single content-vault ``je_*`` file is walled by the content staging floor.

    The single-file door resolves the wall from the file's own vault descriptor,
    so a content ``je_out`` file is rejected consistently with the directory and
    reconciler paths — not silently accepted under the personal wall.
    """
    service = owner_env["service"]
    content_root: Path = owner_env["content_root"]

    staged = content_root / "je_out" / "generated.md"
    _task_file(staged, "Staged Output")
    result = await service.ingest_file(staged, user_uid="user_alpha")

    assert result.is_error
    assert "vault sync boundary" in result.expect_error().message.lower()
