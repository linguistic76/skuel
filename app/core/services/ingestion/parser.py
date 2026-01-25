"""
Ingestion Parser - File Parsing Logic
======================================

Handles parsing of both Markdown and YAML files.
Pure parsing logic, independent of ingestion orchestration.

Extracted from unified_ingestion_service.py for separation of concerns.
"""

import re
from pathlib import Path
from typing import Any

import yaml

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

from .config import DEFAULT_MAX_FILE_SIZE_BYTES

logger = get_logger("skuel.services.ingestion.parser")

# Pattern for extracting YAML frontmatter from markdown files
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


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


def parse_markdown(
    file_path: Path,
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
) -> Result[tuple[dict[str, Any], str]]:
    """
    Parse markdown file into frontmatter dict and body content.

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
            return Result.fail(size_check.expect_error())

        content = file_path.read_text(encoding="utf-8")

        match = FRONTMATTER_PATTERN.match(content)
        if match:
            frontmatter_str = match.group(1)
            body = content[match.end() :]
            try:
                frontmatter = yaml.safe_load(frontmatter_str) or {}
            except yaml.YAMLError as e:
                logger.warning(
                    "Failed to parse YAML frontmatter - using empty frontmatter",
                    extra={
                        "file_path": str(file_path),
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    },
                )
                frontmatter = {}
        else:
            frontmatter = {}
            body = content

        return Result.ok((frontmatter, body))

    except Exception as e:
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
            return Result.fail(size_check.expect_error())

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
        # Extract line/column from YAML error for rich error context
        line_num, col = extract_yaml_error_location(e)

        # Build location info for error message
        location_info = ""
        if line_num is not None:
            location_info = f" at line {line_num}"
            if col is not None:
                location_info += f", column {col}"

        error_msg = f"Invalid YAML syntax{location_info}: {e}"
        return Result.fail(
            Errors.validation(
                error_msg,
                field="yaml_syntax",
                user_message=f"File {file_path.name} has YAML syntax error{location_info}",
            )
        )
    except Exception as e:
        return Result.fail(
            Errors.system(
                f"Failed to parse YAML: {e}",
                operation="parse_yaml",
                details={"path": str(file_path)},
            )
        )


__all__ = [
    "FRONTMATTER_PATTERN",
    "check_file_size",
    "extract_yaml_error_location",
    "format_file_size",
    "parse_markdown",
    "parse_yaml",
]
