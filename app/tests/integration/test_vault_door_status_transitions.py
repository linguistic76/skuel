"""
The vault door honours ADR-087's status contract (arc PR-3).
=============================================================

The bulk upsert ``MERGE``s rather than going through
``update_with_status_guard``, so the primitive's three jobs were all skipped at
the ingest doors: no completion event, no reopen-clear, and no way to tell a
genuine transition from a re-ingest. The node template now reads each node's
prior status between the ``MERGE`` and the property write — under the node's
write-lock, which is the point — and the post-persist step acts on it.

These tests drive the REAL doors (``ingest_file`` and ``ingest_directory``)
against a real graph, because the post-persist seam is exactly where the wiring
can be absent and still look correct from a hand-built backend call.

Pinned:

- a file that arrives ``completed`` publishes one completion event carrying its
  authored ``✅`` date as ``occurred_at``;
- re-ingesting it — including under ``--force``, which re-processes unchanged
  files — publishes ZERO. Without prior-status honesty the feature would be
  worse than the gap it closes;
- a file edited ``completed`` → ``in_progress`` has its completion stamp
  removed and publishes nothing;
- both doors behave identically;
- Habit gets the reopen-clear and no event.

Requires: Docker running with Neo4j testcontainer.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from core.events import CalendarEventCompleted, GoalAchieved, TaskCompleted

OWNER_UID = "user_test_integration"  # seeded by the ensure_test_users fixture


class _CapturingBus:
    """Records every published event; the ingestion service only publishes.

    ``edge_probe`` lets a test observe the graph AT THE MOMENT of publication —
    the real bus awaits its subscribers inline, so what the graph holds here is
    exactly what a subscriber would see.
    """

    def __init__(self) -> None:
        self.published: list[Any] = []
        self.probes: list[Any] = []
        self.edge_probe: Any = None

    async def publish_async(self, event: Any) -> None:
        self.published.append(event)
        if self.edge_probe is not None:
            self.probes.append((type(event).__name__, await self.edge_probe()))

    def completions(self, event_class: type) -> list[Any]:
        return [e for e in self.published if isinstance(e, event_class)]


@pytest.fixture
def bus() -> _CapturingBus:
    return _CapturingBus()


@pytest.fixture
def door(neo4j_driver, bus: _CapturingBus):
    """A real ingestion service with a capturing bus (FULL-tier shape).

    The tracker is wired because the tracked ingestion modes — and ``force``,
    which only has meaning under tracking — are where the re-ingest pins live.
    """
    from adapters.persistence.neo4j.ingestion_backend import IngestionBackend
    from adapters.persistence.neo4j.ingestion_service_factory import (
        make_unified_ingestion_service,
    )
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

    return make_unified_ingestion_service(
        driver=neo4j_driver,
        event_bus=bus,
        ingestion_backend=IngestionBackend(executor=Neo4jQueryExecutor(neo4j_driver)),
    )


def _write(directory: Path, slug: str, frontmatter: str, entity_type: str = "task") -> Path:
    path = directory / f"{slug}.md"
    path.write_text(
        f"---\ntype: {entity_type}\nuid: {entity_type}.{slug}\n"
        f"title: {slug}\nuser_uid: {OWNER_UID}\n{frontmatter}---\n\nBody of {slug}.\n"
    )
    return path


async def _prop(neo4j_driver, uid: str, prop: str) -> Any:
    async with neo4j_driver.session() as session:
        result = await session.run(
            f"MATCH (n:Entity {{uid: $uid}}) RETURN n.{prop} AS value", {"uid": uid}
        )
        record = await result.single()
        return record["value"] if record else None


# ---------------------------------------------------------------------------
# the single-file door
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_arriving_completed_publishes_once(
    clean_neo4j, neo4j_driver, door, bus: _CapturingBus, tmp_path: Path
) -> None:
    """The gap this arc closes: a vault-authored completed task cascades."""
    path = _write(tmp_path, "vault-status-born", "status: completed\ncompletion_date: 2026-03-04\n")

    assert (await door.ingest_file(path)).is_ok

    (event,) = bus.completions(TaskCompleted)
    assert event.task_uid == "task.vault-status-born"
    assert event.user_uid == OWNER_UID
    assert event.is_repeat is False
    # The authored ✅ date, not the ingest moment
    assert event.occurred_at == datetime(2026, 3, 4, 0, 0)


@pytest.mark.asyncio
async def test_reingesting_the_same_completed_file_is_silent(
    clean_neo4j, neo4j_driver, door, bus: _CapturingBus, tmp_path: Path
) -> None:
    """Prior status is read under the write-lock, so a repeat is not a transition."""
    path = _write(
        tmp_path, "vault-status-repeat", "status: completed\ncompletion_date: 2026-03-04\n"
    )

    assert (await door.ingest_file(path)).is_ok
    assert len(bus.completions(TaskCompleted)) == 1

    assert (await door.ingest_file(path)).is_ok
    assert len(bus.completions(TaskCompleted)) == 1, "a re-ingest must not re-announce"


@pytest.mark.asyncio
async def test_editing_a_file_out_of_completed_clears_the_stamp(
    clean_neo4j, neo4j_driver, door, bus: _CapturingBus, tmp_path: Path
) -> None:
    """The reopen half: the stamp is non-null exactly when the entity is completed."""
    _write(tmp_path, "vault-status-reopen", "status: completed\ncompletion_date: 2026-03-04\n")
    path = tmp_path / "vault-status-reopen.md"
    assert (await door.ingest_file(path)).is_ok
    assert await _prop(neo4j_driver, "task.vault-status-reopen", "completion_date") is not None

    _write(tmp_path, "vault-status-reopen", "status: in_progress\n")
    assert (await door.ingest_file(path)).is_ok

    assert await _prop(neo4j_driver, "task.vault-status-reopen", "completion_date") is None
    assert len(bus.completions(TaskCompleted)) == 1, "a reopen publishes no completion"


@pytest.mark.asyncio
async def test_reopen_clears_a_stamp_the_file_still_carries(
    clean_neo4j, neo4j_driver, door, bus: _CapturingBus, tmp_path: Path
) -> None:
    """A stale ``completion_date:`` left in the frontmatter must not survive the reopen.

    The upsert's ``n += props`` re-writes whatever the file declares, so the
    clear has to run after the property write, not instead of it.
    """
    _write(tmp_path, "vault-status-stale", "status: completed\ncompletion_date: 2026-03-04\n")
    path = tmp_path / "vault-status-stale.md"
    assert (await door.ingest_file(path)).is_ok

    _write(tmp_path, "vault-status-stale", "status: in_progress\ncompletion_date: 2026-03-04\n")
    assert (await door.ingest_file(path)).is_ok

    assert await _prop(neo4j_driver, "task.vault-status-stale", "completion_date") is None


@pytest.mark.asyncio
async def test_a_file_that_is_not_completed_publishes_nothing(
    clean_neo4j, neo4j_driver, door, bus: _CapturingBus, tmp_path: Path
) -> None:
    path = _write(tmp_path, "vault-status-open", "status: in_progress\n")

    assert (await door.ingest_file(path)).is_ok

    assert bus.completions(TaskCompleted) == []


@pytest.mark.asyncio
async def test_the_create_marker_never_reaches_the_graph(
    clean_neo4j, neo4j_driver, door, tmp_path: Path
) -> None:
    """Reading the prior status needs MERGE's create/match signal as a property.

    It is removed in the same transaction and must never be committed — a
    surviving ``_ingest_new`` would become a node property on every ingested
    entity, and the flag would then read as a constant on the next sync.
    Checked on both branches: the create (where ``SET n = props`` drops it) and
    the match (where the explicit ``REMOVE`` does).
    """
    path = _write(tmp_path, "vault-status-marker", "status: in_progress\n")

    assert (await door.ingest_file(path)).is_ok
    assert await _prop(neo4j_driver, "task.vault-status-marker", "_ingest_new") is None

    assert (await door.ingest_file(path)).is_ok
    assert await _prop(neo4j_driver, "task.vault-status-marker", "_ingest_new") is None


# ---------------------------------------------------------------------------
# the directory door — including --force
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_force_reingest_of_completed_files_publishes_zero(
    clean_neo4j, neo4j_driver, door, bus: _CapturingBus, tmp_path: Path
) -> None:
    """The pin that matters most: ``--force`` re-processes unchanged files.

    Without a real prior status every forced sync would re-announce the entire
    vault's completion history to goal progress, PS engagement auto-complete and
    the productivity stamps.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    for index in range(3):
        _write(
            vault,
            f"vault-status-force-{index}",
            f"status: completed\ncompletion_date: 2026-03-0{index + 1}\n",
        )

    assert (await door.ingest_directory(vault, ingestion_mode="incremental")).is_ok
    assert len(bus.completions(TaskCompleted)) == 3

    forced = await door.ingest_directory(vault, ingestion_mode="incremental", force=True)
    assert forced.is_ok
    assert len(bus.completions(TaskCompleted)) == 3, "--force must not re-announce completions"


