"""What a vault file may write, through every ingestion door (ADR-070 Decision 11).

Two users hold real vault roots: ALICE on the primary personal root, BOB in the
member-vault family (``{user_vaults_root}/{uid}/``); ADMIN is the content vault's
acts-as account. Every scenario runs through the three doors a vault file reaches
the graph by — ``UnifiedIngestionService.ingest_directory``, the single-file door
``ingest_file``, and ``VaultReconciler.sync`` — and asserts the graph, not a log.

The rules:

1. A personal vault ingests the six Activity types, ``life_path`` and
   ``user_entry``; an Edge file, a Group file and every curriculum type are
   refused there, reported as ignored-with-reason.
2. The upsert never changes a node's owner — a file whose uid names another
   user's node is refused, in the content vault too.
3. A uid-less personal Activity file has its own identity: two users with the
   same filename get two entities, and a rename keeps the entity.
4. A personal Activity file's frontmatter targets are the vault owner's or
   unowned published content — a Ku marked ``publication_state: draft`` draws no
   edge and is warned about in the words a missing target is.

Content vault: an Edge file joins two entities (never a :User or a :Group end,
never an ``OWNS``), and a Group file's owner is the vault's resolved owner.

Every refusal is paired with a positive control in the same sync, so a door that
wrote nothing at all cannot pass. A refusal never names whose node it is.

Requires: Docker running with Neo4j testcontainer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict, cast
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from adapters.persistence.neo4j.ingestion_backend import IngestionBackend
from adapters.persistence.neo4j.ingestion_service_factory import make_unified_ingestion_service
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.type_hints import UserUID
from core.ports.vault_bridge_protocol import VaultBridgePort
from core.services.ingestion.config import build_sync_allowlist
from core.services.ingestion.unified_ingestion_service import UnifiedIngestionService
from core.services.vault.vault_descriptor import VaultDescriptor, VaultKind, VaultRegistry
from core.services.vault.vault_reconciler import VaultReconciler
from core.utils.result_simplified import Result
from core.utils.zone_context import default_zone

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

ALICE = UserUID("user_nb2c_alice")
BOB = UserUID("user_nb2c_bob")
ADMIN = UserUID("user_nb2c_content_admin")

DOORS = ("directory", "file", "reconciler")


class VaultEnv(TypedDict):
    """Three vaults, the service and reconciler syncing them, and the graph."""

    service: UnifiedIngestionService
    reconciler: VaultReconciler
    alice: Path
    bob: Path
    content: Path
    driver: AsyncDriver


def _bridge() -> VaultBridgePort:
    return cast("VaultBridgePort", object())


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _md(type_: str, title: str, extra: str = "") -> str:
    return f"---\ntype: {type_}\ntitle: {title}\n{extra}---\n\nbody of {title}\n"


@pytest_asyncio.fixture
async def env(neo4j_driver, clean_neo4j, tmp_path: Path) -> VaultEnv:
    content_root = tmp_path / "content"
    alice_root = tmp_path / "alice"
    family = tmp_path / "user_vaults"
    bob_root = family / str(BOB)
    for d in (content_root, alice_root, bob_root):
        d.mkdir(parents=True)

    async with neo4j_driver.session() as session:
        for uid in (ALICE, BOB, ADMIN):
            await session.run("MERGE (u:User {uid: $uid}) SET u.title = $uid", uid=uid)

    def personal(owner: UserUID, root: Path) -> VaultDescriptor:
        # No task round-trip: the reconciler door then runs consent-free and
        # inbound-only, which is the half these rules are about.
        return VaultDescriptor(
            kind=VaultKind.PERSONAL,
            root=root,
            owner_uid=owner,
            allowlist=build_sync_allowlist(root, content_root=content_root),
            bridge=_bridge(),
            supports_task_round_trip=False,
        )

    content = VaultDescriptor(
        kind=VaultKind.CONTENT,
        root=content_root,
        owner_uid=ADMIN,
        allowlist=build_sync_allowlist(content_root, content_root=content_root, gates_je_pro=False),
        bridge=_bridge(),
        supports_task_round_trip=False,
    )
    registry = VaultRegistry(
        content=content,
        personal=personal(ALICE, alice_root),
        user_vaults_root=family,
        personal_descriptor_factory=personal,
    )
    service = make_unified_ingestion_service(
        driver=neo4j_driver,
        default_user_uid=UserUID("user_default"),
        ingestion_backend=IngestionBackend(executor=Neo4jQueryExecutor(neo4j_driver)),
    )
    service.vault_registry = registry
    service.sync_allowlist = registry.resolve(VaultKind.PERSONAL, ALICE).value.allowlist
    # A personal sync runs in its owner's zone; the app default stands in.
    user_service = Mock()
    user_service.get_user_zone = AsyncMock(return_value=Result.ok(default_zone()))
    reconciler = VaultReconciler(
        registry=registry,
        unified_ingestion=service,
        user_entry_service=Mock(),
        tasks_service=Mock(),
        user_service=user_service,
    )
    return VaultEnv(
        service=service,
        reconciler=reconciler,
        alice=alice_root,
        bob=bob_root,
        content=content_root,
        driver=neo4j_driver,
    )


_ACTING = {"alice": ALICE, "bob": BOB, "content": ADMIN}


class Outcome:
    """What one sync through one door reported, in door-independent terms."""

    def __init__(self) -> None:
        self.refused: dict[str, str] = {}  # file name -> the reason the door gave
        self.failed: dict[str, str] = {}  # file name -> a non-content error
        self.warnings: list[str] = []


_CONTENT_FAULT_STAGES = {"parsing", "type_detection", "validation", "preparation"}


async def _sync_directory(env: VaultEnv, root: Path, owner: UserUID) -> Outcome:
    out = Outcome()
    result = await env["service"].ingest_directory(root, ingestion_mode="smart", user_uid=owner)
    assert result.is_ok, result
    stats = result.value
    out.warnings = list(stats.warnings)
    for error in stats.errors or []:
        name = Path(str(error.get("file", ""))).name
        if error.get("stage") in _CONTENT_FAULT_STAGES:
            out.refused[name] = str(error.get("error"))
        else:
            out.failed[name] = str(error.get("error"))
    return out


def _edge_files_last(path: Path) -> bool:
    """Sort key: the single-file door has no phase ordering, so a caller syncing a
    vault file by file sends entities before edges."""
    return path.suffix != ".md"


async def _sync_file_by_file(env: VaultEnv, root: Path, owner: UserUID) -> Outcome:
    out = Outcome()
    files = sorted(p for p in root.rglob("*") if p.suffix in {".md", ".yaml", ".yml"})
    files.sort(key=_edge_files_last)
    for path in files:
        result = await env["service"].ingest_file(path, user_uid=owner)
        if result.is_error:
            failure = result.expect_error()
            if failure.category.value == "validation":
                out.refused[path.name] = failure.message
            else:
                out.failed[path.name] = failure.message
        else:
            out.warnings.extend(result.value.get("warnings") or [])
    return out


async def _sync_reconciler(env: VaultEnv, kind: VaultKind, owner: UserUID) -> Outcome:
    out = Outcome()
    result = await env["reconciler"].sync(kind, owner)
    assert result.is_ok, result
    stats = result.value
    out.warnings = list(stats.warnings)
    for line in stats.ignored:
        path, _, reason = line.partition(" — ")
        out.refused[Path(path).name] = reason
    for line in stats.errors:
        out.failed[line] = line
    return out


async def _sync(env: VaultEnv, who: str, door: str) -> Outcome:
    """Sync ``who``'s vault through ``door``; collect what it refused and why."""
    root = {"alice": env["alice"], "bob": env["bob"], "content": env["content"]}[who]
    owner = _ACTING[who]
    if door == "directory":
        return await _sync_directory(env, root, owner)
    if door == "file":
        return await _sync_file_by_file(env, root, owner)
    kind = VaultKind.CONTENT if who == "content" else VaultKind.PERSONAL
    return await _sync_reconciler(env, kind, owner)


