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
from enum import Enum
from pathlib import Path
from typing import Any

from core.utils.logging import get_logger

logger = get_logger("skuel.config")

# ============================================================================
# CREDENTIAL HELPER
# ============================================================================


def _get_neo4j_password() -> str:
    """
    Get Neo4j password from encrypted credential store.

    Falls back to environment variable for migration support.
    """
    try:
        from core.config.credential_store import get_credential

        password = get_credential("NEO4J_PASSWORD", fallback_to_env=True)
        return password or ""
    except Exception:
        # Fallback to env if credential store fails
        return os.getenv("NEO4J_PASSWORD", "")


# ============================================================================
# CORE ARCHITECTURE ENUMS
# ============================================================================


class Environment(str, Enum):
    """System environment definition"""

    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class SchemaVersion(str, Enum):
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

    # Security
    api_key_enabled: bool = False
    api_key_header: str = "X-API-Key"

    @classmethod
    def from_env(cls) -> "APIConfig":
        """Create config from environment variables"""
        return cls(
            host=os.getenv("API_HOST", "0.0.0.0"),
            port=int(os.getenv("API_PORT", "8000")),
            debug=os.getenv("API_DEBUG", "false").lower() == "true",
            reload=os.getenv("API_RELOAD", "false").lower() == "true",
        )


@dataclass
class GraphQLConfig:
    """GraphQL configuration for inbound port"""

    enabled: bool = False
    endpoint: str = "/graphql"
    playground_enabled: bool = True
    introspection_enabled: bool = True


# ============================================================================
# ADAPTER CONFIGURATIONS (Outbound)
# ============================================================================


@dataclass
class DatabaseConfig:
    """Database adapter configuration"""

    # Neo4j settings
    neo4j_uri: str = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    neo4j_username: str = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password: str = field(default_factory=_get_neo4j_password)
    neo4j_database: str = os.getenv("NEO4J_DATABASE", "neo4j")

    # Connection pool
    max_connection_pool_size: int = 50
    max_connection_lifetime: int = 3600
    connection_timeout: float = 30.0
    max_retry_time: float = 30.0
    encrypted: bool = False

    # Query settings
    query_timeout: float = 60.0
    transaction_timeout: float = 120.0
    enable_query_logging: bool = False

    # Performance
    batch_size: int = 1000
    use_bulk_operations: bool = True

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """Create config from environment variables"""
        return cls(
            neo4j_uri=os.getenv("NEO4J_URI", "neo4j://localhost:7687"),
            neo4j_username=os.getenv("NEO4J_USERNAME", "neo4j"),
            neo4j_password=_get_neo4j_password(),
            neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
            max_connection_pool_size=int(os.getenv("NEO4J_MAX_CONNECTION_POOL_SIZE", "50")),
            connection_timeout=float(os.getenv("NEO4J_CONNECTION_TIMEOUT", "30")),
            encrypted=os.getenv("NEO4J_ENCRYPTED", "false").lower() == "true",
        )


