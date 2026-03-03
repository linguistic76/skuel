"""
User Preferences UI Components
================================

Reusable components for editing user preferences and settings.
Uses FormGenerator and CardGenerator for 100% dynamic rendering.

Version: 1.0.0
Date: 2025-10-14
"""

from typing import Any

from fasthtml.common import H1, H2, Div, Form, Option, P, Span

from ui.buttons import Button
from ui.forms import Input, Label, Select


class UserPreferencesComponents:
    """Reusable component library for user preferences interface"""

    @staticmethod
    def render_preferences_editor(user_preferences: dict | None = None) -> Any:
        """
        Render the complete preferences editing form.

        Uses FormGenerator to create the form dynamically from the
        UserPreferencesSchema Pydantic model.

        Args:
            user_preferences: Current preference values (dict)

        Returns:
            Complete preferences editing interface
        """
        user_preferences = user_preferences or {}

        return Div(
            H1("User Settings & Preferences", cls="text-3xl font-bold mb-6"),
            P("Customize your SKUEL experience", cls="text-lg text-base-content/70 mb-8"),
            # Learning Preferences Section
            Div(
                H2("🎓 Learning Preferences", cls="text-2xl font-semibold mb-4"),
                UserPreferencesComponents._render_learning_prefs_form(user_preferences),
                cls="card bg-base-100 shadow-sm p-6 mb-6",
            ),
            # Scheduling Preferences Section
            Div(
                H2("📅 Scheduling & Time", cls="text-2xl font-semibold mb-4"),
                UserPreferencesComponents._render_scheduling_prefs_form(user_preferences),
                cls="card bg-base-100 shadow-sm p-6 mb-6",
            ),
            # Notification Preferences Section
            Div(
                H2("🔔 Notifications", cls="text-2xl font-semibold mb-4"),
                UserPreferencesComponents._render_notification_prefs_form(user_preferences),
                cls="card bg-base-100 shadow-sm p-6 mb-6",
            ),
            # Display Preferences Section
            Div(
                H2("🎨 Display & Appearance", cls="text-2xl font-semibold mb-4"),
                UserPreferencesComponents._render_display_prefs_form(user_preferences),
                cls="card bg-base-100 shadow-sm p-6 mb-6",
            ),
            # Goal Preferences Section
            Div(
                H2("🎯 Goals & Targets", cls="text-2xl font-semibold mb-4"),
                UserPreferencesComponents._render_goal_prefs_form(user_preferences),
                cls="card bg-base-100 shadow-sm p-6 mb-6",
            ),
            # Save button
            Div(
                Button(
                    "Cancel",
                    type="button",
                    cls="btn btn-outline mr-4",
                    onclick="window.location.href='/profile'",
                ),
                Button(
                    "Save All Changes",
                    type="submit",
                    cls="btn btn-primary",
                    form="preferences-form",
                ),
                cls="flex justify-end mt-6",
            ),
            cls="container mx-auto p-6 max-w-4xl",
        )

    @staticmethod
    def _render_learning_prefs_form(prefs: dict) -> Any:
        """Render learning preferences section"""
        return Form(
            Div(
                Label("Learning Level", cls="label font-semibold"),
                Select(name="learning_level", cls="select select-bordered w-full")(
                    Option(
                        "Beginner",
                        value="beginner",
                        selected=prefs.get("learning_level") == "beginner",
                    ),
                    Option(
                        "Intermediate",
                        value="intermediate",
                        selected=prefs.get("learning_level") == "intermediate",
                    ),
                    Option(
                        "Advanced",
                        value="advanced",
                        selected=prefs.get("learning_level") == "advanced",
                    ),
                    Option(
                        "Expert", value="expert", selected=prefs.get("learning_level") == "expert"
                    ),
                ),
                P(
                    "Your current skill level helps us recommend appropriate content",
                    cls="text-sm text-base-content/60 mt-1",
                ),
                cls="form-control mb-4",
            ),
            Div(
                Label("Preferred Learning Modalities", cls="label font-semibold"),
                Div(
                    Div(
                        Input(
                            type="checkbox",
                            name="modality_video",
                            id="modality_video",
                            checked="video" in prefs.get("preferred_modalities", []),
                            cls="checkbox",
                        ),
                        Label("Video", _for="modality_video", cls="ml-2"),
                        cls="flex items-center mb-2",
                    ),
                    Div(
                        Input(
                            type="checkbox",
                            name="modality_reading",
                            id="modality_reading",
                            checked="reading" in prefs.get("preferred_modalities", []),
                            cls="checkbox",
                        ),
                        Label("Reading", _for="modality_reading", cls="ml-2"),
                        cls="flex items-center mb-2",
                    ),
                    Div(
                        Input(
                            type="checkbox",
                            name="modality_interactive",
                            id="modality_interactive",
                            checked="interactive" in prefs.get("preferred_modalities", []),
                            cls="checkbox",
                        ),
                        Label("Interactive", _for="modality_interactive", cls="ml-2"),
                        cls="flex items-center mb-2",
                    ),
                    Div(
                        Input(
                            type="checkbox",
                            name="modality_audio",
                            id="modality_audio",
                            checked="audio" in prefs.get("preferred_modalities", []),
                            cls="checkbox",
                        ),
                        Label("Audio/Podcasts", _for="modality_audio", cls="ml-2"),
                        cls="flex items-center",
                    ),
                    cls="space-y-2",
                ),
                cls="form-control mb-4",
            ),
            id="learning-prefs-form",
            method="POST",
            action="/profile/settings/save",
        )

    @staticmethod
    def _render_scheduling_prefs_form(prefs: dict) -> Any:
        """Render scheduling preferences section"""
        return Form(
            Div(
                Label("Preferred Time of Day", cls="label font-semibold"),
                Select(name="preferred_time_of_day", cls="select select-bordered w-full")(
                    Option(
                        "Anytime",
                        value="anytime",
                        selected=prefs.get("preferred_time_of_day") == "anytime",
                    ),
                    Option(
                        "Morning",
                        value="morning",
                        selected=prefs.get("preferred_time_of_day") == "morning",
                    ),
                    Option(
                        "Afternoon",
                        value="afternoon",
                        selected=prefs.get("preferred_time_of_day") == "afternoon",
                    ),
                    Option(
                        "Evening",
                        value="evening",
                        selected=prefs.get("preferred_time_of_day") == "evening",
                    ),
                    Option(
                        "Night",
                        value="night",
                        selected=prefs.get("preferred_time_of_day") == "night",
                    ),
                ),
                cls="form-control mb-4",
            ),
            Div(
                Label("Available Minutes Daily", cls="label font-semibold"),
                Input(
                    type="number",
                    name="available_minutes_daily",
                    value=prefs.get("available_minutes_daily", 60),
                    min=0,
                    max=1440,
                    cls="input input-bordered w-full",
                ),
                P(
                    f"{prefs.get('available_minutes_daily', 60)} minutes = {prefs.get('available_minutes_daily', 60) / 60:.1f} hours",
                    cls="text-sm text-base-content/60 mt-1",
                ),
                cls="form-control mb-4",
            ),
            id="scheduling-prefs-form",
            method="POST",
            action="/profile/settings/save",
        )

    @staticmethod
    def _render_notification_prefs_form(prefs: dict) -> Any:
        """Render notification preferences section"""
        return Form(
            Div(
                Div(
                    Input(
                        type="checkbox",
                        name="enable_reminders",
                        id="enable_reminders",
                        checked=prefs.get("enable_reminders", True),
                        cls="checkbox",
                    ),
                    Label("Enable Reminders", _for="enable_reminders", cls="ml-2 font-semibold"),
                    cls="flex items-center mb-4",
                ),
                Div(
                    Label("Reminder Minutes Before", cls="label font-semibold"),
                    Input(
                        type="number",
                        name="reminder_minutes_before",
                        value=prefs.get("reminder_minutes_before", 15),
                        min=0,
                        max=1440,
                        cls="input input-bordered w-full",
                    ),
                    cls="form-control mb-4",
                ),
                Div(
                    Label("Daily Summary Time (HH:MM)", cls="label font-semibold"),
                    Input(
                        type="time",
                        name="daily_summary_time",
                        value=prefs.get("daily_summary_time", "09:00"),
                        cls="input input-bordered w-full",
                    ),
                    cls="form-control mb-4",
                ),
                cls="space-y-4",
            ),
            id="notification-prefs-form",
            method="POST",
            action="/profile/settings/save",
        )

    @staticmethod
    def _render_display_prefs_form(prefs: dict) -> Any:
        """Render display preferences section"""
        return Form(
            Div(
                Label("Theme", cls="label font-semibold"),
                Select(name="theme", cls="select select-bordered w-full")(
                    Option("Light", value="light", selected=prefs.get("theme") == "light"),
                    Option("Dark", value="dark", selected=prefs.get("theme") == "dark"),
                    Option("Auto", value="auto", selected=prefs.get("theme") == "auto"),
                ),
                cls="form-control mb-4",
            ),
            Div(
                Label("Language", cls="label font-semibold"),
                Select(name="language", cls="select select-bordered w-full")(
                    Option("English", value="en", selected=prefs.get("language") == "en"),
                    Option("Spanish", value="es", selected=prefs.get("language") == "es"),
                    Option("French", value="fr", selected=prefs.get("language") == "fr"),
                    Option("German", value="de", selected=prefs.get("language") == "de"),
                ),
                cls="form-control mb-4",
            ),
            Div(
                Label("Timezone", cls="label font-semibold"),
                Input(
                    type="text",
                    name="timezone",
                    value=prefs.get("timezone", "UTC"),
                    cls="input input-bordered w-full",
                ),
                P(
                    "e.g., America/New_York, Europe/London, Asia/Tokyo",
                    cls="text-sm text-base-content/60 mt-1",
                ),
                cls="form-control mb-4",
            ),
            id="display-prefs-form",
            method="POST",
            action="/profile/settings/save",
        )

    @staticmethod
    def _render_goal_prefs_form(prefs: dict) -> Any:
        """Render goal preferences section"""
        return Form(
            Div(
                Label("Weekly Task Goal", cls="label font-semibold"),
                Input(
                    type="number",
                    name="weekly_task_goal",
                    value=prefs.get("weekly_task_goal", 10),
                    min=0,
                    max=100,
                    cls="input input-bordered w-full",
                ),
                P(
                    "Target number of tasks to complete each week",
                    cls="text-sm text-base-content/60 mt-1",
                ),
                cls="form-control mb-4",
            ),
            Div(
                Label("Daily Habit Goal", cls="label font-semibold"),
                Input(
                    type="number",
                    name="daily_habit_goal",
                    value=prefs.get("daily_habit_goal", 3),
                    min=0,
                    max=20,
                    cls="input input-bordered w-full",
                ),
                P(
                    "Target number of habits to complete each day",
                    cls="text-sm text-base-content/60 mt-1",
                ),
                cls="form-control mb-4",
            ),
            Div(
                Label("Monthly Learning Hours", cls="label font-semibold"),
                Input(
                    type="number",
                    name="monthly_learning_hours",
                    value=prefs.get("monthly_learning_hours", 20),
                    min=0,
                    max=500,
                    cls="input input-bordered w-full",
                ),
                P("Target learning hours per month", cls="text-sm text-base-content/60 mt-1"),
                cls="form-control mb-4",
            ),
            id="goal-prefs-form",
            method="POST",
            action="/profile/settings/save",
        )

    @staticmethod
    def render_preferences_saved_message() -> Any:
        """Render success message after saving preferences"""
        return Div(
            Div(
                Span("✅", cls="text-3xl mr-3"),
                Span("Preferences saved successfully!", cls="text-lg font-semibold"),
                cls="flex items-center",
            ),
            Button(
                "Back to Profile",
                cls="btn btn-primary mt-4",
                onclick="window.location.href='/profile'",
            ),
            cls="alert alert-success p-6 max-w-2xl mx-auto mt-8",
        )
