"""
Ingestion Parser - File Parsing Logic
======================================

Handles parsing of both Markdown and YAML files.
Pure parsing logic, independent of ingestion orchestration.

Extracted from unified_ingestion_service.py for separation of concerns.
"""

from pathlib import Path
from typing import Any

import yaml

from core.utils.exception_types import FILE_IO_EXCEPTIONS
from core.utils.frontmatter import split_frontmatter
from core.utils.result_simplified import Errors, Result

from .config import DEFAULT_MAX_FILE_SIZE_BYTES

# split_frontmatter captures the text AFTER the opening `---` line, so a YAML
# error's line number is one short of the line the author sees in the file.
_FRONTMATTER_LINE_OFFSET = 1


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def check_file_size(
    file_path: Path,
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
) -> Result[None]:
    """
    Check if file size is within limits.

    Prevents OOM by rejecting files larger than max_file_size_bytes.

    Args:
        file_path: Path to file to check
        max_file_size_bytes: Maximum allowed file size

    Returns:
        Result[None] - Ok if within limits, Fail if too large
    """
    try:
        file_size = file_path.stat().st_size
        if file_size > max_file_size_bytes:
            actual_size = format_file_size(file_size)
            max_size = format_file_size(max_file_size_bytes)
            return Result.fail(
                Errors.validation(
                    f"File too large: {actual_size} exceeds limit of {max_size}",
                    field="file_size",
                    user_message=(
                        f"File {file_path.name} is too large ({actual_size}). "
                        f"Maximum allowed size is {max_size}. "
                        f"Consider splitting the content into smaller files."
                    ),
                )
            )
        return Result.ok(None)
    except OSError as e:
        return Result.fail(
            Errors.system(
                f"Cannot check file size: {e}",
                operation="check_file_size",
                details={"path": str(file_path)},
            )
        )


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


def _yaml_error_location(error: yaml.YAMLError, line_offset: int = 0) -> str:
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


def parse_markdown(
    file_path: Path,
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
) -> Result[tuple[dict[str, Any], str]]:
    """
    Parse markdown file into frontmatter dict and body content.

    A file with no ``---`` fence is a loose note: it parses to empty
    frontmatter and succeeds. A fence that is present but does not parse is
    an authoring error, not an absent one, and fails with a VALIDATION
    Result carrying the line/column — the same shape :func:`parse_yaml`
    returns, so both doors report a broken document the same way.

    Args:
        file_path: Path to markdown file
        max_file_size_bytes: Maximum allowed file size

    Returns:
        Result with tuple of (frontmatter_dict, body_content)
    """
    try:
        # Check file size before reading to prevent OOM
        size_check = check_file_size(file_path, max_file_size_bytes)
        if size_check.is_error:
            return Result.fail(size_check)

        content = file_path.read_text(encoding="utf-8")

        raw_yaml, body = split_frontmatter(content)
        if raw_yaml is not None:
            try:
                frontmatter = yaml.safe_load(raw_yaml) or {}
            except yaml.YAMLError as e:
                # An authored ``---`` fence is a statement of intent, so a fence
                # that does not parse is a broken statement — not the absence of
                # one. Returning empty frontmatter here made an authoring error
                # indistinguishable from a deliberate untyped note: the gate set
                # the file aside as "no 'type:' field", its entity went stale
                # unreported, and a rename then deleted that entity for an
                # unclaimed uid. Same VALIDATION shape parse_yaml returns, which
                # is what files it under the ``parsing`` stage batch.py already
                # documents. A file with NO fence stays a loose note.
                location = _yaml_error_location(e, line_offset=_FRONTMATTER_LINE_OFFSET)
                return Result.fail(
                    Errors.validation(
                        f"Invalid YAML frontmatter{location}: {e}",
                        field="yaml_syntax",
                        user_message=(
                            f"File {file_path.name} has a frontmatter syntax error{location}"
                        ),
                    )
                )
        else:
            frontmatter = {}

        return Result.ok((frontmatter, body))

    except FILE_IO_EXCEPTIONS as e:
        return Result.fail(
            Errors.system(
                f"Failed to parse markdown: {e}",
                operation="parse_markdown",
                details={"path": str(file_path)},
            )
        )


def parse_yaml(
    file_path: Path,
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
) -> Result[dict[str, Any]]:
    """
    Parse YAML file into dictionary.

    Args:
        file_path: Path to YAML file
        max_file_size_bytes: Maximum allowed file size

    Returns:
        Result with parsed dictionary
    """
    try:
        # Check file size before reading to prevent OOM
        size_check = check_file_size(file_path, max_file_size_bytes)
        if size_check.is_error:
            return Result.fail(size_check)

        content = file_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)

        if not data:
            return Result.fail(
                Errors.validation(
                    "YAML file is empty",
                    field="content",
                    user_message=f"File {file_path.name} contains no data",
                )
            )

        return Result.ok(data)

    except yaml.YAMLError as e:
        location_info = _yaml_error_location(e)
        error_msg = f"Invalid YAML syntax{location_info}: {e}"
        return Result.fail(
            Errors.validation(
                error_msg,
                field="yaml_syntax",
                user_message=f"File {file_path.name} has YAML syntax error{location_info}",
            )
        )
    except FILE_IO_EXCEPTIONS as e:
        return Result.fail(
            Errors.system(
                f"Failed to parse YAML: {e}",
                operation="parse_yaml",
                details={"path": str(file_path)},
            )
        )


__all__ = [
    "check_file_size",
    "extract_yaml_error_location",
    "format_file_size",
    "parse_markdown",
    "parse_yaml",
]
