"""
Phase 3.2: Animated Transitions - Visual Feedback for Atomic Habits

This module provides animated transitions and visual feedback for key habit events.
Animations reinforce positive behaviors and make the system feel responsive and engaging.

Animation Categories:
1. Identity Votes - Visual feedback when casting votes toward identity
2. System Strength - Animated meter fills and updates
3. Velocity Tracking - Smooth chart transitions
4. Badge Unlocks - Celebration animations
5. Habit Completion - Confetti and success feedback

All animations use CSS transitions and HTMX for smooth, performant updates.
"""

from fasthtml.common import P, Style

from ui.daisy_components import Div, Span


class AtomicHabitsAnimations:
    """Animation definitions and components for Atomic Habits UI."""

    @staticmethod
    def get_animation_styles() -> Style:
        """
        CSS animation definitions for Atomic Habits.

        Include this in the page head to enable animations.
        """
        css = """
        /* ============================================
           IDENTITY VOTE ANIMATIONS
           ============================================ */

        @keyframes vote-cast {
            0% {
                transform: scale(1);
                opacity: 1;
            }
            50% {
                transform: scale(1.2);
                opacity: 0.8;
            }
            100% {
                transform: scale(1);
                opacity: 1;
            }
        }

        @keyframes vote-particle {
            0% {
                transform: translateY(0) scale(1);
                opacity: 1;
            }
            100% {
                transform: translateY(-100px) scale(0.5);
                opacity: 0;
            }
        }

        .vote-cast-animation {
            animation: vote-cast 0.6s ease-out;
        }

        .vote-particle {
            animation: vote-particle 1s ease-out forwards;
        }

        /* ============================================
           PROGRESS BAR ANIMATIONS
           ============================================ */

        @keyframes progress-fill {
            0% {
                width: 0%;
            }
        }

        @keyframes progress-pulse {
            0%, 100% {
                opacity: 1;
            }
            50% {
                opacity: 0.6;
            }
        }

        .progress-animated {
            animation: progress-fill 1.5s ease-out;
        }

        .progress-pulse {
            animation: progress-pulse 2s ease-in-out infinite;
        }

        /* ============================================
           SYSTEM STRENGTH METER ANIMATIONS
           ============================================ */

        @keyframes meter-fill {
            0% {
                transform: scaleX(0);
                transform-origin: left;
            }
            100% {
                transform: scaleX(1);
                transform-origin: left;
            }
        }

        @keyframes meter-glow {
            0%, 100% {
                box-shadow: 0 0 5px rgba(59, 130, 246, 0.5);
            }
            50% {
                box-shadow: 0 0 20px rgba(59, 130, 246, 0.8);
            }
        }

        .meter-animated {
            animation: meter-fill 1.2s ease-out, meter-glow 2s ease-in-out infinite;
        }

        /* ============================================
           BADGE UNLOCK ANIMATIONS
           ============================================ */

        @keyframes badge-unlock {
            0% {
                transform: scale(0) rotate(-180deg);
                opacity: 0;
            }
            60% {
                transform: scale(1.2) rotate(10deg);
            }
            100% {
                transform: scale(1) rotate(0deg);
                opacity: 1;
            }
        }

        @keyframes badge-shimmer {
            0% {
                background-position: -1000px 0;
            }
            100% {
                background-position: 1000px 0;
            }
        }

        .badge-unlock {
            animation: badge-unlock 0.8s ease-out;
        }

        .badge-shimmer {
            background: linear-gradient(
                90deg,
                transparent,
                rgba(255, 215, 0, 0.5),
                transparent
            );
            background-size: 1000px 100%;
            animation: badge-shimmer 2s infinite;
        }

        /* ============================================
           HABIT COMPLETION ANIMATIONS
           ============================================ */

        @keyframes checkmark-draw {
            0% {
                stroke-dashoffset: 100;
            }
            100% {
                stroke-dashoffset: 0;
            }
        }

        @keyframes confetti-fall {
            0% {
                transform: translateY(-100vh) rotate(0deg);
                opacity: 1;
            }
            100% {
                transform: translateY(100vh) rotate(720deg);
                opacity: 0;
            }
        }

        .checkmark-animated {
            stroke-dasharray: 100;
            animation: checkmark-draw 0.5s ease-out forwards;
        }

        .confetti {
            animation: confetti-fall 3s ease-in-out forwards;
        }

        /* ============================================
           VELOCITY CHART ANIMATIONS
           ============================================ */

        @keyframes bar-grow {
            0% {
                transform: scaleY(0);
                transform-origin: bottom;
            }
            100% {
                transform: scaleY(1);
                transform-origin: bottom;
            }
        }

        @keyframes line-draw {
            0% {
                stroke-dashoffset: 1000;
            }
            100% {
                stroke-dashoffset: 0;
            }
        }

        .chart-bar {
            animation: bar-grow 0.8s ease-out;
        }

        .chart-line {
            stroke-dasharray: 1000;
            animation: line-draw 1.5s ease-out forwards;
        }

        /* ============================================
           STREAK FIRE ANIMATIONS
           ============================================ */

        @keyframes flame-flicker {
            0%, 100% {
                transform: scaleY(1) scaleX(1);
            }
            25% {
                transform: scaleY(1.1) scaleX(0.95);
            }
            50% {
                transform: scaleY(0.95) scaleX(1.05);
            }
            75% {
                transform: scaleY(1.05) scaleX(0.98);
            }
        }

        @keyframes ember-float {
            0% {
                transform: translateY(0) scale(1);
                opacity: 0.8;
            }
            100% {
                transform: translateY(-50px) scale(0.3);
                opacity: 0;
            }
        }

        .streak-flame {
            animation: flame-flicker 1.5s ease-in-out infinite;
        }

        .streak-ember {
            animation: ember-float 2s ease-out infinite;
        }

        /* ============================================
           CARD REVEAL ANIMATIONS
           ============================================ */

        @keyframes card-slide-in {
            0% {
                transform: translateX(-100%);
                opacity: 0;
            }
            100% {
                transform: translateX(0);
                opacity: 1;
            }
        }

        @keyframes card-fade-in {
            0% {
                opacity: 0;
                transform: translateY(20px);
            }
            100% {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .card-slide-in {
            animation: card-slide-in 0.5s ease-out;
        }

        .card-fade-in {
            animation: card-fade-in 0.6s ease-out;
        }

        /* ============================================
           HTMX TRANSITION HOOKS
           ============================================ */

        .htmx-swapping {
            opacity: 0;
            transition: opacity 0.3s ease-out;
        }

        .htmx-settling {
            opacity: 1;
        }

        .htmx-added {
            animation: card-fade-in 0.5s ease-out;
        }

        /* ============================================
           HOVER INTERACTIONS
           ============================================ */

        .habit-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.1);
            transition: all 0.3s ease-out;
        }

        .badge-card:hover {
            transform: scale(1.05);
            transition: all 0.3s ease-out;
        }

        /* ============================================
           LOADING STATES
           ============================================ */

        @keyframes skeleton-loading {
            0% {
                background-position: -200px 0;
            }
            100% {
                background-position: calc(200px + 100%) 0;
            }
        }

        .skeleton {
            background: linear-gradient(
                90deg,
                #f0f0f0 0px,
                #e0e0e0 40px,
                #f0f0f0 80px
            );
            background-size: 200px 100%;
            animation: skeleton-loading 1.5s infinite;
        }
        """

        return Style(css)

    @staticmethod
    def render_vote_particle(identity: str, vote_number: int) -> Div:
        """
        Render animated particle when identity vote is cast.

        Args:
            identity: The identity being voted for (e.g., "writer")
            vote_number: The vote number (e.g., 35)
        """
        return Div(
            Span(f"+1 vote for '{identity}'", cls="text-sm font-bold text-info vote-particle"),
            cls="absolute top-0 left-1/2 transform -translate-x-1/2 pointer-events-none",
        )

    @staticmethod
    def render_animated_progress_bar(
        current: float, target: float, label: str = "", color: str = "blue"
    ) -> Div:
        """
        Render animated progress bar with smooth fill transition.

        Args:
            current: Current progress value,
            target: Target value,
            label: Optional label for the progress bar,
            color: Color theme (blue, green, purple, etc.)
        """
        percentage = min((current / target) * 100, 100) if target > 0 else 0

        color_classes = {
            "blue": "bg-info",
            "green": "bg-success",
            "purple": "bg-secondary",
            "orange": "bg-warning",
            "red": "bg-error",
        }

        bar_color = color_classes.get(color, "bg-info")

        return Div(
            P(label, cls="text-sm font-medium mb-1") if label else None,
            Div(
                Div(cls=f"{bar_color} h-full progress-animated", style=f"width: {percentage}%"),
                cls="w-full bg-base-200 rounded-full h-3 overflow-hidden",
            ),
            P(f"{int(current)}/{int(target)}", cls="text-xs text-base-content/70 mt-1"),
        )

    @staticmethod
    def render_animated_meter(
        value: float, max_value: float = 100, label: str = "", show_glow: bool = True
    ) -> Div:
        """
        Render animated system strength meter with glow effect.

        Args:
            value: Current meter value (0-100),
            max_value: Maximum value (default 100),
            label: Optional label,
            show_glow: Whether to show glow animation
        """
        percentage = min((value / max_value) * 100, 100)

        # Color based on value
        if percentage >= 90:
            color = "bg-green-500"
        elif percentage >= 70:
            color = "bg-blue-500"
        elif percentage >= 50:
            color = "bg-yellow-500"
        else:
            color = "bg-red-500"

        glow_class = "meter-animated" if show_glow else "meter-fill"

        return Div(
            P(label, cls="text-sm font-bold mb-2") if label else None,
            Div(
                Div(
                    Span(f"{value:.1f}%", cls="text-white text-xs font-bold px-2"),
                    cls=f"{color} h-full flex items-center {glow_class}",
                    style=f"width: {percentage}%",
                ),
                cls="w-full bg-base-200 rounded-lg h-8 overflow-hidden",
            ),
        )

    @staticmethod
    def render_checkmark_animation() -> Div:
        """
        Render animated checkmark SVG for habit completion.
        """
        return Div(
            # SVG checkmark with draw animation
            """
            <svg width="100" height="100" viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="45" fill="none" stroke="#10b981" stroke-width="4"/>
                <path d="M 30 50 L 45 65 L 70 35" fill="none" stroke="#10b981"
                      stroke-width="6" stroke-linecap="round" class="checkmark-animated"/>
            </svg>
            """,
            cls="flex items-center justify-center",
        )

    @staticmethod
    def render_confetti_particle(color: str = "#FFD700") -> Div:
        """
        Render single confetti particle for celebrations.

        Args:
            color: Hex color for the confetti piece
        """
        import random

        # Random horizontal position
        left = random.randint(0, 100)

        # Random animation delay
        delay = random.uniform(0, 1)

        return Div(
            cls="confetti absolute w-3 h-3 rounded-sm",
            style=f"background-color: {color}; left: {left}%; animation-delay: {delay}s;",
        )

    @staticmethod
    def render_confetti_burst(count: int = 30) -> Div:
        """
        Render confetti burst animation for celebrations.

        Args:
            count: Number of confetti pieces
        """
        colors = ["#FFD700", "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8"]

        particles = [
            AtomicHabitsAnimations.render_confetti_particle(color=colors[i % len(colors)])
            for i in range(count)
        ]

        return Div(
            *particles, cls="fixed inset-0 pointer-events-none z-50", id="confetti-container"
        )

    @staticmethod
    def render_streak_flame(streak_days: int) -> Div:
        """
        Render animated flame for streak visualization.

        Args:
            streak_days: Number of consecutive days
        """
        # Flame size based on streak length
        if streak_days >= 100:
            size = "text-6xl"
        elif streak_days >= 30:
            size = "text-5xl"
        elif streak_days >= 7:
            size = "text-4xl"
        else:
            size = "text-3xl"

        return Div(
            Span("🔥", cls=f"{size} streak-flame"),
            P(f"{streak_days} days", cls="text-sm font-bold text-orange-600 mt-2"),
            cls="flex flex-col items-center",
        )

    @staticmethod
    def render_velocity_chart_animated(velocities: list[float], labels: list[str]) -> Div:
        """
        Render animated velocity chart with bar growth animation.

        Args:
            velocities: List of velocity values
            labels: List of labels (e.g., week names)
        """
        max_velocity = max(velocities) if velocities else 100

        bars = []
        for i, (velocity, label) in enumerate(zip(velocities, labels, strict=False)):
            bar_height = (velocity / max_velocity) * 100

            # Stagger animation delays
            delay = i * 0.1

            bars.append(
                Div(
                    Div(
                        Span(f"{velocity:.0f}", cls="text-xs font-bold text-white"),
                        cls="bg-blue-600 chart-bar w-full flex items-end justify-center pb-1",
                        style=f"height: {bar_height}%; animation-delay: {delay}s;",
                    ),
                    P(label, cls="text-xs text-base-content/70 mt-2 text-center"),
                    cls="flex-1 flex flex-col items-stretch",
                )
            )

        return Div(Div(*bars, cls="flex items-end justify-around gap-2 h-48"), cls="w-full")

    @staticmethod
    def render_loading_skeleton(height: str = "h-20") -> Div:
        """
        Render loading skeleton for async content.

        Args:
            height: Tailwind height class
        """
        return Div(cls=f"skeleton rounded-lg {height} w-full")

    @staticmethod
    def get_htmx_animation_config() -> dict[str, str]:
        """
        Get HTMX configuration for smooth transitions.

        Use this in HTMX attributes for animated swaps.
        """
        return {
            "hx-swap": "innerHTML transition:true",
            "hx-swap-oob": "true",
        }
