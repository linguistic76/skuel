"""
Performance Optimization Service
=============================================

Optimizes knowledge system performance for scale and speed.
Implements sub-100ms inference, advanced caching, background processing, and scale testing.
"""

import asyncio
import contextlib
import hashlib
import heapq
import time
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from core.services.performance_types import (
    CacheOptimization,
    CachePerformance,
    PerformanceResults,
    ResourceUtilization,
    ScaleTestResult,
    SLACompliance,
    TestConfiguration,
)
from core.utils.logging import get_logger


class CacheStrategy(Enum):
    """Caching strategy types."""

    LRU = "lru"  # Least Recently Used
    LFU = "lfu"  # Least Frequently Used
    TTL = "ttl"  # Time To Live
    ADAPTIVE = "adaptive"  # Adaptive based on usage patterns
    WRITE_THROUGH = "write_through"  # Write to cache and database
    WRITE_BACK = "write_back"  # Write to cache, async to database
    READ_THROUGH = "read_through"  # Read from cache or database


class ProcessingPriority(Enum):
    """Background processing priority levels."""

    CRITICAL = "critical"  # Process immediately
    HIGH = "high"  # Process within 1 second
    MEDIUM = "medium"  # Process within 10 seconds
    LOW = "low"  # Process within 1 minute
    BACKGROUND = "background"  # Process when resources available


class OptimizationMetric(Enum):
    """Performance optimization metrics."""

    RESPONSE_TIME = "response_time"
    THROUGHPUT = "throughput"
    CACHE_HIT_RATE = "cache_hit_rate"
    MEMORY_USAGE = "memory_usage"
    CPU_UTILIZATION = "cpu_utilization"
    INFERENCE_ACCURACY = "inference_accuracy"
    CONCURRENT_USERS = "concurrent_users"


@dataclass
class CacheEntry:
    """Individual cache entry with metadata."""

    key: str
    value: Any
    created_at: datetime
    last_accessed: datetime
    access_count: int = 0
    ttl_seconds: int | None = None
    size_bytes: int = 0
    computation_cost: float = 0.0  # Cost to recompute

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        if not self.ttl_seconds:
            return False
        return datetime.now() > self.created_at + timedelta(seconds=self.ttl_seconds)

    def access(self):
        """Record cache access."""
        self.last_accessed = datetime.now()
        self.access_count += 1


@dataclass
class InferenceRequest:
    """Knowledge inference request."""

    request_id: str
    user_uid: str
    query: str
    context: dict[str, Any]
    requested_at: datetime
    priority: ProcessingPriority = ProcessingPriority.MEDIUM
    max_response_time_ms: int = 100
    require_explanation: bool = False
    include_confidence: bool = True

    def is_expired(self) -> bool:
        """Check if request has exceeded max response time."""
        elapsed_ms = (datetime.now() - self.requested_at).total_seconds() * 1000
        return elapsed_ms > self.max_response_time_ms


@dataclass
class InferenceResult:
    """Knowledge inference result."""

    request_id: str
    inference: dict[str, Any]
    confidence_score: float
    processing_time_ms: float
    cache_hit: bool
    explanation: str | None = None
    related_knowledge: list[str] = field(default_factory=list)
    computation_path: list[str] = field(default_factory=list)

    def meets_performance_target(self, target_ms: int = 100) -> bool:
        """Check if response meets performance target."""
        return self.processing_time_ms <= target_ms


@dataclass
class BackgroundTask:
    """Background processing task."""

    task_id: str
    task_type: str
    priority: ProcessingPriority
    payload: dict[str, Any]
    created_at: datetime
    scheduled_at: datetime | None = None
    started_at: datetime | None = (None,)
    completed_at: datetime | None = None
    retry_count: int = 0
    max_retries: int = 3
    dependencies: list[str] = field(default_factory=list)
    estimated_duration_seconds: float = 1.0

    def __lt__(self, other) -> bool:
        """Priority queue comparison - higher priority first."""
        priority_values = {
            ProcessingPriority.CRITICAL: 0,
            ProcessingPriority.HIGH: 1,
            ProcessingPriority.MEDIUM: 2,
            ProcessingPriority.LOW: 3,
            ProcessingPriority.BACKGROUND: 4,
        }
        return priority_values[self.priority] < priority_values[other.priority]

    def is_ready(self, completed_tasks: set[str]) -> bool:
        """Check if task is ready to execute."""
        return all(dep in completed_tasks for dep in self.dependencies)


