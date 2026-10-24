"""Regression guard for the user-uid checks at the ingestion boundary.

Ownership is an exact string compare, so a colon/bare owner matches no real session or
:User node. These tests lock the fail-fast at the ingestion boundary; the configured
owners are refused at boot unless they are user uids (``VaultConfig.validate_owners``).

NOTE: this file deliberately contains non-canonical literals (`user:foo`, `user.mike`,
…) as test inputs. Do not "normalize" them — they are the cases under test.
"""

from pathlib import Path

import pytest

from core.models.enums.entity_enums import EntityType
from core.models.type_hints import TypeConverter
from core.services.ingestion.preparer import prepare_entity_data
from tests.helpers.ingestion_owner import INGESTION_TEST_OWNER


class TestToUserUid:
    def test_rejects_colon_form(self):
        with pytest.raises(ValueError):
            TypeConverter.to_user_uid("user" + ":system")

    def test_rejects_a_username(self):
        with pytest.raises(ValueError):
            TypeConverter.to_user_uid("user_mike")

    def test_accepts_a_generated_user_uid(self):
        assert TypeConverter.to_user_uid("user_3f9a0c41d2e87b65") == "user_3f9a0c41d2e87b65"


class TestIngestionBoundaryFailFast:
    """`prepare_entity_data` is the storage choke point for owner assignment."""

    def test_absent_user_uid_takes_the_default_owner(self):
        prepared = prepare_entity_data(
            EntityType.TASK, {"title": "Buy milk"}, None, Path("t.md"), INGESTION_TEST_OWNER
        )
        assert prepared["user_uid"] == INGESTION_TEST_OWNER

    def test_noncanonical_explicit_user_uid_is_rejected(self):
        with pytest.raises(ValueError):
            prepare_entity_data(
                EntityType.TASK,
                {"title": "Buy milk", "user_uid": "user" + ":foo"},
                None,
                Path("t.md"),
                INGESTION_TEST_OWNER,
            )
