"""
Journal Project Service
=======================

CRUD operations for Journal Projects.

A Journal Project is like Claude/ChatGPT Projects - simple, transparent:
- User creates project with visible instructions
- User can edit instructions anytime
- User controls which LLM model to use
- No hidden logic, no black boxes

Following SKUEL principles:
- Transparent: All instructions visible
- User-controlled: User decides when to use projects
- Simple: Just CRUD operations, no complexity
"""

import json
from datetime import datetime
from typing import Any

from core.models.journal import (
    JournalProjectPure,
    create_journal_project,
)
from core.models.shared_enums import Domain
from core.services.base_service import BaseService
from core.services.protocols import get_enum_value
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger(__name__)


class JournalProjectService(BaseService):
    """
    Simple CRUD service for journal projects.

    No complex logic - just create, read, update, DETACH DELETE operations.
    Projects are stored in Neo4j via UniversalNeo4jBackend.


    Source Tag: "journal_project_service_explicit"
    - Format: "journal_project_service_explicit" for user-created relationships
    - Format: "journal_project_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from journal_project metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(self, backend) -> None:
        """
        Initialize with backend.

        FAIL-FAST ARCHITECTURE (per CLAUDE.md):
        Backend is ALWAYS required. No optional backends.

        Args:
            backend: UniversalNeo4jBackend[JournalProjectPure] instance - REQUIRED
        """
        super().__init__(backend, "journal_projects")
        self.backend = backend
        self.logger = logger
        logger.info("JournalProjectService initialized")

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for JournalProject entities."""
        return "JournalProject"

    # ========================================================================
    # CREATE
    # ========================================================================

    @with_error_handling("create_project", error_type="database")
    async def create_project(
        self,
        user_uid: str,
        name: str,
        instructions: str,
        model: str = "claude-3-5-sonnet-20241022",
        context_notes: list[str] | None = None,
        domain: Domain | None = None,
    ) -> Result[JournalProjectPure]:
        """
        Create a new journal project.

        Args:
            user_uid: User who owns this project,
            name: Display name (e.g., "Daily Reflection"),
            instructions: Plain text instructions for LLM,
            model: LLM model to use,
            context_notes: Optional reference materials,
            domain: Optional domain categorization

        Returns:
            Result[JournalProjectPure] - The created project
        """
        # Generate UID
        uid = UIDGenerator.generate_uid("jp")

        # Create domain model
        project = create_journal_project(
            uid=uid,
            user_uid=user_uid,
            name=name,
            instructions=instructions,
            model=model,
            context_notes=context_notes,
            domain=domain,
        )

        # Store in backend
        result = await self.backend.create(project)

        if result.is_error:
            self.logger.error(f"Failed to create project: {result.error}")
            return result

        self.logger.info(f"✅ Journal project created: {uid} - {name}")
        return Result.ok(project)

    # ========================================================================
    # READ
    # ========================================================================

    @with_error_handling("get_project", error_type="database")
    async def get_project(self, uid: str) -> Result[JournalProjectPure | None]:
        """
        Get a specific journal project by UID.

        Args:
            uid: Project UID

        Returns:
            Result[Optional[JournalProjectPure]]
        """
        result = await self.backend.get(uid)

        if result.is_error:
            return result

        return Result.ok(result.value)

    @with_error_handling("list_user_projects", error_type="database")
    async def list_user_projects(
        self, user_uid: str, active_only: bool = True
    ) -> Result[list[JournalProjectPure]]:
        """
        List all projects for a user.

        Args:
            user_uid: User UID,
            active_only: If True, only return active projects

        Returns:
            Result[List[JournalProjectPure]]
        """
        if active_only:
            result = await self.backend.find_by(user_uid=user_uid, is_active=True)
        else:
            result = await self.backend.find_by(user_uid=user_uid)

        if result.is_error:
            return result

        projects = result.value or []
        self.logger.info(f"Found {len(projects)} projects for user {user_uid}")
        return Result.ok(projects)

    # ========================================================================
    # UPDATE
    # ========================================================================

    @with_error_handling("update_project", error_type="database")
    async def update_project(
        self,
        uid: str,
        name: str | None = None,
        instructions: str | None = None,
        model: str | None = None,
        context_notes: list[str] | None = None,
        domain: Domain | None = None,
        is_active: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Result[JournalProjectPure]:
        """
        Update a journal project.

        Only provided fields will be updated.

        Args:
            uid: Project UID,
            name: New name (optional),
            instructions: New instructions (optional),
            model: New model (optional),
            context_notes: New context notes (optional),
            domain: New domain (optional),
            is_active: New active status (optional),
            metadata: New metadata (optional)

        Returns:
            Result[JournalProjectPure] - Updated project
        """
        # Get existing project
        get_result = await self.backend.get(uid)

        if get_result.is_error:
            return get_result

        if not get_result.value:
            return Result.fail(Errors.not_found(resource="JournalProject", identifier=uid))

        # Build updates dict with only the fields that changed
        updates: dict[str, Any] = {}

        if name is not None:
            updates["name"] = name
        if instructions is not None:
            updates["instructions"] = instructions
        if model is not None:
            updates["model"] = model
        if context_notes is not None:
            updates["context_notes"] = context_notes
        if domain is not None:
            updates["domain"] = get_enum_value(domain)
        if is_active is not None:
            updates["is_active"] = is_active
        if metadata is not None:
            # JSON-encode metadata dict for Neo4j storage (Neo4j doesn't support nested dicts)
            updates["metadata"] = json.dumps(metadata)

        updates["updated_at"] = datetime.now().isoformat()

        # Update via backend
        result = await self.backend.update(uid, updates)

        if result.is_error:
            self.logger.error(f"Failed to update project {uid}: {result.error}")
            return result

        self.logger.info(f"✅ Journal project updated: {uid}")
        return result

    # ========================================================================
    # FILE-BASED PROJECT LOADING
    # ========================================================================

    async def load_project_from_file(
        self, file_path: str, user_uid: str, project_uid: str | None = None, model: str = "gpt-4o"
    ) -> Result[JournalProjectPure]:
        """
        Load or update a journal project from a markdown instructions file.

        This enables editable instruction files that can be reloaded.

        Args:
            file_path: Path to markdown file with instructions,
            user_uid: User who owns this project,
            project_uid: Optional existing project UID (update) or None (create),
            model: LLM model to use (default: gpt-4o)

        Returns:
            Result[JournalProjectPure] - The loaded/updated project
        """
        try:
            from pathlib import Path

            # Read instructions from file
            path = Path(file_path)
            if not path.exists():
                return Result.fail(
                    Errors.validation(
                        f"Instructions file not found: {file_path}", field="file_path"
                    )
                )

            instructions = path.read_text(encoding="utf-8")

            # Extract project name from filename
            # "instructions - transcripts 0.md" → "Transcripts 0"
            name = path.stem.replace("instructions - ", "").replace("instructions-", "").title()
            if not name or name == "Instructions":
                name = path.stem.title()

            # Check if project_uid provided and if project exists
            if project_uid:
                # Check if project exists
                existing = await self.backend.get(project_uid)

                if existing.is_ok and existing.value:
                    # Update existing project
                    result = await self.update_project(
                        uid=project_uid, instructions=instructions, model=model
                    )
                    self.logger.info(f"✅ Project updated from file: {project_uid} - {file_path}")
                    return result
                else:
                    # Create new project with specific UID
                    from core.models.journal import create_journal_project

                    project = create_journal_project(
                        uid=project_uid,
                        user_uid=user_uid,
                        name=name,
                        instructions=instructions,
                        model=model,
                        context_notes=None,
                        domain=None,
                    )

                    # Store in backend
                    create_result = await self.backend.create(project)

                    if create_result.is_error:
                        return create_result

                    # Store file path in metadata
                    await self.update_project(
                        uid=project_uid, metadata={"source_file": str(file_path)}
                    )

                    self.logger.info(
                        f"✅ Project created from file with specific UID: {project_uid} - {file_path}"
                    )
                    return Result.ok(project)
            else:
                # Create new project with auto-generated UID
                project_result = await self.create_project(
                    user_uid=user_uid,
                    name=name,
                    instructions=instructions,
                    model=model,
                    domain=None,
                )

                if project_result.is_ok:
                    # Store file path in metadata for reloading
                    await self.update_project(
                        uid=project_result.value.uid, metadata={"source_file": str(file_path)}
                    )
                    self.logger.info(
                        f"✅ Project created from file: {project_result.value.uid} - {file_path}"
                    )

                return project_result

        except Exception as e:
            self.logger.error(f"Error loading project from file {file_path}: {e}")
            return Result.fail(
                Errors.system(
                    f"Failed to load project from file: {e!s}", operation="load_project_from_file"
                )
            )

    @with_error_handling("reload_project_from_file", error_type="database")
    async def reload_project_from_file(self, uid: str) -> Result[JournalProjectPure]:
        """
        Reload a project's instructions from its source file.

        The project must have a 'source_file' in metadata.

        Args:
            uid: Project UID

        Returns:
            Result[JournalProjectPure] - The reloaded project
        """
        # Get existing project
        result = await self.get_project(uid)

        if result.is_error or not result.value:
            return Result.fail(result.expect_error())

        project = result.value

        # Check if project has source file
        source_file = project.metadata.get("source_file") if project.metadata else None

        if not source_file:
            return Result.fail(
                Errors.validation(
                    "Project does not have a source_file in metadata", field="source_file"
                )
            )

        # Reload from file
        return await self.load_project_from_file(
            file_path=source_file,
            user_uid=project.user_uid,
            project_uid=uid,
            model=project.model,
        )

    # ========================================================================
    # DELETE
    # ========================================================================

    @with_error_handling("delete_project", error_type="database")
    async def delete_project(self, uid: str) -> Result[bool]:
        """
        DETACH DELETE a journal project.

        Args:
            uid: Project UID

        Returns:
            Result[bool] - True if deleted
        """
        result = await self.backend.delete(uid)

        if result.is_error:
            return result

        self.logger.info(f"✅ Journal project deleted: {uid}")
        return Result.ok(True)

    async def deactivate_project(self, uid: str) -> Result[JournalProjectPure]:
        """
        Soft-DETACH DELETE by marking project as inactive.

        Args:
            uid: Project UID

        Returns:
            Result[JournalProjectPure] - Deactivated project
        """
        return await self.update_project(uid, is_active=False)
