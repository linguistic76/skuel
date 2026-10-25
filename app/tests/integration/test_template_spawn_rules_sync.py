"""The content-vault sync holds an Activity Template to the rules of what it spawns.

A template is authored only in the content vault (ADR-091 S8), and its spawn builds
the instance directly, past the create request a user's own create passes. So the
sync refuses a template file that the request would refuse once copied: an online
event template with no ``meeting_url``, and a copied text field over the instance
request's cap (``copied_text_caps``, derived from the request models, so every
field is covered here the day it is written). A refused file is reported ignored,
naming the file and the field, and writes no node; the preview reports the same
refusal. Controls: the same file, fixed, is previewed as an ingest and synced.

Drives the real ``VaultReconciler`` over a temp content vault and the container.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import Mock

import pytest
import pytest_asyncio

from core.models.enums.entity_enums import EntityType
from core.ports.vault_bridge_protocol import VaultBridgePort
from core.services.ingestion.config import ENTITY_CONFIGS, build_sync_allowlist
from core.services.ps_engagement._spawn_orchestrator import copied_text_caps
from core.services.vault.vault_descriptor import VaultDescriptor, VaultKind, VaultRegistry
from core.services.vault.vault_reconciler import VaultReconciler, VaultSyncStats
from tests.helpers.production_backends import build_ingestion_service, build_production_backends
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import touch_forward

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from neo4j import AsyncDriver

pytestmark = pytest.mark.asyncio

MARK = "zzztplrules"
OWNER = seed_user_uid(f"{MARK}")
TEMPLATE_TYPES = tuple(t for t in EntityType if t.is_activity_template())
CAPPED_FIELDS = [
    (template_type, name, cap)
    for template_type in TEMPLATE_TYPES
    for name, cap in copied_text_caps(template_type).items()
]


class Vault:
    def __init__(self, driver: AsyncDriver, root: Path, reconciler: VaultReconciler) -> None:
        self.driver = driver
        self.root = root
        self.reconciler = reconciler

    def write(self, name: str, frontmatter: dict[str, Any]) -> None:  # boundary: YAML values
        lines = [f"{key}: {value}" for key, value in frontmatter.items()]
        path = self.root / name
        path.write_text("---\n" + "\n".join(lines) + "\n---\nBody.\n")
        touch_forward(path)

    async def preview(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """(would-ingest examples, would-ignore examples)."""
        result = await self.reconciler.preview(VaultKind.CONTENT, OWNER)
        assert result.is_ok, result
        return result.value.would_ingest_examples, result.value.would_ignore_examples

    async def sync(self) -> VaultSyncStats:
        result = await self.reconciler.sync(VaultKind.CONTENT, OWNER)
        assert result.is_ok, result
        assert not result.value.errors, result.value.errors
        return result.value

    async def node(self, uid: str) -> dict[str, Any] | None:  # boundary: raw graph read
        async with self.driver.session() as session:
            record = await (
                await session.run("MATCH (n:Entity {uid: $uid}) RETURN properties(n) AS p", uid=uid)
            ).single()
        return None if record is None else dict(record["p"])


@pytest_asyncio.fixture
async def vault(neo4j_driver: AsyncDriver, tmp_path: Path) -> AsyncIterator[Vault]:
    root = tmp_path / "content"
    root.mkdir()
    service = build_ingestion_service(
        driver=neo4j_driver,
        default_user_uid=OWNER,
        ingestion_backend=build_production_backends(neo4j_driver)["ingestion_backend"],
    )
    descriptor = VaultDescriptor(
        kind=VaultKind.CONTENT,
        root=root,
        owner_uid=OWNER,
        allowlist=build_sync_allowlist(root, content_root=root),
        bridge=cast("VaultBridgePort", object()),
        supports_task_round_trip=False,
    )
    registry = VaultRegistry(content=descriptor, personal=None)
    service.vault_registry = registry
    reconciler = VaultReconciler(
        registry=registry,
        unified_ingestion=service,
        user_entry_service=Mock(),
        tasks_service=Mock(),
        user_service=Mock(),
    )
    yield Vault(neo4j_driver, root, reconciler)
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid CONTAINS $mark OR n.uid = $owner DETACH DELETE n",
            mark=MARK,
            owner=OWNER,
        )
        await session.run(
            "MATCH (m:IngestionMetadata) WHERE m.file_path STARTS WITH $root DELETE m",
            root=str(root.resolve()),
        )


def _uid(template_type: EntityType, slug: str) -> str:
    return f"{ENTITY_CONFIGS[template_type].uid_prefix}.{MARK}.{slug}"


def _refused(lines: tuple[str, ...] | list[str], file_name: str, field: str) -> bool:
    return any(file_name in line and f"'{field}'" in line for line in lines)


@pytest.mark.parametrize("missing", ["absent", "empty"])
async def test_an_online_event_template_needs_a_meeting_url(vault: Vault, missing: str) -> None:
    uid = _uid(EntityType.EVENT_TEMPLATE, f"online-{missing}")
    name = f"online_{missing}_tmpl.md"
    frontmatter: dict[str, Any] = {  # boundary: YAML values
        "type": "event_template",
        "uid": uid,
        "title": f"{MARK} online review",
        "is_online": "true",
    }
    if missing == "empty":
        frontmatter["meeting_url"] = '""'
    vault.write(name, frontmatter)

    _ingest, ignore = await vault.preview()
    assert _refused(ignore, name, "meeting_url"), ignore
    stats = await vault.sync()
    assert _refused(stats.ignored, name, "meeting_url"), stats.ignored
    assert await vault.node(uid) is None

    vault.write(name, frontmatter | {"meeting_url": "https://example.com/review"})
    ingest, ignore = await vault.preview()
    assert any(name in line for line in ingest), ingest
    assert not ignore, ignore
    stats = await vault.sync()
    assert not stats.ignored, stats.ignored
    stored = await vault.node(uid)
    assert stored is not None
    assert stored["meeting_url"] == "https://example.com/review"


@pytest.mark.parametrize(
    ("template_type", "field", "cap"),
    CAPPED_FIELDS,
    ids=[f"{t.value}-{name}" for t, name, _cap in CAPPED_FIELDS],
)
async def test_a_copied_text_field_fits_its_instance_cap(
    vault: Vault, template_type: EntityType, field: str, cap: int
) -> None:
    uid = _uid(template_type, field.replace("_", "-"))
    name = f"{field}_tmpl.md"
    frontmatter: dict[str, Any] = {  # boundary: YAML values
        "type": template_type.value,
        "uid": uid,
        "title": f"{MARK} {field}",
    }
    vault.write(name, frontmatter | {field: "x" * (cap + 1)})

    _ingest, ignore = await vault.preview()
    assert _refused(ignore, name, field), ignore
    stats = await vault.sync()
    assert _refused(stats.ignored, name, field), stats.ignored
    assert await vault.node(uid) is None

    vault.write(name, frontmatter | {field: "x" * cap})
    ingest, ignore = await vault.preview()
    assert any(name in line for line in ingest), ingest
    assert not ignore, ignore
    stats = await vault.sync()
    assert not stats.ignored, stats.ignored
    stored = await vault.node(uid)
    assert stored is not None
    assert stored[field] == "x" * cap
