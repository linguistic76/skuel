"""
Version Management System for Skuel0 Codebase
Version: 1.0
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

__version__ = "1.0"


class VersionManager:
    """Manages version numbering across the codebase"""

    VERSION_PATTERN = re.compile(r'__version__\s*=\s*["\']([^"\']+)["\']')
    VERSION_COMMENT_PATTERN = re.compile(r"#\s*Version:\s*(\d+\.\d+(?:\.\d+)?)")

    def __init__(self, root_path: str = ".") -> None:
        self.root_path = Path(root_path)
        self.version_registry: dict[str, str] = {}
        self.version_history_file = self.root_path / ".version_history.json"
        self.load_version_history()

    def load_version_history(self) -> None:
        """Load version history from JSON file"""
        if self.version_history_file.exists():
            with self.version_history_file.open("r") as f:
                self.version_history = json.load(f)
        else:
            self.version_history = {
                "global_version": "1.0",
                "created_at": datetime.now().isoformat(),
                "files": {},
            }

    def save_version_history(self) -> None:
        """Save version history to JSON file"""
        with self.version_history_file.open("w") as f:
            json.dump(self.version_history, f, indent=2)

    def add_version_to_file(self, file_path: Path, version: str = "1.0") -> bool:
        """Add version number to a Python file"""
        if not file_path.exists() or file_path.suffix != ".py":
            return False

        with file_path.open("r") as f:
            content = f.read()

        # Check if file already has version
        if self.VERSION_PATTERN.search(content) or self.VERSION_COMMENT_PATTERN.search(content):
            return False

        # Add version at the beginning of the file after docstring if present
        lines = content.split("\n")
        insert_index = 0
        in_docstring = False
        docstring_char = None

        for i, line in enumerate(lines):
            # Check for docstring
            if i == 0 and (line.startswith('"""') or line.startswith("'''")):
                docstring_char = '"""' if line.startswith('"""') else "'''"
                if line.count(docstring_char) == 2:  # Single line docstring
                    insert_index = i + 1
                    break
                in_docstring = True
                continue

            if in_docstring:
                if docstring_char and docstring_char in line:
                    insert_index = i + 1
                    break
            elif not line.strip() or line.startswith("#"):
                continue
            else:
                insert_index = i
                break

        # Insert version
        version_line = f'\n__version__ = "{version}"\n'
        lines.insert(insert_index, version_line)

        # Write back to file
        with file_path.open("w") as f:
            f.write("\n".join(lines))

        # Update history
        relative_path = str(file_path.relative_to(self.root_path))
        self.version_history["files"][relative_path] = {
            "version": version,
            "added_at": datetime.now().isoformat(),
        }

        return True

    def get_file_version(self, file_path: Path) -> str | None:
        """Get version number from a Python file"""
        if not file_path.exists():
            return None

        with file_path.open("r") as f:
            content = f.read()

        # Try to find __version__ variable
        match = self.VERSION_PATTERN.search(content)
        if match:
            return match.group(1)

        # Try to find version in comment
        match = self.VERSION_COMMENT_PATTERN.search(content)
        if match:
            return match.group(1)

        return None

    def update_file_version(self, file_path: Path, new_version: str) -> bool:
        """Update version number in a Python file"""
        if not file_path.exists():
            return False

        with file_path.open("r") as f:
            content = f.read()

        # Replace __version__ variable
        new_content = self.VERSION_PATTERN.sub(f'__version__ = "{new_version}"', content)

        # If no __version__ found, try comment
        if new_content == content:
            new_content = self.VERSION_COMMENT_PATTERN.sub(f"# Version: {new_version}", content)

        # If still no change, add version
        if new_content == content:
            return self.add_version_to_file(file_path, new_version)

        with file_path.open("w") as f:
            f.write(new_content)

        # Update history
        relative_path = str(file_path.relative_to(self.root_path))
        if relative_path not in self.version_history["files"]:
            self.version_history["files"][relative_path] = {}

        self.version_history["files"][relative_path].update(
            {"version": new_version, "updated_at": datetime.now().isoformat()}
        )

        return True

    def scan_and_version_all_files(self, version: str = "1.0") -> tuple[list[str], list[str]]:
        """Scan all Python files and add version numbers"""
        versioned = []
        skipped = []

        # Define directories to skip
        skip_dirs = {
            ".venv",
            "__pycache__",
            ".git",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "neo4j-import",
            "neo4j-plugins",
            ".obsidian",
        }

        for py_file in self.root_path.rglob("*.py"):
            # Skip if in excluded directory
            if any(skip_dir in py_file.parts for skip_dir in skip_dirs):
                continue

            relative_path = str(py_file.relative_to(self.root_path))

            if self.add_version_to_file(py_file, version):
                versioned.append(relative_path)
            else:
                # File already has version or couldn't be processed
                existing_version = self.get_file_version(py_file)
                if existing_version:
                    self.version_history["files"][relative_path] = {
                        "version": existing_version,
                        "existing": True,
                    }
                skipped.append(relative_path)

        self.save_version_history()
        return versioned, skipped

    def get_version_report(self) -> dict[str, Any]:
        """Generate a report of all file versions"""
        report = {
            "global_version": self.version_history["global_version"],
            "total_files": len(self.version_history["files"]),
            "files_by_version": {},
        }

        for file_path, info in self.version_history["files"].items():
            version = info.get("version", "unknown")
            if version not in report["files_by_version"]:
                report["files_by_version"][version] = []
            report["files_by_version"][version].append(file_path)

        return report

    def bump_version(self, file_path: Path, bump_type: str = "patch") -> str | None:
        """Bump version number (major.minor.patch)"""
        current_version = self.get_file_version(file_path)
        if not current_version:
            return None

        parts = current_version.split(".")
        if len(parts) == 2:
            parts.append("0")  # Add patch version if missing

        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0

        if bump_type == "major":
            major += 1
            minor = 0
            patch = 0
        elif bump_type == "minor":
            minor += 1
            patch = 0
        elif bump_type == "patch":
            patch += 1

        new_version = f"{major}.{minor}.{patch}" if patch > 0 else f"{major}.{minor}"

        if self.update_file_version(file_path, new_version):
            self.save_version_history()
            return new_version

        return None