# boundary: Neo4j record rows — each query projects its own heterogeneous columns
async def _q(driver: AsyncDriver, cypher: str, **params: object) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(cypher, **params)
        return [dict(r) async for r in result]


# boundary: one Neo4j record row (labels, owners, properties)
async def _node(driver: AsyncDriver, uid: str) -> dict[str, Any]:
    """The node with ``uid`` — which must exist."""
    rows = await _q(
        driver,
        """
        MATCH (n {uid: $uid}) WHERE NOT n:Content
        OPTIONAL MATCH (o:User)-[:OWNS]->(n)
        RETURN [l IN labels(n) WHERE l <> 'Entity'] AS labels, n.user_uid AS user_uid,
               n.owner_uid AS owner_uid, n.title AS title, n.name AS name,
               n.description AS description, collect(o.uid) AS owners
        """,
        uid=uid,
    )
    assert rows, f"no node {uid}"
    return rows[0]


async def _edge_types(driver: AsyncDriver, a: str, b: str) -> list[str]:
    rows = await _q(
        driver, "MATCH ({uid: $a})-[r]->({uid: $b}) RETURN type(r) AS t ORDER BY t", a=a, b=b
    )
    return [r["t"] for r in rows]


# boundary: Neo4j record rows (uid, user_uid, owners)
async def _uids_titled(driver: AsyncDriver, title: str) -> list[dict[str, Any]]:
    return await _q(
        driver,
        """
        MATCH (n:Entity {title: $title})
        OPTIONAL MATCH (o:User)-[:OWNS]->(n)
        RETURN n.uid AS uid, n.user_uid AS user_uid, collect(o.uid) AS owners
        ORDER BY n.user_uid
        """,
        title=title,
    )


