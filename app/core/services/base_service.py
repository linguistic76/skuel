"""
Unified Base Service - Relationship-Centric Architecture
========================================================

SKUEL's 14-Domain + 4-System Architecture - Service Foundation
--------------------------------------------------------------

This module provides the base service class for **6 of the 14 Domains**.
Core principle: Everything has relationships - that's what makes SKUEL
powerful as a knowledge graph platform.

**DECOMPOSED**: January 2026 - BaseService now inherits from 7 focused mixins
following Single Responsibility Principle. See /core/services/mixins/ for details.

DOMAINS USING THIS BASE SERVICE (6 of 14)
----------------------------------------

**Activity Domain Services with BaseService (6 of 7):**
    1. TasksService(BaseService[TasksOperations, Task])
    2. GoalsService(BaseService[GoalsOperations, Goal])
    3. HabitsService(BaseService[HabitsOperations, Habit])
    4. EventsService(BaseService[EventsOperations, Event])
    5. ChoicesService(BaseService[ChoicesOperations, Choice])
    6. PrinciplesService(BaseService[PrinciplesOperations, Principle])

DOMAINS NOT USING THIS BASE SERVICE (8 of 14)
--------------------------------------------

**Activity Domain (1 of 7)** - Standalone facade:
    7. FinanceService - Expenses and budgets (standalone facade)

**Curriculum Domain Services (3)** - Standalone facades:
    8. KuService - Knowledge Units (ku:)
    9. LsService - Learning Steps (ls:)
    10. LpService - Learning Paths (lp:)

**Content/Organization Domains (3)** - Cross-domain composition:
    11. JournalsService - File processing
    12. AnalyticsLifePathService - Life goal alignment
    13. AnalyticsService - Statistical aggregation

THE 4 CROSS-CUTTING SYSTEMS
--------------------------

**Foundation & Infrastructure (not domains):**
    1. UserContextBuilder - ~240 fields cross-domain state
    2. SearchOperations - Unified search
    3. AskesisService - Life context synthesis
    4. Conversation - Turn-based chat interface

MIXIN COMPOSITION (January 2026)
-------------------------------

BaseService is composed from 7 focused mixins:
    - ConversionHelpersMixin: DTO conversion and result handling
    - CrudOperationsMixin: Core CRUD and ownership-verified CRUD
    - SearchOperationsMixin: Text search, graph search, filtering
    - RelationshipOperationsMixin: Graph relationships and prerequisites
    - TimeQueryMixin: Date-based queries for calendar integration
    - UserProgressMixin: Progress and mastery tracking
    - ContextOperationsMixin: Graph context retrieval and enrichment

Architecture Patterns:
    - Protocol-based dependency injection
    - Relationships as first-class citizens
    - Clean, readable code
    - One path forward (no alternatives)
    - Single Responsibility via mixin composition

Documentation:
    /docs/guides/BASESERVICE_QUICK_START.md - New developer onboarding (< 30 min)
    /docs/reference/SUB_SERVICE_CATALOG.md - Which service does what
    /docs/reference/BASESERVICE_METHOD_INDEX.md - Complete method listing
    /docs/architecture/SERVICE_TOPOLOGY.md - Architecture diagrams

See Also:
    /core/ports/base_service_interface.py - Complete interface (all mixins)
    /core/models/shared_enums.py - Domain enum definitions
    /core/ports/domain_protocols.py - Service interfaces
    /adapters/persistence/neo4j/universal_backend.py - Generic backend
    /core/models/query/cypher/ - CypherGenerator methods (modular package)
    /core/services/mixins/ - Decomposed mixin implementations
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar

# Import protocols for type constraints and runtime validation
from core.models.protocols import DomainModelProtocol, DTOProtocol
from core.models.relationship_names import RelationshipName
from core.ports import BackendOperations
from core.services.mixins import (
    ContextOperationsMixin,
    ConversionHelpersMixin,
    CrudOperationsMixin,
    RelationshipOperationsMixin,
    SearchOperationsMixin,
    TimeQueryMixin,
    UserProgressMixin,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins


# Type variables for backward compatibility
# BaseService uses Python 3.12+ type parameter syntax
B = TypeVar("B", bound=BackendOperations)
T = TypeVar("T", bound=DomainModelProtocol)


class BaseService[B: BackendOperations, T: DomainModelProtocol](
    ConversionHelpersMixin[B, T],
    CrudOperationsMixin[B, T],
    SearchOperationsMixin[B, T],
    RelationshipOperationsMixin[B, T],
    TimeQueryMixin[B, T],
    UserProgressMixin[B, T],
    ContextOperationsMixin[B, T],
):
    """
    Unified base service class for all SKUEL entities.

    Type Parameters:
        B: Backend type (must implement BackendOperations protocol)
        T: Entity type (must implement DomainModelProtocol - has uid, timestamps, etc.)

    Core features (via mixins):
    1. CRUD operations - everything needs create, read, update, DETACH DELETE
    2. Relationship management - the heart of SKUEL
    3. Content handling - many entities have content
    4. Status/Progress tracking - universal concept
    5. Validation patterns - consistent across all services

    All services inherit from this single base.
    """

    # Explicit type annotation for MyPy type inference through inheritance
    backend: B

    # Service name for logging (override in subclasses for hierarchical names like "tasks.search")
    # If not set, defaults to class name
    _service_name: ClassVar[str | None] = None

    def __init__(self, backend: B, service_name: str | None = None) -> None:
        """
        Initialize unified base service.

        FAIL-FAST ARCHITECTURE (per CLAUDE.md):
        Backend is ALWAYS required. No optional backends.
        Services run at full capacity or fail immediately at startup.

        Args:
            backend: Backend implementation (protocol/interface) - REQUIRED
            service_name: Name for logging (defaults to _service_name class attribute or class name)
        """
        # FAIL-FAST: Backend is ALWAYS required
        if not backend:
            service = service_name or self._service_name or self.__class__.__name__
            raise ValueError(
                f"{service} backend is REQUIRED. "
                "SKUEL follows fail-fast architecture - all dependencies must be provided at initialization."
            )

        self.backend = backend

        # Logger initialization: parameter > class attribute > class name
        self.service_name = service_name or self._service_name or self.__class__.__name__
        self.logger = get_logger(f"skuel.services.{self.service_name}")

        # Log initialization
        self.logger.debug(f"{self.service_name} initialized with BackendOperations backend")

        # Early validation: fail-fast on missing configuration
        self._validate_configuration()

    # ========================================================================
    # CONFIGURATION VALIDATION
    # ========================================================================

    def _validate_configuration(self) -> None:
        """
        Validate service configuration at initialization time.

        Fail-fast philosophy: catch configuration errors immediately at startup
        rather than during runtime when methods are called.

        Raises:
            ValueError: If critical configuration is missing or invalid
        """
        # Validate: entity_label is resolvable
        try:
            _ = self.entity_label
        except (AttributeError, NotImplementedError):
            raise ValueError(
                f"{self.service_name}: entity_label not configured. "
                "Set _entity_label class attribute or provide _config with entity_label."
            ) from None

        # Validate: search-enabled services have required configuration
        # Check if service defines _search_fields (indicates search capability)
        if getattr(self.__class__, "_search_fields", None) is not None:
            dto_class = self._get_config_value("dto_class")
            model_class = self._get_config_value("model_class")

            if dto_class is None:
                self.logger.warning(
                    f"{self.service_name}: Search enabled but dto_class not configured. "
                    "Search operations will fail at runtime. "
                    "Set via DomainConfig or _dto_class class attribute."
                )

            if model_class is None:
                self.logger.warning(
                    f"{self.service_name}: Search enabled but model_class not configured. "
                    "Search operations will fail at runtime. "
                    "Set via DomainConfig or _model_class class attribute."
                )

    # ========================================================================
    # CONFIGURATION ACCESS (January 2026 - Class-Level)
    # ========================================================================

    @classmethod
    def _get_config_cls(cls) -> Any:
        """
        Get class-level configuration.

        Returns the DomainConfig for this service class, or None if not configured.
        This is a CLASS-LEVEL constant shared by all instances of the same service class.

        Design Note:
            Configuration is defined once at class definition time and is immutable.
            All instances of the same service class share the exact same _config object.
            This method makes class-level access explicit and semantically correct.

        Returns:
            DomainConfig | None: The service's configuration, or None if not configured

        Example:
            config = TasksService._get_config_cls()
            if config:
                print(config.search_fields) # ('title', 'description')

        See Also:
            /docs/patterns/DOMAIN_CONFIG_PATTERN.md - Configuration patterns
            /core/services/domain_config.py - DomainConfig definition
        """
        return cls._config

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT (Auto-Inferred with Override)
    # ========================================================================

    # Optional: Override entity label if different from model class name
    # Set to a string like "Expense" if the Neo4j label differs from _model_class.__name__
    _entity_label: ClassVar[str | None] = None

    @cached_property
    def entity_label(self) -> str:
        """
        Return the graph label for this entity type.

        **AUTO-INFERENCE (January 2026):** By default, infers from _model_class.__name__.
        Services only need to override via _entity_label class attribute when the
        Neo4j label differs from the model class name.

        **OPTIMIZATION (2026-01-31):** Cached property for 50-100x faster access.

        Priority:
            1. _config.entity_label (from DomainConfig, )
            2. _entity_label class attribute (explicit override)
            3. _config.model_class.__name__ (from DomainConfig)
            4. _model_class.__name__ (auto-inferred)
            5. Class name minus "Service" suffix (fallback)
        """
        # Priority 1: DomainConfig.entity_label
        config = self._get_config_cls()
        if config and config.entity_label:
            return config.entity_label

        # Priority 2: Explicit _entity_label class attribute
        if self._entity_label:
            return self._entity_label

        # Priority 3: DomainConfig.model_class
        if config and config.model_class:
            return config.model_class.__name__

        # Priority 4: Infer from _model_class.__name__
        if self._model_class is not None:
            return self._model_class.__name__

        # Priority 5: Fallback to class name manipulation
        class_name = self.__class__.__name__
        # Remove common suffixes
        for suffix in ("CoreService", "SearchService", "IntelligenceService", "Service"):
            if class_name.endswith(suffix):
                return class_name[: -len(suffix)]
        return class_name

    def _get_config_value(self, attr_name: str, default: Any = None) -> Any:
        """
        Get configuration value from DomainConfig.

        **ONE PATH FORWARD (January 2026):**
        DomainConfig is THE configuration source. Class attribute fallback removed.

        Args:
            attr_name: Attribute name (e.g., "dto_class", "search_fields")
            default: Default value if not found in config

        Returns:
            Configuration value from DomainConfig or default

        Raises:
            AttributeError: If attr_name doesn't exist in DomainConfig (developer error)
        """
        # DomainConfig is THE source of truth (class-level access)
        config = self._get_config_cls()
        if config:
            value = getattr(config, attr_name, None)
            if value is not None:
                return value

        # Fallback to default if not in config
        return default

    # ========================================================================
    # CONFIGURATION PROPERTY WRAPPERS (January 2026 - Standardization)
    # ========================================================================

    @cached_property
    def dto_class(self) -> type[DTOProtocol] | None:
        """
        Get DTO class from config or class attribute.

        **OPTIMIZATION (2026-01-31):** Cached property for 50-100x faster access.

        Priority:
            1. _config.dto_class (DomainConfig)
            2. _dto_class (class attribute)
            3. None

        Returns:
            DTO class or None if not configured
        """
        return self._get_config_value("dto_class")

    @cached_property
    def model_class(self) -> type[T] | None:
        """
        Get domain model class from config or class attribute.

        **OPTIMIZATION (2026-01-31):** Cached property for 50-100x faster access.

        Priority:
            1. _config.model_class (DomainConfig)
            2. _model_class (class attribute)
            3. None

        Returns:
            Domain model class or None if not configured
        """
        return self._get_config_value("model_class")

    @cached_property
    def search_fields(self) -> tuple[str, ...]:
        """
        Get search fields from config or class attribute.

        **OPTIMIZATION (2026-01-31):** Cached property for 50-100x faster access.
        **TYPE CONSISTENCY (2026-01-31):** Returns tuple (immutable, no conversion overhead).

        Priority:
            1. _config.search_fields (DomainConfig)
            2. _search_fields (class attribute)
            3. ("title", "description") (default)

        Returns:
            Tuple of field names for text search
        """
        return self._get_config_value("search_fields", ("title", "description"))

    @cached_property
    def search_order_by(self) -> str:
        """
        Get search order by field from config or class attribute.

        **OPTIMIZATION (2026-01-31):** Cached property for 50-100x faster access.

        Priority:
            1. _config.search_order_by (DomainConfig)
            2. _search_order_by (class attribute)
            3. "created_at" (default)

        Returns:
            Field name for ordering search results
        """
        return self._get_config_value("search_order_by", "created_at")

    @cached_property
    def category_field(self) -> str:
        """
        Get category field from config or class attribute.

        **OPTIMIZATION (2026-01-31):** Cached property for 50-100x faster access.

        Priority:
            1. _config.category_field (DomainConfig)
            2. _category_field (class attribute)
            3. "category" (default)

        Returns:
            Field name for category filtering
        """
        return self._get_config_value("category_field", "category")

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (Class Attributes or DomainConfig)
    # ========================================================================
    # Services can configure behavior via:
    # 1. DomainConfig object
    # 2. Individual class attributes (backward compatible)

    # Optional DomainConfig object - takes priority when set
    _config: ClassVar[Any] = None

    # Date field used for date range queries (e.g., "due_date", "target_date", "created_at")
    _date_field: str = "created_at"

    # Status values to exclude when include_completed=False
    _completed_statuses: ClassVar[tuple[str, ...]] = ()

    # DTO class for conversion - subclasses MUST override
    _dto_class: type[DTOProtocol] | None = None

    # Domain model class - subclasses MUST override
    _model_class: type[T] | None = None

    # Search fields for text search - defaults to ("title", "description")
    _search_fields: ClassVar[tuple[str, ...]] = ("title", "description")

    # Order by field for search results
    _search_order_by: str = "created_at"

    # Category field for get_by_category() and list_categories()
    _category_field: str = "category"

    # ========================================================================
    # GRAPH-AWARE FACETED SEARCH CONFIGURATION (January 2026)
    # ========================================================================

    # Graph enrichment patterns for faceted search results
    _graph_enrichment_patterns: ClassVar[
        tuple[tuple[str, str, str] | tuple[str, str, str, str], ...]
    ] = ()

    # User ownership relationship (None for shared content like KU)
    _user_ownership_relationship: ClassVar[str | None] = RelationshipName.OWNS

    # ========================================================================
    # CURRICULUM/PREREQUISITE CONFIGURATION (January 2026 - Unified)
    # ========================================================================

    # Prerequisite relationship type(s) to follow
    _prerequisite_relationships: ClassVar[tuple[str, ...]] = ()

    # Enables relationship type(s) - inverse of prerequisites
    _enables_relationships: ClassVar[tuple[str, ...]] = ()

    # Content field name - where content is stored
    _content_field: str = "content"

    # Mastery threshold for "mastered" status (0.0-1.0)
    _mastery_threshold: float = 0.7

    # Whether this domain supports user progress tracking
    _supports_user_progress: ClassVar[bool] = False

    # ========================================================================
    # DOMAIN-SPECIFIC HOOKS (Optional)
    # ========================================================================

    def _validate_create(self, entity: T) -> Result[None] | None:
        """
        Optional hook for domain-specific creation validation.

        Override in subclasses to add entity-specific business rules.

        Args:
            entity: The entity being created

        Returns:
            None if valid, Result.fail() if validation fails
        """
        return None

    def _validate_update(self, current: T, updates: dict[str, Any]) -> Result[None] | None:
        """
        Optional hook for domain-specific update validation.

        Override in subclasses to add entity-specific business rules.

        Note: Uses dict[str, Any] because domain-specific validation needs
        to access domain-specific keys (priority, amount, label, etc.)

        Args:
            current: The current entity state
            updates: Dictionary of fields being updated

        Returns:
            None if valid, Result.fail() if validation fails
        """
        return None

    def _validate_content(self, content: str) -> Result[None] | None:
        """
        Optional hook for content validation.

        Override in subclasses to add content-specific validation rules.

        Args:
            content: The content being stored

        Returns:
            None if valid, Result.fail() if validation fails
        """
        return None

    def _validate_prerequisites(
        self,
        entity_uid: str,
        prerequisite_uids: list[str],
    ) -> Result[None] | None:
        """
        Optional hook for prerequisite relationship validation.

        Override to prevent circular dependencies, validate prerequisite existence, etc.

        Args:
            entity_uid: The entity gaining prerequisites
            prerequisite_uids: UIDs of proposed prerequisites

        Returns:
            None if valid, Result.fail() if validation fails
        """
        return None

    # ========================================================================
    # STATUS AND PROGRESS TRACKING
    # ========================================================================

    async def update_progress(self, uid: str, progress: float) -> Result[T]:
        """
        Update progress/mastery for an entity.

        Universal concept across SKUEL:
        - KnowledgeUnits have mastery progress
        - Tasks have completion progress
        - Habits have streak progress
        - Goals have achievement progress
        """
        if not uid:
            return Result.fail(Errors.validation(message="UID is required", field="uid"))

        if progress < 0 or progress > 100:
            return Result.fail(
                Errors.validation(
                    message="Progress must be between 0 and 100",
                    field="progress",
                    user_message="Progress percentage must be between 0% and 100%",
                )
            )

        return await self.update(uid, {"progress": progress})

    async def update_status(
        self,
        uid: str,
        new_status: Any,
        allowed_transitions: dict[Any, builtins.list[Any]] | None = None,
    ) -> Result[T]:
        """Update entity status with optional transition validation."""
        if not uid:
            return Result.fail(Errors.validation(message="UID is required", field="uid"))

        # Get current entity if transition validation needed
        if allowed_transitions:
            current_result = await self.get(uid)
            if current_result.is_error:
                return Result.fail(current_result.expect_error())

            current_status = getattr(current_result.value, "status", None)
            if current_status and current_status != new_status:
                allowed = allowed_transitions.get(current_status, [])
                if new_status not in allowed:
                    allowed_str = ", ".join(str(s) for s in allowed)
                    return Result.fail(
                        Errors.business(
                            rule="status_transition",
                            message=f"Cannot transition from {current_status} to {new_status}. Allowed: {allowed_str}",
                        )
                    )

        return await self.update(uid, {"status": new_status})

    # ========================================================================
    # CONTENT HANDLING
    # ========================================================================

    async def update_content(self, uid: str, content: str) -> Result[T]:
        """
        Update entity content (markdown, description, notes, etc).

        Generic content field - many entities have content:
        - KnowledgeUnits have markdown content
        - Tasks have descriptions
        - Events have notes
        - Goals have detailed plans
        """
        if not uid:
            return Result.fail(Errors.validation(message="UID is required", field="uid"))

        if not content:
            return Result.fail(
                Errors.validation(message="Content cannot be empty", field="content")
            )

        return await self.update(uid, {"content": content})

    # ========================================================================
    # INFRASTRUCTURE
    # ========================================================================

    async def ensure_backend_available(self) -> Result[bool]:
        """
        Check that backend is available and working.

        Note: Backend is guaranteed to exist at initialization (fail-fast)
        but this method verifies it's actually functioning.
        """
        try:
            await self.backend.health_check()
            return Result.ok(True)
        except Exception as e:
            return Result.fail(
                Errors.integration(service="backend", operation="health_check", message=str(e))
            )
