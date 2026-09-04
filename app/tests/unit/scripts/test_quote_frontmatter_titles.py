"""Pin ``scripts/quote_frontmatter_titles.py``'s one transform and its refusals.

The script's claim is "the ``title:`` line was the ONLY reason this block failed
YAML, and quoting it changes nothing else". Each test below is a way that claim can
be quietly false: a second defect masked by the quoting, a comment folded into the
title, an offset taken into the parsed block instead of the file's own lines.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import quote_frontmatter_titles as fixer  # type: ignore[import-not-found]

from core.utils.frontmatter import split_frontmatter

BROKEN = "---\ntitle: ADR-013: KU UID Flat Identity\nupdated: 2026-08-14\nstatus: accepted\n---\n\nbody: text\n"


def test_quotes_the_title_and_touches_nothing_else() -> None:
    after, scalar, line = fixer.quote_title(BROKEN)
    assert scalar == "ADR-013: KU UID Flat Identity"
    assert line == 'title: "ADR-013: KU UID Flat Identity"'
    assert after == BROKEN.replace("title: ADR-013: KU UID Flat Identity", line)
    raw, body = split_frontmatter(after)
    assert yaml.safe_load(raw) == {
        "title": scalar,
        "updated": date(2026, 8, 14),
        "status": "accepted",
    }
    # The closing fence grammar (`\n---\s*`) swallows the blank line after it.
    assert body == "body: text\n"


def test_escapes_an_embedded_double_quote_and_backslash() -> None:
    content = '---\ntitle: ADR-9: the "x" \\ case\n---\n'
    after, scalar, _line = fixer.quote_title(content)
    assert (
        yaml.safe_load(split_frontmatter(after)[0])["title"] == scalar == 'ADR-9: the "x" \\ case'
    )


def test_keeps_non_ascii_literal() -> None:
    content = "---\ntitle: ADR-42: privacy — first-class\n---\n"
    after, _scalar, line = fixer.quote_title(content)
    assert line == 'title: "ADR-42: privacy — first-class"'
    assert yaml.safe_load(split_frontmatter(after)[0])["title"] == "ADR-42: privacy — first-class"


def test_preserves_a_crlf_line_ending() -> None:
    content = "---\r\ntitle: A: B\r\nupdated: 2026-01-01\r\n---\r\n"
    after, _scalar, line = fixer.quote_title(content)
    assert line == 'title: "A: B"\r'
    assert after == content.replace("title: A: B\r", line)


def test_indexes_the_file_lines_not_the_parsed_block() -> None:
    """``split_frontmatter``'s opening fence swallows a blank line after ``---``, so
    the raw block starts on file line 2; an offset-from-raw edit would rewrite the
    wrong line (the trap ``docs_updated_field.find_updated`` documents)."""
    content = "---\n\ntitle: A: B\nupdated: 2026-01-01\n---\n"
    after, _scalar, _line = fixer.quote_title(content)
    assert after.split("\n")[2] == 'title: "A: B"'
    assert after.split("\n")[3] == "updated: 2026-01-01"


def test_refuses_a_block_that_already_parses() -> None:
    with pytest.raises(fixer.PremiseError, match="already parses"):
        fixer.quote_title('---\ntitle: "A: B"\n---\n')


def test_refuses_a_second_defect_masked_by_the_title() -> None:
    """Quoting the title must not be mistaken for a fix when another line is
    also broken — the block still fails, so the doc is refused, not half-fixed."""
    content = "---\ntitle: A: B\nsummary: C: D\n---\n"
    with pytest.raises(fixer.PremiseError, match="second defect"):
        fixer.quote_title(content)


def test_refuses_a_comment_in_the_scalar() -> None:
    """``title: A: B # note`` — YAML reads `# note` as a comment; quoting would
    fold it into the title and the round trip would not notice."""
    with pytest.raises(fixer.PremiseError, match="`#`"):
        fixer.quote_title("---\ntitle: A: B # note\n---\n")


def test_refuses_an_already_quoted_title_when_the_failure_is_elsewhere() -> None:
    with pytest.raises(fixer.PremiseError, match="already quoted"):
        fixer.quote_title('---\ntitle: "A: B"\nsummary: C: D\n---\n')


def test_refuses_two_title_lines() -> None:
    with pytest.raises(fixer.PremiseError, match="2 column-0"):
        fixer.quote_title("---\ntitle: A: B\ntitle: C: D\n---\n")


def test_block_parses_treats_no_frontmatter_as_fine() -> None:
    assert fixer.block_parses("# Just a heading\n")
    assert not fixer.block_parses(BROKEN)