@pytest.mark.asyncio
async def test_directory_door_publishes_a_goal_achievement(
    clean_neo4j, neo4j_driver, door, bus: _CapturingBus, tmp_path: Path
) -> None:
    """Goal is the second of the three domains with an entity-completion event."""
    vault = tmp_path / "vault"
    vault.mkdir()
    _write(
        vault,
        "vault-status-goal",
        "status: completed\nachieved_date: 2026-03-04\ncreated_at: '2026-01-01T00:00:00'\n",
        entity_type="goal",
    )

    assert (await door.ingest_directory(vault)).is_ok

    (event,) = bus.completions(GoalAchieved)
    assert event.goal_uid == "goal.vault-status-goal"
    assert event.occurred_at == datetime(2026, 3, 4, 0, 0)
    assert event.actual_duration_days == 62


@pytest.mark.asyncio
async def test_completion_publishes_only_after_the_entity_edges_exist(
    clean_neo4j, neo4j_driver, door, bus: _CapturingBus, tmp_path: Path
) -> None:
    """The ordering rule: a completion event is published AFTER every edge this
    sync writes (Codex #1290 P1).

    The bus awaits its subscribers inline, and those subscribers traverse the
    entity's edges — ``PsPracticeService.handle_event_completed`` follows
    ``APPLIES_KNOWLEDGE`` to count KU practice. The directory door writes nodes
    in phase 1 and edges in phase 2, so publishing inside phase 1 would hand
    every subscriber an entity with no edges, they would find nothing and skip,
    and nothing would repair it: the next sync reads the node as already
    completed and publishes no event at all.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "vault-status-ku.md").write_text(
        "---\ntype: ku\nuid: ku.vault-status-edge\ntitle: Edge KU\n---\n\nBody.\n"
    )
    _write(
        vault,
        "vault-status-edges",
        "status: completed\ncompleted_at: '2026-03-04T09:00:00'\n"
        "connections:\n  applies_knowledge:\n    - ku.vault-status-edge\n",
        entity_type="event",
    )

    async def probe_edges() -> int:
        async with neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (:Entity {uid: 'event.vault-status-edges'})"
                "-[r:APPLIES_KNOWLEDGE]->(:Entity {uid: 'ku.vault-status-edge'}) "
                "RETURN count(r) AS edges"
            )
            record = await result.single()
            return int(record["edges"]) if record else 0

    bus.edge_probe = probe_edges
    assert (await door.ingest_directory(vault)).is_ok

    (event,) = bus.completions(CalendarEventCompleted)
    assert event.event_uid == "event.vault-status-edges"
    completion_probes = [edges for name, edges in bus.probes if name == "CalendarEventCompleted"]
    assert completion_probes == [1], (
        "the APPLIES_KNOWLEDGE edge must already exist when the completion "
        f"event publishes, got {completion_probes}"
    )


@pytest.mark.asyncio
async def test_single_file_door_publishes_after_its_edges_too(
    clean_neo4j, neo4j_driver, door, bus: _CapturingBus, tmp_path: Path
) -> None:
    """Same rule at the other door, which writes edges inside its own upsert call."""
    (tmp_path / "vault-status-ku-single.md").write_text(
        "---\ntype: ku\nuid: ku.vault-status-edge-single\ntitle: Edge KU\n---\n\nBody.\n"
    )
    assert (await door.ingest_file(tmp_path / "vault-status-ku-single.md")).is_ok

    path = _write(
        tmp_path,
        "vault-status-edges-single",
        "status: completed\ncompleted_at: '2026-03-04T09:00:00'\n"
        "connections:\n  applies_knowledge:\n    - ku.vault-status-edge-single\n",
        entity_type="event",
    )

    async def probe_edges() -> int:
        async with neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (:Entity {uid: 'event.vault-status-edges-single'})"
                "-[r:APPLIES_KNOWLEDGE]->(:Entity {uid: 'ku.vault-status-edge-single'}) "
                "RETURN count(r) AS edges"
            )
            record = await result.single()
            return int(record["edges"]) if record else 0

    bus.edge_probe = probe_edges
    assert (await door.ingest_file(path)).is_ok

    completion_probes = [edges for name, edges in bus.probes if name == "CalendarEventCompleted"]
    assert completion_probes == [1]


@pytest.mark.asyncio
async def test_an_emptied_status_line_is_a_reopen(
    clean_neo4j, neo4j_driver, door, bus: _CapturingBus, tmp_path: Path
) -> None:
    """``status:`` with no value ERASES the stored status (Codex #1290 P2).

    The ingest validator admits an empty ``status:`` as absence, and the
    upsert's ``SET n += props`` deletes a property whose new value is null. The
    entity is then definitively not completed, so its stamp must go — an absent
    ``status`` KEY (which writes nothing) is the case that must stay silent, and
    the two are distinguished by key presence, not by value.
    """
    _write(tmp_path, "vault-status-erased", "status: completed\ncompletion_date: 2026-03-04\n")
    path = tmp_path / "vault-status-erased.md"
    assert (await door.ingest_file(path)).is_ok
    assert await _prop(neo4j_driver, "task.vault-status-erased", "completion_date") is not None

    _write(tmp_path, "vault-status-erased", "status:\n")
    assert (await door.ingest_file(path)).is_ok

    assert await _prop(neo4j_driver, "task.vault-status-erased", "status") is None, (
        "precondition: a null status property is removed by `n += props`"
    )
    assert await _prop(neo4j_driver, "task.vault-status-erased", "completion_date") is None
    assert len(bus.completions(TaskCompleted)) == 1


@pytest.mark.asyncio
async def test_a_file_that_declares_no_status_leaves_the_stamp_alone(
    clean_neo4j, neo4j_driver, door, bus: _CapturingBus, tmp_path: Path
) -> None:
    """The other side of the presence test: no ``status`` key writes no status.

    The stored ``completed`` survives untouched, so there is no reopen and the
    stamp must stay — clearing it here would break the same invariant from the
    opposite direction.
    """
    _write(tmp_path, "vault-status-silent", "status: completed\ncompletion_date: 2026-03-04\n")
    path = tmp_path / "vault-status-silent.md"
    assert (await door.ingest_file(path)).is_ok

    _write(tmp_path, "vault-status-silent", "description: no status line here\n")
    assert (await door.ingest_file(path)).is_ok

    assert await _prop(neo4j_driver, "task.vault-status-silent", "status") == "completed"
    assert await _prop(neo4j_driver, "task.vault-status-silent", "completion_date") is not None


@pytest.mark.asyncio
async def test_habit_reopen_clears_without_an_event(
    clean_neo4j, neo4j_driver, door, bus: _CapturingBus, tmp_path: Path
) -> None:
    """Habit has a completion field but no entity-completion event (see the case file)."""
    vault = tmp_path / "vault"
    vault.mkdir()
    _write(
        vault,
        "vault-status-habit",
        "status: completed\ncompleted_at: '2026-03-04T09:00:00'\n",
        entity_type="habit",
    )
    assert (await door.ingest_directory(vault, ingestion_mode="incremental")).is_ok
    assert await _prop(neo4j_driver, "habit.vault-status-habit", "completed_at") is not None
    published_before = list(bus.published)

    _write(vault, "vault-status-habit", "status: active\n", entity_type="habit")
    assert (await door.ingest_directory(vault, ingestion_mode="incremental")).is_ok

    assert await _prop(neo4j_driver, "habit.vault-status-habit", "completed_at") is None
    assert len(bus.published) == len(published_before) + 1, (
        "only the embedding request — a habit reopen announces no completion event"
    )
