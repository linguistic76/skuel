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
import markdown_fences as mf  # type: ignore[import-not-found]

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
    return {(lineno, raw, kind) for _src, lineno, raw, kind in _scan(docs_root, body).dead}


def _scan(docs_root: Path, body: str, name: str = "probe.md") -> ddl.FileScan:
    """Run the real check_file over a probe doc; return the whole scan (dead + skips)."""
    probe = docs_root / "docs" / name
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text(body, encoding="utf-8")
    return ddl.check_file(probe, verbose=False)


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


def test_one_dead_file_two_spellings_one_line_reports_once(docs_root: Path) -> None:
    """Dedup is keyed on the RESOLVED TARGET, not the raw string.

    Making `./core/x.py` checkable created a double-report: the backtick pass reports the
    `./` form while the bare pass independently matches its `/core/x.py` tail, so one
    defect produced two lines. Two spellings of one dead file on one line is one finding;
    two *different* dead files on one line must still be two (asserted below).
    """
    body = "# P\n\nSee `./core/gone.py` and `./core/other_gone.py` here.\n"
    reported = _report(docs_root, body)
    assert len(reported) == 2, f"expected one report per distinct dead file, got {reported}"
    assert {raw for _l, raw, _k in reported} == {"./core/gone.py", "./core/other_gone.py"}


def test_quoted_fence_ends_with_its_blockquote_container() -> None:
    """An unclosed `> ```bash` must not swallow the prose after the quote (Codex, #872).

    Without this the quoted branch treated every later unquoted line as fenced content,
    so an ordinary paragraph's `core/dead.py` was reported as `[code]` — the fix for one
    false negative had manufactured false positives.
    """
    leaky = "> ```bash\n> cp core/a.py x\n\nOrdinary prose naming core/dead.py here.\n"
    assert ddl.extract_fenced_paths(leaky) == [(2, "core/a.py")]
    # A properly closed quoted fence still works.
    assert ddl.extract_fenced_paths("> ```bash\n> cp core/a.py x\n> ```\n") == [(2, "core/a.py")]


# ============================================================================
# CONTAINER BOUNDARIES — the five bugs that ended the hand-written walker
# ============================================================================


def test_fence_in_nested_quote_ends_when_the_inner_quote_ends() -> None:
    """`> > ```bash` closes when the line drops to a single `>` (Codex, #872 r3).

    The hand-written walker asked only "is there still a quote marker?", so outer-quote
    prose stayed inside the fence and its paths reported as `[code]`.
    """
    content = "> > ```bash\n> > cp core/a.py x\n> core/dead.py in outer-quote prose\n"
    assert ddl.extract_fenced_paths(content) == [(2, "core/a.py")]


def test_list_item_fence_ends_when_the_list_container_ends() -> None:
    """A dedent ends the list item, and with it an unclosed fence (Codex, #872 r3).

    The old walker kept no container state, so it scanned to EOF and reported ordinary
    prose paths as `[code]`.
    """
    content = "- step:\n\n  ```bash\n  cp core/a.py x\n\nDedented prose naming core/dead.py.\n"
    assert ddl.extract_fenced_paths(content) == [(4, "core/a.py")]


@pytest.mark.parametrize(
    ("opener", "last_line"),
    [
        ("```bash", "```core/dead.py"),  # delimiter run followed by text
        ("````bash", "```core/dead.py"),  # run shorter than the opener
    ],
)
def test_last_line_of_an_unclosed_fence_is_audited(opener: str, last_line: str) -> None:
    """A near-miss delimiter must not be mistaken for a closer (Codex, #872 r4).

    An unclosed fence has no closing line to skip, so calling its last line a closer
    drops it from the audit — and a `startswith("```")` test accepts three things that
    are not closers: a shorter run, the other delimiter character, and a run followed by
    text. `_closes_fence` compares against the parser's own `token.markup` instead.
    """
    content = f"{opener}\ncp core/a.py x\n{last_line}\n"
    assert ddl.extract_fenced_paths(content) == [(2, "core/a.py"), (3, "core/dead.py")]


@pytest.mark.parametrize(
    "closer", ["```", "`````", "```   ", "> ```"]
)  # exact, longer, trailing space, blockquoted
def test_real_closing_delimiters_are_still_excluded(closer: str) -> None:
    """The other direction: making the check exact must not start reporting closers."""
    quote = "> " if closer.startswith(">") else ""
    content = f"{quote}```bash\n{quote}cp core/a.py x\n{closer}\n"
    assert ddl.extract_fenced_paths(content) == [(2, "core/a.py")]


@pytest.mark.parametrize(
    ("content", "label"),
    [
        ("```bash\n>core/generated.txt\n```\n", "unquoted"),
        ("> ```bash\n> >core/generated.txt\n> ```\n", "quoted, depth 1"),
        ("> > ```bash\n> > >core/generated.txt\n> > ```\n", "quoted, depth 2"),
    ],
)
def test_quoting_a_fence_does_not_change_what_it_reports(content: str, label: str) -> None:
    """A literal `>` in fence content must survive the container strip (Codex, #872 r6).

    `_strip_quote_prefix` stripped every leading `>` greedily, but only `quote_depth` of
    them are container markers. In `> >core/generated.txt` the second `>` is a shell
    redirect — content — and eating it handed the guard a bare path to report, while the
    identical *unquoted* redirect was correctly rejected by the `>` template marker. Same
    command, different answer depending on whether someone quoted the block.
    """
    assert ddl.extract_fenced_paths(content) == [], label


