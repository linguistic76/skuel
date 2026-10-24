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
from datetime import date

import pytest

from core.utils import uid_grammar
from core.utils.uid_grammar import (
    GENERATED_UID,
    OPAQUE_HEX,
    UID_EXEMPTIONS,
    UidVerdict,
    authored_uid_problem,
    classify,
    exemptions_for,
    generated_uid,
    hashed_uid,
    is_known_uid,
    slugify,
)

HEX16 = "3f9a0c41d2e87b65"


class TestClassify:
    @pytest.mark.parametrize(
        "uid",
        [
            "ku.mindfulness.attention",
            "resource.tao-te-ching",
            "lp.mindfulness-101",
            "ex.sel.self-awareness",
            f"task_{HEX16}",
            f"chunk_{HEX16}",
            f"ue_{HEX16}",
            f"user_{HEX16}",
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
            f"task_{HEX16.upper()}",
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
            "task_a1b2c3d4",  # 8 hex: not the one width
            "msg_0123456789ab",  # 12 hex
            "auth_7119a485a92751a3ea752747b8b7d50c",  # 32 hex
            "task_0123456789abcdeg",  # 16, not all hex
            "user_admin",  # a username's uid: exempt, never the shape
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
        assert authored_uid_problem(f"task_{HEX16}", "task") is not None


class TestGeneratedUid:
    def test_builds(self) -> None:
        assert generated_uid("task", HEX16) == f"task_{HEX16}"

    @pytest.mark.parametrize("prefix", ["review_request", "Task", "1x", ""])
    def test_refuses_a_bad_prefix(self, prefix: str) -> None:
        with pytest.raises(ValueError, match="uid prefix"):
            generated_uid(prefix, HEX16)

    @pytest.mark.parametrize(
        "opaque", ["a1b2c3d4", "0123456789ab", HEX16 * 2, HEX16.upper(), "g" * 16, "a-b", ""]
    )
    def test_refuses_any_opaque_part_but_sixteen_hex_digits(self, opaque: str) -> None:
        with pytest.raises(ValueError, match="opaque"):
            generated_uid("task", opaque)

    def test_the_width_is_64_bits(self) -> None:
        """Pinned: a narrower uid collides within a corpus this size (8 hex ≈ 1% at 10k)."""
        assert OPAQUE_HEX == 16


class TestHashedUid:
    def test_is_a_generated_uid(self) -> None:
        uid = hashed_uid("chunk", "content", "ps.a.b", "3")
        assert classify(uid) is UidVerdict.FITS
        assert GENERATED_UID.fullmatch(uid)
        assert re.fullmatch(rf"chunk_[0-9a-f]{{{OPAQUE_HEX}}}", uid)

    def test_the_same_parts_always_mint_the_same_uid(self) -> None:
        assert hashed_uid("chunk", "content", "ps.a.b", "3") == hashed_uid(
            "chunk", "content", "ps.a.b", "3"
        )

    def test_it_is_sha256_over_the_parts_joined_by_nul(self) -> None:
        import hashlib

        digest = hashlib.sha256(b"content\0ps.a.b\x003").hexdigest()[:OPAQUE_HEX]
        assert hashed_uid("chunk", "content", "ps.a.b", "3") == f"chunk_{digest}"

    @pytest.mark.parametrize(
        ("left", "right"),
        [
            (("a", "bc"), ("ab", "c")),  # the separator keeps the parts apart
            (("content", "ps.a.b", "3"), ("reference", "ps.a.b", "3")),
            (("content", "ps.a.b", "3"), ("content", "ps.a.b", "4")),
            (("content", "ps.a.b", "3"), ("content", "ps.a.c", "3")),
        ],
    )
    def test_different_parts_mint_different_uids(
        self, left: tuple[str, ...], right: tuple[str, ...]
    ) -> None:
        assert hashed_uid("chunk", *left) != hashed_uid("chunk", *right)

    @pytest.mark.parametrize("parts", [(), ("",), ("a", ""), ("a\0b",)])
    def test_refuses_parts_that_could_not_identify_a_node(self, parts: tuple[str, ...]) -> None:
        with pytest.raises(ValueError, match="part"):
            hashed_uid("chunk", *parts)

    def test_refuses_a_bad_prefix(self) -> None:
        with pytest.raises(ValueError, match="uid prefix"):
            hashed_uid("Chunk", "a")


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


# writer path → a call of that writer
_DRIVERS: dict[str, Callable[[], str]] = {
    "core.models.finance.invoice:invoice_create_request_to_dto": _invoice_from_request,
    "core.models.finance.invoice:create_invoice": _invoice_factory,
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
    for uid in ("ku.a.b", "resource.x", f"task_{HEX16}", f"user_{HEX16}"):
        assert exemptions_for(uid) == (), uid


def test_a_new_user_uid_fits_the_generated_shape() -> None:
    """A user uid is generated — the username never reaches it."""
    from core.models.user.user import create_user

    uid = create_user("jane-doe", "jane@example.com").uid
    assert classify(uid) is UidVerdict.FITS
    assert uid.startswith("user_")
    assert "jane" not in uid


@pytest.mark.parametrize("uid", ["user_admin", "user_linguistic76", "user_a1b2c3d4"])
def test_a_username_shaped_user_uid_is_unknown(uid: str) -> None:
    """``user_{username}`` is retired: no exemption names it."""
    assert exemptions_for(uid) == ()
    assert not is_known_uid(uid)


class TestIsKnownUid:
    @pytest.mark.parametrize(
        "uid",
        [
            "ku.a.b",
            f"task_{HEX16}",
            f"user_{HEX16}",
            "invoice:5f348e63-fe54-45b9-a6b5-d4205be31270",
        ],
    )
    def test_a_fitting_or_exempt_uid_is_known(self, uid: str) -> None:
        assert is_known_uid(uid)

    @pytest.mark.parametrize(
        "uid", ["task_a1b2c3d4", "task_van-on-monday_5873a134", "ue:daily:u:d", "", "x"]
    )
    def test_any_other_is_not(self, uid: str) -> None:
        assert not is_known_uid(uid)
