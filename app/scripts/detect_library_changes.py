#!/usr/bin/env python3
"""
Library Change Detection Script

Detects PyPI package version changes and suggests which skills may need review.

Usage:
    uv run python scripts/detect_library_changes.py [--from-ref HEAD@{1}]

Called automatically by post-merge hook.

See: @docs-skills-evolution for the Library Upgrade Workflow
"""

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class VersionChange:
    """Represents a version change for a package."""

    package: str
    old_version: str
    new_version: str
    affected_skills: list[str]


def load_skills_metadata(base_path: Path) -> dict[str, Any]:
    """Load skills metadata from YAML."""
    metadata_file = base_path / ".claude" / "skills" / "skills_metadata.yaml"
    with open(metadata_file) as f:
        return yaml.safe_load(f)


def build_package_to_skills_map(skills_data: dict[str, Any]) -> dict[str, list[str]]:
    """
    Build mapping of PyPI package name to skills that use it.

    Returns: {package_name: [skill_names]}
    """
    package_map: dict[str, list[str]] = {}

    for skill in skills_data["skills"]:
        name = skill["name"]
        library_package = skill.get("library_package")

        if library_package:  # Skip null values
            if library_package not in package_map:
                package_map[library_package] = []
            package_map[library_package].append(name)

    return package_map


def parse_uv_lock_packages(lock_file_path: Path) -> dict[str, str]:
    """
    Parse uv.lock to extract package versions.

    Returns: {package_name: version}
    """
    packages: dict[str, str] = {}

    if not lock_file_path.exists():
        return packages

    content = lock_file_path.read_text()

    # Parse [[package]] blocks — same TOML format as poetry.lock:
    # [[package]]
    # name = "pydantic"
    # version = "2.12.5"

    package_blocks = re.findall(
        r'\[\[package\]\]\s+name = "([^"]+)"\s+version = "([^"]+)"', content, re.MULTILINE
    )

    for name, version in package_blocks:
        packages[name] = version

    return packages


def get_git_diff_packages(
    base_path: Path, from_ref: str = "HEAD@{1}"
) -> dict[str, tuple[str, str]]:
    """
    Get package version changes from git diff.

    Args:
        from_ref: Git reference to compare from (default: HEAD@{1} for post-merge)

    Returns: {package_name: (old_version, new_version)}
    """
    try:
        # Check if from_ref exists
        subprocess.run(
            ["git", "rev-parse", "--verify", from_ref],
            cwd=base_path,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        # from_ref doesn't exist (likely first clone)
        return {}

    # Get diff of uv.lock
    try:
        result = subprocess.run(
            ["git", "diff", from_ref, "HEAD", "uv.lock"],
            cwd=base_path,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return {}

    diff_content = result.stdout

    # Parse diff for version changes
    # Look for lines like:
    # -version = "1.3.0"
    # +version = "1.4.0"

    changes: dict[str, tuple[str, str]] = {}

    # Find package name and version changes
    lines = diff_content.split("\n")
    current_package = None

    for i, line in enumerate(lines):
        # Detect package name
        if line.startswith("@@"):
            # Look ahead for [[package]] and name
            for j in range(i + 1, min(i + 10, len(lines))):
                if "[[package]]" in lines[j]:
                    # Find name in next few lines
                    for k in range(j + 1, min(j + 5, len(lines))):
                        name_match = re.match(r'[+-]?name = "([^"]+)"', lines[k])
                        if name_match:
                            current_package = name_match.group(1)
                            break
                    break

        # Detect version changes
        if current_package and line.startswith("-version = "):
            old_version = re.search(r'"([^"]+)"', line)
            # Look for corresponding + line
            if i + 1 < len(lines) and lines[i + 1].startswith("+version = "):
                new_version = re.search(r'"([^"]+)"', lines[i + 1])
                if old_version and new_version:
                    changes[current_package] = (old_version.group(1), new_version.group(1))
                    current_package = None  # Reset

    return changes


def detect_changes(base_path: Path, from_ref: str = "HEAD@{1}") -> list[VersionChange]:
    """
    Detect library version changes and affected skills.

    Returns: List of version changes with affected skills
    """
    skills_data = load_skills_metadata(base_path)
    package_to_skills = build_package_to_skills_map(skills_data)

    # Get package changes from git diff
    package_changes = get_git_diff_packages(base_path, from_ref)

    changes: list[VersionChange] = []

    for package, (old_ver, new_ver) in package_changes.items():
        # Find affected skills
        affected = package_to_skills.get(package, [])

        if affected:  # Only report if skills are affected
            changes.append(
                VersionChange(
                    package=package,
                    old_version=old_ver,
                    new_version=new_ver,
                    affected_skills=affected,
                )
            )

    return changes


def print_report(changes: list[VersionChange]) -> None:
    """Print library change report."""
    if not changes:
        return

    print()
    print("⚠️  Library versions changed. Consider reviewing affected skills:")
    print()

    for change in changes:
        print(f"📦 {change.package}: {change.old_version} → {change.new_version}")
        print("   Skills potentially affected:")
        for skill in change.affected_skills:
            print(f"   - @{skill}")
        print()

        # Try to provide changelog link
        changelog_url = get_changelog_url(change.package)
        if changelog_url:
            print(f"   Changelog: {changelog_url}")
        print()

    print("Workflow: See @docs-skills-evolution 'Library Upgrade Workflow'")
    print()


def get_changelog_url(package: str) -> str | None:
    """Get changelog URL for common packages."""
    changelog_map = {
        "python-fasthtml": "https://github.com/AnswerDotAI/fasthtml/releases",
        "pydantic": "https://github.com/pydantic/pydantic/releases",
        "neo4j": "https://github.com/neo4j/neo4j-python-driver/releases",
        "openai": "https://github.com/openai/openai-python/releases",
        "pytest": "https://github.com/pytest-dev/pytest/releases",
        "prometheus-client": "https://github.com/prometheus/client_python/releases",
    }
    return changelog_map.get(package)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Detect library version changes and suggest skills to review"
    )
    parser.add_argument(
        "--from-ref",
        default="HEAD@{1}",
        help="Git reference to compare from (default: HEAD@{1})",
    )
    args = parser.parse_args()

    base_path = Path(__file__).parent.parent

    changes = detect_changes(base_path, from_ref=args.from_ref)

    if changes:
        print_report(changes)
        # Exit code 0 - this is informational, not an error

    sys.exit(0)


if __name__ == "__main__":
    main()
