"""Pin the fenced-code-block pass in ``scripts/health/dead_doc_links.py``.

Why this file exists
--------------------
``docs/patterns/DOMAIN_LATERAL_SERVICE_QUICK_START.md`` instructed readers to
``cp core/services/goals/goals_lateral_service.py …`` for ~6 months after that file
was deleted (``e8818dc26``), and ``./dev health-links`` reported ZERO broken
references for it across 13 maintenance sweeps (PR #870). The instrument could not
see inside fenced code blocks, and how-to guides are mostly fence — so they were
precisely the doc class it structurally could not audit.

The gap was narrower than "fences are never scanned", and the distinction is the
thing this file pins. ``extract_bare_paths`` is already fence-blind, so a
*project-rooted absolute* path inside a fence was always reported; only **relative**
tokens were invisible. Hence the 4-cell matrix below: {inline, fenced} x
{relative, absolute}. Three of those cells encode long-standing behaviour and one
encodes the fix, and a regression in any of them is a silent loss of coverage.

The placeholder cases are equally load-bearing. Fences hold shell and Python, so
they carry shapes prose does not (``your_service.py``, ``alpine.X.Y.Z.min.js``,
``/etc/prometheus/prometheus.yml``). Each negative below was measured against the
live tree; three of them (``test_foo.py``, ``test_your_service.py``,
``nodes_YYYY.cypher``) are pins for real bugs the measurement caught in the first
cut of the guard.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ has no __init__.py — add it to sys.path for import (matches test_lint_skuel.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "health"))

import dead_doc_links as ddl  # type: ignore[import-not-found]

DEAD_REL = "core/services/goals/goals_lateral_service.py"
DEAD_ABS = "/core/services/goals/goals_lateral_service.py"


# ============================================================================
# THE 4-CELL MATRIX — {inline, fenced} x {relative, absolute}
# ============================================================================


@pytest.fixture
def docs_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway repo root so probe docs resolve without touching the real tree."""
    monkeypatch.setattr(ddl, "ROOT", tmp_path)
    (tmp_path / "docs").mkdir()
    return tmp_path


def _report(docs_root: Path, body: str) -> set[tuple[int, str, str]]:
    """Run the real check_file over a probe doc; return {(lineno, token, kind)}."""
    probe = docs_root / "docs" / "probe.md"
    probe.write_text(body, encoding="utf-8")
    return {(lineno, raw, kind) for _src, lineno, raw, kind in ddl.check_file(probe, verbose=False)}


def test_fenced_relative_path_is_reported(docs_root: Path) -> None:
    """THE regression: `cp <deleted file>` inside a fence must be reported.

    This is the exact shape that survived 13 maintenance sweeps. If this fails, the
    fenced pass has been dropped from check_file and how-to guides are unaudited again.
    """
    found = _report(docs_root, f"# Probe\n\n```bash\ncp {DEAD_REL} target.py\n```\n")
    assert (4, DEAD_REL, "code") in found


def test_four_cell_matrix_inline_and_fenced(docs_root: Path) -> None:
    """All four cells report. Three are long-standing behaviour; the fenced-relative
    cell is the fix. Any cell going quiet is a silent loss of coverage."""
    body = (
        "# Probe\n"
        f"\nInline relative: `{DEAD_REL}`\n"  # L3
        f"\nInline absolute: `{DEAD_ABS}`\n"  # L5
        f"\n```bash\ncp {DEAD_REL} a.py\n"  # L8  fenced relative  <- the fix
        f"cp {DEAD_ABS} b.py\n```\n"  # L9  fenced absolute
    )
    reported = {(lineno, raw) for lineno, raw, _kind in _report(docs_root, body)}
    assert (3, DEAD_REL) in reported, "inline relative regressed"
    assert (5, DEAD_ABS) in reported, "inline absolute regressed"
    assert (8, DEAD_REL) in reported, "fenced relative — the #870 blind spot — regressed"
    assert (9, DEAD_ABS) in reported, "fenced absolute regressed"