# CLI Interface for version management
def main() -> None:
    """CLI for version management"""
    import argparse

    parser = argparse.ArgumentParser(description="Version Management System")
    parser.add_argument(
        "command", choices=["init", "report", "bump", "get"], help="Command to execute"
    )
    parser.add_argument("--file", help="File path for file-specific operations")
    parser.add_argument("--version", default="1.0", help="Version number")
    parser.add_argument(
        "--bump-type",
        choices=["major", "minor", "patch"],
        default="patch",
        help="Type of version bump",
    )

    args = parser.parse_args()

    vm = VersionManager()

    if args.command == "init":
        versioned, skipped = vm.scan_and_version_all_files(args.version)
        print(f"Versioned {len(versioned)} files")
        print(f"Skipped {len(skipped)} files (already versioned or excluded)")

    elif args.command == "report":
        report = vm.get_version_report()
        print(f"Global Version: {report['global_version']}")
        print(f"Total Files: {report['total_files']}")
        print("\nFiles by Version:")
        for version, files in report["files_by_version"].items():
            print(f"  {version}: {len(files)} files")

    elif args.command == "get" and args.file:
        version = vm.get_file_version(Path(args.file))
        if version:
            print(f"Version: {version}")
        else:
            print("No version found")

    elif args.command == "bump" and args.file:
        new_version = vm.bump_version(Path(args.file), args.bump_type)
        if new_version:
            print(f"Bumped to version: {new_version}")
        else:
            print("Failed to bump version")


if __name__ == "__main__":
    main()
