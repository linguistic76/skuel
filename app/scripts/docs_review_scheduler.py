#!/usr/bin/env python3
"""
Documentation Review Scheduler

Generates review schedule based on frontmatter tracking fields:
- last_reviewed: YYYY-MM-DD
- review_frequency: monthly | quarterly | annual

Identifies docs that are overdue for review and provides a prioritized list.

Usage:
    uv run python scripts/docs_review_scheduler.py              # All overdue docs
    uv run python scripts/docs_review_scheduler.py --upcoming   # Due within 30 days
    uv run python scripts/docs_review_scheduler.py --all        # All tracked docs
    uv run python scripts/docs_review_scheduler.py --category patterns  # By category
    uv run python scripts/docs_review_scheduler.py --json       # JSON output
"""

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from core.utils.frontmatter import parse_frontmatter as _parse_frontmatter


@dataclass
class ReviewStatus:
    """Review status for a single documentation file."""

    path: str
    title: str
    category: str
    tracking: str  # code, conceptual, hybrid
    last_reviewed: str | None
    review_frequency: str | None
    days_since_review: int
    days_until_due: int
    is_overdue: bool
    priority: str  # critical, high, medium, low

    def __lt__(self, other: "ReviewStatus") -> bool:
        """Sort by priority then days_until_due."""
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        if priority_order[self.priority] != priority_order[other.priority]:
            return priority_order[self.priority] < priority_order[other.priority]
        return self.days_until_due < other.days_until_due


@dataclass
class ReviewSchedule:
    """Complete review schedule report."""

    generated_at: str
    total_tracked_docs: int
    overdue_docs: int
    upcoming_docs: int
    current_docs: int
    reviews: list[ReviewStatus] = field(default_factory=list)


# Review frequency thresholds (in days)
FREQUENCY_THRESHOLDS = {
    "monthly": 35,  # ~1 month + grace
    "quarterly": 100,  # ~3 months + grace
    "annual": 380,  # ~1 year + grace
}

# Default frequency by category (from freshness_config.yaml)
DEFAULT_FREQUENCIES = {
    "architecture": "quarterly",
    "patterns": "quarterly",
    "decisions": "annual",
    "guides": "quarterly",
    "reference": "monthly",
    "intelligence": "annual",
    "domains": "quarterly",
    "dsl": "quarterly",
    "migrations": "annual",
    "examples": "quarterly",
    "roadmap": "quarterly",
}


def parse_frontmatter(doc_path: Path) -> dict:
    """Parse YAML frontmatter from a markdown file."""
    content = doc_path.read_text(encoding="utf-8")
    return _parse_frontmatter(content)[0]


def calculate_review_status(
    doc_path: Path, frontmatter: dict, project_root: Path
) -> ReviewStatus | None:
    """
    Calculate review status for a document.

    Returns None if document doesn't use conceptual/hybrid tracking.
    """
    tracking = frontmatter.get("tracking", "code")
    if tracking not in ("conceptual", "hybrid"):
        # Only track conceptual/hybrid docs
        return None

    title = frontmatter.get("title", doc_path.stem)
    category = frontmatter.get("category", "uncategorized")
    last_reviewed = frontmatter.get("last_reviewed")
    review_frequency = frontmatter.get("review_frequency")

    # Use default frequency for category if not specified
    if not review_frequency:
        review_frequency = DEFAULT_FREQUENCIES.get(category, "quarterly")

    # Calculate days since last review
    if last_reviewed:
        try:
            # Handle both string and datetime.date objects
            if isinstance(last_reviewed, str):
                last_review_date = datetime.fromisoformat(last_reviewed)
            else:
                # Already a date object from YAML parsing
                last_review_date = datetime.combine(last_reviewed, datetime.min.time())

            days_since = (datetime.now() - last_review_date).days

            # Convert back to string for storage
            if not isinstance(last_reviewed, str):
                last_reviewed = last_reviewed.isoformat()

        except (ValueError, TypeError, AttributeError):
            # Invalid date format - treat as never reviewed
            days_since = 999
            last_reviewed = None
    else:
        # Never reviewed
        days_since = 999

    # Calculate threshold and days until due
    threshold = FREQUENCY_THRESHOLDS.get(review_frequency, 100)
    days_until_due = threshold - days_since

    is_overdue = days_until_due < 0

    # Determine priority
    if days_until_due < -30:
        # More than 30 days overdue
        priority = "critical"
    elif days_until_due < 0:
        # Overdue but less than 30 days
        priority = "high"
    elif days_until_due <= 30:
        # Due within 30 days
        priority = "medium"
    else:
        # Not due soon
        priority = "low"

    rel_path = str(doc_path.relative_to(project_root))

    return ReviewStatus(
        path=rel_path,
        title=title,
        category=category,
        tracking=tracking,
        last_reviewed=last_reviewed,
        review_frequency=review_frequency,
        days_since_review=days_since,
        days_until_due=days_until_due,
        is_overdue=is_overdue,
        priority=priority,
    )