def test_depth_bounded_strip_still_finds_real_quoted_paths() -> None:
    """The other direction: bounding the strip must not resurrect the #870 blind spot."""
    quoted = f"> ```bash\n> cp {DEAD_REL} x.py\n> ```\n"
    assert ddl.extract_fenced_paths(quoted) == [(2, DEAD_REL)]
    nested = f"> > ```bash\n> > cp {DEAD_REL} x.py\n> > ```\n"
    assert ddl.extract_fenced_paths(nested) == [(2, DEAD_REL)]


def test_wrong_char_delimiter_is_content_though_its_token_stays_glued() -> None:
    """Scope pin, so the fix above is not over-claimed.

    `~~~core/dead.py` is not a valid closer for a ``` fence, so the line IS now audited
    as content. The path is still not reported — but for an unrelated and deliberate
    reason: `~` is a TEMPLATE_MARKER kept attached to its token, so the guard rejects the
    whole run. Separated by a space, it reports normally. That is the documented
    fail-safe direction (suppress rather than false-report), not a closer bug.
    """
    glued = "```bash\ncp core/a.py x\n~~~core/dead.py\n"
    assert ddl.extract_fenced_paths(glued) == [(2, "core/a.py")]
    spaced = "```bash\ncp core/a.py x\n~~~ core/dead.py\n"
    assert (3, "core/dead.py") in ddl.extract_fenced_paths(spaced)


def test_four_space_indented_delimiter_is_not_a_fence() -> None:
    """At document root CommonMark allows at most 3 leading spaces before a delimiter;
    4+ makes it an *indented code block*, so a doc literally illustrating fence syntax
    must not have its sample opened as a real fence (Codex, #872 r3)."""
    content = "Example of fence syntax:\n\n    ```bash\n    cp core/dead.py x\n    ```\n"
    assert ddl.extract_fenced_paths(content) == []


def test_tokenizer_and_guard_agree_on_every_template_marker() -> None:
    """Derived from TEMPLATE_MARKERS, so the two cannot drift apart again.

    They had: the tokenizer retained `$ ~ >` while the guard rejected only `{ < *`, so
    `core/services/$DOMAIN/service.py` was reported as a dead repo file — while the
    tokenizer's comment asserted they agreed (Codex, #872). Enumerating cases by hand
    would re-open exactly that gap the next time a marker is added.
    """
    for marker in ddl.TEMPLATE_MARKERS:
        token = f"core/services/x{marker}y/service.py"
        assert ddl.FENCE_TOKEN_RE.findall(token) == [token], (
            f"tokenizer splits on {marker!r}, so the guard never sees the whole token"
        )
        assert not ddl._looks_like_local_path(token), f"guard accepts template marker {marker!r}"


def test_quoted_path_containing_spaces_survives_tokenization() -> None:
    """`FENCE_TOKEN_RE` has no space in its class, so a spaced path shattered into
    fragments that each failed the guard — the pass's own blind spot, for a filename
    shape that already exists here as `docs/design-principles/direction w structuring.md`
    (Codex, #872)."""
    live = "docs/design-principles/direction w structuring.md"
    assert ddl.extract_fenced_paths(f'```bash\ncp "{live}" dest\n```\n') == [(2, live)]
    assert ddl.extract_fenced_paths("```bash\ncp 'docs/a b.md' dest\n```\n") == [(2, "docs/a b.md")]


def test_fence_walker_matches_commonmark_across_the_whole_tree() -> None:
    """Corpus guard: the whole scanned tree still parses to the same fence lines.

    `iter_code_fence_lines` now *is* CommonMark-backed, so this is no longer a
    hand-written-vs-parser differential; it is a canary on the surrounding glue — the
    unclosed-fence handling, the blockquote strip, the `sorted()` contract — over 400+
    real documents rather than the synthetic cases above.

    Its history is the more useful lesson. As a differential it reported ZERO
    disagreements, which I read as "the hand-written walker is equivalent to CommonMark".
    It meant only "the corpus contains none of the shapes where they differ" — review
    then found three such shapes (nested quote, list container, 4-space indent), none
    present in `docs/`. Corpus-relative agreement is not correctness, and a green
    corpus-wide check is the *weaker* evidence here; the synthetic container tests above
    are the ones that would catch a regression.

    Note the `closed` check: an unclosed fence has no closing delimiter to skip, and
    assuming one is what made the first version of this comparison report a false
    disagreement — the harness was wrong, not the code under test.
    """
    markdown_it = pytest.importorskip("markdown_it")
    md = markdown_it.MarkdownIt("commonmark")

    def path_tokens(lines: list[str], numbers: set[int]) -> set[tuple[int, str]]:
        found = set()
        for n in numbers:
            for tok in ddl.FENCE_TOKEN_RE.findall(mf.strip_quote_prefix(lines[n - 1])):
                if ddl._looks_like_local_path(tok.rstrip(".,;:")):
                    found.add((n, tok.rstrip(".,;:")))
        return found

    scanned, disagreements = 0, []
    for doc in ddl.get_md_files()[0]:
        content = doc.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        truth: set[int] = set()
        for token in md.parse(content):
            if token.type != "fence" or not token.map:
                continue
            start, end = token.map
            closed = end - 1 < len(lines) and lines[end - 1].lstrip().startswith(("```", "~~~"))
            truth.update(range(start + 2, (end - 1 if closed else end) + 1))
        mine = {n for n, _lang, _line in ddl.iter_code_fence_lines(content)}
        if path_tokens(lines, mine) != path_tokens(lines, truth):
            disagreements.append(str(doc.relative_to(ddl.ROOT)))
        scanned += 1

    assert scanned > 100, f"only {scanned} docs scanned — the corpus guard is vacuous"
    assert disagreements == [], f"fence walker diverges from CommonMark in: {disagreements}"


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
        # Naming-convention metavariables — the subject the reader substitutes, as
        # distinct from the version/date metavariables above (PR B5).
        "docs/patterns/FEATURE_NAME.md",
        "docs/architecture/SYSTEM_NAME.md",
        "docs/decisions/ADR-XXX.md",
        "docs/decisions/ADR-0XX-example.md",
        "docs/patterns/FEATURE_X.md",
        ".claude/skills/skill-name/SKILL.md",
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
        # The wide rule that was measured and REJECTED — "reject uppercase stems" —
        # would have shadowed these, and every one of the ~200 real docs shaped like
        # them. They pin why the metavariable discriminators are four narrow shapes
        # rather than one broad one.
        "docs/patterns/ANY_USAGE_POLICY.md",
        "docs/patterns/AUTH_PATTERNS.md",
        # Lowercase `_name` is an ordinary module suffix; only the UPPERCASE
        # metavariable is a stand-in, which is why that rule does not fold case.
        "core/models/enums/relationship_names.py",
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


