"""Pin the shared fence walker in ``scripts/health/markdown_fences.py``.

Why this file exists
--------------------
``scripts/health/`` held two fence parsers. ``dead_doc_links`` used a CommonMark
parser; ``stale_names.extract_code_segments`` used a hand-written scanner whose closing
test was ``stripped.startswith(fence_char)`` with ``fence_char = stripped[:3]``. That
test takes ANY line opening with three delimiter characters as a closer, including an
inner fence that carries an info string.

That is not a hypothetical. Six lines across four live documents sit inside a fence and
open with ``` — e.g. ``docs/guides/VOICE_JOURNALING_AND_OBSIDIAN_GUIDE.md:199`` is a
```` ```markwhen ```` sample inside a ```` ```markdown ```` block. The old scanner closed
on each one and then had its fence state INVERTED for the remainder of the document:
code read as prose, prose read as code. 153 lines of prose were scanned as code in three
documents, and every block's real last line was never scanned at all.

The cases below are therefore split into two kinds, and both matter:

  * the *shape* cases — one per way a closer can be faked, several absent from the tree
    today and latent until someone writes one;
  * the *projection* invariant — ``iter_code_fence_lines`` must stay a pure flattening
    of ``iter_code_fence_blocks``, because the moment they diverge there are two parsers
    again, which is the defect this module exists to delete.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import (matches test_lint_skuel.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "health"))

import markdown_fences as mf  # type: ignore[import-not-found]

# ============================================================================
# A CLOSER MUST MATCH: same char, at least as long, no info string
# ============================================================================


def test_inner_fence_with_info_string_does_not_close_an_equal_length_fence() -> None:
    """THE live shape: 6 occurrences across 4 documents.

    A ```` ```python ```` line inside a ```` ``` ```` block is an inner opener, not a
    closer — a closing delimiter carries nothing but whitespace after the run. The old
    scanner closed here and inverted its fence state for the rest of the file.
    """
    content = "```markdown\nSTART\n```markwhen\nx = 1\n```\nafter\n"
    walked = [line for _n, _lang, line in mf.iter_code_fence_lines(content)]
    assert walked == ["START", "```markwhen", "x = 1"]
    # The old scanner closed at line 3, so `x = 1` fell OUT of the block and `after`
    # fell IN — the fence state inverted from that point on.
    assert "after" not in walked


def test_inner_fence_does_not_close_an_outer_wrapper() -> None:
    """The reported repro: a ```` ````markdown ```` wrapper holding a ```` ```bash ````
    sample stays open. A shorter run cannot close a longer one."""
    content = "````markdown\n```bash\ncp a.py b.py\n```\nSTILL_INSIDE\n````\nafter\n"
    walked = [line for _n, _lang, line in mf.iter_code_fence_lines(content)]
    assert walked == ["```bash", "cp a.py b.py", "```", "STILL_INSIDE"]
    assert "after" not in walked


def test_other_delimiter_character_does_not_close() -> None:
    """``~~~`` cannot close a ``` fence, and vice versa."""
    walked = [text for _n, _lang, text in mf.iter_code_fence_lines("```\na\n~~~\nb\n```\nafter\n")]
    assert walked == ["a", "~~~", "b"]


def test_longer_run_may_close_a_shorter_fence() -> None:
    """At least as long — not exactly as long. A 4-tick closer ends a 3-tick fence."""
    walked = [text for _n, _lang, text in mf.iter_code_fence_lines("```\na\n````\nafter\n")]
    assert walked == ["a"]


# ============================================================================
# CONTAINERS AND UNCLOSED FENCES
# ============================================================================


def test_blockquoted_fence_is_walked_and_stripped() -> None:
    """A quoted example is still an example; the `> ` marker is not content.

    One lives at `docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md:318`.
    """
    assert mf.iter_code_fence_lines("> ```python\n> x = 1\n> ```\nafter\n") == [
        (2, "python", "x = 1")
    ]


def test_unquoted_fence_keeps_a_leading_redirect() -> None:
    """The quote strip is scoped to fences opened inside a quote — a shell redirect at
    the start of an unquoted fence line keeps its `>`."""
    assert mf.iter_code_fence_lines("```bash\n> out.txt\n```\n") == [(2, "bash", "> out.txt")]


def test_unclosed_fence_keeps_its_last_line() -> None:
    """An unclosed fence has no closing delimiter to skip, so its final line is content.

    Treating the last line as a closer unconditionally drops it from the scan; a live
    unclosed fence ends `docs/architecture/SERVICE_TOPOLOGY.md`.
    """
    walked = [text for _n, _lang, text in mf.iter_code_fence_lines("```\na\nb\n")]
    assert walked == ["a", "b"]


def test_indented_delimiter_is_not_a_fence() -> None:
    """Four-space-indented ``` is an indented code block under CommonMark, not a fence.
    Opening it as one reports the following prose as code."""
    assert mf.iter_code_fence_lines("    ```\n    a\n    ```\nprose\n") == []


# ============================================================================
# BLOCK CONTRACT: span covers delimiters, lines do not
# ============================================================================


def test_span_covers_delimiters_and_lines_does_not() -> None:
    """The two coordinate rules `stale_names` depends on.

    Keying a block by its opening delimiter reported every fenced hit one line early —
    47 of 121 findings on the live tree. Scanning a delimiter as prose would read an
    info string as an inline span.
    """
    (block,) = mf.iter_code_fence_blocks("intro\n```python\nx = 1\ny = 2\n```\nafter\n")
    assert block.span == (2, 5)
    assert block.lines == ((3, "x = 1"), (4, "y = 2"))
    assert block.lang == "python"


def test_empty_fence_has_a_span_but_no_lines() -> None:
    """An empty block still claims its span, so its delimiters stay out of the prose pass."""
    (block,) = mf.iter_code_fence_blocks("```\n```\n")
    assert block.lines == ()
    assert block.span == (1, 2)


def test_language_tag_is_first_word_lowercased() -> None:
    (block,) = mf.iter_code_fence_blocks("```Python title=x\nx = 1\n```\n")
    assert block.lang == "python"


# ============================================================================
# THE PROJECTION INVARIANT — one walker, two shapes
# ============================================================================


def test_lines_is_exactly_the_flattening_of_blocks() -> None:
    """`iter_code_fence_lines` must stay a projection of `iter_code_fence_blocks`.

    If these can disagree there are two parsers again, and the whole point of this
    module is that there is one. Exercised over every shape above at once.
    """
    content = (
        "prose\n````markdown\n```bash\ncp a.py b.py\n```\n````\n"
        "> ```python\n> q = 1\n> ```\n"
        "```\nunclosed tail\n"
    )
    expected = sorted(
        (lineno, block.lang, text)
        for block in mf.iter_code_fence_blocks(content)
        for lineno, text in block.lines
    )
    assert mf.iter_code_fence_lines(content) == expected
    assert expected, "corpus for the invariant is empty — the check would be vacuous"
