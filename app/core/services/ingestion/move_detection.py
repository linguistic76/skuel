"""
Move Detection - Content-Hash Matching for Uid-Less Vault Renames
==================================================================

Pure matching logic for the move-detection pre-pass
(``IngestionTracker.detect_and_apply_moves``). Phase 1 is exact-hash only:
a gone tracked row and a new untracked file sharing a SHA-256 1:1 is a
rename — the tracker row is rewritten (old path → new path, same uid) so
the #616 path-keyed upsert channel reuses the uid instead of
delete+creating.

Phase 2 seam: ``HashMatchResult`` carries the residual — still-unmatched
delete-candidate rows and still-unmatched new files — which a similarity
matcher (rename + edit in one sync) consumes as its exact input. Adding
that second strategy is a drop-in over the residual, not surgery here.

Contract: /plans/hash-assisted-move-detection.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True)
class MoveCandidate:
    """A would-be-deleted tracked row: gone from disk, uid unclaimed — move source."""

    file_path: str  # canonical absolute path (tracker key form)
    entity_uid: str
    content_hash: str  # last-ingested SHA-256


@dataclass(frozen=True)
class NewFileCandidate:
    """An untracked file the current sync will ingest — move destination."""

    file_path: str  # canonical absolute path (tracker key form)
    content_hash: str  # on-disk SHA-256, computed at pre-pass time


@dataclass(frozen=True)
class MovePair:
    """An unambiguous 1:1 hash match: ``row``'s identity moves to ``new_file``."""

    row: MoveCandidate
    new_file: NewFileCandidate


@dataclass(frozen=True)
class HashMatchResult:
    """Outcome of exact-hash matching, residual included (Phase 2 seam)."""

    pairs: tuple[MovePair, ...] = ()
    # One message per hash shared by 2+ gone rows or 2+ new files — those
    # fall back to delete+create (a wrong merge fuses two notes' identities;
    # a missed move is the safe failure).
    ambiguous: tuple[str, ...] = ()
    # Unmatched candidates on both sides — the similarity pass's input.
    residual_rows: tuple[MoveCandidate, ...] = ()
    residual_files: tuple[NewFileCandidate, ...] = ()


def match_moves_by_hash(
    delete_candidates: Sequence[MoveCandidate],
    new_files: Sequence[NewFileCandidate],
) -> HashMatchResult:
    """Pair gone rows with new files by exact content hash — 1:1 matches only.

    A hash claimed by exactly one gone row AND exactly one new file is a
    move; any ambiguity (2+ on either side) is skipped with a message and
    both sides land in the residual. Trivial-content filtering (empty /
    whitespace-only files) is the caller's job — this function assumes every
    candidate already carries a meaningful hash.
    """
    rows_by_hash: dict[str, list[MoveCandidate]] = {}
    for row in delete_candidates:
        rows_by_hash.setdefault(row.content_hash, []).append(row)
    files_by_hash: dict[str, list[NewFileCandidate]] = {}
    for new_file in new_files:
        files_by_hash.setdefault(new_file.content_hash, []).append(new_file)

    pairs: list[MovePair] = []
    ambiguous: list[str] = []
    matched_row_paths: set[str] = set()
    matched_file_paths: set[str] = set()

    for content_hash, rows in rows_by_hash.items():
        files = files_by_hash.get(content_hash)
        if not files:
            continue
        if len(rows) > 1 or len(files) > 1:
            ambiguous.append(
                f"content hash {content_hash[:12]}… shared by {len(rows)} deleted "
                f"and {len(files)} new file(s) — ambiguous, falling back to "
                "delete+create"
            )
            continue
        pairs.append(MovePair(row=rows[0], new_file=files[0]))
        matched_row_paths.add(rows[0].file_path)
        matched_file_paths.add(files[0].file_path)

    return HashMatchResult(
        pairs=tuple(pairs),
        ambiguous=tuple(ambiguous),
        residual_rows=tuple(
            row for row in delete_candidates if row.file_path not in matched_row_paths
        ),
        residual_files=tuple(
            new_file for new_file in new_files if new_file.file_path not in matched_file_paths
        ),
    )


__all__ = [
    "HashMatchResult",
    "MoveCandidate",
    "MovePair",
    "NewFileCandidate",
    "match_moves_by_hash",
]
