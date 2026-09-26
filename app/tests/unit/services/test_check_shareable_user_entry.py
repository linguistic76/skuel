"""Tests for UnifiedSharingService._check_shareable USER_ENTRY branch (ADR-054, ADR-088 §1).

A UserEntry shares in ANY status (Submit & Share arc R2 — anyone may share
anything, any time); only the privacy rules refuse.
"""

import pytest

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.services.sharing.unified_sharing_service import UnifiedSharingService


class TestCheckShareableUserEntry:
    """USER_ENTRY can be shared at any status, archived included (R2)."""

    @pytest.mark.parametrize(
        "status",
        [
            EntityStatus.DRAFT.value,
            EntityStatus.ACTIVE.value,
            EntityStatus.SUBMITTED.value,
            EntityStatus.COMPLETED.value,
            EntityStatus.ARCHIVED.value,
        ],
    )
    def test_any_status_user_entry_is_shareable(self, status: str):
        result = UnifiedSharingService._check_shareable(status, EntityType.USER_ENTRY.value)
        assert result.is_ok
        assert result.value is True

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

    def test_an_archived_private_entry_may_still_ask_for_feedback(self):
        """Archived is no gate at all; a feedback request also skips the privacy rule."""
        result = UnifiedSharingService._check_shareable(
            EntityStatus.ARCHIVED.value,
            EntityType.USER_ENTRY.value,
            private=True,
            privacy_gated=False,
        )
        assert result.is_ok

    def test_user_entry_branch_precedes_default_completed_gate(self):
        """USER_ENTRY should pass in DRAFT — the default 'only completed' rule must not apply."""
        result = UnifiedSharingService._check_shareable(
            EntityStatus.DRAFT.value, EntityType.USER_ENTRY.value
        )
        assert result.is_ok
