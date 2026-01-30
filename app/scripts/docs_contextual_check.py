#!/usr/bin/env python3
"""
Contextual Documentation Checker

Finds docs that need updating based on code changes, using:
1. Git diff analysis
2. LLM semantic understanding
3. Fast text search for statistical references

Usage:
    # Check based on last commit (default)
    poetry run python scripts/docs_contextual_check.py

    # Check based on specific commit range
    poetry run python scripts/docs_contextual_check.py --since HEAD~3

    # Check specific files (for git hook)
    poetry run python scripts/docs_contextual_check.py --files "file1.py,file2.py"

    # Skip LLM analysis (fast mode, text search only)
    poetry run python scripts/docs_contextual_check.py --fast

    # Non-interactive mode (exit code indicates if docs need updating)
    poetry run python scripts/docs_contextual_check.py --ci
"""

import argparse
import json
import os
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
    confidence: str  # "low", "medium", "high"
    source: str  # "text_search", "llm", "pattern"


def is_git_hook_context() -> bool:
    """Check if we're running in a git hook context."""
    return os.environ.get("GIT_AUTHOR_DATE") is not None or os.environ.get("GIT_DIR") is not None


def is_docs_check_disabled() -> bool:
    """Check if docs-check is disabled via git config."""
    try:
        result = subprocess.run(
            ["git", "config", "--get", "skuel.docs-check"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.stdout.strip().lower() in ("false", "0", "no", "off")
    except Exception:
        return False


def get_changed_files(since: str = "HEAD") -> list[str]:
    """
    Get files changed in the specified commit(s).

    Args:
        since: Git ref (default: HEAD = last commit)

    Returns:
        List of changed file paths relative to repo root
    """
    try:
        # Get files changed in the commit
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", since],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        files = [f for f in result.stdout.strip().split("\n") if f]

        # Filter to relevant file types
        relevant_extensions = {".py", ".md", ".json", ".yaml", ".yml", ".toml"}
        return [f for f in files if Path(f).suffix in relevant_extensions or Path(f).stem in ("CLAUDE",)]
    except subprocess.CalledProcessError:
        return []
    except subprocess.TimeoutExpired:
        print(f"{YELLOW}Warning: git command timed out{RESET}", file=sys.stderr)
        return []


def extract_key_terms(changed_files: list[str]) -> list[str]:
    """
    Extract key terms from changed file paths for text search.

    Examples:
        core/services/tasks/tasks_core_service.py -> ["tasks", "TasksCoreService", "DomainConfig"]
        docs/migrations/PHASE4.md -> ["PHASE4", "migration"]
    """
    terms = set()

    for file_path in changed_files:
        path = Path(file_path)

        # Extract from path components
        for part in path.parts:
            # Add directory/file names (e.g., "tasks", "migrations")
            if part and not part.startswith("."):
                terms.add(part)

            # Extract CamelCase components (e.g., "TasksCoreService" -> "Tasks", "Core", "Service")
            camel_parts = re.findall(r"[A-Z][a-z]+", part)
            terms.update(camel_parts)

        # Extract from filename
        stem = path.stem
        if stem:
            terms.add(stem)

            # Split snake_case (e.g., "tasks_core_service" -> "tasks", "core", "service")
            terms.update(stem.split("_"))

    # Filter out common noise words
    noise = {"py", "service", "test", "tests", "core", "base", "utils", "common", "init"}
    terms = {t for t in terms if len(t) > 2 and t.lower() not in noise}

    return sorted(terms)


def find_docs_with_terms(terms: list[str], docs_dir: Path, project_root: Path) -> dict[str, list[str]]:
    """
    Use ripgrep to find docs mentioning specific terms.

    Returns dict of {doc_path: [matching_terms]}
    """
    if not terms:
        return {}

    doc_matches: dict[str, set[str]] = {}

    try:
        # Build regex pattern: match any of the terms (case-insensitive word boundaries)
        pattern = "|".join(re.escape(term) for term in terms)

        result = subprocess.run(
            ["rg", "-i", "-l", pattern, str(docs_dir), str(project_root / "CLAUDE.md")],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            matching_files = result.stdout.strip().split("\n")

            # For each matching file, find which terms matched
            for file_path in matching_files:
                if not file_path:
                    continue

                try:
                    content = Path(file_path).read_text(encoding="utf-8").lower()
                    matched_terms = [term for term in terms if term.lower() in content]

                    if matched_terms:
                        rel_path = str(Path(file_path).relative_to(project_root))
                        doc_matches[rel_path] = set(matched_terms)
                except Exception:
                    continue

    except subprocess.TimeoutExpired:
        print(f"{YELLOW}Warning: text search timed out{RESET}", file=sys.stderr)
    except FileNotFoundError:
        print(f"{YELLOW}Warning: ripgrep (rg) not found - install for faster search{RESET}", file=sys.stderr)
    except Exception as e:
        print(f"{YELLOW}Warning: text search failed: {e}{RESET}", file=sys.stderr)

    return {k: list(v) for k, v in doc_matches.items()}


def analyze_with_llm(
    changed_files: list[str], project_root: Path, max_files: int = 8
) -> list[DocSuggestion]:
    """
    Use LLM to find docs that might need updating.

    Args:
        changed_files: List of file paths that changed
        project_root: Project root directory
        max_files: Maximum number of files to include in prompt (to avoid huge prompts)

    Returns:
        List of DocSuggestion objects
    """
    # Check for API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return []

    try:
        import anthropic
    except ImportError:
        print(f"{YELLOW}Warning: anthropic package not installed - skipping LLM analysis{RESET}", file=sys.stderr)
        return []

    # Read changed files (limited to avoid huge prompts)
    file_contents: dict[str, str] = {}
    for file_path in changed_files[:max_files]:
        try:
            full_path = project_root / file_path
            if full_path.exists() and full_path.is_file():
                content = full_path.read_text(encoding="utf-8")
                # Truncate large files
                if len(content) > 3000:
                    content = content[:3000] + "\n\n... [truncated] ..."
                file_contents[file_path] = content
        except Exception:
            continue

    if not file_contents:
        return []

    # Build prompt
    prompt = f"""These code files were just changed in a git commit:

{chr(10).join(f"- {f}" for f in changed_files)}

File contents (truncated if large):

{chr(10).join(f"### {f}{chr(10)}```{chr(10)}{c}{chr(10)}```{chr(10)}" for f, c in file_contents.items())}

Based on these changes, which documentation files in /docs or CLAUDE.md might need updating?

Consider these update types:
1. **Migration docs** - Track progress (e.g., "X of Y completed", "Phase N")
2. **Statistical updates** - Service counts, percentages, scores (e.g., "25 services", "9.6/10")
3. **Architecture summaries** - Pattern adoption, completion status
4. **CLAUDE.md sections** - Quick-reference that mentions these patterns
5. **Pattern docs** - Examples from these files, usage guides
6. **Cross-references** - Docs that mention these file paths

Return a JSON array of objects with:
- doc_path: relative path from project root (e.g., "docs/migrations/DOMAINCONFIG_MIGRATION_COMPLETE.md")
- reason: specific reason why this doc needs updating (be concrete)
- confidence: "low", "medium", or "high"

Only include suggestions with medium or high confidence.
Return ONLY the JSON array, no other text.

Example response:
[
  {{"doc_path": "docs/migrations/X.md", "reason": "Tracks migration progress, currently shows 25/34", "confidence": "high"}},
  {{"doc_path": "CLAUDE.md", "reason": "Line 753 references service count", "confidence": "medium"}}
]
"""

    try:
        client = anthropic.Anthropic(api_key=api_key)

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract text response
        response_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                response_text += block.text

        # Parse JSON (handle markdown code blocks if present)
        response_text = response_text.strip()
        if response_text.startswith("```"):
            # Remove markdown code block markers
            response_text = re.sub(r"```(?:json)?\n?", "", response_text).strip()

        suggestions_data = json.loads(response_text)

        # Convert to DocSuggestion objects
        suggestions = []
        for item in suggestions_data:
            if isinstance(item, dict) and "doc_path" in item:
                suggestions.append(
                    DocSuggestion(
                        doc_path=item["doc_path"],
                        reason=item.get("reason", "LLM suggested update"),
                        confidence=item.get("confidence", "medium"),
                        source="llm",
                    )
                )

        return suggestions

    except json.JSONDecodeError as e:
        print(f"{YELLOW}Warning: Failed to parse LLM response as JSON: {e}{RESET}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"{YELLOW}Warning: LLM analysis failed: {e}{RESET}", file=sys.stderr)
        return []


def detect_pattern_changes(changed_files: list[str]) -> list[DocSuggestion]:
    """
    Detect common patterns that indicate specific docs need updating.

    This is a fast, deterministic check for known patterns.
    """
    suggestions = []

    # Pattern 1: DomainConfig changes -> migration doc
    domainconfig_files = [f for f in changed_files if "domain_config" in f.lower() or "_config = " in f.lower()]
    if domainconfig_files:
        suggestions.append(
            DocSuggestion(
                doc_path="docs/migrations/DOMAINCONFIG_MIGRATION_COMPLETE.md",
                reason=f"DomainConfig-related changes detected in {len(domainconfig_files)} file(s)",
                confidence="medium",
                source="pattern",
            )
        )

    # Pattern 2: BaseService changes -> multiple docs
    baseservice_files = [f for f in changed_files if "base_service" in f.lower()]
    if baseservice_files:
        suggestions.extend(
            [
                DocSuggestion(
                    doc_path="docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md",
                    reason="BaseService changes may affect service patterns",
                    confidence="medium",
                    source="pattern",
                ),
                DocSuggestion(
                    doc_path="docs/guides/BASESERVICE_QUICK_START.md",
                    reason="BaseService implementation changed",
                    confidence="low",
                    source="pattern",
                ),
            ]
        )

    # Pattern 3: Protocol changes -> protocol docs
    protocol_files = [f for f in changed_files if "protocol" in f.lower()]
    if protocol_files:
        suggestions.append(
            DocSuggestion(
                doc_path="docs/patterns/protocol_architecture.md",
                reason=f"Protocol changes detected in {len(protocol_files)} file(s)",
                confidence="medium",
                source="pattern",
            )
        )

    # Pattern 4: Service file changes -> CLAUDE.md (if many files changed)
    service_files = [f for f in changed_files if "/services/" in f and f.endswith(".py")]
    if len(service_files) >= 5:
        suggestions.append(
            DocSuggestion(
                doc_path="CLAUDE.md",
                reason=f"Large-scale service changes ({len(service_files)} files) may affect quick-reference",
                confidence="low",
                source="pattern",
            )
        )

    # Pattern 5: Migration doc changes -> check other migration docs for consistency
    migration_files = [f for f in changed_files if "migrations/" in f and f.endswith(".md")]
    if migration_files:
        suggestions.append(
            DocSuggestion(
                doc_path="CLAUDE.md",
                reason="Migration doc changed - CLAUDE.md may need status update",
                confidence="medium",
                source="pattern",
            )
        )

    return suggestions


def merge_suggestions(
    text_suggestions: dict[str, list[str]],
    llm_suggestions: list[DocSuggestion],
    pattern_suggestions: list[DocSuggestion],
) -> list[DocSuggestion]:
    """
    Merge suggestions from different sources and deduplicate.

    Returns sorted list with highest confidence first.
    """
    # Convert text suggestions to DocSuggestion objects
    all_suggestions: dict[str, DocSuggestion] = {}

    for doc_path, terms in text_suggestions.items():
        all_suggestions[doc_path] = DocSuggestion(
            doc_path=doc_path,
            reason=f"Mentions: {', '.join(terms[:5])}",
            confidence="low",
            source="text_search",
        )

    # Add LLM suggestions (higher priority - can override)
    for suggestion in llm_suggestions:
        if suggestion.doc_path in all_suggestions:
            # Merge: keep LLM reason, upgrade confidence
            existing = all_suggestions[suggestion.doc_path]
            all_suggestions[suggestion.doc_path] = DocSuggestion(
                doc_path=suggestion.doc_path,
                reason=suggestion.reason,
                confidence="high" if suggestion.confidence == "high" else existing.confidence,
                source="llm+text_search" if existing.source == "text_search" else "llm",
            )
        else:
            all_suggestions[suggestion.doc_path] = suggestion

    # Add pattern suggestions
    for suggestion in pattern_suggestions:
        if suggestion.doc_path not in all_suggestions:
            all_suggestions[suggestion.doc_path] = suggestion

    # Sort by confidence (high > medium > low)
    confidence_order = {"high": 3, "medium": 2, "low": 1}
    sorted_suggestions = sorted(
        all_suggestions.values(), key=lambda s: confidence_order.get(s.confidence, 0), reverse=True
    )

    return sorted_suggestions


def print_suggestions(suggestions: list[DocSuggestion], changed_files: list[str], interactive: bool = True) -> None:
    """Print formatted suggestions to terminal."""
    if not suggestions:
        print(f"{GREEN}✓ No documentation updates needed{RESET}")
        return

    print(f"\n{BOLD}📄 Documentation Update Suggestions{RESET}")
    print(f"{DIM}Based on changes to {len(changed_files)} file(s){RESET}\n")

    # Group by confidence
    high_conf = [s for s in suggestions if s.confidence == "high"]
    med_conf = [s for s in suggestions if s.confidence == "medium"]
    low_conf = [s for s in suggestions if s.confidence == "low"]

    if high_conf:
        print(f"{RED}🔴 HIGH CONFIDENCE ({len(high_conf)}){RESET}")
        for s in high_conf:
            print(f"  📄 {BOLD}{s.doc_path}{RESET}")
            print(f"     {s.reason}")
            print()

    if med_conf:
        print(f"{YELLOW}🟡 MEDIUM CONFIDENCE ({len(med_conf)}){RESET}")
        for s in med_conf:
            print(f"  📄 {s.doc_path}")
            print(f"     {s.reason}")
            print()

    if low_conf and interactive:
        print(f"{DIM}⚪ LOW CONFIDENCE ({len(low_conf)}){RESET}")
        for s in low_conf:
            print(f"{DIM}  📄 {s.doc_path}")
            print(f"     {s.reason}{RESET}")
            print()

    if interactive:
        print(f"{CYAN}Update docs with:{RESET}")
        for s in high_conf + med_conf:
            print(f"  poetry run python scripts/docs_update.py --doc {s.doc_path}")

        print(f"\n{DIM}Or update all at once:{RESET}")
        print(f"{DIM}  poetry run python scripts/docs_update.py --all{RESET}")

        print(f"\n{DIM}To disable this check: git config skuel.docs-check false{RESET}")


def main() -> int:
    """
    Main entry point.

    Returns:
        0 if no docs need updating, 1 if docs need updating, 2 on error
    """
    parser = argparse.ArgumentParser(
        description="Contextual documentation checker - finds docs that need updating based on code changes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--since", default="HEAD", help="Git ref to check changes since (default: HEAD)")
    parser.add_argument("--files", help="Comma-separated list of changed files (for git hook)")
    parser.add_argument("--fast", action="store_true", help="Skip LLM analysis (text search only)")
    parser.add_argument("--ci", action="store_true", help="CI mode: non-interactive, exit code only")
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Quiet mode: only print if docs need updating",
    )

    args = parser.parse_args()

    # Check if disabled
    if is_docs_check_disabled():
        if not args.quiet:
            print(f"{DIM}📄 Docs check disabled (git config skuel.docs-check = false){RESET}")
        return 0

    # Find project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    docs_dir = project_root / "docs"

    # Get changed files
    if args.files:
        changed_files = [f.strip() for f in args.files.split(",") if f.strip()]
    else:
        changed_files = get_changed_files(args.since)

    if not changed_files:
        if not args.quiet:
            print(f"{DIM}📄 No relevant files changed{RESET}")
        return 0

    # Filter out documentation files (we don't check docs when docs change)
    code_files = [f for f in changed_files if not f.startswith("docs/") and not f.endswith(".md")]

    if not code_files:
        if not args.quiet:
            print(f"{DIM}📄 Only documentation files changed{RESET}")
        return 0

    # Run checks
    suggestions: list[DocSuggestion] = []

    # 1. Pattern detection (fast, deterministic)
    pattern_suggestions = detect_pattern_changes(code_files)

    # 2. Text search (fast)
    terms = extract_key_terms(code_files)
    text_matches = find_docs_with_terms(terms, docs_dir, project_root)
    text_suggestions = {doc: terms for doc, terms in text_matches.items() if doc.startswith("docs/")}

    # 3. LLM analysis (slower, but more accurate)
    llm_suggestions: list[DocSuggestion] = []
    if not args.fast:
        llm_suggestions = analyze_with_llm(code_files, project_root)

    # Merge and deduplicate
    suggestions = merge_suggestions(text_suggestions, llm_suggestions, pattern_suggestions)

    # Filter to only medium/high confidence for output (unless verbose)
    if args.ci or is_git_hook_context():
        suggestions = [s for s in suggestions if s.confidence in ("medium", "high")]

    # Print results
    interactive = not args.ci and not args.quiet
    print_suggestions(suggestions, code_files, interactive)

    # Return exit code
    return 1 if suggestions else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted{RESET}")
        sys.exit(130)
    except Exception as e:
        print(f"{RED}Error: {e}{RESET}", file=sys.stderr)
        sys.exit(2)