def test_fenced_absolute_keeps_its_bare_label(docs_root: Path) -> None:
    """A project-rooted absolute in a fence was always reported by the fence-blind
    `bare` pass. The newer pass runs last so it does not relabel that history."""
    found = _report(docs_root, f"# Probe\n\n```bash\ncp {DEAD_ABS} out.py\n```\n")
    assert found == {(4, DEAD_ABS, "bare")}


def test_live_path_in_fence_is_not_reported(docs_root: Path) -> None:
    """Positive control: the pass must stay silent on a path that actually exists.

    Without this, a pass that reported *nothing* would satisfy the assertions above
    only by accident, and one that reported *everything* would look like a success.
    """
    (docs_root / "core").mkdir()
    (docs_root / "core" / "real_module.py").write_text("", encoding="utf-8")
    body = "# Probe\n\n```bash\ncp core/real_module.py out.py\ncp core/gone.py out.py\n```\n"
    reported = {raw for _l, raw, _k in _report(docs_root, body)}
    assert "core/gone.py" in reported
    assert "core/real_module.py" not in reported


def test_unfenced_prose_relative_path_stays_unreported(docs_root: Path) -> None:
    """Scope pin: a bare relative path in prose is still NOT scanned.

    Only backticked, linked, project-rooted-absolute, and fenced tokens are. Prose
    like "see core/services/foo.py" remains out of scope — widening that is a
    separate decision, and this test fails if it happens by accident.
    """
    assert _report(docs_root, f"# Probe\n\nSee {DEAD_REL} for details.\n") == set()


# ============================================================================
# FENCE PARSING
# ============================================================================


def test_fence_walker_excludes_delimiters_and_outside_text() -> None:
    content = "before\n```bash\ninside\n```\nafter\n"
    assert ddl.iter_code_fence_lines(content) == [(3, "bash", "inside")]


def test_tilde_and_indented_fences_are_walked() -> None:
    """Tilde fences are valid CommonMark, and list items indent their fences."""
    assert ddl.iter_code_fence_lines("~~~python\nx = 1\n~~~\n") == [(2, "python", "x = 1")]
    walked = ddl.iter_code_fence_lines("- step:\n\n  ```sh\n  ls\n  ```\n")
    assert walked == [(4, "sh", "  ls")]


def test_inner_fence_does_not_close_an_outer_wrapper() -> None:
    """A ```` ````markdown ```` wrapper holding a ```` ```bash ```` sample stays open:
    a closer must match the delimiter char, be at least as long, and carry no info
    string. Getting this wrong silently truncates every wrapped example."""
    content = "````markdown\n```bash\ncp a.py b.py\n```\n````\nafter\n"
    walked = [line for _n, _lang, line in ddl.iter_code_fence_lines(content)]
    assert walked == ["```bash", "cp a.py b.py", "```"]
    assert "after" not in walked


def test_blockquoted_fence_is_walked() -> None:
    """A quoted example is still an example (Codex, PR #872).

    `lstrip()` drops whitespace but not the `> ` container marker, so a blockquoted
    fence never opened and its contents were skipped entirely. One lives at
    `docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md:318`. Measured delta on the live
    tree was 0 dead refs — 4 previously-invisible lines, none holding a path token — so
    this pins a *latent* gap, and only a test can keep it closed.
    """
    content = f"> ```bash\n> cp {DEAD_REL} x.py\n> ```\nafter\n"
    assert ddl.iter_code_fence_lines(content) == [(2, "bash", f"cp {DEAD_REL} x.py")]
    assert ddl.extract_fenced_paths(content) == [(2, DEAD_REL)]


def test_unquoted_fence_keeps_a_leading_redirect() -> None:
    """The quote strip is scoped to fences *opened* inside a quote.

    Stripping unconditionally would eat the `>` of a shell redirect. Narrow beats tidy:
    an over-broad strip silently rewrites content the checker is supposed to read.
    """
    assert ddl.iter_code_fence_lines("```bash\n> out.txt\n```\n") == [(2, "bash", "> out.txt")]


