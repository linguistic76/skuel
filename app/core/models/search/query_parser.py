"""
Search Query Parser - Natural Language to Type-Safe Filters
============================================================

Extracts semantic meaning from natural language search queries by leveraging
the from_search_text() methods on SKUEL's enums.

Design Philosophy:
- "show me urgent tasks" → extracts Priority.CRITICAL, Priority.HIGH
- "find completed goals" → extracts ActivityStatus.COMPLETED
- "health habits" → extracts Domain.HEALTH

This bridges the gap between user-friendly natural language and
type-safe filter structures.

Usage:
    from core.models.search.query_parser import SearchQueryParser

    parser = SearchQueryParser()
    parsed = parser.parse("show me urgent tasks in progress")

    # ParsedSearchQuery contains:
    # - raw_query: "show me urgent tasks in progress"
    # - text_query: "show me tasks"  (cleaned for text search)
    # - priorities: [Priority.CRITICAL, Priority.HIGH]
    # - statuses: [ActivityStatus.IN_PROGRESS]
    # - domains: []

Version: 1.0.0
Date: 2025-11-29
"""

from dataclasses import dataclass

from core.models.enums import (
    ActivityStatus,
    ContentType,
    Domain,
    LearningLevel,
    Priority,
)


@dataclass(frozen=True)
class ParsedSearchQuery:
    """
    Result of parsing a natural language search query.

    Contains both the original query and extracted semantic filters.
    """

    # Original query
    raw_query: str

    # Cleaned text for database text search (with filter words removed)
    text_query: str

    # Extracted semantic filters
    priorities: tuple[Priority, ...] = ()
    statuses: tuple[ActivityStatus, ...] = ()
    domains: tuple[Domain, ...] = ()
    learning_levels: tuple[LearningLevel, ...] = ()
    content_types: tuple[ContentType, ...] = ()

    def has_filters(self) -> bool:
        """Check if any semantic filters were extracted."""
        return bool(
            self.priorities
            or self.statuses
            or self.domains
            or self.learning_levels
            or self.content_types
        )

    def has_priority_filter(self) -> bool:
        """Check if priority filters were extracted."""
        return bool(self.priorities)

    def has_status_filter(self) -> bool:
        """Check if status filters were extracted."""
        return bool(self.statuses)

    def has_domain_filter(self) -> bool:
        """Check if domain filters were extracted."""
        return bool(self.domains)

    def get_highest_priority(self) -> Priority | None:
        """Get the highest priority from extracted priorities."""
        if not self.priorities:
            return None
        # Sort by numeric value (CRITICAL=4 > HIGH=3 > MEDIUM=2 > LOW=1)
        return max(self.priorities, key=Priority.to_numeric)

    def to_filter_summary(self) -> str:
        """Generate human-readable summary of extracted filters."""
        parts = []
        if self.priorities:
            priority_names = [p.value for p in self.priorities]
            parts.append(f"priority: {', '.join(priority_names)}")
        if self.statuses:
            status_names = [s.value for s in self.statuses]
            parts.append(f"status: {', '.join(status_names)}")
        if self.domains:
            domain_names = [d.value for d in self.domains]
            parts.append(f"domain: {', '.join(domain_names)}")
        if self.learning_levels:
            level_names = [l.value for l in self.learning_levels]
            parts.append(f"level: {', '.join(level_names)}")

        if parts:
            return f"Filters: {'; '.join(parts)}"
        return "No filters extracted"


