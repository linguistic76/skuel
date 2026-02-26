"""
Prometheus metrics registry for SKUEL.

This module defines all Prometheus metrics (Counter, Gauge, Histogram) used across the application.
Metrics are organized into logical groups: System, HTTP, Database, Events, Relationships, Search.

See: /docs/observability/PROMETHEUS_METRICS.md (to be created in )
"""

from prometheus_client import Counter, Gauge, Histogram


class SystemMetrics:
    """System-level health metrics."""

    def __init__(self) -> None:
        self.cpu_usage = Gauge("skuel_cpu_usage_percent", "CPU usage percentage")

        self.memory_usage = Gauge("skuel_memory_usage_bytes", "Memory usage in bytes")

        self.neo4j_connected = Gauge(
            "skuel_neo4j_connected", "Neo4j connection status (1=up, 0=down)"
        )


class HttpMetrics:
    """HTTP request and response metrics."""

    def __init__(self) -> None:
        self.requests_total = Counter(
            "skuel_http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status"],
        )

        self.request_duration = Histogram(
            "skuel_http_request_duration_seconds",
            "HTTP request latency in seconds",
            ["method", "endpoint"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        )

        self.errors_total = Counter(
            "skuel_http_errors_total",
            "Total HTTP errors",
            ["method", "endpoint", "status"],
        )


class DatabaseMetrics:
    """Neo4j database operation metrics."""

    def __init__(self) -> None:
        self.queries_total = Counter(
            "skuel_neo4j_queries_total",
            "Total Neo4j queries",
            ["operation", "label"],  # operation: create/read/update/delete
        )

        self.query_duration = Histogram(
            "skuel_neo4j_query_duration_seconds",
            "Neo4j query latency in seconds",
            ["operation", "label"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        )

        self.query_errors = Counter(
            "skuel_neo4j_errors_total", "Total Neo4j query errors", ["operation"]
        )


class EventMetrics:
    """Event bus metrics."""

    def __init__(self) -> None:
        # Event publication metrics
        self.events_published_total = Counter(
            "skuel_events_published_total",
            "Total events published",
            ["event_type"],
        )

        self.event_publish_duration_seconds = Histogram(
            "skuel_event_publish_duration_seconds",
            "Event publication overhead (time to call all handlers)",
            ["event_type"],
            buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0),
        )

        # Event handler execution metrics
        self.event_handler_calls_total = Counter(
            "skuel_event_handler_calls_total",
            "Total event handler calls",
            ["event_type", "handler"],
        )

        self.event_handler_duration_seconds = Histogram(
            "skuel_event_handler_duration_seconds",
            "Event handler execution time",
            ["event_type", "handler"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
        )

        self.event_handler_errors_total = Counter(
            "skuel_event_handler_errors_total",
            "Total event handler errors",
            ["event_type", "handler"],
        )

        # Context invalidation metrics
        self.context_invalidations_total = Counter(
            "skuel_context_invalidations_total",
            "Total user context invalidations",
        )


class DomainMetrics:
    """Domain entity activity metrics."""

    def __init__(self) -> None:
        self.entities_created = Counter(
            "skuel_entities_created_total",
            "Total entities created by type",
            ["entity_type"],
        )

        self.entities_completed = Counter(
            "skuel_entities_completed_total",
            "Total entities completed by type",
            ["entity_type"],
        )

        self.active_entities = Gauge(
            "skuel_active_entities_count",
            "Current active entities by type",
            ["entity_type"],
        )


class RelationshipMetrics:
    """
    Graph relationship metrics for tracking SKUEL's graph health and patterns.

    - January 2026

    Tracks the four relationship layers:
    1. Hierarchical - Parent/child (CONTAINS, ORGANIZES)
    2. Lateral - Sibling/dependency (BLOCKS, ENABLES, RELATED_TO) ← PRIMARY FOCUS
    3. Semantic - Meaning-based (80+ types with namespaces)
    4. Cross-domain - Between domains (SERVES_LIFE_PATH, etc.)

    Updated by periodic Neo4j queries (every 5 minutes) in graph health background task.
    """

    def __init__(self) -> None:
        # Overall graph health
        self.graph_density = Gauge(
            "skuel_graph_density",
            "Average relationships per entity (graph connectivity score)",
        )

        self.total_entities = Gauge(
            "skuel_total_entities",
            "Total entities in graph",
        )

        self.total_relationships = Gauge(
            "skuel_total_relationships",
            "Total relationships in graph",
        )

        self.orphaned_entities = Gauge(
            "skuel_orphaned_entities_count",
            "Entities with no relationships (isolated nodes)",
        )

        # Relationship layer tracking
        self.relationships_by_layer = Gauge(
            "skuel_relationships_count",
            "Total relationships by layer",
            ["layer"],  # layer: hierarchical/lateral/semantic/cross_domain
        )

        # Lateral relationship breakdown (PRIMARY FOCUS)
        self.lateral_by_category = Gauge(
            "skuel_lateral_relationships_by_category",
            "Lateral relationships by category",
            ["category"],  # category: structural/dependency/semantic/associative
        )

        # Blocking/dependency tracking
        self.blocking_relationships = Gauge(
            "skuel_blocking_relationships_count",
            "Active BLOCKS relationships",
        )

        self.enables_relationships = Gauge(
            "skuel_enables_relationships_count",
            "Active ENABLES relationships",
        )

        self.dependency_chain_length = Gauge(
            "skuel_dependency_chain_max_length",
            "Maximum dependency chain length (BLOCKS → BLOCKED_BY)",
        )

        # Hierarchical patterns
        self.contains_relationships = Gauge(
            "skuel_contains_relationships_count",
            "CONTAINS relationships (parent → child)",
        )

        self.organizes_relationships = Gauge(
            "skuel_organizes_relationships_count",
            "ORGANIZES relationships (MOC → KU)",
        )

        # Semantic tier activation
        self.semantic_relationships = Gauge(
            "skuel_semantic_relationships_count",
            "Semantic relationships count",
            ["tier"],  # tier: 1/2/3
        )

        # Cross-domain connections
        self.cross_domain_relationships = Gauge(
            "skuel_cross_domain_relationships_count",
            "Relationships crossing domain boundaries",
            ["from_domain", "to_domain"],
        )

        # Graph traversal performance
        self.graph_traversal_depth = Gauge(
            "skuel_graph_traversal_avg_depth",
            "Average graph traversal depth in queries",
        )


class SearchMetrics:
    """Search and query metrics."""

    def __init__(self) -> None:
        self.searches_total = Counter(
            "skuel_searches_total",
            "Total searches by type",
            ["search_type"],  # vector/fulltext/hybrid
        )

        self.search_duration = Histogram(
            "skuel_search_duration_seconds",
            "Search query latency",
            ["search_type"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
        )

        self.search_similarity = Histogram(
            "skuel_search_similarity_score",
            "Search result similarity scores",
            ["search_type"],
            buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
        )


class QueryMetrics:
    """
    Query/operation performance metrics.

    Tracks individual operation performance (e.g., ku_search_by_title, ls_add_knowledge).
    More granular than DatabaseMetrics (which tracks by operation type: create/read/update/delete).
    """

    def __init__(self) -> None:
        self.operation_calls_total = Counter(
            "skuel_operation_calls_total",
            "Total operation calls by name",
            ["operation_name"],  # e.g., ku_search_by_title, ls_add_knowledge
        )

        self.operation_duration_seconds = Histogram(
            "skuel_operation_duration_seconds",
            "Operation execution time in seconds",
            ["operation_name"],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
        )

        self.operation_errors_total = Counter(
            "skuel_operation_errors_total",
            "Total operation errors by name",
            ["operation_name"],
        )


class AiMetrics:
    """
    AI service operation metrics.

    Tracks OpenAI API calls, embedding generation, and Deepgram transcription.
    Critical for monitoring expensive AI operations and enabling cost optimization.
    """

    def __init__(self) -> None:
        # OpenAI API calls
        self.openai_requests_total = Counter(
            "skuel_openai_requests_total",
            "Total OpenAI API requests",
            ["operation", "model"],  # operation: embeddings/chat/completion
        )

        self.openai_duration_seconds = Histogram(
            "skuel_openai_duration_seconds",
            "OpenAI API call duration",
            ["operation", "model"],
            buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
        )

        self.openai_tokens_used = Counter(
            "skuel_openai_tokens_total",
            "Total OpenAI tokens consumed",
            ["operation", "model", "token_type"],  # token_type: prompt/completion
        )

        self.openai_errors_total = Counter(
            "skuel_openai_errors_total",
            "Total OpenAI API errors",
            ["operation", "error_type"],  # error_type: rate_limit/timeout/auth
        )

        # Embedding worker
        self.embedding_queue_size = Gauge(
            "skuel_embedding_queue_size",
            "Pending embeddings in queue",
            ["queue_type"],  # queue_type: entity/chunk
        )

        self.embeddings_processed_total = Counter(
            "skuel_embeddings_processed_total",
            "Total embeddings processed",
            ["entity_type", "status"],  # status: success/failed
        )

        self.embedding_batch_size = Histogram(
            "skuel_embedding_batch_size",
            "Embedding batch size distribution",
            buckets=(1, 5, 10, 25, 50, 100),
        )

        # Deepgram transcription
        self.transcription_requests_total = Counter(
            "skuel_transcription_requests_total",
            "Total transcription requests",
            ["status"],
        )

        self.transcription_duration_seconds = Histogram(
            "skuel_transcription_duration_seconds",
            "Transcription processing time",
            buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
        )


class PrometheusMetrics:
    """
    Central registry for all Prometheus metrics.

    This class provides a single point of access to all metric groups.
    Instantiate once during bootstrap and pass to services that need instrumentation.

    Usage:
        # In services_bootstrap.py
        prometheus_metrics = PrometheusMetrics()

        # In route factories
        await prometheus_metrics.http.requests_total.labels(
            method="GET", endpoint="/tasks", status=200
        ).inc()

        # In UniversalNeo4jBackend
        prometheus_metrics.db.queries_total.labels(
            operation="create", label="Task"
        ).inc()

        # In AI services
        prometheus_metrics.ai.openai_requests_total.labels(
            operation="embeddings", model="text-embedding-3-small"
        ).inc()
    """

    def __init__(self) -> None:
        self.system = SystemMetrics()
        self.http = HttpMetrics()
        self.db = DatabaseMetrics()
        self.events = EventMetrics()
        self.domains = DomainMetrics()
        self.relationships = RelationshipMetrics()
        self.search = SearchMetrics()
        self.queries = QueryMetrics()
        self.ai = AiMetrics()  # January 2026
