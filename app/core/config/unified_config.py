"""
SKUEL Unified Configuration - Ports + Adapters Architecture
============================================================

Core configuration system aligned with hexagonal architecture.
Single source of truth for all configuration in the system.

Architecture:
- Pure configuration dataclasses (no business logic)
- Environment-based configuration
- Type-safe configuration access
- Dependency injection support

Based on legacy/old_structure/config but adapted for clean architecture.
"""

__version__ = "1.0"


import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from core.constants import SYSTEM_USER_UID
from core.models.enums import EntityType
from core.utils.logging import get_logger

logger = get_logger("skuel.config")

# ============================================================================
# CREDENTIAL HELPER
# ============================================================================


def _get_neo4j_password() -> str:
    """
    Get Neo4j password from encrypted credential store.

    `get_credential(..., fallback_to_env=True)` already handles the
    missing-master-key case internally by falling back to `os.getenv`,
    so we don't need a second layer of fallback here.
    """
    from core.config.credential_store import get_credential

    return get_credential("NEO4J_PASSWORD", fallback_to_env=True) or ""


# ============================================================================
# CORE ARCHITECTURE ENUMS
# ============================================================================


class Environment(StrEnum):
    """System environment definition"""

    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class SchemaVersion(StrEnum):
    """Schema versions for evolution tracking"""

    V3_0 = "3.0"  # Current clean architecture version
    V3_1 = "3.1"  # Ports + Adapters enhanced


# ============================================================================
# PORT CONFIGURATIONS (Inbound)
# ============================================================================


@dataclass
class APIConfig:
    """REST API configuration for inbound port"""

    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    reload: bool = False
    cors_origins: list[str] = field(default_factory=list)
    api_prefix: str = "/api"
    docs_url: str = "/docs"
    openapi_url: str = "/openapi.json"

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100
    rate_limit_period: int = 60  # seconds

    @classmethod
    def from_env(cls) -> "APIConfig":
        """Create config from environment variables"""
        return cls(
            # APP_* is THE env naming for these (matches .env.example and both
            # compose files). The former API_* reads were a dead-knob split:
            # every env file in the repo said APP_PORT while the code read
            # API_PORT, so containers silently listened on the 8000 default.
            host=os.getenv("APP_HOST", "0.0.0.0"),
            port=int(os.getenv("APP_PORT", "8000")),
            debug=os.getenv("APP_DEBUG", "false").lower() == "true",
            reload=os.getenv("APP_RELOAD", "false").lower() == "true",
        )


def _default_relationship_type_weights() -> dict[str, float]:
    # Keyed by the namespaced SemanticRelationshipType value (the `semantic_type`
    # edge property), not the coarse RelationshipName edge type. Since Phase 1 of
    # the semantic-relationship-layer roadmap, many semantic predicates collapse
    # onto one RelationshipName (e.g. several onto RELATED_TO); the precise
    # predicate survives only in `semantic_type`, so weight tuning must key on it.
    # get_semantic_relationships returns COALESCE(r.semantic_type, type(r)).
    return {
        # Learning domain - high importance
        "learn:requires_theoretical_understanding": 1.0,
        "learn:requires_practical_application": 0.9,
        "learn:requires_conceptual_foundation": 0.9,
        "learn:builds_mental_model": 0.8,
        "learn:provides_foundation_for": 0.8,
        "learn:extends_pattern": 0.7,
        # Task domain - medium importance
        "task:blocks_until_complete": 1.0,
        "task:enables_start_of": 0.9,
        "task:contributes_to_goal": 0.8,
        # Cross-domain - medium importance
        "cross:applies_knowledge_to": 0.8,
        "cross:practices_via_habit": 0.7,
        "cross:implements_via_task": 0.7,
        # Conceptual - lower importance
        "cross:related_to": 0.5,
        "learn:analogous_to": 0.6,
        "concept:part_of_system": 0.6,
    }