class SearchQueryParser:
    """
    Parses natural language search queries to extract semantic filters.

    Uses the from_search_text() methods on SKUEL's enums to identify
    priority, status, domain, and other semantic indicators in queries.

    Example:
        parser = SearchQueryParser()

        # "urgent tasks" → Priority.CRITICAL, Priority.HIGH
        result = parser.parse("show me urgent tasks")
        assert Priority.CRITICAL in result.priorities

        # "completed health goals" → ActivityStatus.COMPLETED, Domain.HEALTH
        result = parser.parse("completed health goals")
        assert ActivityStatus.COMPLETED in result.statuses
        assert Domain.HEALTH in result.domains
    """

    # Words to remove from text query after extracting semantic filters
    # These are stop words that don't add value to text search
    STOP_WORDS = frozenset(
        {
            "show",
            "me",
            "find",
            "get",
            "list",
            "all",
            "my",
            "the",
            "a",
            "an",
            "with",
            "that",
            "are",
            "is",
            "for",
            "to",
            "of",
            "and",
            "or",
            "in",
            "on",
            "at",
            "by",
        }
    )

    def parse(self, query: str) -> ParsedSearchQuery:
        """
        Parse a natural language query into semantic filters.

        Args:
            query: Natural language search query (e.g., "urgent health tasks")

        Returns:
            ParsedSearchQuery with extracted filters and cleaned text query

        Example:
            >>> parser = SearchQueryParser()
            >>> result = parser.parse("urgent tasks in progress")
            >>> result.priorities
            (Priority.CRITICAL, Priority.HIGH)
            >>> result.statuses
            (ActivityStatus.IN_PROGRESS,)
        """
        if not query or not query.strip():
            return ParsedSearchQuery(raw_query="", text_query="")

        raw_query = query.strip()

        # Extract semantic filters using enum methods
        priorities = tuple(Priority.from_search_text(raw_query))
        statuses = tuple(ActivityStatus.from_search_text(raw_query))
        domains = tuple(Domain.from_search_text(raw_query))
        learning_levels = tuple(LearningLevel.from_search_text(raw_query))
        content_types = tuple(ContentType.from_search_text(raw_query))

        # Build cleaned text query by removing filter synonyms and stop words
        text_query = self._clean_query(
            raw_query, priorities, statuses, domains, learning_levels, content_types
        )

        return ParsedSearchQuery(
            raw_query=raw_query,
            text_query=text_query,
            priorities=priorities,
            statuses=statuses,
            domains=domains,
            learning_levels=learning_levels,
            content_types=content_types,
        )

    def _clean_query(
        self,
        query: str,
        priorities: tuple[Priority, ...],
        statuses: tuple[ActivityStatus, ...],
        domains: tuple[Domain, ...],
        learning_levels: tuple[LearningLevel, ...],
        content_types: tuple[ContentType, ...],
    ) -> str:
        """
        Remove filter words and stop words from query for cleaner text search.

        The goal is to keep only the meaningful search terms after
        semantic filters have been extracted.

        Strategy: Only remove EXACT matches for single-word synonyms,
        and remove multi-word phrases that appear in the query.
        Keep domain-related words that might be search terms (e.g., "tasks").
        """
        # Single-word synonyms to remove (exact matches only)
        words_to_remove: set[str] = set()

        # Multi-word phrases to remove
        phrases_to_remove: set[str] = set()

        # Collect synonyms from matched filters
        for priority in priorities:
            for synonym in priority.get_search_synonyms():
                if " " in synonym:
                    phrases_to_remove.add(synonym)
                else:
                    words_to_remove.add(synonym)

        for status in statuses:
            for synonym in status.get_search_synonyms():
                if " " in synonym:
                    phrases_to_remove.add(synonym)
                else:
                    words_to_remove.add(synonym)

        # For domains, only remove obvious filter words, not content words
        # e.g., remove "health" but keep "tasks" (might be search term)
        domain_filter_words = {"health", "tech", "business", "personal", "creative", "social"}
        for domain in domains:
            for synonym in domain.get_search_synonyms():
                if " " in synonym:
                    phrases_to_remove.add(synonym)
                elif synonym in domain_filter_words:
                    words_to_remove.add(synonym)

        for level in learning_levels:
            for synonym in level.get_search_synonyms():
                if " " in synonym:
                    phrases_to_remove.add(synonym)
                else:
                    words_to_remove.add(synonym)

        for content_type in content_types:
            for synonym in content_type.get_search_synonyms():
                if " " in synonym:
                    phrases_to_remove.add(synonym)
                else:
                    words_to_remove.add(synonym)

        # Start with original query
        cleaned = query.lower()

        # Remove multi-word phrases first
        for phrase in phrases_to_remove:
            cleaned = cleaned.replace(phrase, " ")

        # Split into words and filter
        words = cleaned.split()
        cleaned_words = []

        for word in words:
            # Skip stop words
            if word in self.STOP_WORDS:
                continue
            # Skip exact matches to filter words
            if word in words_to_remove:
                continue
            cleaned_words.append(word)

        # Join remaining words
        cleaned = " ".join(cleaned_words).strip()

        # If everything was removed, return a minimal cleaned version
        if not cleaned:
            # Fall back to original minus just stop words
            words = query.lower().split()
            cleaned = " ".join(w for w in words if w not in self.STOP_WORDS)

        return cleaned

    def extract_priority(self, query: str) -> tuple[Priority, ...]:
        """Extract just priority filters from a query."""
        return tuple(Priority.from_search_text(query))

    def extract_status(self, query: str) -> tuple[ActivityStatus, ...]:
        """Extract just status filters from a query."""
        return tuple(ActivityStatus.from_search_text(query))

    def extract_domain(self, query: str) -> tuple[Domain, ...]:
        """Extract just domain filters from a query."""
        return tuple(Domain.from_search_text(query))


# Module-level convenience function
def parse_search_query(query: str) -> ParsedSearchQuery:
    """
    Convenience function to parse a search query.

    Args:
        query: Natural language search query

    Returns:
        ParsedSearchQuery with extracted filters

    Example:
        >>> from core.models.search.query_parser import parse_search_query
        >>> result = parse_search_query("urgent health tasks")
        >>> result.priorities
        (Priority.CRITICAL, Priority.HIGH)
    """
    return SearchQueryParser().parse(query)
