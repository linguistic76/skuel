#!/usr/bin/env python3
"""
Enhanced Contextual Documentation Checker (v2)

Improvements over v1:
1. Detects new documentation files and suggests INDEX updates
2. More sophisticated pattern matching for observability, metrics, etc.
3. Analyzes documentation files (not just code) to find cross-refs
4. Checks for numerical references that might be stale (counts, percentages)
5. More nuanced confidence scoring

Usage:
    poetry run python scripts/docs_contextual_check_v2.py
    poetry run python scripts/docs_contextual_check_v2.py --since HEAD~3
"""

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
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


def detect_numerical_references(
    changed_files: list[str], project_root: Path
) -> list[DocSuggestion]:
    """
    Detect when code changes might make numerical references stale.

    Examples:
    - "35 metrics" -> should be "43 metrics"
    - "14 domains" -> might need updating
    - "25 services migrated" -> progress tracking
    """
    suggestions = []

    # Patterns that indicate numerical tracking
    numerical_patterns = [
        (r"(\d+)\s+metrics?", "metrics"),
        (r"(\d+)\s+alerts?", "alerts"),
        (r"(\d+)\s+domains?", "domains"),
        (r"(\d+)\s+services?", "services"),
        (r"(\d+)\s+of\s+(\d+)", "progress tracking"),
        (r"(\d+)%", "percentage"),
        (r"Phase\s+(\d+)", "phase number"),
    ]

    # Check if code changes relate to these concepts
    code_keywords = set()
    for file_path in changed_files:
        if file_path.endswith(".py"):
            # Extract key concepts from code files
            if "metrics" in file_path.lower():
                code_keywords.add("metrics")
            if "service" in file_path.lower():
                code_keywords.add("services")
            if "domain" in file_path.lower():
                code_keywords.add("domains")

    if not code_keywords:
        return suggestions

    # Search docs for numerical references to these concepts
    docs_to_check = [
        "CLAUDE.md",
        "docs/INDEX.md",
        "docs/architecture/*.md",
        "docs/migrations/*COMPLETE*.md",
        ".claude/skills/*/SKILL.md",
    ]

    for doc_pattern in docs_to_check:
        try:
            # Find matching docs
            if "*" in doc_pattern:
                import glob

                matching_docs = glob.glob(str(project_root / doc_pattern))
            else:
                doc_path = project_root / doc_pattern
                matching_docs = [str(doc_path)] if doc_path.exists() else []

            for doc_file in matching_docs:
                try:
                    content = Path(doc_file).read_text(encoding="utf-8")

                    # Check each pattern
                    for pattern, concept in numerical_patterns:
                        if concept not in code_keywords and concept != "progress tracking":
                            continue

                        matches = re.findall(pattern, content, re.IGNORECASE)
                        if matches:
                            rel_path = str(Path(doc_file).relative_to(project_root))
                            suggestions.append(
                                DocSuggestion(
                                    doc_path=rel_path,
                                    reason=f"Contains {len(matches)} numerical reference(s) to '{concept}' - verify accuracy",
                                    confidence="medium",
                                    source="numerical_analysis",
                                    action=f"Search for pattern '{pattern}' and verify counts are current",
                                )
                            )
                            break  # One suggestion per doc

                except Exception:
                    continue

        except Exception:
            continue

    return suggestions


