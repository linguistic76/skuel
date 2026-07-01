"""UnifiedIngestionService._resolve_owner / _resolve_allowlist — the chokepoint.

The ingest mechanism reinterprets its ``user_uid`` argument as an acting-user
*hint* and resolves the real owner (and fail-closed wall) from the vault
descriptor governing the target path. These tests pin that behaviour on a
lightweight service instance (constructed without the heavy compose-time
dependencies) so the same file gets the same owner regardless of ingest surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from core.models.type_hints import UserUID
from core.ports.vault_bridge_protocol import VaultBridgePort
from core.services.ingestion.config import SyncAllowlist
from core.services.ingestion.unified_ingestion_service import UnifiedIngestionService
from core.services.vault.vault_descriptor import (
    VaultDescriptor,
    VaultKind,
    VaultRegistry,
)

_DEFAULT = UserUID("user_default")
_CONTENT_OWNER = UserUID("user_admin")
_ACTING = UserUID("user_beta")


def _bridge() -> VaultBridgePort:
    return cast("VaultBridgePort", object())


def _wall(root: Path) -> SyncAllowlist:
    return SyncAllowlist(governed_root=root.resolve(), allowed_dirs=frozenset())


def _registry(content_root: Path, personal_root: Path) -> VaultRegistry:
    content = VaultDescriptor(
        kind=VaultKind.CONTENT,
        root=content_root,
        owner_uid=_CONTENT_OWNER,
        allowlist=_wall(content_root),
        bridge=_bridge(),
        supports_task_round_trip=False,
    )
    personal = VaultDescriptor(
        kind=VaultKind.PERSONAL,
        root=personal_root,
        owner_uid=UserUID("user_placeholder"),
        allowlist=_wall(personal_root),
        bridge=_bridge(),
        supports_task_round_trip=True,
    )
    return VaultRegistry(content=content, personal=personal)


def _service(
    *, registry: VaultRegistry | None, sync_allowlist: SyncAllowlist | None = None
) -> UnifiedIngestionService:
    """Build a bare service exposing only what the resolvers touch.

    ``object.__new__`` skips the compose-time constructor (Neo4j backends, event
    bus, chunker) — ``_resolve_owner`` / ``_resolve_allowlist`` read only
    ``default_user_uid``, ``vault_registry``, and ``sync_allowlist``.
    """
    service = object.__new__(UnifiedIngestionService)
    service.default_user_uid = _DEFAULT
    service.vault_registry = registry
    service.sync_allowlist = sync_allowlist
    return service


# ---------------------------------------------------------------------------
# _resolve_owner
# ---------------------------------------------------------------------------


def test_content_path_owner_is_content_owner_hint_ignored(tmp_path: Path) -> None:
    content_root = tmp_path / "content"
    personal_root = tmp_path / "personal"
    service = _service(registry=_registry(content_root, personal_root))

    owner = service._resolve_owner(content_root / "ku" / "atom.md", _ACTING)

    assert owner == _CONTENT_OWNER  # acting hint discarded for content vault


def test_personal_path_owner_is_acting_user(tmp_path: Path) -> None:
    content_root = tmp_path / "content"
    personal_root = tmp_path / "personal"
    service = _service(registry=_registry(content_root, personal_root))

    owner = service._resolve_owner(personal_root / "notes" / "day.md", _ACTING)

    assert owner == _ACTING  # personal vault attributes to the acting user


def test_no_registry_falls_back_to_hint(tmp_path: Path) -> None:
    service = _service(registry=None)

    assert service._resolve_owner(tmp_path / "x.md", _ACTING) == _ACTING


def test_no_registry_no_hint_falls_back_to_default(tmp_path: Path) -> None:
    service = _service(registry=None)

    assert service._resolve_owner(tmp_path / "x.md", None) == _DEFAULT


# ---------------------------------------------------------------------------
# _resolve_allowlist
# ---------------------------------------------------------------------------


def test_explicit_allowlist_always_wins(tmp_path: Path) -> None:
    content_root = tmp_path / "content"
    personal_root = tmp_path / "personal"
    service = _service(registry=_registry(content_root, personal_root))
    explicit = _wall(tmp_path / "explicit")

    # Even with a registry wired, an explicit wall (reconciler's) is not overridden.
    assert service._resolve_allowlist(content_root, explicit) is explicit


def test_directory_allowlist_derived_from_descriptor(tmp_path: Path) -> None:
    content_root = tmp_path / "content"
    personal_root = tmp_path / "personal"
    registry = _registry(content_root, personal_root)
    service = _service(registry=registry)

    resolved = service._resolve_allowlist(content_root, None)

    # Derived wall is the content descriptor's own governed_root.
    assert resolved is not None
    assert resolved.governed_root == content_root.resolve()


def test_no_registry_allowlist_falls_back_to_sync_allowlist(tmp_path: Path) -> None:
    fallback = _wall(tmp_path / "personal")
    service = _service(registry=None, sync_allowlist=fallback)

    assert service._resolve_allowlist(tmp_path / "content", None) is fallback


# ---------------------------------------------------------------------------
# owner_is_authoritative — file-supplied user_uid cannot spoof ownership
# ---------------------------------------------------------------------------


def test_prepare_authoritative_owner_overrides_file_user_uid(tmp_path: Path) -> None:
    from core.models.enums.entity_enums import EntityType
    from core.services.ingestion.preparer import prepare_entity_data

    spoofed = {"title": "T", "user_uid": "user_victim"}

    governed = prepare_entity_data(
        EntityType.TASK,
        dict(spoofed),
        None,
        tmp_path / "task-a.md",
        UserUID("user_owner"),
        owner_is_authoritative=True,
    )
    assert governed["user_uid"] == "user_owner"  # descriptor wins

    # Backward-compat: ungoverned prepare (default) still preserves explicit uid.
    ungoverned = prepare_entity_data(
        EntityType.TASK,
        dict(spoofed),
        None,
        tmp_path / "task-b.md",
        UserUID("user_owner"),
    )
    assert ungoverned["user_uid"] == "user_victim"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
