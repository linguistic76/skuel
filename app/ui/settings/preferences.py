"""
User Preferences UI Components
================================

Reusable components for editing user preferences and settings.
Builds forms manually with LabelInput/LabelSelect components.

The editor is ONE form: every section's fields post together to
``/settings/save`` (HTMX), and the answer replaces the editor inside
``#settings-content``.
"""

from typing import Any

from fasthtml.common import Div, Form, Option, P, Span

from core.utils.zone_context import zone_names
from ui.components import Button, ButtonT, Card, CardBody, CardHeader, CardTitle
from ui.feedback import Alert, AlertT
from ui.forms import Checkbox, Label, LabelInput, LabelSelect
from ui.patterns.page_header import PageHeader

# The zone <select> and the element that reports what "Use this device's time
# zone" did — SKUEL.useDeviceZone (static/js/skuel.js) is handed both ids.
TIMEZONE_SELECT_ID = "timezone"
TIMEZONE_NOTE_ID = "timezone-device-note"


class UserPreferencesComponents:
    """Reusable component library for user preferences interface"""

    @staticmethod
    def render_preferences_editor(
        user_preferences: dict | None = None, *, default_timezone: str
    ) -> Any:
        """
        Render the complete preferences editing form.

        Args:
            user_preferences: Current preference values (dict)
            default_timezone: The app default zone's name (``SKUEL_TIMEZONE``,
                validated at boot) — the label of the zone list's "SKUEL
                default" entry

        Returns:
            Complete preferences editing interface
        """
        user_preferences = user_preferences or {}

        return Div(
            PageHeader("User Settings & Preferences", subtitle="Customize your SKUEL experience"),
            Form(
                # Learning Preferences Section
                Card(
                    CardHeader(CardTitle("🎓 Learning Preferences")),
                    CardBody(UserPreferencesComponents._render_learning_prefs(user_preferences)),
                    cls="mb-6",
                ),
                # Scheduling Preferences Section
                Card(
                    CardHeader(CardTitle("📅 Scheduling & Time")),
                    CardBody(UserPreferencesComponents._render_scheduling_prefs(user_preferences)),
                    cls="mb-6",
                ),
                # Notification Preferences Section
                Card(
                    CardHeader(CardTitle("🔔 Notifications")),
                    CardBody(
                        UserPreferencesComponents._render_notification_prefs(user_preferences)
                    ),
                    cls="mb-6",
                ),
                # Display Preferences Section
                Card(
                    CardHeader(CardTitle("🎨 Display & Appearance")),
                    CardBody(
                        UserPreferencesComponents._render_display_prefs(
                            user_preferences, default_timezone
                        )
                    ),
                    cls="mb-6",
                ),
                # Goal Preferences Section
                Card(
                    CardHeader(CardTitle("🎯 Goals & Targets")),
                    CardBody(UserPreferencesComponents._render_goal_prefs(user_preferences)),
                    cls="mb-6",
                ),
                # Save button
                Div(
                    Button(
                        "Cancel",
                        type="button",
                        cls=(ButtonT.secondary, "mr-4"),
                        onclick="window.location.href='/settings'",
                    ),
                    Button("Save All Changes", type="submit", cls=ButtonT.primary),
                    cls="flex justify-end mt-6",
                ),
                id="preferences-form",
                hx_post="/settings/save",
                hx_target="#settings-content",
                hx_swap="innerHTML",
            ),
            cls="container mx-auto p-6 max-w-4xl",
        )

    @staticmethod
    def _render_learning_prefs(prefs: dict) -> Any:
        """Render learning preferences section"""
        return Div(
            LabelSelect(
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
                Option("Expert", value="expert", selected=prefs.get("learning_level") == "expert"),
                label="Learning Level",
                lbl_cls="font-semibold",
                name="learning_level",
                help_text="Your current skill level helps us recommend appropriate content",
                cls="space-y-2 mb-4",
            ),
            Div(
                Label("Preferred Learning Modalities", cls="font-semibold"),
                Div(
                    Div(
                        Checkbox(
                            name="modality_video",
                            id="modality_video",
                            checked="video" in prefs.get("preferred_modalities", []),
                        ),
                        Label("Video", _for="modality_video", cls="ml-2"),
                        cls="flex items-center mb-2",
                    ),
                    Div(
                        Checkbox(
                            name="modality_reading",
                            id="modality_reading",
                            checked="reading" in prefs.get("preferred_modalities", []),
                        ),
                        Label("Reading", _for="modality_reading", cls="ml-2"),
                        cls="flex items-center mb-2",
                    ),
                    Div(
                        Checkbox(
                            name="modality_interactive",
                            id="modality_interactive",
                            checked="interactive" in prefs.get("preferred_modalities", []),
                        ),
                        Label("Interactive", _for="modality_interactive", cls="ml-2"),
                        cls="flex items-center mb-2",
                    ),
                    Div(
                        Checkbox(
                            name="modality_audio",
                            id="modality_audio",
                            checked="audio" in prefs.get("preferred_modalities", []),
                        ),
                        Label("Audio/Podcasts", _for="modality_audio", cls="ml-2"),
                        cls="flex items-center",
                    ),
                    cls="space-y-2",
                ),
                cls="space-y-2 mb-4",
            ),
        )

    @staticmethod
    def _render_scheduling_prefs(prefs: dict) -> Any:
        """Render scheduling preferences section"""
        return Div(
            LabelSelect(
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
                label="Preferred Time of Day",
                lbl_cls="font-semibold",
                name="preferred_time_of_day",
                cls="space-y-2 mb-4",
            ),
            Div(
                LabelInput(
                    "Available Minutes Daily",
                    lbl_cls="font-semibold",
                    type="number",
                    name="available_minutes_daily",
                    value=prefs.get("available_minutes_daily", 60),
                    min=0,
                    max=1440,
                    cls="space-y-2",
                ),
                P(
                    f"{prefs.get('available_minutes_daily', 60)} minutes = {prefs.get('available_minutes_daily', 60) / 60:.1f} hours",
                    cls="text-sm text-muted-foreground mt-1",
                ),
                cls="mb-4",
            ),
        )

    @staticmethod
    def _render_notification_prefs(prefs: dict) -> Any:
        """Render notification preferences section"""
        return Div(
            Div(
                Div(
                    Checkbox(
                        name="enable_reminders",
                        id="enable_reminders",
                        checked=prefs.get("enable_reminders", True),
                    ),
                    Label("Enable Reminders", _for="enable_reminders", cls="ml-2 font-semibold"),
                    cls="flex items-center mb-4",
                ),
                LabelInput(
                    "Reminder Minutes Before",
                    lbl_cls="font-semibold",
                    type="number",
                    name="reminder_minutes_before",
                    value=prefs.get("reminder_minutes_before", 15),
                    min=0,
                    max=1440,
                    cls="space-y-2 mb-4",
                ),
                LabelInput(
                    "Daily Summary Time (HH:MM)",
                    lbl_cls="font-semibold",
                    type="time",
                    name="daily_summary_time",
                    value=prefs.get("daily_summary_time", "09:00"),
                    cls="space-y-2 mb-4",
                ),
                cls="space-y-4",
            ),
        )

    # DaisyUI themes (class-based dark mode via Tailwind)
    THEMES = [
        "light",
        "dark",
    ]

    @staticmethod
    def _render_display_prefs(prefs: dict, default_timezone: str) -> Any:
        """Render display preferences section"""
        current_theme = prefs.get("theme", "light")
        theme_options = [
            Option(
                theme.capitalize(),
                value=theme,
                selected=current_theme == theme,
            )
            for theme in UserPreferencesComponents.THEMES
        ]

        return Div(
            LabelSelect(
                *theme_options,
                label="Theme",
                lbl_cls="font-semibold",
                name="theme",
                onchange="this.value === 'dark' ? document.documentElement.classList.add('dark') : document.documentElement.classList.remove('dark'); localStorage.setItem('skuel-theme', this.value)",
                help_text="Theme changes preview instantly. Save to persist.",
                cls="space-y-2 mb-4",
            ),
            LabelSelect(
                Option("English", value="en", selected=prefs.get("language") == "en"),
                Option("Spanish", value="es", selected=prefs.get("language") == "es"),
                Option("French", value="fr", selected=prefs.get("language") == "fr"),
                Option("German", value="de", selected=prefs.get("language") == "de"),
                label="Language",
                lbl_cls="font-semibold",
                name="language",
                cls="space-y-2 mb-4",
            ),
            UserPreferencesComponents._render_timezone_field(
                prefs.get("timezone"), default_timezone
            ),
        )

    @staticmethod
    def _render_timezone_field(choice: str | None, default_timezone: str) -> Any:
        """The zone list and the "Use this device's time zone" button.

        The list is the SKUEL default entry (the empty value — no choice,
        which follows ``SKUEL_TIMEZONE``) and then every name zoneinfo lists,
        the user's choice selected. The button selects the browser's own zone
        (``SKUEL.useDeviceZone``); saving the form keeps it, and the server
        validates what is posted.
        """
        options = [
            Option(f"SKUEL default ({default_timezone})", value="", selected=choice is None),
            *(Option(name, value=name, selected=name == choice) for name in sorted(zone_names())),
        ]
        return Div(
            LabelSelect(
                *options,
                label="Time zone",
                lbl_cls="font-semibold",
                name="timezone",
                id=TIMEZONE_SELECT_ID,
                help_text="The zone your days and times are read in.",
            ),
            Div(
                Button(
                    "Use this device's time zone",
                    type="button",
                    size="sm",
                    onclick=f"SKUEL.useDeviceZone('{TIMEZONE_SELECT_ID}', '{TIMEZONE_NOTE_ID}')",
                ),
                P(
                    id=TIMEZONE_NOTE_ID,
                    aria_live="polite",
                    cls="text-sm text-muted-foreground",
                ),
                cls="flex flex-wrap items-center gap-x-3 gap-y-1",
            ),
            cls="space-y-2 mb-4",
        )

    @staticmethod
    def _render_goal_prefs(prefs: dict) -> Any:
        """Render goal preferences section"""
        return Div(
            LabelInput(
                "Weekly Task Goal",
                lbl_cls="font-semibold",
                type="number",
                name="weekly_task_goal",
                value=prefs.get("weekly_task_goal", 10),
                min=0,
                max=100,
                help_text="Target number of tasks to complete each week",
                cls="space-y-2 mb-4",
            ),
            LabelInput(
                "Daily Habit Goal",
                lbl_cls="font-semibold",
                type="number",
                name="daily_habit_goal",
                value=prefs.get("daily_habit_goal", 3),
                min=0,
                max=20,
                help_text="Target number of habits to complete each day",
                cls="space-y-2 mb-4",
            ),
            LabelInput(
                "Monthly Learning Hours",
                lbl_cls="font-semibold",
                type="number",
                name="monthly_learning_hours",
                value=prefs.get("monthly_learning_hours", 20),
                min=0,
                max=500,
                help_text="Target learning hours per month",
                cls="space-y-2 mb-4",
            ),
        )

    @staticmethod
    def render_preferences_saved_message() -> Any:
        """Render success message after saving preferences"""
        return Alert(
            Div(
                Span("✅", cls="text-3xl mr-3"),
                Span("Preferences saved successfully!", cls="text-lg font-semibold"),
                cls="flex items-center",
            ),
            Button(
                "Back to Settings",
                cls=(ButtonT.primary, "mt-4"),
                onclick="window.location.href='/settings'",
            ),
            variant=AlertT.success,
            cls="p-6 max-w-2xl mx-auto mt-8",
        )