def scan_docs(docs_dir: Path, project_root: Path) -> list[ReviewStatus]:
    """Scan all documentation files and build review schedule."""
    reviews: list[ReviewStatus] = []

    # Scan all .md files in docs directory
    for doc_path in sorted(docs_dir.rglob("*.md")):
        try:
            frontmatter = parse_frontmatter(doc_path)
            status = calculate_review_status(doc_path, frontmatter, project_root)

            if status is not None:
                reviews.append(status)

        except Exception:
            # Skip files that can't be read
            continue

    return reviews


def generate_schedule(reviews: list[ReviewStatus]) -> ReviewSchedule:
    """Generate review schedule report."""
    overdue = [r for r in reviews if r.is_overdue]
    upcoming = [r for r in reviews if not r.is_overdue and r.days_until_due <= 30]
    current = [r for r in reviews if r.days_until_due > 30]

    return ReviewSchedule(
        generated_at=datetime.now().isoformat(),
        total_tracked_docs=len(reviews),
        overdue_docs=len(overdue),
        upcoming_docs=len(upcoming),
        current_docs=len(current),
        reviews=reviews,
    )


def print_schedule(
    schedule: ReviewSchedule,
    show_all: bool = False,
    show_upcoming: bool = False,
    category_filter: str | None = None,
) -> None:
    """Print review schedule in human-readable format."""
    print("Documentation Review Schedule")
    print("=" * 60)
    print(f"Generated: {schedule.generated_at}")
    print()

    # Summary
    print("Summary:")
    print(f"  Total tracked docs: {schedule.total_tracked_docs}")
    print(f"  🔴 Overdue: {schedule.overdue_docs}")
    print(f"  🟡 Upcoming (30 days): {schedule.upcoming_docs}")
    print(f"  🟢 Current: {schedule.current_docs}")
    print()

    # Filter reviews
    reviews = schedule.reviews

    if category_filter:
        reviews = [r for r in reviews if r.category == category_filter]
        print(f"Filtered by category: {category_filter}")
        print()

    if not show_all:
        if show_upcoming:
            # Show upcoming + overdue
            reviews = [r for r in reviews if r.days_until_due <= 30]
        else:
            # Show only overdue (default)
            reviews = [r for r in reviews if r.is_overdue]

    if not reviews:
        if show_all:
            print("No tracked documentation found.")
        elif show_upcoming:
            print("No documentation due for review in the next 30 days.")
        else:
            print("No overdue documentation found. Great job!")
        print()
        return

    # Sort by priority
    reviews.sort()

    # Group by priority
    by_priority: dict[str, list[ReviewStatus]] = {
        "critical": [],
        "high": [],
        "medium": [],
        "low": [],
    }

    for review in reviews:
        by_priority[review.priority].append(review)

    # Print reviews by priority
    if by_priority["critical"]:
        print("🔴 CRITICAL (>30 days overdue):")
        print()
        for review in by_priority["critical"]:
            print(f"  {review.title}")
            print(f"    Path: {review.path}")
            print(f"    Category: {review.category}")
            if review.last_reviewed:
                print(
                    f"    Last reviewed: {review.last_reviewed} ({review.days_since_review} days ago)"
                )
            else:
                print("    Last reviewed: Never")
            print(f"    Frequency: {review.review_frequency}")
            print(f"    Overdue by: {abs(review.days_until_due)} days")
            print()

    if by_priority["high"]:
        print("🔴 HIGH (overdue):")
        print()
        for review in by_priority["high"]:
            print(f"  {review.title}")
            print(f"    Path: {review.path}")
            print(f"    Category: {review.category}")
            if review.last_reviewed:
                print(
                    f"    Last reviewed: {review.last_reviewed} ({review.days_since_review} days ago)"
                )
            else:
                print("    Last reviewed: Never")
            print(f"    Frequency: {review.review_frequency}")
            print(f"    Overdue by: {abs(review.days_until_due)} days")
            print()

    if show_upcoming and by_priority["medium"]:
        print("🟡 UPCOMING (due within 30 days):")
        print()
        for review in by_priority["medium"]:
            print(f"  {review.title}")
            print(f"    Path: {review.path}")
            print(f"    Category: {review.category}")
            if review.last_reviewed:
                print(
                    f"    Last reviewed: {review.last_reviewed} ({review.days_since_review} days ago)"
                )
            else:
                print("    Last reviewed: Never")
            print(f"    Frequency: {review.review_frequency}")
            print(f"    Due in: {review.days_until_due} days")
            print()

    if show_all and by_priority["low"]:
        print("🟢 CURRENT (not due soon):")
        print()
        for review in by_priority["low"]:
            print(f"  {review.title}")
            print(f"    Path: {review.path}")
            print(f"    Category: {review.category}")
            if review.last_reviewed:
                print(
                    f"    Last reviewed: {review.last_reviewed} ({review.days_since_review} days ago)"
                )
            else:
                print("    Last reviewed: Never")
            print(f"    Frequency: {review.review_frequency}")
            print(f"    Due in: {review.days_until_due} days")
            print()

    print("=" * 60)


