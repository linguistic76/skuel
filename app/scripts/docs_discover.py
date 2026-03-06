#!/usr/bin/env python3
"""
Documentation Discovery Tool

Helps developers find relevant documentation by keyword, topic, or task.
Searches across titles, frontmatter, and content with intelligent ranking.

Usage:
    poetry run python scripts/docs_discover.py "error handling"
    poetry run python scripts/docs_discover.py --task "add domain service"
    poetry run python scripts/docs_discover.py --keywords result,validation
    poetry run python scripts/docs_discover.py "cypher" --limit 5
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SearchResult:
    """A documentation search result with relevance score."""

    path: str
    title: str
    category: str
    score: float
    match_type: str  # title, keyword, content, task
    snippet: str = ""
    related_skills: list[str] = field(default_factory=list)

    def __lt__(self, other: "SearchResult") -> bool:
        """Sort by score descending."""
        return self.score > other.score


# Task-based search mappings
TASK_MAP = {
    "add domain": [
        "/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md",
        "/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md",
        "/docs/reference/templates/service_creation.md",
        "/.claude/skills/activity-domains/SKILL.md",
    ],
    "add domain service": [
        "/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md",
        "/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md",
        "/docs/reference/templates/service_creation.md",
    ],
    "write cypher": [
        "/docs/patterns/query_architecture.md",
        "/docs/patterns/GRAPH_ACCESS_PATTERNS.md",
        "/docs/architecture/NEO4J_DATABASE_ARCHITECTURE.md",
        "/.claude/skills/neo4j-cypher-patterns/SKILL.md",
    ],
    "write query": [
        "/docs/patterns/query_architecture.md",
        "/docs/patterns/GRAPH_ACCESS_PATTERNS.md",
        "/.claude/skills/neo4j-cypher-patterns/SKILL.md",
    ],
    "handle errors": [
        "/docs/patterns/ERROR_HANDLING.md",
        "/docs/patterns/RETURN_TYPE_ERROR_PROPAGATION.md",
        "/.claude/skills/result-pattern/SKILL.md",
    ],
    "error handling": [
        "/docs/patterns/ERROR_HANDLING.md",
        "/docs/patterns/RETURN_TYPE_ERROR_PROPAGATION.md",
        "/.claude/skills/result-pattern/SKILL.md",
    ],
    "add route": [
        "/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md",
        "/docs/patterns/ROUTE_FACTORIES.md",
        "/docs/architecture/ROUTING_ARCHITECTURE.md",
        "/.claude/skills/fasthtml/SKILL.md",
    ],
    "create route": [
        "/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md",
        "/docs/patterns/ROUTE_FACTORIES.md",
        "/.claude/skills/fasthtml/SKILL.md",
    ],
    "write test": [
        "/docs/patterns/TESTING_PATTERNS.md",
        "/TESTING.md",
        "/.claude/skills/pytest/SKILL.md",
    ],
    "testing": [
        "/docs/patterns/TESTING_PATTERNS.md",
        "/TESTING.md",
        "/.claude/skills/pytest/SKILL.md",
    ],
    "add ui component": [
        "/docs/patterns/UI_COMPONENT_PATTERNS.md",
        "/docs/guides/SHARED_UI_COMPONENTS_GUIDE.md",
        "/.claude/skills/html-htmx/SKILL.md",
        "/.claude/skills/js-alpine/SKILL.md",
    ],
    "style component": [
        "/docs/patterns/UI_COMPONENT_PATTERNS.md",
        "/.claude/skills/tailwind-css/SKILL.md",
        "/.claude/skills/daisyui/SKILL.md",
    ],
    "search implementation": [
        "/docs/architecture/SEARCH_ARCHITECTURE.md",
        "/docs/patterns/query_architecture.md",
        "/docs/reference/SEARCH_SERVICE_METHODS.md",
        "/.claude/skills/skuel-search-architecture/SKILL.md",
    ],
    "add validation": [
        "/docs/patterns/API_VALIDATION_PATTERNS.md",
        "/docs/patterns/three_tier_type_system.md",
        "/.claude/skills/pydantic/SKILL.md",
    ],
    "type system": [
        "/docs/patterns/three_tier_type_system.md",
        "/.claude/skills/python/SKILL.md",
        "/.claude/skills/pydantic/SKILL.md",
    ],
    "protocol": [
        "/docs/patterns/protocol_architecture.md",
        "/docs/patterns/BACKEND_OPERATIONS_ISP.md",
        "/docs/reference/PROTOCOL_REFERENCE.md",
    ],
    "intelligence service": [
        "/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md",
        "/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md",
        "/.claude/skills/base-analytics-service/SKILL.md",
    ],
    "analytics": [
        "/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md",
        "/.claude/skills/base-analytics-service/SKILL.md",
    ],
}


def parse_frontmatter(content: str) -> dict[str, Any]:
    """Parse YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}

    end_match = re.search(r"\n---\n", content[3:])
    if not end_match:
        return {}

    frontmatter_text = content[3 : end_match.start() + 3]

    try:
        return yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError:
        return {}