def detect_advanced_patterns(changed_files: list[str]) -> list[DocSuggestion]:
    """
    Enhanced pattern detection with more nuanced rules.
    """
    suggestions = []

    # Pattern: Monitoring/observability changes
    monitoring_files = [
        f
        for f in changed_files
        if any(
            x in f.lower()
            for x in ["prometheus", "metrics", "monitoring", "observability", "alert"]
        )
    ]
    if monitoring_files:
        suggestions.append(
            DocSuggestion(
                doc_path="CLAUDE.md",
                reason=f"Monitoring infrastructure changed ({len(monitoring_files)} files)",
                confidence="high",
                source="pattern:monitoring",
                action="Update monitoring/observability section with new metrics/alerts",
            )
        )
        suggestions.append(
            DocSuggestion(
                doc_path=".claude/skills/prometheus-grafana/SKILL.md",
                reason="Monitoring code changes may affect metrics documentation",
                confidence="medium",
                source="pattern:monitoring",
                action="Verify metrics catalog is up to date",
            )
        )

    # Pattern: DomainConfig changes
    domainconfig_files = [f for f in changed_files if "domain_config" in f.lower()]
    if domainconfig_files:
        suggestions.append(
            DocSuggestion(
                doc_path="docs/migrations/DOMAINCONFIG_MIGRATION_COMPLETE.md",
                reason=f"DomainConfig changes in {len(domainconfig_files)} file(s)",
                confidence="high",
                source="pattern:domainconfig",
                action="Update migration progress if new services were migrated",
            )
        )

    # Pattern: Protocol changes
    protocol_files = [f for f in changed_files if "protocol" in f.lower()]
    if protocol_files:
        suggestions.append(
            DocSuggestion(
                doc_path="docs/patterns/protocol_architecture.md",
                reason=f"Protocol changes in {len(protocol_files)} file(s)",
                confidence="high",
                source="pattern:protocol",
                action="Update protocol documentation with new interfaces",
            )
        )
        suggestions.append(
            DocSuggestion(
                doc_path="docs/reference/PROTOCOL_REFERENCE.md",
                reason=f"Protocol changes in {len(protocol_files)} file(s)",
                confidence="high",
                source="pattern:protocol",
                action="Verify protocol catalog is current",
            )
        )

    # Pattern: Service changes (large scale)
    service_files = [f for f in changed_files if "/services/" in f and f.endswith(".py")]
    if len(service_files) >= 5:
        suggestions.append(
            DocSuggestion(
                doc_path="docs/guides/BASESERVICE_QUICK_START.md",
                reason=f"Large-scale service changes ({len(service_files)} files)",
                confidence="medium",
                source="pattern:services",
                action="Review if service patterns or examples need updating",
            )
        )

    # Pattern: Migration docs updated
    migration_files = [f for f in changed_files if "migrations/" in f and f.endswith(".md")]
    if migration_files:
        suggestions.append(
            DocSuggestion(
                doc_path="CLAUDE.md",
                reason="Migration documentation updated - CLAUDE.md may need status sync",
                confidence="high",
                source="pattern:migration",
                action="Update migration status in CLAUDE.md ## Documentation Architecture section",
            )
        )

    # Pattern: Embedding/AI service changes
    ai_files = [
        f
        for f in changed_files
        if any(x in f.lower() for x in ["embedding", "openai", "genai", "llm", "ai_"])
    ]
    if ai_files:
        suggestions.append(
            DocSuggestion(
                doc_path="docs/architecture/NEO4J_GENAI_ARCHITECTURE.md",
                reason=f"AI/embedding service changes ({len(ai_files)} files)",
                confidence="medium",
                source="pattern:ai",
                action="Verify GenAI architecture docs reflect current implementation",
            )
        )

    # Pattern: Key infrastructure files → specific documentation
    # These files are central to the architecture; changes almost always
    # require documentation updates in known locations.
    infrastructure_doc_map: dict[str, list[tuple[str, str]]] = {
        "services_bootstrap.py": [
            (
                "CLAUDE.md",
                "Update Protocol-Based Architecture section (field counts, typing strategies)",
            ),
            (
                "docs/patterns/protocol_architecture.md",
                "Update protocol coverage and Services dataclass field counts",
            ),
            (
                "docs/reference/PROTOCOL_REFERENCE.md",
                "Verify protocol catalog matches current Services fields",
            ),
        ],
        "base_service.py": [
            (
                "docs/guides/BASESERVICE_QUICK_START.md",
                "Verify BaseService examples and mixin documentation",
            ),
            (
                "docs/reference/BASESERVICE_METHOD_INDEX.md",
                "Regenerate method index if methods changed",
            ),
        ],
        "shared_enums.py": [
            ("CLAUDE.md", "Update domain count or EntityType list if enums changed"),
            (
                "docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md",
                "Verify domain list matches enum definitions",
            ),
        ],
        "relationship_registry.py": [
            (
                "docs/decisions/ADR-026-unified-relationship-registry.md",
                "Verify registry documentation matches implementation",
            ),
        ],
        "route_factories.py": [
            (
                "docs/patterns/ROUTE_FACTORIES.md",
                "Update factory documentation if signatures or patterns changed",
            ),
        ],
    }

    for file_path in changed_files:
        filename = Path(file_path).name
        if filename in infrastructure_doc_map:
            for doc_path, action in infrastructure_doc_map[filename]:
                suggestions.append(
                    DocSuggestion(
                        doc_path=doc_path,
                        reason=f"Infrastructure file {filename} changed",
                        confidence="high",
                        source=f"pattern:infrastructure:{filename}",
                        action=action,
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
    """
    Merge suggestions for same doc, keeping highest confidence.
    """
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

    print(f"\n{BOLD}📄 Documentation Update Suggestions (v2){RESET}")
    print(f"{DIM}Based on {len(changed_files)} changed file(s){RESET}\n")

    # Group by confidence
    critical = [s for s in suggestions if s.confidence == "critical"]
    high = [s for s in suggestions if s.confidence == "high"]
    medium = [s for s in suggestions if s.confidence == "medium"]
    _low = [s for s in suggestions if s.confidence == "low"]  # Reserved for future use

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

    if medium:
        print(f"{DIM}🟢 MEDIUM CONFIDENCE ({len(medium)}){RESET}")
        for s in medium:
            print(f"{DIM}  📄 {s.doc_path}")
            print(f"     {s.reason}")
            if s.action:
                print(f"     Action: {s.action}")
            print(f"     Source: {s.source}{RESET}")
            print()

    print(f"{CYAN}Next steps:{RESET}")
    print("  1. Review each suggested doc")
    print("  2. Make necessary updates")
    print("  3. Commit doc updates separately")
    print()
    print(f"{DIM}To disable: git config skuel.docs-check false{RESET}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Enhanced documentation checker (v2)")
    parser.add_argument("--since", default="HEAD", help="Git ref to check (default: HEAD)")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode")

    args = parser.parse_args()

    # Find project root
    project_root = Path(__file__).parent.parent

    # Get changed files
    changed_files = get_changed_files(args.since)

    if not changed_files:
        if not args.quiet:
            print(f"{DIM}📄 No files changed{RESET}")
        return 0

    # Run all detection methods
    all_suggestions: list[DocSuggestion] = []

    # 1. Detect new documentation files (CRITICAL)
    all_suggestions.extend(detect_new_documentation_files(changed_files))

    # 2. Detect numerical references that might be stale
    all_suggestions.extend(detect_numerical_references(changed_files, project_root))

    # 3. Advanced pattern matching
    all_suggestions.extend(detect_advanced_patterns(changed_files))

    # 4. Cross-reference analysis
    all_suggestions.extend(analyze_cross_references(changed_files, project_root))

    # Merge and deduplicate
    suggestions = merge_and_deduplicate(all_suggestions)

    # Filter out low confidence in quiet mode
    if args.quiet:
        suggestions = [s for s in suggestions if s.confidence in ("critical", "high", "medium")]

    # Print results
    if not args.quiet:
        print_suggestions(suggestions, changed_files)
    elif suggestions:
        # In quiet mode, print counts at all actionable levels
        critical_count = sum(1 for s in suggestions if s.confidence == "critical")
        high_count = sum(1 for s in suggestions if s.confidence == "high")
        medium_count = sum(1 for s in suggestions if s.confidence == "medium")
        urgent = critical_count + high_count
        if urgent:
            print(f"{YELLOW}📄 {urgent} doc(s) may need updating{RESET}")
            for s in suggestions:
                if s.confidence in ("critical", "high"):
                    print(f"  - {s.doc_path}: {s.reason}")
        elif medium_count:
            print(f"{YELLOW}📄 {medium_count} doc(s) may need updating (medium confidence){RESET}")
            for s in suggestions:
                if s.confidence == "medium":
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