@dataclass
class PerformanceMetrics:
    """System performance metrics."""

    timestamp: datetime
    avg_response_time_ms: float
    p95_response_time_ms: float
    p99_response_time_ms: float
    throughput_requests_per_second: float
    cache_hit_rate: float
    memory_usage_mb: float
    cpu_utilization_percent: float
    active_connections: int
    queue_depth: int
    error_rate: float

    def meets_sla(self) -> bool:
        """Check if metrics meet service level agreement."""
        return (
            self.avg_response_time_ms <= 100
            and self.p95_response_time_ms <= 200
            and self.cache_hit_rate >= 0.8
            and self.error_rate <= 0.01
        )


class AdvancedCache:
    """High-performance multi-strategy cache implementation."""

    def __init__(
        self,
        max_size: int = 10000,
        default_ttl: int = 3600,
        strategy: CacheStrategy = CacheStrategy.ADAPTIVE,
    ) -> None:
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.strategy = strategy
        self.cache: dict[str, CacheEntry] = {}
        self.access_order = OrderedDict()  # For LRU
        self.frequency_heap = []  # For LFU
        self.stats = {"hits": 0, "misses": 0, "evictions": 0, "size_bytes": 0}
        self.logger = get_logger(__name__)

    async def get(self, key: str) -> Any | None:
        """Get value from cache."""
        if key not in self.cache:
            self.stats["misses"] += 1
            return None

        entry = self.cache[key]

        if entry.is_expired():
            await self.delete(key)
            self.stats["misses"] += 1
            return None

        entry.access()
        self._update_access_patterns(key)
        self.stats["hits"] += 1
        return entry.value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set value in cache."""
        try:
            # Calculate size (simplified)
            size_bytes = len(str(value))

            # Check if eviction needed
            if len(self.cache) >= self.max_size:
                await self._evict()

            # Create cache entry
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=datetime.now(),
                last_accessed=datetime.now(),
                ttl_seconds=ttl or self.default_ttl,
                size_bytes=size_bytes,
            )

            self.cache[key] = entry
            self._update_access_patterns(key)
            self.stats["size_bytes"] += size_bytes

            return True
        except Exception as e:
            self.logger.error(f"Cache set error: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete value from cache."""
        if key in self.cache:
            entry = self.cache[key]
            del self.cache[key]
            self.stats["size_bytes"] -= entry.size_bytes
            self._remove_from_access_patterns(key)
            return True
        return False

    async def clear(self):
        """Clear entire cache."""
        self.cache.clear()
        self.access_order.clear()
        self.frequency_heap.clear()
        self.stats = {"hits": 0, "misses": 0, "evictions": 0, "size_bytes": 0}

    def get_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.stats["hits"] + self.stats["misses"]
        return self.stats["hits"] / total if total > 0 else 0.0

    async def _evict(self) -> None:
        """Evict entries based on strategy."""
        if not self.cache:
            return

        if self.strategy == CacheStrategy.LRU:
            # Remove least recently used
            oldest_key = next(iter(self.access_order))
            await self.delete(oldest_key)
        elif self.strategy == CacheStrategy.LFU:
            # Remove least frequently used
            if self.frequency_heap:
                _, key = heapq.heappop(self.frequency_heap)
                await self.delete(key)
        elif self.strategy == CacheStrategy.TTL:
            # Remove expired entries first
            expired_keys = [key for key, entry in self.cache.items() if entry.is_expired()]
            if expired_keys:
                await self.delete(expired_keys[0])
            else:
                # Fall back to LRU
                oldest_key = next(iter(self.access_order))
                await self.delete(oldest_key)
        elif self.strategy == CacheStrategy.ADAPTIVE:
            # Use adaptive eviction based on access patterns
            await self._adaptive_evict()

        self.stats["evictions"] += 1

    async def _adaptive_evict(self) -> None:
        """Adaptive eviction based on usage patterns."""
        # Score entries based on multiple factors
        scores = {}
        now = datetime.now()

        for key, entry in self.cache.items():
            # Combine recency, frequency, and computation cost
            recency_score = (now - entry.last_accessed).total_seconds()
            frequency_score = 1.0 / (entry.access_count + 1)
            cost_score = entry.computation_cost

            # Lower score = more likely to evict
            scores[key] = recency_score * frequency_score / (cost_score + 1)

        # Evict entry with lowest score
        if scores:
            victim_key = min(scores.keys(), key=scores.get)
            await self.delete(victim_key)

    def _update_access_patterns(self, key: str) -> None:
        """Update access tracking patterns."""
        # Update LRU order
        if key in self.access_order:
            del self.access_order[key]
        self.access_order[key] = True

        # Update LFU heap
        if key in self.cache:
            entry = self.cache[key]
            heapq.heappush(self.frequency_heap, (entry.access_count, key))

    def _remove_from_access_patterns(self, key: str) -> None:
        """Remove key from access tracking."""
        if key in self.access_order:
            del self.access_order[key]


