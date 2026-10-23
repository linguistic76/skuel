"""The plan behind ``scripts/migrations/chunk_and_content_uids_2026_10.py``, over fixture rows.

Every chunk in the old shape gets ``chunk_uid`` of its store, parent and index;
a chunk already in the new shape is left alone; anything the rename cannot
account for is a stop, and a plan with a stop writes nothing.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from core.models.ps_content.content_chunks import ChunkStore, chunk_uid

SCRIPT = (
    Path(__file__).resolve().parents[3] / "scripts/migrations/chunk_and_content_uids_2026_10.py"
)


def _load() -> ModuleType:
    """Import the script by path (``scripts/`` is not a package)."""
    spec = importlib.util.spec_from_file_location("chunk_and_content_uids_2026_10", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


migration = _load()
CONTENT, REFERENCE = migration.CHUNK_LABELS


def _row(uid: str | None, parent: str | None, sequence: int | None, embedded: bool = True) -> Any:
    parents = [] if parent is None else [{"parent_uid": parent, "sequence": sequence}]
    return {"uid": uid, "parents": parents, "embedded": embedded}


def _plan(label: Any, rows: list[Any]) -> Any:
    plan = migration.Plan()
    migration.plan_chunks(label, rows, plan)
    return plan


def test_an_old_uid_becomes_the_minted_one_for_its_store() -> None:
    plan = _plan(
        CONTENT, [_row("ps.a.b:chunk:0", "ps.a.b", 0), _row("ps.a.b:chunk:1", "ps.a.b", 1)]
    )
    assert plan.stops == []
    assert [r.new for r in plan.renames["ContentChunk"]] == [
        chunk_uid(ChunkStore.CONTENT, "ps.a.b", 0),
        chunk_uid(ChunkStore.CONTENT, "ps.a.b", 1),
    ]
    assert plan.embedded["ContentChunk"] == 2

    shelf = _plan(REFERENCE, [_row("resource.x:chunk:0", "resource.x", 0)])
    assert [r.new for r in shelf.renames["ReferenceChunk"]] == [
        chunk_uid(ChunkStore.REFERENCE, "resource.x", 0)
    ]


def test_a_chunk_already_in_the_new_shape_is_left_alone() -> None:
    plan = _plan(CONTENT, [_row(chunk_uid(ChunkStore.CONTENT, "ps.a.b", 0), "ps.a.b", 0)])
    assert plan.stops == [] and plan.renames["ContentChunk"] == []
    assert plan.already["ContentChunk"] == 1


def test_a_reference_uid_minted_for_the_body_store_is_a_stop() -> None:
    """The new shape counts only when it is the uid of THIS store."""
    plan = _plan(REFERENCE, [_row(chunk_uid(ChunkStore.CONTENT, "resource.x", 0), "resource.x", 0)])
    assert plan.stops and "neither the old shape" in plan.stops[0]


def test_every_unaccounted_chunk_is_a_stop() -> None:
    plan = _plan(
        CONTENT,
        [
            _row("ps.a.b:chunk:0", None, None),  # no parent
            _row("ps.a.b:chunk:1", "ps.a.c", 1),  # prefix is not its parent
            _row("ps.a.b:chunk:2", "ps.a.b", 5),  # index is not its sequence
            _row("ps.a.b-2", "ps.a.b", 3),  # neither shape
            _row(None, "ps.a.b", 4),  # no uid
        ],
    )
    assert len(plan.stops) == 5
    assert plan.renames["ContentChunk"] == []


def test_two_parents_is_a_stop() -> None:
    row = {
        "uid": "ps.a.b:chunk:0",
        "parents": [
            {"parent_uid": "ps.a.b", "sequence": 0},
            {"parent_uid": "ps.a.c", "sequence": 0},
        ],
        "embedded": True,
    }
    assert _plan(CONTENT, [row]).stops == ["ContentChunk ps.a.b:chunk:0 has 2 parents"]


def test_a_new_uid_another_chunk_holds_is_a_stop() -> None:
    taken = chunk_uid(ChunkStore.CONTENT, "ps.a.b", 0)
    plan = _plan(CONTENT, [_row("ps.a.b:chunk:0", "ps.a.b", 0), _row(taken, "ps.a.z", 9)])
    assert any("already held" in stop for stop in plan.stops)


def test_content_uids_are_cleared_only_where_they_are_their_entitys() -> None:
    plan = migration.Plan()
    migration.plan_content(
        [
            {"uid": "ps.a.b", "holders": ["ps.a.b"]},  # clear
            {"uid": None, "holders": ["ps.a.c"]},  # already clear
            {"uid": "ps.a.d", "holders": ["ps.a.e"]},  # another uid — stop
            {"uid": "ps.a.f", "holders": []},  # held by none — stop
            {"uid": None, "holders": ["ps.a.g", "ps.a.h"]},  # held by two — stop
        ],
        plan,
    )
    assert (plan.content_to_clear, plan.content_clear) == (1, 1)
    assert len(plan.stops) == 3


async def test_a_plan_with_a_stop_writes_nothing() -> None:
    plan = _plan(CONTENT, [_row("ps.a.b:chunk:0", None, None)])

    class _NoDriver:
        def session(self) -> Any:
            raise AssertionError("a stopped plan must not open a session")

    try:
        await migration.migrate(_NoDriver(), plan)
    except migration.CountMismatchError:
        return
    raise AssertionError("migrate applied a plan with a stop")