def _assert_never_names_owner(reason: str) -> None:
    """A refusal never confirms whose node it is."""
    lowered = reason.lower()
    for leak in (str(BOB).lower(), str(ALICE).lower(), str(ADMIN).lower(), "owned by", "belongs"):
        assert leak not in lowered, f"refusal names an owner: {reason!r}"


# ---------------------------------------------------------------------------
# Part 1 — the type allowlist per vault kind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("door", DOORS)
async def test_personal_vault_refuses_edge_files(env, door) -> None:
    """An Edge file in a personal vault writes nothing — not even between its owner's nodes."""
    d = env["driver"]
    _write(
        env["bob"] / "knowledge" / "bsecret.md", _md("task", "Bob secret", "uid: task.bsecret\n")
    )
    _write(env["bob"] / "knowledge" / "bgoal.md", _md("goal", "Bob goal", "uid: goal.bgoal\n"))
    await _sync(env, "bob", "directory")
    _write(env["alice"] / "knowledge" / "atask.md", _md("task", "Alice task", "uid: task.atask\n"))
    _write(env["alice"] / "knowledge" / "agoal.md", _md("goal", "Alice goal", "uid: goal.agoal\n"))
    edges = {
        "edge_a_to_b": ("task.atask", "task.bsecret", "DEPENDS_ON"),
        "edge_b_to_b": ("task.bsecret", "goal.bgoal", "FULFILLS_GOAL"),
        "edge_owns": (str(ALICE), "task.bsecret", "OWNS"),
        "edge_shares": (str(ALICE), "goal.bgoal", "SHARES_WITH"),
        "edge_own_pair": ("task.atask", "goal.agoal", "FULFILLS_GOAL"),
    }
    for name, (f, t, rel) in edges.items():
        _write(
            env["alice"] / "knowledge" / f"{name}.yaml",
            f"type: Edge\nfrom: {f}\nto: {t}\nrelationship: {rel}\n",
        )

    outcome = await _sync(env, "alice", door)

    for name, (f, t, _rel) in edges.items():
        assert await _edge_types(d, f, t) == [], name
        assert f"{name}.yaml" in outcome.refused, (name, outcome.refused)
        _assert_never_names_owner(outcome.refused[f"{name}.yaml"])
    assert (await _node(d, "task.bsecret"))["owners"] == [str(BOB)]
    # Positive control: the same sync ingested Alice's own Activity files.
    assert (await _node(d, "task.atask"))["owners"] == [str(ALICE)]
    assert (await _node(d, "goal.agoal"))["owners"] == [str(ALICE)]


@pytest.mark.parametrize("door", DOORS)
async def test_personal_vault_refuses_group_and_curriculum(env, door) -> None:
    """A member's Group and curriculum files are refused; the content vault's Ku is untouched."""
    d = env["driver"]
    _write(
        env["content"] / "atom.md",
        "---\ntype: ku\nuid: ku.nb2c.atom\ntitle: The admin's atom\ndescription: curated\n---\n\nbody\n",
    )
    await _sync(env, "content", "directory")

    knowledge = env["bob"] / "knowledge"
    _write(knowledge / "atom.md", "---\ntype: ku\nuid: ku.nb2c.atom\ntitle: Rewritten\n---\n\nx\n")
    _write(knowledge / "newku.md", _md("ku", "Bob ku"))
    _write(knowledge / "step.md", _md("path_step", "Bob step"))
    _write(knowledge / "path.md", _md("learning_path", "Bob path"))
    _write(knowledge / "ex.md", _md("exercise", "Bob exercise", "instructions: do it\n"))
    _write(knowledge / "res.md", _md("resource", "Bob resource"))
    _write(knowledge / "tmpl.md", _md("task_template", "Bob template"))
    _write(knowledge / "grp.md", f"---\ntype: group\nname: Bob group\nowner_uid: {BOB}\n---\n\nx\n")
    _write(knowledge / "map.md", "---\nmoc: true\ntitle: Typeless map\n---\n\n[[newku]]\n")
    _write(knowledge / "mine.md", _md("habit", "Bob habit"))  # positive control

    outcome = await _sync(env, "bob", door)

    for name in (
        "atom.md",
        "newku.md",
        "step.md",
        "path.md",
        "ex.md",
        "res.md",
        "tmpl.md",
        "grp.md",
        "map.md",
    ):
        assert name in outcome.refused, (name, outcome.refused)
    atom = await _node(d, "ku.nb2c.atom")
    assert atom["title"] == "The admin's atom" and atom["description"] == "curated"
    curriculum = await _q(
        d,
        "MATCH (n) WHERE n:Ku OR n:PathStep OR n:LearningPath OR n:Exercise OR n:Resource "
        "OR n:TaskTemplate OR n:Group RETURN n.uid AS uid",
    )
    assert [r["uid"] for r in curriculum] == ["ku.nb2c.atom"]
    habits = await _uids_titled(d, "Bob habit")
    assert len(habits) == 1 and habits[0]["owners"] == [str(BOB)]


