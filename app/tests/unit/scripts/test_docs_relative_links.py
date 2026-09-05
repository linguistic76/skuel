"""Pin ``scripts/docs_relative_links.py``'s one transform and its refusals.

The script's claim is "this link now says the same file in the relative form, and
nothing else on the line changed". Each test below is a way that claim can be quietly
false: an anchor dropped, a space left raw (which the checker reads as not-a-link), a
dead or out-of-vault target rewritten, a second link on the line swallowed, a CRLF
lost, or a rewrite whose two spellings resolve to different files.

The checker's ``ROOT`` is pointed at a fixture tree, so ``resolve_path`` — the one
resolver both the checker and the sweep use — runs against it, not the repo.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ and scripts/health/ have no __init__.py — add both for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "health"))

import dead_doc_links as ddl  # type: ignore[import-not-found]
import docs_relative_links as sweep  # type: ignore[import-not-found]


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A vault-shaped tree: three docs in two directories, one with a space, and one
    file outside ``docs/``."""
    monkeypatch.setattr(ddl, "ROOT", tmp_path)
    for rel in (
        "docs/a/one.md",
        "docs/a/sibling.md",
        "docs/b/two.md",
        "docs/sp ace/three.md",
        "core/x.py",
    ):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")
    return tmp_path


def test_cross_directory_link_keeps_its_anchor_and_text(root: Path) -> None:
    source = root / "docs/a/one.md"
    after, changes = sweep.rewrite_content("see [Two](/docs/b/two.md#sec) now\n", source)
    assert after == "see [Two](../b/two.md#sec) now\n"
    assert changes == [(1, "/docs/b/two.md#sec", "../b/two.md#sec")]


def test_sibling_becomes_a_bare_filename(root: Path) -> None:
    source = root / "docs/a/one.md"
    after, _changes = sweep.rewrite_content("[S](/docs/a/sibling.md)", source)
    assert after == "[S](sibling.md)"


def test_space_in_target_is_reencoded(root: Path) -> None:
    source = root / "docs/a/one.md"
    after, changes = sweep.rewrite_content("[T](/docs/sp%20ace/three.md)", source)
    assert after == "[T](../sp%20ace/three.md)"
    # And it still resolves to the same file through the checker's own resolver.
    assert ddl.resolve_path(changes[0][2], source).resolve() == (root / "docs/sp ace/three.md")


def test_several_links_on_one_line_are_rewritten_independently(root: Path) -> None:
    source = root / "docs/a/one.md"
    line = "[A](/docs/b/two.md), [dead](/docs/b/gone.md), [B](/docs/a/sibling.md#x)"
    after, changes = sweep.rewrite_content(line, source)
    assert after == "[A](../b/two.md), [dead](/docs/b/gone.md), [B](sibling.md#x)"
    assert [c[1] for c in changes] == ["/docs/b/two.md", "/docs/a/sibling.md#x"]


@pytest.mark.parametrize(
    "link",
    [
        "[code](/core/x.py)",  # not a docs→docs link — stays repo-root-absolute
        "[rel](../b/two.md)",  # already the rule's form
        "[root](docs/b/two.md)",  # the no-slash spelling is not this sweep's class
        "[dead](/docs/b/gone.md)",  # a dead target belongs to the sweep queue
        "[escape](/docs/../core/x.py)",  # exists, but resolves OUTSIDE docs/
        '[titled](/docs/b/two.md "t")',  # raw space: the checker never checks it
        "[web](https://example.com/docs/b/two.md)",
    ],
)
def test_links_outside_the_class_are_left_byte_identical(root: Path, link: str) -> None:
    source = root / "docs/a/one.md"
    after, changes = sweep.rewrite_content(link, source)
    assert after == link
    assert changes == []


def test_crlf_lines_survive(root: Path) -> None:
    source = root / "docs/a/one.md"
    content = "[A](/docs/b/two.md)\r\nplain\r\n"
    after, _changes = sweep.rewrite_content(content, source)
    assert after == "[A](../b/two.md)\r\nplain\r\n"


def test_links_inside_fences_and_inline_code_are_rewritten_too(root: Path) -> None:
    """The checker's link pass reads fences and inline code as links, so the sweep
    does the same — otherwise a documentation example would teach the old form and
    report dead on a rename while the checker still calls it a link."""
    source = root / "docs/a/one.md"
    content = "```\n[F](/docs/b/two.md)\n```\n`[I](/docs/b/two.md)`\n"
    after, changes = sweep.rewrite_content(content, source)
    assert after == "```\n[F](../b/two.md)\n```\n`[I](../b/two.md)`\n"
    assert len(changes) == 2


def test_verify_resolution_refuses_a_rewrite_that_changes_the_target(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sweep, "REPO_ROOT", root)
    good = sweep.Rewrite("docs/a/one.md", 1, "/docs/b/two.md", "../b/two.md")
    sweep.verify_resolution(good)
    wrong = sweep.Rewrite("docs/a/one.md", 1, "/docs/b/two.md", "sibling.md")
    with pytest.raises(sweep.PremiseError, match="rewrite refused"):
        sweep.verify_resolution(wrong)
    raw_space = sweep.Rewrite("docs/a/one.md", 1, "/docs/sp%20ace/three.md", "../sp ace/three.md")
    with pytest.raises(sweep.PremiseError, match="raw space"):
        sweep.verify_resolution(raw_space)


def test_the_sweep_parses_links_with_the_checkers_grammar() -> None:
    """One grammar: what the sweep rewrites is what ``extract_markdown_links`` checks."""
    line = "[a](/docs/x.md) and [b](/docs/y.md)"
    checked = [raw for _n, _t, raw in ddl.extract_markdown_links(line)]
    matched = [m.group(2) for m in ddl.MARKDOWN_LINK_RE.finditer(line)]
    assert checked == matched == ["/docs/x.md", "/docs/y.md"]
