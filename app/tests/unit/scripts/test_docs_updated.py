"""Pin the docs ``updated:`` auto-stamp — shared mechanics, stamper and guard.

Why this file exists
--------------------
The feature's whole claim is that ``updated:`` becomes *true by construction*, and
every way that claim can be quietly false is a parsing or history-walking detail
rather than anything a reader would notice. The registration in
``docs/roadmap/deferred-work.md`` accumulated sixteen such traps over ten review
rounds of the contract alone; the tests below are the ones that a future edit could
plausibly reintroduce.

Three deserve naming, because each looks like a simplification:

  * **Never ``yaml.safe_load`` the block.** 35 of 412 docs carry an unquoted
    ``title: ADR-013: KU UID Flat Identity Design`` — a YAML syntax error whose
    ``updated:`` line is nonetheless perfectly well-formed. A YAML-parsing guard
    sits red on all 35 for a ``title:`` defect it does not own.
  * **Leading block only.** Two docs carry a documentation *example* of ``updated:``
    in their body. A whole-file count calls both duplicates.
  * **Stamp-only commits are skipped.** The backfill becomes the newest commit for
    every file it rewrites; compared naively it invalidates its own output.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

# scripts/ has no __init__.py — add it to sys.path for import (matches
# test_duplicate_headings.py). Written without an intermediate variable because a
# plain assignment before an import is what E402 fires on; ruff exempts bare
# sys.path manipulation.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "health"))

import docs_updated as guard  # type: ignore[import-not-found]
import docs_updated_field as field_mod  # type: ignore[import-not-found]

STAMP = date(2026, 9, 1)
Q3 = "'" * 3  # a literal ''' — written this way to keep the source quotable


# ============================================================================
# find_updated — the leading block, nothing else
# ============================================================================


def test_finds_a_plain_iso_value() -> None:
    found = field_mod.find_updated("---\nupdated: 2026-04-20\n---\n\nbody\n")
    assert found is not None
    assert found.value == "2026-04-20"
    assert found.parsed == date(2026, 4, 20)


def test_accepts_a_quoted_scalar() -> None:
    """25 of 219 docs quote the date; a parser that does not strip quotes calls
    every one of them fieldless — which is how the first census of this corpus
    counted 194 dated docs when the true figure was 219."""
    found = field_mod.find_updated("---\nupdated: '2026-04-20'\n---\n")
    assert found is not None
    assert found.parsed == date(2026, 4, 20)


def test_reads_the_field_from_frontmatter_that_is_not_valid_yaml() -> None:
    """An unquoted ``title:`` with a colon-space is a YAML error on 35 real docs.

    Their ``updated:`` is fine, and a guard that YAML-parses reports all 35 as
    unparsable — a permanently red gate for a defect in a different key.
    """
    content = "---\ntitle: ADR-013: KU UID Flat Identity\nupdated: 2026-08-14\n---\n"
    import yaml

    with pytest.raises(yaml.YAMLError):
        yaml.safe_load(content.split("---")[1])

    found = field_mod.find_updated(content)
    assert found is not None
    assert found.parsed == date(2026, 8, 14)


def test_a_body_example_is_not_a_duplicate() -> None:
    """``docs/README.md`` and ``patterns/CYPHER_VS_APOC_STRATEGY.md`` each show an
    ``updated:`` line as documentation. A whole-file count reds the gate on both."""
    content = "---\nupdated: 2026-04-20\n---\n\nWrite the field like this:\n\nupdated: 2026-01-01\n"
    found = field_mod.find_updated(content)
    assert found is not None
    assert found.occurrences == 1


def test_two_keys_in_the_block_are_a_duplicate() -> None:
    found = field_mod.find_updated("---\nupdated: 2026-04-20\nupdated: 2026-05-01\n---\n")
    assert found is not None
    assert found.occurrences == 2


def test_a_blank_line_after_the_opening_fence_does_not_shift_the_index() -> None:
    """`split_frontmatter`'s opening fence is `^---\\s*\\n`, and `\\s*` swallows a blank
    line following the `---` — so the raw block can start on file line 2 while an
    offset-from-raw calculation assumes line 1. Stamping then overwrote `title: X` and
    left the real `updated:` behind: silent metadata loss plus a duplicate key
    (Codex P1 on #1212). The index is taken from the FILE's lines, so it is right by
    construction."""
    source = "---\n\ntitle: X\nupdated: 2020-01-01\n---\n\nbody\n"
    found = field_mod.find_updated(source)
    assert found is not None
    assert source.split("\n")[found.line_index].startswith("updated:")

    out = field_mod.apply_stamp(source, STAMP)
    assert "title: X" in out
    assert field_mod.find_updated(out).occurrences == 1  # type: ignore[union-attr]
    assert "2020-01-01" not in out


def test_a_nested_key_is_not_the_field() -> None:
    """Column 0 only — ``  updated:`` under some other mapping is a different fact."""
    assert field_mod.find_updated("---\nmetadata:\n  updated: 2026-04-20\n---\n") is None


def test_no_frontmatter_is_no_field() -> None:
    assert field_mod.find_updated("# Just a heading\n") is None


@pytest.mark.parametrize(
    "raw_line",
    [
        "updated: '2026-09-01\"",  # mismatched pair
        "updated: " + Q3 + "2026-09-01" + Q3,  # repeated quotes
        "updated: '2026-09-01",  # unclosed
        'updated: 2026-09-01"',  # trailing only
    ],
)
def test_mismatched_quotes_do_not_unwrap_into_a_valid_date(raw_line: str) -> None:
    """``strip("'\"")`` removes the character class from both ends, so every one of
    these reduced to a clean ISO date — malformed frontmatter reading as correctly
    stamped and passing the guard indefinitely (Codex P2 on #1212). Exactly one matching
    pair is unwrapped, so these reach the ``unparsable`` verdict instead."""
    found = field_mod.find_updated(f"---\n{raw_line}\n---\n")
    assert found is not None
    assert found.parsed is None


def test_a_non_iso_value_does_not_parse() -> None:
    found = field_mod.find_updated("---\nupdated: April 2026\n---\n")
    assert found is not None
    assert found.parsed is None


# ============================================================================
# apply_stamp — four shapes, one line touched
# ============================================================================


def test_rewrites_in_place_never_appends() -> None:
    out = field_mod.apply_stamp("---\ntitle: X\nupdated: 2020-01-01\n---\n\nbody\n", STAMP)
    assert out == "---\ntitle: X\nupdated: 2026-09-01\n---\n\nbody\n"
    assert out.count("updated:") == 1


def test_preserves_the_authors_quoting() -> None:
    out = field_mod.apply_stamp("---\nupdated: '2020-01-01'\n---\n", STAMP)
    assert out == "---\nupdated: '2026-09-01'\n---\n"


def test_inserts_into_an_existing_block_before_the_closing_fence() -> None:
    out = field_mod.apply_stamp("---\ntitle: X\n---\n\nbody\n", STAMP)
    assert out == "---\ntitle: X\nupdated: 2026-09-01\n---\n\nbody\n"


def test_creates_the_block_for_a_doc_that_has_none() -> None:
    """A new doc must be stamped, not skipped: it lands through a perfectly normal
    commit, and skipping it is the hook failing at its one job."""
    out = field_mod.apply_stamp("# Title\n\nbody\n", STAMP)
    assert out == "---\nupdated: 2026-09-01\n---\n\n# Title\n\nbody\n"


def test_block_creation_adds_no_deletion_when_the_doc_starts_blank() -> None:
    """Stripping the author's own leading blank would turn a pure insertion into an
    insertion PLUS a deletion, pushing the commit past the stamp-only shortlist —
    so the guard would read the backfill as substantive and fail on that file."""
    out = field_mod.apply_stamp("\n# Title\n", STAMP)
    assert out == "---\nupdated: 2026-09-01\n---\n\n# Title\n"
    assert out.endswith("\n# Title\n")


@pytest.mark.parametrize(
    "source",
    [
        "---\r\ntitle: X\r\nupdated: 2020-01-01\r\n---\r\n\r\nbody\r\n",  # rewrite
        "---\r\ntitle: X\r\n---\r\nbody\r\n",  # insert into an existing block
        "# Title\r\n\r\nbody\r\n",  # create the block
        "\r\n# Title\r\n",  # create, over a document that already starts blank
    ],
)
def test_a_crlf_document_keeps_crlf(source: str) -> None:
    """Writing one LF line into a CRLF file leaves mixed endings in the index, and
    reading/writing the worktree without `newline=""` rewrites the WHOLE file to LF —
    so the two disagree about lines nobody edited, which is precisely the partial
    staging the stamper exists to protect (Codex P2 on #1212)."""
    out = field_mod.apply_stamp(source, STAMP)
    field = field_mod.find_updated(out)
    assert field is not None and field.parsed == STAMP and field.occurrences == 1
    assert "\n" not in out.replace("\r\n", "")
    assert "\r" not in out.replace("\r\n", "")


@pytest.mark.parametrize(
    "source",
    [
        "---\r\ntitle: X\nupdated: 2020-01-01\r\n---\r\n\r\nbody\r\n",
        "---\ntitle: X\r\nupdated: 2020-01-01\n---\n\nbody\n",
        "---\r\ntitle: X\n---\r\nbody\n",
    ],
)
def test_mixed_line_endings_are_stamped_correctly(source: str) -> None:
    """Choosing ONE ending for the whole file makes the writer index a different list
    than `find_updated` did: on the first case it replaced the closing `---` fence
    (silently corrupting the document), and on the second it raised `IndexError`
    (Codex P2 on #1212). Every split here is on `\n`, and each line keeps its own `\r`.
    """
    out = field_mod.apply_stamp(source, STAMP)
    field = field_mod.find_updated(out)
    assert field is not None and field.parsed == STAMP and field.occurrences == 1
    # The document still closes its frontmatter — the fence was not the line replaced.
    assert field_mod.has_malformed_frontmatter(out) is False


def test_stamping_the_same_date_is_a_no_op() -> None:
    content = "---\nupdated: 2026-09-01\n---\n"
    assert field_mod.apply_stamp(content, STAMP) is content


def test_stamping_is_idempotent() -> None:
    once = field_mod.apply_stamp("# T\n", STAMP)
    assert field_mod.apply_stamp(once, STAMP) == once


# ============================================================================
# scope
# ============================================================================


@pytest.mark.parametrize(
    "path,expected",
    [
        ("app/docs/patterns/X.md", True),
        ("app/docs/design-principles/direction w structuring.md", True),
        ("app/docs/roadmap/done/x.md", True),  # archives are NOT exempt
        ("app/docs/patterns/X.py", False),
        ("app/.claude/skills/python/SKILL.md", False),  # carries last_updated already
        ("CLAUDE.md", False),
        ("docs/patterns/X.md", False),  # CWD-relative — the path-base trap
    ],
)
def test_scope(path: str, expected: bool) -> None:
    assert field_mod.in_scope(path) is expected


# ============================================================================
# Generated artifacts are excluded — their drift tests are the stronger guarantee
# ============================================================================


def test_a_generated_artifact_is_excluded() -> None:
    """Stamping one breaks the byte-comparison its generator's drift test performs —
    `test_generate_method_index.py` went red the moment the backfill put a block on
    `reference/BASESERVICE_METHOD_INDEX.md`. Its generator would also wipe the stamp
    on the next run, and the guard would report a correctly regenerated file as
    missing its key."""
    content = (
        "# BaseService Method Index\n\n"
        "**WARNING:** This file is AUTO-GENERATED. Do not edit manually.\n"
    )
    assert field_mod.is_generated(content) is True


@pytest.mark.parametrize(
    "content",
    [
        "# Patterns\n" + "\n" * 20 + "Some docs are AUTO-GENERATED; do not edit those.\n",
        "# Guide\n\nThis guide explains AUTO-GENERATED indexes.\n",
        "# Guide\n\nThis file is NOT auto-generated — edit it freely.\n",
        "# Guide\n\nSee the AUTO-GENERATED index for the full list.\n",
    ],
)
def test_a_doc_merely_mentioning_generated_files_is_not_excluded(content: str) -> None:
    """A positive self-assertion, not the bare phrase, and header-scoped.

    The consequence runs the wrong way for a loose match: a hand-maintained doc caught
    here is dropped from the guard permanently and SILENTLY, while a generated doc that
    omits the banner merely breaks its own drift test on the first stamp, loudly. An
    unqualified `AUTO-GENERATED` substring matches all four of these (Codex P2 on
    #1212); it also matched 12 files corpus-wide against the 2 real artifacts.
    """
    assert field_mod.is_generated(content) is False


# ============================================================================
# Malformed frontmatter — refuse, never prepend a second block
# ============================================================================


def test_an_unclosed_fence_is_malformed() -> None:
    assert field_mod.has_malformed_frontmatter("---\ntitle: X\n\nbody\n") is True
    assert field_mod.has_malformed_frontmatter("---\ntitle: X\n---\nbody\n") is False
    assert field_mod.has_malformed_frontmatter("# No frontmatter\n") is False


def test_stamping_a_malformed_doc_raises_rather_than_shadowing_its_keys() -> None:
    """`split_frontmatter` reports "no frontmatter" for an unclosed fence — the right
    answer for a reader, a dangerous one for a writer. Stamping would prepend a second,
    valid block, and the author's `title:`/`status:`/`related_skills:` would silently
    become body text: present in the file, invisible to every frontmatter parser
    (Codex P2 on #1212)."""
    broken = "---\ntitle: X\nstatus: current\n\n# Body\n"
    with pytest.raises(field_mod.MalformedFrontmatterError):
        field_mod.apply_stamp(broken, STAMP)


def test_the_guard_reports_malformed_as_itself() -> None:
    verdict = guard.evaluate(
        "app/docs/a.md",
        "---\ntitle: X\n\nbody\n",
        _history(date(2026, 8, 30), date(2026, 8, 30)),
    )
    assert verdict is not None
    assert verdict.kind == "malformed"


# ============================================================================
# History — stamp-only commits do not count as substantive
# ============================================================================


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway repo shaped like this one: docs live under ``app/docs/``."""
    root = tmp_path / "repo"
    (root / "app" / "docs").mkdir(parents=True)
    _git(root.parent, "init", "-q", "-b", "main", str(root))
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "T")
    monkeypatch.setattr(field_mod, "REPO_ROOT", root)
    return root


def _commit(repo_path: Path, message: str, when: str) -> None:
    _git(repo_path, "add", "-A")
    subprocess.run(
        ["git", "-C", str(repo_path), "commit", "-q", "-m", message],
        check=True,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(repo_path),
            "GIT_AUTHOR_DATE": when,
            "GIT_COMMITTER_DATE": when,
            "GIT_AUTHOR_NAME": "T",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "T",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        },
    )


def test_a_stamp_only_commit_is_not_the_last_substantive_one(repo: Path) -> None:
    """The exclusion that keeps the backfill from invalidating itself."""
    doc = repo / "app" / "docs" / "a.md"
    doc.write_text("---\nupdated: 2026-01-01\n---\n\nreal content\n")
    _commit(repo, "substantive", "2026-01-01T12:00:00+00:00")

    doc.write_text("---\nupdated: 2026-06-01\n---\n\nreal content\n")
    _commit(repo, "stamp only", "2026-06-01T12:00:00+00:00")

    history = field_mod.load_history({"app/docs/a.md"})["app/docs/a.md"]
    assert history.newest == date(2026, 6, 1)
    assert history.last_substantive == date(2026, 1, 1)


def test_block_creation_counts_as_stamp_only(repo: Path) -> None:
    """The backfill creates blocks on docs that never had one; that commit must be
    excluded too, or those files fail the guard the day the backfill lands."""
    doc = repo / "app" / "docs" / "b.md"
    doc.write_text("# Title\n\nbody\n")
    _commit(repo, "substantive", "2026-02-01T12:00:00+00:00")

    doc.write_text(field_mod.apply_stamp(doc.read_text(), date(2026, 2, 1)))
    _commit(repo, "backfill", "2026-08-31T12:00:00+00:00")

    history = field_mod.load_history({"app/docs/b.md"})["app/docs/b.md"]
    assert history.newest == date(2026, 8, 31)
    assert history.last_substantive == date(2026, 2, 1)


def test_a_whitespace_only_commit_is_substantive(repo: Path) -> None:
    """A commit that changes no `updated:` line is not a stamp commit, however small.

    Allowing "every changed line is a fence or a blank" WITHOUT requiring the key
    made a real commit that merely deleted two blank lines read as stamp-only, and
    three docs were dated from the wrong commit until a live run caught it. The rule
    is "touches only the stamp", which presupposes it touches the stamp.
    """
    doc = repo / "app" / "docs" / "w.md"
    doc.write_text("---\nupdated: 2026-01-01\n---\n\nbody\n\n\ntail\n")
    _commit(repo, "first", "2026-01-01T12:00:00+00:00")

    doc.write_text("---\nupdated: 2026-01-01\n---\n\nbody\n\ntail\n")
    _commit(repo, "drop a blank line", "2026-04-14T12:00:00+00:00")

    history = field_mod.load_history({"app/docs/w.md"})["app/docs/w.md"]
    assert history.last_substantive == date(2026, 4, 14)


def test_editing_a_body_example_of_the_key_is_substantive(repo: Path) -> None:
    """Two docs carry a documentation *example* of an `updated:` line in their body.

    Deciding stamp-only from raw `+`/`-` diff lines cannot tell WHERE a matched line
    sat, so a commit editing only that example was classified as stamp-only — and the
    real edit the guard exists to catch was skipped, leaving stale frontmatter green
    indefinitely (Codex P2 on #1212). Normalising both blobs is positional by
    construction: `apply_stamp` writes only the leading block, so a body difference
    survives it.
    """
    doc = repo / "app" / "docs" / "readme.md"
    doc.write_text("---\nupdated: 2026-01-01\n---\n\nWrite it like this:\n\nupdated: 2020-01-01\n")
    _commit(repo, "first", "2026-01-01T12:00:00+00:00")

    # Only the BODY example changes; the frontmatter stamp is untouched.
    doc.write_text("---\nupdated: 2026-01-01\n---\n\nWrite it like this:\n\nupdated: 2021-02-02\n")
    _commit(repo, "edit the example", "2026-06-01T12:00:00+00:00")

    history = field_mod.load_history({"app/docs/readme.md"})["app/docs/readme.md"]
    assert history.last_substantive == date(2026, 6, 1)


def test_a_quoting_change_is_substantive(repo: Path) -> None:
    """Conservative on purpose: normalisation preserves each blob's own quoting, so
    `updated: X` → `updated: 'X'` does not compare equal. Erring toward substantive
    costs a needless date; erring the other way hides a real edit."""
    doc = repo / "app" / "docs" / "q.md"
    doc.write_text("---\nupdated: 2026-01-01\n---\n\nbody\n")
    _commit(repo, "first", "2026-01-01T12:00:00+00:00")

    doc.write_text("---\nupdated: '2026-02-02'\n---\n\nbody\n")
    _commit(repo, "requote", "2026-06-01T12:00:00+00:00")

    history = field_mod.load_history({"app/docs/q.md"})["app/docs/q.md"]
    assert history.last_substantive == date(2026, 6, 1)


def test_a_malformed_blob_in_history_is_substantive_not_a_traceback(repo: Path) -> None:
    """The stamper warns about an unclosed fence but lets the commit land, so that shape
    reaches history. Letting `MalformedFrontmatterError` escape the stamp-only probe
    would replace the guard's `malformed` verdict with a traceback naming no file and no
    fix (Codex P2 on #1212)."""
    doc = repo / "app" / "docs" / "m.md"
    doc.write_text("---\nupdated: 2026-01-01\n---\n\nbody\n")
    _commit(repo, "first", "2026-01-01T12:00:00+00:00")

    # A small diff that opens a fence it never closes — inside the stamp-only shortlist.
    doc.write_text("---\nupdated: 2026-01-01\n\nbody\n")
    _commit(repo, "break the fence", "2026-06-01T12:00:00+00:00")

    history = field_mod.load_history({"app/docs/m.md"})["app/docs/m.md"]
    assert history.last_substantive == date(2026, 6, 1)


def test_a_body_edit_alongside_a_stamp_is_substantive(repo: Path) -> None:
    doc = repo / "app" / "docs" / "c.md"
    doc.write_text("---\nupdated: 2026-01-01\n---\n\nold\n")
    _commit(repo, "first", "2026-01-01T12:00:00+00:00")

    doc.write_text("---\nupdated: 2026-06-01\n---\n\nnew prose\n")
    _commit(repo, "real edit", "2026-06-01T12:00:00+00:00")

    history = field_mod.load_history({"app/docs/c.md"})["app/docs/c.md"]
    assert history.last_substantive == date(2026, 6, 1)


def test_commit_dates_are_normalised_to_utc(repo: Path) -> None:
    """One timezone for the comparison, or a valid stamp reads as a future date."""
    doc = repo / "app" / "docs" / "d.md"
    doc.write_text("body\n")
    # 2026-03-02 01:00 +05:30 is 2026-03-01 19:30 UTC — a different calendar day.
    _commit(repo, "east of utc", "2026-03-02T01:00:00+05:30")

    history = field_mod.load_history({"app/docs/d.md"})["app/docs/d.md"]
    assert history.newest == date(2026, 3, 1)


# ============================================================================
# Refusing to measure beats measuring wrongly
# ============================================================================


def test_a_shallow_clone_is_refused_not_measured(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`actions/checkout` fetches one commit by default, and there every doc's only
    commit is HEAD: the guard reports the whole corpus stale (343 of 410 measured on a
    depth-1 clone of this branch), or — at a HEAD touching no docs — a green having
    checked nothing. The false green is the worse half."""
    doc = repo / "app" / "docs" / "s.md"
    doc.write_text("---\nupdated: 2026-01-01\n---\n\nbody\n")
    _commit(repo, "first", "2026-01-01T12:00:00+00:00")
    doc.write_text("---\nupdated: 2026-01-01\n---\n\nmore body\n")
    _commit(repo, "second", "2026-06-01T12:00:00+00:00")

    shallow = tmp_path / "shallow"
    _git(tmp_path, "clone", "-q", "--depth", "1", f"file://{repo}", str(shallow))
    assert _git(shallow, "rev-parse", "--is-shallow-repository").strip() == "true"

    monkeypatch.setattr(field_mod, "REPO_ROOT", shallow)
    with pytest.raises(field_mod.ShallowHistoryError):
        field_mod.load_history({"app/docs/s.md"})


def test_an_unhistoried_path_is_refused_not_skipped(repo: Path) -> None:
    """Every tracked file has a creation commit, so a path the traversal never saw
    means the two sides were joined on different bases — `git ls-files` from `app/` is
    CWD-relative while `git log` is repo-root-relative, the mistake that once made a
    census of this corpus read a clean `0 stale`. Skipping it would be a green line
    about a document nobody checked."""
    doc = repo / "app" / "docs" / "real.md"
    doc.write_text("body\n")
    _commit(repo, "first", "2026-01-01T12:00:00+00:00")

    with pytest.raises(field_mod.ShallowHistoryError):
        field_mod.load_history({"app/docs/real.md", "docs/wrong-base.md"})


# ============================================================================
# The guard's verdicts
# ============================================================================


def _history(newest: date, substantive: date) -> field_mod.FileHistory:
    return field_mod.FileHistory(newest=newest, last_substantive=substantive)


def test_a_correctly_stamped_doc_passes() -> None:
    verdict = guard.evaluate(
        "app/docs/a.md",
        "---\nupdated: 2026-08-30\n---\n",
        _history(date(2026, 8, 30), date(2026, 8, 30)),
    )
    assert verdict is None


def test_a_squash_merge_lag_is_absorbed_by_the_rot_window() -> None:
    """``gh pr merge --squash`` builds the final commit server-side where no hook
    runs, and rewrites the author date too — so a correctly stamped doc trails its
    own merge commit. Equality would red the gate on every merge."""
    verdict = guard.evaluate(
        "app/docs/a.md",
        "---\nupdated: 2026-08-28\n---\n",
        _history(date(2026, 8, 30), date(2026, 8, 30)),
    )
    assert verdict is None


def test_rot_beyond_the_window_fails() -> None:
    verdict = guard.evaluate(
        "app/docs/a.md",
        "---\nupdated: 2026-06-01\n---\n",
        _history(date(2026, 8, 30), date(2026, 8, 30)),
    )
    assert verdict is not None
    assert verdict.kind == "stale"


def test_a_missing_field_fails_rather_than_being_skipped() -> None:
    """The bypass this guard exists to catch — ``--no-verify`` on a new doc — leaves
    no date at all, so a date-comparison-only checker stays green on it forever."""
    verdict = guard.evaluate(
        "app/docs/a.md", "# no frontmatter\n", _history(date(2026, 8, 30), date(2026, 8, 30))
    )
    assert verdict is not None
    assert verdict.kind == "missing"


def test_a_future_date_fails_the_upper_bound() -> None:
    """A lower-bound-only check stays green forever on ``updated: 2099-01-01``,
    masking every unstamped edit until the date arrives."""
    verdict = guard.evaluate(
        "app/docs/a.md",
        "---\nupdated: 2099-01-01\n---\n",
        _history(date(2026, 8, 30), date(2026, 8, 30)),
    )
    assert verdict is not None
    assert verdict.kind == "future"


def test_one_day_of_timezone_skew_is_tolerated_on_the_upper_bound() -> None:
    verdict = guard.evaluate(
        "app/docs/a.md",
        "---\nupdated: 2026-08-31\n---\n",
        _history(date(2026, 8, 30), date(2026, 8, 30)),
    )
    assert verdict is None


def test_a_duplicate_key_fails_as_itself() -> None:
    verdict = guard.evaluate(
        "app/docs/a.md",
        "---\nupdated: 2026-08-30\nupdated: 2026-08-30\n---\n",
        _history(date(2026, 8, 30), date(2026, 8, 30)),
    )
    assert verdict is not None
    assert verdict.kind == "duplicate"


def test_an_unparsable_value_is_reported_as_itself_not_as_staleness() -> None:
    """Structural defects are checked before the date comparison — saying 'stale by
    N days' about a doc with no usable date would be a lie."""
    verdict = guard.evaluate(
        "app/docs/a.md",
        "---\nupdated: last Tuesday\n---\n",
        _history(date(2026, 8, 30), date(2026, 8, 30)),
    )
    assert verdict is not None
    assert verdict.kind == "unparsable"


def test_the_report_renders_every_verdict_kind(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The findings branch runs only when something is wrong, so nothing exercised it
    until now — a crash there would land at exactly the moment the guard mattered.
    (A lambda sort key lived on this line through three reviews; `./dev quality` does
    not lint `scripts/` for SKUEL012.)"""
    findings = [guard.Finding(f"app/docs/{kind}.md", kind, "detail") for kind in guard._ORDER]

    def _collect() -> tuple[list[guard.Finding], int, list[str]]:
        return findings, 410, ["app/docs/gen-a.md", "app/docs/gen-b.md"]

    monkeypatch.setattr(guard, "collect", _collect)
    assert guard.main() == 1
    out = capsys.readouterr().out
    for kind in guard._ORDER:
        assert kind in out
    assert "2 generated doc(s) excluded" in out
    # Named, not merely counted: a wrongly-excluded doc must be discoverable.
    assert "app/docs/gen-a.md" in out


def test_every_verdict_kind_has_a_remedy_line() -> None:
    """The report prints ``_REMEDY[kind]`` — a kind added without one would crash
    the guard at exactly the moment it found something."""
    assert set(guard._ORDER) == set(guard._REMEDY)
