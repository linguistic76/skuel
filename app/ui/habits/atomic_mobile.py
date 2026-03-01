"""
Mobile-Optimized Views - Touch-First Atomic Habits UI

This module provides mobile-optimized views for Atomic Habits, designed for:
- Small screens (320px - 480px width)
- Touch interactions (swipe, tap, hold)
- Thumb-zone accessibility
- Progressive disclosure
- One-handed operation

Design Principles:
1. Today's Focus - Show only what matters right now
2. Progressive Disclosure - Reveal complexity on demand
3. Thumb-Zone First - Critical actions within easy reach
4. Swipe Navigation - Natural gesture-based flow
5. Quick Actions - One-tap completion

All components are responsive and degrade gracefully on desktop.
"""

from datetime import date
from typing import Any

from fasthtml.common import H1, H2, H3, P

from ui.daisy_components import Button, Card, CardBody, Div, Span


class AtomicHabitsMobile:
    """Mobile-optimized UI components for Atomic Habits."""

    @staticmethod
    def render_mobile_dashboard(habits_today: list[dict], stats: dict) -> Div:
        """
        Mobile-optimized dashboard with today's focus.

        Args:
            habits_today: Today's habits to complete
            stats: User stats (streaks, identity progress, etc.)
        """
        return Div(
            # Mobile header with quick stats
            AtomicHabitsMobile._render_mobile_header(stats),
            # Today's habits (swipeable cards)
            AtomicHabitsMobile._render_todays_habits_mobile(habits_today),
            # Quick actions (thumb-zone)
            AtomicHabitsMobile._render_quick_actions_mobile(),
            # Bottom navigation
            AtomicHabitsMobile._render_bottom_nav(),
            cls="min-h-screen bg-base-200 mobile-bottom-nav",  # Safe zone support for iOS
            **{"x-data": "{ swipeIndex: 0 }"},  # Alpine.js for swipe state
        )

    @staticmethod
    def _render_mobile_header(stats: dict) -> Div:
        """Compact mobile header with essential stats."""
        streak_days = stats.get("current_streak", 0)
        completion_today = stats.get("completed_today", 0)
        total_today = stats.get("total_today", 0)

        return Div(
            # Compact header
            Div(
                H1("Today's Habits", cls="text-xl font-bold text-base-content"),
                Span(f"{date.today().strftime('%a, %b %d')}", cls="text-sm text-base-content/70"),
                cls="flex justify-between items-center mb-3",
            ),
            # Progress ring (completion %)
            Div(
                Div(
                    # Circular progress
                    Div(
                        Span(
                            f"{completion_today}/{total_today}",
                            cls="text-2xl font-bold text-blue-600",
                        ),
                        P("completed", cls="text-xs text-base-content/70"),
                        cls="absolute inset-0 flex flex-col items-center justify-center",
                    ),
                    cls="relative w-24 h-24 mx-auto mb-2",
                    style="background: conic-gradient(#3B82F6 0% "
                    + f"{(completion_today / total_today * 100) if total_today > 0 else 0}%"
                    + ", #E5E7EB 0% 100%); border-radius: 50%;",
                ),
                # Streak indicator
                Div(
                    Span("🔥", cls="text-2xl"),
                    Span(f"{streak_days} days", cls="text-sm font-medium text-orange-600"),
                    cls="flex items-center gap-2 justify-center",
                )
                if streak_days > 0
                else None,
                cls="text-center py-4",
            ),
            cls="bg-base-100 p-4 shadow-sm sticky top-0 z-10",
        )

    @staticmethod
    def _render_todays_habits_mobile(habits: list[dict]) -> Div:
        """
        Swipeable habit cards optimized for mobile.

        Args:
            habits: List of today's habits
        """
        if not habits:
            return Div(
                P("No habits for today! 🎉", cls="text-center text-base-content/60 py-12"), cls="px-4"
            )

        habit_cards = []
        for i, habit in enumerate(habits):
            habit_cards.append(AtomicHabitsMobile._render_swipeable_habit_card(habit, index=i))

        return Div(
            # Swipe instruction (first time users)
            Div(
                P("← Swipe to navigate →", cls="text-center text-sm text-base-content/60"),
                cls="mb-2",
                **{"x-show": "swipeIndex === 0", "x-transition": ""},
            ),
            # Card container (swipeable)
            Div(
                *habit_cards,
                cls="relative",
                **{
                    "x-ref": "habitCards",
                    "x-on:touchstart": "handleTouchStart($event)",
                    "x-on:touchend": "handleTouchEnd($event)",
                },
            ),
            # Progress dots
            Div(
                *[
                    Span(
                        cls=f"w-2 h-2 rounded-full {'bg-blue-600' if i == 0 else 'bg-base-300'}",
                        **{
                            "x-bind:class": f"{{'bg-blue-600': swipeIndex === {i}, 'bg-base-300': swipeIndex !== {i}}}"
                        },
                    )
                    for i in range(len(habits))
                ],
                cls="flex justify-center gap-2 mt-4 mb-4",
            ),
            cls="px-4 py-2",
        )

    @staticmethod
    def _render_swipeable_habit_card(habit: dict, index: int) -> Any:
        """
        Single swipeable habit card for mobile.

        Args:
            habit: Habit data
            index: Card index in swipe carousel
        """
        uid = habit.get("uid", "")
        name = habit.get("name", "Unnamed Habit")
        identity = habit.get("reinforces_identity")
        essentiality = habit.get("essentiality", "optional")
        cue = habit.get("cue", "")
        is_completed = habit.get("completed_today", False)

        # Essentiality badge color
        essentiality_colors = {
            "essential": "badge-error",
            "critical": "badge-warning",
            "supporting": "badge-info",
            "optional": "badge-ghost",
        }
        badge_color = essentiality_colors.get(essentiality, "badge-ghost")

        return Card(
            CardBody(
                # Essentiality badge
                Span(
                    essentiality.upper(), cls=f"badge badge-sm {badge_color}"
                ),
                # Habit name
                H2(name, cls="text-xl font-bold text-base-content my-3"),
                # Identity (if applicable)
                (
                    Div(
                        Span("🎯", cls="text-lg"),
                        P(f'"{identity}"', cls="text-sm text-purple-700 italic"),
                        cls="flex items-center gap-2 mb-3 p-2 bg-purple-50 rounded",
                    )
                    if identity
                    else None
                ),
                # Cue reminder
                (
                    Div(
                        Span("💡", cls="text-lg"),
                        P(f"Cue: {cue}", cls="text-sm text-base-content/70"),
                        cls="flex items-center gap-2 mb-4 p-2 bg-yellow-50 rounded",
                    )
                    if cue
                    else None
                ),
                # One-tap completion button (thumb-zone)
                Button(
                    "✓ Complete" if not is_completed else "✓ Completed",
                    cls=f"btn w-full {'btn-success' if not is_completed else 'btn-disabled'} text-lg py-4",
                    hx_post=f"/habits/{uid}/complete",
                    hx_target="#main-content",
                    hx_swap="outerHTML",
                    disabled=is_completed,
                ),
                # Swipe indicator
                Div(
                    P("Swipe for next →", cls="text-xs text-base-content/60 text-center mt-2"),
                    cls="",
                    **{"x-show": f"swipeIndex === {index}"},
                ),
            ),
            cls="shadow-lg mb-4",
            **{
                "x-show": f"swipeIndex === {index}",
                "x-transition:enter": "transition ease-out duration-300",
                "x-transition:enter-start": "opacity-0 transform translate-x-full",
                "x-transition:enter-end": "opacity-100 transform translate-x-0",
                "x-transition:leave": "transition ease-in duration-200",
                "x-transition:leave-start": "opacity-100 transform translate-x-0",
                "x-transition:leave-end": "opacity-0 transform -translate-x-full",
            },
        )

    @staticmethod
    def _render_quick_actions_mobile() -> Div:
        """Quick action buttons in thumb-zone."""
        return Div(
            H3("Quick Actions", cls="text-lg font-semibold mb-3 px-4"),
            Div(
                Button(
                    Div(
                        Span("🏅", cls="text-3xl mb-2"),
                        P("Badges", cls="text-sm font-medium"),
                        cls="text-center",
                    ),
                    cls="btn btn-secondary flex-1 h-24",
                    hx_get="/badges/showcase",
                    hx_target="#main-content",
                ),
                Button(
                    Div(
                        Span("📊", cls="text-3xl mb-2"),
                        P("Analytics", cls="text-sm font-medium"),
                        cls="text-center",
                    ),
                    cls="btn btn-secondary flex-1 h-24",
                    hx_get="/habits/analytics",
                    hx_target="#main-content",
                ),
                Button(
                    Div(
                        Span("➕", cls="text-3xl mb-2"),
                        P("New Habit", cls="text-sm font-medium"),
                        cls="text-center",
                    ),
                    cls="btn btn-primary flex-1 h-24",
                    hx_get="/habits/wizard/step1",
                    hx_target="#modal",
                ),
                cls="grid grid-cols-3 gap-3 px-4",
            ),
        )

    @staticmethod
    def _render_bottom_nav() -> Div:
        """Bottom navigation bar (thumb-zone)."""
        return Div(
            Button(
                Div(Span("🏠", cls="text-2xl"), P("Today", cls="text-xs"), cls="text-center"),
                cls="flex-1 btn btn-ghost",
                hx_get="/habits/mobile",
                hx_target="#main-content",
            ),
            Button(
                Div(Span("📋", cls="text-2xl"), P("All Habits", cls="text-xs"), cls="text-center"),
                cls="flex-1 btn btn-ghost",
                hx_get="/habits",
                hx_target="#main-content",
            ),
            Button(
                Div(Span("🎯", cls="text-2xl"), P("Goals", cls="text-xs"), cls="text-center"),
                cls="flex-1 btn btn-ghost",
                hx_get="/goals",
                hx_target="#main-content",
            ),
            Button(
                Div(Span("👤", cls="text-2xl"), P("Profile", cls="text-xs"), cls="text-center"),
                cls="flex-1 btn btn-ghost",
                hx_get="/profile",
                hx_target="#main-content",
            ),
            cls="fixed bottom-0 left-0 right-0 bg-base-100 border-t border-base-200 flex items-stretch h-16 z-20 shadow-lg",
        )

    @staticmethod
    def render_mobile_habit_detail(habit: dict) -> Div:
        """
        Mobile-optimized habit detail view with progressive disclosure.

        Args:
            habit: Complete habit data
        """
        uid = habit.get("uid", "")
        name = habit.get("name", "Unnamed Habit")
        habit.get("reinforces_identity")
        essentiality = habit.get("essentiality", "optional")
        cue = habit.get("cue", "")
        routine = habit.get("routine", "")
        reward = habit.get("reward", "")
        identity_votes = habit.get("identity_votes_cast", 0)
        current_streak = habit.get("current_streak", 0)

        return Div(
            # Back button
            Button(
                "← Back",
                cls="btn btn-ghost mb-4",
                hx_get="/habits/mobile",
                hx_target="#main-content",
            ),
            # Habit header
            Card(
                CardBody(
                    H1(name, cls="text-2xl font-bold mb-3"),
                    Span(
                        essentiality.upper(),
                        cls="text-xs font-bold px-2 py-1 rounded bg-blue-100 text-blue-700",
                    ),
                ),
                cls="mb-4",
            ),
            # Stats
            Div(
                Card(
                    CardBody(
                        Div(
                            Span("🔥", cls="text-3xl"),
                            Div(
                                P(str(current_streak), cls="text-2xl font-bold text-orange-600"),
                                P("day streak", cls="text-xs text-base-content/70"),
                                cls="text-center",
                            ),
                            cls="flex items-center gap-3",
                        ),
                    ),
                ),
                Card(
                    CardBody(
                        Div(
                            Span("🎯", cls="text-3xl"),
                            Div(
                                P(str(identity_votes), cls="text-2xl font-bold text-purple-600"),
                                P("identity votes", cls="text-xs text-base-content/70"),
                                cls="text-center",
                            ),
                            cls="flex items-center gap-3",
                        ),
                    ),
                ),
                cls="grid grid-cols-2 gap-3 mb-4",
            ),
            # Behavior design (collapsible)
            Card(
                CardBody(
                    Button(
                        Div(
                            H3("Behavior Design", cls="text-lg font-semibold"),
                            Span("▼", cls="text-base-content/60", **{"x-show": "!showBehavior"}),
                            Span("▲", cls="text-base-content/60", **{"x-show": "showBehavior"}),
                            cls="flex justify-between items-center w-full",
                        ),
                        cls="w-full text-left",
                        **{"x-on:click": "showBehavior = !showBehavior"},
                    ),
                    # Collapsible content
                    Div(
                        Div(
                            P("💡 Cue:", cls="font-semibold text-sm text-base-content/70"),
                            P(cue or "Not specified", cls="text-base-content/70"),
                            cls="mb-3 p-3 bg-yellow-50 rounded",
                        ),
                        Div(
                            P("🎬 Routine:", cls="font-semibold text-sm text-base-content/70"),
                            P(routine or "Not specified", cls="text-base-content/70"),
                            cls="mb-3 p-3 bg-green-50 rounded",
                        ),
                        Div(
                            P("🎁 Reward:", cls="font-semibold text-sm text-base-content/70"),
                            P(reward or "Not specified", cls="text-base-content/70"),
                            cls="p-3 bg-purple-50 rounded",
                        ),
                        cls="mt-4",
                        **{"x-show": "showBehavior", "x-transition": ""},
                    ),
                ),
                cls="mb-4",
                **{"x-data": "{ showBehavior: false }"},
            ),
            # Actions
            Div(
                Button(
                    "✏️ Edit Habit",
                    cls="btn btn-secondary w-full mb-2",
                    hx_get=f"/habits/{uid}/edit",
                    hx_target="#modal",
                ),
                Button(
                    "🧠 View Patterns",
                    cls="btn btn-secondary w-full mb-2",
                    hx_get=f"/habits/{uid}/patterns",
                    hx_target="#modal",
                ),
                Button(
                    "✓ Complete Today",
                    cls="btn btn-success w-full text-lg py-4",
                    hx_post=f"/habits/{uid}/complete",
                    hx_target="#main-content",
                ),
                cls="mb-4",
            ),
            cls="container mx-auto p-4",
        )

    @staticmethod
    def get_mobile_swipe_script() -> str:
        """
        Alpine.js script for swipe gesture handling.

        Include this in the page to enable swipe navigation.
        """
        return """
        <script>
        document.addEventListener('alpine:init', () => {
            Alpine.data('swipeHandler', () => ({
                swipeIndex: 0
                touchStartX: 0
                touchEndX: 0
                totalCards: 0

                init() {
                    this.totalCards = this.$refs.habitCards.children.length;
                },

                handleTouchStart(event) {
                    this.touchStartX = event.changedTouches[0].screenX;
                },

                handleTouchEnd(event) {
                    this.touchEndX = event.changedTouches[0].screenX;
                    this.handleSwipeGesture();
                },

                handleSwipeGesture() {
                    const swipeThreshold = 50; // Minimum distance for swipe

                    if (this.touchEndX < this.touchStartX - swipeThreshold) {
                        // Swiped left - next card
                        if (this.swipeIndex < this.totalCards - 1) {
                            this.swipeIndex++;
                        }
                    }

                    if (this.touchEndX > this.touchStartX + swipeThreshold) {
                        // Swiped right - previous card
                        if (this.swipeIndex > 0) {
                            this.swipeIndex--;
                        }
                    }
                }
            }))
        })
        </script>
        """
