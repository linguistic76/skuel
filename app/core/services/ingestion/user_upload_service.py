"""
User Upload Service - Per-User Bulk File Upload and Ingestion
=============================================================

Orchestrates bulk YAML file uploads for authenticated users.
Files are written to per-user vault directories and ingested
using the existing UnifiedIngestionService pipeline.

Only Activity Domain types are accepted (Task, Goal, Habit,
Event, Choice, Principle). Curriculum types remain admin-only.

See: /docs/roadmap/obsidian-headless-sync.md
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from core.models.enums.entity_enums import EntityType
from core.models.type_hints import UserUID
from core.utils.exception_types import FILE_IO_EXCEPTIONS, PARSING_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

from .config import DEFAULT_MAX_FILE_SIZE_BYTES
from .unified_ingestion_service import UnifiedIngestionService

logger = get_logger("skuel.services.ingestion.user_upload")

# Only Activity Domain types are allowed for user uploads
ALLOWED_UPLOAD_TYPES: frozenset[EntityType] = frozenset(
    {
        EntityType.TASK,
        EntityType.GOAL,
        EntityType.HABIT,
        EntityType.EVENT,
        EntityType.CHOICE,
        EntityType.PRINCIPLE,
    }
)

# Map detected type string → EntityType for validation
_TYPE_STRING_TO_ENTITY: dict[str, EntityType] = {
    "task": EntityType.TASK,
    "goal": EntityType.GOAL,
    "habit": EntityType.HABIT,
    "event": EntityType.EVENT,
    "choice": EntityType.CHOICE,
    "principle": EntityType.PRINCIPLE,
}

# Map EntityType → subdirectory name
_TYPE_TO_SUBDIR: dict[EntityType, str] = {
    EntityType.TASK: "tasks",
    EntityType.GOAL: "goals",
    EntityType.HABIT: "habits",
    EntityType.EVENT: "events",
    EntityType.CHOICE: "choices",
    EntityType.PRINCIPLE: "principles",
}

VAULT_SUBDIRS: tuple[str, ...] = tuple(_TYPE_TO_SUBDIR.values())

# Limits
MAX_FILES_PER_REQUEST = 50
MAX_FILE_SIZE_BYTES = DEFAULT_MAX_FILE_SIZE_BYTES  # 10 MB


@dataclass(frozen=True)
class FileUploadResult:
    """Result for a single uploaded file."""

    filename: str
    success: bool
    entity_type: str | None = None
    uid: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class UploadBatchResult:
    """Aggregated result for a batch of uploaded files."""

    total: int
    successful: int
    failed: int
    results: list[FileUploadResult] = field(default_factory=list)


def _sanitize_filename(filename: str) -> str | None:
    """Sanitize filename, returning None if unsafe.

    Rejects path traversal attempts and non-YAML extensions.
    Returns the sanitized basename (no directory components).
    """
    if not filename:
        return None

    # Strip directory components — only the basename matters
    name = Path(filename).name

    # Reject path traversal
    if ".." in name or "/" in name or "\\" in name:
        return None

    # Reject hidden files
    if name.startswith("."):
        return None

    # Enforce YAML extension
    suffix = Path(name).suffix.lower()
    if suffix not in (".yaml", ".yml"):
        return None

    return name


def _sanitize_user_uid(user_uid: UserUID) -> str:
    """Convert user_uid to a safe directory name."""
    return str(user_uid).replace(":", "_").replace(".", "_").replace("/", "_")


class UserUploadService:
    """Orchestrates per-user bulk YAML file uploads and ingestion.

    Handles:
    - Per-user vault directory provisioning
    - Filename and content validation
    - Activity Domain type restriction
    - Delegation to UnifiedIngestionService for actual ingestion
    """

    def __init__(
        self,
        ingestion_service: UnifiedIngestionService,
        user_vaults_base: Path,
        max_file_size_bytes: int = MAX_FILE_SIZE_BYTES,
    ) -> None:
        self.ingestion_service = ingestion_service
        self.user_vaults_base = user_vaults_base
        self.max_file_size_bytes = max_file_size_bytes

    def get_user_vault_path(self, user_uid: UserUID) -> Path:
        """Return the vault directory path for a user."""
        safe_uid = _sanitize_user_uid(user_uid)
        return self.user_vaults_base / safe_uid

    def provision_user_vault(self, user_uid: UserUID) -> Path:
        """Create per-user vault directory with Activity Domain subdirectories."""
        vault = self.get_user_vault_path(user_uid)
        for subdir in VAULT_SUBDIRS:
            (vault / subdir).mkdir(parents=True, exist_ok=True)
        return vault

    async def upload_and_ingest(
        self,
        user_uid: UserUID,
        files: list[tuple[str, bytes]],
    ) -> Result[UploadBatchResult]:
        """Upload YAML files to user vault and ingest them.

        Args:
            user_uid: Authenticated user's UID
            files: List of (filename, content_bytes) tuples

        Returns:
            Result with UploadBatchResult containing per-file outcomes.
        """
        if not files:
            return Result.fail(Errors.validation("No files provided"))

        if len(files) > MAX_FILES_PER_REQUEST:
            return Result.fail(
                Errors.validation(f"Too many files: {len(files)} (max {MAX_FILES_PER_REQUEST})")
            )

        # Ensure vault directory exists
        vault_path = self.provision_user_vault(user_uid)

        results: list[FileUploadResult] = []

        for filename, content in files:
            result = await self._process_single_file(user_uid, vault_path, filename, content)
            results.append(result)

        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful

        return Result.ok(
            UploadBatchResult(
                total=len(results),
                successful=successful,
                failed=failed,
                results=results,
            )
        )

    async def _process_single_file(
        self,
        user_uid: UserUID,
        vault_path: Path,
        filename: str,
        content: bytes,
    ) -> FileUploadResult:
        """Validate, write, and ingest a single uploaded file."""

        # 1. Sanitize filename
        safe_name = _sanitize_filename(filename)
        if not safe_name:
            return FileUploadResult(
                filename=filename,
                success=False,
                error="Invalid filename: must be a .yaml or .yml file without path traversal",
            )

        # 2. Check file size
        if len(content) > self.max_file_size_bytes:
            return FileUploadResult(
                filename=filename,
                success=False,
                error=f"File too large: {len(content)} bytes (max {self.max_file_size_bytes})",
            )

        # 3. Parse YAML to detect type (before writing to disk)
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            return FileUploadResult(
                filename=filename,
                success=False,
                error="File is not valid UTF-8 text",
            )

        try:
            data = yaml.safe_load(text)
        except PARSING_EXCEPTIONS as e:
            return FileUploadResult(
                filename=filename,
                success=False,
                error=f"Invalid YAML: {e}",
            )

        if not isinstance(data, dict):
            return FileUploadResult(
                filename=filename,
                success=False,
                error="YAML must contain a mapping (key-value pairs), not a list or scalar",
            )

        # 4. Detect and validate entity type
        type_str = str(data.get("type", "")).strip().lower()
        entity_type = _TYPE_STRING_TO_ENTITY.get(type_str)

        if entity_type is None:
            allowed = ", ".join(sorted(_TYPE_STRING_TO_ENTITY.keys()))
            return FileUploadResult(
                filename=filename,
                success=False,
                error=f"Missing or unsupported 'type' field. Allowed types: {allowed}",
            )

        if entity_type not in ALLOWED_UPLOAD_TYPES:
            return FileUploadResult(
                filename=filename,
                success=False,
                error=f"Type '{type_str}' is not allowed for user uploads",
            )

        # 5. Write to user vault subdirectory
        subdir = _TYPE_TO_SUBDIR[entity_type]
        file_path = vault_path / subdir / safe_name

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(text, encoding="utf-8")
        except FILE_IO_EXCEPTIONS as e:
            return FileUploadResult(
                filename=filename,
                success=False,
                entity_type=type_str,
                error=f"Failed to write file: {e}",
            )

        # 6. Ingest via UnifiedIngestionService with user's UID
        try:
            ingest_result = await self.ingestion_service.ingest_file(file_path, user_uid=user_uid)
        except Exception as e:  # safety-net: ingestion can fail in many ways
            logger.error("Ingestion failed for %s (user %s): %s", filename, user_uid, e)
            return FileUploadResult(
                filename=filename,
                success=False,
                entity_type=type_str,
                error=f"Ingestion failed: {e}",
            )

        if ingest_result.is_error:
            error = ingest_result.expect_error()
            return FileUploadResult(
                filename=filename,
                success=False,
                entity_type=type_str,
                error=str(error),
            )

        # 7. Extract result details
        result_data: dict[str, Any] = ingest_result.value
        return FileUploadResult(
            filename=filename,
            success=True,
            entity_type=type_str,
            uid=result_data.get("uid"),
        )
