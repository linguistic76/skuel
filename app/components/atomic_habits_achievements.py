"""
Phase 3: Achievement Badge System - Gamification for Atomic Habits

This module implements achievement badges that recognize user milestones in their
habit system journey. Based on James Clear's philosophy that "every action is a vote
for who you want to become," badges celebrate meaningful progress markers.

Badge Categories:
1. Identity Establishment - 50 votes cast for an identity
2. System Excellence - High system strength (90%+)
3. Consistency - Streaks and perfect weeks
4. Velocity - High habit velocity (100+)
5. Mastery - Long-term sustained performance

All badges include:
- Visual icon/emoji
- Title and description
- Unlock criteria
- Progress tracking
- Celebration modal on unlock
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, ClassVar

from fasthtml.common import H2, H3, P

from core.ui.daisy_components import Button, Card, CardBody, Div, Label, Progress, Span


class BadgeCategory(str, Enum):
    """Badge categories for organization."""

    IDENTITY = "identity"
    SYSTEM = "system"
    CONSISTENCY = "consistency"
    VELOCITY = "velocity"
    MASTERY = "mastery"


@dataclass(frozen=True)
class Badge:
    """Achievement badge definition."""

    uid: str
    title: str
    description: str
    category: BadgeCategory
    icon: str  # Emoji
    unlock_criteria: str
    points: int  # Gamification points value

    # Progress tracking
    current_value: float = 0.0
    target_value: float = 100.0
    is_unlocked: bool = False
    unlock_date: date | None = None

    def progress_percentage(self) -> float:
        """Calculate progress toward unlocking this badge."""
        if self.is_unlocked:
            return 100.0
        if self.target_value == 0:
            return 0.0
        return min((self.current_value / self.target_value) * 100, 100.0)

    def progress_display(self) -> str:
        """Human-readable progress display."""
        if self.is_unlocked:
            return "Unlocked"
        return f"{int(self.current_value)}/{int(self.target_value)}"

    def rarity_tier(self) -> str:
        """Rarity tier based on points value."""
        if self.points >= 500:
            return "legendary"
        elif self.points >= 300:
            return "epic"
        elif self.points >= 150:
            return "rare"
        else:
            return "common"

    def rarity_color(self) -> str:
        """Color for rarity tier."""
        colors = {
            "legendary": "#FFD700",  # Gold
            "epic": "#9B59B6",  # Purple
            "rare": "#3498DB",  # Blue
            "common": "#95A5A6",  # Gray
        }
        return colors.get(self.rarity_tier(), "#95A5A6")


class AtomicHabitsBadges:
    """Achievement badge definitions and rendering."""

    # Badge registry with unlock criteria
    BADGE_DEFINITIONS: ClassVar[dict[str, dict[str, Any]]] = {
        # Identity Badges
        "identity_established": {
            "title": "Identity Established",
            "description": "Cast 50 votes for a single identity - you've become who you wanted to be",
            "category": BadgeCategory.IDENTITY,
            "icon": "🎯",
            "unlock_criteria": "50 identity votes for one identity",
            "points": 200,
        },
        "multi_identity": {
            "title": "Renaissance Person",
            "description": "Established 3 different identities simultaneously",
            "category": BadgeCategory.IDENTITY,
            "icon": "🌟",
            "unlock_criteria": "3 identities with 50+ votes each",
            "points": 500,
        },
        "identity_master": {
            "title": "Identity Master",
            "description": "Cast 200 votes for a single identity - absolute mastery",
            "category": BadgeCategory.IDENTITY,
            "icon": "👑",
            "unlock_criteria": "200 identity votes for one identity",
            "points": 600,
        },
        # System Excellence Badges
        "system_architect": {
            "title": "System Architect",
            "description": "Achieved 90%+ system strength for a goal",
            "category": BadgeCategory.SYSTEM,
            "icon": "🏗️",
            "unlock_criteria": "90%+ system strength",
            "points": 250,
        },
        "perfect_system": {
            "title": "Perfect System",
            "description": "Achieved 100% system strength - flawless design and execution",
            "category": BadgeCategory.SYSTEM,
            "icon": "💎",
            "unlock_criteria": "100% system strength",
            "points": 500,
        },
        "multi_system": {
            "title": "Systems Thinker",
            "description": "Maintain 85%+ system strength across 5 active goals",
            "category": BadgeCategory.SYSTEM,
            "icon": "🧠",
            "unlock_criteria": "5 goals with 85%+ system strength",
            "points": 400,
        },
        # Consistency Badges
        "perfect_week": {
            "title": "Perfect Week",
            "description": "Completed all essential habits for 7 consecutive days",
            "category": BadgeCategory.CONSISTENCY,
            "icon": "✨",
            "unlock_criteria": "7-day perfect completion streak",
            "points": 150,
        },
        "consistency_champion": {
            "title": "Consistency Champion",
            "description": "30-day streak of never missing an essential habit",
            "category": BadgeCategory.CONSISTENCY,
            "icon": "🔥",
            "unlock_criteria": "30-day perfect streak",
            "points": 300,
        },
        "century_club": {
            "title": "Century Club",
            "description": "100-day streak of consistent essential habit completion",
            "category": BadgeCategory.CONSISTENCY,
            "icon": "💯",
            "unlock_criteria": "100-day perfect streak",
            "points": 600,
        },
        "unbreakable": {
            "title": "Unbreakable",
            "description": "365-day streak - a full year of unwavering consistency",
            "category": BadgeCategory.CONSISTENCY,
            "icon": "⚡",
            "unlock_criteria": "365-day perfect streak",
            "points": 1000,
        },
        # Velocity Badges
        "velocity_champion": {
            "title": "Velocity Champion",
            "description": "Achieved 100+ habit velocity in a single week",
            "category": BadgeCategory.VELOCITY,
            "icon": "🚀",
            "unlock_criteria": "100+ weekly velocity",
            "points": 200,
        },
        "velocity_master": {
            "title": "Velocity Master",
            "description": "Maintained 150+ velocity for 4 consecutive weeks",
            "category": BadgeCategory.VELOCITY,
            "icon": "⚡",
            "unlock_criteria": "150+ velocity for 4 weeks",
            "points": 400,
        },
        # Mastery Badges
        "habit_sculptor": {
            "title": "Habit Sculptor",
            "description": "Designed 10 habits with cue-routine-reward loops",
            "category": BadgeCategory.MASTERY,
            "icon": "🎨",
            "unlock_criteria": "10 well-designed habits",
            "points": 150,
        },
        "goal_achiever": {
            "title": "Goal Achiever",
            "description": "Achieved a goal through systematic habit execution",
            "category": BadgeCategory.MASTERY,
            "icon": "🏆",
            "unlock_criteria": "1 goal achieved via habits",
            "points": 300,
        },
        "master_achiever": {
            "title": "Master Achiever",
            "description": "Achieved 5 goals through systematic habit execution",
            "category": BadgeCategory.MASTERY,
            "icon": "🌟",
            "unlock_criteria": "5 goals achieved via habits",
            "points": 800,
        },
    }

    @staticmethod
    def create_badge(
        badge_id: str,
        current_value: float = 0.0,
        is_unlocked: bool = False,
        unlock_date: date | None = None,
    ) -> Badge:
        """Create a badge instance with progress tracking."""
        definition = AtomicHabitsBadges.BADGE_DEFINITIONS.get(badge_id, {})

        return Badge(
            uid=badge_id,
            title=definition.get("title", "Unknown Badge"),
            description=definition.get("description", ""),
            category=definition.get("category", BadgeCategory.MASTERY),
            icon=definition.get("icon", "🏅"),
            unlock_criteria=definition.get("unlock_criteria", ""),
            points=definition.get("points", 100),
            current_value=current_value,
            target_value=AtomicHabitsBadges._get_target_value(badge_id),
            is_unlocked=is_unlocked,
            unlock_date=unlock_date,
        )

    @staticmethod
    def _get_target_value(badge_id: str) -> float:
        """Get target value for badge unlock."""
        targets = {
            "identity_established": 50.0,
            "multi_identity": 3.0,
            "identity_master": 200.0,
            "system_architect": 90.0,
            "perfect_system": 100.0,
            "multi_system": 5.0,
            "perfect_week": 7.0,
            "consistency_champion": 30.0,
            "century_club": 100.0,
            "unbreakable": 365.0,
            "velocity_champion": 100.0,
            "velocity_master": 4.0,
            "habit_sculptor": 10.0,
            "goal_achiever": 1.0,
            "master_achiever": 5.0,
        }
        return targets.get(badge_id, 100.0)

    @staticmethod
    def render_badge_showcase(user_badges: list[Badge], show_locked: bool = True) -> Div:
        """Render complete badge showcase with categories."""

        # Group badges by category
        by_category: dict[BadgeCategory, list[Badge]] = {}
        for badge in user_badges:
            if badge.category not in by_category:
                by_category[badge.category] = []
            by_category[badge.category].append(badge)

        # Category display order and titles
        category_info = {
            BadgeCategory.IDENTITY: (
                "🎯 Identity",
                "Badges for establishing and mastering identities",
            ),
            BadgeCategory.SYSTEM: ("🏗️ Systems", "Badges for building excellent habit systems"),
            BadgeCategory.CONSISTENCY: ("🔥 Consistency", "Badges for unwavering habit execution"),
            BadgeCategory.VELOCITY: ("🚀 Velocity", "Badges for high-performance habit completion"),
            BadgeCategory.MASTERY: ("🏆 Mastery", "Badges for overall achievement excellence"),
        }

        # Build showcase sections
        sections = []
        for category in [
            BadgeCategory.IDENTITY,
            BadgeCategory.SYSTEM,
            BadgeCategory.CONSISTENCY,
            BadgeCategory.VELOCITY,
            BadgeCategory.MASTERY,
        ]:
            if category not in by_category:
                continue

            title, subtitle = category_info[category]
            badges = by_category[category]

            # Filter locked badges if requested
            if not show_locked:
                badges = [b for b in badges if b.is_unlocked]

            if not badges:
                continue

            # Render category section
            badge_cards = [AtomicHabitsBadges.render_badge_card(badge) for badge in badges]

            sections.append(
                Div(
                    H3(title, cls="text-xl font-bold mb-2"),
                    P(subtitle, cls="text-sm text-gray-600 mb-4"),
                    Div(
                        *badge_cards,
                        cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8",
                    ),
                    cls="mb-6",
                )
            )

        # Calculate total stats
        total_unlocked = sum(1 for b in user_badges if b.is_unlocked)
        total_points = sum(b.points for b in user_badges if b.is_unlocked)
        total_badges = len(user_badges)

        return Div(
            H2("🏅 Achievement Showcase", cls="text-2xl font-bold mb-4"),
            # Stats summary
            Card(
                CardBody(
                    Div(
                        Div(
                            Span(str(total_unlocked), cls="text-3xl font-bold text-blue-600"),
                            P(f"/ {total_badges} Badges", cls="text-sm text-gray-600"),
                            cls="text-center",
                        ),
                        Div(
                            Span(str(total_points), cls="text-3xl font-bold text-yellow-600"),
                            P("Points", cls="text-sm text-gray-600"),
                            cls="text-center",
                        ),
                        Div(
                            Span(
                                f"{(total_unlocked / total_badges * 100):.0f}%",
                                cls="text-3xl font-bold text-green-600",
                            ),
                            P("Completion", cls="text-sm text-gray-600"),
                            cls="text-center",
                        ),
                        cls="flex justify-around items-center",
                    ),
                ),
                cls="mb-6",
            ),
            # Toggle for locked badges
            Div(
                Label("Show locked badges", cls="text-sm font-medium mr-2"),
                Button(
                    "Toggle",
                    cls="btn btn-sm btn-secondary",
                    hx_get="/badges/showcase?show_locked=" + ("false" if show_locked else "true"),
                    hx_target="#badge-showcase",
                ),
                cls="flex items-center justify-end mb-4",
            ),
            # Badge sections by category
            *sections,
            cls="p-6",
        )

    @staticmethod
    def render_badge_card(badge: Badge) -> Card:
        """Render individual badge card with progress."""

        # Opacity and styling for locked badges
        locked_opacity = "opacity-50" if not badge.is_unlocked else ""

        # Rarity border color
        rarity_border = "border-l-4"
        f"border-l-[{badge.rarity_color()}]"

        # Progress bar for locked badges
        progress_section = None
        if not badge.is_unlocked:
            progress_section = Div(
                P(f"Progress: {badge.progress_display()}", cls="text-xs text-gray-600 mb-1"),
                Progress(
                    value=int(badge.progress_percentage()),
                    cls="progress progress-primary w-full h-2",
                ),
                cls="mt-3",
            )

        # Unlock date for unlocked badges
        unlock_info = None
        if badge.is_unlocked and badge.unlock_date:
            unlock_info = P(
                f"Unlocked: {badge.unlock_date.strftime('%b %d, %Y')}",
                cls="text-xs text-green-600 mt-2",
            )

        return Card(
            CardBody(
                # Icon and rarity indicator
                Div(
                    Span(badge.icon, cls=f"text-4xl {locked_opacity}"),
                    Span(
                        badge.rarity_tier().upper(),
                        cls="text-xs font-bold px-2 py-1 rounded",
                        style=f"background-color: {badge.rarity_color()}; color: white;",
                    ),
                    cls="flex justify-between items-start mb-3",
                ),
                # Title and description
                H3(badge.title, cls=f"font-bold text-lg mb-2 {locked_opacity}"),
                P(badge.description, cls=f"text-sm text-gray-600 mb-2 {locked_opacity}"),
                P(f"📋 {badge.unlock_criteria}", cls=f"text-xs text-gray-500 {locked_opacity}"),
                # Points value
                Div(
                    Span("⭐", cls="text-yellow-500"),
                    Span(f"{badge.points} points", cls=f"text-sm font-medium {locked_opacity}"),
                    cls="flex items-center gap-2 mt-2",
                ),
                # Progress or unlock date
                progress_section if progress_section else unlock_info,
            ),
            cls=f"hover:shadow-lg transition-shadow {rarity_border}",
        )

    @staticmethod
    def render_badge_unlock_celebration(badge: Badge) -> Div:
        """Celebration modal shown when badge is unlocked."""

        return Div(
            Div(
                Div(
                    # Animated badge icon
                    Div(Span(badge.icon, cls="text-8xl animate-bounce"), cls="text-center mb-6"),
                    # Achievement announcement
                    H2("🎉 Achievement Unlocked!", cls="text-3xl font-bold text-center mb-4"),
                    # Badge title with rarity
                    Div(
                        H3(badge.title, cls="text-2xl font-bold mb-2"),
                        Span(
                            badge.rarity_tier().upper(),
                            cls="text-sm font-bold px-3 py-1 rounded",
                            style=f"background-color: {badge.rarity_color()}; color: white;",
                        ),
                        cls="flex flex-col items-center mb-4",
                    ),
                    # Description
                    P(badge.description, cls="text-center text-gray-700 mb-6"),
                    # Points earned
                    Card(
                        CardBody(
                            Div(
                                Span("⭐", cls="text-4xl text-yellow-500"),
                                Div(
                                    P(
                                        f"+{badge.points} Points",
                                        cls="text-2xl font-bold text-yellow-600",
                                    ),
                                    P("Added to your total", cls="text-sm text-gray-600"),
                                    cls="text-center",
                                ),
                                cls="flex items-center justify-center gap-4",
                            ),
                        ),
                        cls="bg-yellow-50 mb-6",
                    ),
                    # Share buttons
                    Div(
                        Button("Share Achievement", cls="btn btn-primary btn-wide mb-2"),
                        Button(
                            "View All Badges",
                            cls="btn btn-secondary btn-wide",
                            hx_get="/badges/showcase",
                            hx_target="#main-content",
                        ),
                        cls="flex flex-col items-center gap-2",
                    ),
                    # Close button
                    Button(
                        "✕",
                        cls="btn btn-sm btn-circle absolute right-2 top-2",
                        onclick="document.getElementById('badge-celebration-modal').close()",
                    ),
                    cls="p-8 max-w-md",
                ),
                cls="modal-box",
            ),
            id="badge-celebration-modal",
            cls="modal modal-open",
        )

    @staticmethod
    def render_badge_progress_widget(near_unlock_badges: list[Badge], limit: int = 3) -> Div:
        """Compact widget showing badges close to unlocking."""

        # Sort by progress percentage, show top N
        def get_progress_percentage(badge) -> Any:
            return badge.progress_percentage()

        sorted_badges = sorted(
            [b for b in near_unlock_badges if not b.is_unlocked],
            key=get_progress_percentage,
            reverse=True,
        )[:limit]

        if not sorted_badges:
            return Div(
                P("No badges in progress", cls="text-sm text-gray-500 text-center py-4"),
                cls="bg-gray-50 rounded-lg",
            )

        badge_items = [
            Div(
                Div(
                    Span(badge.icon, cls="text-2xl"),
                    Div(
                        P(badge.title, cls="font-medium text-sm"),
                        P(badge.progress_display(), cls="text-xs text-gray-600"),
                        cls="flex-1",
                    ),
                    cls="flex items-center gap-3 mb-2",
                ),
                Progress(
                    value=int(badge.progress_percentage()),
                    cls="progress progress-primary w-full h-2",
                ),
                cls="mb-4 last:mb-0",
            )
            for badge in sorted_badges
        ]

        return Card(
            CardBody(
                H3("🎯 Next Achievements", cls="font-bold mb-4"),
                *badge_items,
                Button(
                    "View All Badges",
                    cls="btn btn-sm btn-secondary w-full mt-4",
                    hx_get="/badges/showcase",
                    hx_target="#main-content",
                ),
            ),
            cls="bg-gradient-to-br from-blue-50 to-purple-50",
        )

    @staticmethod
    def calculate_badge_progress(user_data: dict) -> list[Badge]:
        """
        Calculate current badge progress based on user data.

        Expected user_data structure:
        {
            "identity_votes": {"writer": 35, "athlete": 60, "learner": 25},
            "system_strengths": [92, 88, 95, 78],  # All goal system strengths
            "perfect_streak_days": 45,
            "weekly_velocities": [120, 115, 130, 125],  # Last 4 weeks
            "designed_habits_count": 8,
            "goals_achieved_count": 2
        }
        """
        badges = []

        identity_votes = user_data.get("identity_votes", {})
        system_strengths = user_data.get("system_strengths", [])
        perfect_streak = user_data.get("perfect_streak_days", 0)
        velocities = user_data.get("weekly_velocities", [])
        designed_habits = user_data.get("designed_habits_count", 0)
        goals_achieved = user_data.get("goals_achieved_count", 0)

        # Identity badges
        max_identity_votes = max(identity_votes.values()) if identity_votes else 0
        identity_count = sum(1 for v in identity_votes.values() if v >= 50)

        badges.append(
            AtomicHabitsBadges.create_badge(
                "identity_established",
                current_value=max_identity_votes,
                is_unlocked=max_identity_votes >= 50,
                unlock_date=date.today() if max_identity_votes >= 50 else None,
            )
        )

        badges.append(
            AtomicHabitsBadges.create_badge(
                "multi_identity", current_value=identity_count, is_unlocked=identity_count >= 3
            )
        )

        badges.append(
            AtomicHabitsBadges.create_badge(
                "identity_master",
                current_value=max_identity_votes,
                is_unlocked=max_identity_votes >= 200,
            )
        )

        # System badges
        max_system_strength = max(system_strengths) if system_strengths else 0
        high_systems_count = sum(1 for s in system_strengths if s >= 85)

        badges.append(
            AtomicHabitsBadges.create_badge(
                "system_architect",
                current_value=max_system_strength,
                is_unlocked=max_system_strength >= 90,
            )
        )

        badges.append(
            AtomicHabitsBadges.create_badge(
                "perfect_system",
                current_value=max_system_strength,
                is_unlocked=max_system_strength >= 100,
            )
        )

        badges.append(
            AtomicHabitsBadges.create_badge(
                "multi_system",
                current_value=high_systems_count,
                is_unlocked=high_systems_count >= 5,
            )
        )

        # Consistency badges
        badges.append(
            AtomicHabitsBadges.create_badge(
                "perfect_week", current_value=perfect_streak, is_unlocked=perfect_streak >= 7
            )
        )

        badges.append(
            AtomicHabitsBadges.create_badge(
                "consistency_champion",
                current_value=perfect_streak,
                is_unlocked=perfect_streak >= 30,
            )
        )

        badges.append(
            AtomicHabitsBadges.create_badge(
                "century_club", current_value=perfect_streak, is_unlocked=perfect_streak >= 100
            )
        )

        badges.append(
            AtomicHabitsBadges.create_badge(
                "unbreakable", current_value=perfect_streak, is_unlocked=perfect_streak >= 365
            )
        )

        # Velocity badges
        max_velocity = max(velocities) if velocities else 0
        sustained_velocity_weeks = sum(1 for v in velocities if v >= 150)

        badges.append(
            AtomicHabitsBadges.create_badge(
                "velocity_champion", current_value=max_velocity, is_unlocked=max_velocity >= 100
            )
        )

        badges.append(
            AtomicHabitsBadges.create_badge(
                "velocity_master",
                current_value=sustained_velocity_weeks,
                is_unlocked=sustained_velocity_weeks >= 4,
            )
        )

        # Mastery badges
        badges.append(
            AtomicHabitsBadges.create_badge(
                "habit_sculptor", current_value=designed_habits, is_unlocked=designed_habits >= 10
            )
        )

        badges.append(
            AtomicHabitsBadges.create_badge(
                "goal_achiever", current_value=goals_achieved, is_unlocked=goals_achieved >= 1
            )
        )

        badges.append(
            AtomicHabitsBadges.create_badge(
                "master_achiever", current_value=goals_achieved, is_unlocked=goals_achieved >= 5
            )
        )

        return badges
