"""Unit tests for the askesis converter chain (now live, ADR-059 follow-up).

Coverage:
- ``askesis_create_request_to_dto`` + ``create_askesis_dto_from_create_dto``
  produce a fully-formed AskesisDTO with a SKUEL-prefixed UID.
- ``askesis_update_request_to_dto`` + ``askesis_update_changes`` patch only the
  fields the request specifies, leaving unspecified fields out of the write.
- ``_enum_value`` normalization handles both Pydantic-coerced strings and
  the enum-default case (``use_enum_values=True`` quirk surfaced when the
  converter chain went live).
"""

from __future__ import annotations

from core.models.askesis.askesis_converters import (
    askesis_create_request_to_dto,
    askesis_update_changes,
    askesis_update_request_to_dto,
    create_askesis_dto_from_create_dto,
)
from core.models.askesis.askesis_dto import AskesisDTO
from core.models.askesis.askesis_request import (
    AskesisCreateRequest,
    AskesisUpdateRequest,
)
from core.models.enums import GuidanceMode
from core.models.enums.askesis_enums import QueryComplexity
from tests.helpers.seed_uids import seed_user_uid


class TestCreateRequestChain:
    """Request → CreateDTO → AskesisDTO."""

    def test_chain_with_explicit_values(self) -> None:
        request = AskesisCreateRequest(
            name="My Askesis",
            version="2.0",
            preferred_guidance_mode=GuidanceMode.SOCRATIC,
            preferred_complexity_level=QueryComplexity.COMPLEX,
        )

        create_dto = askesis_create_request_to_dto(request, seed_user_uid("alice"))
        assert create_dto.user_uid == seed_user_uid("alice")
        assert create_dto.name == "My Askesis"
        assert create_dto.version == "2.0"
        # Pydantic coerces explicit enum inputs to their str value when
        # use_enum_values=True — the converter must not call .value on them.
        assert create_dto.preferred_guidance_mode == "socratic"
        assert create_dto.preferred_complexity_level == "complex"

        dto = create_askesis_dto_from_create_dto(create_dto)
        assert isinstance(dto, AskesisDTO)
        assert dto.uid.startswith("askesis_")
        assert dto.user_uid == seed_user_uid("alice")
        assert dto.preferred_guidance_mode == "socratic"
        assert dto.created_at is not None

    def test_chain_with_defaults_keeps_enum(self) -> None:
        """Default values stay as enum instances (Pydantic V2 quirk)."""
        request = AskesisCreateRequest()

        create_dto = askesis_create_request_to_dto(request, seed_user_uid("bob"))

        # _enum_value extracts .value from the enum default
        assert create_dto.preferred_guidance_mode == "direct"
        assert create_dto.preferred_complexity_level == "moderate"

    def test_uid_format_matches_uidgenerator(self) -> None:
        """UID uses SKUEL's UIDGenerator prefix — no per-user timestamp hack."""
        request = AskesisCreateRequest()
        create_dto = askesis_create_request_to_dto(request, seed_user_uid("charlie"))
        dto = create_askesis_dto_from_create_dto(create_dto)
        # UIDGenerator.generate_random_uid("askesis") → "askesis_<random>"
        # NOT "askesis_{the user uid}_<timestamp>"
        assert dto.uid.startswith("askesis_")
        assert seed_user_uid("charlie") not in dto.uid


class TestUpdateRequestChain:
    """Request → UpdateDTO → the partial patch of the fields the request sets."""

    def test_patches_only_specified_fields(self) -> None:
        request = AskesisUpdateRequest(name="Renamed")
        update_dto = askesis_update_request_to_dto(request, "askesis_existing")

        changes = askesis_update_changes(update_dto)

        # The name and the converter's own intelligence stamp; nothing the request
        # left unset (the version, the guidance mode, the conversation count).
        assert set(changes) == {"name", "last_intelligence_update"}
        assert changes["name"] == "Renamed"

    def test_patches_enum_fields_through_normalization(self) -> None:
        request = AskesisUpdateRequest(preferred_guidance_mode=GuidanceMode.SOCRATIC)
        update_dto = askesis_update_request_to_dto(request, "askesis_existing")

        changes = askesis_update_changes(update_dto)

        # Pydantic coerced the enum input to "socratic"; converter passes
        # through cleanly via _enum_value without calling .value on the str.
        assert changes["preferred_guidance_mode"] == "socratic"
        assert "name" not in changes

    def test_empty_request_patches_only_the_intelligence_stamp(self) -> None:
        request = AskesisUpdateRequest()
        update_dto = askesis_update_request_to_dto(request, "askesis_existing")

        assert set(askesis_update_changes(update_dto)) == {"last_intelligence_update"}
