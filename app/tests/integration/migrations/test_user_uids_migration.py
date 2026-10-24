"""The user-uid migration, census and write, against a real Neo4j and real vault files.

``scripts/migrations/user_uids_2026_10.py`` renames every ``user_{username}`` uid
to ``hashed_uid("user", old uid)``, moves the uids derived from a renamed user —
a periodic note to ``periodic_note_uid`` of its new owner, a default group to
``default_group_uid`` of its new teacher — rewrites every value naming a renamed
uid, and edits the vault frontmatter lines that name a renamed user.

The graph is a scratch container of its own: the census renames EVERY user uid
outside the generated shape, and the shared container holds the session's users.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.graph_driver import open_async_driver
from core.models.group.group import default_group_uid
from core.models.user_entry.user_entry import periodic_note_uid
from core.utils.uid_grammar import hashed_uid

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/migrations/user_uids_2026_10.py"


def _load() -> ModuleType:
    """Import the script by path (``scripts/`` is not a package)."""
    spec = importlib.util.spec_from_file_location("user_uids_2026_10", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


migration = _load()

TEACHER = "user_zzuteach"
TEACHER_NEW = hashed_uid("user", TEACHER)
STUDENT = "user_zzustudent"
STUDENT_NEW = hashed_uid("user", STUDENT)
FITTING = "user_7e57000000000aaa"
NOTE = periodic_note_uid("daily", STUDENT, "2026-10-01")
NOTE_NEW = periodic_note_uid("daily", STUDENT_NEW, "2026-10-01")
GROUP = default_group_uid(TEACHER)
GROUP_NEW = default_group_uid(TEACHER_NEW)
TASK = "task_3f9a0c41d2e87b65"
SESSION = "session_0123456789abcdef"
VECTOR = [0.5, 0.25, 0.125]
NOTE_MD = json.dumps({"entry_kind": "daily", "period_key": "2026-10-01"})
AUTH_MD = json.dumps({"admin_uid": TEACHER})
REPORT_PATH = f"/app/data/reports/{TEACHER}/ue_x/feedback.md"
SUBMITTED = f"---\nuser_uid: {STUDENT}\n---\nMy answer."
EXERCISE_FILE = "/vault/Exer/one_exer.md"

_SEED = """
CREATE (t:User {uid: $teacher, title: 'teach'})
CREATE (s:User {uid: $student, title: 'student'})
CREATE (:User {uid: $fitting, title: 'Fits'})
CREATE (s)-[:OWNS]->(note:Entity:UserEntry {uid: $note, user_uid: $student,
                                            metadata: $note_md, embedding: $vector})
CREATE (:IngestionMetadata {file_path: '/vault/daily/2026-10-01.md', entity_uid: $note})
CREATE (s)-[:OWNS]->(task:Entity:Task {uid: $task, user_uid: $student})
CREATE (s)-[:SHARES_WITH {granted_by: $teacher}]->(task)
CREATE (s)-[:HAS_SESSION]->(:Session {uid: $session, user_uid: $student})
CREATE (:AuthEvent {uid: 'auth_0123456789abcdef', user_uid: $teacher, metadata: $auth_md})
CREATE (t)-[:OWNS]->(g:Group {uid: $group, is_default: true, is_active: true})
CREATE (s)-[:MEMBER_OF]->(g)
CREATE (:IngestionMetadata {file_path: $exercise_file,
                            authored_edges: ['REVIEWED_BY|outgoing|' + $teacher]})
CREATE (t)-[:OWNS]->(:Entity:EntryReport {uid: 'er_0123456789abcdef', user_uid: $teacher,
                                          author_uid: $teacher, report_file_path: $report_path})
CREATE (s)-[:OWNS]->(:Entity:UserEntry {uid: 'ue_0123456789abcdef', user_uid: $student,
                                        content: $submitted})