@dataclass
class VectorSearchConfig:
    """
    Vector search configuration for semantic search.

    Centralizes all vector search parameters to avoid hardcoded values.
    Entity-specific thresholds optimize precision vs recall trade-offs.

    Created: January 2026 (Semantic Search Architecture Improvement)
    See: /docs/architecture/SEARCH_ARCHITECTURE.md
    """

    # Default search parameters
    default_limit: int = 10
    default_min_score: float = 0.7
    batch_size: int = 25

    # Entity-specific minimum similarity thresholds
    # Higher values = more precision, lower recall
    ku_min_score: float = 0.75  # Knowledge requires high semantic similarity
    task_min_score: float = 0.65  # Tasks allow broader matching
    goal_min_score: float = 0.70  # Goals need moderate precision
    habit_min_score: float = 0.70  # Habits similar to goals
    event_min_score: float = 0.65  # Events similar to tasks
    path_step_min_score: float = 0.75  # Learning steps like knowledge
    learning_path_min_score: float = 0.75  # Paths like the steps they hold

    # Lesson-BODY chunk search (SearchRouter body-chunk augmentation).
    # Short body-phrase queries score below the strict 0.7 ContentChunk default
    # (a matched passage inside a long chunk lands ~0.70), while off-topic /
    # nonsense queries floor at ~0.66 against this corpus. 0.68 is the empirically
    # measured gap: admits real body matches, rejects the noise ceiling so the
    # /search empty-state still holds for gibberish. See SEARCH_ARCHITECTURE.md.
    body_chunk_search_min_score: float = 0.68

    # Node→node "Related concepts" lens (Ku + PathStep detail pages).
    # ku_min_score=0.75 is calibrated for text→entity queries and is too strict
    # for node→node similarity, which scores lower across the board. Full-corpus
    # sweep (121 Kus, top-10 each, 2026-07-10): rank-1 neighbour median 0.78;
    # weak cross-topic pairs ceiling ~0.70-0.71, while the 0.71-0.72 band is
    # already defensible — 0.72 admits real neighbours with a margin band over
    # the noise ceiling. At 0.72, 109/121 Kus keep >=1 neighbour (avg 3.9 of
    # limit 5). Applied to PathStep→PathStep too (13-node corpus, thin lists
    # accepted by design). Full distribution tables: the "Related concepts"
    # PR (feat/related-concepts-similarity).
    ku_similar_min_score: float = 0.72
    related_concepts_limit: int = 5  # Chip-row cap on the detail pages

    # Hybrid search weights (0.0-1.0)
    vector_weight: float = 0.5  # 50% vector similarity
    text_weight: float = 0.5  # 50% full-text match

    # RRF (Reciprocal Rank Fusion) parameters
    rrf_k: int = 60  # Standard RRF k value
    # RRF scores live on a 0.0-0.05 scale (not 0-1) — threshold accordingly
    min_rrf_score: float = 0.001

    # Semantic relationship boosting
    semantic_boost_weight: float = 0.3  # 30% semantic, 70% vector similarity
    semantic_boost_enabled: bool = True

    # Relationship type importance weights (higher = more important)
    # Used to weight different semantic relationships when boosting scores
    relationship_type_weights: dict[str, float] = field(
        default_factory=_default_relationship_type_weights
    )

    # Learning state boost/penalty multipliers
    # Applied to search results based on user's learning progress
    learning_state_boost_mastered: float = -0.2  # -20% penalty (already know)
    learning_state_boost_in_progress: float = 0.1  # +10% boost (currently learning)
    learning_state_boost_viewed: float = 0.0  # No change (neutral)
    learning_state_boost_not_started: float = 0.15  # +15% boost (discovery)

    def get_min_score_for_entity(self, entity_type: EntityType | str) -> float:
        """
        Get minimum similarity score for specific entity type.

        Keys are the CANONICAL Neo4j labels (plus the `entity` base label and
        the `EntityType` values, which differ in spelling: `path_step` vs
        `PathStep`). Both spellings are registered because callers arrive from
        both directions — a miss silently returns the generic default rather
        than the calibrated threshold, which is how `Ku` and `PathStep` were
        searched at 0.70 instead of 0.75 (Codex, PR #1074). The retired
        `lpstep` spelling is gone; that label became `PathStep` and its indexes
        are actively dropped as stale by the schema manager.

        Args:
            entity_type: Entity type enum, EntityType value, or Neo4j label

        Returns:
            Minimum similarity score (0.0-1.0)
        """
        entity_lower = (
            entity_type.value.lower()
            if isinstance(entity_type, EntityType)
            else entity_type.lower()
        )
        mapping = {
            # Base label — cross-domain vectors live on :Entity
            "entity": self.ku_min_score,
            "task": self.task_min_score,
            "goal": self.goal_min_score,
            "habit": self.habit_min_score,
            "event": self.event_min_score,
            "ku": self.ku_min_score,
            # NeoLabel spelling and EntityType spelling both land here
            "pathstep": self.path_step_min_score,
            "path_step": self.path_step_min_score,
            "learningpath": self.learning_path_min_score,
            "learning_path": self.learning_path_min_score,
        }
        return mapping.get(entity_lower, self.default_min_score)

    def get_relationship_weight(self, relationship_type: str) -> float:
        """
        Get importance weight for a semantic relationship type.

        Args:
            relationship_type: Namespaced semantic predicate (e.g., "learn:requires_theoretical_understanding")

        Returns:
            Weight value (0.0-1.0), defaults to 0.5 for unknown types
        """
        return self.relationship_type_weights.get(relationship_type, 0.5)

    def get_learning_state_boost(self, learning_state: str) -> float:
        """
        Get boost/penalty multiplier for a learning state.

        Args:
            learning_state: Learning state (mastered, in_progress, viewed, none)

        Returns:
            Boost multiplier (-1.0 to 1.0)
        """
        mapping = {
            "mastered": self.learning_state_boost_mastered,
            "in_progress": self.learning_state_boost_in_progress,
            "viewed": self.learning_state_boost_viewed,
            "none": self.learning_state_boost_not_started,
        }
        return mapping.get(learning_state.lower(), 0.0)


