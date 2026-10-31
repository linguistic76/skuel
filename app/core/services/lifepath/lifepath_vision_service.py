"""
LifePath Vision Service
========================

Captures user's vision in their own words and extracts actionable themes.

This service bridges:
- User's WORDS (vision statement) -> System understanding (themes)
- Themes -> Learning Path recommendations

Flow:
1. User expresses vision: "I want to become a mindful technical leader"
2. Themes are extracted: ["leadership", "mindfulness", "technology", "growth"] —
   by the LLM in FULL tier, by keyword matching in CORE and whenever the LLM's
   reply yields no usable theme
3. Themes match to LP candidates: [lp.mindful-engineer, lp.tech-leadership]
4. User confirms designation or refines vision

Philosophy:
    "The user's vision is understood via the words user uses to communicate"
"""

from __future__ import annotations

import asyncio
import json
import time
from itertools import islice
from typing import TYPE_CHECKING

from core.constants import PromptInput
from core.models.enums.lifepath_enums import ThemeCategory
from core.models.type_hints import UserUID
from core.prompts import PROMPT_REGISTRY
from core.utils.llm_json import parse_json_reply
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.text_truncation import truncate_to_budget

from .lifepath_types import (
    LpRecommendation,
    VisionCapture,
    VisionTheme,
    WordActionAlignment,
)

if TYPE_CHECKING:
    from core.models.pathways.learning_path import LearningPath
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


def _usable(themes: list[VisionTheme]) -> list[VisionTheme]:
    """Each theme once, where it first appears, and no blank one."""
    seen: set[str] = set()
    usable = []
    for theme in themes:
        if theme.theme and theme.theme not in seen:
            seen.add(theme.theme)
            usable.append(theme)
    return usable


