"""UserPreferences.timezone — a user's zone choice, None following SKUEL_TIMEZONE.

No choice is None in every tier: the domain model and the DTO default to it, the
Settings form's request model parses a blank value to it, and a new user carries
it. A name zoneinfo does not list is refused at the request model and at the DTO
parse (the Settings door has its own test, tests/unit/adapters/test_settings_routes.py).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.models.user import UserDTO, UserPreferences, UserPreferencesDTO, create_user
from core.models.user.user_request import UserPreferencesFormRequest

#: Every field the Settings form posts but the zone, each a value the form accepts.
_FORM: dict[str, object] = {
    "learning_level": "intermediate",
    "preferred_time_of_day": "morning",
    "available_minutes_daily": 60,
    "reminder_minutes_before": 15,
    "daily_summary_time": "09:00",
    "theme": "light",
    "language": "en",
    "weekly_task_goal": 10,
    "daily_habit_goal": 3,
    "monthly_learning_hours": 20,
}


def _form(timezone: str) -> UserPreferencesFormRequest:
    return UserPreferencesFormRequest.model_validate({**_FORM, "timezone": timezone})


class TestNoChoiceIsNone:
    def test_every_tier_defaults_to_no_choice(self) -> None:
        assert UserPreferences().timezone is None
        assert UserPreferencesDTO().timezone is None

    def test_a_new_user_has_no_choice(self) -> None:
        user = create_user(username="fresh_zone_user", email="fresh@example.com")
        assert user.preferences.timezone is None


class TestRequestModel:
    def test_a_listed_name_is_kept(self) -> None:
        assert _form("Asia/Bangkok").timezone == "Asia/Bangkok"

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_is_no_choice(self, blank: str) -> None:
        assert _form(blank).timezone is None

    @pytest.mark.parametrize("bad", ["Mars/Olympus", "UTC+7", "localtime"])
    def test_an_unlisted_name_is_refused(self, bad: str) -> None:
        with pytest.raises(ValidationError, match="Unknown time zone"):
            _form(bad)


class TestDtoParse:
    def _parse(self, preferences: dict) -> UserDTO:
        return UserDTO.from_dict(
            {
                "uid": "user_zone_dto",
                "username": "zone_dto",
                "email": "z@example.com",
                "preferences": preferences,
            }
        )

    def test_a_listed_name_is_kept(self) -> None:
        assert self._parse({"timezone": "Asia/Bangkok"}).preferences.timezone == "Asia/Bangkok"

    @pytest.mark.parametrize("stored", [{}, {"timezone": None}, {"timezone": ""}])
    def test_missing_null_or_blank_is_no_choice(self, stored: dict) -> None:
        assert self._parse(stored).preferences.timezone is None

    def test_an_unlisted_name_is_refused(self) -> None:
        with pytest.raises(ValueError, match="Unknown time zone 'Mars/Olympus'"):
            self._parse({"timezone": "Mars/Olympus"})