# ============================================================================
# ADAPTER CONFIGURATIONS (Outbound)
# ============================================================================


@dataclass
class DatabaseConfig:
    """Database adapter configuration"""

    # Neo4j settings
    # TLS comes solely from the URI scheme (neo4j+s:// / bolt+s://) — the driver
    # call passes no encryption kwarg. Production boot refuses plaintext schemes
    # (see core/config/validation.py production URI guard).
    neo4j_uri: str = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    neo4j_username: str = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password: str = field(default_factory=_get_neo4j_password)

    # Connection pool / driver-level timeouts (applied at AsyncGraphDatabase.driver).
    # NOTE: these bound connection establishment, pool acquisition, and managed-
    # transaction retry — NOT a single query's execution time. The per-query
    # server-side timeout (transaction_timeout below) is wired separately at the
    # composition root via TimedDriver (adapters/persistence/neo4j/timed_driver.py),
    # which injects neo4j.Query(timeout=) / begin_transaction(timeout=) on every
    # query the shared driver hands out.
    max_connection_pool_size: int = 50
    max_connection_lifetime: int = 3600
    connection_timeout: float = 30.0
    connection_acquisition_timeout: float = 60.0
    max_retry_time: float = 30.0  # -> driver max_transaction_retry_time

    # Query settings
    # transaction_timeout: server-side per-query / per-tx ceiling in seconds. Wired
    # at compose by wrapping the shared AsyncDriver with TimedDriver; override per
    # call site with neo4j_query_timeout(secs) / unbounded_neo4j_query_timeout().
    # 0 is treated as unbounded (compose maps 0 -> None). Env: NEO4J_TRANSACTION_TIMEOUT.
    transaction_timeout: float = 120.0

    # Schema-change monitoring: opt-in background loop that polls the Neo4j schema
    # on an interval and invalidates the adapter's query-optimization caches when
    # the schema drifts. OFF by default — CORE tier spins up no background workers
    # (see docs/architecture/GRACEFUL_DEGRADATION_ARCHITECTURE.md). Enable per
    # environment. Env: NEO4J_SCHEMA_MONITORING, NEO4J_SCHEMA_MONITORING_INTERVAL.
    schema_monitoring_enabled: bool = False
    schema_monitoring_interval: int = 900

    # Performance
    batch_size: int = 1000
    use_bulk_operations: bool = True

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """Create config from environment variables"""
        # A non-positive poll interval makes the monitor loop busy-spin: a
        # negative delay is truthy (so start_monitoring installs it) and
        # asyncio.sleep(<=0) returns immediately, hammering Neo4j introspection.
        # Reject it at the boundary rather than letting it reach the poller.
        schema_monitoring_interval = int(os.getenv("NEO4J_SCHEMA_MONITORING_INTERVAL", "900"))
        if schema_monitoring_interval < 1:
            raise ValueError(
                "NEO4J_SCHEMA_MONITORING_INTERVAL must be a positive number of seconds "
                f"(got {schema_monitoring_interval})."
            )
        return cls(
            neo4j_uri=os.getenv("NEO4J_URI", "neo4j://localhost:7687"),
            neo4j_username=os.getenv("NEO4J_USERNAME", "neo4j"),
            neo4j_password=_get_neo4j_password(),
            max_connection_pool_size=int(os.getenv("NEO4J_MAX_CONNECTION_POOL_SIZE", "50")),
            max_connection_lifetime=int(os.getenv("NEO4J_MAX_CONNECTION_LIFETIME", "3600")),
            connection_timeout=float(os.getenv("NEO4J_CONNECTION_TIMEOUT", "30")),
            connection_acquisition_timeout=float(
                os.getenv("NEO4J_CONNECTION_ACQUISITION_TIMEOUT", "60")
            ),
            max_retry_time=float(os.getenv("NEO4J_MAX_TRANSACTION_RETRY_TIME", "30")),
            transaction_timeout=float(os.getenv("NEO4J_TRANSACTION_TIMEOUT", "120")),
            schema_monitoring_enabled=os.getenv("NEO4J_SCHEMA_MONITORING", "false").lower()
            == "true",
            schema_monitoring_interval=schema_monitoring_interval,
        )