@pytest.mark.parametrize("door", DOORS)
async def test_personal_vault_ingests_life_path_as_its_owner(env, door) -> None:
    """``life_path`` syncs, owned by the vault owner whatever its ``user_uid:`` line says."""
    d = env["driver"]
    _write(
        env["alice"] / "knowledge" / "theirs.md",
        _md("life_path", "Claims bob", f"user_uid: {BOB}\n"),
    )
    _write(env["alice"] / "knowledge" / "plain.md", _md("life_path", "No user line"))

    outcome = await _sync(env, "alice", door)

    assert outcome.refused == {} and outcome.failed == {}, (outcome.refused, outcome.failed)
    for title in ("Claims bob", "No user line"):
        rows = await _uids_titled(d, title)
        assert len(rows) == 1, (title, rows)
        assert rows[0]["user_uid"] == str(ALICE) and rows[0]["owners"] == [str(ALICE)], rows


# ---------------------------------------------------------------------------
# Part 2 — the upsert never changes a node's owner
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("door", DOORS)
async def test_named_uid_never_reowns_another_users_node(env, door) -> None:
    d = env["driver"]
    _write(
        env["bob"] / "knowledge" / "secret.md",
        "---\ntype: task\nuid: task.secret\ntitle: Bob secret\ndescription: bob only\n---\n\nb\n",
    )
    await _sync(env, "bob", "directory")
    _write(env["alice"] / "knowledge" / "mine.md", _md("task", "Hijacked", "uid: task.secret\n"))
    _write(env["alice"] / "knowledge" / "ok.md", _md("task", "Alice own", "uid: task.alice-own\n"))

    outcome = await _sync(env, "alice", door)

    secret = await _node(d, "task.secret")
    assert secret["user_uid"] == str(BOB) and secret["owners"] == [str(BOB)]
    assert secret["title"] == "Bob secret"
    assert "mine.md" in outcome.refused, outcome.refused
    _assert_never_names_owner(outcome.refused["mine.md"])
    assert (await _node(d, "task.alice-own"))["owners"] == [str(ALICE)]


@pytest.mark.parametrize("door", DOORS)
async def test_content_vault_file_never_reowns_a_users_node(env, door) -> None:
    """The content vault's owner is an account like any other."""
    d = env["driver"]
    _write(env["bob"] / "knowledge" / "secret.md", _md("task", "Bob secret", "uid: task.secret\n"))
    await _sync(env, "bob", "directory")
    _write(env["content"] / "stray.md", _md("task", "Admin overwrite", "uid: task.secret\n"))
    _write(env["content"] / "own.md", _md("task", "Admin own", "uid: task.admin-own\n"))

    outcome = await _sync(env, "content", door)

    secret = await _node(d, "task.secret")
    assert secret["owners"] == [str(BOB)] and secret["title"] == "Bob secret"
    assert "stray.md" in outcome.refused, outcome.refused
    assert (await _node(d, "task.admin-own"))["owners"] == [str(ADMIN)]


# ---------------------------------------------------------------------------
# Part 3 — per-file identity for a uid-less personal Activity file
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("door", DOORS)
async def test_same_filename_in_two_vaults_is_two_entities(env, door) -> None:
    d = env["driver"]
    _write(env["bob"] / "knowledge" / "todo.md", _md("task", "Bob private thing"))
    await _sync(env, "bob", door)
    _write(env["alice"] / "knowledge" / "todo.md", _md("task", "Alice thing"))

    outcome = await _sync(env, "alice", door)

    assert outcome.refused == {}, outcome.refused
    bob = await _uids_titled(d, "Bob private thing")
    alice = await _uids_titled(d, "Alice thing")
    assert len(bob) == 1 and bob[0]["owners"] == [str(BOB)], bob
    assert len(alice) == 1 and alice[0]["owners"] == [str(ALICE)], alice
    assert bob[0]["uid"] != alice[0]["uid"]