@pytest.mark.parametrize("token", ["./core/services/gone.py", "./scripts/gone.py"])
def test_dot_slash_relative_paths_are_checked(token: str) -> None:
    """`./core/...` is the natural copy-paste shell form and a valid citation, but it
    starts with neither `/` nor a project directory, so the guard dropped it (Codex,
    PR #872). Normalised in the shared guard, so the inline-backtick pass gains it too.
    """
    assert ddl._looks_like_local_path(token)
    assert ddl.extract_fenced_paths(f"```bash\ncp {token} x\n```\n") == [(2, token)]


def test_dot_slash_resolves_to_the_same_file_as_the_bare_form(docs_root: Path) -> None:
    """Guard and resolver must agree on what a `./` token means — otherwise a live file
    reports broken (or a dead one reports clean) purely on citation style."""
    (docs_root / "core").mkdir()
    (docs_root / "core" / "real.py").write_text("", encoding="utf-8")
    probe = docs_root / "docs" / "probe.md"
    probe.write_text("x", encoding="utf-8")
    for style in ("core/real.py", "./core/real.py"):
        target = ddl.resolve_path(style, probe)
        assert target is not None and target.exists(), style


def test_all_fence_languages_are_scanned() -> None:
    """Measured choice, not an assumption: dead tokens land in bash, python, yaml,
    cypher, javascript, markdown, html and untagged fences alike, so restricting to
    ```bash/```python would drop genuine findings and buy nothing (PR #871)."""
    for lang in ("bash", "python", "yaml", "cypher", "javascript", "html", ""):
        found = ddl.extract_fenced_paths(f"```{lang}\ncp {DEAD_REL} x\n```\n")
        assert found == [(2, DEAD_REL)], f"fence language {lang!r} not scanned"


# ============================================================================
# THE SHARED SHAPE GUARD — negatives, each measured on the live tree
# ============================================================================


@pytest.mark.parametrize(
    "token",
    [
        # Syntactic templates — the guard's original three markers.
        "core/services/{domain}/{domain}_service.py",
        "core/services/<name>_service.py",
        "core/services/*_service.py",
        # Lexical placeholders. Prose convention, invisible to the markers above.
        "core/services/your_new_service.py",
        "core/services/my_service.py",
        "core/services/new_domain/new_domain_service.py",
        "tests/unit/test_new_feature.py",
        "adapters/inbound/example_ui.py",
        "docs/patterns/YOUR_DOC.md",
        "docs/patterns/OLD_PATTERN.md",
        # `test_` prefix hides the marker behind it — first cut of the guard missed both.
        "tests/unit/test_foo.py",
        "tests/unit/test_your_service.py",
        # Version/date metavariables. `nodes_YYYY` has no \b between `_` and `Y`, which
        # is why the guard cannot use word boundaries here.
        "static/vendor/alpinejs/alpine.X.Y.Z.min.js",
        "scripts/migrations/create_conversation_nodes_YYYY.cypher",
        # Elided segment.
        "adapters/.../relationship_filter_fragments.py",
        # Hypothetical root.
        "/path/to/file.py",
        # Protocol-relative URL — passes the leading-slash test, resolves under ROOT.
        "//unpkg.com/vis-network/dist/vis-network.min.js",
    ],
)
def test_guard_rejects_placeholder_shapes(token: str) -> None:
    assert not ddl._looks_like_local_path(token), f"{token} should be rejected"


