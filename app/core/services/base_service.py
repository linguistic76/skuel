"""
Unified Base Service - Relationship-Centric Architecture
========================================================

SKUEL's Entity Type Architecture - Service Foundation
------------------------------------------------------

This module provides the base service class for all entity type services.
Core principle: Everything has relationships - that's what makes SKUEL
powerful as a knowledge graph platform.

**DECOMPOSED**: January 2026 - BaseService now inherits from 7 focused mixins
following Single Responsibility Principle. See /core/services/mixins/ for details.

ENTITY TYPES USING THIS BASE SERVICE (6)
-----------------------------------------

**Activity Services with BaseService (6):**
    1. TasksService(BaseService[TasksOperations, Task])
    2. GoalsService(BaseService[GoalsOperations, Goal])
    3. HabitsService(BaseService[HabitsOperations, Habit])
    4. EventsService(BaseService[EventsOperations, Event])
    5. ChoicesService(BaseService[ChoicesOperations, Choice])
    6. PrinciplesService(BaseService[PrinciplesOperations, Principle])

SERVICES NOT USING THIS BASE SERVICE (examples)
-----------------------------------------

**Finance (NonKuDomain — Firefly III sidecar, ADR-052):**
    7. FinanceService - Standalone facade (admin-only)

**Curriculum Domain Services (3)** - Standalone facades:
    8. KuService - Knowledge Units (ku.)
    9. PsService - PathSteps (ps.)
    10. LpService - Learning Paths (lp.)

**Content/Organization Domains** - Cross-domain composition:
    11. JournalService - Journal workflows
    12. AnalyticsLifePathService - Life goal alignment
    13. AnalyticsService - Statistical aggregation

CROSS-CUTTING INFRASTRUCTURE
--------------------------

**Foundation & Infrastructure (not domains):**
    1. UserContextBuilder - ~240 fields cross-domain state
    2. SearchOperations - Unified search
    3. AskesisService - Life context synthesis
    4. Conversation - Turn-based chat interface

MIXIN COMPOSITION — METHOD INDEX
---------------------------------

ConversionHelpersMixin:
    (no public async methods — provides sync conversion helpers)

CrudOperationsMixin:
    create, get, update, delete, list,
    verify_ownership, get_for_user, update_for_user, delete_for_user
    Hooks: _validate_create, _validate_update (sync, pre-op)
           _post_create, _post_update, _post_delete (async, post-op)

SearchOperationsMixin:
    search, get_by_relationship, search_connected_to, search_by_tags,
    search_array_field, graph_aware_faceted_search, get_by_status,
    get_for_user_filtered, get_by_category, list_user_categories,
    list_all_categories, count

RelationshipOperationsMixin:
    add_relationship, get_relationships, traverse,
    get_prerequisites, get_enables, add_prerequisite, get_hierarchy

TimeQueryMixin:
    get_user_items_in_range_base, get_user_items_in_range,
    get_upcoming, get_overdue, get_active

ContextOperationsMixin:
    get_with_content, get_with_context

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
    /adapters/persistence/neo4j/query/cypher/ - pure-Cypher build_* functions (modular package)
    /core/services/mixins/ - Decomposed mixin implementations
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar, cast

# Import protocols for type constraints and runtime validation
from core.models.enums import SearchVisibility
from core.models.protocols import DomainModelProtocol, DTOProtocol
from core.models.type_hints import EntityUID, UserUID
from core.models.update_contracts import RawChanges, SupportsToChanges
from core.ports import BackendOperations
from core.services.mixins import (
    ContextOperationsMixin,
    ConversionHelpersMixin,
    CrudOperationsMixin,
    RelationshipOperationsMixin,
    SearchOperationsMixin,
    TimeQueryMixin,
)
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.relationship_names import RelationshipName


# Old-style TypeVars (not PEP 695 inline params) so the update type ``U`` can carry a
# PEP 696 *default* while the Ruff lint target stays at py312 (inline ``[U: B = D]`` is
# py313+ syntax the py312 parser rejects). The default (``RawChanges``) keeps the ~53
# non-activity ``BaseService[Op, T]`` instantiations untouched; only the six Activity
# Domains override ``U`` with their frozen ``*UpdateIntent``.
B = TypeVar("B", bound=BackendOperations)
T = TypeVar("T", bound=DomainModelProtocol)
U = TypeVar("U", bound=SupportsToChanges, default=RawChanges)


class BaseService(
    ConversionHelpersMixin[B, T],
    CrudOperationsMixin[B, T, U],
    SearchOperationsMixin[B, T],
    RelationshipOperationsMixin[B, T],
    TimeQueryMixin[B, T],
    ContextOperationsMixin[B, T],
    Generic[B, T, U],
):
    """
    Unified base service class for all SKUEL entities.

    Type Parameters:
        B: Backend type (must implement BackendOperations protocol)
        T: Entity type (must implement DomainModelProtocol - has uid, timestamps, etc.)

    Core features (via mixins):
    1. CRUD operations - everything needs create, read, update, delete
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
        self.logger = get_logger(f"skuel.services.{self.service_name}")  # type: ignore[assignment]  # structlog BoundLogger

        # Sync DomainConfig values onto the instance so mixins that read
        # self._dto_class / self._model_class / self._prerequisite_relationships
        # see the configured values. Without this, services configured via
        # _config (the modern pattern) fall through to the class-level defaults
        # at runtime — prerequisite traversal silently no-ops on the empty default.
        config = self._get_config_cls()
        if config is not None:
            if getattr(config, "dto_class", None) is not None:
                self._dto_class = config.dto_class
            if getattr(config, "model_class", None) is not None:
                self._model_class = config.model_class
            if config.prerequisite_relationships:
                self._prerequisite_relationships = config.prerequisite_relationships

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
        except (AttributeError, NotImplementedError):  # fmt: skip
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
    _config_lookup_label: ClassVar[str | None] = None

    @cached_property
    def entity_label(self) -> str:
        """
        Return the Neo4j base-label for multi-label Cypher matching.

        For the unified :Entity scheme, this is ``"Entity"`` for all domain entities
        (Tasks, Goals, Habits, …, PathSteps). Standalone entities like Ku and Finance
        override this to their own Neo4j label.

        For the **registry-lookup key** (domain-specific: ``"Task"``, ``"Goal"``, …),
        use :attr:`config_lookup_label` instead.

        Priority:
            1. _config.entity_label (from DomainConfig)
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

    @cached_property
    def config_lookup_label(self) -> str:
        """
        Return the LABEL_CONFIGS registry key for this service.

        Distinct from :attr:`entity_label` (the Neo4j base-label). The lookup label is
        the domain-specific key (``"Task"``, ``"Goal"``, ``"PathStep"``, …) used by
        ``context_operations_mixin`` to fetch the ``DomainRelationshipConfig``.

        Priority:
            1. _config.config_lookup_label (from DomainConfig)
            2. _config_lookup_label class attribute (explicit override)
            3. _config.model_class.__name__
            4. _model_class.__name__
            5. entity_label (last-resort fallback)
        """
        config = self._get_config_cls()
        if config and config.config_lookup_label:
            return config.config_lookup_label

        if self._config_lookup_label:
            return self._config_lookup_label

        if config and config.model_class:
            return config.model_class.__name__

        if self._model_class is not None:
            return self._model_class.__name__

        return self.entity_label

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
            2. ("title", "description") (default)

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
            2. "created_at" (default)

        Returns:
            Field name for ordering search results
        """
        return self._get_config_value("search_order_by", "created_at")

    @cached_property
    def category_field(self) -> str:
        """
        Get category field from DomainConfig.

        **OPTIMIZATION (2026-01-31):** Cached property for 50-100x faster access.

        Priority:
            1. _config.category_field (DomainConfig)
            2. "category" (default)

        Returns:
            Field name for category filtering
        """
        return self._get_config_value("category_field", "category")

    @cached_property
    def search_visibility(self) -> SearchVisibility:
        """
        Get the search-visibility declaration from DomainConfig.

        THE scoping input for every search strategy (text, tags, graph
        traversal, faceted). Derivation lives on DomainConfig — explicit
        declaration wins, otherwise ownership relationship implies
        OWNER_ONLY and its absence implies PUBLIC.

        Returns:
            SearchVisibility (OWNER_ONLY when no DomainConfig exists —
            fail-closed default).
        """
        config = self._get_config_cls()
        if config is None:
            return SearchVisibility.OWNER_ONLY
        return config.get_search_visibility()

    @cached_property
    def ownership_property(self) -> str:
        """
        Get the node property the OWNER_ONLY visibility clause filters on.

        Rides with ``search_visibility`` into every clause composition
        (``DomainConfig.ownership_property``, default ``"user_uid"``) so the
        emitted predicate names the property the domain actually writes —
        Group declares ``"owner_uid"`` (ADR-086).

        Returns:
            Property name ("user_uid" when no DomainConfig exists — matches
            the fail-closed OWNER_ONLY default above).
        """
        config = self._get_config_cls()
        if config is None:
            return "user_uid"
        return str(config.ownership_property)

    @cached_property
    def entity_type_value(self) -> str:
        """
        Get THE EntityType value this domain configures, from DomainConfig.

        THE single vocabulary for stamping search-result ``_domain`` — one
        spelling (EntityType values: "task", "path_step", "ku") from producer
        to consumer, replacing the three vocabularies #536 normalized at the
        render boundary. Distinct from ``config_lookup_label`` (a registry key,
        not an EntityType) — the lookup label already carries two jobs; do not
        add a third.

        Returns:
            EntityType value string. Falls back to the lowered lookup label
            only when no DomainConfig exists (a degenerate, unconfigured
            state — every search service carries a DomainConfig).
        """
        config = self._get_config_cls()
        if config is None:
            return self.config_lookup_label.lower()
        return config.get_entity_type_value()

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
    _completed_statuses: ClassVar[list[str]] = []

    # DTO class for conversion - subclasses MUST override
    _dto_class: type[DTOProtocol] | None = None

    # Domain model class - subclasses MUST override
    _model_class: type[T] | None = None

    # Search fields for text search - defaults to ("title", "description")
    _search_fields: ClassVar[tuple[str, ...]] = ("title", "description")

    # Order by field for search results
    _search_order_by: str = "created_at"

    # ========================================================================
    # GRAPH-AWARE FACETED SEARCH CONFIGURATION (January 2026)
    # ========================================================================

    # Graph enrichment patterns for faceted search results
    _graph_enrichment_patterns: ClassVar[
        tuple[tuple[str, str, str] | tuple[str, str, str, str], ...]
    ] = ()

    # ========================================================================
    # CURRICULUM/PREREQUISITE CONFIGURATION (January 2026 - Unified)
    # ========================================================================

    # Prerequisite relationship type(s) to follow. Not ClassVar (like _dto_class):
    # __init__ syncs the instance attribute from DomainConfig.
    _prerequisite_relationships: tuple[RelationshipName, ...] = ()

    # Content field name - where content is stored
    _content_field: str = "content"

    # ========================================================================
    # DOMAIN-SPECIFIC HOOKS (Optional)
    # ========================================================================
    # _validate_create / _validate_update are declared ONCE, on CrudOperationsMixin
    # (which this class inherits) — the same class that invokes them. BaseService
    # used to re-declare both as identical no-ops, shadowing the mixin's; a domain
    # reading either declaration had no way to tell which one `create()` would call.
    # One hook, one owner, next to its caller.
    #
    # Overriding the hook only binds the class that declares the override. A facade
    # that delegates to a sub-service (self.core) does NOT inherit that sub-service's
    # override, so the hook stays a no-op on the facade — see ChoicesService.create
    # (the entity door), which delegates to ChoicesCoreService.create for exactly
    # this reason; the generated route itself now binds to the request door
    # (CRUDRouteConfig.request_create_method).

    def _validate_prerequisites(
        self,
        entity_uid: EntityUID,
        prerequisite_uids: list[str],
    ) -> Result[None]:
        """
        Optional hook for prerequisite relationship validation.

        Override to prevent circular dependencies, validate prerequisite existence, etc.

        Args:
            entity_uid: The entity gaining prerequisites
            prerequisite_uids: UIDs of proposed prerequisites

        Returns:
            Result.ok(None) if valid, Result.fail() if validation fails
        """
        return Result.ok(None)

    # ========================================================================
    # AUDIENCE-AWARE BY-UID READ (ADR-085)
    # ========================================================================

    async def get_visible_to_user(self, uid: str, user_uid: UserUID) -> Result[T]:
        """
        Get an entity by UID only if this user is in its audience.

        THE audience-aware service-to-service by-UID read (ADR-085 §2): the
        domain's own ``search_visibility`` declaration decides the scoping, so
        a direct read and a search of the same domain agree by construction.
        A PUBLIC domain (curriculum) composes no predicate and this read is
        deliberately as open as ``get()``; an OWNER_ONLY domain returns only
        the requesting user's own entity.

        Not-found and not-visible are the SAME outcome (a NotFound error) —
        the 404-equivalent refusal of OWNERSHIP_VERIFICATION.md, preserved
        below the route layer.

        Backend: ``UniversalNeo4jBackend.get_visible_to_user``

        Args:
            uid: Entity UID to read.
            user_uid: The requesting user, referenced by the audience predicate.

        Returns:
            Result[T]: the entity when visible; NotFound error when absent or
            out of audience.
        """
        if not uid:
            return Result.fail(Errors.validation(message="UID is required", field="uid"))
        if not user_uid:
            return Result.fail(Errors.validation(message="user_uid is required", field="user_uid"))

        result = await self.backend.get_visible_to_user(
            uid, user_uid, self.search_visibility, self.ownership_property
        )

        # Not-found and not-visible converge on the same NotFound (backend
        # returns Result.ok(None) for both) — mirrors get()'s conversion.
        if result.is_ok and result.value is None:
            return Result.fail(Errors.not_found(f"Entity {uid} not found"))

        return cast("Result[T]", result)

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

        # raw-write: generic system field bump. The validated/event-firing service contract
        # is the domain `update_<x>(intent)` path; this universal helper writes a single
        # column directly (U is the subclass's narrowed intent type — not constructible here).
        return await self.backend.update(uid, {"progress": progress})

    # -------------------------------------------------------------------------
    # Test-covered health API — no production caller yet (PLANNED)
    # -------------------------------------------------------------------------

    async def ensure_backend_available(self) -> Result[bool]:
        """
        Check that backend is available and working.

        Note: Backend is guaranteed to exist at initialization (fail-fast)
        but this method verifies it's actually functioning.
        """
        try:
            await self.backend.health_check()
            return Result.ok(True)
        except (*NEO4J_EXCEPTIONS, ConnectionError, OSError) as e:
            return Result.fail(
                Errors.integration(service="backend", operation="health_check", message=str(e))
            )