@pytest.mark.parametrize("door", ("directory", "reconciler"))
async def test_uidless_personal_task_keeps_its_identity_across_resync_and_rename(env, door) -> None:
    """The minted uid is the file's: a re-sync and a rename reuse it; the file is the owner's."""
    d = env["driver"]
    path = _write(env["alice"] / "knowledge" / "plan.md", _md("task", "Plan it"))
    await _sync(env, "alice", door)
    first = await _uids_titled(d, "Plan it")
    assert len(first) == 1 and first[0]["owners"] == [str(ALICE)]
    uid = first[0]["uid"]

    path.write_text(_md("task", "Plan it", "priority: high\n"))  # an edit
    await _sync(env, "alice", door)
    path.rename(env["alice"] / "knowledge" / "plan-renamed.md")  # a pure rename
    await _sync(env, "alice", door)

    rows = await _uids_titled(d, "Plan it")
    assert [r["uid"] for r in rows] == [uid], rows


@pytest.mark.parametrize("door", DOORS)
async def test_a_lost_tracker_row_never_mints_a_second_entity(env, door) -> None:
    """The identity a uid-less file is given does not depend on its stamp landing.

    A first sync whose tracker stamp is lost (a failed write) must not leave the
    next sync to mint a second entity for the same file.
    """
    d = env["driver"]
    _write(env["alice"] / "knowledge" / "once.md", _md("task", "Only once"))
    await _sync(env, "alice", door)
    async with d.session() as session:
        await session.run("MATCH (m:IngestionMetadata) DETACH DELETE m")

    await _sync(env, "alice", door)

    rows = await _uids_titled(d, "Only once")
    assert len(rows) == 1 and rows[0]["owners"] == [str(ALICE)], rows


@pytest.mark.parametrize("door", ("directory", "reconciler"))
async def test_every_file_naming_a_foreign_uid_is_refused(env, door) -> None:
    """Two files that name the same node someone else owns are both refused, every sync."""
    d = env["driver"]
    _write(env["bob"] / "knowledge" / "secret.md", _md("task", "Bob secret", "uid: task.secret\n"))
    await _sync(env, "bob", "directory")
    _write(env["alice"] / "knowledge" / "one.md", _md("task", "One", "uid: task.secret\n"))
    _write(env["alice"] / "knowledge" / "two.md", _md("task", "Two", "uid: task.secret\n"))

    first = await _sync(env, "alice", door)
    second = await _sync(env, "alice", door)

    for outcome in (first, second):
        assert {"one.md", "two.md"} <= set(outcome.refused), outcome.refused
    assert (await _node(d, "task.secret"))["title"] == "Bob secret"


@pytest.mark.parametrize("door", ("directory", "reconciler"))
async def test_deleting_a_refused_file_never_deletes_the_node_it_failed_to_take(env, door) -> None:
    d = env["driver"]
    _write(env["bob"] / "knowledge" / "secret.md", _md("task", "Bob secret", "uid: task.secret\n"))
    await _sync(env, "bob", "directory")
    taker = _write(
        env["alice"] / "knowledge" / "taker.md", _md("task", "Taker", "uid: task.secret\n")
    )
    keeper = _write(env["alice"] / "knowledge" / "keeper.md", _md("task", "Keeper"))
    await _sync(env, "alice", door)
    taker.unlink()

    await _sync(env, "alice", door)

    assert (await _node(d, "task.secret"))["owners"] == [str(BOB)]
    assert keeper.exists() and len(await _uids_titled(d, "Keeper")) == 1


