"""The plan behind ``scripts/migrations/periodic_note_uids_2026_10.py``, over fixture rows.

Every note in the old shape gets ``periodic_note_uid`` of its kind, owner and
period, gains the period key its old uid carried, and its tracker row follows it;
a graph already in the new shape plans nothing; anything the rename cannot account
for is a stop, and a plan with a stop writes nothing.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any

from core.models.user_entry.user_entry import periodic_note_uid

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/migrations/periodic_note_uids_2026_10.py"


def _load() -> ModuleType:
    """Import the script by path (``scripts/`` is not a package)."""
    spec = importlib.util.spec_from_file_location("periodic_note_uids_2026_10", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


migration = _load()

OWNER = "user_a"
OLD = f"ue:daily:{OWNER}:2026-06-16"
NEW = periodic_note_uid("daily", OWNER, "2026-06-16")
VAULT_FILE = "/vault/periodic_notes/Daily/2026-06-16.md"


def _note(
    uid: str,
    metadata: dict[str, Any] | None = None,
    *,
    labels: tuple[str, ...] = ("Entity", "UserEntry"),
    user_uid: str = OWNER,
    owners: tuple[str, ...] = (OWNER,),
    subtree: bool = False,
    embedded: bool = False,
) -> Any:
    return {
        "uid": uid,
        "labels": list(labels),
        "user_uid": user_uid,
        "metadata": None if metadata is None else json.dumps(metadata),
        "owners": list(owners),
        "embedded": embedded,
        "subtree": subtree,
    }


def _vault_note(uid: str = OLD, *, embedded: bool = False, **metadata: Any) -> Any:
    return _note(
        uid, {"entry_kind": "daily", "vault_file_path": VAULT_FILE, **metadata}, embedded=embedded
    )


def _stub(uid: str = OLD, period: str = "2026-06-16") -> Any:
    return _note(uid, {"entry_kind": "daily", "period_key": period})


def _row(entity_uid: str, path: str = VAULT_FILE) -> Any:
    return {"path": path, "entity_uid": entity_uid}


def _plan(
    notes: list[Any], tracker: list[Any] | None = None, elsewhere: tuple[str, ...] = ()
) -> Any:
    """Plan ``notes`` and ``tracker``; the graph's uids are the notes' plus ``elsewhere``."""
    plan = migration.Plan()
    planned = migration.plan_notes(notes, plan)
    migration.plan_tracker(tracker or [], planned, plan)
    migration.plan_collisions(plan, Counter([n["uid"] for n in notes] + list(elsewhere)))
    return plan


def test_a_vault_note_is_renamed_gains_its_period_and_its_tracker_row_follows() -> None:
    plan = _plan([_vault_note(embedded=True)], [_row(OLD)])
    assert plan.stops == []
    [rename] = plan.renames
    assert (rename.old, rename.new) == (OLD, NEW)
    assert json.loads(rename.metadata_after) == {
        "entry_kind": "daily",
        "vault_file_path": VAULT_FILE,
        "period_key": "2026-06-16",
    }
    assert plan.repoints == [migration.Repoint(path=VAULT_FILE, old=OLD, new=NEW)]
    assert (plan.periodic, plan.embedded) == (1, 1)


def test_an_in_app_note_keeps_its_metadata_and_has_no_tracker_row() -> None:
    plan = _plan([_stub()])
    assert plan.stops == [] and plan.repoints == []
    [rename] = plan.renames
    assert rename.new == NEW
    assert rename.metadata_after == rename.metadata_before


def test_every_kind_takes_the_uid_its_door_derives() -> None:
    notes = [
        _note(f"ue:{kind}:{OWNER}:{period}", {"entry_kind": kind})
        for kind, period in [
            ("weekly", "2026-W25"),
            ("monthly", "2026-06"),
            ("quarterly", "2026-Q2"),
            ("yearly", "2026"),
        ]
    ]
    plan = _plan(notes)
    assert plan.stops == []
    assert [r.new for r in plan.renames] == [
        periodic_note_uid("weekly", OWNER, "2026-W25"),
        periodic_note_uid("monthly", OWNER, "2026-06"),
        periodic_note_uid("quarterly", OWNER, "2026-Q2"),
        periodic_note_uid("yearly", OWNER, "2026"),
    ]


def test_the_migrated_graph_plans_nothing_and_holds() -> None:
    """The state the run leaves: read again, it plans no write and stops on nothing."""
    plan = _plan(
        [
            _vault_note(NEW, period_key="2026-06-16"),
            _stub(periodic_note_uid("daily", OWNER, "2026-06-17"), "2026-06-17"),
        ],
        [_row(NEW)],
    )
    assert plan.stops == [] and plan.writes == 0
    assert (plan.periodic, plan.at_derived_uid) == (2, 2)


def test_an_authored_periodic_note_is_left_on_its_uid() -> None:
    plan = _plan([_note("ue.my-week", {"entry_kind": "weekly", "period_key": "2026-W43"})])
    assert plan.stops == [] and plan.writes == 0
    assert plan.authored == 1


def test_a_vault_note_without_a_period_is_not_a_derived_note() -> None:
    """A note whose frontmatter names no period sits on a minted uid by design."""
    plan = _plan([_note("ue_aa11bb22", {"entry_kind": "daily", "vault_file_path": VAULT_FILE})])
    assert plan.stops == [] and plan.writes == 0
    assert plan.periodic == 1


def test_a_note_off_its_derived_uid_is_a_stop() -> None:
    plan = _plan([_stub("ue_0123456789abcdef")])
    assert len(plan.stops) == 1 and f"not at its uid {NEW}" in plan.stops[0]


def test_every_old_note_the_rename_cannot_account_for_is_a_stop() -> None:
    plan = _plan(
        [
            _stub(f"ue:daily:{OWNER}:2026-06-01", "2026-06-01") | {"labels": ["Entity", "Task"]},
            _stub(f"ue:daily:{OWNER}:2026-06-02", "2026-06-02") | {"user_uid": "user_b"},
            _stub(f"ue:daily:{OWNER}:2026-06-03", "2026-06-03") | {"owners": []},
            _stub(f"ue:daily:{OWNER}:2026-06-04", "2026-06-04") | {"owners": [OWNER, "user_b"]},
            _note(f"ue:daily:{OWNER}:2026-06-05", {"entry_kind": "weekly"}),
            _stub(f"ue:daily:{OWNER}:2026-06-06", "2026-06-07"),
            _stub(f"ue:daily:{OWNER}:2026-06-08", "2026-06-08") | {"subtree": True},
            _note(f"ue:daily:{OWNER}:2026-06-09") | {"metadata": "{not json"},
            _note(f"ue:daily:{OWNER}:2026-06-10") | {"metadata": "[1]"},
        ]
    )
    assert len(plan.stops) == 9, plan.stops
    assert plan.renames == []
    assert any("chunk subtree" in stop for stop in plan.stops)


def test_a_ue_colon_uid_outside_the_old_shape_is_a_stop() -> None:
    plan = _plan(
        [
            _note("ue:daily:2026-06-16", {"entry_kind": "daily"}),
            _note(f"ue:hourly:{OWNER}:2026-06-16", {"entry_kind": "daily"}),
        ]
    )
    assert len(plan.stops) == 2
    assert all("outside the shape" in stop for stop in plan.stops)


def test_an_app_note_made_beside_the_old_one_is_a_stop() -> None:
    """Opening the day's note between merge and migration makes a second note at
    the new uid; the run refuses rather than renaming onto it."""
    plan = _plan([_stub(), _stub(NEW)])
    assert f"2 daily notes of {OWNER} for 2026-06-16: {sorted([NEW, OLD])}" in plan.stops
    assert f"{NEW} (for {OLD}) is already held by a node" in plan.stops


def test_a_new_uid_a_node_of_another_label_holds_is_a_stop() -> None:
    plan = _plan([_stub()], elsewhere=(NEW,))
    assert plan.stops == [f"{NEW} (for {OLD}) is already held by a node"]


def test_a_uid_two_nodes_already_hold_is_a_stop() -> None:
    plan = _plan([], elsewhere=("task_x", "task_x"))
    assert plan.stops == ["task_x is already held by 2 nodes"]


def test_two_renames_onto_one_uid_is_a_stop() -> None:
    plan = migration.Plan()
    same = migration.Rename(old="a", new="ue_00", metadata_before="{}", metadata_after="{}")
    plan.renames = [same, same]
    migration.plan_collisions(plan, Counter())
    assert plan.stops == ["2 notes would all become ue_00"]


def test_tracker_rows_and_vault_notes_pair_one_to_one_both_ways() -> None:
    other_file = "/vault/periodic_notes/Daily/elsewhere.md"
    # A row naming an old uid no note holds.
    assert _plan([], [_row(f"ue:daily:{OWNER}:2026-01-01")]).stops == [
        f"tracker row {VAULT_FILE} names ue:daily:{OWNER}:2026-01-01, "
        "which no note it can move holds"
    ]
    # A row from another file than the note's.
    assert any(
        "whose vault file is" in stop
        for stop in _plan([_vault_note()], [_row(OLD), _row(OLD, other_file)]).stops
    )
    # A vault note named by no row.
    assert _plan([_vault_note()], []).stops == [
        f"{VAULT_FILE} (note {NEW}) is named by 0 tracker rows"
    ]
    # A row naming a note no vault file wrote.
    assert any("whose vault file is None" in stop for stop in _plan([_stub()], [_row(OLD)]).stops)


def test_a_row_for_anything_else_is_left_alone() -> None:
    plan = _plan([_vault_note()], [_row(OLD), _row("ue_aa11bb22", "/vault/knowledge/x.md")])
    assert plan.stops == []
    assert [r.old for r in plan.repoints] == [OLD]


def test_every_reference_to_an_old_uid_is_a_stop() -> None:
    plan = migration.Plan()
    migration.plan_references(
        [
            {"holder": "node ue_bb22cc33", "key": "submitted_from_uid"},
            {"holder": "edge ABOUT", "key": "subject_uid"},
        ],
        plan,
    )
    assert plan.stops == [
        "node ue_bb22cc33.submitted_from_uid names an old periodic uid",
        "edge ABOUT.subject_uid names an old periodic uid",
    ]


async def test_a_plan_with_a_stop_writes_nothing() -> None:
    plan = _plan([_stub() | {"subtree": True}])

    class _NoDriver:
        def session(self) -> Any:
            raise AssertionError("a stopped plan must not open a session")

    try:
        await migration.migrate(_NoDriver(), plan)
    except migration.CountMismatchError:
        return
    raise AssertionError("migrate applied a plan with a stop")
