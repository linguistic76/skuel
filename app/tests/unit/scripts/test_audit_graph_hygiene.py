"""Categorizer tests for scripts/audit_graph_hygiene.py (Arc C, R4 ruling).

The script itself is an interactive CLI over the live graph; the pure
categorizers are pinned here against fixture rows.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from audit_graph_hygiene import (  # type: ignore[import-not-found]
    DupGroup,
    domain_label,
    expected_types_by_label,
    find_daily_owner_collisions,
    find_type_mismatches,
    group_cross_entry_duplicates,
    group_same_entry_duplicates,
)


class TestExpectedTypes:
    def test_label_map_covers_the_observed_corruption(self):
        m = expected_types_by_label()
        assert m["Habit"] == "habit"
        assert m["Goal"] == "goal"
        assert m["Ku"] == "ku"
        assert m["PathStep"] == "path_step"

    def test_domain_label_ignores_base_and_shadow_labels(self):
        assert domain_label(["Entity", "Habit"]) == "Habit"
        assert domain_label(["Entity", "Content", "PathStep"]) == "PathStep"
        assert domain_label(["Entity"]) is None
        assert domain_label(["Entity", "Habit", "Goal"]) is None


class TestTypeMismatches:
    def test_flags_wrong_type_and_derives_expected_from_label(self):
        rows = [
            {"uid": "habit_bad", "labels": ["Entity", "Habit"], "entity_type": "ku"},
            {"uid": "habit_ok", "labels": ["Entity", "Habit"], "entity_type": "habit"},
            {"uid": "goal_bad", "labels": ["Entity", "Goal"], "entity_type": "ku"},
        ]
        found = find_type_mismatches(rows)
        assert [(f.uid, f.expected) for f in found] == [
            ("habit_bad", "habit"),
            ("goal_bad", "goal"),
        ]

    def test_missing_type_counts_as_mismatch(self):
        rows = [{"uid": "task_null", "labels": ["Entity", "Task"], "entity_type": None}]
        found = find_type_mismatches(rows)
        assert found[0].expected == "task" and found[0].current is None

    def test_multi_label_nodes_are_skipped_not_guessed(self):
        rows = [{"uid": "weird", "labels": ["Entity", "Habit", "Goal"], "entity_type": "ku"}]
        assert find_type_mismatches(rows) == []


def _row(
    uid: str,
    entry: str = "ue:daily:u:2026-06-16",
    label: str = "Habit",
    title: str = "Meditate",
    created: str = "2026-07-02T12:00:00",
    owner: str = "user_a",
    edges: list[str] | None = None,
) -> dict:
    return {
        "uid": uid,
        "entry_uid": entry,
        "labels": ["Entity", label],
        "title": title,
        "created_at": created,
        "owner": owner,
        "edge_sigs": edges if edges is not None else ["EXTRACTED_FROM:out", "OWNS:in"],
    }


class TestSameEntryDuplicates:
    def test_oldest_wins_rest_are_losers(self):
        rows = [
            _row("habit_2", created="2026-07-02T15:00:00"),
            _row("habit_1", created="2026-07-02T12:00:00"),
            _row("habit_3", created="2026-07-02T21:00:00"),
        ]
        groups = group_same_entry_duplicates(rows)
        assert len(groups) == 1
        g = groups[0]
        assert g.winner_uid == "habit_1"
        assert g.loser_uids == ["habit_2", "habit_3"]
        assert g.blockers == []

    def test_title_normalization_groups_rewordings(self):
        rows = [_row("h1", title="Meditate "), _row("h2", title="  meditate")]
        assert len(group_same_entry_duplicates(rows)) == 1

    def test_different_entries_do_not_group(self):
        rows = [
            _row("h1", entry="ue:daily:a:2026-06-16"),
            _row("h2", entry="ue:daily:a:2026-06-17"),
        ]
        assert group_same_entry_duplicates(rows) == []

    def test_unexpected_loser_edge_blocks_the_group(self):
        rows = [
            _row("h1", created="2026-07-02T12:00:00"),
            _row(
                "h2",
                created="2026-07-02T15:00:00",
                edges=["EXTRACTED_FROM:out", "OWNS:in", "HAS_COMPLETION:out"],
            ),
        ]
        groups = group_same_entry_duplicates(rows)
        assert len(groups) == 1
        assert any("HAS_COMPLETION" in b for b in groups[0].blockers)

    def test_owner_mismatch_blocks_the_group(self):
        rows = [_row("h1", owner="user_a"), _row("h2", owner="user_b", created="2026-07-03")]
        groups = group_same_entry_duplicates(rows)
        assert any("owner mismatch" in b for b in groups[0].blockers)


class TestCrossEntryDuplicates:
    def test_same_title_across_entries_is_report_only(self):
        rows = [
            _row("h1", entry="ue_legacy", owner="user_a"),
            _row("h2", entry="ue:daily:user_b:2026-06-16", owner="user_b"),
        ]
        groups = group_cross_entry_duplicates(rows)
        assert len(groups) == 1
        assert isinstance(groups[0], DupGroup)
        assert groups[0].blockers  # always blocked — Arc E's fix

    def test_single_entry_groups_are_not_cross_entry(self):
        rows = [_row("h1"), _row("h2")]
        assert group_cross_entry_duplicates(rows) == []


class TestDailyOwnerCollisions:
    def test_same_date_two_owners_collides(self):
        rows = [
            {"uid": "ue:daily:user_a:2026-06-16", "owner": "user_a"},
            {"uid": "ue:daily:user_b:2026-06-16", "owner": "user_b"},
            {"uid": "ue:daily:user_a:2026-06-17", "owner": "user_a"},
            {"uid": "ue_random", "owner": "user_a"},
        ]
        collisions = find_daily_owner_collisions(rows)
        assert len(collisions) == 1
        assert collisions[0]["date"] == "2026-06-16"
        assert len(collisions[0]["entries"]) == 2
