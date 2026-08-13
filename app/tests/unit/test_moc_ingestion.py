"""MOC ingestion — ``moc: true`` body links → ORGANIZES edges (parse + wiring).

Pins the MOC ingestion arc's PR-1 seams:
1. Link extraction — both Obsidian styles (wiki + markdown), URL-encoded paths,
   alias/heading forms, dedupe, document-position order, non-note skips.
2. Preparer hook — ``moc: true`` stashes the transient ``_moc_links`` key;
   unflagged files don't get it.
3. UID acceptance — the batch door no longer prefix-rejects an authored
   UserEntry uid (``moc:worldview``, the seed fixture's actual failure);
   the user-entry door normalizes authored uids colon→dot while derived
   periodic uids keep their colon-form calendar contract.
4. The service edge pass — resolution winner selection, self-link skip,
   ordered targets, and the two vault postures (personal silent /
   content Arc E warnings).

See: plans/moc-knowledge-channel-design-notes.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.models.enums.entity_enums import EntityType
from core.models.enums.pipeline import Pipeline
from core.services.ingestion.batch import parse_file_sync
from core.services.ingestion.moc_links import (
    extract_moc_link_suffixes,
    frontmatter_organizes_targets,
)
from core.services.ingestion.preparer import prepare_entity_data
from core.services.ingestion.user_entry_ingestion import build_user_entry_request
from core.services.ingestion.validator import validate_uid_format
from core.utils.result_simplified import Result

# ============================================================================
# 1. Link extraction (moc_links.py)
# ============================================================================


class TestExtractMocLinkSuffixes:
    def test_wiki_link_basic(self):
        assert extract_moc_link_suffixes("[[my note]]") == ["/my note.md"]

    def test_wiki_link_alias_and_heading(self):
        body = "[[target|shown text]] then [[other#section]] and [[both#h|alias]]"
        assert extract_moc_link_suffixes(body) == [
            "/target.md",
            "/other.md",
            "/both.md",
        ]

    def test_wiki_link_heading_only_names_no_note(self):
        assert extract_moc_link_suffixes("[[#just a heading]]") == []

    def test_markdown_link_url_encoded(self):
        body = "[topics](topics%20-%20mind%20body.md)"
        assert extract_moc_link_suffixes(body) == ["/topics - mind body.md"]

    def test_markdown_link_parentheses_in_filename(self):
        body = "[skuel theme](skuel%20-%20theme(s)%20background.md)"
        assert extract_moc_link_suffixes(body) == ["/skuel - theme(s) background.md"]

    def test_markdown_link_subfolder(self):
        assert extract_moc_link_suffixes("[d](0design/delmad.md)") == ["/0design/delmad.md"]

    def test_markdown_link_extensionless_treated_as_note(self):
        assert extract_moc_link_suffixes("[n](some note)") == ["/some note.md"]

    def test_external_urls_skipped(self):
        body = "[site](https://example.com/page.md) [mail](mailto:a@b.c) [[real]]"
        assert extract_moc_link_suffixes(body) == ["/real.md"]

    def test_images_and_attachments_skipped(self):
        body = "![alt](diagram.png) [pdf](paper.pdf) [[note]]"
        assert extract_moc_link_suffixes(body) == ["/note.md"]

    def test_parent_relative_paths_skipped(self):
        assert extract_moc_link_suffixes("[up](../outside.md)") == []

    def test_dot_slash_prefix_stripped(self):
        assert extract_moc_link_suffixes("[n](./sibling.md)") == ["/sibling.md"]

    def test_order_is_document_position_and_first_occurrence_wins(self):
        body = "\n".join(
            [
                "[a](a.md)",
                "[[b]]",
                "[a again](a.md)",  # duplicate — keeps position 0
                "[[c|alias]]",
            ]
        )
        assert extract_moc_link_suffixes(body) == ["/a.md", "/b.md", "/c.md"]

    def test_wiki_and_markdown_order_interleaves(self):
        body = "[[w1]] then [m1](m1.md) then [[w2]]"
        assert extract_moc_link_suffixes(body) == ["/w1.md", "/m1.md", "/w2.md"]

    def test_empty_and_none_bodies(self):
        assert extract_moc_link_suffixes(None) == []
        assert extract_moc_link_suffixes("") == []
        assert extract_moc_link_suffixes("no links here, just #tags and prose") == []

    def test_md_extension_kept_with_dots_in_name(self):
        body = "[c](curriculum%20-%20eal.yoga%20-%20conjuring%20points.md)"
        assert extract_moc_link_suffixes(body) == ["/curriculum - eal.yoga - conjuring points.md"]


# ============================================================================
# 2. Preparer hook (_moc_links stash)
# ============================================================================


class TestPreparerMocHook:
    def test_moc_true_stashes_ordered_suffixes(self):
        data = {"type": "ku", "uid": "ku:test", "title": "T", "moc": True}
        body = "[[first]] and [second](second.md)"
        entity = prepare_entity_data(EntityType.KU, data, body, Path("test.md"))
        assert entity["_moc_links"] == ["/first.md", "/second.md"]
        # The plain flag flows through as an inert property.
        assert entity["moc"] is True

    def test_moc_true_with_empty_body_stashes_empty_list(self):
        data = {"type": "ku", "uid": "ku:test", "title": "T", "moc": True}
        entity = prepare_entity_data(EntityType.KU, data, None, Path("test.md"))
        assert entity["_moc_links"] == []

    def test_no_moc_flag_no_stash(self):
        data = {"type": "ku", "uid": "ku:test", "title": "T"}
        entity = prepare_entity_data(EntityType.KU, data, "[[linked]]", Path("test.md"))
        assert "_moc_links" not in entity

    def test_moc_non_true_values_do_not_trigger(self):
        for value in (False, "true", 1, None):
            data = {"type": "ku", "uid": "ku:test", "title": "T", "moc": value}
            entity = prepare_entity_data(EntityType.KU, data, "[[x]]", Path("test.md"))
            assert "_moc_links" not in entity, f"moc={value!r} must not trigger the pass"

    def test_pathstep_organizes_frontmatter_is_normalized(self):
        """Colon-authored ``organizes:`` targets must normalize to dots — both
        for the rel-config edge MATCH (latent pre-existing miss) and for the
        MOC pass's protected-targets comparison."""
        data = {
            "type": "ps",
            "uid": "ps:test:map",
            "title": "T",
            "organizes": ["ku:test:fm-child"],
            "moc": True,
        }
        entity = prepare_entity_data(EntityType.PATH_STEP, data, "[[x]]", Path("map.md"))
        assert entity["organizes"] == ["ku.test.fm-child"]
        assert frontmatter_organizes_targets(entity) == ["ku.test.fm-child"]

    def test_frontmatter_organizes_targets_shapes(self):
        assert frontmatter_organizes_targets({}) == []
        assert frontmatter_organizes_targets({"organizes": "ku.single"}) == ["ku.single"]
        assert frontmatter_organizes_targets({"organizes": ["ku.a", 7, "ku.b"]}) == [
            "ku.a",
            "ku.b",
        ]


