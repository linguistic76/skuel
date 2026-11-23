"""What each vault holds, and what each refuses — the content vault, a personal vault, neither.

Every file-ingestible type belongs to exactly one place: the content vault
(curriculum, curated resources, Groups), a personal vault (the six Activities, a
life path, notes), or no vault at all (a record the app writes as a learner works).
Each vault refuses every other type with a reason that says where the file belongs,
and the directory door's parse stage and the single-file door give that one verdict.
"""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.ports.vault_bridge_protocol import VaultBridgePort
from core.services.ingestion.batch import parse_file_sync
from core.services.ingestion.config import ENTITY_CONFIGS, build_sync_allowlist
from core.services.ingestion.unified_ingestion_service import UnifiedIngestionService
from core.services.ingestion.vault_policy import (
    APP_RECORDED_TYPES,
    CONTENT_VAULT_TYPES,
    PERSONAL_VAULT_TYPES,
    vault_refusal,
)
from core.services.vault.vault_descriptor import VaultDescriptor, VaultKind, VaultRegistry
from tests.helpers.ingestion_owner import INGESTION_TEST_OWNER

ACTIVITIES = sorted((t for t in EntityType if t.is_activity()), key=str)
OWNED_OR_RECORDED = sorted(PERSONAL_VAULT_TYPES | APP_RECORDED_TYPES, key=str)
CONTENT_TYPES = sorted(CONTENT_VAULT_TYPES, key=str)
# A declared type with no ingestion config: the app writes it, no file can.
NOT_FILE_INGESTIBLE = sorted((t for t in EntityType if t not in ENTITY_CONFIGS), key=str)


def _file(tmp_path: Path, name: str, frontmatter: str) -> Path:
    path = tmp_path / name
    path.write_text(f"---\n{frontmatter}\n---\n\nbody\n", encoding="utf-8")
    return path


class TestEveryIngestibleTypeHasOnePlace:
    def test_the_three_sets_partition_the_file_ingestible_types(self) -> None:
        places = (CONTENT_VAULT_TYPES, PERSONAL_VAULT_TYPES, APP_RECORDED_TYPES)
        assert frozenset().union(*places) == frozenset(ENTITY_CONFIGS)
        for one, other in combinations(places, 2):
            assert not one & other

    def test_the_content_vault_holds_curriculum_resources_and_groups(self) -> None:
        assert {
            EntityType.KU,
            EntityType.PATH_STEP,
            EntityType.LEARNING_PATH,
            EntityType.EXERCISE,
            *(t for t in EntityType if t.is_activity_template()),
            EntityType.RESOURCE,
            NonKuDomain.GROUP,
        } == CONTENT_VAULT_TYPES


class TestTheContentVault:
    @pytest.mark.parametrize("entity_type", OWNED_OR_RECORDED, ids=str)
    def test_every_type_a_person_owns_or_the_app_records_is_refused(
        self, entity_type: EntityType
    ) -> None:
        assert vault_refusal(VaultKind.CONTENT, entity_type, {"title": "t"}) is not None

    @pytest.mark.parametrize("entity_type", CONTENT_TYPES, ids=str)
    def test_every_content_type_is_ingested(self, entity_type: EntityType | NonKuDomain) -> None:
        assert vault_refusal(VaultKind.CONTENT, entity_type, {"uid": "x.y"}) is None

    def test_an_edge_file_is_ingested(self) -> None:
        assert vault_refusal(VaultKind.CONTENT, None, {"type": "Edge"}) is None

    @pytest.mark.parametrize("activity", ACTIVITIES, ids=str)
    def test_an_activity_is_pointed_at_a_personal_vault_and_its_template(
        self, activity: EntityType
    ) -> None:
        reason = vault_refusal(VaultKind.CONTENT, activity, {"uid": f"{activity.value}.a"})
        assert reason is not None
        assert "personal vault" in reason
        assert f"'type: {activity.template_type().value}'" in reason

    def test_a_note_is_pointed_at_a_personal_vault_or_a_plain_note(self) -> None:
        reason = vault_refusal(VaultKind.CONTENT, EntityType.USER_ENTRY, {"pipeline": "knowledge"})
        assert reason is not None
        assert "personal vault" in reason
        assert "remove its 'type:' line" in reason

    def test_a_life_path_is_pointed_at_a_personal_vault(self) -> None:
        reason = vault_refusal(VaultKind.CONTENT, EntityType.LIFE_PATH, {})
        assert reason is not None and "personal vault" in reason


class TestAPersonalVault:
    @pytest.mark.parametrize("entity_type", sorted(PERSONAL_VAULT_TYPES, key=str), ids=str)
    def test_every_personal_type_is_ingested(self, entity_type: EntityType) -> None:
        assert vault_refusal(VaultKind.PERSONAL, entity_type, {"title": "t"}) is None

    @pytest.mark.parametrize("entity_type", CONTENT_TYPES, ids=str)
    def test_every_content_type_is_refused_as_the_content_vaults(
        self, entity_type: EntityType | NonKuDomain
    ) -> None:
        reason = vault_refusal(VaultKind.PERSONAL, entity_type, {"type": str(entity_type)})
        assert reason is not None and "content vault only" in reason

    def test_an_edge_file_is_refused(self) -> None:
        reason = vault_refusal(VaultKind.PERSONAL, None, {"type": "Edge"})
        assert reason is not None and "content vault only" in reason


