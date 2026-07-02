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

**The "acts-as" ownership model (canonical explanation — ADR-070).**
The content vault account (``content_owner_uid``) is the account the content vault
*acts as* — it is **not** a fictional owner stamped on curriculum. Curriculum
(Ku/PathStep/LP/Exercise) is SHARED-by-type and drops its owner at persist, so
access rights are ``f(EntityType)`` computed at read time, never materialized on
the node. The acts-as account only matters for a USER_OWNED *stray* that appears
in the content vault, and it holds the content vault's outbound consent flag.
:meth:`VaultRegistry.resolve_by_path` is the mechanism: it attributes one owner
per vault by *path*, so the same file yields the same owner via any ingest
surface (dashboard, reconciler, watcher, bare script). Anything else that needs
to explain this ownership model should point here rather than restate it.

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


def _owned_by(template: VaultDescriptor, acting_user_uid: UserUID) -> VaultDescriptor:
    """The personal template with the acting user stamped as owner (ADR-070 Decision 5)."""
    return replace(template, owner_uid=acting_user_uid)


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
        return Result.ok(_owned_by(self._personal, acting_user_uid))

    def resolve_by_path(self, path: Path, acting_user_uid: UserUID) -> Result[VaultDescriptor]:
        """Return the descriptor that governs a target file/dir ``path``.

        This is the by-path counterpart to :meth:`resolve` (which is by-kind).
        Callers that only know a directory (the ``/api/ingest/*`` doors, the
        watcher, ad-hoc scripts) use this so the *owner* attributed to what they
        ingest is a function of the vault the file lives in — not of the caller's
        own identity. Access rights thus become surface-independent.

        Precedence is fail-safe:

        1. **Personal wins for any in-personal-root path.** The personal
           descriptor is the only one that attributes USER_OWNED entities to a
           *person* (its ``owner_uid`` is the acting user), and it is returned
           *only* for a path inside the personal root — so a stray path can never
           be silently owned by whoever happens to be acting. This also covers the
           **combined vault** (``INGESTION_PATH`` coincident with or nested inside
           ``VAULT_ROOT``): the whole thing is one user-owned vault — consistent
           with ``build_sync_allowlist``, which opens such a vault whole. SHARED
           curriculum still drops its owner at persist regardless, so a Ku in a
           combined vault is unaffected; only USER_OWNED types carry the owner.
        2. **Content root.** Owned by the fixed content admin; ``acting_user_uid``
           is ignored (curriculum is SHARED-by-type and drops its owner anyway;
           any USER_OWNED stray gets the content acts-as owner, consistently).
        3. **Neither root → content default.** Arbitrary dirs (e.g. an admin
           staging path outside both vaults) resolve to the content/SHARED
           acts-as descriptor — never a random user's USER_OWNED descriptor.

        Accepts a file or a directory path; containment (``is_relative_to``)
        handles both. If neither descriptor is registered (minimal composes),
        returns ``Result.fail`` so the caller falls back to its default owner.
        """
        resolved = path.resolve()

        if self._personal is not None:
            personal_root = self._personal.root.resolve()
            if resolved == personal_root or resolved.is_relative_to(personal_root):
                return Result.ok(_owned_by(self._personal, acting_user_uid))

        if self._content is not None:
            # In-content path, or a path under neither root: content/SHARED acts-as
            # is the safe default — never a random user's USER_OWNED descriptor.
            return Result.ok(self._content)

        return Result.fail(Errors.not_found(resource="vault for path", identifier=str(resolved)))

    def nested_vault_roots(self, directory: Path) -> list[Path]:
        """Registered vault roots that sit *strictly below* ``directory``.

        A directory scan is only sound when it belongs to a single vault: the
        governing descriptor (from :meth:`resolve_by_path`) attributes one owner
        and one wall to the whole batch. If another vault's root is nested under
        the scanned directory, the scan can sweep that entire vault too. This is
        the raw containment primitive; :meth:`conflicting_nested_roots` layers the
        owner-uniformity judgement on top (a nested root is only a problem when it
        resolves to a *different* vault kind than the directory).

        Sibling roots (the live split-root config) and coincident roots (the
        combined-root default) are *not* strict descendants, so neither trips
        this — only a scan of a genuine ancestor directory does.
        """
        resolved = directory.resolve()
        nested: list[Path] = []
        for descriptor in (self._content, self._personal):
            if descriptor is None:
                continue
            root = descriptor.root.resolve()
            if root != resolved and root.is_relative_to(resolved):
                nested.append(root)
        return nested

    def conflicting_nested_roots(self, directory: Path, acting_user_uid: UserUID) -> list[Path]:
        """Nested vault roots that resolve to a *different kind* than ``directory``.

        A directory scan attributes one owner + one wall to the whole batch (the
        bulk-upsert engine), which is sound only if every file it may collect
        resolves by-path to the same descriptor as the directory. A nested vault
        root that resolves to a different :class:`VaultKind` would have its files
        swept under the wrong owner — the caller rejects such a scan.

        Returns ``[]`` for a **combined vault** (a content root nested inside a
        personal root resolves to the *same* personal descriptor as the enclosing
        directory), so the normal nested-config personal sync is allowed. Returns
        the offending roots for an **ancestor** scan (roots resolve to differing
        kinds) or a **personal vault nested inside a content scan** (the personal
        root resolves to PERSONAL, the content directory to CONTENT) — the case
        that would otherwise stamp a user's private files with the content owner.
        """
        directory_descriptor = self.resolve_by_path(directory, acting_user_uid)
        if directory_descriptor.is_error:
            return []
        directory_kind = directory_descriptor.value.kind
        conflicting: list[Path] = []
        for root in self.nested_vault_roots(directory):
            nested = self.resolve_by_path(root, acting_user_uid)
            if nested.is_ok and nested.value.kind is not directory_kind:
                conflicting.append(root)
        return conflicting


__all__ = ["VaultDescriptor", "VaultKind", "VaultRegistry"]
