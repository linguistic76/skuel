"""The uid grammar (core/utils/uid_grammar.py) and its exemption register.

Every ``UID_EXEMPTIONS`` entry names the functions that mint its shape. The
drivers below call each one; an entry whose writers no longer mint its shape —
or mint a uid that already fits — is stale and fails here, so the PR that
migrates a shape also deletes its entry.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

import pytest

from core.models.enums.entity_enums import EntityType
from core.utils import uid_grammar
from core.utils.uid_grammar import (
    UID_EXEMPTIONS,
    UidVerdict,
    authored_uid_problem,
    classify,
    exemptions_for,
    generated_uid,
    slugify,
)


class TestClassify:
    @pytest.mark.parametrize(
        "uid",
        [
            "ku.mindfulness.attention",
            "resource.tao-te-ching",
            "lp.mindfulness-101",
            "ex.sel.self-awareness",
            "task_a1b2c3d4",
            "task_0123456789ab",
            "user_admin",
            "ue_beb86ecb",
        ],
    )
    def test_fits(self, uid: str) -> None:
        assert classify(uid) is UidVerdict.FITS

    @pytest.mark.parametrize(
        "uid",
        [
            "ue:daily:user_admin:2026-10-18",
            "ps.a.b:chunk:0",
            "ku.Attention",
            "ku.it's",
            "ku.café",
            "ku.with space",
            "",
        ],
    )
    def test_outside(self, uid: str) -> None:
        assert classify(uid) is UidVerdict.OUTSIDE

    @pytest.mark.parametrize(
        "uid",
        [
            "task_van-on-monday_5873a134",  # a uid segment inside a generated uid
            "group_default_user_admin",  # another uid inside it
            "hc.user_admin.habit_a1b2c3d4.1760000000",
            "insight.principle_alignment.task_x.20261018120000",
            "ku.a.b.c",  # four segments
            "ku.",
            "ku.a--b",
            "ku.-a",
            "5f348e63-fe54-45b9-a6b5-d4205be31270",  # no prefix
            "task_",
        ],
    )
    def test_shape(self, uid: str) -> None:
        assert classify(uid) is UidVerdict.SHAPE


class TestAuthoredUidProblem:
    def test_both_authored_shapes_pass(self) -> None:
        assert authored_uid_problem("ku.mindfulness.attention", "ku") is None
        assert authored_uid_problem("resource.tao-te-ching", "resource") is None

    def test_wrong_prefix(self) -> None:
        problem = authored_uid_problem("moc.worldview", "ue")
        assert problem is not None and "must start with 'ue.'" in problem

    def test_charset_is_named(self) -> None:
        problem = authored_uid_problem("ku.it's-mine", "ku")
        assert problem is not None and "[a-z0-9._-]" in problem

    def test_colon_is_outside_the_charset(self) -> None:
        problem = authored_uid_problem("ku:python-basics", "ku")
        assert problem is not None and "[a-z0-9._-]" in problem

    @pytest.mark.parametrize("uid", ["ku.a.b.c", "ku.a_b", "ku.a--b", "ku."])
    def test_shape_is_named(self, uid: str) -> None:
        problem = authored_uid_problem(uid, "ku")
        assert problem is not None and "'ku.{slug}'" in problem

    def test_a_generated_uid_is_not_an_authored_one(self) -> None:
        assert authored_uid_problem("task_a1b2c3d4", "task") is not None


class TestGeneratedUid:
    def test_builds(self) -> None:
        assert generated_uid("task", "a1b2c3d4") == "task_a1b2c3d4"

    @pytest.mark.parametrize("prefix", ["review_request", "Task", "1x", ""])
    def test_refuses_a_bad_prefix(self, prefix: str) -> None:
        with pytest.raises(ValueError, match="uid prefix"):
            generated_uid(prefix, "a1b2c3d4")

    @pytest.mark.parametrize("opaque", ["a-b", "a_b", "A1", ""])
    def test_refuses_a_bad_opaque_part(self, opaque: str) -> None:
        with pytest.raises(ValueError, match="opaque"):
            generated_uid("task", opaque)


class TestSlugify:
    def test_plain_text(self) -> None:
        assert slugify("Meditation Basics") == "meditation-basics"

    def test_special_characters_removed(self) -> None:
        assert slugify("What's Next? (Part 2)") == "whats-next-part-2"

    def test_whitespace_and_hyphen_runs_collapse(self) -> None:
        assert slugify("  a  --  b  ") == "a-b"

    def test_markdown_link_slugs_to_link_text(self) -> None:
        assert slugify("[Foo Bar](https://example.com/x)") == "foo-bar"

    def test_underscores_become_hyphens(self) -> None:
        assert slugify("active_listening") == "active-listening"
        assert slugify("a _ b__c") == "a-b-c"

    def test_accents_fold_to_ascii(self) -> None:
        assert slugify("Café Crème") == "cafe-creme"
        assert slugify("naïve résumé") == "naive-resume"

    def test_text_with_no_ascii_letter_slugs_to_nothing(self) -> None:
        assert slugify("日本語") == ""
        assert slugify("") == ""

    @pytest.mark.parametrize("text", ["Café Crème", "a_b c", "[x](y) — z", "Ünïcödé 2"])
    def test_every_slug_is_one_segment(self, text: str) -> None:
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slugify(text))


# ---------------------------------------------------------------------------
# The exemption register — one driver per writer, run against the live code
# ---------------------------------------------------------------------------


def _chunk() -> str:
    from core.models.ps_content.content_chunks import ContentChunk, ContentChunkType

    return ContentChunk(
        parent_uid="ps.a.b",
        chunk_index=3,
        chunk_type=ContentChunkType.SECTION,
        text="t",
        context_before="",
        context_after="",
    ).chunk_id


def _periodic() -> str:
    from core.models.user_entry.user_entry import periodic_note_uid

    return periodic_note_uid("daily", "user_admin", "2026-10-18")


def _named_generated() -> str:
    from core.utils.uid_generator import UIDGenerator

    return UIDGenerator.generate_uid("task", "Van on Monday")


def _personal_file() -> str:
    from core.services.ingestion.vault_policy import personal_file_uid

    return personal_file_uid(EntityType.TASK, Path("/vault/plan.md"), "user_a", None)


def _habit_completion() -> str:
    from core.services.habits.habits_completion_service import habit_completion_uid

    return habit_completion_uid("user_admin", "habit_a1b2c3d4", datetime(2026, 10, 18, 12))


def _insight() -> str:
    from core.models.insight.persisted_insight import InsightType, PersistedInsight
    from core.models.type_hints import EntityUID

    return PersistedInsight.generate_uid(
        InsightType.PRINCIPLE_ALIGNMENT, EntityUID("task_a1b2c3d4")
    )


def _default_group() -> str:
    from core.models.group.group import default_group_uid

    return default_group_uid("user_admin")


def _search_event() -> str:
    from core.services.search_event_recorder import search_event_uid

    return search_event_uid()


def _transcription() -> str:
    from core.services.transcription.transcription_service import transcription_uid

    return transcription_uid()


def _instruction_set() -> str:
    from core.services.content_enrichment_service import instruction_set_uid

    return instruction_set_uid("Reflective Journal")


def _invoice_from_request() -> str:
    from core.models.finance.invoice import (
        InvoiceCreateRequest,
        LineItemInput,
        invoice_create_request_to_dto,
    )
    from core.models.type_hints import UserUID

    request = InvoiceCreateRequest(
        invoice_type="outgoing",
        counterparty="Client",
        invoice_date=date(2026, 10, 18),
        items=[LineItemInput(description="work", quantity=1, unit_price=10.0)],
    )
    return invoice_create_request_to_dto(request, UserUID("user_admin")).uid


def _invoice_factory() -> str:
    from core.models.finance.invoice import create_invoice
    from core.models.type_hints import UserUID

    return create_invoice(
        UserUID("user_admin"),
        "outgoing",
        "Client",
        date(2026, 10, 18),
        [{"description": "work", "quantity": 1, "unit_price": 10.0}],
    ).uid


def _user_from_username() -> str:
    from core.models.user.user import create_user

    return create_user("Jane-Doe", "jane@example.com").uid


# writer path → a call of that writer
_DRIVERS: dict[str, Callable[[], str]] = {
    "core.models.ps_content.content_chunks:ContentChunk.chunk_id": _chunk,
    "core.models.user_entry.user_entry:periodic_note_uid": _periodic,
    "core.utils.uid_generator:UIDGenerator.generate_uid": _named_generated,
    "core.services.ingestion.vault_policy:personal_file_uid": _personal_file,
    "core.services.habits.habits_completion_service:habit_completion_uid": _habit_completion,
    "core.models.insight.persisted_insight:PersistedInsight.generate_uid": _insight,
    "core.models.group.group:default_group_uid": _default_group,
    "core.services.search_event_recorder:search_event_uid": _search_event,
    "core.services.transcription.transcription_service:transcription_uid": _transcription,
    "core.services.content_enrichment_service:instruction_set_uid": _instruction_set,
    "core.models.finance.invoice:invoice_create_request_to_dto": _invoice_from_request,
    "core.models.finance.invoice:create_invoice": _invoice_factory,
    "core.models.user.user:create_user": _user_from_username,
}

_WRITERS = [(exemption, writer) for exemption in UID_EXEMPTIONS for writer in exemption.writers]


def test_every_writer_has_a_driver() -> None:
    assert {writer for _, writer in _WRITERS} == set(_DRIVERS)


@pytest.mark.parametrize(
    ("exemption", "writer"), _WRITERS, ids=[f"{e.name}-{w}" for e, w in _WRITERS]
)
def test_each_writer_still_mints_its_exempt_shape(
    exemption: uid_grammar.UidExemption, writer: str
) -> None:
    """Stale when the writer is gone, or no longer mints the shape outside the grammar."""
    module_path, _, qualname = writer.partition(":")
    target: object = importlib.import_module(module_path)
    for part in qualname.split("."):
        target = getattr(target, part)  # an AttributeError here: the writer is gone
    uid = _DRIVERS[writer]()
    assert exemption.matches(uid), (
        f"exemption '{exemption.name}' is stale: {writer} now mints {uid!r} — delete the "
        "entry (or the writer from it)"
    )
    assert classify(uid) is not UidVerdict.FITS, (
        f"{writer} mints {uid!r}, which fits the grammar — exemption '{exemption.name}' is stale"
    )
    assert exemption in exemptions_for(uid)


def test_no_exemption_admits_a_uid_that_fits() -> None:
    for uid in ("ku.a.b", "resource.x", "task_a1b2c3d4", "user_admin"):
        assert exemptions_for(uid) == (), uid


def test_a_shape_two_writers_mint_names_both() -> None:
    """``user_foo_12345678`` is a username's uid and a named generated one alike."""
    names = [exemption.name for exemption in exemptions_for("user_foo_12345678")]
    assert names == ["named_generated", "user_from_username"]
