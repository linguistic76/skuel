"""Unit tests for the askesis converter chain (now live, ADR-059 follow-up).

Coverage:
- ``askesis_create_request_to_dto`` + ``create_askesis_dto_from_create_dto``
  produce a fully-formed AskesisDTO with a SKUEL-prefixed UID.
- ``askesis_update_request_to_dto`` + ``apply_askesis_update_to_dto`` only
  patch the fields the request specifies, leaving unspecified fields alone.
- ``_enum_value`` normalization handles both Pydantic-coerced strings and
  the enum-default case (``use_enum_values=True`` quirk surfaced when the
  converter chain went live).
"""

from __future__ import annotations

from core.models.askesis.askesis_converters import (
    apply_askesis_update_to_dto,
    askesis_create_request_to_dto,
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


class TestCreateRequestChain:
    """Request → CreateDTO → AskesisDTO."""

    def test_chain_with_explicit_values(self) -> None:
        request = AskesisCreateRequest(
            name="My Askesis",
            version="2.0",
            preferred_guidance_mode=GuidanceMode.SOCRATIC,
            preferred_complexity_level=QueryComplexity.COMPLEX,
        )

        create_dto = askesis_create_request_to_dto(request, "user_alice")
        assert create_dto.user_uid == "user_alice"
        assert create_dto.name == "My Askesis"
        assert create_dto.version == "2.0"
        # Pydantic coerces explicit enum inputs to their str value when
        # use_enum_values=True — the converter must not call .value on them.
        assert create_dto.preferred_guidance_mode == "socratic"
        assert create_dto.preferred_complexity_level == "complex"

        dto = create_askesis_dto_from_create_dto(create_dto)
        assert isinstance(dto, AskesisDTO)
        assert dto.uid.startswith("askesis_")
        assert dto.user_uid == "user_alice"
        assert dto.preferred_guidance_mode == "socratic"
        assert dto.created_at is not None

    def test_chain_with_defaults_keeps_enum(self) -> None:
        """Default values stay as enum instances (Pydantic V2 quirk)."""
        request = AskesisCreateRequest()

        create_dto = askesis_create_request_to_dto(request, "user_bob")

        # _enum_value extracts .value from the enum default
        assert create_dto.preferred_guidance_mode == "direct"
        assert create_dto.preferred_complexity_level == "moderate"

    def test_uid_format_matches_uidgenerator(self) -> None:
        """UID uses SKUEL's UIDGenerator prefix — no per-user timestamp hack."""
        request = AskesisCreateRequest()
        create_dto = askesis_create_request_to_dto(request, "user_charlie")
        dto = create_askesis_dto_from_create_dto(create_dto)
        # UIDGenerator.generate_random_uid("askesis") → "askesis_<random>"
        # NOT "askesis_user_charlie_<timestamp>"
        assert dto.uid.startswith("askesis_")
        assert "user_charlie" not in dto.uid


class TestUpdateRequestChain:
    """Request → UpdateDTO → apply patch to existing AskesisDTO."""

    def _existing_dto(self) -> AskesisDTO:
        return AskesisDTO(
            uid="askesis_existing",
            user_uid="user_alice",
            name="Original",
            version="1.0",
            preferred_guidance_mode=GuidanceMode.DIRECT.value,
            preferred_complexity_level=QueryComplexity.MODERATE.value,
            total_conversations=42,
        )

    def test_patches_only_specified_fields(self) -> None:
        request = AskesisUpdateRequest(name="Renamed")
        update_dto = askesis_update_request_to_dto(request, "askesis_existing")
        existing = self._existing_dto()

        patched = apply_askesis_update_to_dto(existing, update_dto)

        assert patched.name == "Renamed"
        # Unspecified fields untouched
        assert patched.version == "1.0"
        assert patched.preferred_guidance_mode == GuidanceMode.DIRECT.value
        assert patched.total_conversations == 42

    def test_patches_enum_fields_through_normalization(self) -> None:
        request = AskesisUpdateRequest(preferred_guidance_mode=GuidanceMode.SOCRATIC)
        update_dto = askesis_update_request_to_dto(request, "askesis_existing")
        existing = self._existing_dto()

        patched = apply_askesis_update_to_dto(existing, update_dto)

        # Pydantic coerced the enum input to "socratic"; converter passes
        # through cleanly via _enum_value without calling .value on the str.
        assert patched.preferred_guidance_mode == "socratic"
        assert patched.name == "Original"  # untouched

    def test_empty_request_is_no_op(self) -> None:
        request = AskesisUpdateRequest()
        update_dto = askesis_update_request_to_dto(request, "askesis_existing")
        existing = self._existing_dto()
        snapshot = (existing.name, existing.version, existing.preferred_guidance_mode)

        patched = apply_askesis_update_to_dto(existing, update_dto)

        assert (patched.name, patched.version, patched.preferred_guidance_mode) == snapshot
