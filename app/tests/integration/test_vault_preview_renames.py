"""A sync preview names exactly what the sync then deletes and moves.

For a renamed file — an authored-uid file, a uid-less UserEntry note, a uid-less
personal Task, an Edge file, a content file whose uid is its file name — and for
a real deletion, the preview run before a sync reports as deleted the files whose
entity or relationship the sync removes, and as moved the renames the sync
reports, line for line. The preview writes no tracker row. After the sync, every
node the vault wrote is held by a tracker row: a rename never strands the old
node where no later sync can delete it.

Drives the real ``VaultReconciler`` (preview, then sync) over temp content and
personal vaults and the container.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.vault.filesystem_adapter import FilesystemVaultAdapter
from core.models.user.user import User, UserPreferences
from core.services.ingestion.config import build_sync_allowlist
from core.services.ingestion.ingestion_tracker import parse_edge_identity
from core.services.sharing.unified_sharing_service import UnifiedSharingService
from core.services.user_entry.user_entry_service import UserEntryService
from core.services.vault.vault_descriptor import VaultDescriptor, VaultKind, VaultRegistry
from core.services.vault.vault_reconciler import VaultReconciler, VaultSyncPreview
from core.utils.result_simplified import Result
from tests.helpers.production_backends import build_ingestion_service, build_production_backends
from tests.helpers.seed_uids import seed_user_uid

if TYPE_CHECKING:
    from _pytest.mark.structures import ParameterSet
    from neo4j import AsyncDriver

pytestmark = pytest.mark.asyncio

MARK = "zzzpreviewmv"
OWNER = seed_user_uid(MARK)
PERSONAL_DIR = "knowledge/"

KU = "---\ntype: ku\nuid: ku.{mark}.{slug}\ntitle: Ku {slug}\n---\nBody of {slug}.\n"
KU_NAMED_BY_FILE = "---\ntype: ku\ntitle: Ku {slug}\n---\nBody of {slug}, named by its file.\n"
NOTE = (
    "---\ntype: user_entry\npipeline: knowledge\ntitle: Note {slug}\n---\n"
    + " ".join(f"thought{i}" for i in range(80))
    + "\n"
)
TASK = "---\ntype: task\ntitle: Task {slug}\n---\nTask body {slug}.\n"
DAILY = (
    "---\ntype: user_entry\npipeline: extract_activities\nmetadata:\n  entry_kind: daily\n"
    "date: 2026-08-23\n---\nA day.\n"
)
YAML_NOTE = (
    f"type: user_entry\nuid: ue.{MARK}.yaml-note\npipeline: knowledge\ntitle: A YAML note\n"
    "content: The note's own words.\n"
)
MD_NOTE = (
    f"---\ntype: user_entry\nuid: ue.{MARK}.md-note\npipeline: knowledge\ntitle: A note\n---\n"
    "The note's own words.\n"
)
EDGE = f"type: Edge\nfrom: ku.{MARK}.a\nto: ku.{MARK}.b\nrelationship: RELATED_TO\n"


@dataclass
class Vaults:
    driver: AsyncDriver
    roots: dict[VaultKind, Path]
    reconcilers: dict[VaultKind, VaultReconciler]


@pytest_asyncio.fixture
async def vaults(neo4j_driver: AsyncDriver, clean_neo4j: None, tmp_path: Path) -> Vaults:
    async with neo4j_driver.session() as session:
        await session.run("MERGE (u:User {uid: $uid}) SET u.title = $uid", uid=OWNER)
    backends = build_production_backends(neo4j_driver)
    entries = UserEntryService(
        backend=backends["user_entry_backend"],
        sharing_service=UnifiedSharingService(backend=backends["sharing_backend"]),
    )
    owner = User(uid=OWNER, title=OWNER, preferences=UserPreferences(vault_write_consent=True))
    users = Mock()
    users.get_user = AsyncMock(return_value=Result.ok(owner))
    users.get_user_zone = AsyncMock(return_value=Result.ok(owner.zone()))

    content = tmp_path / "content"
    personal = tmp_path / "personal"
    content.mkdir()
    (personal / PERSONAL_DIR).mkdir(parents=True)
    roots = {VaultKind.CONTENT: content, VaultKind.PERSONAL: personal}
    reconcilers: dict[VaultKind, VaultReconciler] = {}
    for kind, root in roots.items():
        allowlist = (
            build_sync_allowlist(root, content_root=root, gates_je_pro=False)
            if kind is VaultKind.CONTENT
            else build_sync_allowlist(root, content_root=content)
        )
        descriptor = VaultDescriptor(
            kind=kind,
            root=root,
            owner_uid=OWNER,
            allowlist=allowlist,
            bridge=FilesystemVaultAdapter(allowed_root=root),
            supports_task_round_trip=False,
        )
        registry = (
            VaultRegistry(content=descriptor, personal=None)
            if kind is VaultKind.CONTENT
            else VaultRegistry(content=None, personal=descriptor)
        )
        ingestion = build_ingestion_service(
            driver=neo4j_driver,
            default_user_uid=OWNER,
            ingestion_backend=build_production_backends(
                neo4j_driver, Neo4jQueryExecutor(neo4j_driver)
            )["ingestion_backend"],
            user_entry_service=entries,
        )
        ingestion.vault_registry = registry
        ingestion.sync_allowlist = allowlist
        reconcilers[kind] = VaultReconciler(
            registry=registry,
            unified_ingestion=ingestion,
            user_entry_service=entries,
            tasks_service=Mock(),
            user_service=users,
        )
    return Vaults(driver=neo4j_driver, roots=roots, reconcilers=reconcilers)


async def _rows(vaults: Vaults, root: Path) -> dict[str, str]:
    """Each tracker row under ``root``: vault-relative path → identity."""
    async with vaults.driver.session() as session:
        result = await session.run(
            "MATCH (m:IngestionMetadata) WHERE m.file_path STARTS WITH $root "
            "RETURN m.file_path AS path, m.entity_uid AS uid",
            root=str(root.resolve()) + "/",
        )
        prefix = str(root.resolve()) + "/"
        return {row["path"].removeprefix(prefix): row["uid"] async for row in result}


async def _exists(vaults: Vaults, identity: str) -> bool:
    """Whether the node — or, for an edge identity, the relationship — is in the graph."""
    edge = parse_edge_identity(identity)
    async with vaults.driver.session() as session:
        if edge is None:
            result = await session.run(
                "MATCH (n:Entity {uid: $uid}) RETURN count(n) AS n", uid=identity
            )
        else:
            result = await session.run(
                f"MATCH (:Entity {{uid: $a}})-[r:{edge[1]}]->(:Entity {{uid: $b}}) "
                "RETURN count(r) AS n",
                a=edge[0],
                b=edge[2],
            )
        record = await result.single()
        return record is not None and record["n"] > 0


async def _vault_nodes(vaults: Vaults) -> set[str]:
    async with vaults.driver.session() as session:
        result = await session.run(
            "MATCH (n:Entity) WHERE n.uid CONTAINS $mark OR n.user_uid = $owner "
            "RETURN n.uid AS uid",
            mark=MARK,
            owner=OWNER,
        )
        return {row["uid"] async for row in result}


Change = Callable[[Path], None]


def _write(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (root / name).write_text(text)


def _rename(old: str, new: str, *, edit: str = "") -> Change:
    def change(root: Path) -> None:
        text = (root / old).read_text()
        (root / old).unlink()
        (root / new).write_text(text + edit)

    return change


def _delete(name: str) -> Change:
    def change(root: Path) -> None:
        (root / name).unlink()

    return change


def _kus() -> dict[str, str]:
    return {f"{slug}.md": KU.format(mark=MARK, slug=slug) for slug in ("a", "b", "c")}


def _notes(directory: str) -> dict[str, str]:
    return {f"{directory}{slug}.md": NOTE.replace("{slug}", slug) for slug in ("x", "y", "z")}


@dataclass(frozen=True)
class Run:
    """One preview, then one sync, over the same change."""

    would_delete: set[str]  # the preview's would-delete paths, entity and edge files
    deleted: set[str]  # the tracked paths whose node or relationship the sync removed
    preview: VaultSyncPreview
    moves: list[str]  # the sync's move lines
    untracked: set[str]  # vault nodes no tracker row holds after the sync


async def _preview_then_sync(
    vaults: Vaults, kind: VaultKind, files: dict[str, str], change: Change
) -> Run:
    root = vaults.roots[kind]
    reconciler = vaults.reconcilers[kind]
    _write(root, files)
    first = await reconciler.sync(kind, OWNER)
    assert first.is_ok, first
    assert not first.value.errors, first.value.errors
    rows_before = await _rows(vaults, root)
    change(root)

    preview = await reconciler.preview(kind, OWNER)
    assert preview.is_ok, preview
    assert await _rows(vaults, root) == rows_before

    synced = await reconciler.sync(kind, OWNER)
    assert synced.is_ok, synced
    assert not synced.value.errors, synced.value.errors
    return Run(
        would_delete={
            *preview.value.would_delete_entity_examples,
            *preview.value.would_delete_edge_examples,
        },
        deleted={path for path, uid in rows_before.items() if not await _exists(vaults, uid)},
        preview=preview.value,
        moves=synced.value.moves,
        untracked=await _vault_nodes(vaults) - set((await _rows(vaults, root)).values()),
    )


RENAMES: list[ParameterSet] = [
    pytest.param(VaultKind.CONTENT, _kus(), _rename("c.md", "c2.md"), id="authored-uid"),
    pytest.param(
        VaultKind.CONTENT,
        _kus(),
        _rename("c.md", "c2.md", edit="More.\n"),
        id="authored-uid-edited",
    ),
    pytest.param(
        VaultKind.CONTENT,
        _notes(""),
        _rename("z.md", "z2.md"),
        id="uidless-note-content",
    ),
    pytest.param(
        VaultKind.CONTENT,
        _notes(""),
        _rename("z.md", "z2.md", edit="one more line\n"),
        id="uidless-note-content-edited",
    ),
    pytest.param(
        VaultKind.PERSONAL,
        _notes(PERSONAL_DIR),
        _rename(f"{PERSONAL_DIR}z.md", f"{PERSONAL_DIR}z2.md"),
        id="uidless-note-personal",
    ),
    pytest.param(
        VaultKind.PERSONAL,
        _notes(PERSONAL_DIR),
        _rename(f"{PERSONAL_DIR}z.md", f"{PERSONAL_DIR}z2.md", edit="one more line\n"),
        id="uidless-note-personal-edited",
    ),
    pytest.param(
        VaultKind.PERSONAL,
        {f"{PERSONAL_DIR}{s}.md": TASK.format(slug=s) for s in "pq"},
        _rename(f"{PERSONAL_DIR}q.md", f"{PERSONAL_DIR}q2.md"),
        id="uidless-task-personal",
    ),
    pytest.param(
        VaultKind.PERSONAL,
        {**_notes(PERSONAL_DIR), f"{PERSONAL_DIR}2026-08-23.md": DAILY},
        _rename(f"{PERSONAL_DIR}2026-08-23.md", f"{PERSONAL_DIR}day.md", edit="Then more.\n"),
        id="periodic-note-personal-edited",
    ),
    pytest.param(
        VaultKind.CONTENT,
        {**_kus(), "note.yaml": YAML_NOTE},
        _rename("note.yaml", "note2.yaml", edit="tags: [moved]\n"),
        id="yaml-user-entry-edited",
    ),
    pytest.param(
        VaultKind.CONTENT,
        {**_kus(), "edge.yaml": EDGE},
        _rename("edge.yaml", "edge2.yaml"),
        id="edge",
    ),
    pytest.param(
        VaultKind.CONTENT,
        {**_kus(), "edge.yaml": EDGE},
        _rename("edge.yaml", "edge2.yaml", edit="# moved\n"),
        id="edge-edited",
    ),
]


@pytest.mark.parametrize(("kind", "files", "change"), RENAMES)
async def test_a_rename_the_sync_keeps_is_previewed_as_a_move(
    vaults: Vaults, kind: VaultKind, files: dict[str, str], change: Change
) -> None:
    run = await _preview_then_sync(vaults, kind, files, change)

    assert run.would_delete == run.deleted == set()
    assert run.untracked == set()
    assert len(run.moves) == 1
    assert list(run.preview.would_move_examples) == run.moves


NAMED_BY_FILE = {
    f"{MARK}-{slug}.md": KU_NAMED_BY_FILE.format(slug=slug) for slug in ("s1", "s2", "s3")
}


@pytest.mark.parametrize("edit", ["", "More.\n"], ids=["pure", "edited"])
async def test_a_file_named_uid_rename_deletes_the_old_node_and_is_previewed_so(
    vaults: Vaults, edit: str
) -> None:
    run = await _preview_then_sync(
        vaults,
        VaultKind.CONTENT,
        NAMED_BY_FILE,
        _rename(f"{MARK}-s3.md", f"{MARK}-s3-renamed.md", edit=edit),
    )

    assert run.would_delete == run.deleted == {f"{MARK}-s3.md"}
    assert run.untracked == set()
    assert run.moves == []
    assert run.preview.would_move_examples == ()


DELETIONS: list[ParameterSet] = [
    pytest.param(VaultKind.CONTENT, _notes(""), _delete("z.md"), "z.md", id="content-deleted"),
    pytest.param(
        VaultKind.PERSONAL,
        _notes(PERSONAL_DIR),
        _delete(f"{PERSONAL_DIR}z.md"),
        f"{PERSONAL_DIR}z.md",
        id="personal-deleted",
    ),
    pytest.param(
        VaultKind.PERSONAL,
        {f"{PERSONAL_DIR}{s}.md": TASK.format(slug=s) for s in "pq"},
        _rename(f"{PERSONAL_DIR}q.md", f"{PERSONAL_DIR}q2.md", edit="A new line.\n"),
        f"{PERSONAL_DIR}q.md",
        id="uidless-task-renamed-and-edited",
    ),
]


@pytest.mark.parametrize(("kind", "files", "change", "gone"), DELETIONS)
async def test_a_deletion_the_sync_makes_is_previewed_as_a_deletion(
    vaults: Vaults, kind: VaultKind, files: dict[str, str], change: Change, gone: str
) -> None:
    run = await _preview_then_sync(vaults, kind, files, change)

    assert run.would_delete == run.deleted == {gone}
    assert run.untracked == set()
    assert run.moves == []
    assert run.preview.would_move_examples == ()


def _reorganise(root: Path) -> None:
    """Every tracked file leaves its path: two move into a folder, one is deleted."""
    (root / "moved").mkdir()
    for slug in ("a", "b"):
        (root / "moved" / f"{slug}.md").write_text((root / f"{slug}.md").read_text())
        (root / f"{slug}.md").unlink()
    (root / "c.md").unlink()


async def test_a_reorganisation_that_empties_every_tracked_path_is_previewed_as_the_sync_runs(
    vaults: Vaults,
) -> None:
    run = await _preview_then_sync(vaults, VaultKind.CONTENT, _kus(), _reorganise)

    assert run.would_delete == run.deleted == {"c.md"}
    assert run.preview.refusal_warning is None
    assert run.untracked == set()
    assert sorted(run.moves) == ["a.md → moved/a.md", "b.md → moved/b.md"]
    assert sorted(run.preview.would_move_examples) == sorted(run.moves)


def _rename_to_a_refused_pipeline(root: Path) -> None:
    text = (root / "note.md").read_text().replace("pipeline: knowledge", "pipeline: bogus")
    (root / "note.md").unlink()
    (root / "note2.md").write_text(text)


async def test_a_renamed_note_the_sync_refuses_is_previewed_as_a_deletion_and_an_ignore(
    vaults: Vaults,
) -> None:
    run = await _preview_then_sync(
        vaults, VaultKind.CONTENT, {**_kus(), "note.md": MD_NOTE}, _rename_to_a_refused_pipeline
    )

    assert run.would_delete == run.deleted == {"note.md"}
    assert [line.split(" — ")[0] for line in run.preview.would_ignore_examples] == ["note2.md"]
    assert run.untracked == set()
    assert run.moves == []
    assert run.preview.would_move_examples == ()


def _rename_onto_a_tracked_path(root: Path) -> None:
    (root / "b.md").write_text((root / "a.md").read_text())
    (root / "a.md").unlink()


async def test_a_file_renamed_onto_a_tracked_path_is_previewed_as_the_sync_reports_it(
    vaults: Vaults,
) -> None:
    run = await _preview_then_sync(vaults, VaultKind.CONTENT, _kus(), _rename_onto_a_tracked_path)

    assert run.would_delete == run.deleted == set()
    assert run.moves == ["a.md → b.md"]
    assert list(run.preview.would_move_examples) == run.moves
