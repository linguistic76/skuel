"""
Relationship Decorator
======================

Auto-generates relationship methods on backend instances/classes from RelationshipType enum.
When you add a relationship to shared_enums.py, methods are automatically created.

Key Features:
- Works with BOTH direct UniversalNeo4jBackend instances AND wrapper classes
- Type-safe relationship creation
- Bidirectional relationship support
- Automatic method naming (link_to_goal, link_to_knowledge, etc.)
- Works with RelationshipType enum from shared_enums.py

Updated October 5, 2025:
- Now supports 100% dynamic architecture with direct UniversalNeo4jBackend instances
- Use add_relationships() function for instance-based decoration
"""

from typing import Any, TypeVar

from core.models.enums import RelationshipType
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

T = TypeVar("T")
logger = get_logger(__name__)


def relationship(
    rel_type: RelationshipType,
    target_label: str,
    bidirectional: bool = False,
    reverse_rel_type: RelationshipType | None = None,
):
    """
    Decorator to auto-generate relationship methods on backend classes.

    Adds methods:
    - link_to_{target}(source_uid, target_uid) -> Result[None]
    - unlink_from_{target}(source_uid, target_uid) -> Result[None]
    - get_{target}_relationships(source_uid) -> Result[List[str]]

    Args:
        rel_type: Relationship type from RelationshipType enum,
        target_label: Neo4j label of target node,
        bidirectional: If True, creates reverse relationship too,
        reverse_rel_type: Relationship type for reverse (if bidirectional)

    Usage:
        @relationship(RelationshipType.CONTRIBUTES_TO_GOAL, "Goal")
        @relationship(RelationshipType.REQUIRES_KNOWLEDGE, "Entity")
        class TasksUniversalBackend(UniversalNeo4jBackend[Task]):
            pass

        # Auto-generates:
        # - backend.link_to_goal(task_uid, goal_uid)
        # - backend.unlink_from_goal(task_uid, goal_uid)
        # - backend.get_goal_relationships(task_uid)
        # - backend.link_to_knowledge(task_uid, knowledge_uid)
        # - etc.
    """

    def decorator(cls) -> Any:
        # Get source label from class (assumes UniversalNeo4jBackend pattern)
        # We'll inject methods that use self.label and self.execute_query

        target_name_lower = target_label.lower()

        # Generate link method
        async def link_method(
            self, source_uid: str, target_uid: str, properties: dict[str, Any] | None = None
        ) -> Result[None]:
            """Auto-generated link method."""
            try:
                # Build properties clause if provided
                props_clause = ""
                params = {"source_uid": source_uid, "target_uid": target_uid}

                if properties:
                    # Add properties to relationship
                    props_clause = "SET r += $props"
                    params["props"] = properties

                query = f"""
                MATCH (s:{self.label} {{uid: $source_uid}})
                MATCH (t:{target_label} {{uid: $target_uid}})
                MERGE (s)-[r:{rel_type.value}]->(t)
                {props_clause}
                RETURN r
                """

                result = await self.execute_query(query, params)
                if result.is_error:
                    return Result.fail(result.expect_error())

                # If bidirectional, create reverse relationship
                if bidirectional and reverse_rel_type:
                    reverse_query = f"""
                    MATCH (s:{self.label} {{uid: $source_uid}})
                    MATCH (t:{target_label} {{uid: $target_uid}})
                    MERGE (t)-[r:{reverse_rel_type.value}]->(s)
                    RETURN r
                    """
                    result = await self.execute_query(reverse_query, params)
                    if result.is_error:
                        return Result.fail(result.expect_error())

                self.logger.info(
                    f"Linked {self.label}:{source_uid} -{rel_type.value}-> {target_label}:{target_uid}"
                )
                return Result.ok(None)

            except Exception as e:
                self.logger.error(f"Failed to create relationship: {e}")
                return Result.fail(
                    Errors.database(
                        operation=f"link_to_{target_name_lower}",
                        message=f"Relationship creation failed: {e}",
                        entity=self.label,
                    )
                )

        # Generate unlink method
        async def unlink_method(self, source_uid: str, target_uid: str) -> Result[None]:
            """Auto-generated unlink method."""
            try:
                query = f"""
                MATCH (s:{self.label} {{uid: $source_uid}})-[r:{rel_type.value}]->(t:{target_label} {{uid: $target_uid}})
                DELETE r
                RETURN count(*) as deleted
                """

                params = {"source_uid": source_uid, "target_uid": target_uid}

                result = await self.execute_query(query, params)
                if result.is_error:
                    return Result.fail(result.expect_error())

                if not result.value:
                    return Result.fail(
                        Errors.not_found(
                            resource=f"{self.label}-{target_label}",
                            identifier=f"{source_uid}→{target_uid}",
                        )
                    )

                # If bidirectional, delete reverse relationship
                if bidirectional and reverse_rel_type:
                    reverse_query = f"""
                    MATCH (t:{target_label} {{uid: $target_uid}})-[r:{reverse_rel_type.value}]->(s:{self.label} {{uid: $source_uid}})
                    DELETE r
                    RETURN count(*) as deleted
                    """
                    await self.execute_query(reverse_query, params)

                self.logger.info(
                    f"Unlinked {self.label}:{source_uid} -{rel_type.value}-> {target_label}:{target_uid}"
                )
                return Result.ok(None)

            except Exception as e:
                self.logger.error(f"Failed to delete relationship: {e}")
                return Result.fail(
                    Errors.database(
                        operation=f"unlink_from_{target_name_lower}",
                        message=f"Relationship deletion failed: {e}",
                        entity=self.label,
                    )
                )

        # Generate get relationships method
        async def get_relationships_method(self, source_uid: str) -> Result[list[str]]:
            """Auto-generated get relationships method."""
            try:
                query = f"""
                MATCH (s:{self.label} {{uid: $source_uid}})-[:{rel_type.value}]->(t:{target_label})
                RETURN t.uid as target_uid
                """

                params = {"source_uid": source_uid}

                result = await self.execute_query(query, params)
                if result.is_error:
                    return Result.fail(result.expect_error())

                target_uids = [record["target_uid"] for record in result.value]

                return Result.ok(target_uids)

            except Exception as e:
                self.logger.error(f"Failed to get relationships: {e}")
                return Result.fail(
                    Errors.database(
                        operation=f"get_{target_name_lower}_relationships",
                        message=f"Get relationships failed: {e}",
                        entity=self.label,
                    )
                )

        # Attach methods to class
        setattr(cls, f"link_to_{target_name_lower}", link_method)
        setattr(cls, f"unlink_from_{target_name_lower}", unlink_method)
        setattr(cls, f"get_{target_name_lower}_relationships", get_relationships_method)

        # Track registered relationships for introspection
        if not isinstance(getattr(cls, "_registered_relationships", None), list):
            cls._registered_relationships = []

        cls._registered_relationships.append(
            {
                "rel_type": rel_type,
                "target_label": target_label,
                "bidirectional": bidirectional,
                "reverse_rel_type": reverse_rel_type,
            }
        )

        logger.debug(
            f"Registered relationship methods for {cls.__name__}: "
            f"link_to_{target_name_lower}, unlink_from_{target_name_lower}, get_{target_name_lower}_relationships"
        )

        return cls

    return decorator


