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
    find_daily_owner_collisions,
    find_role_value_drift,
    find_type_mismatches,
    group_same_entry_duplicates,
    plan_about_entity_repoints,
    plan_cross_entry_dedup,
    plan_ku_enrollment_migrations,
    plan_test_user_cleanup,
    plan_wrong_door_cleanup,
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


def _entry(uid: str, owner: str = "user_a", pipeline: str = "extract_activities") -> dict:
    return {"uid": uid, "owner": owner, "pipeline": pipeline, "created_at": "2026-06-16"}


class TestWrongDoorPlan:
    def test_journal_door_entries_and_content_owner_entities_deleted(self):
        entries = [
            _entry("ue:daily:user_admin:2026-06-16", owner="user_admin"),
            _entry("ue:daily:user_a:2026-06-16", owner="user_a"),
        ]
        rows = [
            _row("h_admin", entry="ue:daily:user_admin:2026-06-16", owner="user_admin"),
            _row("h_personal", entry="ue:daily:user_a:2026-06-16", owner="user_a"),
        ]
        plan = plan_wrong_door_cleanup(entries, rows, content_owner="user_admin")
        assert [e["uid"] for e in plan.entries_to_delete] == ["ue:daily:user_admin:2026-06-16"]
        assert [e["uid"] for e in plan.entities_to_delete] == ["h_admin"]
        assert plan.orphaned_survivors == []

    def test_all_periodic_prefixes_count_as_journal_door(self):
        """ingest_user_entry mints ue:daily:/ue:weekly:/ue:monthly: — all three
        are the journal door for the R2 ruling (Kody #503: monthly was missed)."""
        entries = [
            _entry("ue:daily:user_admin:2026-06-16", owner="user_admin"),
            _entry("ue:weekly:user_admin:2026-W25", owner="user_admin"),
            _entry("ue:monthly:user_admin:2026-06", owner="user_admin"),
        ]
        plan = plan_wrong_door_cleanup(entries, [], content_owner="user_admin")
        assert sorted(e["uid"] for e in plan.entries_to_delete) == [
            "ue:daily:user_admin:2026-06-16",
            "ue:monthly:user_admin:2026-06",
            "ue:weekly:user_admin:2026-W25",
        ]

    def test_legacy_entry_duplicate_deleted_only_with_surviving_copy(self):
        entries = [
            _entry("ue_legacy", owner="user_a"),
            _entry("ue:daily:user_a:2026-06-16", owner="user_a"),
        ]
        rows = [
            _row("h_old", entry="ue_legacy", owner="user_a"),
            _row("h_new", entry="ue:daily:user_a:2026-06-16", owner="user_a"),
            _row("t_unique", entry="ue_legacy", owner="user_a", label="Task", title="only here"),
        ]
        plan = plan_wrong_door_cleanup(entries, rows, content_owner="user_admin")
        assert [e["uid"] for e in plan.entries_to_delete] == ["ue_legacy"]
        assert [e["uid"] for e in plan.entities_to_delete] == ["h_old"]
        # unique legacy entity survives, provenance edge dies with the entry
        assert [o["uid"] for o in plan.orphaned_survivors] == ["t_unique"]

    def test_unexpected_edges_block_deletion(self):
        entries = [_entry("ue:daily:user_admin:2026-06-16", owner="user_admin")]
        rows = [
            _row(
                "h_admin",
                entry="ue:daily:user_admin:2026-06-16",
                owner="user_admin",
                edges=["EXTRACTED_FROM:out", "OWNS:in", "HAS_COMPLETION:out"],
            ),
        ]
        plan = plan_wrong_door_cleanup(entries, rows, content_owner="user_admin")
        assert plan.entities_to_delete == []
        assert any("HAS_COMPLETION" in b for b in plan.blocked_entities)

    def test_non_extract_activities_and_test_user_entries_untouched(self):
        entries = [
            _entry("ue_journal_upload", owner="user_a", pipeline="llm_summary"),
            _entry("ue:daily:user_verifyperiodic:2026-06-01", owner="user_verifyperiodic"),
        ]
        plan = plan_wrong_door_cleanup(entries, [], content_owner="user_admin")
        assert plan.entries_to_delete == []


class TestCrossEntryDedup:
    def test_oldest_survivor_wins_after_wrong_door_exclusions(self):
        rows = [
            _row(
                "h1",
                entry="ue:daily:user_a:2026-06-30",
                created="2026-07-01T11:00:00",
            ),
            _row(
                "h2",
                entry="ue:daily:user_a:2026-07-15",
                created="2026-07-01T12:00:00",
            ),
            _row("h_gone", entry="ue_legacy", created="2026-06-01T00:00:00"),
        ]
        groups = plan_cross_entry_dedup(rows, {"ue_legacy"}, {"h_gone"})
        assert len(groups) == 1
        g = groups[0]
        assert g.winner_uid == "h1"
        assert g.loser_uids == ["h2"]
        assert g.blockers == []

    def test_single_entry_groups_are_not_cross_entry(self):
        rows = [_row("h1"), _row("h2")]
        assert plan_cross_entry_dedup(rows, set(), set()) == []

    def test_test_user_groups_are_blocked(self):
        rows = [
            _row("h1", entry="ue:daily:user_a:2026-06-30", owner="user_a"),
            _row(
                "h2",
                entry="ue:daily:user_verifyperiodic:2026-06-01",
                owner="user_verifyperiodic",
                created="2026-07-02T00:00:00",
            ),
        ]
        groups = plan_cross_entry_dedup(rows, set(), set())
        assert len(groups) == 1
        assert any("test user" in b for b in groups[0].blockers)

    def test_unexpected_loser_edges_block_the_group(self):
        rows = [
            _row("h1", entry="ue:daily:user_a:2026-06-30", created="2026-07-01T11:00:00"),
            _row(
                "h2",
                entry="ue:daily:user_a:2026-07-15",
                created="2026-07-01T12:00:00",
                edges=["EXTRACTED_FROM:out", "OWNS:in", "SUPPORTS_GOAL:out"],
            ),
        ]
        groups = plan_cross_entry_dedup(rows, set(), set())
        assert any("SUPPORTS_GOAL" in b for b in groups[0].blockers)


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
                "uid": "ue:daily:user_verifyperiodic:2026-06-01",
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
