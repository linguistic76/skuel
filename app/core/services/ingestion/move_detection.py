"""
Move Detection - Content Matching for Uid-Less Vault Renames
=============================================================

Pure matching logic for the move-detection pre-pass
(``IngestionTracker.detect_and_apply_moves``), two strategies in sequence:

- **Phase 1 — exact hash**: a gone tracked row and a new untracked file
  sharing a SHA-256 1:1 is a pure rename — the tracker row is rewritten
  (old path → new path, same uid) so the #616 path-keyed upsert channel
  reuses the uid instead of delete+creating.
- **Phase 2 — lexical similarity** over Phase 1's residual (the
  still-unmatched delete-candidate rows vs still-unmatched new files):
  a rename + edit in one sync changes the hash, so the gone node's
  last-ingested body (``Entity.content``) is compared against the new
  file's resolved on-disk content with word-shingle Jaccard, and only a
  MUTUAL best match at or above ``SIMILARITY_MOVE_THRESHOLD`` is a move.
  Everything else stays delete+create — a missed move is the safe
  failure; a wrong merge silently fuses two notes' identities.

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


# Phase 2 crux — bias HIGH: a false positive silently fuses two notes'
# identities, a false negative just falls back to delete+create (today's
# behavior). Tuned empirically during runtime verification, not guessed.
SIMILARITY_MOVE_THRESHOLD = 0.8

# Word-shingle width for the Jaccard scorer. Trigrams capture phrasing and
# order (resistant to common-word inflation); texts too short for a full
# shingle fall back to unigram sets.
_SHINGLE_SIZE = 3


@dataclass(frozen=True)
class SimilarityPair:
    """A mutual-best similarity match: ``row``'s identity moves to ``new_file``."""

    row: MoveCandidate
    new_file: NewFileCandidate
    score: float


@dataclass(frozen=True)
class SimilarityMatchResult:
    """Outcome of mutual-best similarity matching over the exact-hash residual."""

    pairs: tuple[SimilarityPair, ...] = ()
    # One message per candidate whose top score was tied between 2+ partners —
    # no unique best means no mutual agreement, so it abstains (delete+create).
    ambiguous: tuple[str, ...] = ()


def _shingle_set(tokens: list[str], width: int) -> frozenset[tuple[str, ...]]:
    """All ``width``-word shingles of a token sequence."""
    return frozenset(tuple(tokens[i : i + width]) for i in range(len(tokens) - width + 1))


def similarity_score(a: str, b: str) -> float:
    """Jaccard similarity of the two texts' word shingles, in [0.0, 1.0].

    Both sides must be comparable forms — the caller resolves frontmatter
    (explicit ``content:`` wins, else the markdown body) exactly the way
    ingestion does before scoring; this function only normalizes case and
    whitespace (``str.split()`` collapses all whitespace runs, so reflowed
    markdown scores identically). When either side is too short for a full
    shingle, BOTH sides fall back to unigram sets so the comparison stays
    symmetric.
    """
    tokens_a = a.lower().split()
    tokens_b = b.lower().split()
    if not tokens_a or not tokens_b:
        return 0.0
    width = _SHINGLE_SIZE if min(len(tokens_a), len(tokens_b)) >= _SHINGLE_SIZE else 1
    set_a = _shingle_set(tokens_a, width)
    set_b = _shingle_set(tokens_b, width)
    intersection = len(set_a & set_b)
    if intersection == 0:
        return 0.0
    return intersection / len(set_a | set_b)


def _unique_best(scores_by_index: dict[int, float]) -> int | None:
    """Index with the strictly highest score, or None on empty/tied top."""
    if not scores_by_index:
        return None
    best_score = max(scores_by_index.values())
    winners = [idx for idx, score in scores_by_index.items() if score == best_score]
    return winners[0] if len(winners) == 1 else None


def match_moves_by_similarity(
    rows: Sequence[tuple[MoveCandidate, str]],
    new_files: Sequence[tuple[NewFileCandidate, str]],
    threshold: float = SIMILARITY_MOVE_THRESHOLD,
) -> SimilarityMatchResult:
    """Pair gone rows with new files by mutual-best lexical similarity.

    Each candidate arrives with its comparison content: the row's is the gone
    node's last-ingested body (``Entity.content``), the file's is the resolved
    on-disk content (frontmatter handled the way ingestion resolves it). A
    (row R, file F) pair is a move iff F is R's unique best match AND R is F's
    unique best match AND their score ≥ ``threshold`` — git-style two-way
    agreement, so a wrong merge needs two coinciding errors, not one lucky
    score. A tied top score on either side abstains (reported in
    ``ambiguous``); every unpaired candidate stays delete+create.
    """
    eligible: dict[tuple[int, int], float] = {}
    for i, (_, row_content) in enumerate(rows):
        for j, (_, file_content) in enumerate(new_files):
            score = similarity_score(row_content, file_content)
            if score >= threshold:
                eligible[(i, j)] = score

    best_file_for_row = {
        i: _unique_best({j: s for (ri, j), s in eligible.items() if ri == i})
        for i in range(len(rows))
    }
    best_row_for_file = {
        j: _unique_best({i: s for (i, fj), s in eligible.items() if fj == j})
        for j in range(len(new_files))
    }

    pairs: list[SimilarityPair] = []
    ambiguous: list[str] = []
    for i, (row, _) in enumerate(rows):
        best_j = best_file_for_row[i]
        if best_j is None:
            if any(ri == i for (ri, _fj) in eligible):
                ambiguous.append(
                    f"similarity top score for gone row {row.file_path} is tied "
                    "between multiple new files — ambiguous, falling back to "
                    "delete+create"
                )
            continue
        if best_row_for_file[best_j] != i:
            continue
        pairs.append(
            SimilarityPair(row=row, new_file=new_files[best_j][0], score=eligible[(i, best_j)])
        )
    for j, (new_file, _) in enumerate(new_files):
        if best_row_for_file[j] is None and any(fj == j for (_ri, fj) in eligible):
            ambiguous.append(
                f"similarity top score for new file {new_file.file_path} is tied "
                "between multiple gone rows — ambiguous, falling back to "
                "delete+create"
            )

    return SimilarityMatchResult(pairs=tuple(pairs), ambiguous=tuple(ambiguous))


__all__ = [
    "SIMILARITY_MOVE_THRESHOLD",
    "HashMatchResult",
    "MoveCandidate",
    "MovePair",
    "NewFileCandidate",
    "SimilarityMatchResult",
    "SimilarityPair",
    "match_moves_by_hash",
    "match_moves_by_similarity",
    "similarity_score",
]
