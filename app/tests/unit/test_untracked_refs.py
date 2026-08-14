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

    def test_marked_wiki_links_are_caught_by_the_cue(self) -> None:
        """A MARKED wiki-link still fires: `_probe` flattens the brackets and the
        cue alternative sees `Memory: slug`. No separate wiki-link rule needed."""
        guard = _load_guard()
        assert guard.MEMORY_CITATION.search(
            guard._probe("- **Memory:** [[project_journals_discussion_arc]]")
        )

    def test_does_not_flag_a_bare_wiki_link(self) -> None:
        """Codex #1047 round 5, and it reverses an earlier assumption of mine.
        `[[target]]` is PRODUCT syntax here — `core/services/ingestion/moc_links.py`
        parses wiki-links for MOC ingestion, and a tracked fixture in
        `test_content_boundary.py` embeds them. Gating on slug shape would red the
        always-on gate on a legitimate MOC example. Resolving the target does not
        help either: a dangling MOC link is RULED legitimate in a personal vault.
        So the bare form joins the bare backticked slug on the cannot-gate list."""
        guard = _load_guard()
        for line in (
            "moc.write_text('---\\nmoc: true\\n---\\n\\n[[link-a]] [[linked-note]]\\n')",
            "- Wiki-links: ``[[target]]``, ``[[target|alias]]``, ``[[target#heading]]``",
            "See [[some-vault-note]] for the map.",
        ):
            assert not guard.MEMORY_CITATION.search(guard._probe(line)), f"should NOT flag: {line}"

    def test_basename_suppression_only_clears_unmarked_filenames(self) -> None:
        """Codex #1047 round 6. The tracked-basename check exists to stop a bare
        `project_x.md` link being read as memory — but it must not override an
        EXPLICIT marker. If a tracked file ever shares a basename with a memory
        doc, `Memory: project_x.md` still means memory; suppressing it would let a
        coincidence of naming produce a false clean."""
        guard = _load_guard()
        # Unmarked → carries the group the suppression is allowed to act on.
        unmarked = guard.MEMORY_CITATION.search(guard._probe("project_foo.md"))
        assert unmarked and unmarked.group("unmarked")
        # Cued and tagged → same filename, but the suppression must not reach them.
        for line in ("Memory: project_foo.md", "project_foo.md (memory)"):
            hit = guard.MEMORY_CITATION.search(guard._probe(line))
            assert hit, f"should flag: {line}"
            assert not hit.group("unmarked"), f"marker must outrank basename check: {line}"

    def test_accepts_uppercase_cues(self) -> None:
        """Codex #1047 round 5: `MEMORY:` and `See MEMORY:` are unambiguous marked
        citations. The CUE is case-insensitive; the slug and document-name forms
        stay lowercase, which is what keeps SHOUTING doc names out."""
        guard = _load_guard()
        for line in (
            "MEMORY: project_external_slug",
            "See MEMORY: entity-label-overload",
        ):
            assert guard.MEMORY_CITATION.search(guard._probe(line)), f"should flag: {line}"
        assert not guard.MEMORY_CITATION.search(
            guard._probe("**File:** `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md`")
        )

    def test_does_not_flag_a_path_qualified_document_link(self) -> None:
        """Codex #1047 round 4, the dangerous direction: an unqualified prefix
        match reads a legitimate tracked doc as memory. In an ALWAYS-ON gate a
        false positive reds every PR, which is worse than letting one citation
        slip — hence both a `(?<![/\\w])` lookbehind and a tracked-file check."""
        guard = _load_guard()
        for line in (
            "see [docs/user_guide.md](docs/user_guide.md)",
            "- `/docs/reference/project_index.md` — the generated index",
        ):
            assert not guard.MEMORY_CITATION.search(guard._probe(line)), f"should NOT flag: {line}"

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

    def test_flags_the_trailing_memory_tag(self) -> None:
        """Codex #1047 round 3: the tag can FOLLOW the slug. No live instance
        existed, but PR #1046 removed citations in this exact shape — they matched
        only because those slugs ended in `.md`, so a hyphenated one would have
        passed. A gap with no current violation is still a gap."""
        guard = _load_guard()
        for line in (
            "see entity-label-overload (memory)",
            "    project_template_relative_offset.md (memory)",
            "- the lookup label has two jobs (see entity-label-overload (memory))",
        ):
            assert guard.MEMORY_CITATION.search(guard._probe(line)), f"should flag: {line}"

    def test_does_not_flag_memory_used_as_a_field_label(self) -> None:
        """Codex #1047 round 7. A bare `Memory:` is not a citation verb — it is
        also an ordinary field or metric label. `see memory X` stays permissive
        because the verb is unmistakable; the colon form requires the slug to look
        like a memory doc (backticked, prefixed, or a .md name)."""
        guard = _load_guard()
        for line in ("Peak Memory: per_worker_buffer", "Memory: page_cache"):
            assert not guard.MEMORY_CITATION.search(guard._probe(line)), f"should NOT flag: {line}"
        # …while the real observed shape of this form still fires.
        assert guard.MEMORY_CITATION.search(
            guard._probe(
                "- Memory: `project_find_by_user_uid_vs_owns`, `project_user_uid_canonical`."
            )
        )

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
