"""CI-enforced: no tracked file may cite the gitignored scratch tier.

`app/plans/` is the zero-ceremony thinking surface, and its counterpart rule is that
nothing tracked may cite it — that prohibition IS the graduation trigger (CLAUDE.md
§ Documentation Architecture). CI runs tests/unit/, so this test is the gate that
stops the class from regrowing. Logic lives in scripts/audit_untracked_refs.py (also
`./dev quality` check 6c).

The class this guards is not hypothetical: an August 2026 audit found 35 such
citations across 21 files, 23 of them pointing at documents that existed nowhere.
`scripts/health/dead_doc_links.py` never saw them — it validates links inside .md
files only, so a dead path in a Python docstring went unchecked for months.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit_untracked_refs.py"


def _load_guard():
    """Load by path — the guard runs on bare Python in CI and pulls in no app deps."""
    spec = importlib.util.spec_from_file_location("audit_untracked_refs", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_tracked_file_cites_the_scratch_tier() -> None:
    """The gate itself: zero citations, zero tracked files under plans/."""
    guard = _load_guard()
    citations, under_scratch = guard.find_violations()

    assert not citations, "Tracked file(s) cite a gitignored scratch document:\n" + "\n".join(
        f"  {rel}:{lineno}  {line[:100]}" for rel, lineno, line in citations
    )
    assert not under_scratch, (
        "Tracked file(s) live under a gitignored scratch directory "
        "(gitignore does not apply to already-tracked files — `git rm --cached`):\n"
        + "\n".join(f"  {rel}" for rel in under_scratch)
    )


class TestCitationPattern:
    """The regex has to separate a POINTER AT scratch from prose ABOUT the tier."""

    def test_flags_the_citation_shapes_this_arc_actually_found(self) -> None:
        guard = _load_guard()
        for line in (
            "See: /home/mike/.claude/plans/upload-userentry-integration.md",
            "See: /.claude/plans/ku-decomposition-domain-types.md",
            "Contract: /plans/uidless-vault-entry-identity-upsert.md",
            "See: plans/moc-knowledge-channel-design-notes.md",
            "- Plan (full design): `~/.claude/plans/secrets-out-of-worktree.md`",
            "See: plans/design_handoff_calendar_month/README.md",
        ):
            assert guard.SCRATCH_CITATION.search(line), f"should flag: {line}"

    def test_does_not_flag_prose_about_the_tier(self) -> None:
        """CLAUDE.md defines this rule and .gitignore implements it — both name
        `plans/` without pointing at a document. Flagging them would make the
        guard reject the policy that authorizes it."""
        guard = _load_guard()
        for line in (
            "plans/",  # the .gitignore pattern
            "- `app/plans/` (**gitignored**, outside `docs/`) — the thinking surface",
            "Finished scratch moves to `app/plans/done/` — same gitignored tier",
            "its source document was an untracked `plans/` file that no longer exists",
            "`plans/done/` and `docs/roadmap/done/` are not two archives of the same thing",
        ):
            assert not guard.SCRATCH_CITATION.search(line), f"should NOT flag: {line}"

    def test_does_not_flag_a_tracked_docs_plans_path(self) -> None:
        """`docs/plans/` would be TRACKED content, not the scratch tier. No such
        directory exists today, but the guard must not claim jurisdiction over one."""
        guard = _load_guard()
        assert not guard.SCRATCH_CITATION.search(
            "- Strategic Quality Initiatives Plan: `/docs/plans/STRATEGIC_QUALITY_INITIATIVES_PLAN.md`"
        )
