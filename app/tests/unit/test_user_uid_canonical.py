"""Regression guard for the canonical user-id format (`user_<name>`).

The system user was once spelled two ways — `UserUID("user_system")` in the user
service vs the ingestion default `"user:system"` — and ingestion stamped colon/bare
owners that no real session or :User node could ever match (ownership is an exact
string compare). These tests lock the canonical convention: one constant, a canonical
default, fail-fast at the ingestion boundary, and a one-time normalizer for legacy data.

NOTE: this file deliberately contains non-canonical literals (`user:foo`, `user.mike`,
…) as test inputs. Do not "normalize" them — they are the cases under test.
"""

from pathlib import Path

import pytest

from core.constants import SYSTEM_USER_UID
from core.models.enums.entity_enums import EntityType
from core.models.type_hints import TypeConverter
from core.services.ingestion.config import DEFAULT_USER_UID
from core.services.ingestion.preparer import _prepare_core


class TestCanonicalConstants:
    def test_system_user_uid_is_canonical(self):
        assert SYSTEM_USER_UID == "user_system"
        assert TypeConverter.to_user_uid(SYSTEM_USER_UID) == SYSTEM_USER_UID

    def test_ingestion_default_is_canonical(self):
        # The ingestion default must never reintroduce the colon form.
        assert DEFAULT_USER_UID.startswith("user_")
        assert TypeConverter.to_user_uid(DEFAULT_USER_UID) == DEFAULT_USER_UID


class TestToUserUid:
    def test_rejects_colon_form(self):
        with pytest.raises(ValueError):
            TypeConverter.to_user_uid("user" + ":system")

    def test_accepts_canonical(self):
        assert TypeConverter.to_user_uid("user_mike") == "user_mike"


class TestNormalizeUserUid:
    @pytest.mark.parametrize(
        ("legacy", "expected"),
        [
            ("user" + ":system", "user_system"),
            ("user" + ".mike", "user_mike"),
            ("user" + "-456", "user_456"),
            ("system", "user_system"),
            ("user_system", "user_system"),  # already canonical, unchanged
            ("user" + ":test_learner", "user_test_learner"),  # internal underscore preserved
            ("user" + "-foo-bar", "user_foo-bar"),  # only the leading separator is rewritten
        ],
    )
    def test_normalizes_legacy_forms(self, legacy, expected):
        assert TypeConverter.normalize_user_uid(legacy) == expected


class TestIngestionBoundaryFailFast:
    """`_prepare_core` is the storage choke point for owner assignment."""

    def test_absent_user_uid_gets_canonical_default(self):
        prepared = _prepare_core(EntityType.TASK, {"title": "Buy milk"}, None, Path("t.md"))
        assert prepared["user_uid"] == DEFAULT_USER_UID
        assert prepared["user_uid"].startswith("user_")

    def test_noncanonical_explicit_user_uid_is_rejected(self):
        with pytest.raises(ValueError):
            _prepare_core(
                EntityType.TASK,
                {"title": "Buy milk", "user_uid": "user" + ":foo"},
                None,
                Path("t.md"),
            )