def test_every_pass_consults_both_vocabularies(docs_root: Path) -> None:
    """THE guard-drift pin: all four passes reject a stand-in, not just the two wired.

    The backtick and fence passes reached `_is_placeholder` through
    `_looks_like_local_path`; `extract_bare_paths` and `_is_checkable_link_target`
    called only `_has_template_marker`. So a token already IN the placeholder
    vocabulary was reported by those two anyway — 5 findings, measured 2026-09-01.

    One probe per pass, each carrying a shape from the OTHER vocabulary than the pass
    historically consulted, so a regression in either direction fails here.
    """
    body = (
        "# P\n\n"
        "Bare: /docs/patterns/NEW_FEATURE.md\n\n"  # bare pass, placeholder vocabulary
        "Link: [T](adapters/.../fragments.py)\n\n"  # link pass, placeholder vocabulary
        "Backtick: `core/services/{domain}/x.py`\n\n"  # backtick pass, template markers
        "```bash\ncp core/services/your_service.py .\n```\n"  # fence pass, placeholders
    )
    assert _report(docs_root, body) == set()


def test_bare_pass_rejects_a_placeholder_already_in_the_vocabulary(docs_root: Path) -> None:
    """The proof that named the drift: `new_feature` was ALREADY a topic marker.

    Extending the vocabulary could never have silenced this one — the pass did not
    consult the vocabulary at all. That ordering is why the two narrowings shipped
    together and not vocabulary-first.
    """
    assert ddl._is_placeholder("/docs/patterns/NEW_FEATURE.md") is True
    assert ddl.extract_bare_paths("see /docs/patterns/NEW_FEATURE.md\n") == []


def test_elided_generic_subscript_is_not_a_link(docs_root: Path) -> None:
    """A generic whose argument list is ELIDED survives the raw-space discriminator.

    `[T](...)` has no space in its destination, so B1's shape guard cannot see it; the
    elided-path-segment substring already in the vocabulary is what rejects it. The
    `http`-prefixed form is the reason this is a SUBSTRING test and not an exact match:
    an exact-match rule would have missed it (Codex, PR #1222).
    """
    for destination in ("...", "http..."):
        assert _report(docs_root, f"# P\n\nrequire_found[T]({destination})\n") == set(), destination
    # …while a real elision-free dead destination still reports.
    assert _report(docs_root, f"# P\n\n[x]({DEAD_REL})\n") == {(3, DEAD_REL, "link")}


def test_metavariable_rules_are_stem_scoped_and_case_sensitive() -> None:
    """Both scopings are load-bearing, and each has a near-miss on the other side.

    STEM, not segment: an extension must not defeat the suffix test. CASE-SENSITIVE:
    `_NAME` is a metavariable while `relationship_names.py` is an ordinary module, and
    folding case here would widen the rule past what was measured.
    """
    assert ddl._is_metavariable_segment("FEATURE_NAME.md") is True
    assert ddl._is_metavariable_segment("FEATURE_NAME") is True
    assert ddl._is_metavariable_segment("relationship_names.py") is False
    assert ddl._is_metavariable_segment("feature_name.py") is False
    # The all-X token needs a non-letter boundary, and a DIGIT is one — `ADR-0XX`.
    assert ddl._is_metavariable_segment("ADR-XXX.md") is True
    assert ddl._is_metavariable_segment("ADR-0XX-example.md") is True
    # A single `X` is not a token; `_X` is caught by the suffix rule, not this one.
    assert ddl.PLACEHOLDER_ALL_X_RE.search("FEATURE_X") is None
    assert ddl._is_metavariable_segment("FEATURE_X.md") is True


def test_related_architecture_is_deliberately_still_reported() -> None:
    """The ninth of nine, excluded ON PURPOSE — a one-off rule is pure shadow risk.

    It fits no discriminator, and this pin is what keeps that a DECISION rather than an
    oversight: if a future entry ever swallows it, this test says so and the rule gets
    re-argued instead of quietly widening.
    """
    assert ddl._is_placeholder("/docs/architecture/RELATED_ARCHITECTURE.md") is False