# ============================================================================
# 3. UID acceptance (the seed fixture's actual failure)
# ============================================================================


class TestUserEntryUidAcceptance:
    def test_batch_door_accepts_authored_moc_uid(self, tmp_path: Path):
        """``uid: moc:worldview`` on a user_entry file must parse, not
        prefix-reject — the batch door now mirrors the single-file door
        (which routes USER_ENTRY before uid validation)."""
        f = tmp_path / "nous topics.md"
        f.write_text(
            "---\ntype: user_entry\npipeline: knowledge\nuid: moc:worldview\n"
            "title: Worldview Taxonomy\nmoc: true\n---\n[[some topic]]\n"
        )
        entity_type, entity_data, error = parse_file_sync(f)
        assert error is None, f"batch door rejected the fixture shape: {error}"
        assert entity_type == EntityType.USER_ENTRY
        assert entity_data is not None
        assert entity_data["_moc_links"] == ["/some topic.md"]

    def test_other_types_keep_prefix_validation(self, tmp_path: Path):
        f = tmp_path / "bad.md"
        f.write_text("---\ntype: ku\nuid: moc:worldview\ntitle: T\n---\nbody\n")
        _, _entity_data, error = parse_file_sync(f)
        assert error is not None
        assert "must start with 'ku:'" in error["error"]

    def test_validate_uid_format_still_rejects_user_entry_prefix_directly(self, tmp_path: Path):
        """The validator itself is unchanged — the exemption is the batch
        door's routing decision, mirroring the single-file door."""
        result = validate_uid_format(
            EntityType.USER_ENTRY, {"uid": "moc:worldview"}, tmp_path / "f.md"
        )
        assert result.is_error


