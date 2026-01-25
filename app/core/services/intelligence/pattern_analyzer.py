"""
Pattern Analyzer
================

Pattern detection utilities for entity analysis in intelligence services.

Consolidates word frequency, keyword detection, and dict extraction patterns
that were duplicated across TasksIntelligenceService and PrinciplesIntelligenceService.

Created: January 2026
ADR: Intelligence Service Helper Consolidation

Usage:
    from core.services.intelligence import PatternAnalyzer

    # Word frequency from task titles
    patterns = PatternAnalyzer.extract_word_frequencies(
        [t.title for t in tasks], min_word_length=4, top_n=10
    )

    # Keyword-based detection (define extractor as named function)
    def get_lowercase_title(t): return t.title.lower()
    opportunities = PatternAnalyzer.detect_by_keywords(
        tasks,
        [(["debug", "fix", "bug"], "Error handling patterns")],
        get_lowercase_title,
        min_matches=3
    )

    # Dict field counting
    counts = PatternAnalyzer.extract_dict_field_counts(
        context_dict, ["goals", "habits", "tasks"]
    )
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


class PatternAnalyzer:
    """
    Static utility methods for pattern detection in entity text.

    Consolidates analysis patterns from:
    - TasksIntelligenceService: _analyze_task_patterns, _identify_learning_opportunities,
      _identify_knowledge_gaps, _identify_skill_opportunities
    - PrinciplesIntelligenceService: _extract_activities_from_dict, _extract_recent_activities_from_dict
    """

    @staticmethod
    def extract_word_frequencies(
        texts: Sequence[str],
        min_word_length: int = 4,
        exclude_words: set[str] | None = None,
        top_n: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Extract word frequency patterns from text list.

        Used by TasksIntelligenceService for task title pattern analysis.

        Args:
            texts: Sequence of text strings to analyze
            min_word_length: Minimum word length to include (default: 4)
            exclude_words: Set of words to exclude (default: None)
            top_n: Number of top patterns to return (default: 10)

        Returns:
            List of {"name": word, "frequency": count} dicts, sorted by frequency

        Example:
            patterns = PatternAnalyzer.extract_word_frequencies(
                [t.title for t in tasks],
                min_word_length=4,
                exclude_words={"the", "and", "for"},
                top_n=10
            )
        """
        exclude = exclude_words or set()
        word_counts: Counter[str] = Counter()

        for text in texts:
            for word in text.lower().split():
                if len(word) >= min_word_length and word not in exclude:
                    word_counts[word] += 1

        return [
            {"name": word, "frequency": count} for word, count in word_counts.most_common(top_n)
        ]

    @staticmethod
    def detect_by_keywords(
        entities: Sequence[Any],
        keyword_sets: list[tuple[list[str], str]],
        text_extractor: Callable[[Any], str],
        min_matches: int = 2,
    ) -> list[str]:
        """
        Detect patterns by keyword matching in entity text.

        Used by TasksIntelligenceService for learning opportunities and knowledge gaps.

        Args:
            entities: List of entities to analyze
            keyword_sets: List of (keywords, detection_name) tuples
            text_extractor: Function to get searchable text from entity
            min_matches: Minimum matches required to report detection (default: 2)

        Returns:
            List of detected pattern names

        Example:
            def get_lowercase_title(t): return t.title.lower()
            opportunities = PatternAnalyzer.detect_by_keywords(
                tasks,
                [
                    (["debug", "fix", "error", "bug"], "Error handling patterns"),
                    (["api", "integration", "connect"], "API integration practices"),
                ],
                get_lowercase_title,
                min_matches=3
            )
        """
        detections = []

        for keywords, detection_name in keyword_sets:
            matches = [e for e in entities if any(kw in text_extractor(e) for kw in keywords)]
            if len(matches) >= min_matches:
                detections.append(detection_name)

        return detections

    @staticmethod
    def detect_by_indicator_tuples(
        entities: Sequence[Any],
        indicators: list[tuple[str, str]],
        text_extractor: Callable[[Any], str],
        min_matches: int = 2,
    ) -> list[str]:
        """
        Detect patterns using simple indicator-to-detection mapping.

        Simpler variant of detect_by_keywords for single-keyword indicators.

        Used by TasksIntelligenceService for knowledge gap detection.

        Args:
            entities: List of entities to analyze
            indicators: List of (indicator_word, detection_name) tuples
            text_extractor: Function to get searchable text from entity
            min_matches: Minimum matches required (default: 2)

        Returns:
            List of detected pattern names

        Example:
            def get_lowercase_title(t): return t.title.lower()
            gaps = PatternAnalyzer.detect_by_indicator_tuples(
                tasks,
                [
                    ("test", "Testing strategies"),
                    ("performance", "Performance optimization"),
                    ("security", "Security best practices"),
                ],
                get_lowercase_title
            )
        """
        detections = []

        for indicator, detection_name in indicators:
            matches = [e for e in entities if indicator in text_extractor(e)]
            if len(matches) >= min_matches:
                detections.append(detection_name)

        return detections

    @staticmethod
    def extract_skill_keywords(
        entities: Sequence[Any],
        text_extractor: Callable[[Any], str],
        skill_keywords: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Extract skill development opportunities from entity text.

        Used by TasksIntelligenceService for skill opportunity identification.

        Args:
            entities: List of entities to analyze
            text_extractor: Function to get searchable text from entity
            skill_keywords: Optional list of keywords to detect (default: common tech skills)

        Returns:
            List of {"skill": name, "suggestion": text, "source": "task_analysis"} dicts

        Example:
            def get_lowercase_title(t): return t.title.lower()
            skills = PatternAnalyzer.extract_skill_keywords(
                tasks,
                get_lowercase_title,
                ["python", "react", "database", "testing"]
            )
        """
        default_keywords = [
            "python",
            "javascript",
            "react",
            "api",
            "database",
            "testing",
            "deploy",
            "docker",
            "kubernetes",
            "sql",
        ]
        keywords = skill_keywords or default_keywords
        found_skills: set[str] = set()

        for entity in entities:
            text = text_extractor(entity)
            for keyword in keywords:
                if keyword in text:
                    found_skills.add(keyword)

        return [
            {
                "skill": skill,
                "suggestion": f"Consider deepening knowledge in {skill}",
                "source": "task_analysis",
            }
            for skill in sorted(found_skills)
        ]

    @staticmethod
    def extract_dict_field_counts(
        context_dict: dict[str, Any],
        field_keys: list[str],
    ) -> dict[str, int]:
        """
        Extract and count list lengths from dict fields.

        Used by PrinciplesIntelligenceService for activity extraction.

        Args:
            context_dict: Dict containing lists as values
            field_keys: List of keys to extract and count

        Returns:
            Dict of key -> count for each field

        Example:
            counts = PatternAnalyzer.extract_dict_field_counts(
                context_dict,
                ["goals", "habits", "tasks", "events"]
            )
            # Returns {"goals": 3, "habits": 5, "tasks": 10, "events": 2}
        """
        return {key: len(context_dict.get(key, [])) for key in field_keys}

    @staticmethod
    def identify_factors(
        entities: Sequence[Any],
        conditions: list[tuple[Callable[[Sequence[Any]], bool], str]],
    ) -> list[str]:
        """
        Identify success/risk factors based on entity conditions.

        Used by TasksIntelligenceService and GoalsIntelligenceService for factor identification.

        Args:
            entities: List of entities to analyze
            conditions: List of (condition_fn, factor_name) tuples

        Returns:
            List of identified factor names

        Example:
            def has_high_priority_focus(ts):
                return sum(1 for t in ts if t.priority.is_high()) / len(ts) > 0.4
            def has_detailed_descriptions(ts):
                return sum(1 for t in ts if t.description) / len(ts) > 0.6
            factors = PatternAnalyzer.identify_factors(
                tasks,
                [
                    (has_high_priority_focus, "High priority focus drives completion"),
                    (has_detailed_descriptions, "Detailed task descriptions improve completion"),
                ]
            )
        """
        return [name for condition, name in conditions if condition(entities)]

    @staticmethod
    def count_by_category(
        entities: Sequence[Any],
        category_extractor: Callable[[Any], str],
    ) -> dict[str, int]:
        """
        Count entities by category.

        Args:
            entities: List of entities to categorize
            category_extractor: Function to get category from entity

        Returns:
            Dict of category -> count

        Example:
            def get_status_value(t): return t.status.value
            counts = PatternAnalyzer.count_by_category(tasks, get_status_value)
            # Returns {"pending": 5, "in_progress": 3, "completed": 10}
        """
        counts: dict[str, int] = {}
        for entity in entities:
            category = category_extractor(entity)
            counts[category] = counts.get(category, 0) + 1
        return counts

    @staticmethod
    def find_peak_time(
        entities: Sequence[Any],
        time_extractor: Callable[[Any], int | None],
    ) -> dict[str, Any] | None:
        """
        Find the peak time (hour) for entity activity.

        Used by TasksIntelligenceService for completion pattern analysis.

        Args:
            entities: List of entities with time data
            time_extractor: Function to extract hour (0-23) from entity, or None if unavailable

        Returns:
            Dict with "peak_hour", "count", "confidence" or None if no data

        Example:
            def get_completion_hour(t): return t.completed_at.hour if t.completed_at else None
            peak = PatternAnalyzer.find_peak_time(completed_tasks, get_completion_hour)
            # Returns {"peak_hour": 14, "count": 15, "confidence": 0.7}
        """
        hours = [time_extractor(e) for e in entities]
        valid_hours = [h for h in hours if h is not None]

        if not valid_hours:
            return None

        hour_counts = Counter(valid_hours)
        peak_hour, peak_count = hour_counts.most_common(1)[0]

        # Confidence based on how much peak stands out
        avg_count = sum(hour_counts.values()) / len(hour_counts) if hour_counts else 1
        confidence = min(1.0, peak_count / (avg_count * 2)) if avg_count > 0 else 0.5

        return {
            "peak_hour": peak_hour,
            "count": peak_count,
            "confidence": round(confidence, 2),
        }