class LifePathVisionService:
    """
    Service for capturing and analyzing user vision statements.

    Extracts themes from a natural-language vision statement (the LLM in FULL
    tier, keyword matching in CORE), then matches the themes to Learning Paths.
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

    async def capture_vision(
        self, user_uid: UserUID, vision_statement: str
    ) -> Result[VisionCapture]:
        """
        Extract the themes of the user's vision statement.

        FULL tier asks the LLM; CORE matches keywords. Whatever keeps the LLM
        from answering a usable theme (the provider failed, the reply is not
        JSON or not an array of themes, it names no theme) falls back to the
        keywords, so extraction never refuses a vision: only a statement under
        10 characters is refused. Either extractor's themes are kept once each,
        and a blank one not at all.

        Args:
            user_uid: User identifier
            vision_statement: User's vision in their own words

        Returns:
            Result[VisionCapture] with the extracted themes; ``llm_model`` names
            the model only when the LLM's themes were kept
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

        themes: list[VisionTheme] = []
        llm_model: str | None = None
        if self.llm_service:
            extracted = await self._extract_themes_with_llm(self.llm_service, vision_statement)
            themes = _usable(extracted or [])
            if themes:
                llm_model = self.llm_service.config.model_name
            elif extracted is not None:
                logger.warning(
                    "Vision themes fell back to keywords: the LLM's reply named no usable theme"
                )
        if not themes:
            themes = _usable(self._extract_themes_keywords(vision_statement))

        processing_time = int((time.time() - start_time) * 1000)

        vision_capture = VisionCapture(
            user_uid=user_uid,
            vision_statement=vision_statement,
            themes=tuple(themes),
            llm_model=llm_model,
            processing_time_ms=processing_time,
        )

        logger.info(
            f"Vision captured for {user_uid}: {len(themes)} themes extracted",
            extra={"themes": [t.theme for t in themes]},
        )

        return Result.ok(vision_capture)

    async def _extract_themes_with_llm(
        self, llm_service: LLMService, vision_statement: str
    ) -> list[VisionTheme] | None:
        """
        The themes the LLM reads in the vision statement, as it named them.

        None when its reply cannot be read as themes, with the reason logged:
        the provider failed, the reply is not JSON, or the JSON is not an array.
        An array entry that is not an object with a string ``theme`` is skipped.
        """
        prompt = PROMPT_REGISTRY.render(
            "lifepath_vision_themes",
            vision_statement=truncate_to_budget(vision_statement, PromptInput.FIELD_MAX_CHARS),
        )
        response = await llm_service.generate(prompt)
        if response.error:
            logger.warning(
                f"Vision themes fell back to keywords: the LLM failed ({response.error})"
            )
            return None

        try:
            reply = parse_json_reply(response.content)
        except json.JSONDecodeError as e:
            logger.warning(f"Vision themes fell back to keywords: the reply is not JSON ({e})")
            return None
        if not isinstance(reply, list):
            logger.warning(
                "Vision themes fell back to keywords: "
                f"the reply is a JSON {type(reply).__name__}, not an array"
            )
            return None

        themes = []
        for entry in reply:
            if not isinstance(entry, dict) or not isinstance(entry.get("theme"), str):
                continue
            theme = entry["theme"].strip().lower()
            context = entry.get("context")
            themes.append(
                VisionTheme(
                    theme=theme,
                    category=self._categorize_theme(theme),
                    confidence=0.9,  # LLM extraction has high confidence
                    context=context if isinstance(context, str) else None,
                )
            )
        return themes

    def _extract_themes_keywords(self, vision_statement: str) -> list[VisionTheme]:
        """
        Extract themes by keyword matching: CORE tier, and FULL's fallback.

        The known keywords the statement contains; failing any, up to five of
        its longer words.
        """
        vision_lower = vision_statement.lower()
        themes = [
            VisionTheme(
                theme=keyword,
                category=category,
                confidence=0.7,  # Lower confidence for keyword match
            )
            for keyword, category in THEME_CATEGORY_MAPPING.items()
            if keyword in vision_lower
        ]
        if themes:
            return themes

        # No known keyword: the statement's longer words, each once
        words: list[str] = []
        for word in vision_statement.split():
            clean = word.lower().strip(".,!?")
            if (
                len(clean) > 4
                and clean not in {"want", "become", "like", "would", "could"}
                and clean not in words
            ):
                words.append(clean)
                if len(words) >= 5:
                    break
        return [
            VisionTheme(theme=word, category=ThemeCategory.PERSONAL_GROWTH, confidence=0.5)
            for word in words
        ]

    def _categorize_theme(self, theme: str) -> ThemeCategory:
        """Map a theme keyword to its category."""
        theme_lower = theme.lower()
        return THEME_CATEGORY_MAPPING.get(theme_lower, ThemeCategory.PERSONAL_GROWTH)

    async def match_learning_paths(
        self, themes: list[str], limit: int = 5
    ) -> Result[list[LpRecommendation]]:
        """
        Find Learning Paths that match the extracted vision themes.

        Each theme is its own search, and a path any theme finds is a
        candidate: the LP text search matches its query as one phrase, so the
        themes joined into one query would find only a path that holds them
        all, side by side. No themes means no candidates, and no search.

        Args:
            themes: List of theme keywords
            limit: Maximum recommendations to return

        Returns:
            Result[list[LpRecommendation]] sorted by match score; a failed
            search fails the whole read
        """
        if not self.lp_service:
            return Result.fail(
                Errors.system(
                    "LP service not available",
                    operation="match_learning_paths",
                )
            )

        themes = [theme for theme in dict.fromkeys(t.strip() for t in themes) if theme]
        if not themes:
            return Result.ok([])

        logger.info(f"Matching LPs to themes: {themes}")

        lp_search = self.lp_service.search
        search_results = await asyncio.gather(
            *(lp_search.search(query=theme, limit=limit * 2) for theme in themes)
        )
        lps: dict[str, LearningPath] = {}
        for search_result in search_results:
            if search_result.is_error:
                return Result.fail(search_result)
            for found in search_result.value:
                lps.setdefault(found.uid, found)

        recommendations = []

        for lp in lps.values():
            # Calculate match score based on how many themes appear in LP
            lp_description = lp.description or ""
            lp_text = f"{lp.title} {lp_description} {' '.join(lp.outcomes)}".lower()
            matching = [t for t in themes if t.lower() in lp_text]
            match_score = len(matching) / len(themes)

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

    async def calculate_word_action_alignment(  # skuel-lint: disable=SKUEL029 -- facade-delegated: service facade awaits this via delegation (facade uniformity)
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
            for theme in islice(missing_in_actions, 3):
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