def extract_snippet(content: str, query: str, max_length: int = 150) -> str:
    """Extract a snippet of text around the search query."""
    # Remove frontmatter
    if content.startswith("---"):
        end_match = re.search(r"\n---\n", content[3:])
        if end_match:
            content = content[end_match.end() + 3 :]

    # Find query in content (case-insensitive)
    query_lower = query.lower()
    content_lower = content.lower()

    index = content_lower.find(query_lower)
    if index == -1:
        # Query not in content, return first paragraph
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                return line[:max_length] + "..." if len(line) > max_length else line
        return ""

    # Extract text around query
    start = max(0, index - 50)
    end = min(len(content), index + len(query) + 100)

    snippet = content[start:end]

    # Clean up snippet
    snippet = snippet.strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."

    return snippet


def calculate_relevance_score(
    doc_path: Path,
    content: str,
    frontmatter: dict,
    query: str,
    query_terms: list[str],
) -> tuple[float, str]:
    """
    Calculate relevance score for a document.

    Returns (score, match_type).

    Scoring:
    - Title exact match: 10.0
    - Title partial match: 7.0
    - Keyword match: 5.0
    - Content match (multiple terms): 3.0
    - Content match (single term): 1.0
    """
    title = frontmatter.get("title", doc_path.stem).lower()
    keywords = [k.lower() for k in frontmatter.get("keywords", [])]
    related_skills = frontmatter.get("related_skills", [])
    content_lower = content.lower()
    query_lower = query.lower()

    # Title exact match
    if query_lower == title:
        return 10.0, "title"

    # Title contains query
    if query_lower in title:
        return 7.0, "title"

    # Title contains any query term
    for term in query_terms:
        if term.lower() in title:
            return 6.0, "title"

    # Keyword exact match
    if query_lower in keywords:
        return 5.0, "keyword"

    # Keyword partial match
    for keyword in keywords:
        if query_lower in keyword or keyword in query_lower:
            return 4.5, "keyword"

    # Related skills match
    for skill in related_skills:
        if query_lower in skill.lower():
            return 4.0, "skill"

    # Content match - count term occurrences
    term_matches = sum(1 for term in query_terms if term.lower() in content_lower)

    if term_matches >= len(query_terms):
        # All terms present
        return 3.0, "content"
    elif term_matches > 0:
        # Some terms present
        return 1.0 + (term_matches * 0.5), "content"

    return 0.0, "none"


