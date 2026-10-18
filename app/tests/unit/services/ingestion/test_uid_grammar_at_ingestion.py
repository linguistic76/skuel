"""The uid grammar at both ingestion doors, and the personal-vault ``uid:`` refusal.

A uid a file supplies — its ``uid:`` line, or the uid its file name gives — is
read against ``uid_grammar.authored_uid_problem`` for every type, ``user_entry``
included, at the directory door (``parse_file_sync``) and the single-file door
(``ingest_file``). A personal-vault file never authors a ``uid:`` line (ADR-070
Decision 11): the vault policy refuses it, telling the author to remove it.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.entity_enums import EntityType
from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry import UserEntry
from core.services.ingestion.batch import parse_file_sync
from core.services.ingestion.preparer import prepare_entity_data
from core.services.ingestion.unified_ingestion_service import UnifiedIngestionService
from core.services.ingestion.validator import validate_uid_format
from core.services.ingestion.vault_policy import (
    file_vault_refusal,
    personal_file_uid,
    personal_vault_refusal,
    uid_in_use_reason,
)
from core.services.user_entry.audience_resolver import ShareOutcome
from core.services.vault.vault_descriptor import VaultKind
from core.utils.result_simplified import Result
from core.utils.uid_grammar import UidVerdict, classify, exemption_for
from tests.helpers.ingestion_owner import INGESTION_TEST_OWNER


def _file(tmp_path: Path, name: str, frontmatter: str) -> Path:
    path = tmp_path / name
    path.write_text(f"---\n{frontmatter}\n---\n\nbody\n", encoding="utf-8")
    return path


class TestValidateUidFormat:
    @pytest.mark.parametrize(
        ("entity_type", "uid"),
        [
            (EntityType.KU, "ku.mindfulness.attention"),
            (EntityType.RESOURCE, "resource.tao-te-ching"),
            (EntityType.LEARNING_PATH, "lp.mindfulness-101"),
            (EntityType.USER_ENTRY, "ue.worldview"),
        ],
    )
    def test_both_authored_shapes_pass(self, tmp_path: Path, entity_type, uid: str) -> None:
        assert validate_uid_format(entity_type, {"uid": uid}, tmp_path / "f.md").is_ok

    @pytest.mark.parametrize(
        "uid",
        ["ku.It's-mine", "ku.with space", "ku.café", "ku.a.b.c", "ku.a_b", "ku:python-basics"],
    )
    def test_a_uid_outside_the_grammar_is_refused(self, tmp_path: Path, uid: str) -> None:
        result = validate_uid_format(EntityType.KU, {"uid": uid}, tmp_path / "f.md")
        assert result.is_error, uid
        assert result.expect_error().details.get("field") == "uid"

    def test_user_entry_is_checked_too(self, tmp_path: Path) -> None:
        """A UserEntry uid is read like any other type's — ``list.goals`` has the wrong prefix."""
        result = validate_uid_format(
            EntityType.USER_ENTRY, {"uid": "list.goals"}, tmp_path / "goals list.md"
        )
        assert result.is_error
        assert "must start with 'ue.'" in result.expect_error().message

    def test_a_colon_user_entry_uid_is_refused(self, tmp_path: Path) -> None:
        """Forwarding ``moc:worldview`` would upsert a node apart from one stored in dot form."""
        result = validate_uid_format(
            EntityType.USER_ENTRY, {"uid": "moc:worldview"}, tmp_path / "worldview.md"
        )
        assert result.is_error
        assert "[a-z0-9._-]" in result.expect_error().message


class TestDirectoryDoor:
    def test_an_authored_user_entry_uid_is_checked(self, tmp_path: Path) -> None:
        f = _file(
            tmp_path, "goals list.md", "type: user_entry\npipeline: knowledge\nuid: list.goals"
        )
        _, entity_data, error = parse_file_sync(f, INGESTION_TEST_OWNER)
        assert entity_data is None and error is not None
        assert error["field"] == "uid" and "must start with 'ue.'" in error["error"]

    def test_a_user_entry_uid_in_the_grammar_passes(self, tmp_path: Path) -> None:
        f = _file(tmp_path, "goals.md", "type: user_entry\npipeline: knowledge\nuid: ue.goals")
        entity_type, _, error = parse_file_sync(f, INGESTION_TEST_OWNER)
        assert error is None and entity_type is EntityType.USER_ENTRY

    def test_a_quote_in_an_authored_uid_is_refused(self, tmp_path: Path) -> None:
        f = _file(tmp_path, "q.md", 'type: ku\nuid: "ku.it\'s"\ntitle: Q')
        _, _, error = parse_file_sync(f, INGESTION_TEST_OWNER)
        assert error is not None and "[a-z0-9._-]" in error["error"]

    def test_a_file_name_outside_the_grammar_gives_no_uid(self, tmp_path: Path) -> None:
        f = _file(tmp_path, "My Note.md", "type: ku\ntitle: Mine")
        _, entity_data, error = parse_file_sync(f, INGESTION_TEST_OWNER)
        assert entity_data is None and error is not None
        assert "rename the file" in error["error"] and "ku.my-note" in error["error"]

    def test_a_file_name_in_the_grammar_gives_its_uid(self, tmp_path: Path) -> None:
        f = _file(tmp_path, "my-note.md", "type: ku\ntitle: Mine")
        _, entity_data, error = parse_file_sync(f, INGESTION_TEST_OWNER)
        assert error is None and entity_data is not None
        assert entity_data["uid"] == "ku.my-note"

    def test_the_preparer_refuses_a_name_outside_the_grammar(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="rename the file"):
            prepare_entity_data(
                EntityType.KU, {"type": "ku"}, "body", tmp_path / "Café.md", INGESTION_TEST_OWNER
            )