"""

_SEED_PARAMS: dict[str, Any] = {  # boundary: cypher parameters
    "teacher": TEACHER,
    "student": STUDENT,
    "fitting": FITTING,
    "note": NOTE,
    "note_md": NOTE_MD,
    "vector": VECTOR,
    "task": TASK,
    "session": SESSION,
    "auth_md": AUTH_MD,
    "group": GROUP,
    "exercise_file": EXERCISE_FILE,
    "report_path": REPORT_PATH,
    "submitted": SUBMITTED,
}


@pytest_asyncio.fixture(loop_scope="session")
async def graph(scratch_neo4j_container: Any) -> AsyncIterator[Any]:
    """An unguarded driver onto the scratch container, seeded, emptied after each test."""
    driver = open_async_driver(
        scratch_neo4j_container.get_connection_url(), auth=("neo4j", "unused")
    )
    await driver.execute_query("MATCH (n) DETACH DELETE n")
    await driver.execute_query(_SEED, _SEED_PARAMS)
    yield driver
    await driver.execute_query("MATCH (n) DETACH DELETE n")
    await driver.close()


@pytest.fixture
def vaults(tmp_path: Path) -> tuple[Path, Path]:
    """A content vault naming the teacher and a personal vault naming the student."""
    content, personal = tmp_path / "content", tmp_path / "personal"
    (content / "Exer").mkdir(parents=True)
    (content / "Exer" / "one_exer.md").write_text(
        f"---\ntype: exercise\nuid: ex.zzu.one\nteacher: {TEACHER}\n---\n# One\n"
    )
    (content / "Ku").mkdir()
    (content / "Ku" / "plain.md").write_text("---\ntype: ku\n---\nNo account here.\n")
    (personal / "knowledge").mkdir(parents=True)
    # A standalone YAML entry is one mapping — its top-level ownership line names an account.
    (personal / "knowledge" / "entry.yaml").write_text(
        "type: user_entry\nownership: zzustudent\nnested:\n  ownership: kept\n"
    )
    # The bare name also appears in prose: only the ownership line names an account.
    (personal / "knowledge" / "bare.md").write_text(
        "---\ntype: user_entry\nownership: zzustudent\n---\nMention zzustudent here.\n"
    )
    (personal / "knowledge" / "list.md").write_bytes(
        f'---\r\ntype: user_entry\r\nuser_uid: "{STUDENT}"\r\n---\r\nBody\r\n'.encode()
    )
    return content, personal


async def _rows(driver: Any, query: str, **params: Any) -> list[dict[str, Any]]:
    result = await driver.execute_query(query, params)
    return [dict(record) for record in result.records]


async def _census(driver: Any, vaults: tuple[Path, Path], tmp_path: Path) -> Any:
    return await migration.census(driver, list(vaults), tmp_path / "user_vaults")


class TestTheRename:
    async def test_census_plans_every_user_and_what_derives_from_one(
        self, graph: Any, vaults: tuple[Path, Path], tmp_path: Path
    ) -> None:
        plan = await _census(graph, vaults, tmp_path)

        assert plan.stops == [], plan.stops
        assert {r.old: r.new for r in plan.renames} == {
            TEACHER: TEACHER_NEW,
            STUDENT: STUDENT_NEW,
            NOTE: NOTE_NEW,
            GROUP: GROUP_NEW,
        }
        assert sorted((w.target, w.holder, w.key) for w in plan.rewrites) == [
            ("edge", "SHARES_WITH", "granted_by"),
            ("node", "AuthEvent", "metadata"),
            ("node", "AuthEvent", "user_uid"),
            ("node", "EntryReport", "author_uid"),
            ("node", "EntryReport", "user_uid"),
            ("node", "IngestionMetadata", "authored_edges"),
            ("node", "IngestionMetadata", "entity_uid"),
            ("node", "Session", "user_uid"),
            ("node", "Task", "user_uid"),
            ("node", "User", "title"),
            ("node", "UserEntry", "user_uid"),
            ("node", "UserEntry", "user_uid"),
        ]
        assert dict(plan.quoted) == {"EntryReport.report_file_path": 1, "UserEntry.content": 1}
        assert sorted(edit.path.name for edit in plan.files) == [
            "bare.md",
            "entry.yaml",
            "list.md",
            "one_exer.md",
        ]
        assert plan.embedded == 1

    async def test_confirm_renames_in_place_and_moves_every_reference(
        self, graph: Any, vaults: tuple[Path, Path], tmp_path: Path
    ) -> None:
        plan = await _census(graph, vaults, tmp_path)

        written = await migration.migrate(graph, plan)
        assert written == {
            "renamed": 4,
            "node values rewritten": 11,
            "edge values rewritten": 1,
        }
        assert migration.edit_vaults(plan) == 4
        assert await migration.read_back(graph, plan, list(vaults), tmp_path / "user_vaults") == []

        users = await _rows(graph, "MATCH (u:User) RETURN u.uid AS uid, u.title AS name")
        assert sorted((row["uid"], row["name"]) for row in users) == sorted(
            [(TEACHER_NEW, "teach"), (STUDENT_NEW, "student"), (FITTING, "fits")]
        )
        # The periodic note: at the uid its writer derives from the new owner, vector kept.
        note = await _rows(
            graph,
            "MATCH (:User {uid: $s})-[:OWNS]->(e:UserEntry {uid: $n}) RETURN e.embedding AS v",
            s=STUDENT_NEW,
            n=NOTE_NEW,
        )
        assert [row["v"] for row in note] == [VECTOR]
        # The default group: at the uid enrollment MERGEs on, flagged, roster kept.
        group = await _rows(
            graph,
            "MATCH (:User {uid: $t})-[:OWNS]->(g:Group)<-[:MEMBER_OF]-(:User {uid: $s}) "
            "RETURN g.uid AS uid, g.is_default AS d",
            t=TEACHER_NEW,
            s=STUDENT_NEW,
        )
        assert [(row["uid"], row["d"]) for row in group] == [(GROUP_NEW, True)]
        values = await _rows(
            graph,
            "MATCH (a:AuthEvent), (s:Session), (x:IngestionMetadata {file_path: $f}), "
            "(:User)-[r:SHARES_WITH]->() "
            "RETURN a.metadata AS auth, a.user_uid AS actor, s.user_uid AS session, "
            "x.authored_edges AS keys, r.granted_by AS granted",
            f=EXERCISE_FILE,
        )
        assert values == [
            {
                "auth": json.dumps({"admin_uid": TEACHER_NEW}),
                "actor": TEACHER_NEW,
                "session": STUDENT_NEW,
                "keys": [f"REVIEWED_BY|outgoing|{TEACHER_NEW}"],
                "granted": TEACHER_NEW,
            }
        ]
        # Text that quotes a uid is left as written.
        quoted = await _rows(
            graph,
            "MATCH (r:EntryReport), (e:UserEntry {uid: 'ue_0123456789abcdef'}) "
            "RETURN r.report_file_path AS path, e.content AS content",
        )
        assert quoted == [{"path": REPORT_PATH, "content": SUBMITTED}]
        # The vault files name the new uids; every other byte is the same.
        content, personal = vaults
        assert (content / "Exer" / "one_exer.md").read_text() == (
            f"---\ntype: exercise\nuid: ex.zzu.one\nteacher: {TEACHER_NEW}\n---\n# One\n"
        )
        assert (personal / "knowledge" / "list.md").read_bytes() == (
            f'---\r\ntype: user_entry\r\nuser_uid: "{STUDENT_NEW}"\r\n---\r\nBody\r\n'.encode()
        )
        assert (personal / "knowledge" / "entry.yaml").read_text() == (
            f"type: user_entry\nownership: {STUDENT_NEW}\nnested:\n  ownership: kept\n"
        )
        # A bare username on an ownership line named its user_{name} uid: it names the new one.
        assert (personal / "knowledge" / "bare.md").read_text() == (
            f"---\ntype: user_entry\nownership: {STUDENT_NEW}\n---\nMention zzustudent here.\n"
        )

    async def test_a_second_run_finds_nothing_to_move(
        self, graph: Any, vaults: tuple[Path, Path], tmp_path: Path
    ) -> None:
        plan = await _census(graph, vaults, tmp_path)
        await migration.migrate(graph, plan)
        migration.edit_vaults(plan)

        again = await _census(graph, vaults, tmp_path)
        assert (again.renames, again.rewrites, again.files, again.stops) == ([], [], [], [])

    async def test_a_run_whose_file_edits_did_not_land_plans_them_again(
        self, graph: Any, vaults: tuple[Path, Path], tmp_path: Path
    ) -> None:
        """The graph moved and the files did not: their hashes name live users."""
        plan = await _census(graph, vaults, tmp_path)
        await migration.migrate(graph, plan)

        again = await _census(graph, vaults, tmp_path)
        assert again.renames == [] and again.stops == []
        assert sorted(edit.path.name for edit in again.files) == [
            "bare.md",
            "entry.yaml",
            "list.md",
            "one_exer.md",
        ]
        migration.edit_vaults(again)
        content, _ = vaults
        assert f"teacher: {TEACHER_NEW}\n" in (content / "Exer" / "one_exer.md").read_text()


async def test_a_username_shaped_like_a_renamed_uid_is_left_to_the_username_rule(
    graph: Any, vaults: tuple[Path, Path], tmp_path: Path
) -> None:
    """``user_zzuteach`` fits the username rule: another account may hold it as its name."""
    await graph.execute_query(
        "CREATE (:User {uid: 'user_7e57000000000bbb', title: $name, display_name: $name})",
        {"name": TEACHER},
    )

    plan = await _census(graph, vaults, tmp_path)

    assert plan.stops == [], plan.stops
    assert not [w for w in plan.rewrites if w.before == TEACHER and w.holder == "User"]
    assert plan.quoted["User.title"] == 1
    assert plan.quoted["User.display_name"] == 1


class TestTheStops:
    async def test_a_vault_naming_a_user_outside_its_frontmatter_stops_the_run(
        self, graph: Any, vaults: tuple[Path, Path], tmp_path: Path
    ) -> None:
        content, _ = vaults
        (content / "Ku" / "mention.md").write_text(f"---\ntype: ku\n---\nAsk {TEACHER}.\n")

        plan = await _census(graph, vaults, tmp_path)

        assert any("mention.md:4" in stop for stop in plan.stops), plan.stops
        with pytest.raises(migration.CountMismatchError):
            await migration.migrate(graph, plan)

    async def test_an_owner_line_with_a_comment_is_edited_and_keeps_it(
        self, graph: Any, vaults: tuple[Path, Path], tmp_path: Path
    ) -> None:
        _, personal = vaults
        note = personal / "knowledge" / "commented.md"
        note.write_text("---\ntype: user_entry\nownership: zzustudent # me\n---\n")

        plan = await _census(graph, vaults, tmp_path)

        assert plan.stops == [], plan.stops
        (edit,) = [edit for edit in plan.files if edit.path == note]
        assert edit.after == f"---\ntype: user_entry\nownership: {STUDENT_NEW} # me\n---\n"

    async def test_a_declared_owner_no_line_edit_reaches_stops_the_run(
        self, graph: Any, vaults: tuple[Path, Path], tmp_path: Path
    ) -> None:
        """Ingestion reads a folded scalar's owner; the line editor cannot move it."""
        _, personal = vaults
        (personal / "knowledge" / "folded.md").write_text(
            "---\ntype: user_entry\nownership: >-\n  zzustudent\n---\n"
        )

        plan = await _census(graph, vaults, tmp_path)

        assert any("folded.md: its ownership:" in stop for stop in plan.stops), plan.stops

    async def test_a_vault_naming_a_renamed_group_stops_the_run(
        self, graph: Any, vaults: tuple[Path, Path], tmp_path: Path
    ) -> None:
        _, personal = vaults
        (personal / "knowledge" / "shared.md").write_text(
            f"---\ntype: user_entry\naudience: group:{GROUP}\n---\n"
        )

        plan = await _census(graph, vaults, tmp_path)

        assert any(f"shared.md:3 names {GROUP}" in stop for stop in plan.stops), plan.stops

    async def test_a_member_vault_is_read_too(
        self, graph: Any, vaults: tuple[Path, Path], tmp_path: Path
    ) -> None:
        member = tmp_path / "user_vaults" / STUDENT_NEW / "knowledge"
        member.mkdir(parents=True)
        (member / "note.md").write_text("---\ntype: user_entry\nownership: zzustudent\n---\n")

        plan = await _census(graph, vaults, tmp_path)

        assert plan.stops == [], plan.stops
        assert tmp_path / "user_vaults" / STUDENT_NEW / "knowledge" / "note.md" in {
            edit.path for edit in plan.files
        }

    async def test_a_per_user_vault_named_by_a_renamed_user_stops_the_run(
        self, graph: Any, vaults: tuple[Path, Path], tmp_path: Path
    ) -> None:
        (tmp_path / "user_vaults" / STUDENT).mkdir(parents=True)

        plan = await _census(graph, vaults, tmp_path)

        assert any("per-user vault" in stop for stop in plan.stops), plan.stops

    async def test_a_periodic_note_off_its_derived_uid_stops_the_run(
        self, graph: Any, vaults: tuple[Path, Path], tmp_path: Path
    ) -> None:
        await graph.execute_query(
            "MATCH (s:User {uid: $s}) CREATE (s)-[:OWNS]->(:Entity:UserEntry "
            "{uid: 'ue_ffffffffffffffff', metadata: $md})",
            {"s": STUDENT, "md": json.dumps({"entry_kind": "daily", "period_key": "2026-10-02"})},
        )

        plan = await _census(graph, vaults, tmp_path)

        assert any("ue_ffffffffffffffff" in stop for stop in plan.stops), plan.stops

    async def test_a_default_group_off_its_derived_uid_stops_the_run(
        self, graph: Any, vaults: tuple[Path, Path], tmp_path: Path
    ) -> None:
        await graph.execute_query(
            "MATCH (t:User {uid: $t}) CREATE (t)-[:OWNS]->(:Group "
            "{uid: 'group_ffffffffffffffff', is_default: true})",
            {"t": TEACHER},
        )

        plan = await _census(graph, vaults, tmp_path)

        assert any("group_ffffffffffffffff" in stop for stop in plan.stops), plan.stops

    async def test_a_renamed_node_holding_chunks_stops_the_run(
        self, graph: Any, vaults: tuple[Path, Path], tmp_path: Path
    ) -> None:
        await graph.execute_query(
            "MATCH (e:UserEntry {uid: $n}) "
            "CREATE (e)-[:HAS_CONTENT]->(:Content)-[:HAS_CHUNK]->(:ContentChunk {uid: 'c'})",
            {"n": NOTE},
        )

        plan = await _census(graph, vaults, tmp_path)

        assert any("holds chunks" in stop for stop in plan.stops), plan.stops

    @pytest.mark.parametrize(
        ("titles", "stop"),
        [(["jane doe"], "outside"), (["Sam", "sam"], "fold to")],
        ids=["outside-the-rule", "two-fold-to-one"],
    )
    async def test_a_username_the_rule_cannot_hold_stops_the_run(
        self, graph: Any, vaults: tuple[Path, Path], tmp_path: Path, titles: list[str], stop: str
    ) -> None:
        for number, title in enumerate(titles):
            await graph.execute_query(
                "CREATE (:User {uid: $uid, title: $title})",
                {"uid": f"user_7e5700000000{number:04x}", "title": title},
            )

        plan = await _census(graph, vaults, tmp_path)

        assert any(stop in item for item in plan.stops), plan.stops

    async def test_a_value_quoting_a_user_in_other_text_stops_the_run(
        self, graph: Any, vaults: tuple[Path, Path], tmp_path: Path
    ) -> None:
        await graph.execute_query(
            "MATCH (t:Task) SET t.description = $d", {"d": f"Ask {TEACHER} on Monday"}
        )

        plan = await _census(graph, vaults, tmp_path)

        assert plan.stops == ["node Task.description names a renamed uid inside other text"]