def search_docs(
    docs_dir: Path, query: str, limit: int = 10, include_skills: bool = True
) -> list[SearchResult]:
    """
    Search documentation by keyword/phrase.

    Searches across:
    - Document titles
    - Frontmatter keywords
    - Related skills
    - Content
    """
    query_terms = [term.strip() for term in query.split() if len(term.strip()) > 2]
    results: list[SearchResult] = []

    # Search in /docs/
    for doc_path in docs_dir.rglob("*.md"):
        try:
            content = doc_path.read_text(encoding="utf-8")
            frontmatter = parse_frontmatter(content)

            score, match_type = calculate_relevance_score(
                doc_path, content, frontmatter, query, query_terms
            )

            if score > 0:
                snippet = extract_snippet(content, query)
                rel_path = str(doc_path.relative_to(docs_dir.parent))

                result = SearchResult(
                    path=rel_path,
                    title=frontmatter.get("title", doc_path.stem),
                    category=frontmatter.get("category", "uncategorized"),
                    score=score,
                    match_type=match_type,
                    snippet=snippet,
                    related_skills=frontmatter.get("related_skills", []),
                )
                results.append(result)

        except Exception:
            # Skip files that can't be read
            continue

    # Search in skills if enabled
    if include_skills:
        skills_dir = docs_dir.parent / ".claude" / "skills"
        if skills_dir.exists():
            for skill_dir in skills_dir.iterdir():
                if not skill_dir.is_dir() or skill_dir.name.startswith("_"):
                    continue

                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists():
                    try:
                        content = skill_md.read_text(encoding="utf-8")
                        frontmatter = parse_frontmatter(content)

                        # Adjust scoring for skills (boost by 0.5)
                        score, match_type = calculate_relevance_score(
                            skill_md, content, {"title": skill_dir.name}, query, query_terms
                        )
                        score = score * 1.2  # Slight boost for skills

                        if score > 0:
                            snippet = extract_snippet(content, query)
                            rel_path = str(skill_md.relative_to(docs_dir.parent))

                            result = SearchResult(
                                path=rel_path,
                                title=f"{skill_dir.name} (skill)",
                                category="skill",
                                score=score,
                                match_type=match_type,
                                snippet=snippet,
                            )
                            results.append(result)

                    except Exception:
                        continue

    # Sort by score and limit
    results.sort()
    return results[:limit]


def search_by_task(docs_dir: Path, task: str) -> list[SearchResult]:
    """
    Find documentation by developer task.

    Uses predefined task mappings for common development tasks.
    Falls back to keyword search if no mapping found.
    """
    task_lower = task.lower().strip()

    # Try exact match
    if task_lower in TASK_MAP:
        doc_paths = TASK_MAP[task_lower]
    else:
        # Try fuzzy match (substring)
        matches = [key for key in TASK_MAP if task_lower in key or key in task_lower]
        if matches:
            # Use first match
            doc_paths = TASK_MAP[matches[0]]
        else:
            # Fall back to keyword search
            return search_docs(docs_dir, task, limit=10)

    results: list[SearchResult] = []
    project_root = docs_dir.parent

    for i, doc_path_str in enumerate(doc_paths):
        # Convert to absolute path
        if doc_path_str.startswith("/"):
            doc_path = project_root / doc_path_str.lstrip("/")
        else:
            doc_path = project_root / doc_path_str

        if not doc_path.exists():
            continue

        try:
            content = doc_path.read_text(encoding="utf-8")
            frontmatter = parse_frontmatter(content)

            # Score by order in task map (first = most relevant)
            score = 10.0 - (i * 0.5)

            snippet = extract_snippet(content, task, max_length=200)
            rel_path = str(doc_path.relative_to(project_root))

            result = SearchResult(
                path=rel_path,
                title=frontmatter.get("title", doc_path.stem),
                category=frontmatter.get("category", "task-based"),
                score=score,
                match_type="task",
                snippet=snippet,
                related_skills=frontmatter.get("related_skills", []),
            )
            results.append(result)

        except Exception:
            continue

    return results


