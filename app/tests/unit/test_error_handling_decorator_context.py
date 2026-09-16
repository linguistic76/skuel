"""``with_error_handling``'s uid extraction — both call shapes, no annotation evaluation.

The decorator enriches the error it returns with the value of ``uid_param``. Two
invariants are pinned here:

- A positional call yields the uid exactly as a keyword call does — ``args`` never
  includes ``self``, so the index into the signature must skip it.
- Extraction never evaluates the method's annotations. Under PEP 649 a parameter
  typed with a ``TYPE_CHECKING``-only import is an ordinary, lint-mandated shape
  (UP037 is live, TC002/TC003 permanently ignored — ADR-067 § Deferred), and the
  VALUE format would raise ``NameError`` on it at the moment an error was being
  reported.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.type_hints import UserUID


class _Service:
    @with_error_handling("get_user", error_type="database", uid_param="user_uid")
    async def get_user_async(self, user_uid: UserUID) -> Result[None]:
        raise RuntimeError("boom")

    @with_error_handling("get_user", error_type="database", uid_param="user_uid")
    def get_user_sync(self, user_uid: UserUID) -> Result[None]:
        raise RuntimeError("boom")

    @with_error_handling("update", error_type="database", uid_param="user_uid")
    async def update(self, payload: dict[str, str], user_uid: UserUID) -> Result[None]:
        raise RuntimeError("boom")


def test_positional_and_keyword_calls_extract_the_same_uid() -> None:
    positional = asyncio.run(_Service().get_user_async("u1"))
    keyword = asyncio.run(_Service().get_user_async(user_uid="u1"))
    assert positional.is_error and keyword.is_error
    assert positional.expect_error().details["details"] == {"uid": "u1"}
    assert keyword.expect_error().details["details"] == {"uid": "u1"}


def test_sync_wrapper_extracts_the_positional_uid() -> None:
    result = _Service().get_user_sync("u2")
    assert result.expect_error().details["details"] == {"uid": "u2"}


def test_positional_index_skips_self_not_the_first_real_parameter() -> None:
    result = asyncio.run(_Service().update({"k": "v"}, "u3"))
    assert result.expect_error().details["details"] == {"uid": "u3"}


def test_extraction_never_evaluates_a_type_checking_only_annotation() -> None:
    # ``UserUID`` is imported under TYPE_CHECKING above, so evaluating the
    # signature's annotations would raise NameError instead of returning a Result.
    try:
        result = asyncio.run(_Service().get_user_async("u4"))
    except NameError as exc:  # pragma: no cover - the defect this test exists for
        pytest.fail(f"uid extraction evaluated the method's annotations: {exc}")
    assert result.expect_error().details["details"] == {"uid": "u4"}
