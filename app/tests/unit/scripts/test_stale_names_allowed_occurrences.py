"""Audit ``stale_names.py``'s two fine-grained exemptions: what do they keep invisible?

The whole-file suppressor (``SKIP_FILES``) has its own audit in
``test_stale_names_suppression.py``. This file audits the two NARROWER escapes that
PR #986 called for after the earlier "bulk-add files to SKIP_FILES to force the count
to 0" pass was reverted:

  * ``ALLOWED_OCCURRENCES`` — one identifier at one LINE, in one otherwise-scanned doc.
    The earlier draft of exactly this shipped without an audit and was reverted with the
    bulk-add; the mechanism is sound, the missing audit was the defect. This file is that
    audit. It is line-anchored, not merely (file, identifier)-keyed: Codex (PR #988)
    showed the coarser key would silently suppress a *second*, genuinely-stale mention of
    an already-allowed identifier while the audit stayed green — the identity-scoping trap
    the suppression audit was built to catch. Anchoring on the line closes it: any hit not
    at an allowed line is reported.
  * ``SCAN_EXCLUDE_DIRS`` — a whole frozen-archive subtree (``docs/migrations/``), out
    of remit like ``docs/roadmap/done/``.

The discipline is the same one the suppression audit encodes and SKUEL026 encodes for
lint suppressions: **an exemption that suppresses nothing is a finding**. A dead allow
entry is not harmless — it is a rubber stamp that will silently swallow the first real
stale name that lands on the same (file, line), so the audit fails on it and forces a
human to re-justify or delete it.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import (matches test_lint_skuel.py
# and test_stale_names_suppression.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "health"))

import stale_names as sn  # type: ignore[import-not-found]


def _scan_target_strs() -> set[str]:
    """ROOT-relative forward-slash paths the scanner actually looks at."""
    return {str(p.relative_to(sn.ROOT)) for p in sn.get_scan_targets()}


def _raw_occurrences(path: Path) -> set[tuple[int, str]]:
    """Every (line, identifier) the scanner raw-matches in ``path`` (pre-allowlist)."""
    return {(lineno, old) for lineno, old, _replacement, _kind in sn.scan_file(path)}


def _dead_allow_entries() -> list[str]:
    """Every ALLOWED_OCCURRENCES entry that suppresses nothing, with why.

    Two ways an entry can be dead, both the same rubber-stamp defect:
      * the file is not a live scan target (moved, or itself excluded/skipped), so the
        allow can never fire; or
      * that identifier does not raw-match at that exact line — the line moved (a doc
        edit shifted it) or the entry was mis-typed, so removing it would surface no hit.
    """
    targets = _scan_target_strs()
    dead: list[str] = []
    for rel_path, entries in sn.ALLOWED_OCCURRENCES.items():
        if rel_path not in targets:
            dead.append(f"{rel_path}: not a live scan target — allow can never fire")
            continue
        raw = _raw_occurrences(sn.ROOT / rel_path)
        dead.extend(
            f"{rel_path}:{lineno} {identifier!r} raw-matches nothing at that line — dead anchor"
            for (lineno, identifier) in entries
            if (lineno, identifier) not in raw
        )
    return dead


# ── ALLOWED_OCCURRENCES: real-data audit ─────────────────────────────────────


def test_allowed_files_are_live_scan_targets() -> None:
    """An allow keyed on a file the scanner never reads suppresses nothing.

    Covers the moved-file case (the file was renamed) and the double-exempt case (the
    file is already inside SCAN_EXCLUDE_DIRS or SKIP_FILES, so the per-occurrence entry
    is redundant and should be dropped).
    """
    targets = _scan_target_strs()
    stray = [rel for rel in sn.ALLOWED_OCCURRENCES if rel not in targets]
    assert stray == [], (
        f"ALLOWED_OCCURRENCES keys are not live scan targets: {stray}. Either the file "
        "moved (fix the key) or it is already covered by SCAN_EXCLUDE_DIRS/SKIP_FILES "
        "(drop the redundant per-occurrence entry)."
    )


def test_every_allowed_entry_anchors_a_real_hit() -> None:
    """Positive control, per (file, line, identifier) — no dead anchors (SKUEL026)."""
    dead = _dead_allow_entries()
    assert dead == [], (
        "ALLOWED_OCCURRENCES has entries that hide nothing — a rubber stamp that will "
        f"swallow the first real stale name on the same (file, line): {dead}. The line "
        "likely moved (re-anchor it) or the entry is mistyped; fix or delete it."
    )


def test_every_allowed_entry_carries_a_rationale() -> None:
    """Each exemption sits under a stated justification — no blank grants."""
    blank = [
        f"{rel_path}:{lineno} {identifier}"
        for rel_path, entries in sn.ALLOWED_OCCURRENCES.items()
        for (lineno, identifier), rationale in entries.items()
        if not rationale.strip()
    ]
    assert blank == [], f"ALLOWED_OCCURRENCES entries with an empty rationale: {blank}"


# ── SCAN_EXCLUDE_DIRS: real-data audit ───────────────────────────────────────


def test_excluded_dirs_all_exist() -> None:
    """An exclusion pointing at a moved/renamed subtree excludes nothing."""
    missing = [str(d) for d in sn.SCAN_EXCLUDE_DIRS if not d.is_dir()]
    assert missing == [], f"SCAN_EXCLUDE_DIRS entries are not directories on disk: {missing}"


def test_every_excluded_dir_earns_its_exclusion() -> None:
    """Positive control, per dir — a subtree with no tracked identifiers needs no exclusion.

    If the archive contains nothing this scanner would ever flag, the exclusion is dead
    weight that will silently hide the first tracked name written into it later.
    """
    for excluded in sn.SCAN_EXCLUDE_DIRS:
        hits = sum(len(sn.scan_file(md)) for md in excluded.rglob("*.md"))
        assert hits > 0, (
            f"{excluded} is excluded but contains no tracked identifier — the exclusion "
            "suppresses nothing today and will hide its first real hit; remove it until "
            "the subtree actually needs it."
        )


def test_no_scan_target_lives_under_an_excluded_dir() -> None:
    """The exclusion must actually remove the archive from the scanned set."""
    leaked = [
        str(p.relative_to(sn.ROOT)) for p in sn.get_scan_targets() if sn._under_excluded_dir(p)
    ]
    assert leaked == [], f"excluded-dir files leaked into scan targets: {leaked}"


# ── Mechanism logic: synthetic, proves the guards bite even with empty real data ──


def test_is_allowed_occurrence_is_scoped_to_one_line_and_one_identifier(monkeypatch) -> None:
    """The allow exempts ONLY the named (line, identifier) — never a whole file."""
    monkeypatch.setitem(sn.ALLOWED_OCCURRENCES, "docs/example.md", {(18, "KuType"): "why"})
    assert sn._is_allowed_occurrence("docs/example.md", 18, "KuType") is True
    # The SAME identifier on a DIFFERENT line is still reported — the line-anchoring that
    # closes the (file, identifier) blind spot Codex flagged (PR #988).
    assert sn._is_allowed_occurrence("docs/example.md", 19, "KuType") is False
    # A different identifier at the SAME line is still scanned.
    assert sn._is_allowed_occurrence("docs/example.md", 18, "KuStatus") is False
    # The same occurrence in a DIFFERENT file is still scanned.
    assert sn._is_allowed_occurrence("docs/other.md", 18, "KuType") is False


def test_dead_allow_audit_bites(monkeypatch) -> None:
    """Prove the positive-control audit fails on a dead entry — otherwise it is theatre."""
    # Branch A: file is not a scan target at all.
    monkeypatch.setitem(sn.ALLOWED_OCCURRENCES, "docs/does-not-exist.md", {(1, "KuType"): "x"})
    assert any("does-not-exist" in problem for problem in _dead_allow_entries())

    # Branch B: a real scan target, but a (line, identifier) that raw-matches nothing
    # there — covers both a moved line and a never-tracked identifier.
    a_real_target = str(next(iter(sn.get_scan_targets())).relative_to(sn.ROOT))
    monkeypatch.setitem(
        sn.ALLOWED_OCCURRENCES, a_real_target, {(999_999, "ThisIdentifierIsNotTracked"): "x"}
    )
    assert any("ThisIdentifierIsNotTracked" in problem for problem in _dead_allow_entries())


def test_under_excluded_dir_matches_subtree_not_siblings() -> None:
    """The directory-scope predicate matches inside the subtree and nowhere else."""
    migrations = sn.ROOT / "docs" / "migrations"
    assert sn._under_excluded_dir(migrations / "SOME_MIGRATION.md") is True
    assert sn._under_excluded_dir(migrations / "sub" / "deeper.md") is True
    # A sibling under docs/ that merely shares a prefix is NOT excluded.
    assert sn._under_excluded_dir(sn.ROOT / "docs" / "patterns" / "x.md") is False
    assert sn._under_excluded_dir(sn.ROOT / "docs" / "migrations-notes.md") is False
