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

from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.models.enums.user_enums import UserRole
from core.models.type_hints import UserUID
from core.utils.exception_types import (
    FILE_IO_EXCEPTIONS,
    NEO4J_EXCEPTIONS,
    PARSING_EXCEPTIONS,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

from .config import DEFAULT_MAX_FILE_SIZE_BYTES
from .unified_ingestion_service import UnifiedIngestionService

# Ingestion can fail across three substrates: Neo4j writes, filesystem I/O on
# referenced vault files, and YAML/content parsing of dependent documents.
# Narrow the catch to this union so genuinely unexpected bugs still propagate.
_INGESTION_EXCEPTIONS: tuple[type[BaseException], ...] = (
    *NEO4J_EXCEPTIONS,
    *FILE_IO_EXCEPTIONS,
    *PARSING_EXCEPTIONS,
)

# Entity identifier union covering both Activity Domain (EntityType) and
# non-Entity domains like Group (NonKuDomain).
UploadType = EntityType | NonKuDomain

logger = get_logger("skuel.services.ingestion.user_upload")

# Types users may upload. Activity Domain types and UserEntry are open to all
# authenticated users; Group uploads are additionally gated on
# UserRole.TEACHER (ADR-053). UserEntry uploads carry a ``pipeline:`` field
# that is validated separately by the ingestion preparer (ADR-054) — audio
# pipelines are rejected because /upload is YAML-only.
ALLOWED_UPLOAD_TYPES: frozenset[UploadType] = frozenset(
    {
        EntityType.TASK,
        EntityType.GOAL,
        EntityType.HABIT,
        EntityType.EVENT,
        EntityType.CHOICE,
        EntityType.PRINCIPLE,
        EntityType.USER_ENTRY,
        NonKuDomain.GROUP,
    }
)

# Upload types that require UserRole.TEACHER or higher.
TEACHER_ONLY_UPLOAD_TYPES: frozenset[UploadType] = frozenset({NonKuDomain.GROUP})

# Map detected type string → UploadType for validation
_TYPE_STRING_TO_ENTITY: dict[str, UploadType] = {
    "task": EntityType.TASK,
    "goal": EntityType.GOAL,
    "habit": EntityType.HABIT,
    "event": EntityType.EVENT,
    "choice": EntityType.CHOICE,
    "principle": EntityType.PRINCIPLE,
    "user_entry": EntityType.USER_ENTRY,
    "group": NonKuDomain.GROUP,
}

# Map UploadType → subdirectory name
_TYPE_TO_SUBDIR: dict[UploadType, str] = {
    EntityType.TASK: "tasks",
    EntityType.GOAL: "goals",
    EntityType.HABIT: "habits",
    EntityType.EVENT: "events",
    EntityType.CHOICE: "choices",
    EntityType.PRINCIPLE: "principles",
    EntityType.USER_ENTRY: "user_entries",
    NonKuDomain.GROUP: "groups",
}

VAULT_SUBDIRS: tuple[str, ...] = tuple(_TYPE_TO_SUBDIR.values())

# Limits
MAX_FILES_PER_REQUEST = 50
MAX_FILE_SIZE_BYTES = DEFAULT_MAX_FILE_SIZE_BYTES  # 10 MB


@dataclass(frozen=True)
class FileUploadResult:
    """Result for a single uploaded file.

    ``warnings`` surfaces non-fatal issues — e.g. a UserEntry persisted
    successfully but one of its declared group shares failed (user not a
    member, group missing). The entry exists; the uploader just needs to
    know it did not reach every intended audience.
    """

    filename: str
    success: bool
    entity_type: str | None = None
    uid: str | None = None
    error: str | None = None
    warnings: tuple[str, ...] = ()


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
        user_role: UserRole = UserRole.REGISTERED,
    ) -> Result[UploadBatchResult]:
        """Upload YAML files to user vault and ingest them.

        Args:
            user_uid: Authenticated user's UID
            files: List of (filename, content_bytes) tuples
            user_role: Caller's role — gates teacher-only upload types
                (defaults to REGISTERED for conservative rejection).

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
            result = await self._process_single_file(
                user_uid, vault_path, filename, content, user_role
            )
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
        user_role: UserRole,
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

        # Teacher-only gate (Group uploads require UserRole.TEACHER or higher)
        if entity_type in TEACHER_ONLY_UPLOAD_TYPES and not user_role.has_permission(
            UserRole.TEACHER
        ):
            return FileUploadResult(
                filename=filename,
                success=False,
                entity_type=type_str,
                error=f"Type '{type_str}' requires teacher role",
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
        except _INGESTION_EXCEPTIONS as e:
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
        warnings = _extract_share_warnings(result_data)
        return FileUploadResult(
            filename=filename,
            success=True,
            entity_type=type_str,
            uid=result_data.get("uid"),
            warnings=warnings,
        )


def _extract_share_warnings(result_data: dict[str, Any]) -> tuple[str, ...]:
    """Lift per-target ``ShareOutcome.failed`` entries into human-readable warnings.

    Only UserEntry ingestion populates ``share_outcome``; other types return
    an empty tuple. The shape is ``{"failed": [{"target": ..., "reason": ...}]}``
    as produced by ``ShareOutcome.to_payload()``.
    """
    share_outcome = result_data.get("share_outcome")
    if not isinstance(share_outcome, dict):
        return ()
    failed = share_outcome.get("failed")
    if not isinstance(failed, list):
        return ()
    warnings: list[str] = []
    for item in failed:
        if not isinstance(item, dict):
            continue
        target = str(item.get("target") or "(unknown)")
        reason = str(item.get("reason") or "unknown reason")
        warnings.append(f"Share to {target} failed: {reason}")
    return tuple(warnings)
