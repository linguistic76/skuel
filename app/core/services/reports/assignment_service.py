"""
Assignment Service
====================

CRUD operations for Assignments (instruction templates).

An Assignment is like Claude/ChatGPT Projects - simple, transparent:
- User creates project with visible instructions
- User can edit instructions anytime
- User controls which LLM model to use
- No hidden logic, no black boxes

Works with any Ku type (assignments, curriculum, etc.)
"""

import json
from datetime import date, datetime
from typing import Any

from core.models.enums import Domain
from core.models.enums.ku_enums import ProcessorType, ProjectScope
from core.models.ku import Assignment, AssignmentDTO, create_assignment
from core.models.relationship_names import RelationshipName
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.services.protocols import get_enum_value
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger(__name__)


class AssignmentService(BaseService):
    """
    Simple CRUD service for Assignments (instruction templates).

    No complex logic - just create, read, update, delete operations.
    Assignments are stored in Neo4j via UniversalNeo4jBackend.
    """

    _config = DomainConfig(
        dto_class=AssignmentDTO,
        model_class=Assignment,
        entity_label="Assignment",
        search_fields=("name", "instructions"),
        search_order_by="created_at",
        user_ownership_relationship="OWNS",
    )

    def __init__(self, backend) -> None:
        """
        Initialize with backend.

        Args:
            backend: UniversalNeo4jBackend[Assignment] instance - REQUIRED
        """
        super().__init__(backend, "assignments")
        self.backend = backend
        self.logger = logger
        logger.info("AssignmentService initialized")

    @property
    def entity_label(self) -> str:
        """Return the graph label for Assignment entities."""
        return "Assignment"

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
        scope: ProjectScope = ProjectScope.PERSONAL,
        due_date: date | None = None,
        processor_type: ProcessorType = ProcessorType.LLM,
        group_uid: str | None = None,
    ) -> Result[Assignment]:
        """
        Create a new Assignment.

        For ASSIGNED scope (teacher assignments):
        - group_uid is required
        - Creates a FOR_GROUP relationship to the target group

        Args:
            user_uid: User who owns this project
            name: Display name
            instructions: Plain text instructions for LLM
            model: LLM model to use
            context_notes: Optional reference materials
            domain: Optional domain categorization
            scope: PERSONAL (default) or ASSIGNED (teacher assignment)
            due_date: Due date for ASSIGNED scope
            processor_type: LLM, HUMAN, or HYBRID
            group_uid: Target group UID for ASSIGNED scope

        Returns:
            Result[Assignment] - The created assignment
        """
        if scope == ProjectScope.ASSIGNED and not group_uid:
            return Result.fail(
                Errors.validation("group_uid is required for assigned projects", field="group_uid")
            )

        uid = UIDGenerator.generate_uid("kp")

        project = create_assignment(
            uid=uid,
            user_uid=user_uid,
            name=name,
            instructions=instructions,
            model=model,
            context_notes=context_notes,
            domain=domain,
            scope=scope,
            due_date=due_date,
            processor_type=processor_type,
            group_uid=group_uid,
        )

        result = await self.backend.create(project)

        if result.is_error:
            self.logger.error(f"Failed to create project: {result.error}")
            return result

        # Create FOR_GROUP relationship for ASSIGNED scope
        if scope == ProjectScope.ASSIGNED and group_uid:
            try:
                await self.backend.driver.execute_query(
                    f"""
                    MATCH (project:Assignment {{uid: $project_uid}})
                    MATCH (group:Group {{uid: $group_uid}})
                    MERGE (project)-[:{RelationshipName.FOR_GROUP}]->(group)
                    RETURN true as success
                    """,
                    project_uid=uid,
                    group_uid=group_uid,
                )
                self.logger.info(f"FOR_GROUP relationship created: {uid} -> {group_uid}")
            except Exception as e:
                self.logger.warning(f"Failed to create FOR_GROUP relationship: {e}")

        self.logger.info(f"Assignment created: {uid} - {name} (scope={scope.value})")
        return Result.ok(project)

    # ========================================================================
    # READ
    # ========================================================================

    @with_error_handling("get_project", error_type="database")
    async def get_project(self, uid: str) -> Result[Assignment | None]:
        """Get a specific Assignment by UID."""
        result = await self.backend.get(uid)
        if result.is_error:
            return result
        return Result.ok(result.value)

    @with_error_handling("list_user_projects", error_type="database")
    async def list_user_projects(
        self, user_uid: str, active_only: bool = True
    ) -> Result[list[Assignment]]:
        """List all assignments for a user."""
        if active_only:
            result = await self.backend.find_by(user_uid=user_uid, is_active=True)
        else:
            result = await self.backend.find_by(user_uid=user_uid)

        if result.is_error:
            return result

        projects = result.value or []
        self.logger.info(f"Found {len(projects)} assignments for user {user_uid}")
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
    ) -> Result[Assignment]:
        """
        Update an Assignment. Only provided fields will be updated.
        """
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return get_result
        if not get_result.value:
            return Result.fail(Errors.not_found(resource="Assignment", identifier=uid))

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
            updates["metadata"] = json.dumps(metadata)

        updates["updated_at"] = datetime.now().isoformat()

        result = await self.backend.update(uid, updates)
        if result.is_error:
            self.logger.error(f"Failed to update assignment {uid}: {result.error}")
            return result

        self.logger.info(f"Assignment updated: {uid}")
        return result

    # ========================================================================
    # ASSIGNMENT QUERIES (ADR-040)
    # ========================================================================

    @with_error_handling("list_group_assignments", error_type="database")
    async def list_group_assignments(self, group_uid: str) -> Result[list[Assignment]]:
        """
        Get all ASSIGNED projects for a group.

        Args:
            group_uid: Group UID

        Returns:
            Result containing list of assigned projects
        """
        result = await self.backend.find_by(group_uid=group_uid, scope="assigned", is_active=True)
        if result.is_error:
            return result

        projects = result.value or []
        self.logger.info(f"Found {len(projects)} assignments for group {group_uid}")
        return Result.ok(projects)

    @with_error_handling("get_student_assignments", error_type="database")
    async def get_student_assignments(self, user_uid: str) -> Result[list[Assignment]]:
        """
        Get all assignments for a student (via MEMBER_OF -> Group <- FOR_GROUP -> Assignment).

        Args:
            user_uid: Student UID

        Returns:
            Result containing list of assigned projects
        """
        records, _, _ = await self.backend.driver.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF}]->(group:Group)
            MATCH (project:Assignment)-[:{RelationshipName.FOR_GROUP}]->(group)
            WHERE project.is_active = true AND project.scope = 'assigned'
            RETURN project
            ORDER BY project.due_date ASC, project.created_at DESC
            """,
            user_uid=user_uid,
        )

        projects = []
        for record in records:
            props = dict(record["project"])
            try:
                project = Assignment(**props)
                projects.append(project)
            except Exception as e:
                self.logger.warning(f"Failed to deserialize assignment: {e}")

        self.logger.info(f"Found {len(projects)} assignments for student {user_uid}")
        return Result.ok(projects)

    # ========================================================================
    # FILE-BASED PROJECT LOADING
    # ========================================================================

    async def load_project_from_file(
        self, file_path: str, user_uid: str, project_uid: str | None = None, model: str = "gpt-4o"
    ) -> Result[Assignment]:
        """
        Load or update an Assignment from a markdown instructions file.
        """
        try:
            from pathlib import Path

            path = Path(file_path)
            if not path.exists():
                return Result.fail(
                    Errors.validation(
                        f"Instructions file not found: {file_path}", field="file_path"
                    )
                )

            instructions = path.read_text(encoding="utf-8")
            name = path.stem.replace("instructions - ", "").replace("instructions-", "").title()
            if not name or name == "Instructions":
                name = path.stem.title()

            if project_uid:
                existing = await self.backend.get(project_uid)
                if existing.is_ok and existing.value:
                    result = await self.update_project(
                        uid=project_uid, instructions=instructions, model=model
                    )
                    self.logger.info(f"Assignment updated from file: {project_uid} - {file_path}")
                    return result
                else:
                    project = create_assignment(
                        uid=project_uid,
                        user_uid=user_uid,
                        name=name,
                        instructions=instructions,
                        model=model,
                    )
                    create_result = await self.backend.create(project)
                    if create_result.is_error:
                        return create_result
                    await self.update_project(
                        uid=project_uid, metadata={"source_file": str(file_path)}
                    )
                    self.logger.info(f"Assignment created from file: {project_uid} - {file_path}")
                    return Result.ok(project)
            else:
                project_result = await self.create_project(
                    user_uid=user_uid,
                    name=name,
                    instructions=instructions,
                    model=model,
                )
                if project_result.is_ok:
                    await self.update_project(
                        uid=project_result.value.uid, metadata={"source_file": str(file_path)}
                    )
                    self.logger.info(
                        f"Assignment created from file: {project_result.value.uid} - {file_path}"
                    )
                return project_result

        except Exception as e:
            self.logger.error(f"Error loading assignment from file {file_path}: {e}")
            return Result.fail(
                Errors.system(
                    f"Failed to load assignment from file: {e!s}", operation="load_project_from_file"
                )
            )

    # ========================================================================
    # DELETE
    # ========================================================================

    @with_error_handling("delete_project", error_type="database")
    async def delete_project(self, uid: str) -> Result[bool]:
        """Delete an Assignment."""
        result = await self.backend.delete(uid)
        if result.is_error:
            return result
        self.logger.info(f"Assignment deleted: {uid}")
        return Result.ok(True)

    async def deactivate_project(self, uid: str) -> Result[Assignment]:
        """Soft-delete by marking assignment as inactive."""
        return await self.update_project(uid, is_active=False)
