"""Audit ``stale_names.py``'s occurrence-level exemption: what does it keep invisible?

The whole-file suppressor (``SKIP_FILES``) has its own audit in
``test_stale_names_suppression.py``. This file audits ``ALLOWED_OCCURRENCES``, the
narrower escape PR #986 called for after the earlier "bulk-add files to SKIP_FILES to
force the count to 0" pass was reverted.

``ALLOWED_OCCURRENCES`` exempts a COUNTED set of hits for one identifier at one LINE, in
one otherwise-scanned doc. The earlier draft of exactly this shipped without an audit and
was reverted with the bulk-add; the mechanism is sound, the missing audit was the defect.
This file is that audit. It is line-anchored AND count-pinned, not merely
(file, identifier)-keyed: Codex (PR #988) showed the coarser key would silently suppress a
*second*, genuinely-stale mention of an already-allowed identifier — whether it lands on a
different line, or as an extra hit on the *same* line (two inline spans) — while the audit
stayed green. That is the identity-scoping trap the suppression audit was built to catch.
Anchoring on (line, count) closes both: any hit not at an allowed line, and any hit beyond
the allowed count on an allowed line, is reported. (There is deliberately no directory-scope
exclusion to audit — no subtree here is uniformly frozen, so frozen snippets inside
maintained guides get occurrence-level allowances too; Codex, PR #988.)

The discipline is the same one the suppression audit encodes and SKUEL026 encodes for
lint suppressions: **an exemption that suppresses nothing is a finding**. A dead allow
entry is not harmless — it is a rubber stamp that will silently swallow the first real
stale name that lands on the same (file, line), so the audit fails on it and forces a
human to re-justify or delete it.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import (matches test_lint_skuel.py
# and test_stale_names_suppression.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "health"))

import stale_names as sn  # type: ignore[import-not-found]


def _scan_target_strs() -> set[str]:
    """ROOT-relative forward-slash paths the scanner actually looks at."""
    return {str(p.relative_to(sn.ROOT)) for p in sn.get_scan_targets()}


def _raw_counts(path: Path) -> Counter[tuple[int, str]]:
    """How many times the scanner raw-matches each (line, identifier) in ``path``.

    Kept as counts, not a set: a physical line can name one identifier more than once
    (two inline-code spans), and the count is exactly what the allowlist must pin.
    """
    return Counter((lineno, old) for lineno, old, _replacement, _kind in sn.scan_file(path))


def _dead_allow_entries() -> list[str]:
    """Every ALLOWED_OCCURRENCES entry whose count does not match reality, with why.

    An entry is dead / mis-scoped when:
      * the file is not a live scan target (moved, or itself excluded/skipped), so the
        allow can never fire; or
      * the audited count does not equal the raw hit count at that exact line — the line
        moved, the entry was mis-typed, or the number of same-line mentions changed. Under
        AND over both count: allowing 2 where 1 exists is a standing over-grant that will
        swallow the next same-line hit; allowing 1 where 2 exist leaves one reported (good)
        but means the entry is not describing reality (fix the count).
    """
    targets = _scan_target_strs()
    dead: list[str] = []
    for rel_path, entries in sn.ALLOWED_OCCURRENCES.items():
        if rel_path not in targets:
            dead.append(f"{rel_path}: not a live scan target — allow can never fire")
            continue
        raw = _raw_counts(sn.ROOT / rel_path)
        dead.extend(
            f"{rel_path}:{lineno} {identifier!r} allows {allow.hits} but raw-matches "
            f"{raw[(lineno, identifier)]} at that line — re-anchor / fix the count"
            for (lineno, identifier), allow in entries.items()
            if raw[(lineno, identifier)] != allow.hits
        )
    return dead


# ── ALLOWED_OCCURRENCES: real-data audit ─────────────────────────────────────


def test_allowed_files_are_live_scan_targets() -> None:
    """An allow keyed on a file the scanner never reads suppresses nothing.

    Covers the moved-file case (the file was renamed) and the double-exempt case (the
    file is already in SKIP_FILES, so the per-occurrence entry is redundant).
    """
    targets = _scan_target_strs()
    stray = [rel for rel in sn.ALLOWED_OCCURRENCES if rel not in targets]
    assert stray == [], (
        f"ALLOWED_OCCURRENCES keys are not live scan targets: {stray}. Either the file "
        "moved (fix the key) or it is already covered by SKIP_FILES (drop the redundant "
        "per-occurrence entry)."
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
        for (lineno, identifier), allow in entries.items()
        if not allow.why.strip()
    ]
    assert blank == [], f"ALLOWED_OCCURRENCES entries with an empty rationale: {blank}"


def test_every_allowed_count_is_at_least_one() -> None:
    """A grant that covers zero hits is meaningless — count must be a positive integer."""
    bad = [
        f"{rel_path}:{lineno} {identifier} hits={allow.hits}"
        for rel_path, entries in sn.ALLOWED_OCCURRENCES.items()
        for (lineno, identifier), allow in entries.items()
        if allow.hits < 1
    ]
    assert bad == [], f"ALLOWED_OCCURRENCES entries with a non-positive count: {bad}"


# ── Mechanism logic: synthetic, proves the guards bite even with empty real data ──


def test_allowed_count_is_scoped_to_one_line_and_one_identifier(monkeypatch) -> None:
    """The allow exempts ONLY the named (line, identifier), and only up to its count."""
    monkeypatch.setitem(
        sn.ALLOWED_OCCURRENCES, "docs/example.md", {(18, "KuType"): sn.Allow("why")}
    )
    assert sn._allowed_count("docs/example.md", 18, "KuType") == 1
    # The SAME identifier on a DIFFERENT line is still reported — line-anchoring closes the
    # (file, identifier) blind spot Codex flagged (PR #988, round 1).
    assert sn._allowed_count("docs/example.md", 19, "KuType") == 0
    # A different identifier at the SAME line is still scanned.
    assert sn._allowed_count("docs/example.md", 18, "KuStatus") == 0
    # The same occurrence in a DIFFERENT file is still scanned.
    assert sn._allowed_count("docs/other.md", 18, "KuType") == 0


def test_allow_count_defaults_to_one() -> None:
    """The common single-mention case needs no explicit count."""
    assert sn.Allow("why").hits == 1
    assert sn.Allow("why", hits=2).hits == 2


def test_dead_allow_audit_bites(monkeypatch) -> None:
    """Prove the positive-control audit fails on a dead entry — otherwise it is theatre."""
    # Branch A: file is not a scan target at all.
    monkeypatch.setitem(
        sn.ALLOWED_OCCURRENCES, "docs/does-not-exist.md", {(1, "KuType"): sn.Allow("x")}
    )
    assert any("does-not-exist" in problem for problem in _dead_allow_entries())

    # Branch B: a real scan target, but a (line, identifier) that raw-matches nothing
    # there — covers both a moved line and a never-tracked identifier.
    a_real_target = str(next(iter(sn.get_scan_targets())).relative_to(sn.ROOT))
    monkeypatch.setitem(
        sn.ALLOWED_OCCURRENCES,
        a_real_target,
        {(999_999, "ThisIdentifierIsNotTracked"): sn.Allow("x")},
    )
    assert any("ThisIdentifierIsNotTracked" in problem for problem in _dead_allow_entries())


def test_count_mismatch_audit_bites(monkeypatch) -> None:
    """A count that over- or under-states the real hits at the anchor is a finding.

    This is the same-line defect Codex flagged (PR #988, round 2): a single physical line
    can name one identifier twice (two inline spans). Pinning the count means a grant of 1
    where 2 exist — or 2 where 1 exists — fails the audit instead of silently absorbing the
    extra. Built on a synthetic file so it does not depend on live doc content.
    """
    fixture = sn.ROOT / "docs" / "example.md"  # not real; we drive scan_file via monkeypatch

    def fake_scan(_path: Path) -> list[tuple[int, str, str, str]]:
        # Two raw hits for KuType at line 42 (as two inline spans would produce).
        return [(42, "KuType", "EntityType", "renamed"), (42, "KuType", "EntityType", "renamed")]

    monkeypatch.setattr(sn, "scan_file", fake_scan)
    monkeypatch.setattr(sn, "get_scan_targets", lambda: [fixture])

    # Under-count: allow 1 where 2 exist.
    monkeypatch.setitem(
        sn.ALLOWED_OCCURRENCES, "docs/example.md", {(42, "KuType"): sn.Allow("why")}
    )
    assert any("42" in problem and "KuType" in problem for problem in _dead_allow_entries())

    # Exact count clears it.
    monkeypatch.setitem(
        sn.ALLOWED_OCCURRENCES, "docs/example.md", {(42, "KuType"): sn.Allow("why", hits=2)}
    )
    assert _dead_allow_entries() == []

    # Over-count: allow 3 where 2 exist — a standing over-grant.
    monkeypatch.setitem(
        sn.ALLOWED_OCCURRENCES, "docs/example.md", {(42, "KuType"): sn.Allow("why", hits=3)}
    )
    assert any("42" in problem and "KuType" in problem for problem in _dead_allow_entries())