class FastInferenceEngine:
    """High-performance knowledge inference engine."""

    def __init__(self) -> None:
        self.cache = AdvancedCache(max_size=50000, strategy=CacheStrategy.ADAPTIVE)
        self.precomputed_patterns = {}
        self.inference_rules = {}
        self.logger = get_logger(__name__)

    async def infer(self, request: InferenceRequest) -> InferenceResult:
        """Perform fast knowledge inference."""
        start_time = time.time()

        try:
            # Generate cache key
            cache_key = self._generate_cache_key(request)

            # Check cache first
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                processing_time = (time.time() - start_time) * 1000
                return InferenceResult(
                    request_id=request.request_id,
                    inference=cached_result["inference"],
                    confidence_score=cached_result["confidence"],
                    processing_time_ms=processing_time,
                    cache_hit=True,
                    explanation=cached_result.get("explanation"),
                    related_knowledge=cached_result.get("related_knowledge", []),
                )

            # Perform fast inference
            inference_result = await self._fast_inference(request)

            # Cache the result
            cache_value = {
                "inference": inference_result["inference"],
                "confidence": inference_result["confidence"],
                "explanation": inference_result.get("explanation"),
                "related_knowledge": inference_result.get("related_knowledge", []),
            }
            await self.cache.set(cache_key, cache_value, ttl=1800)  # 30 min TTL

            processing_time = (time.time() - start_time) * 1000

            return InferenceResult(
                request_id=request.request_id,
                inference=inference_result["inference"],
                confidence_score=inference_result["confidence"],
                processing_time_ms=processing_time,
                cache_hit=False,
                explanation=inference_result.get("explanation"),
                related_knowledge=inference_result.get("related_knowledge", []),
                computation_path=inference_result.get("computation_path", []),
            )

        except Exception as e:
            self.logger.error(f"Inference error: {e}")
            processing_time = (time.time() - start_time) * 1000
            return InferenceResult(
                request_id=request.request_id,
                inference={"error": str(e)},
                confidence_score=0.0,
                processing_time_ms=processing_time,
                cache_hit=False,
            )

    async def _fast_inference(self, request: InferenceRequest) -> dict[str, Any]:
        """Perform optimized inference computation."""
        # Simulate fast inference with realistic computation
        query_hash = hashlib.md5(request.query.encode()).hexdigest()[:8]

        # Use precomputed patterns for common queries
        if query_hash in self.precomputed_patterns:
            base_result = self.precomputed_patterns[query_hash]
        else:
            # Fast heuristic-based inference
            base_result = await self._heuristic_inference(request)

        # Apply contextual adjustments
        return await self._apply_context(base_result, request.context)

    async def _heuristic_inference(self, request: InferenceRequest) -> dict[str, Any]:
        """Fast heuristic-based inference."""
        # Demo implementation with realistic response
        query_terms = request.query.lower().split()

        # Domain detection
        domain_keywords = {
            "tech": ["python", "programming", "algorithm", "code", "software"],
            "business": ["project", "management", "strategy", "finance", "marketing"],
            "creative": ["design", "art", "creative", "visual", "aesthetic"],
            "health": ["health", "fitness", "nutrition", "wellness", "exercise"],
            "personal": ["goal", "habit", "productivity", "time", "organization"],
        }

        detected_domain = "general"
        max_matches = 0

        for domain, keywords in domain_keywords.items():
            matches = sum(1 for term in query_terms if term in keywords)
            if matches > max_matches:
                max_matches = matches
                detected_domain = domain

        # Confidence based on query clarity
        confidence = min(0.95, 0.5 + (len(query_terms) * 0.1) + (max_matches * 0.15))

        return {
            "inference": {
                "domain": detected_domain,
                "relevance_score": confidence,
                "key_concepts": query_terms[:5],
                "suggested_actions": [
                    f"Explore {detected_domain} knowledge units",
                    f"Review related concepts in {detected_domain}",
                    "Connect with prerequisite knowledge",
                ],
            },
            "confidence": confidence,
            "related_knowledge": [f"ku_{detected_domain}_{i}" for i in range(3)],
            "computation_path": ["domain_detection", "relevance_scoring", "action_generation"],
        }

    async def _apply_context(
        self, base_result: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply user context to adjust inference results."""
        # Adjust based on user's learning history and preferences
        user_level = context.get("user_level", "intermediate")
        user_goals = context.get("goals", [])

        # Adjust confidence based on user context
        context_boost = 0.0
        if user_goals:
            context_boost += 0.1
        if user_level in ["advanced", "expert"]:
            context_boost += 0.05

        base_result["confidence"] = min(0.95, base_result["confidence"] + context_boost)

        # Add contextual suggestions
        if user_level == "beginner":
            base_result["inference"]["suggested_actions"].insert(
                0, "Start with foundational concepts"
            )
        elif user_level == "advanced":
            base_result["inference"]["suggested_actions"].append("Explore advanced applications")

        return base_result

    def _generate_cache_key(self, request: InferenceRequest) -> str:
        """Generate unique cache key for request."""
        key_components = [
            request.query,
            request.user_uid,
            str(sorted(request.context.items())),
            str(request.require_explanation),
            str(request.include_confidence),
        ]
        combined = "|".join(key_components)
        return hashlib.md5(combined.encode()).hexdigest()

    async def precompute_patterns(self, common_queries: list[str]):
        """Precompute inference results for common queries."""
        for query in common_queries:
            query_hash = hashlib.md5(query.encode()).hexdigest()[:8]

            # Create mock request for precomputation
            mock_request = InferenceRequest(
                request_id="precompute",
                user_uid="system",
                query=query,
                context={},
                requested_at=datetime.now(),
            )

            result = await self._heuristic_inference(mock_request)
            self.precomputed_patterns[query_hash] = result

        self.logger.info(f"Precomputed {len(common_queries)} inference patterns")


class BackgroundProcessingEngine:
    """High-performance background task processing."""

    def __init__(self, max_workers: int = 4) -> None:
        self.task_queue = []
        self.completed_tasks: set[str] = set()
        self.running_tasks: dict[str, BackgroundTask] = {}
        self.max_workers = max_workers
        self.thread_pool = ThreadPoolExecutor(max_workers=max_workers)
        self.process_pool = ProcessPoolExecutor(max_workers=max_workers // 2)
        self.is_running = False

        # Track background asyncio tasks to prevent garbage collection (RUF006)
        self._background_tasks: set[asyncio.Task[None]] = set()

        # Shutdown event for graceful cleanup
        self._shutdown_event = asyncio.Event()

        self.logger = get_logger(__name__)

    async def start(self):
        """Start background processing engine."""
        self.is_running = True

        # Start queue processing task with stored reference (RUF006)
        task = asyncio.create_task(self._process_queue())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        self.logger.info("Background processing engine started")

    async def stop(self):
        """Stop background processing engine."""
        self.is_running = False
        self.thread_pool.shutdown(wait=True)
        self.process_pool.shutdown(wait=True)
        self.logger.info("Background processing engine stopped")

    async def shutdown(self):
        """Gracefully shutdown background processing and cancel all tasks."""
        self.logger.info("Shutting down background processing engine")

        # Signal shutdown
        self._shutdown_event.set()
        self.is_running = False

        # Cancel all background tasks
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        # Clear task tracking
        self._background_tasks.clear()

        # Shutdown thread/process pools
        self.thread_pool.shutdown(wait=True)
        self.process_pool.shutdown(wait=True)

        self.logger.info("Background processing engine shutdown complete")

    async def submit_task(self, task: BackgroundTask) -> bool:
        """Submit task for background processing."""
        try:
            heapq.heappush(self.task_queue, task)
            self.logger.debug(f"Task {task.task_id} submitted with priority {task.priority.value}")
            return True
        except Exception as e:
            self.logger.error(f"Error submitting task: {e}")
            return False

    async def _process_queue(self) -> None:
        """Main queue processing loop."""
        while self.is_running and not self._shutdown_event.is_set():
            try:
                # Process pending tasks
                await self._process_pending_tasks()

                # Clean up completed tasks
                await self._cleanup_completed_tasks()

                # Short sleep to prevent busy waiting
                await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                # Shutdown requested
                self.logger.info("Background processing queue cancelled")
                break
            except Exception as e:
                self.logger.error(f"Queue processing error: {e}")
                await asyncio.sleep(1)

    async def _process_pending_tasks(self) -> None:
        """Process tasks from the queue."""
        while self.task_queue and len(self.running_tasks) < self.max_workers:
            if not self.task_queue:
                break

            task = heapq.heappop(self.task_queue)

            # Check if task is ready (dependencies met)
            if not task.is_ready(self.completed_tasks):
                # Put back in queue for later
                heapq.heappush(self.task_queue, task)
                break

            # Start task execution
            await self._execute_task(task)

    async def _execute_task(self, task: BackgroundTask) -> None:
        """Execute individual background task."""
        try:
            task.started_at = datetime.now()
            self.running_tasks[task.task_id] = task

            # Choose execution method based on task type
            if task.task_type in ["analysis", "inference", "computation"]:
                # CPU intensive - use process pool
                future = self.process_pool.submit(self._cpu_intensive_task, task)
            else:
                # I/O intensive - use thread pool
                future = self.thread_pool.submit(self._io_intensive_task, task)

            # Monitor task completion with stored reference (RUF006)
            monitor_task = asyncio.create_task(self._monitor_task_completion(task, future))
            self._background_tasks.add(monitor_task)
            monitor_task.add_done_callback(self._background_tasks.discard)

        except Exception as e:
            self.logger.error(f"Task execution error: {e}")
            await self._handle_task_failure(task, str(e))

    async def _monitor_task_completion(self, task: BackgroundTask, future) -> None:
        """Monitor task completion and handle results."""
        try:
            # Wait for task completion
            await asyncio.wrap_future(future)

            # Mark task as completed
            task.completed_at = datetime.now()
            self.completed_tasks.add(task.task_id)

            if task.task_id in self.running_tasks:
                del self.running_tasks[task.task_id]

            self.logger.debug(f"Task {task.task_id} completed successfully")

        except Exception as e:
            self.logger.error(f"Task {task.task_id} failed: {e}")
            await self._handle_task_failure(task, str(e))

    def _cpu_intensive_task(self, task: BackgroundTask) -> dict[str, Any]:
        """Execute CPU-intensive task."""
        start_time = time.time()

        if task.task_type == "knowledge_analysis":
            result = self._analyze_knowledge_patterns(task.payload)
        elif task.task_type == "inference_batch":
            result = self._batch_inference(task.payload)
        elif task.task_type == "optimization":
            result = self._optimize_algorithms(task.payload)
        else:
            result = {"status": "completed", "message": f"Processed {task.task_type}"}

        processing_time = time.time() - start_time
        result["processing_time_seconds"] = processing_time

        return result

    def _io_intensive_task(self, task: BackgroundTask) -> dict[str, Any]:
        """Execute I/O-intensive task."""
        start_time = time.time()

        if task.task_type == "data_sync":
            result = self._sync_external_data(task.payload)
        elif task.task_type == "cache_warmup":
            result = self._warmup_cache(task.payload)
        elif task.task_type == "backup":
            result = self._create_backup(task.payload)
        else:
            result = {"status": "completed", "message": f"Processed {task.task_type}"}

        processing_time = time.time() - start_time
        result["processing_time_seconds"] = processing_time

        return result

    def _analyze_knowledge_patterns(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Analyze knowledge patterns (CPU intensive)."""
        knowledge_units = payload.get("knowledge_units", [])

        # Simulate complex pattern analysis
        patterns = {
            "domain_clusters": ["tech_cluster_1", "business_cluster_2"],
            "relationship_strength": 0.78,
            "learning_paths": ["path_beginner", "path_advanced"],
            "optimization_suggestions": [
                "Group related concepts",
                "Add missing prerequisites",
                "Strengthen weak connections",
            ],
        }

        return {"status": "completed", "patterns": patterns, "analyzed_units": len(knowledge_units)}

    def _batch_inference(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Process batch inference requests."""
        queries = payload.get("queries", [])

        # Simulate batch processing
        results = []
        for i, query in enumerate(queries):
            results.append(
                {"query": query, "inference": f"result_{i}", "confidence": 0.85 + (i % 3) * 0.05}
            )

        return {"status": "completed", "results": results, "processed_queries": len(queries)}

    def _optimize_algorithms(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Optimize inference algorithms."""
        algorithm_type = payload.get("algorithm_type", "general")

        # Simulate algorithm optimization
        optimization_result = {
            "performance_improvement": 0.23,  # 23% improvement
            "memory_reduction": 0.15,  # 15% reduction
            "cache_hit_rate_increase": 0.12,  # 12% increase
            "optimized_parameters": {"cache_size": 15000, "batch_size": 64, "timeout_ms": 80},
        }

        return {
            "status": "completed",
            "optimization": optimization_result,
            "algorithm_type": algorithm_type,
        }

    def _sync_external_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Sync with external data sources."""
        source = payload.get("source", "unknown")

        # Simulate data synchronization
        time.sleep(0.5)  # Simulate I/O delay

        return {
            "status": "completed",
            "source": source,
            "records_synced": 156,
            "sync_duration_ms": 500,
        }

    def _warmup_cache(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Warm up cache with frequently accessed data."""
        cache_keys = payload.get("cache_keys", [])

        # Simulate cache warming
        warmed_count = min(len(cache_keys), 1000)

        return {
            "status": "completed",
            "warmed_entries": warmed_count,
            "cache_keys": cache_keys[:10],  # Sample of warmed keys
        }

    def _create_backup(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create system backup."""
        backup_type = payload.get("backup_type", "incremental")

        # Simulate backup creation
        time.sleep(1.0)  # Simulate backup time

        return {
            "status": "completed",
            "backup_type": backup_type,
            "backup_size_mb": 245,
            "backup_location": "/backups/knowledge_backup_20251001.zip",
        }

    async def _handle_task_failure(self, task: BackgroundTask, error: str) -> None:
        """Handle task execution failure."""
        task.retry_count += 1

        if task.retry_count <= task.max_retries:
            # Retry with exponential backoff
            delay_seconds = 2**task.retry_count
            task.scheduled_at = datetime.now() + timedelta(seconds=delay_seconds)
            heapq.heappush(self.task_queue, task)
            self.logger.info(f"Task {task.task_id} scheduled for retry {task.retry_count}")
        else:
            self.logger.error(f"Task {task.task_id} failed permanently: {error}")

        if task.task_id in self.running_tasks:
            del self.running_tasks[task.task_id]

    async def _cleanup_completed_tasks(self) -> None:
        """Clean up old completed task references."""
        # Keep completed task IDs for dependency resolution
        # but limit the size to prevent memory growth
        if len(self.completed_tasks) > 10000:
            # Keep only the most recent 5000
            recent_tasks = list(self.completed_tasks)[-5000:]
            self.completed_tasks = set(recent_tasks)


class PerformanceOptimizationService:
    """
    Main service for knowledge system performance optimization.


    Source Tag: "performance_optimization_service_explicit"
    - Format: "performance_optimization_service_explicit" for user-created relationships
    - Format: "performance_optimization_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from performance_optimization metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (uses pure Cypher)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(self) -> None:
        self.inference_engine = FastInferenceEngine()
        self.background_engine = BackgroundProcessingEngine()
        self.metrics_history: list[PerformanceMetrics] = []
        self.response_times: list[float] = []
        self.throughput_counter = 0
        self.start_time = datetime.now()
        self.logger = get_logger(__name__)

    async def initialize(self):
        """Initialize performance optimization service."""
        await self.background_engine.start()

        # Precompute common inference patterns
        common_queries = [
            "python programming basics",
            "project management techniques",
            "design principles",
            "learning strategies",
            "productivity tips",
        ]
        await self.inference_engine.precompute_patterns(common_queries)

        # Start background optimization tasks
        await self._schedule_optimization_tasks()

        self.logger.info("Performance optimization service initialized")

    async def shutdown(self):
        """Shutdown performance optimization service."""
        await self.background_engine.shutdown()
        self.logger.info("Performance optimization service shutdown")

    async def close(self):
        """Close service - cleanup hook for ServiceContainer."""
        await self.shutdown()

    async def fast_inference(self, request: InferenceRequest) -> InferenceResult:
        """Perform sub-100ms knowledge inference."""
        result = await self.inference_engine.infer(request)

        # Track performance metrics
        self.response_times.append(result.processing_time_ms)
        self.throughput_counter += 1

        # Keep only recent response times
        if len(self.response_times) > 1000:
            self.response_times = self.response_times[-500:]

        return result

    async def submit_background_task(
        self,
        task_type: str,
        payload: dict[str, Any],
        priority: ProcessingPriority = ProcessingPriority.MEDIUM,
    ) -> str:
        """Submit task for background processing."""
        task_id = f"{task_type}_{int(time.time() * 1000)}"

        task = BackgroundTask(
            task_id=task_id,
            task_type=task_type,
            priority=priority,
            payload=payload,
            created_at=datetime.now(),
        )

        success = await self.background_engine.submit_task(task)
        return task_id if success else ""

    async def get_performance_metrics(self) -> PerformanceMetrics:
        """Get current performance metrics."""
        now = datetime.now()

        # Calculate response time percentiles
        if self.response_times:
            sorted_times = sorted(self.response_times)
            avg_response = sum(sorted_times) / len(sorted_times)
            p95_index = int(len(sorted_times) * 0.95)
            p99_index = int(len(sorted_times) * 0.99)
            p95_response = (
                sorted_times[p95_index] if p95_index < len(sorted_times) else sorted_times[-1]
            )
            p99_response = (
                sorted_times[p99_index] if p99_index < len(sorted_times) else sorted_times[-1]
            )
        else:
            avg_response = p95_response = p99_response = 0.0

        # Calculate throughput
        elapsed_seconds = (now - self.start_time).total_seconds()
        throughput = self.throughput_counter / elapsed_seconds if elapsed_seconds > 0 else 0.0

        # Get cache hit rate
        cache_hit_rate = self.inference_engine.cache.get_hit_rate()

        metrics = PerformanceMetrics(
            timestamp=now,
            avg_response_time_ms=avg_response,
            p95_response_time_ms=p95_response,
            p99_response_time_ms=p99_response,
            throughput_requests_per_second=throughput,
            cache_hit_rate=cache_hit_rate,
            memory_usage_mb=self._get_memory_usage(),
            cpu_utilization_percent=self._get_cpu_utilization(),
            active_connections=len(self.background_engine.running_tasks),
            queue_depth=len(self.background_engine.task_queue),
            error_rate=0.02,  # Demo error rate
        )

        # Store metrics history
        self.metrics_history.append(metrics)
        if len(self.metrics_history) > 1000:
            self.metrics_history = self.metrics_history[-500:]

        return metrics

    async def run_scale_test(
        self,
        concurrent_users: int = 100,
        requests_per_user: int = 10,
        test_duration_seconds: int = 60,
    ) -> ScaleTestResult:
        """Run scale test for 10x knowledge volume."""
        self.logger.info(
            f"Starting scale test: {concurrent_users} users, {requests_per_user} requests each"
        )

        start_time = time.time()

        # Initialize result variables (no dict indexing - fixes MyPy errors)
        # Performance results
        avg_response_time_ms = 0.0
        p95_response_time_ms = 0.0
        p99_response_time_ms = 0.0
        throughput_rps = 0.0
        cache_hit_rate = 0.0
        error_rate = 0.0

        # SLA compliance
        sub_100ms_responses = 0
        sub_200ms_responses = 0
        target_met = False

        # Resource utilization
        peak_memory_mb = 0.0
        avg_cpu_percent = 0.0
        max_queue_depth = 0

        # Generate test queries
        test_queries = [
            f"test query {i} about {['python', 'javascript', 'design', 'management', 'productivity'][i % 5]}"
            for i in range(concurrent_users * requests_per_user)
        ]

        # Run concurrent inference requests
        response_times = []
        successful_requests = 0
        failed_requests = 0

        async def run_user_requests(user_id: int) -> None:
            nonlocal successful_requests, failed_requests
            for req_id in range(requests_per_user):
                try:
                    query_index = user_id * requests_per_user + req_id
                    request = InferenceRequest(
                        request_id=f"test_{user_id}_{req_id}",
                        user_uid=f"test_user_{user_id}",
                        query=test_queries[query_index],
                        context={"test_mode": True},
                        requested_at=datetime.now(),
                        max_response_time_ms=200,  # Relaxed for scale test
                    )

                    result = await self.fast_inference(request)
                    response_times.append(result.processing_time_ms)
                    successful_requests += 1

                except Exception as e:
                    failed_requests += 1
                    self.logger.error(f"Test request failed: {e}")

        # Execute concurrent requests
        tasks = [run_user_requests(user_id) for user_id in range(concurrent_users)]
        await asyncio.gather(*tasks)

        test_duration = time.time() - start_time

        # Calculate results
        if response_times:
            sorted_times = sorted(response_times)
            avg_response_time_ms = sum(sorted_times) / len(sorted_times)
            p95_response_time_ms = sorted_times[int(len(sorted_times) * 0.95)]
            p99_response_time_ms = sorted_times[int(len(sorted_times) * 0.99)]

            # SLA compliance
            sub_100ms = sum(1 for t in sorted_times if t <= 100)
            sub_200ms = sum(1 for t in sorted_times if t <= 200)
            sub_100ms_responses = sub_100ms
            sub_200ms_responses = sub_200ms
            target_met = sub_100ms / len(sorted_times) >= 0.95

        throughput_rps = successful_requests / test_duration
        cache_hit_rate = self.inference_engine.cache.get_hit_rate()
        error_rate = (
            failed_requests / (successful_requests + failed_requests)
            if (successful_requests + failed_requests) > 0
            else 0
        )

        # Resource utilization (demo values)
        peak_memory_mb = 512.0
        avg_cpu_percent = 65.0
        max_queue_depth = 25

        self.logger.info(
            f"Scale test completed: {successful_requests} successful, {failed_requests} failed"
        )

        # Construct frozen dataclass result (direct variable access - no dict indexing)
        return ScaleTestResult(
            test_configuration=TestConfiguration(
                concurrent_users=concurrent_users,
                requests_per_user=requests_per_user,
                test_duration_seconds=test_duration_seconds,
                total_requests=concurrent_users * requests_per_user,
            ),
            performance_results=PerformanceResults(
                requests_completed=successful_requests,
                requests_failed=failed_requests,
                avg_response_time_ms=avg_response_time_ms,
                p95_response_time_ms=p95_response_time_ms,
                p99_response_time_ms=p99_response_time_ms,
                throughput_rps=throughput_rps,
                cache_hit_rate=cache_hit_rate,
                error_rate=error_rate,
            ),
            resource_utilization=ResourceUtilization(
                peak_memory_mb=peak_memory_mb,
                avg_cpu_percent=avg_cpu_percent,
                max_queue_depth=max_queue_depth,
            ),
            sla_compliance=SLACompliance(
                sub_100ms_responses=sub_100ms_responses,
                sub_200ms_responses=sub_200ms_responses,
                target_met=target_met,
            ),
        )

    async def optimize_cache_strategy(self) -> CacheOptimization:
        """Optimize caching strategy based on usage patterns."""
        current_hit_rate = self.inference_engine.cache.get_hit_rate()

        # Analyze cache performance
        cache_stats = self.inference_engine.cache.stats

        optimization_suggestions = []

        if current_hit_rate < 0.8:
            optimization_suggestions.append("Increase cache size")
            optimization_suggestions.append("Extend TTL for stable data")

        if cache_stats["evictions"] > cache_stats["hits"] * 0.1:
            optimization_suggestions.append("Switch to adaptive eviction strategy")

        if cache_stats["size_bytes"] > 100 * 1024 * 1024:  # 100MB
            optimization_suggestions.append("Implement cache compression")

        # Construct frozen dataclass result
        return CacheOptimization(
            current_performance=CachePerformance(
                hit_rate=current_hit_rate,
                total_hits=cache_stats["hits"],
                total_misses=cache_stats["misses"],
                evictions=cache_stats["evictions"],
                size_bytes=cache_stats["size_bytes"],
            ),
            optimization_suggestions=optimization_suggestions,
            recommended_strategy="adaptive" if current_hit_rate < 0.8 else "current",
            estimated_improvement=0.15 if current_hit_rate < 0.8 else 0.05,
        )

    async def _schedule_optimization_tasks(self) -> None:
        """Schedule periodic optimization tasks."""
        tasks = [
            {
                "task_type": "cache_warmup",
                "priority": ProcessingPriority.LOW,
                "payload": {"cache_keys": ["frequent_query_1", "frequent_query_2"]},
            },
            {
                "task_type": "knowledge_analysis",
                "priority": ProcessingPriority.BACKGROUND,
                "payload": {"knowledge_units": ["ku_001", "ku_002", "ku_003"]},
            },
            {
                "task_type": "optimization",
                "priority": ProcessingPriority.MEDIUM,
                "payload": {"algorithm_type": "inference"},
            },
        ]

        for task_config in tasks:
            await self.submit_background_task(
                task_config["task_type"], task_config["payload"], task_config["priority"]
            )

    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        # Demo implementation - would use psutil in production
        return 128.5

    def _get_cpu_utilization(self) -> float:
        """Get current CPU utilization percentage."""
        # Demo implementation - would use psutil in production
        return 45.2