def test_placeholder_guard_only_ever_subtracts() -> None:
    """Directional pin. `_is_placeholder` gates reports OFF, so a gap costs one noisy
    advisory line while an over-match costs real coverage. It must never be read as
    evidence that something IS broken — nothing may branch on a True to report."""
    assert ddl._is_placeholder("core/services/your_service.py") is True
    assert ddl._is_placeholder(DEAD_REL) is False


# ============================================================================
# THE LINK-DESTINATION GUARD — Python subscripts are not links (PR B1)
# ============================================================================


def test_generic_subscript_is_not_read_as_a_link(docs_root: Path) -> None:
    """THE class: `Backend[T](driver, "Task", Task)` parses as `[T](driver, "Task", Task)`.

    24 findings measured on the live tree 2026-09-01, every one a Python generic
    subscript and not one an actual link — ADR-019/023 and the pytest skill are dense
    with them. The link pass was the only one of the four with no shape guard at all.
    """
    body = '# P\n\nbackend = UniversalNeo4jBackend[T](driver, "Task", Task)\n'
    assert _report(docs_root, body) == set()


@pytest.mark.parametrize(
    "target",
    [
        'driver, "Task", Task',  # the dominant live shape
        "Generic[B, T]",  # ADR-023:72
        "name: str, value: T",  # pydantic skill
        "data: dict[str, Any], entity_class: type[T]",  # ASYNC_SYNC_DESIGN_PATTERN:141
    ],
)
def test_raw_space_destinations_are_not_checkable(target: str) -> None:
    """A raw space is the discriminator, and it is CommonMark-grounded rather than
    heuristic: an unescaped space cannot appear in a link destination at all."""
    assert not ddl._is_checkable_link_target(target)


def test_comma_is_not_a_rejection_signal() -> None:
    """The narrowing that would have been wrong. The arc's first sketch rejected commas
    too — but the corpus's six comma-bearing destinations are all correctly
    `%20`-encoded vault links, and one of them names a REAL file. Rejecting commas would
    have declared a live link uncheckable to remove a false positive that the encoding
    fix removes properly.
    """
    encoded = "dp%20-%20emergence,%20patience,%20non-attachment.md"
    assert ddl._is_checkable_link_target(encoded)


def test_link_destination_with_a_template_marker_is_skipped() -> None:
    """Latent-gap pin, measured zero on the live tree (like the blockquoted-fence case).

    `core/services/{domain}/x.py` in backticks is rejected by `_looks_like_local_path`
    while the identical token as a link destination was reported — one token, two
    answers, decided by which pass saw it first.
    """
    for marker in ddl.TEMPLATE_MARKERS:
        assert not ddl._is_checkable_link_target(f"core/services/x{marker}y/service.py")


def test_ordinary_dead_link_is_still_reported(docs_root: Path) -> None:
    """Positive control for the guard: it must not have quieted the link pass itself."""
    assert _report(docs_root, f"# P\n\nSee [the service]({DEAD_REL}).\n") == {(3, DEAD_REL, "link")}


# ============================================================================
# URL-DECODING — `%20` is a space, not a filename character (PR B1)
# ============================================================================


def test_percent_encoded_destination_resolves_to_the_real_file(docs_root: Path) -> None:
    """`resolve_path` never unquoted, so a correctly-encoded citation of a real
    space-bearing file reported dead purely because of its encoding."""
    real = docs_root / "docs" / "a b, c.md"
    real.write_text("x", encoding="utf-8")
    assert _report(docs_root, "# P\n\n[note](a%20b,%20c.md)\n") == set()


def test_percent_encoded_destination_of_a_missing_file_still_reports(docs_root: Path) -> None:
    """The other direction: decoding must not turn the pass off, only resolve it."""
    reported = {raw for _l, raw, _k in _report(docs_root, "# P\n\n[note](a%20b,%20c.md)\n")}
    assert reported == {"a%20b,%20c.md"}


def test_live_encoded_citation_of_a_real_file_resolves() -> None:
    """Live-tree pin, because the fixture above proves only the mechanism.

    This exact citation sits at `dp - emergence, patience, non-attachment.md:301` and
    names its own file. It reports dead without the unquote and clean with it — the one
    finding in the parser class that resolves to a REAL file rather than disappearing.
    """
    source = ddl.ROOT / "docs" / "design-principles" / "dp - emergence, patience, non-attachment.md"
    target = ddl.resolve_path("dp%20-%20emergence,%20patience,%20non-attachment.md", source)
    assert target is not None and target.exists()


# ============================================================================
# THE BARE PASS AND THE SHARED MARKER PREDICATE (PR B1)
# ============================================================================


@pytest.mark.parametrize(
    "token",
    [
        "/ui/**/*.py",  # ADR-071:311 — Tailwind content glob
        "/static/js/*.js",  # ADR-071:315
        "/ui/{domain}/layout.py",  # skuel-ui/reference.md:12
    ],
)
def test_bare_pass_rejects_globs_and_templates(docs_root: Path, token: str) -> None:
    """`extract_bare_paths` never consulted a shape guard, so glob and template patterns
    were reported as dead repo files — 7 findings measured 2026-09-01."""
    assert _report(docs_root, f"# P\n\nContent scanned from {token} here.\n") == set()


def test_bare_pass_rejects_every_marker_its_tokenizer_admits() -> None:
    """Derived from TEMPLATE_MARKERS rather than hand-listed, the same discipline the
    fence tokenizer/guard pair uses — a marker added later must not need a second edit.

    Scoped to the markers the bare-path regex can actually produce: its character class
    already excludes `<` and `>`, so those never reach the check.
    """
    for marker in ddl.TEMPLATE_MARKERS:
        token = f"/ui/x{marker}y/layout.py"
        if not ddl.extract_bare_paths(f"see {token} here"):
            continue  # the regex excluded the marker; nothing for the guard to reject
        assert ddl.extract_bare_paths(f"see {token} here") == [], marker