@pytest.mark.parametrize("door", ("directory", "reconciler"))
async def test_a_personal_vault_never_deletes_shared_content(env, door) -> None:
    """A personal vault's tracker row that names a shared Ku never deletes it.

    A personal vault deletes only its owner's nodes: when a tracked file is gone and
    its row names a node nobody owns, the node stays and the sync reports it. The
    owner's own deletions in the same sync still run.
    """
    d = env["driver"]
    _write(env["content"] / "atom.md", "---\ntype: ku\nuid: ku.nb2c.atom\ntitle: Atom\n---\n\nx\n")
    await _sync(env, "content", "directory")
    mine = _write(env["alice"] / "knowledge" / "mine.md", _md("task", "Mine"))
    _write(env["alice"] / "knowledge" / "keeper.md", _md("task", "Keeper"))
    await _sync(env, "alice", door)
    legacy = (env["alice"] / "knowledge" / "atom.md").resolve()
    async with d.session() as session:
        await session.run(
            "CREATE (:IngestionMetadata {file_path: $path, entity_uid: 'ku.nb2c.atom', "
            "content_hash: 'legacy', file_mtime: 0.0, last_ingested_at: datetime(), "
            "authored_edges: []})",
            path=str(legacy),
        )
    mine.unlink()

    outcome = await _sync(env, "alice", door)

    assert (await _node(d, "ku.nb2c.atom"))["title"] == "Atom"
    assert any("ku.nb2c.atom" in warning for warning in outcome.warnings), outcome.warnings
    assert await _uids_titled(d, "Mine") == []  # positive control: her own deletion ran
    assert len(await _uids_titled(d, "Keeper")) == 1


# ---------------------------------------------------------------------------
# Part 4 — a personal Activity file's frontmatter targets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("door", DOORS)
async def test_frontmatter_targets_link_only_the_owners_or_shared_content(env, door) -> None:
    d = env["driver"]
    _write(env["content"] / "atom.md", "---\ntype: ku\nuid: ku.nb2c.atom\ntitle: Atom\n---\n\nx\n")
    await _sync(env, "content", "directory")
    _write(env["bob"] / "knowledge" / "secret.md", _md("task", "Bob secret", "uid: task.secret\n"))
    _write(env["bob"] / "knowledge" / "bgoal.md", _md("goal", "Bob goal", "uid: goal.bgoal\n"))
    await _sync(env, "bob", "directory")
    _write(env["alice"] / "knowledge" / "agoal.md", _md("goal", "Alice goal", "uid: goal.agoal\n"))
    _write(
        env["alice"] / "knowledge" / "atask.md",
        "---\ntype: task\nuid: task.atask\ntitle: Alice task\n"
        "fulfills_goal_uid: goal.bgoal\n"
        "connections:\n  fulfills_goal: [goal.bgoal, goal.agoal]\n"
        "  depends_on: [task.secret]\n  applies_knowledge: [ku.nb2c.atom]\n"
        "---\n\nbody\n",
    )
    _write(
        env["alice"] / "knowledge" / "other.md",
        "---\ntype: task\nuid: task.other\ntitle: Other\n"
        "connections:\n  fulfills_goal: [goal.bgoal]\n---\n\nbody\n",
    )

    outcome = await _sync(env, "alice", door)

    assert await _edge_types(d, "task.atask", "goal.bgoal") == []
    assert await _edge_types(d, "task.atask", "task.secret") == []
    assert await _edge_types(d, "task.other", "goal.bgoal") == []
    # Positive controls: the owner's own goal and shared content still link.
    assert await _edge_types(d, "task.atask", "goal.agoal") == ["FULFILLS_GOAL"]
    assert await _edge_types(d, "task.atask", "ku.nb2c.atom") == ["APPLIES_KNOWLEDGE"]
    # The goal column is one fact with the edge — never another user's goal.
    columns = await _q(
        d,
        "MATCH (t:Task) WHERE t.uid IN ['task.atask', 'task.other'] "
        "RETURN t.uid AS uid, t.fulfills_goal_uid AS goal ORDER BY uid",
    )
    assert columns == [
        {"uid": "task.atask", "goal": "goal.agoal"},
        {"uid": "task.other", "goal": None},
    ]
    # A refused target reads exactly like a missing one.
    for warning in outcome.warnings:
        _assert_never_names_owner(warning)


