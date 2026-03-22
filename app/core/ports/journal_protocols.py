"""
Journal Protocols
==================

Route-facing protocols for the Journal domain — standalone, user-owned
reflective practice.

Journal is NOT a submission and NOT a report. These protocols are separate
from submission_protocols.py.

Protocol Responsibilities
--------------------------
    JournalInputOperations   — CRUD, file upload, FIFO cleanup, transcription handling
    JournalOutputOperations  — LLM processing, je_output generation and retrieval

ISP-compliant: each protocol captures only the methods called from routes.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from datetime import date
from typing import Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result


@runtime_checkable
class JournalInputOperations(Protocol):
    """CRUD, file upload, and lifecycle management for journal entry inputs.

    Route consumers: journal_api.py, journals_ui.py
    Implementation: JournalInputService
    """

    # ------------------------------------------------------------------
    # CREATION
    # ------------------------------------------------------------------

    async def create_journal_entry(
        self,
        user_uid: str,
        content: str | None = None,
        mood: str | None = None,
        energy_level: str | None = None,
        entry_date: date | None = None,
        instructions: str | None = None,
        max_retention: int | None = None,
    ) -> Result[Any]:
        """Create a text-based journal entry. Returns Result[JeInput]."""
        ...

    async def submit_journal_file(
        self,
        file_content: bytes,
        original_filename: str,
        user_uid: str,
        file_type: str | None = None,
        instructions: str | None = None,
        max_retention: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Result[Any]:
        """Upload an audio/text file as journal entry. Returns Result[JeInput]."""
        ...

    # ------------------------------------------------------------------
    # RETRIEVAL
    # ------------------------------------------------------------------

    async def get_je_input(self, uid: str) -> Result[Any | None]:
        """Get a journal entry input by UID. Returns Result[JeInput | None]."""
        ...

    async def list_je_inputs(
        self,
        user_uid: str,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Result[list[Any]]:
        """List journal entry inputs for a user. Returns Result[list[JeInput]]."""
        ...

    async def get_je_inputs_by_date_range(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
    ) -> Result[list[Any]]:
        """Get journal entries within a date range. Returns Result[list[JeInput]]."""
        ...

    # ------------------------------------------------------------------
    # LIFECYCLE
    # ------------------------------------------------------------------

    async def make_permanent(self, uid: str, user_uid: str) -> Result[bool]:
        """Make an ephemeral journal entry permanent (disable FIFO cleanup)."""
        ...

    async def delete_je_input(self, uid: str, user_uid: str) -> Result[bool]:
        """Delete a journal entry input and its associated files."""
        ...

    # ------------------------------------------------------------------
    # TITLE GENERATION
    # ------------------------------------------------------------------

    async def generate_journal_title(
        self, user_uid: str, entry_date: date | None = None
    ) -> Result[str]:
        """Generate a sequential title for a new journal entry."""
        ...


@runtime_checkable
class JournalOutputOperations(Protocol):
    """LLM processing and je_output generation/retrieval.

    Route consumers: journal_api.py, journals_ui.py
    Implementation: JournalOutputService
    """

    async def generate_output(
        self,
        je_input_uid: str,
        user_uid: str,
        enrichment_mode: str = "activity_tracking",
        custom_instructions: str | None = None,
    ) -> Result[Any]:
        """Process a je_input through LLM and create a je_output. Returns Result[JeOutput]."""
        ...

    async def get_je_output(self, uid: str) -> Result[Any | None]:
        """Get a journal entry output by UID. Returns Result[JeOutput | None]."""
        ...

    async def get_je_output_for_input(self, je_input_uid: str) -> Result[Any | None]:
        """Get the je_output associated with a je_input. Returns Result[JeOutput | None]."""
        ...

    async def list_je_outputs(
        self,
        user_uid: str,
        limit: int = 50,
        offset: int = 0,
    ) -> Result[list[Any]]:
        """List journal entry outputs for a user. Returns Result[list[JeOutput]]."""
        ...

    async def get_output_file_content(self, uid: str) -> Result[str | None]:
        """Get the content of a je_output file from disk."""
        ...

    async def download_output_file(self, uid: str) -> Result[str | None]:
        """Get the file path of a je_output for download. Returns Result[file_path]."""
        ...
