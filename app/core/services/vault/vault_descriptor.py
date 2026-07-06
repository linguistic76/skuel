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
admin account (``content_owner_uid``); every personal vault is owned by exactly
one user. Personal roots are **per-user** (ADR-070 Decision 5):

* The **primary** personal vault (``VAULT_ROOT``) is bound to one account at
  compose time (``SKUEL_PERSONAL_VAULT_OWNER``) — its descriptor carries that
  real owner, not a placeholder.
* Every **other** user resolves to their own member vault at
  ``{user_vaults_root}/{user_uid}/``, built on demand by the injected
  ``personal_descriptor_factory`` (per-root allowlist + bridge). A user with no
  vault directory gets ``Result.fail`` — never someone else's vault.

**The "acts-as" ownership model (canonical explanation — ADR-070).**
The content vault account (``content_owner_uid``) is the account the content vault
*acts as* — it is **not** a fictional owner stamped on curriculum. Curriculum
(Ku/PathStep/LP/Exercise) is SHARED-by-type and drops its owner at persist, so
access rights are ``f(EntityType)`` computed at read time, never materialized on
the node. The acts-as account only matters for a USER_OWNED *stray* that appears
in the content vault, and it holds the content vault's outbound consent flag.
:meth:`VaultRegistry.resolve_by_path` is the mechanism: it attributes one owner
per vault by *path*, so the same file yields the same owner via any ingest
surface (dashboard, reconciler, watcher, bare script) — and since personal roots
are per-user, that owner is now truly caller-independent: a path in the primary
root belongs to its bound owner, a path in ``user_vaults/{uid}/`` to ``{uid}``.
Anything else that needs to explain this ownership model should point here
rather than restate it.

See: docs/decisions/ADR-070-bidirectional-vault-bridge.md
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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


# Builds a PERSONAL descriptor for one user's member vault (allowlist + bridge
# bound to that root). Injected from composition — the bridge is an adapter, so
# the registry itself must stay adapter-free (SKUEL022).
PersonalDescriptorFactory = Callable[[UserUID, Path], VaultDescriptor]


def _is_safe_vault_segment(segment: str) -> bool:
    """True when ``segment`` is a single, non-hidden path component.

    Guards the ``{user_vaults_root}/{user_uid}`` join: a UID that is empty,
    hidden, ``.``/``..``, absolute, or multi-segment must never become a vault
    directory. (Directory layout under ``user_vaults_root`` is server-controlled;
    this is defense in depth, not UID sniffing — the segment IS the owner.)
    """
    return segment == Path(segment).name and bool(segment) and not segment.startswith(".")