def test_bare_pass_still_reports_a_plain_dead_absolute(docs_root: Path) -> None:
    """Positive control: the marker rejection must not quiet the pass."""
    assert _report(docs_root, f"# P\n\nSee {DEAD_ABS} here.\n") == {(3, DEAD_ABS, "bare")}


# ============================================================================
# TWO-PATH JOINS — and why spaces are NOT rejected wholesale (PR B1)
# ============================================================================


def test_two_path_join_span_is_not_one_path() -> None:
    """A prose join names TWO paths, so it resolves to neither and reports as a dead
    file nobody ever cited — 9 findings measured 2026-09-01."""
    join = "core/services/submissions/ + core/services/feedback/report_project_service.py"
    assert not ddl._looks_like_local_path(join)


def test_spaces_are_not_rejected_wholesale() -> None:
    """⚠️ The narrowing that must stay narrow (Codex, PR #872).

    The guard is shared with the fence pass, whose quoted-span handling exists precisely
    so a space-bearing filename survives tokenization. A blanket space rejection would
    undo that AND lose a live finding: the guide's `FastHTML Best Practices` citation at
    `docs/patterns/FASTHTML_TYPE_HINTS_GUIDE.md:433` is a genuinely dead path with two
    spaces in it. Its separator is a literal EN DASH, escaped below because ruff's
    ambiguous-character rule rejects the raw glyph — the value must stay byte-identical
    to the live citation for this pin to mean anything.
    """
    assert ddl._looks_like_local_path("/docs/FastHTML Best Practices \u2013 fasthtml.html")
    assert ddl._looks_like_local_path("docs/design-principles/direction w structuring.md")


def test_dead_space_bearing_path_in_a_quoted_fence_is_still_reported(docs_root: Path) -> None:
    """The other half of the #872 pin: the quoted-fence path stays *detectable* when the
    file is DEAD, which is the only case that produces a finding."""
    body = '# P\n\n```bash\ncp "docs/gone file.md" dest\n```\n'
    assert _report(docs_root, body) == {(4, "docs/gone file.md", "code")}


# ============================================================================
# SCOPE CARVE-OUTS — excluded, counted, and printed (PR B1)
# ============================================================================


def test_carve_out_entries_all_exist() -> None:
    """Stale-registration guard. A carve-out naming a file that no longer exists is a
    silent no-op, and the skip count it inflates is the only thing that would say so."""
    missing = [
        rel for rel in (*ddl.FREEFORM_FILES, *ddl.TEMPLATE_FILES) if not (ddl.ROOT / rel).is_file()
    ]
    assert missing == [], f"carve-out entries no longer in the tree: {missing}"
    for directory in (*ddl.TEMPLATE_DIRS, *ddl.HISTORY_DIRS):
        assert (ddl.ROOT / directory).is_dir(), directory
        # ...and inside the scanned tree. A carve-out for a directory this checker never
        # visits is the same silent no-op as one naming a deleted path.
        assert any((ddl.ROOT / directory).is_relative_to(base) for base in ddl.SCAN_DIRS), directory