def _ingestion_service() -> tuple[UnifiedIngestionService, MagicMock]:
    user_entries = MagicMock()
    entry = UserEntry(uid="ue_new", title="Probe", user_uid="user_1", pipeline=Pipeline.KNOWLEDGE)
    user_entries.create_entry = AsyncMock(return_value=Result.ok((entry, ShareOutcome())))
    user_entries.get_entry = AsyncMock(return_value=Result.ok(None))
    backend = MagicMock()
    backend.get_ingestion_metadata = AsyncMock(return_value=Result.ok([]))
    svc = UnifiedIngestionService(
        write_backend=MagicMock(),
        bulk_backend=MagicMock(),
        user_entry_service=user_entries,
        ingestion_backend=backend,
        default_user_uid=INGESTION_TEST_OWNER,
    )
    svc._chunk_entity_content = AsyncMock(return_value=True)  # type: ignore[method-assign]
    return svc, user_entries


@pytest.mark.asyncio
class TestSingleFileDoor:
    async def test_an_authored_user_entry_uid_is_checked_before_the_entry_door(
        self, tmp_path: Path
    ) -> None:
        svc, user_entries = _ingestion_service()
        f = _file(
            tmp_path, "goals list.md", "type: user_entry\npipeline: knowledge\nuid: list.goals"
        )

        result = await svc.ingest_file(f, user_uid="user_1")

        assert result.is_error
        assert "must start with 'ue.'" in result.expect_error().message
        user_entries.create_entry.assert_not_awaited()

    async def test_a_user_entry_without_a_uid_still_reaches_the_entry_door(
        self, tmp_path: Path
    ) -> None:
        svc, user_entries = _ingestion_service()
        f = _file(tmp_path, "goals.md", "type: user_entry\npipeline: knowledge\ntitle: Goals")

        result = await svc.ingest_file(f, user_uid="user_1")

        assert result.is_ok, result
        user_entries.create_entry.assert_awaited_once()


class TestPersonalFilesAuthorNoUid:
    @pytest.mark.parametrize(
        "entity_type", [EntityType.TASK, EntityType.USER_ENTRY, EntityType.LIFE_PATH]
    )
    def test_a_uid_line_is_refused_with_its_remedy(self, entity_type: EntityType) -> None:
        reason = personal_vault_refusal(entity_type, {"uid": "task.morning-run"})
        assert reason is not None and "remove the 'uid:' line" in reason

    def test_without_a_uid_line_the_file_is_ingested(self) -> None:
        assert personal_vault_refusal(EntityType.TASK, {"title": "t"}) is None

    def test_a_curriculum_file_is_refused_for_its_type_first(self) -> None:
        reason = personal_vault_refusal(EntityType.KU, {"uid": "ku.a.b"})
        assert reason is not None and "'type: ku'" in reason

    def test_the_preview_reads_the_same_verdict(self, tmp_path: Path) -> None:
        f = _file(tmp_path, "run.md", "type: task\nuid: task.morning-run\ntitle: Run")
        reason = file_vault_refusal(f, VaultKind.PERSONAL)
        assert reason is not None and "remove the 'uid:' line" in reason
        assert file_vault_refusal(f, VaultKind.CONTENT) is None

    def test_the_uid_in_use_reason_no_longer_offers_a_personal_uid(self) -> None:
        reason = uid_in_use_reason("task.secret")
        assert "give the file its own" not in reason
        assert "content-vault" in reason


class TestPersonalFileUid:
    def test_a_non_ascii_stem_derives_an_ascii_slug(self) -> None:
        uid = personal_file_uid(EntityType.TASK, Path("/vault/Café plan.md"), "user_a", None)
        assert uid.startswith("task_cafe-plan_"), uid
        assert classify(uid) is not UidVerdict.OUTSIDE

    def test_a_stem_with_no_ascii_slug_derives_the_plain_shape(self) -> None:
        uid = personal_file_uid(EntityType.TASK, Path("/vault/日本語.md"), "user_a", None)
        assert classify(uid) is UidVerdict.FITS, uid

    def test_an_ascii_stem_derives_what_it_always_did(self) -> None:
        """An ASCII stem derives the uid it derived before the ASCII fold."""
        uid = personal_file_uid(EntityType.TASK, Path("/vault/plan-it.md"), "user_a", None)
        assert uid.startswith("task_plan-it_")
        exemption = exemption_for(uid)
        assert exemption is not None and exemption.name == "named_generated"