@dataclass
class CacheConfig:
    """
    Cache adapter configuration

    In-memory cache (provider="memory") is THE path — no Redis adapter/client
    exists in the repo. The redis_* fields below are config-only placeholders
    for a future adapter; nothing reads them at runtime.
    """

    enabled: bool = True
    provider: str = "memory"  # Options: "memory" (current), "redis" (ready but disabled)

    # Redis settings (FUTURE - Ready to use when provider="redis")
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None

    # Cache behavior
    default_ttl: int = 3600  # 1 hour
    max_entries: int = 10000
    eviction_policy: str = "lru"

    # Feature-specific TTLs
    search_cache_ttl: int = 1800  # 30 minutes
    user_context_ttl: int = 86400  # 24 hours
    facet_cache_ttl: int = 3600  # 1 hour

    @property
    def redis_url(self) -> str:
        """Construct Redis connection URL from config fields"""
        password_part = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{password_part}{self.redis_host}:{self.redis_port}/{self.redis_db}"


@dataclass
class MessageQueueConfig:
    """
    Message queue adapter configuration

    FUTURE SERVICE: RabbitMQ/Kafka support is PRE-WIRED but currently DISABLED
    Status: Planned for future (see FUTURE_SERVICES.md)
    Current: Uses in-memory event bus (enabled=False, provider="memory")
    Enable when: Distributed architecture or microservices needed
    Note: Requires implementing RabbitMQ/Kafka adapters in /adapters/infrastructure/
    """

    enabled: bool = False  # SET TO TRUE when external queue is needed
    provider: str = "memory"  # Options: "memory" (current), "rabbitmq" (planned), "kafka" (planned)

    # Connection settings (FUTURE - For RabbitMQ/Kafka when implemented)
    host: str = "localhost"
    port: int = 5672
    username: str = "guest"
    password: str = "guest"

    # Queue settings (FUTURE - For RabbitMQ/Kafka when implemented)
    exchange: str = "skuel"
    queue_prefix: str = "skuel."
    durable: bool = True
    auto_ack: bool = False


# ============================================================================
# CORE DOMAIN CONFIGURATIONS
# ============================================================================


