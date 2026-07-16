"""
Frontmatter Parser - Shared YAML frontmatter extraction for Markdown files.

Provides two levels of parsing:
- split_frontmatter: Returns raw YAML text + body (for scripts that modify frontmatter text)
- parse_frontmatter: Returns parsed dict + body (the common case)

Used by ingestion parser, hierarchy parser, and ~12 scripts.
"""

import re
from typing import Any

import yaml

# Matches YAML frontmatter block: --- (optional whitespace) \n content \n --- (optional whitespace)
# terminated by a newline OR end-of-file (frontmatter-only files, e.g. approval
# report files with no body, end right at the closing fence).
_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)


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


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """
    Parse markdown content into frontmatter dict and body.

    Returns (frontmatter_dict, body). Returns ({}, content) if no frontmatter
    or on YAML parse error.
    """
    raw, body = split_frontmatter(content)
    if raw is None:
        return {}, content

    try:
        frontmatter = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        return {}, content

    return frontmatter, body


def parse_frontmatter_bytes(content: bytes) -> dict[str, Any]:
    """Parse YAML frontmatter from raw bytes.

    Decodes bytes to text (replacing errors) then delegates to parse_frontmatter.
    Returns empty dict on malformed/missing frontmatter.
    """
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:  # safety-net: malformed bytes should not crash upload
        return {}
    frontmatter, _ = parse_frontmatter(text)
    return frontmatter


__all__ = [
    "parse_frontmatter",
    "parse_frontmatter_bytes",
    "split_frontmatter",
]