@pytest.mark.parametrize("door", DOORS)
async def test_a_draft_target_draws_no_edge_and_reads_like_a_missing_one(env, door) -> None:
    d = env["driver"]
    _write(env["content"] / "atom.md", "---\ntype: ku\nuid: ku.nb2f.atom\ntitle: Atom\n---\n\nx\n")
    _write(
        env["content"] / "draft.md",
        "---\ntype: ku\nuid: ku.nb2f.draft\ntitle: Draft\npublication_state: draft\n---\n\nx\n",
    )
    await _sync(env, "content", "directory")
    assert (await _q(d, "MATCH (k:Ku {uid: 'ku.nb2f.draft'}) RETURN k.publication_state AS s")) == [
        {"s": "draft"}
    ]
    _write(
        env["alice"] / "knowledge" / "a.md",
        "---\ntype: task\nuid: task.a\ntitle: A\n"
        "connections:\n  applies_knowledge: [ku.nb2f.draft, ku.nb2f.atom]\n---\n\nx\n",
    )
    _write(
        env["alice"] / "knowledge" / "b.md",
        "---\ntype: task\nuid: task.b\ntitle: B\n"
        "connections:\n  applies_knowledge: [ku.nb2f.nowhere]\n---\n\nx\n",
    )

    outcome = await _sync(env, "alice", door)

    assert await _edge_types(d, "task.a", "ku.nb2f.draft") == []
    # Positive control: a published Ku in the same list still links.
    assert await _edge_types(d, "task.a", "ku.nb2f.atom") == ["APPLIES_KNOWLEDGE"]
    draft = [w for w in outcome.warnings if "ku.nb2f.draft" in w]
    missing = [w for w in outcome.warnings if "ku.nb2f.nowhere" in w]
    assert len(draft) == 1 and len(missing) == 1, outcome.warnings
    assert draft[0].replace("task.a", "X").replace("ku.nb2f.draft", "Y") == missing[0].replace(
        "task.b", "X"
    ).replace("ku.nb2f.nowhere", "Y")


async def test_a_source_path_step_names_only_a_path_step(env) -> None:
    """``source_path_step_uid`` lands on the node as written; its reader resolves a PathStep only.

    Every activity detail page renders the title its ``source_path_step_uid`` names
    ("From learning step: …"). A vault file can write any uid there, so the reader —
    not the door — is where another user's entity stops: a uid that is not a
    PathStep renders nothing, exactly like a uid that names nothing.
    """
    from adapters.persistence.neo4j.connection_fetch_backend import ConnectionFetchBackend
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

    d = env["driver"]
    _write(env["content"] / "step.md", _md("path_step", "A real step", "uid: ps.nb2c.step\n"))
    await _sync(env, "content", "directory")
    _write(env["bob"] / "knowledge" / "secret.md", _md("task", "Bob secret", "uid: task.secret\n"))
    await _sync(env, "bob", "directory")
    _write(
        env["alice"] / "knowledge" / "a.md",
        _md("task", "Points at bob", "uid: task.a\nsource_path_step_uid: task.secret\n"),
    )
    await _sync(env, "alice", "reconciler")

    fetch = ConnectionFetchBackend(Neo4jQueryExecutor(d))
    assert await fetch.fetch_source_pathstep("task.secret", ALICE) is None
    assert await fetch.fetch_source_pathstep("task.nowhere", ALICE) is None
    # Positive control: a real PathStep still resolves.
    assert await fetch.fetch_source_pathstep("ps.nb2c.step", ALICE) == {
        "uid": "ps.nb2c.step",
        "title": "A real step",
    }


async def test_refused_target_reads_like_a_missing_one(env) -> None:
    """The warning for another user's goal is the warning for a goal that does not exist."""
    _write(env["bob"] / "knowledge" / "bgoal.md", _md("goal", "Bob goal", "uid: goal.bgoal\n"))
    await _sync(env, "bob", "directory")
    _write(
        env["alice"] / "knowledge" / "a.md",
        "---\ntype: task\nuid: task.a\ntitle: A\nconnections:\n  fulfills_goal: [goal.bgoal]\n---\n\nx\n",
    )
    _write(
        env["alice"] / "knowledge" / "b.md",
        "---\ntype: task\nuid: task.b\ntitle: B\nconnections:\n  fulfills_goal: [goal.nowhere]\n---\n\nx\n",
    )

    outcome = await _sync(env, "alice", "reconciler")

    foreign = [w for w in outcome.warnings if "goal.bgoal" in w]
    missing = [w for w in outcome.warnings if "goal.nowhere" in w]
    assert len(foreign) == 1 and len(missing) == 1, outcome.warnings
    assert foreign[0].replace("task.a", "X").replace("goal.bgoal", "Y") == missing[0].replace(
        "task.b", "X"
    ).replace("goal.nowhere", "Y")


