"""
Tests for core.utils.text_truncation — sentence-boundary-aware truncation.
"""

import pytest

from core.utils.text_truncation import truncate_to_budget


class TestTruncateToBudget:
    """Tests for truncate_to_budget()."""

    def test_short_text_unchanged(self) -> None:
        """Text within budget passes through unchanged."""
        text = "Hello world."
        assert truncate_to_budget(text, 100) == text

    def test_exact_budget_unchanged(self) -> None:
        """Text exactly at budget passes through unchanged."""
        text = "x" * 500
        assert truncate_to_budget(text, 500) == text

    def test_truncation_adds_ellipsis(self) -> None:
        """Truncated text ends with '...'."""
        text = "a" * 200
        result = truncate_to_budget(text, 100)
        assert result.endswith("...")
        assert len(result) <= 100

    def test_prefers_sentence_boundary(self) -> None:
        """Truncation cuts at sentence end ('. ') when possible."""
        text = "First sentence. Second sentence. Third sentence that goes on and on."
        result = truncate_to_budget(text, 40)
        assert result.endswith("...")
        # Should cut after "Second sentence." (32 chars + "...")
        assert "First sentence." in result

    def test_prefers_paragraph_boundary(self) -> None:
        """Truncation prefers paragraph break over sentence end."""
        text = "First paragraph.\n\nSecond paragraph. More text here that continues."
        result = truncate_to_budget(text, 50)
        assert result.endswith("...")
        assert "First paragraph." in result

    def test_falls_back_to_word_boundary(self) -> None:
        """When no sentence/paragraph boundary, cuts at word boundary."""
        text = "word " * 50  # 250 chars, no periods
        result = truncate_to_budget(text, 100)
        assert result.endswith("...")
        assert not result.endswith(" ...")  # Shouldn't end with space before ellipsis

    def test_hard_cut_no_spaces(self) -> None:
        """Text with no boundaries gets a hard cut."""
        text = "x" * 200
        result = truncate_to_budget(text, 100)
        assert result == "x" * 97 + "..."
        assert len(result) == 100

    def test_empty_string(self) -> None:
        """Empty string passes through."""
        assert truncate_to_budget("", 100) == ""

    def test_does_not_cut_too_early(self) -> None:
        """Boundary in the first half of text is skipped (too much waste)."""
        # Period at position 10, then 190 chars of content
        text = "Short. " + "x" * 193
        result = truncate_to_budget(text, 150)
        # Should NOT cut at "Short." (only 6 chars) — too early
        assert len(result) > 50

    def test_newline_boundary(self) -> None:
        """Single newline is used as boundary when no paragraph/sentence break."""
        text = "Line one content\nLine two content\nLine three with lots more text"
        result = truncate_to_budget(text, 45)
        assert result.endswith("...")

    def test_realistic_lesson_content(self) -> None:
        """Simulates real Lesson content truncation."""
        lessons = [f"## Lesson {i}\n\n{'This is the content of lesson. ' * 100}" for i in range(10)]
        text = "\n\n---\n\n".join(lessons)
        assert len(text) > 10000

        result = truncate_to_budget(text, 10000)
        assert len(result) <= 10000
        assert result.endswith("...")

    def test_budget_one(self) -> None:
        """Very small budget still produces valid output."""
        result = truncate_to_budget("Hello world", 4)
        assert result == "H..."
        assert len(result) == 4

    @pytest.mark.parametrize("budget", [50, 100, 500, 1000, 5000])
    def test_result_never_exceeds_budget(self, budget: int) -> None:
        """Result length never exceeds the specified budget."""
        text = "A sentence here. " * 500
        result = truncate_to_budget(text, budget)
        assert len(result) <= budget
