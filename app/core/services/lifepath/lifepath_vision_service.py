"""
LifePath Vision Service
========================

Captures user's vision in their own words and extracts actionable themes.

This service bridges:
- User's WORDS (vision statement) -> System understanding (themes)
- Themes -> Learning Path recommendations

Flow:
1. User expresses vision: "I want to become a mindful technical leader"
2. LLM extracts themes: ["leadership", "mindfulness", "technology", "growth"]
3. Themes match to LP candidates: [lp:mindful-engineer, lp:tech-leadership]
4. User confirms designation or refines vision

Philosophy:
    "The user's vision is understood via the words user uses to communicate"
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from core.models.enums.lifepath_enums import ThemeCategory
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

from .lifepath_types import (
    LpRecommendation,
    VisionCapture,
    VisionTheme,
    WordActionAlignment,
)

if TYPE_CHECKING:
    from core.services.llm_service import LLMService
    from core.services.lp_service import LpService
    from core.services.user.unified_user_context import UserContext

logger = get_logger(__name__)


# Theme category mapping for common keywords
THEME_CATEGORY_MAPPING: dict[str, ThemeCategory] = {
    # Personal growth
    "growth": ThemeCategory.PERSONAL_GROWTH,
    "self-improvement": ThemeCategory.PERSONAL_GROWTH,
    "mindfulness": ThemeCategory.PERSONAL_GROWTH,
    "meditation": ThemeCategory.PERSONAL_GROWTH,
    "discipline": ThemeCategory.PERSONAL_GROWTH,
    "habits": ThemeCategory.PERSONAL_GROWTH,
    # Career
    "leadership": ThemeCategory.CAREER,
    "career": ThemeCategory.CAREER,
    "professional": ThemeCategory.CAREER,
    "management": ThemeCategory.CAREER,
    "promotion": ThemeCategory.CAREER,
    "technical": ThemeCategory.CAREER,
    "engineer": ThemeCategory.CAREER,
    "developer": ThemeCategory.CAREER,
    # Health
    "health": ThemeCategory.HEALTH,
    "fitness": ThemeCategory.HEALTH,
    "exercise": ThemeCategory.HEALTH,
    "nutrition": ThemeCategory.HEALTH,
    "wellness": ThemeCategory.HEALTH,
    "mental health": ThemeCategory.HEALTH,
    # Relationships
    "family": ThemeCategory.RELATIONSHIPS,
    "relationships": ThemeCategory.RELATIONSHIPS,
    "community": ThemeCategory.RELATIONSHIPS,
    "connection": ThemeCategory.RELATIONSHIPS,
    "social": ThemeCategory.RELATIONSHIPS,
    # Financial
    "financial": ThemeCategory.FINANCIAL,
    "wealth": ThemeCategory.FINANCIAL,
    "money": ThemeCategory.FINANCIAL,
    "investing": ThemeCategory.FINANCIAL,
    "independence": ThemeCategory.FINANCIAL,
    "freedom": ThemeCategory.FINANCIAL,
    # Creative
    "creative": ThemeCategory.CREATIVE,
    "art": ThemeCategory.CREATIVE,
    "music": ThemeCategory.CREATIVE,
    "writing": ThemeCategory.CREATIVE,
    "design": ThemeCategory.CREATIVE,
    "innovation": ThemeCategory.CREATIVE,
    # Spiritual
    "spiritual": ThemeCategory.SPIRITUAL,
    "purpose": ThemeCategory.SPIRITUAL,
    "meaning": ThemeCategory.SPIRITUAL,
    "values": ThemeCategory.SPIRITUAL,
    "transcendence": ThemeCategory.SPIRITUAL,
    # Intellectual
    "learning": ThemeCategory.INTELLECTUAL,
    "knowledge": ThemeCategory.INTELLECTUAL,
    "education": ThemeCategory.INTELLECTUAL,
    "mastery": ThemeCategory.INTELLECTUAL,
    "expertise": ThemeCategory.INTELLECTUAL,
    # Impact
    "impact": ThemeCategory.IMPACT,
    "contribution": ThemeCategory.IMPACT,
    "legacy": ThemeCategory.IMPACT,
    "change": ThemeCategory.IMPACT,
    "difference": ThemeCategory.IMPACT,
    "matter": ThemeCategory.IMPACT,
    # Lifestyle
    "balance": ThemeCategory.LIFESTYLE,
    "adventure": ThemeCategory.LIFESTYLE,
    "travel": ThemeCategory.LIFESTYLE,
    "lifestyle": ThemeCategory.LIFESTYLE,
}


class LifePathVisionService:
    """
    Service for capturing and analyzing user vision statements.

    Uses LLM to extract themes from natural language vision statements,
    then matches themes to Learning Paths for recommendation.
    """

    def __init__(
        self,
        llm_service: LLMService | None = None,
        lp_service: LpService | None = None,
    ) -> None:
        """
        Initialize vision service.

        Args:
            llm_service: LLM service for theme extraction
            lp_service: LP service for recommendations
        """
        self.llm_service = llm_service
        self.lp_service = lp_service
        logger.info("LifePathVisionService initialized")

    async def capture_vision(self, user_uid: str, vision_statement: str) -> Result[VisionCapture]:
        """
        Extract themes from user's vision statement.

        Uses LLM to parse the natural language vision into
        structured themes that can be matched to Learning Paths.

        Args:
            user_uid: User identifier
            vision_statement: User's vision in their own words

        Returns:
            Result[VisionCapture] with extracted themes
        """
        logger.info(f"Capturing vision for user {user_uid}")
        start_time = time.time()

        if not vision_statement or len(vision_statement.strip()) < 10:
            return Result.fail(
                Errors.validation(
                    "Vision statement must be at least 10 characters",
                    field="vision_statement",
                )
            )

        # Extract themes using LLM or fallback
        if self.llm_service:
            themes_result = await self._extract_themes_with_llm(vision_statement)
        else:
            # Fallback to keyword extraction
            themes_result = self._extract_themes_keywords(vision_statement)

        if themes_result.is_error:
            return Result.fail(themes_result.expect_error())

        themes = themes_result.value
        processing_time = int((time.time() - start_time) * 1000)

        vision_capture = VisionCapture(
            user_uid=user_uid,
            vision_statement=vision_statement,
            themes=tuple(themes),
            llm_model=self.llm_service.config.model_name if self.llm_service else None,
            processing_time_ms=processing_time,
        )

        logger.info(
            f"Vision captured for {user_uid}: {len(themes)} themes extracted",
            extra={"themes": [t.theme for t in themes]},
        )

        return Result.ok(vision_capture)

    async def _extract_themes_with_llm(self, vision_statement: str) -> Result[list[VisionTheme]]:
        """
        Extract themes using LLM.

        Prompts the LLM to identify key themes and aspirations
        from the user's vision statement.
        """
        if not self.llm_service:
            return Result.fail(
                Errors.system("LLM service not available", operation="extract_themes")
            )

        prompt = f"""Analyze this life vision statement and extract 3-7 key themes.
