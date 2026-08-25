"""Pin the duplicate-heading guard in ``scripts/health/duplicate_headings.py``.

Why this file exists
--------------------
The guard's value rests entirely on WHERE it draws the line, not on finding repeated
strings. Measured over the authored corpus, "same text anywhere in the file" fires 137
times and "same text at the same level under the same parent" fires 3 — and the 134
difference is all legitimate structure (a ``### Tests`` under each of five PR sections).
A false positive in an always-on gate is worse than a miss, so the scoping rule is the
thing under test, case by case.

Two narrowings are also pinned because each was a measured decision that a later reader
would otherwise "fix" back into a false positive:

  * **setext headings are ignored** — an unfilled ADR template writes ``**Pros:**`` above
    an empty ``-`` bullet, and CommonMark reads a lone ``-`` after a paragraph as a setext
    underline, so the bold label becomes an ``<h2>``. Six such phantoms exist in the tree.
  * **blockquoted headings are ignored** — quoted material is someone else's outline.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import (matches test_lint_skuel.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "health"))

import duplicate_headings as dh  # type: ignore[import-not-found]

# ============================================================================
# THE SCOPING RULE — same text is not enough; it must share level AND parent
# ============================================================================


def test_repeat_under_same_parent_is_a_duplicate() -> None:
    """THE live shape: a superseded section outliving its replacement (#1153)."""
    content = "# Doc\n\n## PR-5 — ride-along\n\nold\n\n## PR-5 — close the record\n\nnew\n"
    # Same heading text is required for a match; these differ, so nothing fires.
    assert dh.find_duplicates(content) == []

    exact = "# Doc\n\n## PR-5\n\nold\n\n## PR-5\n\nnew\n"
    found = dh.find_duplicates(exact)
    assert len(found) == 1
    text, first, dup, parents = found[0]
    assert (text, first, dup) == ("PR-5", 3, 7)
    assert parents == ("Doc",)


def test_same_text_under_different_parents_is_legitimate() -> None:
    """``### Tests`` under each PR section is good structure, not a defect.

    This is the 134-hit difference between the naive rule and the shipped one.
    """
    content = "# Doc\n\n## PR-1\n\n### Tests\n\na\n\n## PR-2\n\n### Tests\n\nb\n"
    assert dh.find_duplicates(content) == []


def test_same_text_at_different_levels_is_not_a_duplicate() -> None:
    """A section and a subsection may share a name — they are different scopes."""
    content = "# Doc\n\n## Overview\n\n### Overview\n\ndetail\n"
    assert dh.find_duplicates(content) == []


def test_sibling_repeat_deeper_in_the_tree_is_caught() -> None:
    """The rule is not top-level-only — it applies at every depth."""
    content = "# D\n\n## A\n\n### Tests\n\nx\n\n### Tests\n\ny\n"
    found = dh.find_duplicates(content)
    assert len(found) == 1
    assert found[0][0] == "Tests"
    assert found[0][3] == ("D", "A")


def test_case_differences_still_count_as_duplicates() -> None:
    """``## Next`` and ``## next`` are one section in two spellings.

    Anchor links cannot tell them apart either, so neither does the guard.
    """
    content = "# D\n\n## Next\n\na\n\n## next\n\nb\n"
    assert len(dh.find_duplicates(content)) == 1


def test_a_reopened_parent_scope_does_not_leak() -> None:
    """Popping the heading path must restore the OUTER scope, not clear it.

    ``## A / ### x`` then ``## B / ### x`` is legitimate; but a second ``## A``
    afterwards is a duplicate of the first. Both facts come from the same pop logic.
    """
    content = "# D\n\n## A\n\n### x\n\n## B\n\n### x\n\n## A\n\n"
    found = dh.find_duplicates(content)
    assert [f[0] for f in found] == ["A"]


# ============================================================================
# NARROWINGS — each pinned because "fixing" it reintroduces a false positive
# ============================================================================


def test_setext_headings_are_ignored() -> None:
    """The unfilled-ADR-template shape: ``**Pros:**`` over an empty ``-`` bullet.

    CommonMark makes that an ``<h2>``. Six exist in the tree; none is an authored
    section, and reporting them would red the gate for a template artifact.
    """
    content = "# D\n\n**Pros:**\n- \n\n**Pros:**\n- \n"
    assert dh.extract_headings(content) == [(1, 1, "D")]
    assert dh.find_duplicates(content) == []


def test_blockquoted_headings_are_ignored() -> None:
    """Quoted material is someone else's outline, not this document's."""
    content = "# D\n\n> ## Quoted\n\n> ## Quoted\n"
    assert dh.extract_headings(content) == [(1, 1, "D")]
    assert dh.find_duplicates(content) == []


def test_list_nested_headings_are_not_ignored() -> None:
    """Only QUOTED headings are out of scope — list-nested ones are this doc's own.

    The parser raises ``level`` for every container, so a ``token.level > 0`` test
    discards list-nested headings too. Two ``## Setup`` subsections inside one numbered
    procedure are a real duplicate. Zero such headings exist in the corpus today, which
    is precisely why the cheap test looked equivalent (Codex, #1154).
    """
    content = "# D\n\n1. Step one\n\n   ## Setup\n\n   a\n\n2. Step two\n\n   ## Setup\n\n   b\n"
    assert [h[2] for h in dh.extract_headings(content)] == ["D", "Setup", "Setup"]
    assert len(dh.find_duplicates(content)) == 1


def test_a_quoted_heading_does_not_suppress_later_real_ones() -> None:
    """Depth must come back DOWN — a close that never decrements blinds the rest."""
    content = "# D\n\n> ## Quoted\n\n## Real\n\na\n\n## Real\n\nb\n"
    assert len(dh.find_duplicates(content)) == 1


def test_headings_inside_code_fences_are_ignored() -> None:
    """A ``## sample`` in a fenced block is content, not structure.

    Free from the CommonMark parser — pinned so a future regex rewrite cannot
    silently lose it.
    """
    content = "# D\n\n```markdown\n## PR-5\n## PR-5\n```\n\ntext\n"
    assert dh.extract_headings(content) == [(1, 1, "D")]
    assert dh.find_duplicates(content) == []


def test_trailing_atx_closers_do_not_change_the_text() -> None:
    """``## Title ##`` is the same heading as ``## Title``."""
    content = "# D\n\n## Title\n\na\n\n## Title ##\n\nb\n"
    assert len(dh.find_duplicates(content)) == 1


# ============================================================================
# COMPARISON TEXT — what a reader sees, not what the source says
# ============================================================================


def test_inline_markup_does_not_hide_a_duplicate() -> None:
    """``## Setup`` and ``## **Setup**`` are the same section wearing two costumes.

    THE realistic shape: a replacement reformats its title and the superseded section
    survives underneath. Comparing ``inline.content`` (raw source) would miss it. It is
    also an anchor collision — GitHub renders both to ``#setup``.
    """
    content = "# D\n\n## Setup\n\nold\n\n## **Setup**\n\nnew\n"
    found = dh.find_duplicates(content)
    assert len(found) == 1
    assert found[0][0] == "Setup", "the REPORTED text is the rendered form"


def test_a_linked_heading_matches_its_plain_twin() -> None:
    content = "# D\n\n## [Setup](http://x)\n\na\n\n## Setup\n\nb\n"
    assert len(dh.find_duplicates(content)) == 1


def test_code_span_matches_its_plain_twin() -> None:
    """``## `foo()` `` and ``## foo()`` also share the anchor ``#foo``."""
    content = "# D\n\n## `foo()`\n\na\n\n## foo()\n\nb\n"
    assert len(dh.find_duplicates(content)) == 1


def test_distinct_image_headings_are_not_duplicates() -> None:
    """THE false-positive shape: an ``image`` child's ``content`` IS its alt text.

    Omitting it collapsed ``## ![Alpha](a.png)`` and ``## ![Beta](b.png)`` to two empty
    strings, reported as a duplicate — reddening `./dev health` and the weekly janitor
    on a valid document. A false positive in an always-on gate is the one failure this
    scanner's design says it must not have (Codex, #1154).
    """
    content = "# D\n\n## ![Alpha](a.png)\n\na\n\n## ![Beta](b.png)\n\nb\n"
    assert [h[2] for h in dh.extract_headings(content)] == ["D", "Alpha", "Beta"]
    assert dh.find_duplicates(content) == []


def test_images_sharing_alt_text_are_still_duplicates() -> None:
    """Alt text is the displayed text, so equal alts are equal headings."""
    content = "# D\n\n## ![Same](a.png)\n\na\n\n## ![Same](b.png)\n\nb\n"
    assert len(dh.find_duplicates(content)) == 1


def test_headings_that_render_to_nothing_never_match() -> None:
    """The generalising guard behind the image fix.

    Any inline token type the walker does not know collapses to "", so without this
    every unknown type is a latent FALSE POSITIVE rather than a miss. Two alt-less
    images are not "the same section" in any sense worth reporting.

    Note the contract: extraction KEEPS them (they occupy the outline), matching skips
    them — see the sibling test below for why the first half matters.
    """
    content = "# D\n\n## ![](a.png)\n\na\n\n## ![](b.png)\n\nb\n"
    assert [h[2] for h in dh.extract_headings(content)] == ["D", "", ""]
    assert dh.find_duplicates(content) == []


def test_empty_headings_still_scope_their_children() -> None:
    """A guard against a false positive must not CREATE one.

    Dropping empty headings from the outline re-parents their children onto the nearest
    non-empty ancestor, so two `#### Setup` subsections under two different image
    headings collapse into one scope and get reported. Each empty heading therefore
    occupies the path under a key unique to its own line (Codex, #1154).
    """
    content = "# D\n\n### ![](one.png)\n\n#### Setup\n\na\n\n### ![](two.png)\n\n#### Setup\n\nb\n"
    assert dh.find_duplicates(content) == []

    # ...and a REAL duplicate under one empty parent is still caught.
    same_parent = "# D\n\n### ![](one.png)\n\n#### Setup\n\na\n\n#### Setup\n\nb\n"
    found = dh.find_duplicates(same_parent)
    assert len(found) == 1
    assert found[0][3] == ("D", "(untitled)"), "an empty parent displays as (untitled)"


def test_internal_whitespace_is_collapsed() -> None:
    """`## Quick Start` and `## Quick  Start` render identically and share an anchor.

    HTML collapses whitespace runs, so raw-source comparison missed the duplicate.
    """
    content = "# D\n\n## Quick Start\n\na\n\n## Quick  Start\n\nb\n"
    assert len(dh.find_duplicates(content)) == 1
    assert dh.extract_headings(content)[2][2] == "Quick Start", "reported text is normalised"


def test_rendered_text_strips_markup_but_keeps_content() -> None:
    content = "# D\n\n## **Bold** and `code`\n"
    assert dh.extract_headings(content)[1] == (3, 2, "Bold and code")


# ============================================================================
# SCOPE — the freeform carve-out must stay visible, not silent
# ============================================================================


def test_freeform_dirs_are_excluded_from_the_scan() -> None:
    """``docs/design-principles/`` holds pasted transcripts, not authored structure.

    The exclusion is by SCOPE and is reported in the run output; this pins that the
    directory is actually skipped rather than merely intended to be.
    """
    scanned, skipped = dh.get_md_files()
    assert skipped > 0, "the freeform tier should contain files"
    assert not any(dh._is_freeform(p) for p in scanned)


def test_the_authored_corpus_is_clean() -> None:
    """The gate's own promise: zero duplicates in docs/ and .claude/skills/.

    Earned by fixing all three findings (a stale ``EventHandlerService`` catalog entry,
    a mislabelled ``Quick Start`` stub, a mislabelled ``Implementation`` block), not by
    widening the carve-out.
    """
    scanned, _ = dh.get_md_files()
    offenders = [(f, dups) for f in scanned if (dups := dh.check_file(f))]
    assert offenders == []
