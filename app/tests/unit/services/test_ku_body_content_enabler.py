"""Ku lesson bodies — config gate + the :Content-node read fallback.

The stubs → lessons enabler (2026-07-06): Ku joins PathStep as a
``chunks_body_content`` type, and ``get_with_content`` gains a real backend
fallback (``UniversalNeo4jBackend.get_content``) for bodies that live on the
:Content node rather than the entity (ADR-074). The fallback is also what
restores the PathStep reading body on /explore/ps pages, which had been
silently empty since the body pop landed without a read counterpart.
"""

import logging
from dataclasses import dataclass, field

import pytest

from core.models.enums.entity_enums import EntityType
from core.models.relationship_names import RelationshipName
from core.services.ingestion.config import ENTITY_CONFIGS, EntityIngestionConfig
from core.services.mixins.context_operations_mixin import ContextOperationsMixin
from core.utils.result_simplified import Errors, Result

# ---------------------------------------------------------------------------
# Ingestion config gate
# ---------------------------------------------------------------------------


def test_ku_and_path_step_are_body_chunked():
    """Both lesson-bearing types extract AND chunk their markdown bodies."""
    for entity_type in (EntityType.KU, EntityType.PATH_STEP):
        config = ENTITY_CONFIGS[entity_type]
        assert config.extracts_body_content is True
        assert config.chunks_body_content is True


def test_chunked_types_always_extract():
    """Config invariant: chunking consumes the `content` key extraction sets."""
    for entity_type, config in ENTITY_CONFIGS.items():
        if config.chunks_body_content:
            assert config.extracts_body_content, (
                f"{entity_type}: chunks_body_content without extracts_body_content"
            )


def test_chunks_without_extracts_is_rejected():
    """A chunked-but-not-extracted config would silently ingest empty bodies."""
    with pytest.raises(ValueError, match="requires extracts_body_content"):
        EntityIngestionConfig(
            entity_label="Broken",
            uid_prefix="broken",
            chunks_body_content=True,
        )


# ---------------------------------------------------------------------------
# get_with_content — inline-first, :Content-node fallback
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Entity:
    uid: str
    content: str | None = None


@dataclass
class _Backend:
    """Fake backend recording get_content consultations."""

    body: str | None = None
    calls: list[str] = field(default_factory=list)

    async def get_content(self, uid: str) -> Result[str | None]:
        self.calls.append(uid)
        return Result.ok(self.body)


class _Host(ContextOperationsMixin):
    _content_field = "content"
    _dto_class = None
    _model_class = None
    _prerequisite_relationships: tuple[RelationshipName, ...] = ()

    def __init__(self, entity: _Entity, backend: _Backend) -> None:
        self._entity = entity
        self.backend = backend
        self.logger = logging.getLogger("test.get_with_content")

    @property
    def entity_label(self) -> str:
        return "Entity"

    @property
    def config_lookup_label(self) -> str:
        return "Ku"

    async def get(self, uid: str) -> Result[_Entity | None]:
        return Result.ok(self._entity)


@pytest.mark.asyncio
async def test_inline_content_wins_without_backend_roundtrip():
    backend = _Backend(body="should not be read")
    host = _Host(_Entity(uid="ku.x", content="inline body"), backend)

    result = await host.get_with_content("ku.x")

    assert result.is_ok
    _, content = result.value
    assert content == "inline body"
    assert backend.calls == []


@pytest.mark.asyncio
async def test_missing_inline_falls_back_to_content_node():
    """Vault-ingested lesson bodies live on :Content — the fallback reads them."""
    backend = _Backend(body="## Lesson body from :Content")
    host = _Host(_Entity(uid="ku.discipline.regret"), backend)

    result = await host.get_with_content("ku.discipline.regret")

    assert result.is_ok
    _, content = result.value
    assert content == "## Lesson body from :Content"
    assert backend.calls == ["ku.discipline.regret"]


@pytest.mark.asyncio
async def test_reference_only_entity_returns_none_content():
    backend = _Backend(body=None)
    host = _Host(_Entity(uid="ku.values.stories"), backend)

    result = await host.get_with_content("ku.values.stories")

    assert result.is_ok
    entity, content = result.value
    assert entity.uid == "ku.values.stories"
    assert content is None


@dataclass
class _FailingBackend:
    async def get_content(self, uid: str) -> Result[str | None]:
        return Result.fail(Errors.database(operation="get_content", message="neo4j down"))


@pytest.mark.asyncio
async def test_content_read_failure_propagates_not_degrades():
    """A backend read error must fail the Result — never silently render a
    body-less page (Kody finding, PR #535)."""
    host = _Host(_Entity(uid="ku.discipline.regret"), _FailingBackend())

    result = await host.get_with_content("ku.discipline.regret")

    assert result.is_error
