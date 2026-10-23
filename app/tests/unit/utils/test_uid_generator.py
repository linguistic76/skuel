"""Every uid minter mints the uid grammar's one generated shape (core/utils/uid_grammar.py).

``UIDGenerator.generate_random_uid`` is the one random minter; every writer of a
random uid calls it. A uid derived from the parts that identify its node is
``uid_grammar.hashed_uid``. Each minter is driven below: random ones mint a fresh
``{prefix}_{16 hex}`` on every call, derived ones the same uid for the same parts.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest

from core.models.enums.entity_enums import EntityType
from core.utils.uid_generator import UIDGenerator
from core.utils.uid_grammar import OPAQUE_HEX, UidVerdict, classify


def _one_shape(prefix: str) -> re.Pattern[str]:
    return re.compile(rf"{prefix}_[0-9a-f]{{{OPAQUE_HEX}}}")


class TestGenerateRandomUid:
    def test_mints_the_one_shape(self):
        uid = UIDGenerator.generate_random_uid("task")
        assert _one_shape("task").fullmatch(uid), uid
        assert classify(uid) is UidVerdict.FITS

    def test_every_call_mints_a_fresh_uid(self):
        assert len({UIDGenerator.generate_random_uid("er") for _ in range(200)}) == 200

    @pytest.mark.parametrize("prefix", ["review_request", "Task", ""])
    def test_refuses_a_prefix_outside_the_grammar(self, prefix: str):
        with pytest.raises(ValueError, match="uid prefix"):
            UIDGenerator.generate_random_uid(prefix)

    def test_has_no_named_form(self):
        """A uid never carries its entity's title: the one shape is opaque."""
        assert "generate_uid" not in vars(UIDGenerator)


# ---------------------------------------------------------------------------
# Random minters: (prefix, call)
# ---------------------------------------------------------------------------


def _auth_event() -> str:
    from core.models.auth.auth_event import generate_auth_event_uid

    return generate_auth_event_uid()


def _session() -> str:
    from core.models.auth.session import generate_session_uid

    return generate_session_uid()


def _reset_token() -> str:
    from core.models.auth.password_reset_token import generate_reset_token_uid

    return generate_reset_token_uid()


def _device() -> str:
    from core.models.auth.device import generate_device_uid

    return generate_device_uid()


def _search_event() -> str:
    from core.services.search_event_recorder import search_event_uid

    return search_event_uid()


def _transcription() -> str:
    from core.services.transcription.transcription_service import transcription_uid

    return transcription_uid()


def _insight() -> str:
    from core.models.insight.persisted_insight import PersistedInsight

    return PersistedInsight.generate_uid()


def _task_dto() -> str:
    from core.models.task.task_dto import TaskDTO

    return TaskDTO.create_task("user_admin", "Van on Monday").uid


_RANDOM: dict[str, tuple[str, Callable[[], str]]] = {
    "auth_event": ("auth", _auth_event),
    "session": ("session", _session),
    "reset_token": ("reset", _reset_token),
    "device": ("device", _device),
    "search_event": ("search", _search_event),
    "transcription": ("transcription", _transcription),
    "insight": ("insight", _insight),
    "task_dto_with_a_title": ("task", _task_dto),
}


@pytest.mark.parametrize("name", sorted(_RANDOM))
def test_each_random_minter_mints_a_fresh_uid_of_the_one_shape(name: str):
    prefix, mint = _RANDOM[name]
    first, second = mint(), mint()
    assert _one_shape(prefix).fullmatch(first), first
    assert first != second


# ---------------------------------------------------------------------------
# Derived minters: (prefix, call with fixed parts)
# ---------------------------------------------------------------------------


def _habit_completion() -> str:
    from core.services.habits.habits_completion_service import habit_completion_uid

    return habit_completion_uid("user_admin", "habit_3f9a0c41d2e87b65", datetime(2026, 10, 23, 12))


def _default_group() -> str:
    from core.models.group.group import default_group_uid

    return default_group_uid("user_admin")


def _instruction_set() -> str:
    from core.services.content_enrichment_service import instruction_set_uid

    return instruction_set_uid("Reflective Journal")


def _personal_file() -> str:
    from core.services.ingestion.vault_policy import personal_file_uid

    return personal_file_uid(EntityType.TASK, Path("/vault/plan.md"), "user_a", None)


def _periodic_note() -> str:
    from core.models.user_entry.user_entry import periodic_note_uid

    return periodic_note_uid("daily", "user_admin", "2026-10-23")


def _chunk() -> str:
    from core.models.ps_content.content_chunks import ChunkStore, chunk_uid

    return chunk_uid(ChunkStore.CONTENT, "ps.a.b", 3)


def _progress() -> str:
    from core.models.progress import generate_progress_uid

    return generate_progress_uid("user_admin", "task_3f9a0c41d2e87b65", datetime(2026, 10, 23))


def _embedding() -> str:
    from core.models.vectors import generate_embedding_uid

    return generate_embedding_uid("ku.a.b", "text-embedding-3-small", datetime(2026, 10, 23))


def _mastery() -> str:
    from core.models.pathways.mastery import mastery_uid

    return mastery_uid("user_admin", "ku.a.b")


_DERIVED: dict[str, tuple[str, Callable[[], str]]] = {
    "habit_completion": ("hc", _habit_completion),
    "default_group": ("group", _default_group),
    "instruction_set": ("instructions", _instruction_set),
    "personal_file": ("task", _personal_file),
    "periodic_note": ("ue", _periodic_note),
    "chunk": ("chunk", _chunk),
    "progress": ("progress", _progress),
    "embedding": ("embedding", _embedding),
    "mastery": ("mastery", _mastery),
}


@pytest.mark.parametrize("name", sorted(_DERIVED))
def test_each_derived_minter_mints_the_same_uid_of_the_one_shape(name: str):
    prefix, mint = _DERIVED[name]
    uid = mint()
    assert _one_shape(prefix).fullmatch(uid), uid
    assert mint() == uid


def test_a_default_group_uid_does_not_spell_its_teacher():
    """Recognised by ``is_default``, owned through ``OWNS`` — never read off the uid."""
    from core.models.group.group import default_group_uid

    assert "user_admin" not in default_group_uid("user_admin")
    assert default_group_uid("user_admin") != default_group_uid("user_mike")


def test_two_owners_derive_two_personal_file_uids():
    from core.services.ingestion.vault_policy import personal_file_uid

    path = Path("/vault/plan.md")
    assert personal_file_uid(EntityType.TASK, path, "user_a", None) != personal_file_uid(
        EntityType.TASK, path, "user_b", None
    )


async def test_the_default_instruction_set_is_read_at_the_uid_its_writer_derives():
    """The reader and the writer of the default set name it the same way."""
    from unittest.mock import AsyncMock, MagicMock

    from core.services.content_enrichment_service import (
        DEFAULT_INSTRUCTION_SET_NAME,
        ContentEnrichmentService,
        instruction_set_uid,
    )
    from core.utils.result_simplified import Result

    backend = MagicMock()
    backend.load_exercise_instructions = AsyncMock(return_value=Result.ok([]))
    await ContentEnrichmentService(backend=backend)._load_instructions(None)

    backend.load_exercise_instructions.assert_awaited_once_with(
        instruction_set_uid(DEFAULT_INSTRUCTION_SET_NAME)
    )