# ---------------------------------------------------------------------------
# Content vault — Edge files join two entities; a Group is the vault's own
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("door", DOORS)
async def test_content_edge_files_never_write_access_edges(env, door) -> None:
    d = env["driver"]
    _write(env["bob"] / "knowledge" / "bgoal.md", _md("goal", "Bob goal", "uid: goal.bgoal\n"))
    await _sync(env, "bob", "directory")
    async with d.session() as session:
        await session.run(
            "CREATE (:Group {uid: 'group.nb2c-class', name: 'Class', is_active: true})"
        )
    c = env["content"]
    _write(c / "a.md", "---\ntype: ku\nuid: ku.nb2c.a\ntitle: A\n---\n\nx\n")
    _write(c / "b.md", "---\ntype: ku\nuid: ku.nb2c.b\ntitle: B\n---\n\nx\n")
    lateral = (
        "ENABLES",
        "RELATED_TO",
        "PREREQUISITE_FOR",
        "COMPLEMENTARY_TO",
        "SIMILAR_TO",
        "BLOCKS",
        "EXACERBATED_BY",
    )
    for rel in lateral:
        _write(
            c / f"lat_{rel.lower()}.yaml",
            f"type: Edge\nfrom: ku.nb2c.a\nto: ku.nb2c.b\nrelationship: {rel}\n",
        )
    access = {
        "acc_owns_user": (str(ADMIN), "goal.bgoal", "OWNS"),
        "acc_owns_entities": ("ku.nb2c.a", "ku.nb2c.b", "OWNS"),
        "acc_shares": (str(ADMIN), "goal.bgoal", "SHARES_WITH"),
        "acc_member": (str(BOB), "group.nb2c-class", "MEMBER_OF"),
        "acc_group_share": ("ku.nb2c.a", "group.nb2c-class", "SHARED_WITH_GROUP"),
        "acc_submit": ("ku.nb2c.a", "group.nb2c-class", "SUBMITTED_TO_GROUP"),
        "acc_to_user": ("ku.nb2c.a", str(BOB), "RELATED_TO"),
        # An access type between two entities grants nothing, and is still
        # never written: an Edge file authors no ownership, sharing or membership.
        "acc_shares_entities": ("ku.nb2c.a", "ku.nb2c.b", "SHARES_WITH"),
        "acc_member_entities": ("ku.nb2c.a", "ku.nb2c.b", "MEMBER_OF"),
        "acc_group_share_entities": ("ku.nb2c.a", "ku.nb2c.b", "SHARED_WITH_GROUP"),
        "acc_submit_entities": ("ku.nb2c.a", "ku.nb2c.b", "SUBMITTED_TO_GROUP"),
    }
    for name, (f, t, rel) in access.items():
        _write(c / f"{name}.yaml", f"type: Edge\nfrom: {f}\nto: {t}\nrelationship: {rel}\n")

    outcome = await _sync(env, "content", door)

    for name, (f, t, rel) in access.items():
        assert rel not in await _edge_types(d, f, t), name
        reported = {**outcome.refused, **outcome.failed}
        assert any(name in key or name in reason for key, reason in reported.items()), (
            name,
            reported,
        )
    assert (await _node(d, "goal.bgoal"))["owners"] == [str(BOB)]
    # Positive control: every live lateral type the content vault authors is written.
    assert await _edge_types(d, "ku.nb2c.a", "ku.nb2c.b") == sorted(lateral)


@pytest.mark.parametrize("door", DOORS)
async def test_content_group_file_is_owned_by_the_vaults_owner(env, door) -> None:
    d = env["driver"]
    _write(
        env["content"] / "grp.md", f"---\ntype: group\nname: A class\nowner_uid: {BOB}\n---\n\nx\n"
    )

    outcome = await _sync(env, "content", door)

    assert outcome.refused == {} and outcome.failed == {}, (outcome.refused, outcome.failed)
    group = await _node(d, "group.grp")
    assert group["owner_uid"] == str(ADMIN) and group["owners"] == [str(ADMIN)], group


# ---------------------------------------------------------------------------
# Preview — says what the sync will do
# ---------------------------------------------------------------------------


async def test_preview_reports_refused_files_as_ignored_with_reason(env) -> None:
    k = env["alice"] / "knowledge"
    _write(k / "edge.yaml", "type: Edge\nfrom: a\nto: b\nrelationship: RELATED_TO\n")
    _write(k / "ku.md", _md("ku", "A ku"))
    _write(k / "grp.md", "---\ntype: group\nname: G\n---\n\nx\n")
    _write(k / "task.md", _md("task", "A task"))

    preview = await env["reconciler"].preview(VaultKind.PERSONAL, ALICE)

    assert preview.is_ok, preview
    value = preview.value
    assert value.would_ingest_count == 1, value
    assert value.would_ignore_count == 3, value
    joined = "\n".join(value.would_ignore_examples)
    for name in ("edge.yaml", "ku.md", "grp.md"):
        assert name in joined, joined

    # The sync then does what the preview said.
    outcome = await _sync(env, "alice", "reconciler")
    assert set(outcome.refused) == {"edge.yaml", "ku.md", "grp.md"}, outcome.refused
