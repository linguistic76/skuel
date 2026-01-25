#!/usr/bin/env python3
"""
Script to add validation functions across Activity domain UI files.

Usage: python add_validation.py <domain> <file_path>
Example: python add_validation.py goals goals_ui.py
"""

import re
import sys
from typing import Tuple


def add_validation_function(content: str, domain: str) -> Tuple[str, dict]:
    """
    Add validate_*_form_data function to the file.

    Returns:
        Tuple of (modified_content, stats_dict)
    """

    # Domain-specific validation rules
    validation_templates = {
        "goals": '''
    def validate_goal_form_data(form_data: dict[str, Any]) -> Result[None]:
        """
        Validate goal form data early.

        Pure function: returns clear error messages for UI.

        Args:
            form_data: Raw form data from request

        Returns:
            Result.ok(None) if valid, Errors.validation() with user-friendly message if invalid
        """
        # Required fields
        title = form_data.get("title", "").strip()
        if not title:
            return Errors.validation("Goal title is required")

        if len(title) > 200:
            return Errors.validation("Goal title must be 200 characters or less")

        # Date validation
        target_date_str = form_data.get("target_date", "")
        if target_date_str:
            try:
                target_date = date.fromisoformat(target_date_str)
                if target_date < date.today():
                    return Errors.validation("Target date must be in the future")
            except ValueError:
                return Errors.validation("Invalid date format")

        return Result.ok(None)
''',
        "habits": '''
    def validate_habit_form_data(form_data: dict[str, Any]) -> Result[None]:
        """
        Validate habit form data early.

        Pure function: returns clear error messages for UI.

        Args:
            form_data: Raw form data from request

        Returns:
            Result.ok(None) if valid, Errors.validation() with user-friendly message if invalid
        """
        # Required fields
        title = form_data.get("title", "").strip()
        if not title:
            return Errors.validation("Habit title is required")

        if len(title) > 200:
            return Errors.validation("Habit title must be 200 characters or less")

        # Frequency validation
        frequency_str = form_data.get("frequency", "")
        if frequency_str:
            try:
                frequency = int(frequency_str)
                if frequency < 1:
                    return Errors.validation("Frequency must be at least 1")
                if frequency > 365:
                    return Errors.validation("Frequency must be 365 or less")
            except ValueError:
                return Errors.validation("Invalid frequency")

        return Result.ok(None)
''',
        "events": '''
    def validate_event_form_data(form_data: dict[str, Any]) -> Result[None]:
        """
        Validate event form data early.

        Pure function: returns clear error messages for UI.

        Args:
            form_data: Raw form data from request

        Returns:
            Result.ok(None) if valid, Errors.validation() with user-friendly message if invalid
        """
        # Required fields
        title = form_data.get("title", "").strip()
        if not title:
            return Errors.validation("Event title is required")

        if len(title) > 200:
            return Errors.validation("Event title must be 200 characters or less")

        # Time validation
        start_time_str = form_data.get("start_time", "")
        end_time_str = form_data.get("end_time", "")

        if start_time_str and end_time_str:
            try:
                from datetime import time
                start = time.fromisoformat(start_time_str)
                end = time.fromisoformat(end_time_str)
                if end <= start:
                    return Errors.validation("End time must be after start time")
            except ValueError:
                return Errors.validation("Invalid time format")

        return Result.ok(None)
''',
        "choices": '''
    def validate_choice_form_data(form_data: dict[str, Any]) -> Result[None]:
        """
        Validate choice form data early.

        Pure function: returns clear error messages for UI.

        Args:
            form_data: Raw form data from request

        Returns:
            Result.ok(None) if valid, Errors.validation() with user-friendly message if invalid
        """
        # Required fields
        title = form_data.get("title", "").strip()
        if not title:
            return Errors.validation("Choice title is required")

        if len(title) > 200:
            return Errors.validation("Choice title must be 200 characters or less")

        return Result.ok(None)
''',
        "principles": '''
    def validate_principle_form_data(form_data: dict[str, Any]) -> Result[None]:
        """
        Validate principle form data early.

        Pure function: returns clear error messages for UI.

        Args:
            form_data: Raw form data from request

        Returns:
            Result.ok(None) if valid, Errors.validation() with user-friendly message if invalid
        """
        # Required fields
        name = form_data.get("name", "").strip()
        if not name:
            return Errors.validation("Principle name is required")

        if len(name) > 200:
            return Errors.validation("Principle name must be 200 characters or less")

        return Result.ok(None)
''',
    }

    template = validation_templates.get(domain)
    if not template:
        return content, {"error": f"Unknown domain: {domain}"}

    # Find PURE COMPUTATION HELPERS section
    pattern = r"# ={70,}\n\s*# PURE COMPUTATION HELPERS"
    match = re.search(pattern, content)

    if not match:
        return content, {"error": "Could not find PURE COMPUTATION HELPERS section"}

    # Insert after the section header
    insert_pos = match.end()
    # Find the next line break
    next_line = content.find("\n", insert_pos)
    insert_pos = next_line + 1

    modified_content = content[:insert_pos] + template + content[insert_pos:]

    return modified_content, {"domain": domain, "function_added": True}


def main():
    if len(sys.argv) < 3:
        print("Usage: python add_validation.py <domain> <file_path>")
        print("Example: python add_validation.py goals goals_ui.py")
        sys.exit(1)

    domain = sys.argv[1]
    file_path = sys.argv[2]

    print(f"Processing {file_path} for domain '{domain}'...")

    # Read file
    with open(file_path, "r") as f:
        content = f.read()

    # Apply transformation
    modified_content, stats = add_validation_function(content, domain)

    if "error" in stats:
        print(f"❌ Error: {stats['error']}")
        sys.exit(1)

    # Write back
    with open(file_path, "w") as f:
        f.write(modified_content)

    print(f"✅ Success: Added validate_{domain}_form_data() function")
    print(f"   ⚠️  TODO: Call validation in create_{domain}_from_form() function")


if __name__ == "__main__":
    main()
