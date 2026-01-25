#!/usr/bin/env python3
"""
Script to extract god helper functions across Activity domain UI files.

Usage: python refactor_god_helper.py <domain> <file_path>
Example: python refactor_god_helper.py goals goals_ui.py
"""

import re
import sys
from typing import Tuple


def extract_god_helper(content: str, domain: str) -> Tuple[str, dict]:
    """
    Extract the god helper pattern and create pure functions.

    Returns:
        Tuple of (modified_content, stats_dict)
    """

    # Domain-specific configurations
    domain_config = {
        "goals": {
            "entity": "goal",
            "entity_plural": "goals",
            "filters": ["status_filter", "sort_by"],
        },
        "habits": {
            "entity": "habit",
            "entity_plural": "habits",
            "filters": ["category", "status_filter", "sort_by"],
        },
        "events": {
            "entity": "event",
            "entity_plural": "events",
            "filters": ["event_type", "date_filter", "sort_by"],
        },
        "choices": {
            "entity": "choice",
            "entity_plural": "choices",
            "filters": ["status_filter", "sort_by"],
        },
        "principles": {
            "entity": "principle",
            "entity_plural": "principles",
            "filters": ["category", "strength_filter", "sort_by"],
        },
    }

    config = domain_config.get(domain)
    if not config:
        return content, {"error": f"Unknown domain: {domain}"}

    entity = config["entity"]
    entity_plural = config["entity_plural"]

    # Helper functions template
    helper_template = f'''
    # ========================================================================
    # PURE COMPUTATION HELPERS (Testable without mocks)
    # ========================================================================

    def compute_{entity}_stats({entity_plural}: list[Any]) -> dict[str, int]:
        """Calculate {entity} statistics.

        Pure function: testable without database or async.

        Args:
            {entity_plural}: List of {entity} entities

        Returns:
            Stats dict with counts
        """
        # TODO: Implement domain-specific stats
        return {{
            "total": len({entity_plural}),
        }}

    def apply_{entity}_filters(
        {entity_plural}: list[Any],
        **filters,
    ) -> list[Any]:
        """Apply filter criteria to {entity} list.

        Pure function: testable without database or async.

        Args:
            {entity_plural}: List of {entity} entities
            **filters: Filter parameters

        Returns:
            Filtered list of {entity_plural}
        """
        # TODO: Implement domain-specific filters
        return {entity_plural}

    def apply_{entity}_sort({entity_plural}: list[Any], sort_by: str = "created_at") -> list[Any]:
        """Sort {entity_plural} by specified field.

        Pure function: testable without database or async.

        Args:
            {entity_plural}: List of {entity} entities
            sort_by: Sort field

        Returns:
            Sorted list of {entity_plural}
        """
        # TODO: Implement domain-specific sorting
        return {entity_plural}
'''

    # Find the get_filtered_* function
    pattern = rf"async def get_filtered_{entity_plural}\("
    match = re.search(pattern, content)

    if not match:
        return content, {"error": f"Could not find get_filtered_{entity_plural} function"}

    # Insert helpers before the function
    insert_pos = match.start()
    modified_content = content[:insert_pos] + helper_template + "\n" + content[insert_pos:]

    return modified_content, {"domain": domain, "helpers_added": 3, "function_found": True}


def main():
    if len(sys.argv) < 3:
        print("Usage: python refactor_god_helper.py <domain> <file_path>")
        print("Example: python refactor_god_helper.py goals goals_ui.py")
        sys.exit(1)

    domain = sys.argv[1]
    file_path = sys.argv[2]

    print(f"Processing {file_path} for domain '{domain}'...")

    # Read file
    with open(file_path, "r") as f:
        content = f.read()

    # Apply transformation
    modified_content, stats = extract_god_helper(content, domain)

    if "error" in stats:
        print(f"❌ Error: {stats['error']}")
        sys.exit(1)

    # Write back
    with open(file_path, "w") as f:
        f.write(modified_content)

    print(f"✅ Success: Added {stats['helpers_added']} helper functions")
    print(f"   Domain: {stats['domain']}")
    print(f"   ⚠️  TODO: Manually implement the helper logic based on tasks_ui.py patterns")


if __name__ == "__main__":
    main()
