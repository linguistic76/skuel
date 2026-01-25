#!/usr/bin/env python3
"""
Script to add type annotations across Activity domain UI files.

Usage: python add_type_annotations.py <file_path>
Example: python add_type_annotations.py goals_ui.py
"""

import re
import sys
from pathlib import Path


def add_type_protocols(content: str) -> tuple[str, dict]:
    """
    Add Protocol type definitions to the file.

    Returns:
        Tuple of (modified_content, stats_dict)
    """

    # Check if Protocol already imported
    if "from typing import" in content and "Protocol" in content:
        # Already has Protocol, skip
        return content, {"already_added": True, "protocols_added": 0}

    # Add Protocol to imports
    typing_import_pattern = r"from typing import ([^\n]+)"
    match = re.search(typing_import_pattern, content)

    if match:
        # Add Protocol to existing typing import
        current_imports = match.group(1)
        if "Protocol" not in current_imports:
            new_imports = current_imports.rstrip() + ", Protocol"
            content = content.replace(match.group(0), f"from typing import {new_imports}")
    else:
        # Add new typing import with Protocol
        import_section_pattern = r"(from typing import Any\n)"
        content = re.sub(import_section_pattern, r"\1from typing import Protocol\n", content)

    # Protocol definitions
    protocol_code = '''

# ========================================================================
# TYPE PROTOCOLS
# ========================================================================


class RouteDecorator(Protocol):
    """Protocol for FastHTML route decorator."""

    def __call__(self, path: str, methods: list[str] | None = None) -> Any:
        ...


class Request(Protocol):
    """Protocol for Starlette Request (lightweight)."""

    query_params: dict[str, str]

    async def form(self) -> dict[str, Any]:
        ...

'''

    # Find the logger line and insert after it
    logger_pattern = r"(logger = get_logger\([^\)]+\)\n)"
    match = re.search(logger_pattern, content)

    if not match:
        return content, {"error": "Could not find logger definition"}

    insert_pos = match.end()
    modified_content = content[:insert_pos] + protocol_code + content[insert_pos:]

    # Update function signature if it exists
    create_routes_pattern = r"def create_(\w+)_ui_routes\(_app, rt, (\w+)_service:"
    match = re.search(create_routes_pattern, modified_content)

    if match:
        domain = match.group(1)
        service_name = match.group(2)

        old_sig = match.group(0)
        new_sig = f"""def create_{domain}_ui_routes(
    _app: Any,
    rt: RouteDecorator,
    {service_name}_service:"""

        modified_content = modified_content.replace(old_sig, new_sig)

        # Also add return type
        # Find the closing of the signature and add -> list:
        sig_end_pattern = rf"(def create_{domain}_ui_routes\([^)]+\)[^:]*)(:|$)"
        modified_content = re.sub(sig_end_pattern, r"\1 -> list:", modified_content, count=1)

    return modified_content, {"protocols_added": 2, "signature_updated": bool(match)}


def main():
    if len(sys.argv) < 2:
        print("Usage: python add_type_annotations.py <file_path>")
        print("Example: python add_type_annotations.py goals_ui.py")
        sys.exit(1)

    file_path = sys.argv[1]

    print(f"Processing {file_path}...")

    # Read file
    with Path(file_path).open() as f:
        content = f.read()

    # Apply transformation
    modified_content, stats = add_type_protocols(content)

    if "error" in stats:
        print(f"❌ Error: {stats['error']}")
        sys.exit(1)

    if stats.get("already_added"):
        print("⚠️  Protocol types already present, skipping")
        return

    # Write back
    with Path(file_path).open("w") as f:
        f.write(modified_content)

    print(f"✅ Success: Added {stats['protocols_added']} Protocol definitions")
    if stats.get("signature_updated"):
        print("   ✓ Updated function signature")
    print("   ⚠️  TODO: Add Request type to parse_filters() and other helpers")


if __name__ == "__main__":
    main()
