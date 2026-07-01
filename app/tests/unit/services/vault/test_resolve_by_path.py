"""VaultRegistry.resolve_by_path — owner is a function of the vault, not the caller.

These tests pin the by-path resolution that makes ingest ownership
surface-independent (ADR-070): the personal descriptor is only ever returned for
a path *inside* the personal root (stamped with the acting user), the content
descriptor owns its own root plus every path under neither vault, and a registry
with no descriptors fails so the caller falls back to its default owner.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from core.models.type_hints import UserUID
from core.ports.vault_bridge_protocol import VaultBridgePort
from core.services.ingestion.config import SyncAllowlist
from core.services.vault.vault_descriptor import (
    VaultDescriptor,
    VaultKind,
    VaultRegistry,
)

_ACTING = UserUID("user_alpha")
_CONTENT_OWNER = UserUID("user_admin")
_PLACEHOLDER = UserUID("user_system")


def _bridge() -> VaultBridgePort:
    """A do-nothing bridge — resolve_by_path never calls it."""
    return cast("VaultBridgePort", object())


def _wall(root: Path) -> SyncAllowlist:
    return SyncAllowlist(governed_root=root.resolve(), allowed_dirs=frozenset())


def _content(root: Path) -> VaultDescriptor:
    return VaultDescriptor(
        kind=VaultKind.CONTENT,
        root=root,
        owner_uid=_CONTENT_OWNER,
        allowlist=_wall(root),
        bridge=_bridge(),
        supports_task_round_trip=False,
    )


def _personal(root: Path) -> VaultDescriptor:
    return VaultDescriptor(
        kind=VaultKind.PERSONAL,
        root=root,
        owner_uid=_PLACEHOLDER,  # template placeholder; stamped at resolve
        allowlist=_wall(root),
        bridge=_bridge(),
        supports_task_round_trip=True,
    )


def test_personal_root_stamps_acting_user(tmp_path: Path) -> None:
    content_root = tmp_path / "content"
    personal_root = tmp_path / "personal"
    registry = VaultRegistry(content=_content(content_root), personal=_personal(personal_root))

    result = registry.resolve_by_path(personal_root / "knowledge" / "note.md", _ACTING)

    assert result.is_ok
    descriptor = result.value
    assert descriptor.kind is VaultKind.PERSONAL
    assert descriptor.owner_uid == _ACTING  # acting user, not the placeholder


def test_content_root_ignores_acting_hint(tmp_path: Path) -> None:
    content_root = tmp_path / "content"
    personal_root = tmp_path / "personal"
    registry = VaultRegistry(content=_content(content_root), personal=_personal(personal_root))

    result = registry.resolve_by_path(content_root / "ku" / "atom.md", _ACTING)

    assert result.is_ok
    descriptor = result.value
    assert descriptor.kind is VaultKind.CONTENT
    assert descriptor.owner_uid == _CONTENT_OWNER  # hint ignored


def test_path_under_neither_root_falls_back_to_content(tmp_path: Path) -> None:
    content_root = tmp_path / "content"
    personal_root = tmp_path / "personal"
    registry = VaultRegistry(content=_content(content_root), personal=_personal(personal_root))

    # An admin staging dir outside both vaults — must NOT be a random user's
    # USER_OWNED descriptor; the safe default is the content acts-as owner.
    result = registry.resolve_by_path(tmp_path / "elsewhere" / "stray.md", _ACTING)

    assert result.is_ok
    assert result.value.kind is VaultKind.CONTENT
    assert result.value.owner_uid == _CONTENT_OWNER


def test_coincident_roots_personal_wins(tmp_path: Path) -> None:
    # Combined-root config (default .env before split): personal precedence means
    # the acting user owns their own entries rather than the content acts-as owner.
    shared_root = tmp_path / "vault"
    registry = VaultRegistry(content=_content(shared_root), personal=_personal(shared_root))

    result = registry.resolve_by_path(shared_root / "note.md", _ACTING)

    assert result.is_ok
    assert result.value.kind is VaultKind.PERSONAL
    assert result.value.owner_uid == _ACTING


def test_nested_content_under_personal_is_combined_vault(tmp_path: Path) -> None:
    # INGESTION_PATH nested *under* VAULT_ROOT is a COMBINED vault (consistent with
    # build_sync_allowlist, which opens such a vault whole): everything under the
    # personal root is the user's own. USER_OWNED files → acting user; SHARED
    # curriculum still drops its owner at persist regardless.
    personal_root = tmp_path / "vault"
    content_root = personal_root / "curriculum"
    registry = VaultRegistry(content=_content(content_root), personal=_personal(personal_root))

    content_path = registry.resolve_by_path(content_root / "ku" / "atom.md", _ACTING)
    personal_path = registry.resolve_by_path(personal_root / "notes" / "day.md", _ACTING)

    assert content_path.is_ok and content_path.value.kind is VaultKind.PERSONAL
    assert content_path.value.owner_uid == _ACTING
    assert personal_path.is_ok and personal_path.value.kind is VaultKind.PERSONAL
    assert personal_path.value.owner_uid == _ACTING


def test_content_only_path_when_personal_nested_under_content(tmp_path: Path) -> None:
    # Personal nested under content. A personal-root path is the user's own; a path
    # under content but outside the personal root is content/SHARED.
    content_root = tmp_path / "vault"
    personal_root = content_root / "me"
    registry = VaultRegistry(content=_content(content_root), personal=_personal(personal_root))

    personal_path = registry.resolve_by_path(personal_root / "notes" / "day.md", _ACTING)
    content_path = registry.resolve_by_path(content_root / "ku" / "atom.md", _ACTING)

    assert personal_path.is_ok and personal_path.value.kind is VaultKind.PERSONAL
    assert personal_path.value.owner_uid == _ACTING
    assert content_path.is_ok and content_path.value.kind is VaultKind.CONTENT
    assert content_path.value.owner_uid == _CONTENT_OWNER


def test_no_descriptors_fails(tmp_path: Path) -> None:
    registry = VaultRegistry(content=None, personal=None)

    result = registry.resolve_by_path(tmp_path / "anything.md", _ACTING)

    assert result.is_error


def test_content_only_registry_owns_all_paths(tmp_path: Path) -> None:
    # No personal descriptor: every path resolves to the content acts-as owner,
    # never accidentally attributed to the acting user.
    content_root = tmp_path / "content"
    registry = VaultRegistry(content=_content(content_root), personal=None)

    inside = registry.resolve_by_path(content_root / "x.md", _ACTING)
    outside = registry.resolve_by_path(tmp_path / "other" / "y.md", _ACTING)

    assert inside.is_ok and inside.value.owner_uid == _CONTENT_OWNER
    assert outside.is_ok and outside.value.owner_uid == _CONTENT_OWNER


def test_personal_only_registry_walls_out_of_root(tmp_path: Path) -> None:
    # No content descriptor + a path outside the personal root → Result.fail, so
    # a personal descriptor is NEVER returned for an out-of-root path.
    personal_root = tmp_path / "personal"
    registry = VaultRegistry(content=None, personal=_personal(personal_root))

    inside = registry.resolve_by_path(personal_root / "in.md", _ACTING)
    outside = registry.resolve_by_path(tmp_path / "out.md", _ACTING)

    assert inside.is_ok and inside.value.owner_uid == _ACTING
    assert outside.is_error


# ---------------------------------------------------------------------------
# nested_vault_roots — the multi-vault-span guard
# ---------------------------------------------------------------------------


def test_nested_roots_empty_for_sibling_roots(tmp_path: Path) -> None:
    # Live split-root config: content + personal are siblings — scanning either
    # root sweeps only itself.
    content_root = tmp_path / "content"
    personal_root = tmp_path / "personal"
    registry = VaultRegistry(content=_content(content_root), personal=_personal(personal_root))

    assert registry.nested_vault_roots(content_root) == []
    assert registry.nested_vault_roots(personal_root) == []


def test_nested_roots_empty_for_coincident_roots(tmp_path: Path) -> None:
    # Combined-root default: content == personal == scanned dir — a root is not a
    # strict descendant of itself, so no span.
    shared_root = tmp_path / "vault"
    registry = VaultRegistry(content=_content(shared_root), personal=_personal(shared_root))

    assert registry.nested_vault_roots(shared_root) == []


def test_nested_roots_detects_ancestor_scan(tmp_path: Path) -> None:
    # Scanning a genuine ancestor of both roots sweeps both vaults → flagged.
    content_root = tmp_path / "obsidian" / "content"
    personal_root = tmp_path / "obsidian" / "personal"
    registry = VaultRegistry(content=_content(content_root), personal=_personal(personal_root))

    nested = registry.nested_vault_roots(tmp_path / "obsidian")

    assert set(nested) == {content_root.resolve(), personal_root.resolve()}


def test_nested_roots_empty_for_subdir_scan(tmp_path: Path) -> None:
    # Scanning inside a vault (a subdir) nests no other root.
    content_root = tmp_path / "content"
    personal_root = tmp_path / "personal"
    registry = VaultRegistry(content=_content(content_root), personal=_personal(personal_root))

    assert registry.nested_vault_roots(content_root / "ku") == []


# ---------------------------------------------------------------------------
# conflicting_nested_roots — the owner-uniformity guard decision
# ---------------------------------------------------------------------------


def test_conflicting_roots_empty_for_split_siblings(tmp_path: Path) -> None:
    # Sibling vaults nest nothing → any single-root scan is owner-uniform.
    content_root = tmp_path / "content"
    personal_root = tmp_path / "personal"
    registry = VaultRegistry(content=_content(content_root), personal=_personal(personal_root))

    assert registry.conflicting_nested_roots(content_root, _ACTING) == []
    assert registry.conflicting_nested_roots(personal_root, _ACTING) == []


def test_conflicting_roots_ancestor_scan_rejected(tmp_path: Path) -> None:
    # Scanning an ancestor of both siblings: the nested personal root resolves to
    # PERSONAL, the ancestor directory (fallback) to CONTENT → conflict.
    content_root = tmp_path / "obsidian" / "content"
    personal_root = tmp_path / "obsidian" / "personal"
    registry = VaultRegistry(content=_content(content_root), personal=_personal(personal_root))

    conflicting = registry.conflicting_nested_roots(tmp_path / "obsidian", _ACTING)

    assert personal_root.resolve() in conflicting


def test_conflicting_roots_empty_for_combined_vault(tmp_path: Path) -> None:
    # Content nested under personal is a COMBINED vault: the nested content root
    # resolves to the SAME personal descriptor as the enclosing directory → no
    # conflict, so the normal nested-config personal sync is allowed.
    personal_root = tmp_path / "vault"
    content_root = personal_root / "curriculum"
    registry = VaultRegistry(content=_content(content_root), personal=_personal(personal_root))

    assert registry.conflicting_nested_roots(personal_root, _ACTING) == []


def test_conflicting_roots_personal_nested_in_content_rejected(tmp_path: Path) -> None:
    # Mirror config: personal nested under content. A CONTENT scan of the content
    # root nests the personal root, which resolves to PERSONAL ≠ CONTENT → conflict
    # (otherwise the user's private files would be stamped with the content owner).
    content_root = tmp_path / "vault"
    personal_root = content_root / "me"
    registry = VaultRegistry(content=_content(content_root), personal=_personal(personal_root))

    conflicting = registry.conflicting_nested_roots(content_root, _ACTING)

    assert conflicting == [personal_root.resolve()]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
