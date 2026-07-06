"""VaultRegistry per-user personal roots — no code path serves another user's vault.

Pins the per-user resolution model (ADR-070 Decision 5, made real): the primary
personal vault (VAULT_ROOT) is owner-bound at compose time; every other user
resolves to their own ``{user_vaults_root}/{user_uid}/`` member vault built by
the injected factory — or ``Result.fail`` when no such directory exists. By-path
resolution attributes a member path to the member directory's user, and the
nested-root guards treat member vaults as real vault roots.
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

_PRIMARY = UserUID("user_primary")
_MEMBER = UserUID("user_member")
_STRANGER = UserUID("user_stranger")
_CONTENT_OWNER = UserUID("user_admin")


def _bridge() -> VaultBridgePort:
    return cast("VaultBridgePort", object())


def _wall(root: Path) -> SyncAllowlist:
    return SyncAllowlist(governed_root=root.resolve(), allowed_dirs=frozenset())


def _descriptor(kind: VaultKind, root: Path, owner: UserUID) -> VaultDescriptor:
    return VaultDescriptor(
        kind=kind,
        root=root,
        owner_uid=owner,
        allowlist=_wall(root),
        bridge=_bridge(),
        supports_task_round_trip=kind is VaultKind.PERSONAL,
    )


def _factory(owner_uid: UserUID, root: Path) -> VaultDescriptor:
    return _descriptor(VaultKind.PERSONAL, root, owner_uid)


def _registry(tmp_path: Path) -> tuple[VaultRegistry, Path, Path]:
    """Split-root registry + member family; returns (registry, primary_root, family_root)."""
    content_root = tmp_path / "content"
    primary_root = tmp_path / "personal"
    family_root = tmp_path / "user_vaults"
    registry = VaultRegistry(
        content=_descriptor(VaultKind.CONTENT, content_root, _CONTENT_OWNER),
        personal=_descriptor(VaultKind.PERSONAL, primary_root, _PRIMARY),
        user_vaults_root=family_root,
        personal_descriptor_factory=_factory,
    )
    return registry, primary_root, family_root


# ---------------------------------------------------------------------------
# resolve(PERSONAL, user) — by-kind
# ---------------------------------------------------------------------------


def test_bound_owner_gets_primary_root(tmp_path: Path) -> None:
    registry, primary_root, _ = _registry(tmp_path)

    result = registry.resolve(VaultKind.PERSONAL, _PRIMARY)

    assert result.is_ok
    assert result.value.root == primary_root
    assert result.value.owner_uid == _PRIMARY


def test_other_user_gets_own_member_vault_not_primary(tmp_path: Path) -> None:
    registry, primary_root, family_root = _registry(tmp_path)
    (family_root / str(_MEMBER)).mkdir(parents=True)

    result = registry.resolve(VaultKind.PERSONAL, _MEMBER)

    assert result.is_ok
    assert result.value.root == (family_root / str(_MEMBER)).resolve()
    assert result.value.owner_uid == _MEMBER
    assert result.value.root != primary_root  # never someone else's vault


def test_user_without_member_directory_fails(tmp_path: Path) -> None:
    registry, _, _ = _registry(tmp_path)  # family root exists but has no member dirs

    result = registry.resolve(VaultKind.PERSONAL, _STRANGER)

    assert result.is_error  # fail — never fall through to the primary root


def test_no_family_wired_other_user_fails(tmp_path: Path) -> None:
    registry = VaultRegistry(
        content=None,
        personal=_descriptor(VaultKind.PERSONAL, tmp_path / "personal", _PRIMARY),
    )

    assert registry.resolve(VaultKind.PERSONAL, _PRIMARY).is_ok
    assert registry.resolve(VaultKind.PERSONAL, _STRANGER).is_error


def test_unsafe_uid_never_joins_the_family_root(tmp_path: Path) -> None:
    registry, _, _ = _registry(tmp_path)
    # Even with a directory physically present at the traversal target, a
    # multi-segment / dot-dot / hidden "uid" must not resolve.
    (tmp_path / "outside").mkdir()

    for evil in ("../outside", "a/b", "..", ".", "", ".hidden"):
        result = registry.resolve(VaultKind.PERSONAL, UserUID(evil))
        assert result.is_error, f"unsafe uid {evil!r} resolved a vault"


def test_family_requires_factory_and_root_together() -> None:
    with pytest.raises(ValueError, match="together"):
        VaultRegistry(content=None, personal=None, user_vaults_root=Path("/tmp/x"))
    with pytest.raises(ValueError, match="together"):
        VaultRegistry(content=None, personal=None, personal_descriptor_factory=_factory)


# ---------------------------------------------------------------------------
# resolve_by_path — member family attribution
# ---------------------------------------------------------------------------


def test_member_path_attributed_to_member_not_caller(tmp_path: Path) -> None:
    registry, _, family_root = _registry(tmp_path)
    member_root = family_root / str(_MEMBER)
    member_root.mkdir(parents=True)

    result = registry.resolve_by_path(member_root / "notes" / "day.md", _STRANGER)

    assert result.is_ok
    assert result.value.kind is VaultKind.PERSONAL
    assert result.value.owner_uid == _MEMBER  # the directory's user, never the caller


def test_family_root_itself_is_not_a_personal_vault(tmp_path: Path) -> None:
    registry, _, family_root = _registry(tmp_path)
    family_root.mkdir(parents=True)

    result = registry.resolve_by_path(family_root, _STRANGER)

    # The umbrella belongs to no user — safe content/SHARED default.
    assert result.is_ok
    assert result.value.kind is VaultKind.CONTENT


def test_stray_file_directly_under_family_root_is_not_personal(tmp_path: Path) -> None:
    registry, _, family_root = _registry(tmp_path)
    family_root.mkdir(parents=True)
    stray = family_root / "readme.md"
    stray.write_text("not a vault")

    result = registry.resolve_by_path(stray, _STRANGER)

    assert result.is_ok
    assert result.value.kind is VaultKind.CONTENT  # no member dir → no personal owner


def test_primary_root_still_wins_over_family(tmp_path: Path) -> None:
    registry, primary_root, _ = _registry(tmp_path)

    result = registry.resolve_by_path(primary_root / "knowledge" / "n.md", _MEMBER)

    assert result.is_ok
    assert result.value.owner_uid == _PRIMARY


# ---------------------------------------------------------------------------
# nested-root guards — member vaults are real vault roots
# ---------------------------------------------------------------------------


def test_ancestor_scan_lists_member_vaults(tmp_path: Path) -> None:
    registry, primary_root, family_root = _registry(tmp_path)
    member_a = family_root / "user_a"
    member_b = family_root / "user_b"
    member_a.mkdir(parents=True)
    member_b.mkdir(parents=True)

    nested = registry.nested_vault_roots(tmp_path)

    assert member_a.resolve() in nested
    assert member_b.resolve() in nested
    assert primary_root.resolve() in nested


def test_scan_of_family_root_conflicts(tmp_path: Path) -> None:
    registry, _, family_root = _registry(tmp_path)
    member_a = family_root / "user_a"
    member_a.mkdir(parents=True)

    conflicting = registry.conflicting_nested_roots(family_root, _STRANGER)

    # Sweeping every user's vault under one owner is never sound.
    assert member_a.resolve() in conflicting


def test_scan_inside_one_member_vault_is_clean(tmp_path: Path) -> None:
    registry, _, family_root = _registry(tmp_path)
    member_a = family_root / "user_a"
    (member_a / "notes").mkdir(parents=True)
    (family_root / "user_b").mkdir(parents=True)

    assert registry.conflicting_nested_roots(member_a, _STRANGER) == []
    assert registry.conflicting_nested_roots(member_a / "notes", _STRANGER) == []


def test_member_family_nested_under_primary_is_governed_by_primary(tmp_path: Path) -> None:
    # Misconfiguration: the member family placed INSIDE the primary personal
    # root. By-path the primary template wins (everything under the primary
    # root is the bound owner's — combined-vault precedent), so a member path
    # attributes to the primary owner; the member's by-kind sync is refused by
    # the reconciler's surface-independence guard (owner mismatch), tested in
    # test_reconciler_coincident_guard.py.
    content_root = tmp_path / "content"
    primary_root = tmp_path / "personal"
    family_root = primary_root / "user_vaults"
    (family_root / "user_a").mkdir(parents=True)
    registry = VaultRegistry(
        content=_descriptor(VaultKind.CONTENT, content_root, _CONTENT_OWNER),
        personal=_descriptor(VaultKind.PERSONAL, primary_root, _PRIMARY),
        user_vaults_root=family_root,
        personal_descriptor_factory=_factory,
    )

    by_path = registry.resolve_by_path(family_root / "user_a" / "n.md", UserUID("user_a"))

    assert by_path.is_ok
    assert by_path.value.owner_uid == _PRIMARY  # enclosing vault governs
    # And the scan of the primary root is uniform — no conflicting nested roots.
    assert registry.conflicting_nested_roots(primary_root, _PRIMARY) == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