def relationships(*rel_configs: Any):
    """
    Multi-relationship decorator for registering multiple relationships at once.

    Args:
        *rel_configs: Tuples of (rel_type, target_label, bidirectional, reverse_rel_type),

    Usage:
        @relationships(
            (RelationshipType.CONTRIBUTES_TO_GOAL, "Goal", False, None),
            (RelationshipType.REQUIRES_KNOWLEDGE, "Entity", False, None),
            (RelationshipType.BLOCKED_BY, "Task", True, RelationshipType.BLOCKS)
        )
        class TasksUniversalBackend(UniversalNeo4jBackend[Task]):
            pass
    """

    def decorator(cls) -> Any:
        for config in rel_configs:
            rel_type, target_label = config[0], config[1]
            bidirectional = config[2] if len(config) > 2 else False
            reverse_rel_type = config[3] if len(config) > 3 else None

            # Apply single relationship decorator
            cls = relationship(rel_type, target_label, bidirectional, reverse_rel_type)(cls)

        return cls

    return decorator


def get_registered_relationships(backend_class: type) -> list[dict[str, Any]]:
    """
    Get all registered relationships for a backend class.

    Args:
        backend_class: Backend class decorated with @relationship,

    Returns:
        List of relationship configurations
    """
    return getattr(backend_class, "_registered_relationships", [])


