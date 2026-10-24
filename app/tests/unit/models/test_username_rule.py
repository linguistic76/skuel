"""The username rule — what a username is, and where it is never used.

A username is the account's login handle: folded to lowercase, then 3-30 of
``[a-z0-9_-]``. It is stored as the user's ``title`` and never reaches the uid,
which is generated (``user_{16 hex}``). Both doors that create an account — sign-up
(``GraphAuthService.sign_up``, tested beside it) and ``UserCoreService.create_user``
— fold and check it before looking it up.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.models.user.user import USERNAME, create_user, fold_username, username_problem
from core.services.user.user_core_service import UserCoreService
from core.utils.result_simplified import ErrorCategory, Result
from core.utils.uid_grammar import is_generated_uid


class TestTheRule:
    @pytest.mark.parametrize("raw", ["Mike", " mike ", "MIKE"])
    def test_folding_makes_one_name_of_every_spelling(self, raw: str) -> None:
        assert fold_username(raw) == "mike"

    @pytest.mark.parametrize("name", ["mfan0110", "linguistic76", "uxsmoke", "jane-doe", "a_b"])
    def test_a_username(self, name: str) -> None:
        assert username_problem(name) is None

    @pytest.mark.parametrize(
        "name", ["al", "a" * 31, "jane doe", "o'brien", "café", "Mike", "a.b", "<b>", ""]
    )
    def test_not_a_username(self, name: str) -> None:
        assert username_problem(name)
        assert not USERNAME.fullmatch(name)


def test_the_uid_is_generated_and_the_username_is_the_title() -> None:
    first, second = create_user("mike", "a@example.com"), create_user("mike", "b@example.com")

    assert is_generated_uid(first.uid, "user")
    assert first.uid != second.uid
    assert first.title == "mike"
    assert "mike" not in first.uid


class TestUserCoreServiceCreate:
    @pytest.mark.asyncio
    async def test_it_folds_before_the_lookup(self) -> None:
        repo = AsyncMock()
        repo.get_user_by_username.return_value = Result.ok(None)
        repo.create_user.side_effect = Result.ok
        service = UserCoreService(repo)

        result = await service.create_user(" Mike ", "m@example.com")

        assert result.is_ok
        repo.get_user_by_username.assert_awaited_once_with("mike")
        assert result.value.title == "mike"

    @pytest.mark.asyncio
    async def test_it_refuses_a_name_outside_the_rule(self) -> None:
        repo = AsyncMock()
        service = UserCoreService(repo)

        result = await service.create_user("jane doe", "j@example.com")

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.VALIDATION
        repo.get_user_by_username.assert_not_awaited()
        repo.create_user.assert_not_awaited()
