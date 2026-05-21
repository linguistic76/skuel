"""
Group Ingestion Unit Tests
===========================

Covers:
- Detector maps "group" → NonKuDomain.GROUP.
- ENTITY_CONFIGS has Group entry with base_label=None (non-Entity node).
- UserUploadService teacher gate: non-teachers are rejected.
- UserUploadService TEACHER role accepts Group YAML and dispatches ingestion.
- ALLOWED_UPLOAD_TYPES includes NonKuDomain.GROUP.

See: ADR-053
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.entity_enums import NonKuDomain
from core.models.enums.user_enums import UserRole
from core.services.ingestion.config import ENTITY_CONFIGS
from core.services.ingestion.detector import TYPE_MAPPING, detect_entity_type
from core.services.ingestion.user_upload_service import (
    ALLOWED_UPLOAD_TYPES,
    TEACHER_ONLY_UPLOAD_TYPES,
    UserUploadService,
)
from core.utils.result_simplified import Result


class TestGroupDetector:
    def test_type_mapping_has_group(self):
        assert TYPE_MAPPING["group"] == NonKuDomain.GROUP

    def test_detect_entity_type_group_yaml(self, tmp_path):
        data = {"type": "group", "name": "Physics 101"}
        result = detect_entity_type(data, tmp_path / "group_physics.yaml")
        assert result == NonKuDomain.GROUP


class TestGroupEntityConfig:
    def test_config_registered(self):
        config = ENTITY_CONFIGS[NonKuDomain.GROUP]
        assert config.entity_label == "Group"
        assert config.uid_prefix == "group"
        assert "name" in config.required_fields

    def test_group_is_not_entity_labeled(self):
        """Group is a standalone :Group node — no :Entity base label."""
        assert ENTITY_CONFIGS[NonKuDomain.GROUP].base_label is None

    def test_requires_user_uid(self):
        """Upload user becomes owner_uid."""
        assert ENTITY_CONFIGS[NonKuDomain.GROUP].requires_user_uid is True


class TestUploadAllowList:
    def test_group_in_allowed_upload_types(self):
        assert NonKuDomain.GROUP in ALLOWED_UPLOAD_TYPES

    def test_group_is_teacher_only(self):
        assert NonKuDomain.GROUP in TEACHER_ONLY_UPLOAD_TYPES


class TestUserUploadServiceTeacherGate:
    def _make_service(self, tmp_path: Path):
        ingestion = MagicMock()
        ingestion.ingest_file = AsyncMock(
            return_value=Result.ok(
                {
                    "uid": "group_physics-101_abc",
                    "entity_type": "group",
                    "success": True,
                }
            )
        )
        return UserUploadService(
            ingestion_service=ingestion,
            user_vaults_base=tmp_path,
        )

    @pytest.mark.anyio
    async def test_registered_user_rejected_for_group_upload(self, tmp_path):
        service = self._make_service(tmp_path)
        yaml_bytes = b"type: group\nname: Physics 101\nuid: group_physics-101_abc\n"

        result = await service.upload_and_ingest(
            user_uid="user_reg_01",
            files=[("group_physics.yaml", yaml_bytes)],
            user_role=UserRole.REGISTERED,
        )

        assert result.is_ok
        batch = result.value
        assert batch.failed == 1
        assert batch.successful == 0
        assert "teacher" in (batch.results[0].error or "").lower()
        # ingestion must not have been dispatched
        service.ingestion_service.ingest_file.assert_not_awaited()

    @pytest.mark.anyio
    async def test_member_user_rejected_for_group_upload(self, tmp_path):
        service = self._make_service(tmp_path)
        yaml_bytes = b"type: group\nname: Physics 101\nuid: group_physics-101_abc\n"

        result = await service.upload_and_ingest(
            user_uid="user_mem_01",
            files=[("group_physics.yaml", yaml_bytes)],
            user_role=UserRole.MEMBER,
        )

        assert result.is_ok
        assert result.value.failed == 1
        service.ingestion_service.ingest_file.assert_not_awaited()

    @pytest.mark.anyio
    async def test_teacher_accepted_for_group_upload(self, tmp_path):
        service = self._make_service(tmp_path)
        yaml_bytes = b"type: group\nname: Physics 101\nuid: group_physics-101_abc\n"

        result = await service.upload_and_ingest(
            user_uid="user_teacher_01",
            files=[("group_physics.yaml", yaml_bytes)],
            user_role=UserRole.TEACHER,
        )

        assert result.is_ok
        batch = result.value
        assert batch.successful == 1, batch.results[0].error
        assert batch.failed == 0
        service.ingestion_service.ingest_file.assert_awaited_once()
        # File should have been written under groups/ subdirectory
        vault = service.get_user_vault_path("user_teacher_01")
        assert (vault / "groups" / "group_physics.yaml").exists()

    @pytest.mark.anyio
    async def test_teacher_task_upload_still_allowed(self, tmp_path):
        """Regression: teacher gate must not reject ordinary activity uploads."""
        service = self._make_service(tmp_path)
        service.ingestion_service.ingest_file = AsyncMock(
            return_value=Result.ok({"uid": "task_x", "entity_type": "task", "success": True})
        )
        yaml_bytes = b"type: task\ntitle: Prep lecture\nuid: task_prep_abc\n"

        result = await service.upload_and_ingest(
            user_uid="user_teacher_01",
            files=[("task_prep.yaml", yaml_bytes)],
            user_role=UserRole.TEACHER,
        )

        assert result.is_ok
        assert result.value.successful == 1
