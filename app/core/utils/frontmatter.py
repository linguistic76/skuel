"""
Frontmatter Parser - Shared YAML frontmatter extraction for Markdown files.

Provides two levels of parsing:
- split_frontmatter: Returns raw YAML text + body (for scripts that modify frontmatter text)
- parse_frontmatter: Returns parsed dict + body (the common case)

Authoring a ``---`` fence is a statement of intent, so the two failure shapes
are NOT the same: a file with no fence is a plain note and parses to empty
frontmatter, while a fence whose YAML does not parse is a broken statement and
fails with a VALIDATION Result carrying the author's line/column. Collapsing
the second into the first made a broken file indistinguishable from a
deliberate one and let callers report a misleading reason for it.

Used by ingestion parser, hierarchy parser, and ~12 scripts.
"""

import re
from typing import Any

import yaml

from core.utils.result_simplified import Errors, Result

# Matches YAML frontmatter block: --- (optional whitespace) \n content \n --- (optional whitespace)
# terminated by a newline OR end-of-file (frontmatter-only files, e.g. approval
# report files with no body, end right at the closing fence).
_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)

# The pattern captures the text AFTER the opening `---` line, so a YAML error's
# line number is one short of the line the author sees in the file.
FRONTMATTER_LINE_OFFSET = 1


def extract_yaml_error_location(error: yaml.YAMLError) -> tuple[int | None, int | None]:
    """
    Extract line and column numbers from a YAML error.

    Args:
        error: YAML parsing error

    Returns:
        Tuple of (line_number, column) or (None, None)
    """
    problem_mark = getattr(error, "problem_mark", None)
    if problem_mark is not None:
        mark = problem_mark
        # YAML uses 0-based indexing, convert to 1-based for display
        return (mark.line + 1, mark.column + 1)
    return (None, None)


def yaml_error_location(error: yaml.YAMLError, line_offset: int = 0) -> str:
    """Render a YAML error's position as ``" at line N, column M"``, else ``""``.

    ``line_offset`` shifts the line into the enclosing FILE's numbering: YAML
    sees only the text handed to it, so a frontmatter error's line 5 is the
    file's line 6 once the opening ``---`` fence is counted. An author who is
    sent to the wrong line has to find the fault themselves, which is most of
    the work this message exists to save.
    """
    line_num, col = extract_yaml_error_location(error)
    if line_num is None:
        return ""
    line_num += line_offset
    if col is None:
        return f" at line {line_num}"
    return f" at line {line_num}, column {col}"


def split_frontmatter(content: str) -> tuple[str | None, str]:
    """
    Split markdown content into raw YAML frontmatter text and body.

    Returns (raw_yaml_text, body). Returns (None, content) if no frontmatter found.
    Useful when you need to manipulate the raw frontmatter string.
    """
    match = _FRONTMATTER_PATTERN.match(content)
    if match:
        return match.group(1), content[match.end() :]
    return None, content


def parse_frontmatter(content: str) -> Result[tuple[dict[str, Any], str]]:
    """
    Parse markdown content into frontmatter dict and body.

    No fence → ok with ``({}, content)``: a plain note, which is a legitimate
    thing to be. A fence that does not parse → VALIDATION failure carrying the
    author's line/column, because a broken opt-in is not an absent one.
    """
    raw, body = split_frontmatter(content)
    if raw is None:
        return Result.ok(({}, content))

    try:
        frontmatter = yaml.safe_load(raw) or {}
    except yaml.YAMLError as e:
        location = yaml_error_location(e, line_offset=FRONTMATTER_LINE_OFFSET)
        return Result.fail(
            Errors.validation(
                f"Invalid YAML frontmatter{location}: {e}",
                field="yaml_syntax",
                user_message=f"Frontmatter has a syntax error{location}",
            )
        )

    return Result.ok((frontmatter, body))


__all__ = [
    "FRONTMATTER_LINE_OFFSET",
    "extract_yaml_error_location",
    "parse_frontmatter",
    "split_frontmatter",
    "yaml_error_location",
]
