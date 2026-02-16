#!/usr/bin/env python3
"""
Contextual Documentation Checker (v2 — slimmed)

Two high-signal detection methods:
1. Detects new documentation files and suggests INDEX updates
2. Cross-reference analysis via ripgrep (docs that reference changed files)

Noisy detectors (numerical references, broad keyword patterns) removed —
those are now handled by the Claude Code PostToolUse hook which has
semantic understanding of what actually changed.

Usage:
    poetry run python scripts/docs_contextual_check_v2.py
    poetry run python scripts/docs_contextual_check_v2.py --since HEAD~3
    poetry run python scripts/docs_contextual_check_v2.py --since HEAD --json
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# ANSI color codes
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


@dataclass
class DocSuggestion:
    """A suggestion to update a documentation file."""

    doc_path: str
    reason: str
    confidence: str  # "low", "medium", "high", "critical"
    source: str
    action: str = ""  # Specific action to take


def get_changed_files(since: str = "HEAD") -> list[str]:
    """Get files changed in the specified commit."""
    try:
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", since],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return [f for f in result.stdout.strip().split("\n") if f]
    except Exception:
        return []


def detect_new_documentation_files(changed_files: list[str]) -> list[DocSuggestion]:
    """
    Detect when new documentation files are added.

    This triggers INDEX updates and cross-reference checks.
    """
    suggestions = []

    # Find new .md files in docs/ or root
    new_docs = []
    new_skill_docs = []

    for file_path in changed_files:
        # Check if file is new (added, not modified)
        try:
            result = subprocess.run(
                [
                    "git",
                    "diff-tree",
                    "--no-commit-id",
                    "--diff-filter=A",
                    "-r",
                    "HEAD",
                    "--",
                    file_path,
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
            is_new = bool(result.stdout.strip())
        except Exception:
            is_new = False

        if is_new:
            if file_path.startswith("docs/") and file_path.endswith(".md"):
                new_docs.append(file_path)
            elif file_path.startswith(".claude/skills/") and file_path.endswith(".md"):
                new_skill_docs.append(file_path)
            elif file_path.endswith(".md") and not file_path.startswith("test"):
                new_docs.append(file_path)

    # Suggest INDEX update
    if new_docs:
        suggestions.append(
            DocSuggestion(
                doc_path="docs/INDEX.md",
                reason=f"Added {len(new_docs)} new doc(s): {', '.join(Path(d).name for d in new_docs[:3])}",
                confidence="critical",
                source="new_file_detection",
                action="Add new documentation files to INDEX.md with descriptions",
            )
        )

    # Suggest skill index update
    if new_skill_docs:
        suggestions.append(
            DocSuggestion(
                doc_path="CLAUDE.md",
                reason=f"Added new skill documentation: {', '.join(Path(d).name for d in new_skill_docs)}",
                confidence="high",
                source="new_file_detection",
                action="Update skill descriptions in CLAUDE.md if needed",
            )
        )

    return suggestions


def analyze_cross_references(changed_files: list[str], project_root: Path) -> list[DocSuggestion]:
    """
    Find docs that directly reference changed file paths.

    More accurate than keyword search - looks for explicit file path mentions.
    """
    suggestions = []

    # Build search patterns from file paths
    file_patterns = []
    for file_path in changed_files:
        if file_path.endswith(".py"):
            # Add the full path
            file_patterns.append(file_path)
            # Add just the filename
            file_patterns.append(Path(file_path).name)

    if not file_patterns:
        return suggestions

    # Search docs for these file paths
    docs_dir = project_root / "docs"

    try:
        # Use ripgrep to find file path mentions
        pattern = "|".join(re.escape(p) for p in file_patterns[:20])  # Limit to avoid huge regex

        result = subprocess.run(
            ["rg", "-l", pattern, str(docs_dir), str(project_root / "CLAUDE.md")],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            matching_docs = result.stdout.strip().split("\n")

            for doc_path in matching_docs:
                if doc_path:
                    rel_path = str(Path(doc_path).relative_to(project_root))
                    suggestions.append(
                        DocSuggestion(
                            doc_path=rel_path,
                            reason="Contains explicit reference to modified file path",
                            confidence="high",
                            source="cross_reference",
                            action="Verify file path references and examples are still accurate",
                        )
                    )

    except Exception:
        pass

    return suggestions


def merge_and_deduplicate(all_suggestions: list[DocSuggestion]) -> list[DocSuggestion]:
    """Merge suggestions for same doc, keeping highest confidence."""
    by_doc: dict[str, DocSuggestion] = {}

    confidence_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}

    for suggestion in all_suggestions:
        doc_path = suggestion.doc_path

        if doc_path not in by_doc:
            by_doc[doc_path] = suggestion
        else:
            existing = by_doc[doc_path]
            current_conf = confidence_order.get(suggestion.confidence, 0)
            existing_conf = confidence_order.get(existing.confidence, 0)

            if current_conf > existing_conf:
                # Merge reasons
                by_doc[doc_path] = DocSuggestion(
                    doc_path=doc_path,
                    reason=f"{suggestion.reason}; {existing.reason}",
                    confidence=suggestion.confidence,
                    source=f"{suggestion.source}+{existing.source}",
                    action=suggestion.action or existing.action,
                )

    # Sort by confidence
    def by_confidence(suggestion: DocSuggestion) -> int:
        return confidence_order.get(suggestion.confidence, 0)

    return sorted(by_doc.values(), key=by_confidence, reverse=True)


def print_suggestions(suggestions: list[DocSuggestion], changed_files: list[str]) -> None:
    """Print formatted suggestions."""
    if not suggestions:
        print(f"{GREEN}✓ No documentation updates needed{RESET}")
        return

    print(f"\n{BOLD}📄 Documentation Update Suggestions{RESET}")
    print(f"{DIM}Based on {len(changed_files)} changed file(s){RESET}\n")

    # Group by confidence
    critical = [s for s in suggestions if s.confidence == "critical"]
    high = [s for s in suggestions if s.confidence == "high"]

    if critical:
        print(f"{RED}{BOLD}🔴 CRITICAL - ACTION REQUIRED ({len(critical)}){RESET}")
        for s in critical:
            print(f"  📄 {BOLD}{s.doc_path}{RESET}")
            print(f"     {RED}{s.reason}{RESET}")
            if s.action:
                print(f"     {CYAN}Action: {s.action}{RESET}")
            print(f"     {DIM}Source: {s.source}{RESET}")
            print()

    if high:
        print(f"{YELLOW}🟡 HIGH CONFIDENCE ({len(high)}){RESET}")
        for s in high:
            print(f"  📄 {BOLD}{s.doc_path}{RESET}")
            print(f"     {s.reason}")
            if s.action:
                print(f"     {CYAN}Action: {s.action}{RESET}")
            print(f"     {DIM}Source: {s.source}{RESET}")
            print()

    print(f"{CYAN}Next steps:{RESET}")
    print("  1. Review each suggested doc")
    print("  2. Make necessary updates")
    print("  3. Commit doc updates separately")
    print()
    print(f"{DIM}To disable: git config skuel.docs-check false{RESET}")


def print_json(suggestions: list[DocSuggestion], changed_files: list[str]) -> None:
    """Print suggestions as JSON for programmatic consumption."""
    output = {
        "changed_files": changed_files,
        "suggestions": [asdict(s) for s in suggestions],
    }
    print(json.dumps(output, indent=2))


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Documentation checker (high-signal detectors only)"
    )
    parser.add_argument("--since", default="HEAD", help="Git ref to check (default: HEAD)")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode")
    parser.add_argument(
        "--json", action="store_true", help="JSON output for programmatic consumption"
    )

    args = parser.parse_args()

    # Find project root
    project_root = Path(__file__).parent.parent

    # Get changed files
    changed_files = get_changed_files(args.since)

    if not changed_files:
        if args.json:
            print_json([], [])
        elif not args.quiet:
            print(f"{DIM}📄 No files changed{RESET}")
        return 0

    # Run high-signal detection methods only
    all_suggestions: list[DocSuggestion] = []

    # 1. Detect new documentation files (CRITICAL)
    all_suggestions.extend(detect_new_documentation_files(changed_files))

    # 2. Cross-reference analysis (HIGH)
    all_suggestions.extend(analyze_cross_references(changed_files, project_root))

    # Merge and deduplicate
    suggestions = merge_and_deduplicate(all_suggestions)

    # JSON output mode
    if args.json:
        print_json(suggestions, changed_files)
        return 1 if suggestions else 0

    # Print results
    if not args.quiet:
        print_suggestions(suggestions, changed_files)
    elif suggestions:
        critical_count = sum(1 for s in suggestions if s.confidence == "critical")
        high_count = sum(1 for s in suggestions if s.confidence == "high")
        urgent = critical_count + high_count
        if urgent:
            print(f"{YELLOW}📄 {urgent} doc(s) may need updating{RESET}")
            for s in suggestions:
                if s.confidence in ("critical", "high"):
                    print(f"  - {s.doc_path}: {s.reason}")

    return 1 if suggestions else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted{RESET}")
        sys.exit(130)
    except Exception as e:
        print(f"{RED}Error: {e}{RESET}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(2)