@dataclass
class SearchConfig:
    """Unified search service configuration"""

    # Query processing
    max_query_length: int = 500
    min_query_length: int = 2
    default_limit: int = 25
    max_limit: int = 100

    # Facet extraction
    enable_facet_extraction: bool = True
    facet_extraction_method: str = "hybrid"  # pattern, llm, hybrid
    confidence_threshold: float = 0.7

    # Cross-domain search
    enable_cross_domain: bool = True
    parallel_search: bool = True
    max_parallel_domains: int = 5

    # Caching
    cache_enabled: bool = True
    cache_ttl: int = 1800  # 30 minutes

    # Performance
    query_timeout_seconds: float = 10.0
    enable_query_optimization: bool = True
    enable_result_ranking: bool = True


@dataclass
class AskesisConfig:
    """Askesis service configuration"""

    # Conversation management
    max_conversation_history: int = 20
    max_facet_history: int = 10
    conversation_timeout: int = 3600  # 1 hour

    # LLM integration
    enable_llm: bool = False
    llm_provider: str = "mock"  # mock, openai, anthropic
    llm_model: str = "gpt-4"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 500

    # Pedagogical settings
    guidance_mode: str = "discovery"  # discovery, guided, practice
    enable_progress_tracking: bool = True
    enable_recommendations: bool = True

    # Response generation
    response_style: str = "educational"
    include_examples: bool = True
    include_exercises: bool = True


@dataclass
class KnowledgeConfig:
    """Knowledge domain configuration"""

    # Domain system
    domains: list[str] = field(default_factory=list)

    # Mastery levels
    mastery_levels: list[str] = field(default_factory=list)

    # Learning tracking
    track_prerequisites: bool = True
    track_learning_paths: bool = True
    track_mastery: bool = True

    # Content settings
    auto_generate_summaries: bool = False
    extract_keywords: bool = True
    detect_prerequisites: bool = True


# ============================================================================
# APPLICATION CONFIGURATIONS
# ============================================================================


def _default_data_path() -> Any:
    return Path("data")


def _default_features() -> Any:
    return {
        "semantic_search": False,
        "llm_responses": False,
        "learning_analytics": True,
    }


@dataclass
class ApplicationConfig:
    """General application configuration"""

    name: str = "SKUEL"
    version: str = "3.1.0"
    description: str = "Unified Learning System"

    # Runtime settings
    debug: bool = False

    # Paths
    base_path: Path = Path(__file__).parent.parent.parent
    data_path: Path = field(default_factory=_default_data_path)

    # Logging — both consumed by setup_logging() at startup (main.py).
    # log_level also feeds uvicorn; log_format picks the structlog renderer
    # (json everywhere except the local/development splits, which set text).
    log_level: str = "INFO"
    log_format: str = "json"  # json, text

    # Monitoring
    metrics_enabled: bool = True
    tracing_enabled: bool = False
    health_check_enabled: bool = True

    # Feature flags (simple dict for now)
    features: dict[str, Any] = field(default_factory=_default_features)


@dataclass
class FeatureFlags:
    """Feature flags for gradual rollout"""

    # Search features
    enable_semantic_search: bool = False
    enable_vector_search: bool = False
    enable_graph_search: bool = True

    # AI features
    enable_llm_extraction: bool = False
    enable_llm_responses: bool = False
    enable_embeddings: bool = False

    # Learning features
    enable_spaced_repetition: bool = True
    enable_learning_analytics: bool = True
    enable_recommendations: bool = True

    # Experimental
    enable_experimental_features: bool = False
    enable_beta_features: bool = False


# ============================================================================
# DEPENDENCY INJECTION CONFIGURATION
# ============================================================================

# The two personal-vault transports (ADR-075 Decision 6).
VAULT_TRANSPORTS: frozenset[str] = frozenset({"filesystem", "local_agent"})