For each theme, provide:
- The theme keyword (1-2 words)
- A brief context from the original statement

Vision: "{vision_statement}"

Return themes as a JSON array like:
[
  {{"theme": "leadership", "context": "become a technical leader"}},
  {{"theme": "mindfulness", "context": "mindful approach"}}
]

Focus on actionable aspirations, not generic words."""

        try:
            response = await self.llm_service.generate(prompt)
            if response.error:
                return Result.fail(
                    Errors.integration("llm", f"LLM extraction failed: {response.error}")
                )

            # Parse LLM response
            import json

            themes_data = json.loads(response.content)
            themes = []
            for t in themes_data:
                theme_str = t.get("theme", "").lower().strip()
                category = self._categorize_theme(theme_str)
                themes.append(
                    VisionTheme(
                        theme=theme_str,
                        category=category,
                        confidence=0.9,  # LLM extraction has high confidence
                        context=t.get("context"),
                    )
                )
            return Result.ok(themes)

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            # Fall back to keyword extraction
            return self._extract_themes_keywords(vision_statement)
        except Exception as e:
            logger.error(f"LLM theme extraction failed: {e}")
            return Result.fail(
                Errors.system(f"Theme extraction failed: {e}", operation="extract_themes")
            )

    def _extract_themes_keywords(self, vision_statement: str) -> Result[list[VisionTheme]]:
        """
        Extract themes using keyword matching (fallback).

        Simple approach: find known keywords in the vision statement.
        """
        themes = []
        vision_lower = vision_statement.lower()

        for keyword, category in THEME_CATEGORY_MAPPING.items():
            if keyword in vision_lower:
                themes.append(
                    VisionTheme(
                        theme=keyword,
                        category=category,
                        confidence=0.7,  # Lower confidence for keyword match
                        context=None,
                    )
                )

        # Deduplicate by theme keyword
        seen = set()
        unique_themes = []
        for t in themes:
            if t.theme not in seen:
                seen.add(t.theme)
                unique_themes.append(t)

        if not unique_themes:
            # Extract any noun-like words as fallback
            words = vision_statement.split()
            for word in words:
                clean = word.lower().strip(".,!?")
                if len(clean) > 4 and clean not in {"want", "become", "like", "would", "could"}:
                    unique_themes.append(
                        VisionTheme(
                            theme=clean,
                            category=ThemeCategory.PERSONAL_GROWTH,
                            confidence=0.5,
                        )
                    )
                    if len(unique_themes) >= 5:
                        break

        return Result.ok(unique_themes)

    def _categorize_theme(self, theme: str) -> ThemeCategory:
        """Map a theme keyword to its category."""
        theme_lower = theme.lower()
        return THEME_CATEGORY_MAPPING.get(theme_lower, ThemeCategory.PERSONAL_GROWTH)

    async def recommend_learning_paths(
        self, themes: list[str], limit: int = 5
    ) -> Result[list[LpRecommendation]]:
        """
        Find Learning Paths that match the extracted vision themes.

        Args:
            themes: List of theme keywords
            limit: Maximum recommendations to return

        Returns:
            Result[list[LpRecommendation]] sorted by match score
        """
        if not self.lp_service:
            return Result.fail(
                Errors.system(
                    "LP service not available",
                    operation="recommend_learning_paths",
                )
            )

        logger.info(f"Recommending LPs for themes: {themes}")

        # Search LPs using theme keywords
        search_query = " ".join(themes)
        search_result = await self.lp_service.search.search(query=search_query, limit=limit * 2)

        if search_result.is_error:
            return Result.fail(search_result.expect_error())

        lps = search_result.value
        recommendations = []

        for lp in lps:
            # Calculate match score based on how many themes appear in LP
            lp_description = lp.description or ""
            lp_text = f"{lp.title} {lp_description} {' '.join(lp.outcomes)}".lower()
            matching = [t for t in themes if t.lower() in lp_text]
            match_score = len(matching) / len(themes) if themes else 0

            recommendations.append(
                LpRecommendation(
                    lp_uid=lp.uid,
                    lp_name=lp.title,
                    match_score=match_score,
                    matching_themes=tuple(matching),
                    lp_domain=lp.domain.value if lp.domain else None,
                )
            )

        def get_match_score(rec: LpRecommendation) -> float:
            return rec.match_score

        # Sort by match score descending
        recommendations.sort(key=get_match_score, reverse=True)

        return Result.ok(recommendations[:limit])

    async def calculate_word_action_alignment(
        self, vision_themes: list[str], user_context: UserContext
    ) -> Result[WordActionAlignment]:
        """
        Measure alignment between user's stated WORDS and actual ACTIONS.

        This is the core bridge that answers:
        "Are you LIVING what you SAID?"

        Args:
            vision_themes: Themes extracted from user's vision statement
            user_context: User's actual behavior data

        Returns:
            Result[WordActionAlignment] with gap analysis
        """
        logger.info(f"Calculating word-action alignment for {user_context.user_uid}")

        # Extract "action themes" from UserContext
        action_themes = self._extract_action_themes(user_context)

        # Calculate overlap
        vision_set = set(t.lower() for t in vision_themes)
        action_set = set(t.lower() for t in action_themes)

        matched = vision_set & action_set
        missing_in_actions = vision_set - action_set
        unexpected = action_set - vision_set

        # Calculate alignment score
        if not vision_set:
            alignment_score = 0.0
        else:
            alignment_score = len(matched) / len(vision_set)

        # Generate insights
        insights = []
        recommendations = []

        if missing_in_actions:
            for theme in list(missing_in_actions)[:3]:
                insights.append(
                    f"Your vision mentions '{theme}' but it's not reflected in your activities"
                )
                recommendations.append(f"Consider creating habits or goals related to '{theme}'")

        if unexpected and len(unexpected) > len(matched):
            insights.append(
                "Your activities show priorities not mentioned in your vision statement"
            )
            recommendations.append(
                "Consider updating your vision to reflect your actual priorities"
            )

        if alignment_score >= 0.8:
            insights.append("Excellent alignment! Your actions reflect your stated vision")
        elif alignment_score >= 0.5:
            insights.append("Good progress aligning actions with vision")
        else:
            insights.append("Significant gap between your stated vision and daily actions")

        return Result.ok(
            WordActionAlignment(
                user_uid=user_context.user_uid,
                vision_themes=tuple(vision_themes),
                action_themes=tuple(action_themes),
                alignment_score=alignment_score,
                matched_themes=tuple(matched),
                missing_in_actions=tuple(missing_in_actions),
                unexpected_actions=tuple(unexpected),
                insights=tuple(insights),
                recommendations=tuple(recommendations),
            )
        )

    def _extract_action_themes(self, context: UserContext) -> list[str]:
        """
        Extract themes from user's actual behavior (UserContext).

        Maps UserContext fields to theme keywords.
        """
        themes = []

        # Check habits for lifestyle themes
        if context.habit_streaks:
            for habit_name in context.habit_streaks:
                name_lower = habit_name.lower()
                if "meditat" in name_lower or "mindful" in name_lower:
                    themes.append("mindfulness")
                if "exercis" in name_lower or "workout" in name_lower:
                    themes.append("health")
                if "read" in name_lower or "learn" in name_lower:
                    themes.append("learning")
                if "code" in name_lower or "program" in name_lower:
                    themes.append("technical")

        # Check goals for aspiration themes
        if context.active_goal_uids:
            # Would need to fetch goal details to extract themes
            themes.append("goal-driven")

        # Check knowledge mastery
        if context.mastered_knowledge_uids:
            themes.append("knowledge")
            themes.append("mastery")

        # Check principle alignment
        if context.core_principle_uids:
            themes.append("values")

        return list(set(themes))
