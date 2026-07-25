"""
Prometheus metrics registry for SKUEL.

This module defines all Prometheus metrics (Counter, Gauge, Histogram) used across the application.
Metrics are organized into logical groups: HTTP, Database, Events, Domains, Relationships, Queries, AI.

See: /docs/observability/PROMETHEUS_METRICS.md
"""

from prometheus_client import Counter, Gauge, Histogram


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

        # Hierarchical patterns
        self.contains_relationships = Gauge(
            "skuel_contains_relationships_count",
            "CONTAINS relationships (parent → child)",
        )

        self.organizes_relationships = Gauge(
            "skuel_organizes_relationships_count",
            "ORGANIZES relationships (MOC → KU)",
        )

        # Knowledge-subgraph structural health (ADR-080 Horizon-1). A
        # knowledge-scoped view of graph health — the raw signals the
        # KnowledgeHealthService interprets into a GDS-readiness score. Updated by
        # the same 5-min graph-health poller (no new worker → CORE-safe).
        self.knowledge_kus_total = Gauge(
            "skuel_knowledge_kus_total",
            "Total Ku nodes in the knowledge subgraph",
        )

        self.knowledge_orphan_kus = Gauge(
            "skuel_knowledge_orphan_kus_count",
            "Kus with zero incident relationships (isolated knowledge)",
        )

        self.knowledge_avg_ku_degree = Gauge(
            "skuel_knowledge_avg_ku_degree",
            "Average incident relationships per Ku (knowledge connectivity)",
        )

        self.knowledge_composed_kus = Gauge(
            "skuel_knowledge_composed_kus_count",
            "Kus composed into >=1 PathStep (USES_KU/CONTAINS_KNOWLEDGE/TRAINS_KU)",
        )

        self.knowledge_prerequisite_edges = Gauge(
            "skuel_knowledge_prerequisite_edges_count",
            "Prerequisite-DAG edges among knowledge nodes "
            "(PREREQUISITE_FOR/DEPENDS_ON/REQUIRES_PREREQUISITE)",
        )

        self.knowledge_organizes_edges = Gauge(
            "skuel_knowledge_organizes_edges_count",
            "ORGANIZES/MOC edges among knowledge nodes",
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

    Tracks AI API calls (OpenAI LLM, HuggingFace embeddings), and Deepgram transcription.
    Critical for monitoring expensive AI operations and enabling cost optimization.
    """

    def __init__(self) -> None:
        # AI API calls (provider-agnostic: OpenAI LLM, HuggingFace embeddings, etc.)
        self.ai_requests_total = Counter(
            "skuel_ai_requests_total",
            "Total AI API requests",
            ["operation", "model"],  # operation: embeddings/chat/completion
        )

        self.ai_duration_seconds = Histogram(
            "skuel_ai_duration_seconds",
            "AI API call duration",
            ["operation", "model"],
            buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
        )

        self.ai_errors_total = Counter(
            "skuel_ai_errors_total",
            "Total AI API errors",
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
        prometheus_metrics.ai.ai_requests_total.labels(
            operation="embeddings", model="text-embedding-3-small"
        ).inc()
    """

    def __init__(self) -> None:
        self.http = HttpMetrics()
        self.db = DatabaseMetrics()
        self.events = EventMetrics()
        self.domains = DomainMetrics()
        self.relationships = RelationshipMetrics()
        self.queries = QueryMetrics()
        self.ai = AiMetrics()
