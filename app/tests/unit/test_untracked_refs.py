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


class TestMemoryCitationPattern:
    """Memory slugs must be told apart from document names and code symbols."""

    def test_flags_the_marked_forms_this_arc_found(self) -> None:
        """Asserted through ``_probe``, the way ``find_violations`` matches — the
        pattern is written against delimiter-flattened text, so testing it on raw
        lines would test something the guard never runs."""
        guard = _load_guard()
        for line in (
            "    project_template_relative_offset.md (memory)",
            "- `memory/feedback_leverage_maintained_software.md` — the principle",
            "Full traced rationale: memory `project_update_intents_phase7_plan`.",
            "Edge schema (per project_pathstep_lifecycle_contract.md):",
            "- Memory: `project_find_by_user_uid_vs_owns`, `project_user_uid_canonical`.",
        ):
            assert guard.MEMORY_CITATION.search(guard._probe(line)), f"should flag: {line}"

    def test_does_not_flag_tracked_document_filenames(self) -> None:
        """The regression that made this guard report 81 false positives: an
        IGNORECASE pattern reads SHOUTING doc names as memory slugs."""
        guard = _load_guard()
        for line in (
            "**File:** `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md`",
            "- `/docs/CROSS_REFERENCE_INDEX.md` - Auto-generated skill↔doc mapping",
            "`/docs/intelligence/USER_CONTEXT_INTELLIGENCE.md`",
        ):
            assert not guard.MEMORY_CITATION.search(line), f"should NOT flag: {line}"

    def test_flags_markdown_formatted_and_wrapped_markers(self) -> None:
        """Codex #1047 P2: a marker separated from its slug by markdown emphasis,
        wiki-brackets, or a NEWLINE still cites memory. Both shapes were live in
        the tree while the guard reported clean — a false clean is the failure this
        whole arc exists to prevent."""
        guard = _load_guard()
        # markdown emphasis + wiki-link between marker and slug
        assert guard.MEMORY_CITATION.search(
            guard._probe("- **Memory:** [[project_journals_discussion_arc]]")
        )
        # marker ends one line, slug begins the next (inside a comment block)
        assert guard.MEMORY_CITATION.search(
            guard._probe(
                "    # understand cache semantics before changing. See memory:",
                "    # project_lucide_mutationobserver_infinite_loop.",
            )
        )

    def test_flags_bare_wiki_links(self) -> None:
        """`[[project_foo]]` needs no marker — Python has no `[[ ]]` syntax, so
        unlike a bare backticked slug this form is unambiguous and IS gated."""
        guard = _load_guard()
        for line in (
            "- **Privacy commitment:** [[project_journal_privacy_commitment]] (ADR-073)",
            "per standing merge authorization — [[feedback_standing_merge_after_reviews]]):",
        ):
            assert guard.WIKILINK_MEMORY_CITATION.search(line), f"should flag: {line}"

    def test_flags_hyphenated_and_prefixless_slugs(self) -> None:
        """Codex #1047 round 2: real memory slugs are not all
        `project_`/`feedback_`-prefixed with underscores. `entity-label-overload`
        is hyphenated and prefixless, and two live docstrings cited it."""
        guard = _load_guard()
        for line in (
            "        not an EntityType) — see memory entity-label-overload.",
            "        conflated with ``config_lookup_label`` (see memory entity-label-overload:",
        ):
            assert guard.MEMORY_CITATION.search(guard._probe(line)), f"should flag: {line}"

    def test_does_not_flag_prose_about_ram(self) -> None:
        """The cost of widening the slug grammar: 'memory' is an ordinary English
        word here. A CUE — `see memory`, a colon, or a path slash — is what makes a
        citation, and `(?<!in-)` keeps the in-memory compound out."""
        guard = _load_guard()
        for line in (
            "    The counter lives in the in-memory rate-limit store",
            "            10-100x performance improvement over in-memory filtering.",
            "dataclass is the in-memory projection returned by the facade's lifecycle",
            "| Memory exhaustion on large result sets | Low | Medium | monitor memory usage |",
            "- Minimal memory footprint (~few KB)",
            "- Memory intensive (loading all KUs and prerequisites into Python)",
        ):
            assert not guard.MEMORY_CITATION.search(guard._probe(line)), f"should NOT flag: {line}"

    def test_does_not_flag_an_identifier_that_merely_contains_memory(self) -> None:
        """`self.user_memory[user_uid]` flattens to `user_memory user_uid` under
        _probe, which read as marker-plus-slug until \\b anchored the marker."""
        guard = _load_guard()
        for line in (
            "            self.user_memory[user_uid] = {}",
            "        if user_uid not in self.user_memory:",
            "        self.user_memory[user_uid][key] = value",
        ):
            assert not guard.MEMORY_CITATION.search(guard._probe(line)), f"should NOT flag: {line}"

    def test_does_not_flag_real_code_symbols(self) -> None:
        """Why the unmarked bare-slug form is deliberately out of scope: these are
        legitimate identifiers of exactly the shape a memory slug has."""
        guard = _load_guard()
        for line in (
            "| `user_ownership_relationship` | `str \\| None` | `'OWNS'` |",
            "requires `user_service` to be set",
            "- `feedback_points` carries typed `FeedbackPoint` objects",
            "when `user_context` is supplied the mastery split is real",
        ):
            assert not guard.MEMORY_CITATION.search(line), f"should NOT flag: {line}"


class TestScratchPathEdgeCases:
    def test_does_not_flag_a_tracked_docs_plans_path(self) -> None:
        """`docs/plans/` would be TRACKED content, not the scratch tier. No such
        directory exists today, but the guard must not claim jurisdiction over one."""
        guard = _load_guard()
        assert not guard.SCRATCH_CITATION.search(
            "- Strategic Quality Initiatives Plan: `/docs/plans/STRATEGIC_QUALITY_INITIATIVES_PLAN.md`"
        )