class TestARecordTheAppWrites:
    @pytest.mark.parametrize("kind", [VaultKind.CONTENT, VaultKind.PERSONAL], ids=str)
    @pytest.mark.parametrize("entity_type", sorted(APP_RECORDED_TYPES, key=str), ids=str)
    def test_no_vault_syncs_it(self, kind: VaultKind, entity_type: EntityType) -> None:
        reason = vault_refusal(kind, entity_type, {"type": entity_type.value})
        assert reason is not None
        assert "recorded by the app" in reason
        assert "content vault" not in reason

    def test_outside_every_vault_nothing_is_refused_by_kind(self) -> None:
        assert vault_refusal(None, EntityType.INTERACTION, {}) is None


class TestTheDirectoryDoorsParseStage:
    def test_a_content_vault_task_is_refused_before_any_field_check(self, tmp_path: Path) -> None:
        f = _file(tmp_path, "run.md", "type: task\nuid: task.morning-run\ntitle: Run")

        entity_type, data, error = parse_file_sync(
            f, INGESTION_TEST_OWNER, vault_kind=VaultKind.CONTENT
        )

        assert entity_type is None and data is None and error is not None
        assert error["stage"] == "validation"
        assert error["field"] == "type"
        assert "'type: task_template'" in error["error"]

    def test_a_content_vault_ku_parses(self, tmp_path: Path) -> None:
        f = _file(tmp_path, "attention.md", "type: ku\nuid: ku.mind.attention\ntitle: Attention")

        entity_type, _, error = parse_file_sync(
            f, INGESTION_TEST_OWNER, vault_kind=VaultKind.CONTENT
        )

        assert error is None and entity_type is EntityType.KU

    @pytest.mark.parametrize("kind", [VaultKind.CONTENT, VaultKind.PERSONAL], ids=str)
    def test_an_interaction_is_refused_in_both_vaults(
        self, tmp_path: Path, kind: VaultKind
    ) -> None:
        f = _file(
            tmp_path,
            "ia.md",
            "type: interaction\ninteraction_type: exercise_submission\ntarget_uid: ex.a",
        )

        _, _, error = parse_file_sync(f, INGESTION_TEST_OWNER, vault_kind=kind)

        assert error is not None and error["stage"] == "validation"
        assert "recorded by the app" in error["error"]

    @pytest.mark.parametrize("kind", [VaultKind.CONTENT, VaultKind.PERSONAL], ids=str)
    @pytest.mark.parametrize("entity_type", NOT_FILE_INGESTIBLE, ids=str)
    def test_a_type_no_file_can_hold_is_reported_as_unsupported_in_both_vaults(
        self, tmp_path: Path, kind: VaultKind, entity_type: EntityType
    ) -> None:
        f = _file(tmp_path, "r.md", f"type: {entity_type.value}\ntitle: R")

        _, _, error = parse_file_sync(f, INGESTION_TEST_OWNER, vault_kind=kind)

        assert error is not None and error["stage"] == "validation"
        assert f"unsupported type '{entity_type.value}'" in error["error"]
        assert "content vault" not in error["error"]


def _service_over(kind: VaultKind, root: Path) -> UnifiedIngestionService:
    """An ingestion service whose registry governs ``root`` as a vault of ``kind``."""
    allowlist = (
        build_sync_allowlist(root, content_root=root, gates_je_pro=False)
        if kind is VaultKind.CONTENT
        else build_sync_allowlist(root, content_root=root.parent / "content")
    )
    descriptor = VaultDescriptor(
        kind=kind,
        root=root,
        owner_uid=INGESTION_TEST_OWNER,
        allowlist=allowlist,
        bridge=cast("VaultBridgePort", object()),
        supports_task_round_trip=False,
    )
    svc = UnifiedIngestionService(
        write_backend=MagicMock(),
        bulk_backend=MagicMock(),
        user_entry_service=MagicMock(),
        ingestion_backend=MagicMock(),
        default_user_uid=INGESTION_TEST_OWNER,
    )
    svc.vault_registry = (
        VaultRegistry(content=descriptor, personal=None)
        if kind is VaultKind.CONTENT
        else VaultRegistry(content=None, personal=descriptor)
    )
    return svc


@pytest.mark.asyncio
class TestTheSingleFileDoor:
    async def test_a_content_vault_note_is_refused_before_the_entry_door(
        self, tmp_path: Path
    ) -> None:
        svc = _service_over(VaultKind.CONTENT, tmp_path)
        create_entry = AsyncMock()
        svc.user_entry_service = MagicMock(create_entry=create_entry)
        f = _file(tmp_path, "note.md", "type: user_entry\npipeline: knowledge\ntitle: Note")

        result = await svc.ingest_file(f, user_uid=INGESTION_TEST_OWNER)

        assert result.is_error
        assert "personal vault" in result.expect_error().message
        create_entry.assert_not_awaited()

    async def test_a_personal_vault_interaction_is_refused(self, tmp_path: Path) -> None:
        svc = _service_over(VaultKind.PERSONAL, tmp_path)
        (tmp_path / "knowledge").mkdir()
        f = _file(
            tmp_path / "knowledge",
            "ia.md",
            "type: interaction\ninteraction_type: exercise_submission\ntarget_uid: ex.a",
        )

        result = await svc.ingest_file(f, user_uid=INGESTION_TEST_OWNER)

        assert result.is_error
        assert "recorded by the app" in result.expect_error().message
