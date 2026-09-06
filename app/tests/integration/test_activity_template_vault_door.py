"""
Integration: the Activity Template vault door, driven against a real Neo4j.

The unit tests pin the configuration; this pins the behaviour the configuration
is for. A vault holding one template file per kind plus a PathStep that attaches
all six must produce, after one directory sync:

- six ``:Entity:<Kind>Template`` nodes carrying ``status: active`` (the value
  ``PsEngagementService`` requires before it will spawn anything from them), and
- six ``HAS_*_TEMPLATE`` edges from the PathStep, each landing on the right
  label — the edges ``ps_engagement/_template_loader`` walks at spawn time.

Also pinned here, because neither is visible to a config assertion:

- an authored ``due_offset: {days: 7}`` survives the round trip as a
  RelativeOffset — the property reaches Neo4j as a JSON string, not a map;
- ``event_uids`` and ``event_template_uids`` are two channels, and each lands
  on the label its name says (the naming hazard the held rename closed);
- a dropped ``task_template_uids`` target loses its edge on the next sync, so
  attachment is retractable like every other frontmatter-authored edge.

Requires: Docker running with Neo4j testcontainer.

See: /docs/roadmap/activity-templates-vault-door.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.ingestion_backend import IngestionBackend
from adapters.persistence.neo4j.ingestion_service_factory import make_unified_ingestion_service
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.templates.offset_helpers import jsonable_to_offset
from core.models.templates.relative_offset import RelativeOffset
from core.services.ingestion.config import DEFAULT_USER_UID
from core.services.ingestion.types import IncrementalStats

_MARK = "zzztmpl"
_PS = f"ps.{_MARK}.host"
_EVENT = f"event.{_MARK}.instance"

# (type value, uid prefix, Neo4j label, the PS frontmatter field that attaches it,
#  the edge that field authors)
_KINDS: tuple[tuple[str, str, str, str, str], ...] = (
    ("task_template", "tt", "TaskTemplate", "task_template_uids", "HAS_TASK_TEMPLATE"),
    ("goal_template", "gt", "GoalTemplate", "goal_template_uids", "HAS_GOAL_TEMPLATE"),
    ("habit_template", "ht", "HabitTemplate", "habit_template_uids", "HAS_HABIT_TEMPLATE"),
    ("event_template", "et", "EventTemplate", "event_template_uids", "HAS_EVENT_TEMPLATE"),
    ("choice_template", "ct", "ChoiceTemplate", "choice_template_uids", "HAS_CHOICE_TEMPLATE"),
    (
        "principle_template",
        "pt",
        "PrincipleTemplate",
        "principle_template_uids",
        "HAS_PRINCIPLE_TEMPLATE",
    ),
)


def _template_uid(prefix: str) -> str:
    return f"{prefix}.{_MARK}.one"


def _template_file(vault: Path, type_value: str, prefix: str, *, extra: str = "") -> Path:
    path = vault / f"{prefix}_{_MARK}_tmpl.md"
    path.write_text(
        "---\n"
        f"type: {type_value}\n"
        f"uid: {_template_uid(prefix)}\n"
        f"title: Template {type_value}\n"
        f"{extra}"
        "---\n"
        "Body.\n"
    )
    return path


def _event_file(vault: Path) -> Path:
    path = vault / f"{_MARK}_event.md"
    path.write_text(f"---\ntype: event\nuid: {_EVENT}\ntitle: Instance Event\n---\nBody.\n")
    return path


def _ps_file(
    vault: Path,
    *,
    attach: dict[str, list[str]] | None = None,
    event_uids: list[str] | None = None,
) -> Path:
    lines = ["type: ps", f"uid: {_PS}", "title: Template Host"]
    for field, values in (attach or {}).items():
        lines.append(f"{field}:")
        lines.extend(f"  - {value}" for value in values)
    if event_uids is not None:
        lines.append("event_uids:")
        lines.extend(f"  - {value}" for value in event_uids)
    path = vault / f"{_MARK}_host_Ps.md"
    path.write_text("---\n" + "\n".join(lines) + "\n---\nBody.\n")
    return path


def _full_vault(vault: Path) -> None:
    """One template file per kind, an Event instance, and a PS attaching them all."""
    for type_value, prefix, _label, _field, _edge in _KINDS:
        extra = "due_offset:\n  days: 7\n" if type_value == "task_template" else ""
        _template_file(vault, type_value, prefix, extra=extra)
    _event_file(vault)
    _ps_file(
        vault,
        attach={field: [_template_uid(prefix)] for _t, prefix, _l, field, _e in _KINDS},
        event_uids=[_EVENT],
    )


async def _node(neo4j_driver, uid: str) -> dict[str, Any] | None:
    async with neo4j_driver.session() as session:
        res = await session.run(
            "MATCH (n {uid: $uid}) RETURN properties(n) AS props, labels(n) AS labels",
            {"uid": uid},
        )
        record = await res.single()
        return dict(record) if record else None


async def _edge_target_labels(neo4j_driver, from_uid: str, rel: str) -> list[list[str]]:
    async with neo4j_driver.session() as session:
        res = await session.run(
            f"MATCH (a {{uid: $f}})-[:{rel}]->(b) RETURN labels(b) AS labels",
            {"f": from_uid},
        )
        return [list(record["labels"]) async for record in res]


async def _sync(service, vault: Path, **kwargs: Any) -> IncrementalStats:
    result = await service.ingest_directory(vault, ingestion_mode="smart", **kwargs)
    assert result.is_ok, f"sync failed: {result}"
    stats = cast("IncrementalStats", result.value)
    assert not stats.errors, f"sync errors: {stats.errors}"
    return stats


@pytest_asyncio.fixture
async def template_service(neo4j_driver):
    executor = Neo4jQueryExecutor(neo4j_driver)
    service = make_unified_ingestion_service(
        driver=neo4j_driver,
        ingestion_backend=IngestionBackend(executor=executor),
    )
    # The Event INSTANCE in the vault is user-owned, and the ingest door refuses
    # a batch naming an owner with no :User node (ADR-086). Templates themselves
    # are PS-owned and need none.
    async with neo4j_driver.session() as session:
        await session.run("MERGE (u:User {uid: $uid})", {"uid": str(DEFAULT_USER_UID)})
    yield service
    # Session-scoped container — remove this module's nodes + tracker rows.
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n:Entity) WHERE n.uid CONTAINS $mark DETACH DELETE n", {"mark": _MARK}
        )
        await session.run(
            "MATCH (s:IngestionMetadata) WHERE s.entity_uid CONTAINS $mark DELETE s",
            {"mark": _MARK},
        )


@pytest.mark.integration
class TestActivityTemplateVaultDoor:
    async def test_every_kind_ingests_with_the_labels_engagement_reads(
        self, template_service, neo4j_driver, tmp_path: Path
    ):
        vault = tmp_path / "vault"
        vault.mkdir()
        _full_vault(vault)
        await _sync(template_service, vault)

        for type_value, prefix, label, _field, _edge in _KINDS:
            node = await _node(neo4j_driver, _template_uid(prefix))
            assert node is not None, f"{type_value} did not ingest"
            assert set(node["labels"]) == {"Entity", label}
            assert node["props"]["entity_type"] == type_value

    async def test_absent_status_lands_as_active_so_engagement_can_spawn(
        self, template_service, neo4j_driver, tmp_path: Path
    ):
        """No file declares ``status:``. PsEngagementService refuses a non-ACTIVE
        template, so an unstamped node would make every vault template inert."""
        vault = tmp_path / "vault"
        vault.mkdir()
        _full_vault(vault)
        await _sync(template_service, vault)

        for _t, prefix, _label, _field, _edge in _KINDS:
            node = await _node(neo4j_driver, _template_uid(prefix))
            assert node is not None
            assert node["props"]["status"] == "active"

    async def test_pathstep_attaches_all_six_at_the_right_label(
        self, template_service, neo4j_driver, tmp_path: Path
    ):
        vault = tmp_path / "vault"
        vault.mkdir()
        _full_vault(vault)
        await _sync(template_service, vault)

        for _t, _prefix, label, _field, edge in _KINDS:
            targets = await _edge_target_labels(neo4j_driver, _PS, edge)
            assert len(targets) == 1, f"{edge} should attach exactly one template"
            assert label in targets[0]

    async def test_event_instance_and_event_template_are_two_channels(
        self, template_service, neo4j_driver, tmp_path: Path
    ):
        """``event_uids`` reaches an :Event; ``event_template_uids`` an
        :EventTemplate. Before the held rename executed, one name served both
        and a uid followed from it matched nothing."""
        vault = tmp_path / "vault"
        vault.mkdir()
        _full_vault(vault)
        await _sync(template_service, vault)

        scheduled = await _edge_target_labels(neo4j_driver, _PS, "SCHEDULES_EVENT")
        assert len(scheduled) == 1
        assert "Event" in scheduled[0]
        assert "EventTemplate" not in scheduled[0]

        templated = await _edge_target_labels(neo4j_driver, _PS, "HAS_EVENT_TEMPLATE")
        assert len(templated) == 1
        assert "EventTemplate" in templated[0]

    async def test_authored_offset_round_trips_as_a_relative_offset(
        self, template_service, neo4j_driver, tmp_path: Path
    ):
        """A nested map cannot be a Neo4j property — it must land as JSON the
        reader can rebuild, in the same shape the DTO write path stores."""
        vault = tmp_path / "vault"
        vault.mkdir()
        _full_vault(vault)
        await _sync(template_service, vault)

        node = await _node(neo4j_driver, _template_uid("tt"))
        assert node is not None
        stored = node["props"]["due_offset"]
        assert isinstance(stored, str), "an offset must persist as JSON, not a map"
        assert jsonable_to_offset(stored) == RelativeOffset(days=7)

    async def test_dropped_attachment_loses_its_edge_on_the_next_sync(
        self, template_service, neo4j_driver, tmp_path: Path
    ):
        vault = tmp_path / "vault"
        vault.mkdir()
        _full_vault(vault)
        await _sync(template_service, vault)
        assert await _edge_target_labels(neo4j_driver, _PS, "HAS_TASK_TEMPLATE")

        attach = {field: [_template_uid(prefix)] for _t, prefix, _l, field, _e in _KINDS}
        del attach["task_template_uids"]
        _ps_file(vault, attach=attach, event_uids=[_EVENT])
        await _sync(template_service, vault)

        assert not await _edge_target_labels(neo4j_driver, _PS, "HAS_TASK_TEMPLATE"), (
            "a template dropped from the PS frontmatter must lose its attachment"
        )
        assert await _edge_target_labels(neo4j_driver, _PS, "HAS_GOAL_TEMPLATE"), (
            "the attachments still declared must survive"
        )

    async def test_unparseable_offset_is_reported_not_persisted(
        self, template_service, neo4j_driver, tmp_path: Path
    ):
        """``{day: 7}`` would rebuild as a ZERO offset — the spawned task would be
        due today and the write would report success. It must be refused instead."""
        vault = tmp_path / "vault"
        vault.mkdir()
        _template_file(vault, "task_template", "tt", extra="due_offset:\n  day: 7\n")

        result = await template_service.ingest_directory(vault, ingestion_mode="smart")
        assert result.is_ok
        stats = cast("IncrementalStats", result.value)
        assert stats.files_ingested == 0

        assert await _node(neo4j_driver, _template_uid("tt")) is None