class _FakeAudienceResolver:
    """Minimal resolver for build_user_entry_request paths under test."""

    async def resolve_default_teachers(self, user_uid: Any) -> list[str]:
        return []

    async def validate_references(self, **kwargs: Any) -> Result[None]:
        return Result.ok(None)

    def validate(self, request: Any) -> Result[None]:
        return Result.ok(None)


@pytest.mark.asyncio
class TestUserEntryDoorUidNormalization:
    async def _build(self, data: dict[str, Any], file_path: Path):
        return await build_user_entry_request(
            data=data,
            file_path=file_path,
            user_uid="user_test",  # type: ignore[arg-type]
            audience_resolver=_FakeAudienceResolver(),  # type: ignore[arg-type]
            body="body text",
        )

    async def test_authored_uid_normalized_colon_to_dot(self, tmp_path: Path):
        result = await self._build(
            {"pipeline": "knowledge", "uid": "moc:worldview", "title": "T", "moc": True},
            tmp_path / "nous topics.md",
        )
        assert result.is_ok
        assert result.value.uid == "moc.worldview"
        assert result.value.pipeline == Pipeline.KNOWLEDGE

    async def test_moc_flag_rides_metadata_inert(self, tmp_path: Path):
        result = await self._build(
            {"pipeline": "knowledge", "uid": "moc:worldview", "title": "T", "moc": True},
            tmp_path / "nous topics.md",
        )
        assert result.is_ok
        assert result.value.metadata["moc"] is True

    async def test_no_moc_flag_no_metadata_marker(self, tmp_path: Path):
        result = await self._build(
            {"pipeline": "knowledge", "uid": "k:note", "title": "T"},
            tmp_path / "note.md",
        )
        assert result.is_ok
        assert "moc" not in result.value.metadata

    async def test_derived_periodic_uid_keeps_colon_form(self, tmp_path: Path):
        """The calendar routes mint ``ue:daily:{user}:{date}`` — derived
        periodic uids must NOT be normalized (existing graph contract)."""
        result = await self._build(
            {
                "pipeline": "extract_activities",
                "title": "Daily",
                "metadata": {"entry_kind": "daily"},
                "date": "2026-07-04",
            },
            tmp_path / "2026-07-04.md",
        )
        assert result.is_ok
        assert result.value.uid == "ue:daily:user_test:2026-07-04"


# ============================================================================
# 4. The service edge pass (_apply_moc_links)
# ============================================================================