def search_by_keywords(docs_dir: Path, keywords: list[str], limit: int = 10) -> list[SearchResult]:
    """
    Search by multiple keywords (AND logic).

    All keywords must be present in title, frontmatter, or content.
    """
    results: list[SearchResult] = []

    for doc_path in docs_dir.rglob("*.md"):
        try:
            content = doc_path.read_text(encoding="utf-8")
            frontmatter = parse_frontmatter(content)

            title = frontmatter.get("title", doc_path.stem).lower()
            doc_keywords = [k.lower() for k in frontmatter.get("keywords", [])]
            content_lower = content.lower()

            # Check if all keywords match
            matches = []
            for keyword in keywords:
                keyword_lower = keyword.lower()
                if (
                    keyword_lower in title
                    or keyword_lower in doc_keywords
                    or keyword_lower in content_lower
                ):
                    matches.append(keyword)

            if len(matches) == len(keywords):
                # All keywords present
                score = 5.0 + len(matches)

                snippet = extract_snippet(content, keywords[0])
                rel_path = str(doc_path.relative_to(docs_dir.parent))

                result = SearchResult(
                    path=rel_path,
                    title=frontmatter.get("title", doc_path.stem),
                    category=frontmatter.get("category", "uncategorized"),
                    score=score,
                    match_type="keywords",
                    snippet=snippet,
                    related_skills=frontmatter.get("related_skills", []),
                )
                results.append(result)

        except Exception:
            continue

    # Sort by score and limit
    results.sort()
    return results[:limit]


def print_results(results: list[SearchResult], query: str) -> None:
    """Print search results in a readable format."""
    if not results:
        print(f"No results found for: {query}")
        print()
        print("Try:")
        print("  - Using different keywords")
        print("  - Using --task for common development tasks")
        print("  - Checking available tasks with --list-tasks")
        return

    print(f"Found {len(results)} result(s) for: {query}")
    print("=" * 60)
    print()

    for i, result in enumerate(results, 1):
        print(f"{i}. {result.title}")
        print(f"   Path: {result.path}")
        print(f"   Match: {result.match_type} (score: {result.score:.1f})")

        if result.related_skills:
            skills_str = ", ".join(result.related_skills)
            print(f"   Skills: {skills_str}")

        if result.snippet:
            print(f"   {result.snippet}")

        print()


def list_available_tasks() -> None:
    """List all available task-based search queries."""
    print("Available Task-Based Searches:")
    print("=" * 60)
    print()

    tasks = sorted(TASK_MAP.keys())
    for task in tasks:
        print(f'  --task "{task}"')
        docs = TASK_MAP[task]
        print(f"      → {len(docs)} document(s)")

    print()
    print(f"Total: {len(tasks)} predefined tasks")


def main() -> None:
    args = sys.argv[1:]

    if not args or "--help" in args or "-h" in args:
        print(__doc__)
        return

    if "--list-tasks" in args:
        list_available_tasks()
        return

    # Parse arguments
    task_mode = False
    keywords_mode = False
    limit = 10
    query_parts = []

    i = 0
    while i < len(args):
        arg = args[i]

        if arg == "--task":
            task_mode = True
            i += 1
            continue
        if arg == "--keywords":
            keywords_mode = True
            i += 1
            continue
        if arg == "--limit":
            if i + 1 < len(args):
                try:
                    limit = int(args[i + 1])
                    i += 2
                    continue
                except ValueError:
                    print(f"Error: Invalid limit value: {args[i + 1]}", file=sys.stderr)
                    sys.exit(1)
            else:
                print("Error: --limit requires a value", file=sys.stderr)
                sys.exit(1)
        elif not arg.startswith("--"):
            query_parts.append(arg)

        i += 1

    if not query_parts:
        print("Error: No search query provided", file=sys.stderr)
        print("Usage: poetry run python scripts/docs_discover.py <query>", file=sys.stderr)
        sys.exit(1)

    query = " ".join(query_parts)

    # Find docs directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    docs_dir = project_root / "docs"

    if not docs_dir.exists():
        print(f"Error: docs directory not found at {docs_dir}", file=sys.stderr)
        sys.exit(1)

    # Perform search
    if task_mode:
        results = search_by_task(docs_dir, query)
    elif keywords_mode:
        keywords = [k.strip() for k in query.split(",")]
        results = search_by_keywords(docs_dir, keywords, limit=limit)
    else:
        results = search_docs(docs_dir, query, limit=limit)

    # Print results
    print_results(results, query)


if __name__ == "__main__":
    main()