def print_categories(schedule: ReviewSchedule) -> None:
    """Print available categories for filtering."""
    categories = set(r.category for r in schedule.reviews)

    print("Available Categories:")
    print("=" * 60)
    print()

    for category in sorted(categories):
        count = sum(1 for r in schedule.reviews if r.category == category)
        overdue = sum(1 for r in schedule.reviews if r.category == category and r.is_overdue)

        status = "🔴" if overdue > 0 else "🟢"
        print(f"  {status} {category}: {count} doc(s), {overdue} overdue")

    print()
    print("Use --category <name> to filter by category")
    print("=" * 60)


def main() -> None:
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(__doc__)
        return

    # Parse arguments
    show_all = "--all" in args
    show_upcoming = "--upcoming" in args
    show_categories = "--categories" in args
    json_output = "--json" in args
    category_filter = None

    for i, arg in enumerate(args):
        if arg == "--category" and i + 1 < len(args):
            category_filter = args[i + 1]

    # Find project root and docs directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    docs_dir = project_root / "docs"

    if not docs_dir.exists():
        print(f"Error: docs directory not found at {docs_dir}", file=sys.stderr)
        sys.exit(1)

    # Scan and generate schedule
    reviews = scan_docs(docs_dir, project_root)
    schedule = generate_schedule(reviews)

    # Output based on flags
    if json_output:
        output = asdict(schedule)
        print(json.dumps(output, indent=2, default=str))
    elif show_categories:
        print_categories(schedule)
    else:
        print_schedule(
            schedule,
            show_all=show_all,
            show_upcoming=show_upcoming,
            category_filter=category_filter,
        )


if __name__ == "__main__":
    main()
