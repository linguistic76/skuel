"""Tests for UnifiedSharingService._check_shareable USER_ENTRY branch (ADR-054)."""

import pytest

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.services.sharing.unified_sharing_service import UnifiedSharingService


class TestCheckShareableUserEntry:
    """USER_ENTRY can be shared at any non-archived status."""

    @pytest.mark.parametrize(
        "status",
        [
            EntityStatus.DRAFT.value,
            EntityStatus.ACTIVE.value,
            EntityStatus.SUBMITTED.value,
            EntityStatus.COMPLETED.value,
        ],
    )
    def test_non_archived_user_entry_is_shareable(self, status: str):
        result = UnifiedSharingService._check_shareable(status, EntityType.USER_ENTRY.value)
        assert result.is_ok
        assert result.value is True

    def test_archived_user_entry_is_not_shareable(self):
        result = UnifiedSharingService._check_shareable(
            EntityStatus.ARCHIVED.value, EntityType.USER_ENTRY.value
        )
        assert result.is_error
        err = str(result.expect_error())
        assert "archived" in err.lower()
        assert "user entries" in err.lower() or "user_entry" in err.lower()

    def test_a_private_flag_refuses_a_share_but_not_a_feedback_request(self):
        shared = UnifiedSharingService._check_shareable(
            EntityStatus.ACTIVE.value, EntityType.USER_ENTRY.value, private=True
        )
        assert shared.is_error
        assert "private" in str(shared.expect_error()).lower()
        submitted = UnifiedSharingService._check_shareable(
            EntityStatus.ACTIVE.value,
            EntityType.USER_ENTRY.value,
            private=True,
            privacy_gated=False,
        )
        assert submitted.is_ok

    @pytest.mark.parametrize("pipeline", ["transcribe_and_structure", "reference"])
    def test_a_private_pipeline_refuses_a_share(self, pipeline: str):
        result = UnifiedSharingService._check_shareable(
            EntityStatus.ACTIVE.value, EntityType.USER_ENTRY.value, pipeline=pipeline
        )
        assert result.is_error
        assert pipeline in str(result.expect_error())

    @pytest.mark.parametrize("pipeline", ["none", "knowledge", "teacher_review", "llm_summary"])
    def test_a_shareable_pipeline_passes(self, pipeline: str):
        assert UnifiedSharingService._check_shareable(
            EntityStatus.ACTIVE.value, EntityType.USER_ENTRY.value, pipeline=pipeline
        ).is_ok

    def test_archived_is_refused_before_privacy_even_for_a_feedback_request(self):
        result = UnifiedSharingService._check_shareable(
            EntityStatus.ARCHIVED.value,
            EntityType.USER_ENTRY.value,
            private=True,
            privacy_gated=False,
        )
        assert result.is_error
        assert "archived" in str(result.expect_error()).lower()

    def test_user_entry_branch_precedes_default_completed_gate(self):
        """USER_ENTRY should pass in DRAFT — the default 'only completed' rule must not apply."""
        result = UnifiedSharingService._check_shareable(
            EntityStatus.DRAFT.value, EntityType.USER_ENTRY.value
        )
        assert result.is_ok
