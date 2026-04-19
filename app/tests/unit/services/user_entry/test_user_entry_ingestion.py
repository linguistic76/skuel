"""Tests for user_entry_ingestion (/upload → UserEntryService bridge)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.metadata_enums import Visibility
from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry import UserEntry
from core.services.ingestion.user_entry_ingestion import (
    build_user_entry_request,
    ingest_user_entry,
)
from core.services.user_entry.audience_resolver import AudienceResolver, ShareOutcome
from core.utils.result_simplified import Result


def _resolver(teachers=None) -> AudienceResolver:
    resolver = AudienceResolver(sharing_service=None, group_service=None)
    resolver.resolve_default_teachers = AsyncMock(return_value=teachers or [])  # type: ignore[method-assign]
    return resolver


class TestBuildUserEntryRequest:
    @pytest.mark.asyncio
    async def test_missing_pipeline_rejected(self):
        result = await build_user_entry_request(
            data={"title": "x"},
            file_path=Path("reflection.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_error
        assert "pipeline" in str(result.expect_error()).lower()

    @pytest.mark.asyncio
    async def test_audio_pipeline_rejected(self):
        result = await build_user_entry_request(
            data={"pipeline": "transcribe_and_structure"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_error
        assert "audio" in str(result.expect_error()).lower()

    @pytest.mark.asyncio
    async def test_default_audience_expands_to_user_groups(self):
        resolver = _resolver(teachers=["g_a", "g_b"])
        result = await build_user_entry_request(
            data={"pipeline": "teacher_review", "title": "Essay"},
            file_path=Path("essay.yaml"),
            user_uid="user_1",
            audience_resolver=resolver,
        )
        assert result.is_ok
        req = result.value
        assert req.pipeline == Pipeline.TEACHER_REVIEW
        assert req.share_with_groups == ["g_a", "g_b"]
        resolver.resolve_default_teachers.assert_awaited_once_with("user_1")

    @pytest.mark.asyncio
    async def test_explicit_group_audience(self):
        result = await build_user_entry_request(
            data={"pipeline": "teacher_review", "audience": "group:g_class"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_ok
        assert result.value.share_with_groups == ["g_class"]

    @pytest.mark.asyncio
    async def test_audience_group_without_uid_rejected(self):
        result = await build_user_entry_request(
            data={"pipeline": "none", "audience": "group:"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_error
        assert "group" in str(result.expect_error()).lower()

    @pytest.mark.asyncio
    async def test_public_audience_sets_visibility(self):
        result = await build_user_entry_request(
            data={"pipeline": "none", "audience": "public"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_ok
        assert result.value.visibility == Visibility.PUBLIC
        assert result.value.share_with_groups == []

    @pytest.mark.asyncio
    async def test_private_audience_no_shares_no_visibility(self):
        result = await build_user_entry_request(
            data={"pipeline": "none", "audience": "private"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_ok
        req = result.value
        assert req.share_with_groups == []
        assert req.visibility is None

    @pytest.mark.asyncio
    async def test_teacher_review_with_zero_groups_is_rejected_by_validator(self):
        """Student in no groups + TEACHER_REVIEW + no explicit audience →
        validator fails (ADR §3 — no silent no-audience turn-ins)."""
        result = await build_user_entry_request(
            data={"pipeline": "teacher_review"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(teachers=[]),
        )
        assert result.is_error
        assert "audience" in str(result.expect_error()).lower()

    @pytest.mark.asyncio
    async def test_title_defaults_from_filename(self):
        result = await build_user_entry_request(
            data={"pipeline": "none"},
            file_path=Path("my-deep-reflection.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_ok
        assert result.value.title == "My Deep Reflection"

    @pytest.mark.asyncio
    async def test_unknown_pipeline_rejected(self):
        result = await build_user_entry_request(
            data={"pipeline": "does_not_exist"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            audience_resolver=_resolver(),
        )
        assert result.is_error
        assert "pipeline" in str(result.expect_error()).lower()


class TestIngestUserEntry:
    @pytest.mark.asyncio
    async def test_delegates_to_create_entry(self):
        entry = UserEntry(
            uid="ue_1",
            title="Essay",
            user_uid="user_1",
            pipeline=Pipeline.TEACHER_REVIEW,
        )
        outcome = ShareOutcome(shared_groups=("g_a",))

        service = MagicMock()
        service.audience_resolver = _resolver(teachers=["g_a"])
        service.create_entry = AsyncMock(return_value=Result.ok((entry, outcome)))

        result = await ingest_user_entry(
            data={"pipeline": "teacher_review", "title": "Essay"},
            file_path=Path("essay.yaml"),
            user_uid="user_1",
            user_entry_service=service,
        )

        assert result.is_ok
        payload = result.value
        assert payload["uid"] == "ue_1"
        assert payload["entity_type"] == "user_entry"
        assert payload["success"] is True
        assert payload["relationships_created"] == 1  # one shared group, no exercise
        assert payload["share_outcome"]["shared_groups"] == ["g_a"]

    @pytest.mark.asyncio
    async def test_validation_error_short_circuits(self):
        service = MagicMock()
        service.audience_resolver = _resolver()
        service.create_entry = AsyncMock()

        result = await ingest_user_entry(
            data={"title": "no pipeline"},
            file_path=Path("x.yaml"),
            user_uid="user_1",
            user_entry_service=service,
        )

        assert result.is_error
        service.create_entry.assert_not_awaited()
