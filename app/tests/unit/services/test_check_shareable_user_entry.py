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

    def test_user_entry_branch_precedes_default_completed_gate(self):
        """USER_ENTRY should pass in DRAFT — the default 'only completed' rule must not apply."""
        result = UnifiedSharingService._check_shareable(
            EntityStatus.DRAFT.value, EntityType.USER_ENTRY.value
        )
        assert result.is_ok