class VaultRegistry:
    """Resolves a :class:`VaultDescriptor` for a ``(kind, acting_user)`` pair.

    Holds one global ``CONTENT`` descriptor, one **primary** ``PERSONAL``
    descriptor (``VAULT_ROOT``, bound to its real owner at compose time), and a
    **member-vault family** rooted at ``user_vaults_root``: any other user's
    personal vault lives at ``{user_vaults_root}/{user_uid}/`` and its descriptor
    is built on demand by ``personal_descriptor_factory``. Resolution never hands
    one user another user's vault (ADR-070 Decision 5).
    """

    def __init__(
        self,
        *,
        content: VaultDescriptor | None,
        personal: VaultDescriptor | None,
        user_vaults_root: Path | None = None,
        personal_descriptor_factory: PersonalDescriptorFactory | None = None,
    ) -> None:
        # ``personal`` is the primary personal vault, owner-bound at compose
        # time. ``user_vaults_root`` + factory enable the per-user member
        # family; they come as a pair (a root without a way to build a
        # descriptor for it — or vice versa — is a wiring bug, fail fast).
        if (user_vaults_root is None) != (personal_descriptor_factory is None):
            raise ValueError(
                "user_vaults_root and personal_descriptor_factory must be provided together"
            )
        self._content = content
        self._personal = personal
        self._user_vaults_root = user_vaults_root
        self._factory = personal_descriptor_factory

    def resolve(self, kind: VaultKind, acting_user_uid: UserUID) -> Result[VaultDescriptor]:
        """Return the descriptor for ``kind`` as seen by ``acting_user_uid``.

        ``CONTENT`` returns the singleton content descriptor (owner is the fixed
        admin account; ``acting_user_uid`` is ignored). ``PERSONAL`` returns the
        primary descriptor when the acting user IS its bound owner; any other
        user resolves to their own ``{user_vaults_root}/{user_uid}/`` member
        vault — or ``Result.fail`` when that directory does not exist. No code
        path serves a personal vault to a non-owner.
        """
        if kind is VaultKind.CONTENT:
            if self._content is None:
                return Result.fail(Errors.not_found(resource="content vault", identifier="content"))
            return Result.ok(self._content)

        if self._personal is not None and acting_user_uid == self._personal.owner_uid:
            return Result.ok(self._personal)

        member = self._member_vault_root(acting_user_uid)
        if member is not None and member.is_dir() and self._factory is not None:
            return Result.ok(self._factory(acting_user_uid, member))

        # No member directory exists (or no family is wired): this user has no
        # personal vault. Fail — never fall through to someone else's root.
        return Result.fail(
            Errors.not_found(resource="personal vault", identifier=str(acting_user_uid))
        )

    def _member_vault_root(self, user_uid: UserUID) -> Path | None:
        """``{user_vaults_root}/{user_uid}`` when the family is wired and the UID is joinable."""
        if self._user_vaults_root is None:
            return None
        segment = str(user_uid)
        if not _is_safe_vault_segment(segment):
            return None
        return self._user_vaults_root.resolve() / segment

    def resolve_by_path(self, path: Path, acting_user_uid: UserUID) -> Result[VaultDescriptor]:
        """Return the descriptor that governs a target file/dir ``path``.

        This is the by-path counterpart to :meth:`resolve` (which is by-kind).
        Callers that only know a directory (the ``/api/ingest/*`` doors, the
        watcher, ad-hoc scripts) use this so the *owner* attributed to what they
        ingest is a function of the vault the file lives in — not of the caller's
        own identity. Access rights thus become surface-independent.
        ``acting_user_uid`` is accepted for signature symmetry but never decides
        ownership: every personal root carries its own bound owner.

        Precedence is fail-safe:

        1. **Primary personal root wins for any in-root path**, attributed to its
           bound owner. This also covers the **combined vault** (``INGESTION_PATH``
           coincident with or nested inside ``VAULT_ROOT``): the whole thing is one
           user-owned vault — consistent with ``build_sync_allowlist``, which opens
           such a vault whole. SHARED curriculum still drops its owner at persist
           regardless, so a Ku in a combined vault is unaffected; only USER_OWNED
           types carry the owner.
        2. **Member vault family.** A path under ``{user_vaults_root}/{uid}/`` is
           owned by ``{uid}`` — the directory the file lives in, never the caller.
           (``user_vaults_root`` itself, hidden entries, and non-directories fall
           through: they belong to no user's vault.)
        3. **Content root.** Owned by the fixed content admin (curriculum is
           SHARED-by-type and drops its owner anyway; any USER_OWNED stray gets
           the content acts-as owner, consistently).
        4. **Neither root → content default.** Arbitrary dirs (e.g. an admin
           staging path outside every vault) resolve to the content/SHARED
           acts-as descriptor — never a random user's USER_OWNED descriptor.

        Accepts a file or a directory path; containment (``is_relative_to``)
        handles both. If no descriptor can govern the path (minimal composes),
        returns ``Result.fail`` so the caller falls back to its default owner.
        """
        resolved = path.resolve()

        if self._personal is not None:
            personal_root = self._personal.root.resolve()
            if resolved == personal_root or resolved.is_relative_to(personal_root):
                return Result.ok(self._personal)

        member = self._member_descriptor_for_path(resolved)
        if member is not None:
            return Result.ok(member)

        if self._content is not None:
            # In-content path, or a path under no root: content/SHARED acts-as
            # is the safe default — never a random user's USER_OWNED descriptor.
            return Result.ok(self._content)

        return Result.fail(Errors.not_found(resource="vault for path", identifier=str(resolved)))

    def _member_descriptor_for_path(self, resolved: Path) -> VaultDescriptor | None:
        """The member-vault descriptor governing ``resolved``, if any.

        Only a path *strictly inside* an existing, non-hidden member directory
        qualifies; ``user_vaults_root`` itself and direct stray files under it
        belong to no user's vault.
        """
        if self._user_vaults_root is None or self._factory is None:
            return None
        family_root = self._user_vaults_root.resolve()
        if resolved == family_root or not resolved.is_relative_to(family_root):
            return None
        segment = resolved.relative_to(family_root).parts[0]
        member_root = family_root / segment
        if not _is_safe_vault_segment(segment) or not member_root.is_dir():
            return None
        return self._factory(UserUID(segment), member_root)

    def nested_vault_roots(self, directory: Path) -> list[Path]:
        """Registered vault roots that sit *strictly below* ``directory``.

        A directory scan is only sound when it belongs to a single vault: the
        governing descriptor (from :meth:`resolve_by_path`) attributes one owner
        and one wall to the whole batch. If another vault's root is nested under
        the scanned directory, the scan can sweep that entire vault too. This is
        the raw containment primitive; :meth:`conflicting_nested_roots` layers the
        owner-uniformity judgement on top (a nested root is only a problem when it
        resolves to a *different* vault kind than the directory).

        Member vaults count: when ``directory`` contains the user-vaults root
        (or IS it), every existing member directory is a nested personal root —
        a scan of that ancestor would sweep multiple users' vaults.

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
        # Member vaults are direct children of the family root, so they can sit
        # strictly below ``directory`` only when it IS the family root or an
        # ancestor of it — enumerate the O(users) family only then, never on a
        # scan inside one member vault (every personal sync).
        if self._user_vaults_root is not None:
            family_root = self._user_vaults_root.resolve()
            if resolved == family_root or family_root.is_relative_to(resolved):
                for member_root in self._member_vault_roots():
                    if member_root not in nested:
                        nested.append(member_root)
        return nested

    def _member_vault_roots(self) -> list[Path]:
        """Existing member-vault directories under ``user_vaults_root``."""
        if self._user_vaults_root is None:
            return []
        family_root = self._user_vaults_root.resolve()
        if not family_root.is_dir():
            return []
        return [
            child
            for child in sorted(family_root.iterdir())
            if child.is_dir() and _is_safe_vault_segment(child.name)
        ]

    def conflicting_nested_roots(self, directory: Path, acting_user_uid: UserUID) -> list[Path]:
        """Nested vault roots whose governing descriptor differs from ``directory``'s.

        A directory scan attributes one owner + one wall to the whole batch (the
        bulk-upsert engine), which is sound only if every file it may collect
        resolves by-path to the same descriptor as the directory. A nested vault
        root that resolves to a different :class:`VaultKind` OR a different owner
        would have its files swept under the wrong owner — the caller rejects
        such a scan.

        Returns ``[]`` for a **combined vault** (a content root nested inside a
        personal root resolves to the *same* personal descriptor as the enclosing
        directory), so the normal nested-config personal sync is allowed. Returns
        the offending roots for an **ancestor** scan (roots resolve to differing
        descriptors), a **personal vault nested inside a content scan**, a scan
        of the user-vaults root itself (each member resolves to its own PERSONAL
        owner, the umbrella directory to the content default), or a member vault
        nested under the primary personal root (same kind, different owner) —
        every case that would otherwise stamp users' private files with the
        wrong owner.
        """
        directory_descriptor = self.resolve_by_path(directory, acting_user_uid)
        if directory_descriptor.is_error:
            return []
        governing = directory_descriptor.value
        conflicting: list[Path] = []
        for root in self.nested_vault_roots(directory):
            nested = self.resolve_by_path(root, acting_user_uid)
            if nested.is_error:
                continue
            same = (
                nested.value.kind is governing.kind
                and nested.value.owner_uid == governing.owner_uid
            )
            if not same:
                conflicting.append(root)
        return conflicting


__all__ = ["PersonalDescriptorFactory", "VaultDescriptor", "VaultKind", "VaultRegistry"]
