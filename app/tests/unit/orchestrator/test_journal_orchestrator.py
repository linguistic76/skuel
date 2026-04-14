"""Tests for the JournalOrchestrator."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.orchestrator.journal_orchestrator import JournalOrchestrator
from core.utils.result_simplified import ErrorCategory, Errors, Result


@pytest.fixture
def mock_journal_input() -> MagicMock:
    mock = MagicMock()
    mock.list_je_inputs = AsyncMock()
    mock.get_je_input = AsyncMock()
    mock.submit_journal_file = AsyncMock()
    mock.delete_je_input = AsyncMock()
    mock.generate_journal_title = AsyncMock()
    return mock


@pytest.fixture
def mock_journal_output() -> MagicMock:
    mock = MagicMock()
    mock.get_je_output_for_input = AsyncMock()
    # cleanup_date_range is sync — leave as plain MagicMock
    return mock


@pytest.fixture
def mock_exercises() -> MagicMock:
    mock = MagicMock()
    mock.list_user_exercises = AsyncMock()
    mock.create_exercise = AsyncMock()
    return mock


@pytest.fixture
def mock_user_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def orchestrator_full(
    mock_journal_input: MagicMock,
    mock_journal_output: MagicMock,
    mock_exercises: MagicMock,
    mock_user_service: MagicMock,
) -> JournalOrchestrator:
    return JournalOrchestrator(
        journal_input_service=mock_journal_input,
        exercises_service=mock_exercises,
        user_service=mock_user_service,
        journal_output_service=mock_journal_output,
    )


@pytest.fixture
def orchestrator_core(
    mock_journal_input: MagicMock,
    mock_exercises: MagicMock,
    mock_user_service: MagicMock,
) -> JournalOrchestrator:
    return JournalOrchestrator(
        journal_input_service=mock_journal_input,
        exercises_service=mock_exercises,
        user_service=mock_user_service,
        journal_output_service=None,
    )


def _mk_je_input(user_uid: str = "user-1") -> MagicMock:
    je = MagicMock()
    je.user_uid = user_uid
    return je


# --- get_journal_for_download ---


@pytest.mark.asyncio
async def test_get_journal_for_download_success(
    orchestrator_full: JournalOrchestrator,
    mock_journal_input: MagicMock,
    mock_journal_output: MagicMock,
) -> None:
    je_input = _mk_je_input("user-1")
    je_output = MagicMock()
    mock_journal_input.get_je_input.return_value = Result.ok(je_input)
    mock_journal_output.get_je_output_for_input.return_value = Result.ok(je_output)

    result = await orchestrator_full.get_journal_for_download("ji_1", "user-1")

    assert result.is_ok
    assert result.value == (je_input, je_output)
    mock_journal_output.get_je_output_for_input.assert_called_once_with("ji_1")


@pytest.mark.asyncio
async def test_get_journal_for_download_not_found_missing_input(
    orchestrator_full: JournalOrchestrator,
    mock_journal_input: MagicMock,
    mock_journal_output: MagicMock,
) -> None:
    mock_journal_input.get_je_input.return_value = Result.ok(None)

    result = await orchestrator_full.get_journal_for_download("ji_1", "user-1")

    assert result.is_error
    err = result.expect_error()
    assert err.category == ErrorCategory.NOT_FOUND
    assert err.details["resource"] == "JeInput"
    mock_journal_output.get_je_output_for_input.assert_not_called()


@pytest.mark.asyncio
async def test_get_journal_for_download_not_found_input_error(
    orchestrator_full: JournalOrchestrator,
    mock_journal_input: MagicMock,
) -> None:
    mock_journal_input.get_je_input.return_value = Result.fail(
        Errors.database("read", "boom")
    )

    result = await orchestrator_full.get_journal_for_download("ji_1", "user-1")

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.NOT_FOUND
    assert result.expect_error().details["resource"] == "JeInput"


@pytest.mark.asyncio
async def test_get_journal_for_download_unauthorized_returns_not_found(
    orchestrator_full: JournalOrchestrator,
    mock_journal_input: MagicMock,
    mock_journal_output: MagicMock,
) -> None:
    mock_journal_input.get_je_input.return_value = Result.ok(_mk_je_input("other-user"))

    result = await orchestrator_full.get_journal_for_download("ji_1", "user-1")

    assert result.is_error
    err = result.expect_error()
    assert err.category == ErrorCategory.NOT_FOUND
    assert err.details["resource"] == "JeInput"
    mock_journal_output.get_je_output_for_input.assert_not_called()


@pytest.mark.asyncio
async def test_get_journal_for_download_core_tier_missing_output_service(
    orchestrator_core: JournalOrchestrator,
    mock_journal_input: MagicMock,
    mock_journal_output: MagicMock,
) -> None:
    mock_journal_input.get_je_input.return_value = Result.ok(_mk_je_input("user-1"))

    result = await orchestrator_core.get_journal_for_download("ji_1", "user-1")

    assert result.is_error
    err = result.expect_error()
    assert err.category == ErrorCategory.SYSTEM
    assert "CORE tier" in err.message
    mock_journal_output.get_je_output_for_input.assert_not_called()


@pytest.mark.asyncio
async def test_get_journal_for_download_output_missing(
    orchestrator_full: JournalOrchestrator,
    mock_journal_input: MagicMock,
    mock_journal_output: MagicMock,
) -> None:
    mock_journal_input.get_je_input.return_value = Result.ok(_mk_je_input("user-1"))
    mock_journal_output.get_je_output_for_input.return_value = Result.ok(None)

    result = await orchestrator_full.get_journal_for_download("ji_1", "user-1")

    assert result.is_error
    err = result.expect_error()
    assert err.category == ErrorCategory.NOT_FOUND
    assert err.details["resource"] == "JeOutput"


@pytest.mark.asyncio
async def test_get_journal_for_download_output_error(
    orchestrator_full: JournalOrchestrator,
    mock_journal_input: MagicMock,
    mock_journal_output: MagicMock,
) -> None:
    mock_journal_input.get_je_input.return_value = Result.ok(_mk_je_input("user-1"))
    mock_journal_output.get_je_output_for_input.return_value = Result.fail(
        Errors.database("read", "boom")
    )

    result = await orchestrator_full.get_journal_for_download("ji_1", "user-1")

    assert result.is_error
    assert result.expect_error().details["resource"] == "JeOutput"


# --- tier-gating ---


@pytest.mark.asyncio
async def test_get_je_output_for_input_core_tier_fails(
    orchestrator_core: JournalOrchestrator,
) -> None:
    result = await orchestrator_core.get_je_output_for_input("ji_1")

    assert result.is_error
    err = result.expect_error()
    assert err.category == ErrorCategory.SYSTEM
    assert "CORE tier" in err.message


def test_cleanup_date_range_core_tier_fails(orchestrator_core: JournalOrchestrator) -> None:
    result = orchestrator_core.cleanup_date_range(datetime(2026, 1, 1), datetime(2026, 2, 1))

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.SYSTEM


def test_cleanup_date_range_delegates_when_available(
    orchestrator_full: JournalOrchestrator, mock_journal_output: MagicMock
) -> None:
    stats = {"deleted": 3}
    mock_journal_output.cleanup_date_range.return_value = Result.ok(stats)

    start = datetime(2026, 1, 1)
    end = datetime(2026, 2, 1)
    result = orchestrator_full.cleanup_date_range(start, end)

    assert result.is_ok
    assert result.value == stats
    mock_journal_output.cleanup_date_range.assert_called_once_with(start, end)


# --- thin delegation ---


@pytest.mark.asyncio
async def test_list_je_inputs_delegates(
    orchestrator_full: JournalOrchestrator, mock_journal_input: MagicMock
) -> None:
    mock_journal_input.list_je_inputs.return_value = Result.ok([])

    await orchestrator_full.list_je_inputs("user-1", status="draft", limit=10)

    mock_journal_input.list_je_inputs.assert_called_once_with(
        user_uid="user-1", status="draft", limit=10
    )


@pytest.mark.asyncio
async def test_submit_journal_file_delegates(
    orchestrator_full: JournalOrchestrator, mock_journal_input: MagicMock
) -> None:
    mock_journal_input.submit_journal_file.return_value = Result.ok(MagicMock())

    await orchestrator_full.submit_journal_file(
        file_content=b"xyz",
        original_filename="a.m4a",
        user_uid="user-1",
        metadata={"k": "v"},
    )

    mock_journal_input.submit_journal_file.assert_called_once_with(
        file_content=b"xyz",
        original_filename="a.m4a",
        user_uid="user-1",
        metadata={"k": "v"},
    )


@pytest.mark.asyncio
async def test_delete_je_input_delegates(
    orchestrator_full: JournalOrchestrator, mock_journal_input: MagicMock
) -> None:
    mock_journal_input.delete_je_input.return_value = Result.ok(True)

    await orchestrator_full.delete_je_input("ji_1", "user-1")

    mock_journal_input.delete_je_input.assert_called_once_with("ji_1", "user-1")


@pytest.mark.asyncio
async def test_generate_journal_title_delegates(
    orchestrator_full: JournalOrchestrator, mock_journal_input: MagicMock
) -> None:
    mock_journal_input.generate_journal_title.return_value = Result.ok("Entry 1")
    dt = datetime(2026, 4, 14)

    await orchestrator_full.generate_journal_title("user-1", dt)

    mock_journal_input.generate_journal_title.assert_called_once_with("user-1", dt)


@pytest.mark.asyncio
async def test_list_user_exercises_delegates(
    orchestrator_full: JournalOrchestrator, mock_exercises: MagicMock
) -> None:
    mock_exercises.list_user_exercises.return_value = Result.ok([])

    await orchestrator_full.list_user_exercises("user-1")

    mock_exercises.list_user_exercises.assert_called_once_with("user-1")


@pytest.mark.asyncio
async def test_create_exercise_delegates(
    orchestrator_full: JournalOrchestrator, mock_exercises: MagicMock
) -> None:
    mock_exercises.create_exercise.return_value = Result.ok(MagicMock())

    await orchestrator_full.create_exercise("user-1", "Name", "Do this")

    mock_exercises.create_exercise.assert_called_once_with(
        user_uid="user-1", name="Name", instructions="Do this"
    )