def test_carved_out_files_are_skipped_and_counted_per_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Excluded by SCOPE, not suppressed: the counts are what keep the exclusions visible.

    Two counts, not one: the classes carve out for different reasons (links that can
    never be checked vs. links that should not be), and the 73-file history set would
    swamp the 6-file unvalidatable set if they shared a number.
    """
    monkeypatch.setattr(ddl, "ROOT", tmp_path)
    monkeypatch.setattr(ddl, "SCAN_DIRS", [tmp_path / "docs", tmp_path / ".claude" / "skills"])
    unvalidatable = (*ddl.FREEFORM_FILES, *ddl.TEMPLATE_FILES, ".claude/skills/_templates/T.md")
    history = tuple(f"{d}/2026-01-01-log.md" for d in ddl.HISTORY_DIRS)
    for rel in (*unvalidatable, *history):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"[x]({DEAD_REL})\n", encoding="utf-8")
    kept = tmp_path / "docs" / "design-principles" / "HUB_PAGES.md"
    kept.write_text(f"[x]({DEAD_REL})\n", encoding="utf-8")

    scanned, skips = ddl.get_md_files()

    assert skips.unvalidatable == len(unvalidatable)
    assert skips.history == len(history)
    assert [p.name for p in scanned] == ["HUB_PAGES.md"]


def test_a_maintained_spec_beside_the_freeform_notes_is_not_carved_out() -> None:
    """⚠️ FILE-scoped, never the directory (Codex, PR #1214). `design-principles/` holds
    freeform notes AND maintained specs; `HUB_PAGES.md` cites the deleted
    `ui/teaching/hub.py`, and a directory carve-out would hide that rot."""
    scanned, _ = ddl.get_md_files()
    names = {p.name for p in scanned}
    assert "HUB_PAGES.md" in names
    assert "direction w structuring.md" not in names


def test_run_prints_every_skip_count(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """All four counts print on EVERY run, zero included: a silent zero is how a rotted
    carve-out, a broken route matcher or a dead marker channel looks exactly like a
    clean scan. The marker count is 0 until PR B4 applies the first one — printing that
    zero is the point."""
    monkeypatch.setattr(sys, "argv", ["dead_doc_links.py"])
    ddl.main()
    out = capsys.readouterr().out
    assert "freeform notes + templates" in out
    assert "history directories" in out
    assert "registered application routes" in out
    assert f"{ddl.HISTORICAL_MARKER} markers" in out


# ============================================================================
# HISTORY DIRECTORIES — a dead link in a dated record is the record being faithful
# ============================================================================


def test_history_directories_are_carved_out_of_the_live_tree() -> None:
    """Live-tree pin: the four dated-record directories leave the scan, 226 findings
    with them (measured 2026-09-01). Directory membership IS the classification here —
    unlike `design-principles/`, these hold nothing but records."""
    rels = {p.relative_to(ddl.ROOT).as_posix() for p in ddl.get_md_files()[0]}
    for directory in ddl.HISTORY_DIRS:
        assert not any(rel.startswith(f"{directory}/") for rel in rels), directory


def test_history_carve_out_takes_only_the_dated_half_of_roadmap() -> None:
    """⚠️ `docs/roadmap/done/`, never `docs/roadmap/`. The live half is "what might
    still happen" and its dead links are ordinary rot — 14 of them on the sweep queue.
    A carve-out one directory level too high would swallow the queue it feeds."""
    rels = {p.relative_to(ddl.ROOT).as_posix() for p in ddl.get_md_files()[0]}
    assert "docs/roadmap/deferred-work.md" in rels
    assert not any(rel.startswith("docs/roadmap/done/") for rel in rels)


def test_history_dir_match_is_anchored_at_a_path_separator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sibling sharing the prefix is a different directory (the same anchoring lesson
    B2 learned when `ADR-050-typo` resolved as `ADR-050`). Carving out `docs/migrations`
    must not carve out `docs/migrations-v2`."""
    monkeypatch.setattr(ddl, "ROOT", tmp_path)
    monkeypatch.setattr(ddl, "SCAN_DIRS", [tmp_path / "docs"])
    for rel in ("docs/migrations/log.md", "docs/migrations-v2/plan.md", "docs/migrations.md"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")

    scanned, skips = ddl.get_md_files()

    assert skips.history == 1
    assert {p.name for p in scanned} == {"plan.md", "migrations.md"}


# ============================================================================
# THE HISTORICAL MARKER — per-citation, honored only where a dead link may be history
# ============================================================================

ADR_PROBE = "decisions/ADR-999-probe.md"


def test_marked_dead_citation_is_skipped_and_counted(docs_root: Path) -> None:
    """THE mechanism: an ADR's narrative citation of a deleted file opts out one line at
    a time. 70 of the 154 `decisions/` findings are narrative (measured 2026-09-01), and
    a whole-tier carve-out would have hidden the 81 standing-contract ones with them."""
    scan = _scan(
        docs_root, f"# ADR\n\nWe deleted `{DEAD_REL}`. {ddl.HISTORICAL_MARKER}\n", ADR_PROBE
    )
    assert scan.dead == []
    assert scan.marker_skips == 1
    assert scan.stale_markers == []


def test_marker_over_a_live_target_is_itself_reported(docs_root: Path) -> None:
    """⭐ The SKUEL026 inversion, and the marker's whole advantage over a carve-out: it
    stays falsifiable. A marker that silently covered a live target would be a carve-out
    in costume."""
    (docs_root / "core").mkdir()
    (docs_root / "core" / "alive.py").write_text("", encoding="utf-8")
    scan = _scan(docs_root, f"# ADR\n\nSee `core/alive.py`. {ddl.HISTORICAL_MARKER}\n", ADR_PROBE)
    assert scan.dead == []
    assert scan.marker_skips == 0
    assert [(line, reason) for _src, line, reason in scan.stale_markers] == [
        (3, "no dead reference on this line")
    ]


def test_marker_outside_the_decisions_tier_is_never_honored(docs_root: Path) -> None:
    """Scope pin. Honoring it corpus-wide would let a marker copied into a live doc
    silence the sweep queue — the one thing the ADR ruling was careful not to buy. One
    rule catches it: a marker that suppresses nothing is reported, and out of scope it
    can never suppress anything."""
    scan = _scan(
        docs_root, f"# Guide\n\nSee `{DEAD_REL}`. {ddl.HISTORICAL_MARKER}\n", "patterns/G.md"
    )
    assert {raw for _s, _l, raw, _k in scan.dead} == {DEAD_REL}
    assert scan.marker_skips == 0
    assert [reason for _src, _line, reason in scan.stale_markers] == [
        "markers are honored only in docs/decisions/"
    ]


def test_marker_line_alone_produces_no_citation(docs_root: Path) -> None:
    """The marker is inert as a reference: no path, no extension, no project prefix, and
    `<`/`>` are TEMPLATE_MARKERS besides. If it ever parsed as one, marking a line would
    manufacture the finding it was meant to remove.

    It is also the shape an author reaches for first — the marker on its own line above
    the citation. Line-scoped means that does not work, and the run says so rather than
    going quiet: the marker is reported as suppressing nothing.
    """
    scan = _scan(docs_root, f"# ADR\n\n{ddl.HISTORICAL_MARKER}\nSee `{DEAD_REL}`.\n", ADR_PROBE)
    assert {(line, raw) for _s, line, raw, _k in scan.dead} == {(4, DEAD_REL)}
    assert scan.marker_skips == 0
    assert [line for _src, line, _reason in scan.stale_markers] == [3]


@pytest.mark.parametrize(
    "spelling",
    [
        "<!-- historical: replaced by ADR-054 -->",  # a payload is not this grammar
        "<!-- Historical -->",  # one canonical spelling
        "<!-- historically we used it -->",  # prose that merely starts the same
        "<!--historical-ish-->",  # superset acceptance is the bug B2 caught
        "<!-- history -->",
        "historical",  # not a comment at all
    ],
)
def test_near_miss_grammars_are_not_markers(docs_root: Path, spelling: str) -> None:
    """⚠️ Match the SHAPE, anchored — the comment delimiters ARE the anchors, so nothing
    that merely CONTAINS the word qualifies. B2's one review finding was this class one
    layer down: a pattern anchored only at the start read `ADR-050-typo` as `ADR-050`. A
    near-miss is not a marker, so its citation stays red — fail toward reporting."""
    scan = _scan(docs_root, f"# ADR\n\nSee `{DEAD_REL}`. {spelling}\n", ADR_PROBE)
    assert {raw for _s, _l, raw, _k in scan.dead} == {DEAD_REL}
    assert scan.marker_skips == 0
    assert scan.stale_markers == []


@pytest.mark.parametrize("spelling", ["<!--historical-->", "<!--  historical  -->"])
def test_whitespace_inside_the_marker_is_flexible(docs_root: Path, spelling: str) -> None:
    """The other direction, so the grammar is narrow rather than merely strict: only
    whitespace varies, and the canonical spelling must satisfy its own pattern."""
    scan = _scan(docs_root, f"# ADR\n\nWe deleted `{DEAD_REL}`. {spelling}\n", ADR_PROBE)
    assert scan.dead == []
    assert scan.marker_skips == 1
    assert ddl.HISTORICAL_MARKER_RE.search(ddl.HISTORICAL_MARKER)


def test_one_marker_covers_every_dead_citation_on_its_line(docs_root: Path) -> None:
    """Line-scoped, which in this corpus is per-citation: 153 of 154 `decisions/`
    findings are alone on their line, and the single two-finding line (ADR-070:255,
    naming two deleted scripts) is homogeneous. ⚠️ A line mixing narrative with a
    standing contract must be SPLIT before marking — one marker would silence both."""
    body = f"# ADR\n\nDeleted `{DEAD_REL}` and `scripts/gone.py`. {ddl.HISTORICAL_MARKER}\n"
    scan = _scan(docs_root, body, ADR_PROBE)
    assert scan.dead == []
    assert scan.marker_skips == 2


@pytest.mark.parametrize(
    ("position", "body"),
    [
        # An inline code span — how prose names the marker mid-sentence.
        ("code span", f"# ADR\n\nWrite `{{shown}}` on the line. See `{DEAD_REL}`.\n"),
        # Fence content — how a doc shows the marker as a copyable sample.
        ("fence content", f"# ADR\n\n```\n{{shown}}\n```\n\nSee `{DEAD_REL}`.\n"),
        # ⚠️ The delimiter lines. A fence's INFO STRING is not a content line, so the
        # `iter_code_fence_lines` projection left this one counting (Codex, PR #1219).
        (
            "fence info string",
            f"# ADR\n\n```markdown {{shown}}\nsample\n```\n\nSee `{DEAD_REL}`.\n",
        ),
        ("fence closer", f"# ADR\n\n```markdown\nsample\n``` {{shown}}\n\nSee `{DEAD_REL}`.\n"),
    ],
)
def test_a_quoted_marker_is_prose_about_the_marker(
    docs_root: Path, position: str, body: str
) -> None:
    """Documenting this checker requires writing the shape it hunts — the same problem
    `stale_names.py` answers with a `SKIP_FILES` list. A code-span rule needs no
    registry and generalises to the next doc that names the marker. Measured: the four
    occurrences across `HEALTH_CHECKS.md` and `deferred-work.md` each reported as a
    marker-that-suppresses-nothing until this rule existed.

    The exclusion takes each fence's whole SPAN, delimiter lines included, which is why
    the last two positions are here: `FenceBlock` carries `span` precisely because "a
    delimiter line is neither content nor prose".
    """
    scan = _scan(docs_root, body.format(shown=ddl.HISTORICAL_MARKER), ADR_PROBE)
    assert {raw for _s, _l, raw, _k in scan.dead} == {DEAD_REL}, position
    assert scan.marker_skips == 0, position
    assert scan.stale_markers == [], position


def test_a_marker_in_an_info_string_cannot_suppress_that_lines_citation(
    docs_root: Path,
) -> None:
    """The failure scenario behind the finding, not just its symptom (Codex, PR #1219).

    The prose passes DO read a fence opener — that is what `FenceBlock.span` exists to
    warn about — so a citation sharing an info string with a marker would have been
    suppressed by it, silently, inside the one tier where a citation may not vanish.
    Measured on the live tree: zero findings currently sit on a delimiter line, so this
    pins a latent gap rather than a live one.
    """
    body = f"# ADR\n\n```markdown {DEAD_ABS} {ddl.HISTORICAL_MARKER}\nsample\n```\n"
    scan = _scan(docs_root, body, ADR_PROBE)
    assert {raw for _s, _l, raw, _k in scan.dead} == {DEAD_ABS}
    assert scan.marker_skips == 0


def test_no_doc_in_the_tree_carries_a_marker_that_suppresses_nothing() -> None:
    """Corpus invariant, driven over the production path — the check that catches a
    marker gone stale because its target came back, or one written where it is not
    honored. It is also what caught this PR's own documentation."""
    stale = [
        f"{source}:{lineno} — {reason}"
        for md_file in ddl.get_md_files()[0]
        for source, lineno, reason in ddl.check_file(md_file, verbose=False).stale_markers
    ]
    assert stale == [], f"markers suppressing nothing: {stale}"


def test_a_stale_marker_alone_fails_the_run(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A finding that does not redden the run is not a finding. With zero dead links and
    one marker suppressing nothing, the run must still report and exit 1."""
    monkeypatch.setattr(ddl, "ROOT", tmp_path)
    monkeypatch.setattr(ddl, "SCAN_DIRS", [tmp_path / "docs"])
    monkeypatch.setattr(sys, "argv", ["dead_doc_links.py"])
    probe = tmp_path / "docs" / "decisions" / "ADR-999-probe.md"
    probe.parent.mkdir(parents=True)
    probe.write_text(f"# ADR\n\nNothing dead here. {ddl.HISTORICAL_MARKER}\n", encoding="utf-8")

    assert ddl.main() == 1
    out = capsys.readouterr().out
    assert "Markers that suppress nothing" in out
    assert "ADR-999-probe.md:3" in out


# ============================================================================
# ROUTE-SHAPED TARGETS — matched against live registrations (PR B1)
# ============================================================================


@pytest.fixture
def fake_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway root whose `adapters/inbound/` registers exactly two routes."""
    monkeypatch.setattr(ddl, "ROOT", tmp_path)
    (tmp_path / "docs").mkdir()
    inbound = tmp_path / "adapters" / "inbound"
    inbound.mkdir(parents=True)
    (inbound / "journals_routes.py").write_text(
        "def register(rt):\n"
        '    """Docstring example: @rt("/ghost") — prose, not a registration."""\n'
        '    @rt("/journals", methods=["GET"])\n'
        "    def journals(request):\n"
        "        return None\n"
        '    @rt("/manifest.json")\n'
        "    def manifest(request):\n"
        "        return None\n",
        encoding="utf-8",
    )
    (inbound / "activity_ui_factory.py").write_text(
        "def register(rt, domain):\n"
        '    @rt(f"/{domain}")\n'
        "    def listing(request):\n"
        "        return None\n",
        encoding="utf-8",
    )
    return tmp_path


def test_registered_route_target_is_skipped_and_counted(fake_app: Path) -> None:
    """Docs cite app URLs with the same spelling a repo path uses. A live route is not a
    missing file — but the skip is counted, never silent."""
    scan = _scan(fake_app, "# P\n\nOpen [the journal](/journals) and `/manifest.json`.\n")
    assert scan.dead == []
    assert scan.route_skips == 2


def test_unregistered_route_shaped_target_stays_red(fake_app: Path) -> None:
    """⚠️ The class is defined by MATCHING a registration, never by shape (Codex, #1214).

    `/journals/browse` is exactly the trap: route-shaped, cited three times in the voice
    journaling guide, and registered nowhere since PR #420 deleted it. A shape rule would
    have hidden it; matching keeps it red for the sweep queue.
    """
    scan = _scan(fake_app, "# P\n\nSee [history](/journals/browse).\n")
    assert {raw for _s, _l, raw, _k in scan.dead} == {"/journals/browse"}
    assert scan.route_skips == 0


def test_route_paths_come_from_the_ast_not_the_text(fake_app: Path) -> None:
    """A docstring is prose. Grepping `@rt("` would have registered `/ghost` from the
    fixture's own docstring — an auditor's example silently suppressing real rot."""
    assert "/ghost" not in ddl.registered_route_paths()
    assert {"/journals", "/manifest.json"} <= ddl.registered_route_paths()


def test_fstring_route_is_not_extracted_and_its_target_stays_red(fake_app: Path) -> None:
    """Documented direction, not an oversight. The activity/domain factories register
    `@rt(f"/{domain}")`, which no static pass resolves, so the live `/tasks` keeps
    reporting. An unmatched route costs one advisory line; a wrongly-matched one hides
    real rot. Fail toward reporting."""
    assert not any(p.startswith("/tasks") for p in ddl.registered_route_paths())
    scan = _scan(fake_app, "# P\n\nSee [tasks](/tasks).\n")
    assert {raw for _s, _l, raw, _k in scan.dead} == {"/tasks"}


def test_repo_rooted_targets_are_never_route_matched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `/docs/…` or `/core/…` citation is a file path by convention. Measured: no live
    route sits under a PROJECT_PREFIX — this blocks the class if one ever does."""
    monkeypatch.setattr(ddl, "ROOT", tmp_path)
    inbound = tmp_path / "adapters" / "inbound"
    inbound.mkdir(parents=True)
    (inbound / "odd.py").write_text(
        'def register(rt):\n    @rt("/docs/patterns/gone.md")\n    def x(request):\n'
        "        return None\n",
        encoding="utf-8",
    )
    assert "/docs/patterns/gone.md" in ddl.registered_route_paths()
    assert not ddl._is_registered_route("/docs/patterns/gone.md")


def test_live_route_catalog_matches_the_real_registrations() -> None:
    """Corpus pin against the real tree: the PWA assets are registered in
    `adapters/inbound/pwa_routes.py` and match; `/journals/browse` does not exist and
    must not. If this goes quiet, the extractor stopped reading the routes tree."""
    catalog = ddl.registered_route_paths()
    assert len(catalog) > 100, f"route catalog looks empty: {len(catalog)}"
    for served in ("/manifest.json", "/service-worker.js", "/offline.html", "/journals"):
        assert ddl._is_registered_route(served), served
    for gone in ("/journals/browse", "/yaml_templates/_schemas/"):
        assert not ddl._is_registered_route(gone), gone