class _FakeWriteBackend:
    """Records resolution/refresh calls; returns canned resolution rows."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.resolve_calls: list[tuple[list[str], str | None]] = []
        self.refresh_calls: list[tuple[str, list[str], list[str]]] = []

    async def resolve_path_suffixes(
        self, suffixes: list[str], root_prefix: str | None
    ) -> list[dict[str, Any]]:
        self.resolve_calls.append((suffixes, root_prefix))
        return self.rows

    async def refresh_moc_organizes(
        self, source_uid: str, target_uids: list[str], protected_target_uids: list[str]
    ) -> int:
        self.refresh_calls.append((source_uid, target_uids, protected_target_uids))
        return len(target_uids)


def _make_service(backend: _FakeWriteBackend) -> Any:
    from core.services.ingestion.unified_ingestion_service import UnifiedIngestionService

    return UnifiedIngestionService(
        write_backend=backend,  # type: ignore[arg-type]
        bulk_backend=object(),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
class TestApplyMocLinks:
    async def test_resolved_targets_keep_document_order(self):
        backend = _FakeWriteBackend(
            [
                {"suffix": "/b.md", "entity_uid": "ue_b", "file_path": "/vault/b.md"},
                {"suffix": "/a.md", "entity_uid": "ue_a", "file_path": "/vault/a.md"},
            ]
        )
        service = _make_service(backend)
        warnings = await service._apply_moc_links(
            "moc.test", ["/a.md", "/b.md", "/missing.md"], Path("/vault/moc.md")
        )
        assert backend.refresh_calls == [("moc.test", ["ue_a", "ue_b"], [])]
        assert warnings == []  # no registry → personal posture → silent skip

    async def test_ambiguous_suffix_picks_shortest_then_lexicographic(self):
        backend = _FakeWriteBackend(
            [
                {"suffix": "/n.md", "entity_uid": "ue_deep", "file_path": "/vault/deep/sub/n.md"},
                {"suffix": "/n.md", "entity_uid": "ue_near", "file_path": "/vault/n.md"},
            ]
        )
        service = _make_service(backend)
        await service._apply_moc_links("moc.test", ["/n.md"], Path("/vault/moc.md"))
        assert backend.refresh_calls == [("moc.test", ["ue_near"], [])]

    async def test_self_link_dropped(self):
        backend = _FakeWriteBackend(
            [
                {"suffix": "/moc.md", "entity_uid": "moc.test", "file_path": "/vault/moc.md"},
                {"suffix": "/a.md", "entity_uid": "ue_a", "file_path": "/vault/a.md"},
            ]
        )
        service = _make_service(backend)
        await service._apply_moc_links("moc.test", ["/moc.md", "/a.md"], Path("/vault/moc.md"))
        assert backend.refresh_calls == [("moc.test", ["ue_a"], [])]

    async def test_empty_links_still_refresh_to_drop_stale_edges(self):
        backend = _FakeWriteBackend([])
        service = _make_service(backend)
        await service._apply_moc_links("moc.test", [], Path("/vault/moc.md"))
        assert backend.resolve_calls == []  # nothing to resolve
        assert backend.refresh_calls == [("moc.test", [], [])]

    async def test_protected_frontmatter_targets_pass_through(self):
        """A file with BOTH ``organizes:`` frontmatter and ``moc: true`` keeps
        its frontmatter-authored edges — protected uids reach the refresh."""
        backend = _FakeWriteBackend(
            [{"suffix": "/a.md", "entity_uid": "ue_a", "file_path": "/vault/a.md"}]
        )
        service = _make_service(backend)
        await service._apply_moc_links("ps.map", ["/a.md"], Path("/vault/map.md"), ["ku.fm-child"])
        assert backend.refresh_calls == [("ps.map", ["ue_a"], ["ku.fm-child"])]

    async def test_content_vault_posture_warns_on_unresolved(self, tmp_path: Path):
        from core.services.ingestion.config import SyncAllowlist
        from core.services.vault.vault_descriptor import (
            VaultDescriptor,
            VaultKind,
            VaultRegistry,
        )

        content_root = tmp_path / "0vault"
        content_root.mkdir()
        descriptor = VaultDescriptor(
            kind=VaultKind.CONTENT,
            root=content_root,
            owner_uid="user_content",  # type: ignore[arg-type]
            allowlist=SyncAllowlist(
                governed_root=content_root, allowed_dirs=frozenset({content_root})
            ),
            bridge=None,  # type: ignore[arg-type]
            supports_task_round_trip=False,
        )
        backend = _FakeWriteBackend([])
        service = _make_service(backend)
        service.vault_registry = VaultRegistry(content=descriptor, personal=None)

        warnings = await service._apply_moc_links(
            "ps.moc-map", ["/missing.md"], content_root / "moc-map.md"
        )
        assert warnings == [
            "ps.moc-map: MOC link target '/missing.md' does not resolve to an "
            "ingested entity — ORGANIZES edge not created"
        ]
        # Resolution was scoped to the content vault root.
        assert backend.resolve_calls == [(["/missing.md"], str(content_root.resolve()))]

    async def test_personal_vault_posture_stays_silent(self, tmp_path: Path):
        from core.services.ingestion.config import SyncAllowlist
        from core.services.vault.vault_descriptor import (
            VaultDescriptor,
            VaultKind,
            VaultRegistry,
        )

        personal_root = tmp_path / "personal"
        personal_root.mkdir()
        descriptor = VaultDescriptor(
            kind=VaultKind.PERSONAL,
            root=personal_root,
            owner_uid="user_test",  # type: ignore[arg-type]
            allowlist=SyncAllowlist(
                governed_root=personal_root, allowed_dirs=frozenset({personal_root})
            ),
            bridge=None,  # type: ignore[arg-type]
            supports_task_round_trip=True,
        )
        backend = _FakeWriteBackend([])
        service = _make_service(backend)
        service.vault_registry = VaultRegistry(content=None, personal=descriptor)

        warnings = await service._apply_moc_links(
            "moc.worldview", ["/never ingested.md"], personal_root / "knowledge" / "m.md"
        )
        assert warnings == []
        assert backend.refresh_calls == [("moc.worldview", [], [])]