@dataclass
class CacheConfig:
    """
    Cache adapter configuration

    FUTURE SERVICE: Redis support is PRE-WIRED but currently DISABLED
    Status: Ready to enable when needed (see FUTURE_SERVICES.md)
    Current: Uses in-memory cache (provider="memory")
    Enable when: Production deployment or multi-instance scaling needed
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
# AI & GENAI CONFIGURATIONS
# ============================================================================


@dataclass
class GenAIConfig:
    """
    Neo4j GenAI plugin configuration.

    ARCHITECTURE:
    - API keys configured at database level (AuraDB console)
    - No per-query credential passing
    - Graceful degradation when unavailable
    """

    # Feature flags
    enabled: bool = field(default=False)
    vector_search_enabled: bool = field(default=False)

    # Provider configuration (database-level, not per-query)
    provider: str = field(default="openai")  # openai, anthropic, azure
    embedding_model: str = field(default="text-embedding-3-small")
    embedding_dimension: int = field(default=1536)

    # Vector index configuration
    vector_index_similarity: str = field(default="cosine")  # cosine, euclidean
    vector_index_name_prefix: str = field(default="vector_idx")

    # Batch processing
    batch_size: int = field(default=25)  # Neo4j optimal batch size
    max_concurrent_batches: int = field(default=5)

    # Fallback behavior
    fallback_to_keyword_search: bool = field(default=True)
    show_unavailable_features: bool = field(default=True)

    @classmethod
    def from_env(cls) -> "GenAIConfig":
        """Create config from environment variables"""
        return cls(
            enabled=os.getenv("GENAI_ENABLED", "false").lower() == "true",
            vector_search_enabled=os.getenv("GENAI_VECTOR_SEARCH_ENABLED", "false").lower() == "true",
            provider=os.getenv("GENAI_PROVIDER", "openai"),
            embedding_model=os.getenv("GENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            embedding_dimension=int(os.getenv("GENAI_EMBEDDING_DIMENSION", "1536")),
            batch_size=int(os.getenv("GENAI_BATCH_SIZE", "25")),
            fallback_to_keyword_search=os.getenv("GENAI_FALLBACK_TO_KEYWORD_SEARCH", "true").lower() == "true",
            show_unavailable_features=os.getenv("GENAI_SHOW_UNAVAILABLE_FEATURES", "true").lower() == "true",
        )


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


def _default_logs_path() -> Any:
    return Path("logs")


def _default_features() -> Any:
    return {
        "semantic_search": False,
        "llm_responses": False,
        "learning_analytics": True,
    }


def _default_allowed_subdirs() -> Any:
    return ["knowledge", "tasks", "habits", "goals", "journals", "neo4j/import", "neo4j/export"]


def _default_allowed_extensions() -> Any:
    return [".md", ".yaml", ".yml", ".json", ".csv"]


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
    logs_path: Path = field(default_factory=_default_logs_path)

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json, text
    log_to_file: bool = True
    log_to_console: bool = True

    # Monitoring
    metrics_enabled: bool = True
    tracing_enabled: bool = False
    health_check_enabled: bool = True

    # Security
    enable_auth: bool = False
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 1440  # 24 hours

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


@dataclass
class VaultConfig:
    """Configuration for Obsidian vault and file sync"""

    # Vault location
    vault_root: str = os.getenv("VAULT_ROOT", "/home/mike/0bsidian/skuel")
    vault_enabled: bool = os.getenv("VAULT_ENABLED", "true").lower() == "true"

    # Sync settings
    auto_sync: bool = os.getenv("AUTO_SYNC_VAULT", "true").lower() == "true"
    watch_vault: bool = os.getenv("WATCH_VAULT", "false").lower() == "true"
    sync_interval_minutes: int = int(os.getenv("SYNC_INTERVAL_MINUTES", "30"))

    # Neo4j import/export paths (subdirectories of vault_root)
    neo4j_import_dir: str = "neo4j/import"
    neo4j_export_dir: str = "neo4j/export"

    # Permission settings
    allowed_subdirs: list[str] = field(default_factory=_default_allowed_subdirs)

    # File filters
    allowed_extensions: list[str] = field(default_factory=_default_allowed_extensions)

    # Security
    restrict_access: bool = True  # Only access explicitly allowed paths
    validate_paths: bool = True  # Validate all path access

    @property
    def vault_path(self) -> Path:
        """Get vault path as Path object"""
        return Path(self.vault_root)

    @property
    def import_path(self) -> Path:
        """Get Neo4j import path"""
        return self.vault_path / self.neo4j_import_dir

    @property
    def export_path(self) -> Path:
        """Get Neo4j export path"""
        return self.vault_path / self.neo4j_export_dir

    @classmethod
    def from_env(cls) -> "VaultConfig":
        """Create config from environment variables"""
        return cls(
            vault_root=os.getenv("VAULT_ROOT", "/home/mike/0bsidian/skuel"),
            vault_enabled=os.getenv("VAULT_ENABLED", "true").lower() == "true",
            auto_sync=os.getenv("AUTO_SYNC_VAULT", "true").lower() == "true",
            watch_vault=os.getenv("WATCH_VAULT", "false").lower() == "true",
            sync_interval_minutes=int(os.getenv("SYNC_INTERVAL_MINUTES", "30")),
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
    graphql: GraphQLConfig = field(default_factory=GraphQLConfig)

    # Adapter configurations (Outbound)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    message_queue: MessageQueueConfig = field(default_factory=MessageQueueConfig)

    # AI and GenAI configurations
    genai: GenAIConfig = field(default_factory=GenAIConfig)

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
        self.api.api_key_enabled = True

        self.database.enable_query_logging = False
        self.database.encrypted = True

        self.cache.enabled = True
        self.cache.provider = "redis"

        self.application.log_level = "WARNING"
        self.application.enable_auth = True

        self.features.enable_experimental_features = False

    def _apply_staging_settings(self) -> None:
        """Apply staging-specific settings"""
        self.api.debug = False
        self.api.reload = False

        self.database.enable_query_logging = True

        self.application.log_level = "INFO"

        self.features.enable_beta_features = True

    def _apply_development_settings(self) -> None:
        """Apply development-specific settings"""
        self.api.debug = True
        self.api.reload = True
        self.api.rate_limit_enabled = False

        self.database.enable_query_logging = True

        self.application.debug = True
        self.application.log_level = "DEBUG"

        self.features.enable_experimental_features = True
        self.features.enable_beta_features = True

    def _apply_test_settings(self) -> None:
        """Apply test-specific settings"""
        self.database.neo4j_database = "test"

        self.cache.enabled = False

        self.dependencies.use_mock_services = True
        self.dependencies.repository_provider = "memory"

        self.application.log_level = "ERROR"

    def _apply_local_settings(self) -> None:
        """Apply local development settings"""
        self.api.debug = True
        self.api.reload = True

        self.database.enable_query_logging = True

        self.application.log_level = "DEBUG"

        self.features.enable_experimental_features = True

    def _load_from_env(self) -> None:
        """Load configuration from environment variables"""
        # Database from env
        self.database = DatabaseConfig.from_env()

        # API from env
        self.api = APIConfig.from_env()

        # GenAI from env
        self.genai = GenAIConfig.from_env()

        # Override specific settings from env
        if os.getenv("CACHE_ENABLED"):
            self.cache.enabled = os.getenv("CACHE_ENABLED", "true").lower() == "true"

        if os.getenv("LOG_LEVEL"):
            self.application.log_level = os.getenv("LOG_LEVEL")

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
            "database": {"uri": self.database.neo4j_uri, "database": self.database.neo4j_database},
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
        "graphql": config.graphql,
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
        required_vars.extend(["NEO4J_PASSWORD", "JWT_SECRET", "API_KEY"])

    missing = [var for var in required_vars if not os.getenv(var)]

    if missing:
        logger.error("Missing required environment variables", missing=missing)
        return False

    return True
