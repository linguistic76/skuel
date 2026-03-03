"""
Atomic Habits UI Components - MVP
==========================================

Implements the 4 core MVP components:
1. Habit creation wizard with identity
2. Identity progress bar (votes/50)
3. System strength meter
4. Habit completion celebration

Based on James Clear's "Atomic Habits" philosophy visualized for SKUEL users.
"""

from typing import Any

from fasthtml.common import H2, H3, H4, Div, Form, Option, P, Span, Strong
from ui.buttons import Button
from ui.cards import Card, CardBody
from ui.forms import Input, Label, Select, Textarea
from ui.habits.atomic_animations import AtomicHabitsAnimations


class AtomicHabitsComponents:
    """
    MVP components for Atomic Habits visualization.

    Philosophy: "You do not rise to the level of your goals.
                 You fall to the level of your systems."
                 - James Clear
    """

    # ========================================================================
    # COMPONENT 1: HABIT CREATION WIZARD WITH IDENTITY
    # ========================================================================

    @staticmethod
    def render_habit_creation_wizard(step: int = 1, form_data: dict | None = None) -> Any:
        """
        Multi-step habit creation wizard with identity-based motivation.

        Steps:
        1. Basic habit info + identity statement
        2. Behavior design (cue-routine-reward)
        3. Link to goals with essentiality
        4. Review and create
        """
        form_data = form_data or {}

        if step == 1:
            return AtomicHabitsComponents._wizard_step_1_identity(form_data)
        elif step == 2:
            return AtomicHabitsComponents._wizard_step_2_behavior(form_data)
        elif step == 3:
            return AtomicHabitsComponents._wizard_step_3_goals(form_data)
        elif step == 4:
            return AtomicHabitsComponents._wizard_step_4_review(form_data)
        else:
            return AtomicHabitsComponents._wizard_step_1_identity(form_data)

    @staticmethod
    def _wizard_step_1_identity(form_data: dict) -> Any:
        """Step 1: Habit name, description, and identity statement"""
        return Card(
            CardBody(
                # Progress indicator
                Div(Span("Step 1 of 4", cls="text-sm text-base-content/60"), cls="mb-4 text-right"),
                # Header
                H2("Create New Habit", cls="text-2xl font-bold mb-2"),
                P(
                    "Every habit is a vote for the type of person you wish to become",
                    cls="text-base-content/70 italic mb-6",
                ),
                # Form
                Form(
                    # Habit name
                    Div(
                        Label("What habit do you want to build?", _for="habit-name", cls="label"),
                        Input(
                            type="text",
                            id="habit-name",
                            name="name",
                            placeholder="Write 500 words daily",
                            value=form_data.get("name", ""),
                            required=True,
                            cls="input input-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Identity statement
                    Div(
                        Label(
                            "📖 This habit will help you become...", _for="identity", cls="label"
                        ),
                        Input(
                            type="text",
                            id="identity",
                            name="reinforces_identity",
                            placeholder="I am a writer",
                            value=form_data.get("reinforces_identity", ""),
                            cls="input input-bordered w-full",
                        ),
                        P(
                            "✨ Every completion is a vote for this identity",
                            cls="text-sm text-blue-600 mt-1",
                        ),
                        cls="mb-4",
                    ),
                    # Description
                    Div(
                        Label("Description (optional)", _for="description", cls="label"),
                        Textarea(
                            id="description",
                            name="description",
                            placeholder="What will you do, when, and why?",
                            rows="3",
                            cls="textarea textarea-bordered w-full",
                            children=form_data.get("description", ""),
                        ),
                        cls="mb-4",
                    ),
                    # Frequency & Duration
                    Div(
                        Div(
                            Label("Frequency", _for="recurrence", cls="label"),
                            Select(
                                Option(
                                    "Daily",
                                    value="daily",
                                    selected=form_data.get("recurrence_pattern") == "daily",
                                ),
                                Option(
                                    "Weekly",
                                    value="weekly",
                                    selected=form_data.get("recurrence_pattern") == "weekly",
                                ),
                                Option(
                                    "Monthly",
                                    value="monthly",
                                    selected=form_data.get("recurrence_pattern") == "monthly",
                                ),
                                id="recurrence",
                                name="recurrence_pattern",
                                cls="select select-bordered w-full",
                            ),
                            cls="flex-1",
                        ),
                        Div(
                            Label("Duration (minutes)", _for="duration", cls="label"),
                            Input(
                                type="number",
                                id="duration",
                                name="duration_minutes",
                                value=form_data.get("duration_minutes", 15),
                                min="1",
                                cls="input input-bordered w-full",
                            ),
                            cls="flex-1",
                        ),
                        cls="flex gap-4 mb-6",
                    ),
                    # Action buttons
                    Div(
                        Button(
                            "Cancel", type="button", cls="btn btn-ghost", onclick="closeModal()"
                        ),
                        Button(
                            "Next: Behavior Design →",
                            type="submit",
                            cls="btn btn-primary",
                            hx_post="/habits/wizard/step2",
                            hx_target="#wizard-container",
                            hx_include="[name]",
                        ),
                        cls="flex justify-between",
                    ),
                    hx_post="/habits/wizard/step2",
                    hx_target="#wizard-container",
                ),
            ),
            id="wizard-container",
            cls="max-w-2xl mx-auto",
        )

    @staticmethod
    def _wizard_step_2_behavior(form_data: dict) -> Any:
        """Step 2: Behavior design (Cue-Routine-Reward)"""
        return Card(
            CardBody(
                # Progress
                Div(Span("Step 2 of 4", cls="text-sm text-base-content/60"), cls="mb-4 text-right"),
                H2("⚙️ Behavior Design", cls="text-2xl font-bold mb-2"),
                P(
                    "Design your habit using the Atomic Habits framework",
                    cls="text-base-content/70 mb-6",
                ),
                Form(
                    # Cue
                    Div(
                        Label(
                            "Cue (What triggers this habit?)", _for="cue", cls="label font-semibold"
                        ),
                        P(
                            "The time, location, or event that starts your habit",
                            cls="text-sm text-base-content/60 mb-2",
                        ),
                        Input(
                            type="text",
                            id="cue",
                            name="cue",
                            placeholder="After morning coffee",
                            value=form_data.get("cue", ""),
                            cls="input input-bordered w-full",
                        ),
                        cls="mb-4 p-4 bg-blue-50 rounded-lg",
                    ),
                    # Routine
                    Div(
                        Label(
                            "Routine (What's the exact action?)",
                            _for="routine",
                            cls="label font-semibold",
                        ),
                        P(
                            "The specific behavior you'll perform",
                            cls="text-sm text-base-content/60 mb-2",
                        ),
                        Input(
                            type="text",
                            id="routine",
                            name="routine",
                            placeholder="Open laptop, write in daily journal",
                            value=form_data.get("routine", ""),
                            cls="input input-bordered w-full",
                        ),
                        cls="mb-4 p-4 bg-green-50 rounded-lg",
                    ),
                    # Reward
                    Div(
                        Label(
                            "Reward (How do you celebrate?)",
                            _for="reward",
                            cls="label font-semibold",
                        ),
                        P(
                            "The immediate satisfaction you feel",
                            cls="text-sm text-base-content/60 mb-2",
                        ),
                        Input(
                            type="text",
                            id="reward",
                            name="reward",
                            placeholder="Cross off day on calendar, feel accomplished",
                            value=form_data.get("reward", ""),
                            cls="input input-bordered w-full",
                        ),
                        cls="mb-6 p-4 bg-purple-50 rounded-lg",
                    ),
                    # Actions
                    Div(
                        Button(
                            "← Back",
                            type="button",
                            cls="btn btn-ghost",
                            hx_post="/habits/wizard/step1",
                            hx_target="#wizard-container",
                            hx_include="[name]",
                        ),
                        Button(
                            "Next: Link Goals →",
                            type="submit",
                            cls="btn btn-primary",
                            hx_post="/habits/wizard/step3",
                            hx_target="#wizard-container",
                            hx_include="[name]",
                        ),
                        cls="flex justify-between",
                    ),
                    hx_post="/habits/wizard/step3",
                    hx_target="#wizard-container",
                ),
            ),
            id="wizard-container",
            cls="max-w-2xl mx-auto",
        )

    @staticmethod
    def _wizard_step_3_goals(form_data: dict) -> Any:
        """Step 3: Link to goals with essentiality classification"""
        # Mock goals for demonstration
        mock_goals = [
            {"uid": "goal_1", "title": "Write and Publish First Novel", "timeframe": "6 months"},
            {
                "uid": "goal_2",
                "title": "Develop Consistent Writing Practice",
                "timeframe": "3 months",
            },
        ]

        return Card(
            CardBody(
                # Progress
                Div(Span("Step 3 of 4", cls="text-sm text-base-content/60"), cls="mb-4 text-right"),
                H2("📘 Link to Goals", cls="text-2xl font-bold mb-2"),
                P("How essential is this habit for each goal?", cls="text-base-content/70 mb-6"),
                Form(
                    # Goal essentiality selectors
                    Div(
                        *[
                            AtomicHabitsComponents._render_goal_essentiality_selector(
                                goal, form_data
                            )
                            for goal in mock_goals
                        ],
                        cls="space-y-4 mb-6",
                    ),
                    # Info box
                    Div(
                        P("💡 Tip:", cls="font-semibold mb-2"),
                        P(
                            "Reserve ESSENTIAL for the 1-3 habits you absolutely cannot achieve this goal without. Most habits are SUPPORTING.",
                            cls="text-sm text-base-content/70",
                        ),
                        cls="bg-yellow-50 p-4 rounded-lg mb-6",
                    ),
                    # Actions
                    Div(
                        Button(
                            "← Back",
                            type="button",
                            cls="btn btn-ghost",
                            hx_post="/habits/wizard/step2",
                            hx_target="#wizard-container",
                            hx_include="[name]",
                        ),
                        Button(
                            "Next: Review →",
                            type="submit",
                            cls="btn btn-primary",
                            hx_post="/habits/wizard/step4",
                            hx_target="#wizard-container",
                            hx_include="[name]",
                        ),
                        cls="flex justify-between",
                    ),
                    hx_post="/habits/wizard/step4",
                    hx_target="#wizard-container",
                ),
            ),
            id="wizard-container",
            cls="max-w-2xl mx-auto",
        )

    @staticmethod
    def _render_goal_essentiality_selector(goal: dict, _form_data: dict) -> Any:
        """Render essentiality radio buttons for a goal"""
        goal_uid = goal["uid"]

        return Card(
            CardBody(
                H3(f"📘 {goal['title']}", cls="text-lg font-semibold mb-2"),
                P(f"Timeframe: {goal['timeframe']}", cls="text-sm text-base-content/60 mb-3"),
                Div(
                    Label("This habit is:", cls="label mb-2"),
                    Div(
                        # Essential
                        Label(
                            Input(
                                type="radio",
                                name=f"goal_{goal_uid}_essentiality",
                                value="essential",
                                cls="radio radio-error",
                            ),
                            Span("ESSENTIAL", cls="ml-2 font-semibold"),
                            cls="flex items-center cursor-pointer",
                        ),
                        P(
                            "🔴 Goal is IMPOSSIBLE without this habit",
                            cls="text-xs text-base-content/70 ml-6 mb-2",
                        ),
                        # Critical
                        Label(
                            Input(
                                type="radio",
                                name=f"goal_{goal_uid}_essentiality",
                                value="critical",
                                cls="radio radio-warning",
                            ),
                            Span("CRITICAL", cls="ml-2 font-semibold"),
                            cls="flex items-center cursor-pointer",
                        ),
                        P(
                            "🟠 Goal is VERY DIFFICULT without this habit",
                            cls="text-xs text-base-content/70 ml-6 mb-2",
                        ),
                        # Supporting
                        Label(
                            Input(
                                type="radio",
                                name=f"goal_{goal_uid}_essentiality",
                                value="supporting",
                                cls="radio radio-info",
                                checked=True,
                            ),
                            Span("SUPPORTING", cls="ml-2 font-semibold"),
                            cls="flex items-center cursor-pointer",
                        ),
                        P(
                            "🟡 Goal is EASIER with this habit",
                            cls="text-xs text-base-content/70 ml-6 mb-2",
                        ),
                        # Optional
                        Label(
                            Input(
                                type="radio",
                                name=f"goal_{goal_uid}_essentiality",
                                value="optional",
                                cls="radio radio-success",
                            ),
                            Span("OPTIONAL", cls="ml-2 font-semibold"),
                            cls="flex items-center cursor-pointer",
                        ),
                        P(
                            "🟢 Habit is TANGENTIALLY helpful",
                            cls="text-xs text-base-content/70 ml-6",
                        ),
                        cls="space-y-2",
                    ),
                    cls="mb-3",
                ),
            ),
            cls="bg-base-200",
        )

    @staticmethod
    def _wizard_step_4_review(form_data: dict) -> Any:
        """Step 4: Review and create"""
        return Card(
            CardBody(
                # Progress
                Div(Span("Step 4 of 4", cls="text-sm text-base-content/60"), cls="mb-4 text-right"),
                H2("✅ Review & Create", cls="text-2xl font-bold mb-6"),
                # Review summary
                Div(
                    # Basic info
                    Card(
                        CardBody(
                            H3("Habit Details", cls="font-semibold mb-3"),
                            Div(
                                P(Strong("Name: "), form_data.get("name", "N/A")),
                                P(
                                    Strong("Identity: "),
                                    form_data.get("reinforces_identity", "N/A"),
                                ),
                                P(
                                    Strong("Frequency: "),
                                    form_data.get("recurrence_pattern", "daily").title(),
                                ),
                                P(
                                    Strong("Duration: "),
                                    f"{form_data.get('duration_minutes', 15)} minutes",
                                ),
                                cls="space-y-2",
                            ),
                        ),
                        cls="bg-blue-50 mb-4",
                    ),
                    # Behavior design
                    Card(
                        CardBody(
                            H3("Behavior Design", cls="font-semibold mb-3"),
                            Div(
                                P(Strong("Cue: "), form_data.get("cue", "Not specified")),
                                P(Strong("Routine: "), form_data.get("routine", "Not specified")),
                                P(Strong("Reward: "), form_data.get("reward", "Not specified")),
                                cls="space-y-2",
                            ),
                        ),
                        cls="bg-green-50 mb-4",
                    ),
                    # Philosophy reminder
                    Card(
                        CardBody(
                            P(
                                '"You do not rise to the level of your goals. '
                                'You fall to the level of your systems."',
                                cls="italic text-base-content/70 mb-2",
                            ),
                            P(
                                "— James Clear, Atomic Habits",
                                cls="text-sm text-base-content/60 text-right",
                            ),
                        ),
                        cls="bg-yellow-50 mb-6",
                    ),
                    cls="mb-6",
                ),
                # Actions
                Div(
                    Button(
                        "← Back",
                        type="button",
                        cls="btn btn-ghost",
                        hx_post="/habits/wizard/step3",
                        hx_target="#wizard-container",
                    ),
                    Button(
                        "Create Habit 🎉",
                        type="submit",
                        cls="btn btn-primary btn-lg",
                        hx_post="/api/habits/create-with-identity",
                        hx_target="#main-content",
                    ),
                    cls="flex justify-between",
                ),
            ),
            id="wizard-container",
            cls="max-w-2xl mx-auto",
        )

    # ========================================================================
    # COMPONENT 2: IDENTITY PROGRESS BAR
    # ========================================================================

    @staticmethod
    def render_identity_progress_bar(
        identity: str,
        votes_cast: int,
        votes_required: int = 50,
        size: str = "md",
        animate: bool = True,
    ) -> Any:
        """
        Identity establishment progress bar with smooth animation.

        Shows votes cast toward identity establishment (research-backed 50-rep threshold).

        Args:
            identity: Identity statement (e.g., "I am a writer"),
            votes_cast: Number of habit completions (identity votes),
            votes_required: Threshold for identity establishment (default 50),
            size: 'sm', 'md', or 'lg',
            animate: Whether to animate the progress bar
        """
        percentage = min((votes_cast / votes_required) * 100, 100)
        is_established = votes_cast >= votes_required

        # Size classes
        size_classes = {"sm": "text-sm", "md": "text-base", "lg": "text-lg"}
        text_class = size_classes.get(size, "text-base")

        # Color based on progress
        if is_established:
            bar_color = "bg-gradient-to-r from-green-500 to-emerald-600"
            text_color = "text-green-700"
            status_icon = "⭐"
            status_text = "ESTABLISHED"
        elif percentage >= 80:
            bar_color = "bg-gradient-to-r from-blue-500 to-indigo-600"
            text_color = "text-blue-700"
            status_icon = "🔥"
            status_text = "Almost there!"
        elif percentage >= 50:
            bar_color = "bg-gradient-to-r from-yellow-500 to-orange-600"
            text_color = "text-yellow-700"
            status_icon = "💪"
            status_text = "Halfway!"
        else:
            bar_color = "bg-gradient-to-r from-gray-400 to-gray-600"
            text_color = "text-base-content/70"
            status_icon = "🌱"
            status_text = "Building"

        votes_remaining = max(0, votes_required - votes_cast)

        # Animation classes
        animation_class = "progress-animated" if animate else ""

        return Div(
            # Identity label with vote cast animation trigger
            P(
                f"{status_icon} {identity}",
                cls=f"{text_class} font-semibold {text_color} mb-2 vote-cast-animation",
                id=f"identity-{identity.replace(' ', '-')}",
            ),
            # Progress bar with smooth fill animation
            Div(
                Div(
                    style=f"width: {percentage}%",
                    cls=f"{bar_color} h-full rounded-full {animation_class} flex items-center justify-end pr-2",
                    **{"data-percentage": str(percentage)},
                ),
                cls="w-full bg-base-300 rounded-full h-6 mb-2 overflow-hidden",
            ),
            # Stats
            Div(
                Span(f"{votes_cast}/{votes_required} votes", cls="text-sm font-medium"),
                Span(
                    f"{status_text}" if is_established else f"{votes_remaining} more to establish",
                    cls="text-sm text-base-content/70",
                ),
                cls="flex justify-between items-center",
            ),
            # Milestone message
            (
                Div(
                    P(
                        "✨ Identity established! This is who you are now.",
                        cls="text-sm text-green-700 font-medium mt-2 p-2 bg-green-50 rounded",
                    )
                )
                if is_established
                else None
            ),
            cls="mb-4",
        )

    # ========================================================================
    # COMPONENT 3: SYSTEM STRENGTH METER
    # ========================================================================

    @staticmethod
    def render_system_strength_meter(
        goal_title: str,
        system_strength: float,
        diagnosis: str,
        habit_breakdown: dict[str, int] | None = None,
        show_breakdown: bool = True,
        animate: bool = True,
    ) -> Any:
        """
        System strength meter showing goal's habit system health with animation.

        Args:
            goal_title: Goal title,
            system_strength: 0-1 score,
            diagnosis: Human-readable assessment,
            habit_breakdown: Dict with 'essential', 'critical', 'supporting', 'optional' counts,
            show_breakdown: Whether to show habit essentiality breakdown,
            animate: Whether to animate the meter fill
        """
        habit_breakdown = habit_breakdown or {
            "essential": 0,
            "critical": 0,
            "supporting": 0,
            "optional": 0,
        }

        percentage = int(system_strength * 100)

        # Color coding
        if system_strength >= 0.8:
            bg_color = "bg-green-100"
            bar_color = "bg-gradient-to-r from-green-500 to-emerald-600"
            text_color = "text-green-700"
            icon = "🎉"
            label = "EXCELLENT"
        elif system_strength >= 0.6:
            bg_color = "bg-blue-100"
            bar_color = "bg-gradient-to-r from-blue-500 to-indigo-600"
            text_color = "text-blue-700"
            icon = "👍"
            label = "GOOD"
        elif system_strength >= 0.4:
            bg_color = "bg-yellow-100"
            bar_color = "bg-gradient-to-r from-yellow-500 to-orange-600"
            text_color = "text-yellow-700"
            icon = "⚠️"
            label = "MODERATE"
        else:
            bg_color = "bg-red-100"
            bar_color = "bg-gradient-to-r from-red-500 to-rose-600"
            text_color = "text-red-700"
            icon = "❌"
            label = "WEAK"

        total_habits = sum(habit_breakdown.values())

        return Card(
            CardBody(
                # Header
                Div(
                    H3(f"🎯 {goal_title}", cls="text-lg font-semibold mb-2"),
                    P("Habit System Strength", cls="text-sm text-base-content/70 mb-4"),
                    cls="mb-4",
                ),
                # Strength meter
                Div(
                    Div(
                        Span(f"{percentage}%", cls=f"text-3xl font-bold {text_color}"),
                        Span(f"{icon} {label}", cls=f"text-sm font-semibold {text_color}"),
                        cls="flex items-center justify-between mb-2",
                    ),
                    # Progress bar with animation
                    Div(
                        Div(
                            style=f"width: {percentage}%",
                            cls=f"{bar_color} h-4 rounded-full {'meter-animated' if animate else 'transition-all duration-500'}",
                        ),
                        cls="w-full bg-base-300 rounded-full h-4 mb-3",
                    ),
                    # Diagnosis
                    P(diagnosis, cls="text-sm text-base-content/70 italic mb-4"),
                    cls=f"p-4 {bg_color} rounded-lg mb-4",
                ),
                # Habit breakdown
                (
                    Div(
                        H4("Habit System Breakdown", cls="text-sm font-semibold mb-3"),
                        Div(
                            # Essential
                            Div(
                                Span("🔴 ESSENTIAL", cls="text-sm font-medium"),
                                Span(str(habit_breakdown["essential"]), cls="text-sm font-bold"),
                                cls="flex justify-between mb-2",
                            ),
                            # Critical
                            Div(
                                Span("🟠 CRITICAL", cls="text-sm font-medium"),
                                Span(str(habit_breakdown["critical"]), cls="text-sm font-bold"),
                                cls="flex justify-between mb-2",
                            ),
                            # Supporting
                            Div(
                                Span("🟡 SUPPORTING", cls="text-sm font-medium"),
                                Span(str(habit_breakdown["supporting"]), cls="text-sm font-bold"),
                                cls="flex justify-between mb-2",
                            ),
                            # Optional
                            Div(
                                Span("🟢 OPTIONAL", cls="text-sm font-medium"),
                                Span(str(habit_breakdown["optional"]), cls="text-sm font-bold"),
                                cls="flex justify-between mb-2",
                            ),
                            # Total
                            Div(
                                Span("TOTAL", cls="text-sm font-bold"),
                                Span(str(total_habits), cls="text-sm font-bold"),
                                cls="flex justify-between pt-2 border-t border-base-300",
                            ),
                            cls="space-y-1",
                        ),
                        cls="bg-base-100 p-4 rounded-lg",
                    )
                    if show_breakdown
                    else None
                ),
            ),
        )

    # ========================================================================
    # COMPONENT 4: HABIT COMPLETION CELEBRATION
    # ========================================================================

    @staticmethod
    def render_habit_completion_celebration(
        habit_name: str,
        identity: str | None,
        votes_cast: int,
        votes_required: int = 50,
        goal_impacts: list[dict] | None = None,
    ) -> Any:
        """
        Celebration modal shown after completing a habit.

        Shows identity vote cast and goal system impacts.

        Args:
            habit_name: Habit that was completed,
            identity: Identity statement (if identity-based habit),
            votes_cast: New total votes cast,
            votes_required: Votes needed for establishment,
            goal_impacts: List of dicts with 'title', 'system_strength_delta', 'velocity_delta'
        """
        goal_impacts = goal_impacts or []
        is_identity_habit = identity is not None
        percentage = min((votes_cast / votes_required) * 100, 100)
        just_established = votes_cast == votes_required

        return Div(
            # Include animation styles
            AtomicHabitsAnimations.get_animation_styles(),
            # Confetti burst for celebration
            AtomicHabitsAnimations.render_confetti_burst(count=40),
            Card(
                CardBody(
                    # Celebration header with animation
                    Div(
                        # Animated checkmark
                        AtomicHabitsAnimations.render_checkmark_animation(),
                        H2(
                            "✅ Completed!",
                            cls="text-3xl font-bold text-green-700 mb-2 card-fade-in",
                        ),
                        P(habit_name, cls="text-xl text-base-content/70"),
                        cls="text-center mb-6",
                    ),
                    # Identity vote (if applicable)
                    (
                        Div(
                            Div(
                                H3(
                                    "🎉 IDENTITY VOTE CAST 🎉",
                                    cls="text-2xl font-bold text-center mb-4 text-purple-700 vote-cast-animation",
                                ),
                                P(
                                    f'You are becoming "{identity}"',
                                    cls="text-lg text-center text-base-content/70 mb-4",
                                ),
                                # Animated progress bar
                                Div(
                                    Div(
                                        style=f"width: {percentage}%",
                                        cls="bg-gradient-to-r from-purple-500 to-pink-600 h-3 rounded-full progress-animated",
                                    ),
                                    cls="w-full bg-base-300 rounded-full h-3 mb-2",
                                ),
                                P(
                                    f"{votes_cast}/{votes_required} votes ({int(percentage)}% established)",
                                    cls="text-sm text-center text-base-content/70",
                                ),
                                # Just established?
                                (
                                    Div(
                                        P(
                                            "✨ IDENTITY ESTABLISHED! ✨",
                                            cls="text-xl font-bold text-green-700 mb-2",
                                        ),
                                        P(
                                            "After 50 repetitions, your brain has formed new neural pathways. "
                                            "This is no longer an aspiration - it's who you are.",
                                            cls="text-sm text-base-content/70",
                                        ),
                                        cls="mt-4 p-4 bg-green-50 rounded-lg text-center",
                                    )
                                    if just_established
                                    else None
                                ),
                                cls="p-6 bg-purple-50 rounded-lg mb-6",
                            ),
                        )
                        if is_identity_habit
                        else None
                    ),
                    # Goal impacts
                    (
                        Div(
                            H3("Impact on Goals:", cls="text-lg font-semibold mb-3"),
                            Div(
                                *[
                                    AtomicHabitsComponents._render_goal_impact(impact)
                                    for impact in goal_impacts
                                ],
                                cls="space-y-3",
                            ),
                            cls="mb-6",
                        )
                        if goal_impacts
                        else None
                    ),
                    # Quote
                    Div(
                        P(
                            '"Every action you take is a vote for the type of person you wish to become."',
                            cls="italic text-base-content/70 mb-2",
                        ),
                        P("— James Clear", cls="text-sm text-base-content/60 text-right"),
                        cls="p-4 bg-base-200 rounded-lg mb-6",
                    ),
                    # Actions
                    Div(
                        Button(
                            "View Updated Dashboard",
                            cls="btn btn-primary",
                            hx_get="/habits",
                            hx_target="#main-content",
                        ),
                        Button("Close", cls="btn btn-ghost", onclick="closeModal()"),
                        cls="flex gap-4 justify-center",
                    ),
                ),
                cls="max-w-lg mx-auto",
            ),
        )

    @staticmethod
    def _render_goal_impact(impact: dict) -> Any:
        """Render a single goal impact card"""
        title = impact.get("title", "Unknown Goal")
        strength_delta = impact.get("system_strength_delta", 0)
        velocity_delta = impact.get("velocity_delta", 0)

        return Div(
            P(f"📘 {title}", cls="font-semibold mb-1"),
            P(
                f"System Strength: +{strength_delta}% | Velocity: +{velocity_delta}",
                cls="text-sm text-green-600",
            ),
            cls="p-3 bg-green-50 rounded",
        )


# Export
__all__ = ["AtomicHabitsComponents"]
