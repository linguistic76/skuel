"""
VaultDescriptor + VaultRegistry — ADR-070 multi-vault model
============================================================

One :class:`~core.services.vault.vault_reconciler.VaultReconciler` serves every
vault through a **descriptor** that carries the vault's root, its owning account,
its fail-closed allowlist, its outbound bridge adapter, and whether it supports
the task round-trip. This is what lets a single reconciler code path drive both
the admin **content** vault (curriculum) and a user's **personal** vault instead
of the two divergent sync paths SKUEL used to carry.

Ownership is the vault discriminator: the content vault is owned by a single
admin account (``content_owner_uid``), a personal vault by the acting user. The
registry stamps the acting user onto the personal descriptor at resolve time so
the model is per-user from day one (ADR-070 Decision 5) even though Stage 1 only
serves one local user.

See: docs/decisions/ADR-070-bidirectional-vault-bridge.md
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from core.models.type_hints import UserUID
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.vault_bridge_protocol import VaultBridgePort
    from core.services.ingestion.config import SyncAllowlist


class VaultKind(Enum):
    """The two kinds of vault SKUEL syncs.

    ``CONTENT`` — admin-authored curriculum (Ku/PathStep/LP), SHARED. Owned by a
        single admin account; ingested inbound-only today (the curriculum
        outbound writeback is designed-for but deferred — curriculum YAML has no
        checkbox round-trip).
    ``PERSONAL`` — a user's Obsidian vault (daily notes, knowledge). USER_OWNED
        and fully bidirectional (🆔 task round-trip, ADR-070).
    """

    CONTENT = "content"
    PERSONAL = "personal"


@dataclass(frozen=True)
class VaultDescriptor:
    """Everything the reconciler needs to sync one vault.

    Attributes:
        kind: Which :class:`VaultKind` this describes.
        root: Absolute vault root directory.
        owner_uid: The account the vault's entries are attributed to (inbound
            ingest ``user_uid``) and whose ``vault_write_consent`` gates outbound.
        allowlist: Fail-closed folder wall scoped to this vault's own root.
        bridge: Outbound write adapter (Stage 1 ``FilesystemVaultAdapter``),
            ``allowed_root``-bound to this vault.
        supports_task_round_trip: Whether outbound (🆔 injection + done-date
            writeback) runs. ``False`` for the content vault (structural no-op
            until curriculum writeback is built).
    """

    kind: VaultKind
    root: Path
    owner_uid: UserUID
    allowlist: SyncAllowlist
    bridge: VaultBridgePort
    supports_task_round_trip: bool


class VaultRegistry:
    """Resolves a :class:`VaultDescriptor` for a ``(kind, acting_user)`` pair.

    Stage 1 holds one global ``CONTENT`` descriptor and one ``PERSONAL`` template
    (single local user). ``PERSONAL`` resolution stamps the acting user onto the
    template's ``owner_uid`` so a future multi-tenant registry can return that
    user's own vault without any reconciler change (ADR-070 Decision 5).
    """

    def __init__(
        self,
        *,
        content: VaultDescriptor | None,
        personal: VaultDescriptor | None,
    ) -> None:
        # ``personal`` is a template: every field but ``owner_uid`` is final;
        # ``resolve`` replaces ``owner_uid`` with the acting user. Stage 1's
        # single personal vault means the template's placeholder owner is never
        # used directly.
        self._content = content
        self._personal = personal

    def resolve(self, kind: VaultKind, acting_user_uid: UserUID) -> Result[VaultDescriptor]:
        """Return the descriptor for ``kind``.

        ``CONTENT`` returns the singleton content descriptor (owner is the fixed
        admin account; ``acting_user_uid`` is ignored). ``PERSONAL`` returns the
        personal template with ``owner_uid`` set to ``acting_user_uid``.
        """
        if kind is VaultKind.CONTENT:
            if self._content is None:
                return Result.fail(Errors.not_found(resource="content vault", identifier="content"))
            return Result.ok(self._content)

        if self._personal is None:
            return Result.fail(
                Errors.not_found(resource="personal vault", identifier=str(acting_user_uid))
            )
        return Result.ok(replace(self._personal, owner_uid=acting_user_uid))


__all__ = ["VaultDescriptor", "VaultKind", "VaultRegistry"]