@dataclass
class VaultConfig:
    """Configuration for Obsidian vault and file sync"""

    # Vault location. VAULT_ROOT is the *personal* vault (ADR-070) — distinct from
    # INGESTION_PATH (the content vault below). Its default must therefore be the
    # personal-vault path, not the content vault, or an unset VAULT_ROOT would
    # collapse the two and stage personal journal files under shared curriculum.
    vault_root: str = os.getenv("VAULT_ROOT", "/home/mike/0bsidian/skuel")
    vault_enabled: bool = os.getenv("VAULT_ENABLED", "true").lower() == "true"

    # Ingestion data directory (where files are staged for ingestion)
    ingestion_root: str = os.getenv("INGESTION_PATH", "/home/mike/0bsidian/0vault")

    # The account the content vault (INGESTION_PATH) *acts as* (ADR-070). For the
    # canonical acts-as ownership model see the module docstring of
    # core/services/vault/vault_descriptor.py (resolve_by_path).
    content_owner_uid: str = os.getenv("SKUEL_CONTENT_VAULT_OWNER", "user_admin")

    # The account VAULT_ROOT (the primary personal vault) BELONGS TO. Personal
    # sync for any other user resolves to {user_vaults_root}/{user_uid}/ instead
    # (VaultRegistry per-user roots). Defaults to the default-user chain so a
    # single-user install binds its one real account with no new config; the
    # user_system terminal default binds VAULT_ROOT to nobody (fail-safe: every
    # user then gets a derived per-user root).
    personal_vault_owner_uid: str = os.getenv(
        "SKUEL_PERSONAL_VAULT_OWNER", os.getenv("SKUEL_DEFAULT_USER_UID", str(SYSTEM_USER_UID))
    )

    # Per-user vault uploads directory
    user_vaults_root: str = os.getenv("SKUEL_USER_VAULTS_ROOT", "data/user_vaults")

    # Personal-vault transport (ADR-075 Decision 6): "filesystem" (Stage 1
    # default — vault on the server's disk) or "local_agent" (Stage 2 — vaults
    # live on users' machines; sync pulls through each user's connected
    # skuel-vault-agent into the server-side staging mirror). Applies to
    # PERSONAL descriptors only; the content vault is server-local by
    # definition and always stays filesystem.
    vault_transport: str = os.getenv("VAULT_TRANSPORT", "filesystem")

    def validated_transport(self) -> str:
        """The configured transport, fail-fast on an unknown value (compose calls this).

        For ``local_agent``, also refuses mirror roots that overlap the content
        vault (Kody #531): the mirror puller's deletion sweep manages its root
        as a pull-owned cache, so a combined/nested layout would let a personal
        sync delete curriculum files missing from the user's agent listing.
        """
        if self.vault_transport not in VAULT_TRANSPORTS:
            raise ValueError(
                f"Invalid VAULT_TRANSPORT {self.vault_transport!r} — "
                f"must be one of {', '.join(sorted(VAULT_TRANSPORTS))} (ADR-075 Decision 6)"
            )
        if self.vault_transport == "local_agent":
            content = self.ingestion_path.resolve()
            for name, root in (
                ("VAULT_ROOT", self.vault_path.resolve()),
                ("SKUEL_USER_VAULTS_ROOT", self.user_vaults_path.resolve()),
            ):
                if content == root or content.is_relative_to(root) or root.is_relative_to(content):
                    raise ValueError(
                        f"VAULT_TRANSPORT=local_agent requires {name} ({root}) to not "
                        f"overlap INGESTION_PATH ({content}) — the staging mirror's "
                        "deletion sweep would treat curriculum files as pull-managed "
                        "cache (ADR-075 Decision 4)."
                    )
        return self.vault_transport

    @property
    def vault_path(self) -> Path:
        """Get vault path as Path object"""
        return Path(self.vault_root)

    @property
    def ingestion_path(self) -> Path:
        """Get ingestion data directory as absolute Path"""
        p = Path(self.ingestion_root)
        return p if p.is_absolute() else Path.cwd() / p

    @property
    def user_vaults_path(self) -> Path:
        """Get per-user vaults base directory as absolute Path"""
        p = Path(self.user_vaults_root)
        return p if p.is_absolute() else Path.cwd() / p

    @classmethod
    def from_env(cls) -> "VaultConfig":
        """Create config from environment variables"""
        return cls(
            vault_root=os.getenv("VAULT_ROOT", "/home/mike/0bsidian/skuel"),
            vault_enabled=os.getenv("VAULT_ENABLED", "true").lower() == "true",
            ingestion_root=os.getenv("INGESTION_PATH", "/home/mike/0bsidian/0vault"),
            user_vaults_root=os.getenv("SKUEL_USER_VAULTS_ROOT", "data/user_vaults"),
            content_owner_uid=os.getenv("SKUEL_CONTENT_VAULT_OWNER", "user_admin"),
            personal_vault_owner_uid=os.getenv(
                "SKUEL_PERSONAL_VAULT_OWNER",
                os.getenv("SKUEL_DEFAULT_USER_UID", str(SYSTEM_USER_UID)),
            ),
            vault_transport=os.getenv("VAULT_TRANSPORT", "filesystem"),
        )