def add_relationships(backend_instance, *rel_configs: Any):
    """
    Add relationship methods to a UniversalNeo4jBackend instance (100% dynamic pattern).

    This function enables the 100% dynamic architecture by adding relationship methods
    to backend instances created directly without wrapper classes.

    Args:
        backend_instance: UniversalNeo4jBackend instance
        *rel_configs: Tuples of (rel_type, target_label, bidirectional, reverse_rel_type)

    Returns:
        The same backend instance with relationship methods added,

    Usage:
        # 100% Dynamic Pattern (October 2025)
        tasks_backend = UniversalNeo4jBackend[Task](driver, "Task", Task)
        tasks_backend = add_relationships(
            tasks_backend,
            (RelationshipType.CONTRIBUTES_TO_GOAL, "Goal", False, None),
            (RelationshipType.REQUIRES_KNOWLEDGE, "Entity", False, None)
        )

        # Now you can use auto-generated methods:
        await tasks_backend.link_to_goal(task_uid, goal_uid)
        await tasks_backend.link_to_knowledge(task_uid, knowledge_uid)

    Note: This replaces the old wrapper class pattern:
        # OLD PATTERN (deprecated):
        @relationship(...)
        class TaskBackend(UniversalNeo4jBackend[Task]):
            pass
    """
    # Track registered relationships
    if not isinstance(getattr(backend_instance, "_registered_relationships", None), list):
        backend_instance._registered_relationships = []

    for config in rel_configs:
        rel_type, target_label = config[0], config[1]
        bidirectional = config[2] if len(config) > 2 else False
        reverse_rel_type = config[3] if len(config) > 3 else None

        target_name_lower = target_label.lower()

        # Generate link method (bound to instance)
        async def link_method(
            source_uid: str,
            target_uid: str,
            properties: dict[str, Any] | None = None,
            _backend=backend_instance,
            _rel_type=rel_type,
            _target_label=target_label,
            _bidirectional=bidirectional,
            _reverse_rel_type=reverse_rel_type,
            _target_name_lower=target_name_lower,
        ) -> Result[None]:
            """Auto-generated link method."""
            try:
                props_clause = ""
                params = {"source_uid": source_uid, "target_uid": target_uid}

                if properties:
                    props_clause = "SET r += $props"
                    params["props"] = properties

                query = f"""
                MATCH (s:{_backend.label} {{uid: $source_uid}})
                MATCH (t:{_target_label} {{uid: $target_uid}})
                MERGE (s)-[r:{_rel_type.value}]->(t)
                {props_clause}
                RETURN r
                """

                result = await _backend.execute_query(query, params)
                if result.is_error:
                    return Result.fail(result.expect_error())

                if _bidirectional and _reverse_rel_type:
                    reverse_query = f"""
                    MATCH (s:{_backend.label} {{uid: $source_uid}})
                    MATCH (t:{_target_label} {{uid: $target_uid}})
                    MERGE (t)-[r:{_reverse_rel_type.value}]->(s)
                    RETURN r
                    """
                    result = await _backend.execute_query(reverse_query, params)
                    if result.is_error:
                        return Result.fail(result.expect_error())

                _backend.logger.info(
                    f"Linked {_backend.label}:{source_uid} -{_rel_type.value}-> {_target_label}:{target_uid}"
                )
                return Result.ok(None)

            except Exception as e:
                _backend.logger.error(f"Failed to create relationship: {e}")
                return Result.fail(
                    Errors.database(
                        operation=f"link_to_{_target_name_lower}",
                        message=f"Relationship creation failed: {e}",
                        entity=_backend.label,
                    )
                )

        # Generate unlink method
        async def unlink_method(
            source_uid: str,
            target_uid: str,
            _backend=backend_instance,
            _rel_type=rel_type,
            _target_label=target_label,
            _bidirectional=bidirectional,
            _reverse_rel_type=reverse_rel_type,
            _target_name_lower=target_name_lower,
        ) -> Result[None]:
            """Auto-generated unlink method."""
            try:
                query = f"""
                MATCH (s:{_backend.label} {{uid: $source_uid}})-[r:{_rel_type.value}]->(t:{_target_label} {{uid: $target_uid}})
                DELETE r
                RETURN count(*) as deleted
                """

                params = {"source_uid": source_uid, "target_uid": target_uid}

                result = await _backend.execute_query(query, params)
                if result.is_error:
                    return Result.fail(result.expect_error())

                if not result.value:
                    return Result.fail(
                        Errors.not_found(
                            resource=f"{_backend.label}-{_target_label}",
                            identifier=f"{source_uid}→{target_uid}",
                        )
                    )

                if _bidirectional and _reverse_rel_type:
                    reverse_query = f"""
                    MATCH (t:{_target_label} {{uid: $target_uid}})-[r:{_reverse_rel_type.value}]->(s:{_backend.label} {{uid: $source_uid}})
                    DELETE r
                    RETURN count(*) as deleted
                    """
                    await _backend.execute_query(reverse_query, params)

                _backend.logger.info(
                    f"Unlinked {_backend.label}:{source_uid} -{_rel_type.value}-> {_target_label}:{target_uid}"
                )
                return Result.ok(None)

            except Exception as e:
                _backend.logger.error(f"Failed to delete relationship: {e}")
                return Result.fail(
                    Errors.database(
                        operation=f"unlink_from_{_target_name_lower}",
                        message=f"Relationship deletion failed: {e}",
                        entity=_backend.label,
                    )
                )

        # Generate get relationships method
        async def get_relationships_method(
            source_uid: str,
            _backend=backend_instance,
            _rel_type=rel_type,
            _target_label=target_label,
            _target_name_lower=target_name_lower,
        ) -> Result[list[str]]:
            """Auto-generated get relationships method."""
            try:
                query = f"""
                MATCH (s:{_backend.label} {{uid: $source_uid}})-[:{_rel_type.value}]->(t:{_target_label})
                RETURN t.uid as target_uid
                """

                params = {"source_uid": source_uid}

                result = await _backend.execute_query(query, params)
                if result.is_error:
                    return Result.fail(result.expect_error())

                target_uids = [record["target_uid"] for record in result.value]

                return Result.ok(target_uids)

            except Exception as e:
                _backend.logger.error(f"Failed to get relationships: {e}")
                return Result.fail(
                    Errors.database(
                        operation=f"get_{_target_name_lower}_relationships",
                        message=f"Get relationships failed: {e}",
                        entity=_backend.label,
                    )
                )

        # Attach methods to instance
        setattr(backend_instance, f"link_to_{target_name_lower}", link_method)
        setattr(backend_instance, f"unlink_from_{target_name_lower}", unlink_method)
        setattr(
            backend_instance, f"get_{target_name_lower}_relationships", get_relationships_method
        )

        # Track registration
        backend_instance._registered_relationships.append(
            {
                "rel_type": rel_type,
                "target_label": target_label,
                "bidirectional": bidirectional,
                "reverse_rel_type": reverse_rel_type,
            }
        )

        logger.debug(
            f"Added relationship methods to {backend_instance.label} instance: "
            f"link_to_{target_name_lower}, unlink_from_{target_name_lower}, get_{target_name_lower}_relationships"
        )

    return backend_instance
