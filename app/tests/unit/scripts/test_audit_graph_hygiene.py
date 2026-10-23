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
    domain_label,
    expected_types_by_label,
    find_role_value_drift,
    find_type_mismatches,
    group_same_entry_duplicates,
    plan_about_entity_repoints,
    plan_cross_entry_dedup,
    plan_ku_enrollment_migrations,
    plan_test_user_cleanup,
)


class TestExpectedTypes:
    def test_label_map_covers_the_observed_corruption(self):
        m = expected_types_by_label()
        assert m["Habit"] == "habit"
        assert m["Goal"] == "goal"
        assert m["Ku"] == "ku"
        assert m["PathStep"] == "path_step"

    def test_domain_label_ignores_the_base_label(self):
        assert domain_label(["Entity", "Habit"]) == "Habit"
        assert domain_label(["Entity", "Content", "PathStep"]) is None
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
    entry: str = "ue_u0616",
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

    def test_oldest_is_read_by_instant_not_by_digits(self):
        """A ``…Z`` stamp and a fractional offset-less one in the same second:
        their digits sort the later first ('.' before 'Z'); their instants do not."""
        rows = [
            _row("habit_later", created="2026-07-02T12:00:00.500000"),
            _row("habit_older", created="2026-07-02T12:00:00Z"),
        ]
        g = group_same_entry_duplicates(rows)[0]
        assert g.winner_uid == "habit_older"
        assert g.loser_uids == ["habit_later"]

    def test_an_unreadable_stamp_blocks_the_group(self):
        """An unreadable stamp sorts last, yet may be the oldest: no member is
        provably the winner while one cannot be read."""
        rows = [_row("h1", created="2026-07-02T12:00:00Z"), _row("h2", created="early July")]
        g = group_same_entry_duplicates(rows)[0]
        assert "no readable created_at on h2 — the oldest cannot be told" in g.blockers

    def test_title_normalization_groups_rewordings(self):
        rows = [_row("h1", title="Meditate "), _row("h2", title="  meditate")]
        assert len(group_same_entry_duplicates(rows)) == 1

    def test_different_entries_do_not_group(self):
        rows = [
            _row("h1", entry="ue_a0616"),
            _row("h2", entry="ue_a0617"),
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


class TestCrossEntryDedup:
    def test_the_oldest_wins_across_entries(self):
        rows = [
            _row(
                "h1",
                entry="ue_usera0630",
                created="2026-07-01T11:00:00",
            ),
            _row(
                "h2",
                entry="ue_usera0715",
                created="2026-07-01T12:00:00",
            ),
        ]
        groups = plan_cross_entry_dedup(rows)
        assert len(groups) == 1
        g = groups[0]
        assert g.winner_uid == "h1"
        assert g.loser_uids == ["h2"]
        assert g.blockers == []

    def test_the_cross_entry_winner_is_read_by_instant_not_by_digits(self):
        rows = [
            _row("h_later", entry="ue_usera0630", created="2026-07-01T11:00:00.5"),
            _row("h_older", entry="ue_usera0715", created="2026-07-01T11:00:00Z"),
        ]
        g = plan_cross_entry_dedup(rows)[0]
        assert g.winner_uid == "h_older"
        assert g.loser_uids == ["h_later"]

    def test_an_unreadable_stamp_blocks_the_cross_entry_group(self):
        rows = [
            _row("h1", entry="ue_usera0630", created="2026-07-01T11:00:00Z"),
            _row("h2", entry="ue_usera0715", created=""),
        ]
        g = plan_cross_entry_dedup(rows)[0]
        assert "no readable created_at on h2 — the oldest cannot be told" in g.blockers

    def test_single_entry_groups_are_not_cross_entry(self):
        rows = [_row("h1"), _row("h2")]
        assert plan_cross_entry_dedup(rows) == []

    def test_test_user_groups_are_blocked(self):
        rows = [
            _row("h1", entry="ue_usera0630", owner="user_a"),
            _row(
                "h2",
                entry="ue_userverifyperiodic0601",
                owner="user_verifyperiodic",
                created="2026-07-02T00:00:00",
            ),
        ]
        groups = plan_cross_entry_dedup(rows)
        assert len(groups) == 1
        assert any("test user" in b for b in groups[0].blockers)

    def test_unexpected_loser_edges_block_the_group(self):
        rows = [
            _row("h1", entry="ue_usera0630", created="2026-07-01T11:00:00"),
            _row(
                "h2",
                entry="ue_usera0715",
                created="2026-07-01T12:00:00",
                edges=["EXTRACTED_FROM:out", "OWNS:in", "SUPPORTS_GOAL:out"],
            ),
        ]
        groups = plan_cross_entry_dedup(rows)
        assert any("SUPPORTS_GOAL" in b for b in groups[0].blockers)


class TestTestUserCleanup:
    def test_clean_user_with_subtree_is_deletable(self):
        users = [
            {
                "uid": "user_verifyperiodic",
                "email": "v@example.com",
                "edge_sigs": ["OWNS:out", "HAS_SESSION:out", "HAD_AUTH_EVENT:out"],
                "session_count": 2,
                "auth_event_count": 2,
            }
        ]
        owned = [
            {
                "owner": "user_verifyperiodic",
                "uid": "ue_userverifyperiodic0601",
                "labels": ["Entity", "UserEntry"],
                "edge_sigs": ["OWNS:in"],
            }
        ]
        plans = plan_test_user_cleanup(users, owned)
        assert len(plans) == 1 and not plans[0].blockers
        assert plans[0].owned[0]["label"] == "UserEntry"

    def test_unexpected_user_edge_blocks_whole_user(self):
        users = [
            {
                "uid": "user_csrfprobe2",
                "email": "c@test.local",
                "edge_sigs": ["HAS_SESSION:out", "SHARES_WITH:out"],
                "session_count": 1,
                "auth_event_count": 0,
            }
        ]
        plans = plan_test_user_cleanup(users, [])
        assert plans[0].blockers and "SHARES_WITH" in plans[0].blockers[0]


class TestKuEnrollmentMigrations:
    def test_single_covering_ps_is_migratable(self):
        rows = [
            {
                "user_uid": "user_x",
                "ku_uid": "ku.a.b",
                "edge_props": {"progress_score": 0.0},
                "covering_ps": ["ps.a.step-1"],
            }
        ]
        plans = plan_ku_enrollment_migrations(rows)
        assert not plans[0].blockers and plans[0].target_ps == "ps.a.step-1"

    def test_uncovered_and_multi_covered_go_to_dialog(self):
        rows = [
            {"user_uid": "u", "ku_uid": "ku.orphan", "edge_props": {}, "covering_ps": []},
            {
                "user_uid": "u",
                "ku_uid": "ku.shared",
                "edge_props": {},
                "covering_ps": ["ps.one", "ps.two"],
            },
        ]
        plans = plan_ku_enrollment_migrations(rows)
        assert "no covering PathStep" in plans[0].blockers[0]
        assert plans[0].target_ps is None
        assert "multiple covering PathSteps" in plans[1].blockers[0]


class TestAboutEntityRepoints:
    RULED = {"task_dupe": "task_winner"}

    def _row(self, uid, title="move furniture", owner="user_x", edges=None, sources=None):
        return {
            "uid": uid,
            "title": title,
            "owner": owner,
            "labels": ["Entity", "Task"],
            "edge_sigs": edges if edges is not None else ["OWNS:in", "ABOUT_ENTITY:in"],
            "about_sources": sources or [],
        }

    def test_valid_pair_repoints(self):
        rows = [
            self._row("task_dupe", sources=["insight.completion_pattern.x"]),
            self._row("task_winner", edges=["OWNS:in"]),
        ]
        plans = plan_about_entity_repoints(rows, ruled=self.RULED)
        assert not plans[0].blockers
        assert plans[0].label == "Task"
        assert plans[0].sources == ["insight.completion_pattern.x"]

    def test_missing_survivor_or_title_drift_blocks(self):
        no_survivor = plan_about_entity_repoints([self._row("task_dupe")], ruled=self.RULED)
        assert "survivor missing" in no_survivor[0].blockers[0]
        drifted = plan_about_entity_repoints(
            [self._row("task_dupe"), self._row("task_winner", title="something else")],
            ruled=self.RULED,
        )
        assert any("titles no longer match" in b for b in drifted[0].blockers)

    def test_unexpected_dupe_edge_blocks(self):
        rows = [
            self._row("task_dupe", edges=["OWNS:in", "ABOUT_ENTITY:in", "BLOCKS:out"]),
            self._row("task_winner"),
        ]
        plans = plan_about_entity_repoints(rows, ruled=self.RULED)
        assert any("unexpected edges" in b for b in plans[0].blockers)

    def test_already_cleaned_dupe_reports_not_crashes(self):
        plans = plan_about_entity_repoints([self._row("task_winner")], ruled=self.RULED)
        assert "dupe not found" in plans[0].blockers[0]


class TestRoleValueDrift:
    def test_uppercase_enum_name_normalizes(self):
        rows = [
            {"uid": "user_a", "role": "MEMBER"},
            {"uid": "user_b", "role": "member"},
            {"uid": "user_c", "role": "admin"},
        ]
        drifts = find_role_value_drift(rows)
        assert drifts == [{"uid": "user_a", "role": "MEMBER", "fix": "member"}]

    def test_unknown_value_reports_without_fix(self):
        drifts = find_role_value_drift([{"uid": "user_x", "role": "superuser"}])
        assert drifts[0]["fix"] is None


class TestOrphanAuthCleanup:
    def test_null_user_uid_events_are_audit_trail_not_deletions(self):
        from audit_graph_hygiene import plan_orphan_auth_cleanup

        sessions = [{"uid": "session_x", "user_uid": "user_gone"}]
        events = [
            {"uid": "auth_orphan", "user_uid": "user_gone"},
            {"uid": "auth_failed_login", "user_uid": None},
        ]
        plan = plan_orphan_auth_cleanup(sessions, events)
        assert [r["uid"] for r in plan.sessions] == ["session_x"]
        assert [r["uid"] for r in plan.auth_events] == ["auth_orphan"]
        assert [r["uid"] for r in plan.audit_trail] == ["auth_failed_login"]


class TestTestUserCleanupKodyFindings:
    """Kody #504: unlabeled owned rows must block the user, not silently drop."""

    def test_unlabeled_owned_entity_blocks_the_owner(self):
        users = [
            {
                "uid": "user_verifyperiodic",
                "email": "v@example.com",
                "edge_sigs": ["OWNS:out"],
                "session_count": 0,
                "auth_event_count": 0,
            }
        ]
        owned = [
            {
                "owner": "user_verifyperiodic",
                "uid": "weird_node",
                "labels": ["Entity"],  # no single domain label
                "edge_sigs": ["OWNS:in"],
            }
        ]
        plans = plan_test_user_cleanup(users, owned)
        assert plans[0].blockers and "no single domain label" in plans[0].blockers[0]
        assert plans[0].owned == []


class TestRepointSubsetSemantics:
    """EXPECTED_DUPE_EDGES is a ceiling (subset), not equality — a dupe whose
    ABOUT_ENTITY edge was already re-pointed by a partial prior run must stay
    deletable on re-run (Kody #504 equality suggestion rejected for this)."""

    def test_dupe_missing_about_entity_edge_is_still_fixable(self):
        rows = [
            {
                "uid": "task_dupe",
                "title": "move furniture",
                "owner": "user_x",
                "labels": ["Entity", "Task"],
                "edge_sigs": ["OWNS:in"],  # ABOUT_ENTITY already re-pointed
                "about_sources": [],
            },
            {
                "uid": "task_winner",
                "title": "move furniture",
                "owner": "user_x",
                "labels": ["Entity", "Task"],
                "edge_sigs": ["OWNS:in", "ABOUT_ENTITY:in"],
                "about_sources": ["insight.x"],
            },
        ]
        plans = plan_about_entity_repoints(rows, ruled={"task_dupe": "task_winner"})
        assert not plans[0].blockers