@dataclass
class DependencyConfig:
    """Configuration for dependency injection"""

    # Service bindings
    use_mock_services: bool = False
    service_timeout: float = 30.0

    # Repository bindings
    repository_provider: str = "neo4j"  # neo4j, memory, mock

    # Adapter bindings
    cache_adapter: str = "memory"  # memory, redis
    queue_adapter: str = "memory"  # memory, rabbitmq

    # Lifecycle
    singleton_services: bool = True
    lazy_initialization: bool = True


# ============================================================================
# UNIFIED CONFIGURATION
# ============================================================================


@dataclass
class UnifiedConfig:
    """
    Complete unified configuration for SKUEL system.
    Single source of truth for all configuration.
    """

    # Environment
    environment: Environment = Environment.LOCAL
    schema_version: str = SchemaVersion.V3_1.value

    # Port configurations (Inbound)
    api: APIConfig = field(default_factory=APIConfig)

    # Adapter configurations (Outbound)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    message_queue: MessageQueueConfig = field(default_factory=MessageQueueConfig)

    # Core domain configurations
    search: SearchConfig = field(default_factory=SearchConfig)
    askesis: AskesisConfig = field(default_factory=AskesisConfig)
    knowledge: KnowledgeConfig = field(default_factory=KnowledgeConfig)

    # Vault and sync configuration
    vault: VaultConfig = field(default_factory=VaultConfig)

    # Application configurations
    application: ApplicationConfig = field(default_factory=ApplicationConfig)
    features: FeatureFlags = field(default_factory=FeatureFlags)
    dependencies: DependencyConfig = field(default_factory=DependencyConfig)

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_environment(cls, env: Environment | None = None) -> "UnifiedConfig":
        """
        Create configuration based on environment.

        Args:
            env: Environment to use (defaults to ENV var or LOCAL)

        Returns:
            Configured UnifiedConfig instance
        """
        if env is None:
            env_str = os.getenv("SKUEL_ENVIRONMENT", "local")
            env = Environment(env_str.lower())

        config = cls(environment=env)

        # Load environment-specific settings
        if env == Environment.PRODUCTION:
            config._apply_production_settings()
        elif env == Environment.STAGING:
            config._apply_staging_settings()
        elif env == Environment.DEVELOPMENT:
            config._apply_development_settings()
        elif env == Environment.TEST:
            config._apply_test_settings()
        else:  # LOCAL
            config._apply_local_settings()

        # Load from environment variables
        config._load_from_env()

        return config

    def _apply_production_settings(self) -> None:
        """Apply production-specific settings"""
        self.api.debug = False
        self.api.reload = False
        self.api.rate_limit_enabled = True

        # Memory cache is THE path until a Redis adapter exists — no Redis
        # client exists anywhere in the repo, so provider stays "memory".
        self.cache.enabled = True

        self.application.log_level = "WARNING"

        self.features.enable_experimental_features = False

    def _apply_staging_settings(self) -> None:
        """Apply staging-specific settings"""
        self.api.debug = False
        self.api.reload = False

        self.application.log_level = "INFO"

        self.features.enable_beta_features = True

    def _apply_development_settings(self) -> None:
        """Apply development-specific settings"""
        self.api.debug = True
        self.api.reload = True
        self.api.rate_limit_enabled = False

        self.application.debug = True
        self.application.log_level = "DEBUG"
        self.application.log_format = "text"

        self.features.enable_experimental_features = True
        self.features.enable_beta_features = True

    def _apply_test_settings(self) -> None:
        """Apply test-specific settings"""
        self.cache.enabled = False

        self.dependencies.use_mock_services = True
        self.dependencies.repository_provider = "memory"

        self.application.log_level = "ERROR"

    def _apply_local_settings(self) -> None:
        """Apply local development settings"""
        self.api.debug = True
        self.api.reload = True

        self.application.log_level = "DEBUG"
        self.application.log_format = "text"

        self.features.enable_experimental_features = True

    def _load_from_env(self) -> None:
        """Load configuration from environment variables.

        KNOWN DEBT: this runs AFTER _apply_{environment}_settings() and
        wholesale-REPLACES self.database / self.api via from_env(), discarding
        any environment-split values on those two sub-configs (e.g. the
        production debug=False / rate_limit_enabled=True split). Sub-configs
        not rebuilt here keep their split values. Precedence redesign
        (defaults < environment split < explicit env vars) is tracked in
        TECHNICAL_DEBT.md and is its own PR — do not band-aid it here.
        """
        # Database from env
        self.database = DatabaseConfig.from_env()

        # API from env
        self.api = APIConfig.from_env()

        # Override specific settings from env
        if os.getenv("CACHE_ENABLED"):
            self.cache.enabled = os.getenv("CACHE_ENABLED", "true").lower() == "true"

        log_level = os.getenv("LOG_LEVEL")
        if log_level:
            self.application.log_level = log_level

    def validate(self) -> list[str]:
        """
        Validate configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Validate database
        if not self.database.neo4j_uri:
            errors.append("Database URI is required")

        # Validate API
        if self.api.port < 1 or self.api.port > 65535:
            errors.append(f"Invalid API port: {self.api.port}")

        # Validate cache
        if self.cache.enabled and self.cache.provider == "redis" and not self.cache.redis_host:
            errors.append("Redis host required when Redis cache enabled")

        # Validate search
        if self.search.max_limit < self.search.default_limit:
            errors.append("Search max_limit must be >= default_limit")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            "environment": self.environment.value,
            "schema_version": self.schema_version,
            "api": {"host": self.api.host, "port": self.api.port, "debug": self.api.debug},
            "database": {"uri": self.database.neo4j_uri},
            "cache": {"enabled": self.cache.enabled, "provider": self.cache.provider},
            "features": {
                "semantic_search": self.features.enable_semantic_search,
                "llm_responses": self.features.enable_llm_responses,
            },
        }


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================


def create_config(environment: Environment | None = None) -> UnifiedConfig:
    """
    Create configuration for the specified environment.

    Args:
        environment: Target environment (defaults to ENV var or LOCAL)

    Returns:
        Configured UnifiedConfig instance
    """
    config = UnifiedConfig.from_environment(environment)

    # Validate configuration
    errors = config.validate()
    if errors:
        import warnings

        for error in errors:
            warnings.warn(f"Configuration warning: {error}", stacklevel=2)

    return config


def create_test_config() -> UnifiedConfig:
    """Create configuration for test environment"""
    return create_config(Environment.TEST)


def create_development_config() -> UnifiedConfig:
    """Create configuration for development environment"""
    return create_config(Environment.DEVELOPMENT)


def create_production_config() -> UnifiedConfig:
    """Create configuration for production environment"""
    return create_config(Environment.PRODUCTION)


def get_config_for_adapter(adapter_type: str, config: UnifiedConfig) -> Any:
    """
    Get configuration for a specific adapter.

    Args:
        adapter_type: Type of adapter (database, cache, queue, etc.)
        config: Unified configuration

    Returns:
        Adapter-specific configuration
    """
    adapters = {
        "database": config.database,
        "cache": config.cache,
        "queue": config.message_queue,
        "api": config.api,
    }

    return adapters.get(adapter_type)


# ============================================================================
# CONFIGURATION VALIDATION
# ============================================================================


def validate_environment_config() -> bool:
    """
    Validate that all required environment variables are set.

    Returns:
        True if valid, False otherwise
    """
    required_vars = []

    # Add production requirements
    env = os.getenv("SKUEL_ENVIRONMENT", "local")
    if env == "production":
        required_vars.append("NEO4J_PASSWORD")

    missing = [var for var in required_vars if not os.getenv(var)]

    if missing:
        logger.error("Missing required environment variables", missing=missing)
        return False

    return True
