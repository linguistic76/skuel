"""Journal UI Orchestrator
=========================

Application orchestrator for the Journals Hub. Consolidates
JournalInputService, JournalOutputService, and ExerciseService into a single
unified facade for journals_ui.py.

Required services (JournalInputService, ExerciseService, UserService) are always
present. JournalOutputService is optional — it is ``None`` when
``INTELLIGENCE_TIER=core`` (no LLM key configured). Methods that require it
return ``Result.fail(...)`` when unavailable, centralising all availability
guards in one place rather than scattering them across route handlers.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.exercises.exercise import Exercise
    from core.models.journal.je_input import JeInput
    from core.models.journal.je_output import JeOutput
    from core.ports.query_types import CleanupStats
    from core.services.exercises.exercise_service import ExerciseService
    from core.services.journal import JournalInputService, JournalOutputService
    from core.services.user_service import UserService


class JournalOrchestrator:
    """Facade for the Journals UI layer.

    Abstracts cross-service reads so the UI routing layer depends only on this
    orchestrator. JournalInputService, ExerciseService, and UserService are
    always required. JournalOutputService is optional — callers receive a
    graceful ``Result.fail`` when the service is unavailable (CORE tier).
    """

    def __init__(  # noqa: ANN204
        self,
        journal_input_service: "JournalInputService",
        exercises_service: "ExerciseService",
        user_service: "UserService",
        journal_output_service: "JournalOutputService | None" = None,
    ):
        self._journal_input = journal_input_service
        self._journal_output = journal_output_service
        self._exercises = exercises_service
        self._user_service = user_service

    @property
    def user_service(self) -> "UserService":
        """Expose user service for admin role checks."""
        return self._user_service

    # --- Journal Input ---

    async def list_je_inputs(
        self,
        user_uid: str,
        status: Any = None,
        limit: int = 50,
    ) -> "Result[list[JeInput]]":
        """List journal entries for a user, optionally filtered by status."""
        return await self._journal_input.list_je_inputs(
            user_uid=user_uid,
            status=status,
            limit=limit,
        )

    async def get_je_input(self, uid: str) -> "Result[JeInput | None]":
        """Fetch a single journal entry by UID."""
        return await self._journal_input.get_je_input(uid)

    async def submit_journal_file(
        self,
        file_content: bytes,
        original_filename: str,
        user_uid: str,
        metadata: dict[str, Any] | None = None,
    ) -> "Result[JeInput]":
        """Upload a file as a new journal entry."""
        return await self._journal_input.submit_journal_file(
            file_content=file_content,
            original_filename=original_filename,
            user_uid=user_uid,
            metadata=metadata,
        )

    async def delete_je_input(self, uid: str, user_uid: str) -> "Result[bool]":
        """Delete a journal entry and its associated files."""
        return await self._journal_input.delete_je_input(uid, user_uid)

    async def generate_journal_title(self, user_uid: str, entry_date: datetime) -> "Result[str]":
        """Generate a sequential title for a new journal entry."""
        return await self._journal_input.generate_journal_title(user_uid, entry_date)

    # --- Journal Output ---

    async def get_je_output_for_input(self, je_input_uid: str) -> "Result[JeOutput | None]":
        """Get the JeOutput linked to a JeInput via TRANSFORMS relationship."""
        if not self._journal_output:
            return Result.fail(
                Errors.system(
                    message="Journal output service not available (CORE tier)",
                    service="journal_output_service",
                )
            )
        return await self._journal_output.get_je_output_for_input(je_input_uid)

    async def get_journal_for_download(
        self, uid: str, user_uid: str
    ) -> "Result[tuple[JeInput, JeOutput]]":
        """Fetch a JeInput + its JeOutput, enforcing ownership.

        Combines the ownership check on JeInput with the TRANSFORMS lookup for
        JeOutput into a single call, removing the two-step pattern from routes.

        Returns:
            Result containing (je_input, je_output) tuple, or a failure if the
            entry is not found, not owned by the user, or has no output.
        """
        input_result = await self._journal_input.get_je_input(uid)
        if input_result.is_error or input_result.value is None:
            return Result.fail(Errors.not_found(resource="JeInput", identifier=uid))

        je_input = input_result.value
        if je_input.user_uid != user_uid:
            # Per SKUEL ownership pattern: return not_found rather than leaking existence
            return Result.fail(Errors.not_found(resource="JeInput", identifier=uid))

        if not self._journal_output:
            return Result.fail(
                Errors.system(
                    message="Journal output service not available (CORE tier)",
                    service="journal_output_service",
                )
            )

        output_result = await self._journal_output.get_je_output_for_input(uid)
        if output_result.is_error or output_result.value is None:
            return Result.fail(Errors.not_found(resource="JeOutput", identifier=uid))

        return Result.ok((je_input, output_result.value))

    def cleanup_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> "Result[CleanupStats]":
        """Delete je_output files within a date range. Admin-only.

        Note: synchronous — mirrors the underlying service method signature.
        """
        if not self._journal_output:
            return Result.fail(
                Errors.system(
                    message="Journal output service not available (CORE tier)",
                    service="journal_output_service",
                )
            )
        return self._journal_output.cleanup_date_range(start_date, end_date)

    # --- Exercises (instruction files) ---

    async def list_user_exercises(self, user_uid: str) -> "Result[list[Exercise]]":
        """List saved instruction files (stored as Exercise entities) for a user."""
        return await self._exercises.list_user_exercises(user_uid)

    async def create_exercise(
        self, user_uid: str, name: str, instructions: str
    ) -> "Result[Exercise]":
        """Save a new instruction file as an Exercise entity."""
        return await self._exercises.create_exercise(
            user_uid=user_uid,
            name=name,
            instructions=instructions,
        )