@pytest.mark.parametrize(
    "token",
    [
        DEAD_REL,
        DEAD_ABS,
        "docs/patterns/UNIFIED_INGESTION_GUIDE.md",
        "scripts/health/dead_doc_links.py",
        "monitoring/prometheus/alerts.yml",
        # Real files whose names brush the placeholder vocabulary. If the guard ever
        # widens into these, genuine rot goes unreported.
        "core/services/user_entry/user_entry_service.py",
        "tests/unit/test_base_service.py",
        "core/models/enums/entity_enums.py",
        # These three are pins for real shadowing the vocabulary caused in its first
        # cut, found by scoring the guard against every file in the tree rather than
        # against the placeholders it was written for. A substring `new_domain` ate
        # the first — a live repo file — and a bare `foo` prefix ate the other two.
        "tests/integration/test_new_domain_relationships.py",
        "ui/components/footer.html",
        "core/utils/footnotes.py",
    ],
)
def test_guard_accepts_real_citation_shapes(token: str) -> None:
    assert ddl._looks_like_local_path(token), f"{token} should be checkable"


def test_topic_marker_separates_scaffolding_from_a_real_test() -> None:
    """The pair that forced `_matches_topic_marker` to be more than a prefix test.

    Both segments contain the marker; only one is a stand-in. A prefix test shadows the
    real file, an equality test misses the scaffolded names — so this pin holds both
    ends, and either regression is a silent behaviour change.
    """
    assert ddl._is_placeholder("tests/unit/test_new_feature.py") is True
    assert ddl._is_placeholder("core/services/new_domain/new_domain_service.py") is True
    assert ddl._is_placeholder("docs/intelligence/NEW_DOMAIN_INTELLIGENCE.md") is True
    assert ddl._is_placeholder("tests/integration/test_new_domain_relationships.py") is False


def test_placeholder_vocabulary_shadows_no_file_in_the_tree() -> None:
    """Discovery pin, not a hand-enumerated list.

    The vocabulary gates reports OFF, so anything it matches is invisible to the
    checker forever — a shadowed real file is a permanent blind spot of exactly the
    kind this pass exists to close. Derive the check from the tree so a future entry
    cannot open one silently; hand-listing cases would only ever pin today's.
    """
    shadowed = [
        rel
        for rel in (
            str(p.relative_to(ddl.ROOT))
            for p in ddl.ROOT.rglob("*")
            if p.is_file() and p.suffix in ddl.LOCAL_EXTENSIONS and "__pycache__" not in p.parts
        )
        # Third-party trees are never cited by path in SKUEL docs.
        if not rel.startswith((".venv/", "node_modules/", "htmlcov/")) and ddl._is_placeholder(rel)
    ]
    assert shadowed == [], f"placeholder vocabulary hides real files: {shadowed}"


def test_template_marker_stays_attached_to_its_token() -> None:
    """FENCE_TOKEN_RE must keep `{`/`}` inside the token.

    Splitting on them would hand the guard a clean-looking fragment — the whole path
    is rejected, but `{domain}_service.py` alone would sail through as a real name.
    """
    assert (
        ddl.extract_fenced_paths("```bash\ncp core/services/{domain}/{domain}_x.py .\n```\n") == []
    )


def test_non_project_rooted_absolutes_in_fences_are_skipped() -> None:
    """Absolute paths in a fence are usually filesystem- or URL-absolute — container
    mounts and service-worker cache lists — not repo-relative. Measured on the live
    tree this rejects 20 tokens, every one a false positive."""
    for token in ("/etc/prometheus/prometheus.yml", "/offline.html", "/vault/bad.md"):
        assert ddl.extract_fenced_paths(f"```yaml\n- {token}\n```\n") == [], token
    # ...while a project-rooted absolute is still extracted.
    assert ddl.extract_fenced_paths(f"```bash\ncp {DEAD_ABS} x\n```\n") == [(2, DEAD_ABS)]


def test_placeholder_guard_only_ever_subtracts() -> None:
    """Directional pin. `_is_placeholder` gates reports OFF, so a gap costs one noisy
    advisory line while an over-match costs real coverage. It must never be read as
    evidence that something IS broken — nothing may branch on a True to report."""
    assert ddl._is_placeholder("core/services/your_service.py") is True
    assert ddl._is_placeholder(DEAD_REL) is False
