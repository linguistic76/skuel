"""
Event Bus Infrastructure
========================

Type-safe in-memory event bus for SKUEL's event-driven architecture.

Features:
- Type-safe event subscriptions
- Sync and async handler support
- Error handling with logging
- Event replay capability (for testing)

Can be replaced with distributed implementations (Redis, RabbitMQ, Kafka) later.

Design:
- Subscribers register by event TYPE (class), not string
- Handlers receive strongly-typed event objects
- Failed handlers don't block other handlers
- Event history can be captured for debugging/replay

Migration Status:
- Phase 1: Domain events defined ✅
- Phase 2: Services publishing events 🚧
- Phase 3: Subscribers wired in bootstrap 🚧
"""

import asyncio
import time
from collections.abc import Callable
from typing import Any

from core.utils.logging import get_logger

logger = get_logger(__name__)


class InMemoryEventBus:
    """
    Type-safe in-memory event bus for single-process use.

    Supports both sync and async event handlers.
    Perfect for starting - can be replaced with distributed bus later.

    Usage:
        # Subscribe to typed events
        event_bus.subscribe(TaskCompleted, handler_function)

        # Publish typed events
        event = TaskCompleted(task_uid="...", user_uid="...", occurred_at=datetime.now())
        await event_bus.publish_async(event)
    """

    def __init__(
        self,
        capture_history: bool = False,
        metrics_cache: Any = None,
    ) -> None:
        """
        Initialize event bus.

        Args:
            capture_history: If True, maintain event history for debugging/replay
            metrics_cache: MetricsCache instance for performance tracking (optional)
        """
        self._handlers: dict[type, list[Callable]] = {}
        self._async_handlers: dict[type, list[Callable]] = {}
        self._capture_history = capture_history
        self._event_history: list[
            Any
        ] = []  # Always initialize (populated only if capture_history=True)
        self._metrics_cache = metrics_cache

        # Track background tasks to prevent garbage collection (RUF006)
        self._background_tasks: set[asyncio.Task[None]] = set()

        logger.info(
            f"In-memory event bus initialized "
            f"(typed events enabled, metrics_cache={'enabled' if metrics_cache else 'disabled'})"
        )

    def publish(self, event: Any) -> None:
        """
        Publish an event to all registered handlers (sync version).

        Args:
            event: Event object (instance of a domain event class)

        Note: Prefer publish_async() for async contexts.
        """
        event_type = type(event)

        # Capture event in history if enabled
        if self._capture_history:
            self._event_history.append(event)

        # Log the event
        event_type_str = getattr(event, "event_type", event_type.__name__)
        logger.debug(f"Publishing event: {event_type_str}")

        # Call synchronous handlers
        for handler in self._handlers.get(event_type, []):
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in event handler for {event_type_str}: {e}", exc_info=True)

        # Schedule async handlers as background tasks
        for handler in self._async_handlers.get(event_type, []):
            task = asyncio.create_task(self._call_async_handler(handler, event))
            # Store reference to prevent garbage collection (RUF006)
            self._background_tasks.add(task)
            # Auto-cleanup when done to prevent memory leaks
            task.add_done_callback(self._background_tasks.discard)

    async def publish_async(self, event: Any) -> None:
        """
        Publish an event to all registered handlers (async version).

        Preferred method for async contexts (services).

        Args:
            event: Event object (instance of a domain event class)
        """
        event_type = type(event)
        event_type_str = getattr(event, "event_type", event_type.__name__)

        # Start timing for performance monitoring
        start_time = time.perf_counter() if self._metrics_cache else None

        # Capture event in history if enabled
        if self._capture_history:
            self._event_history.append(event)

        # Log the event
        logger.debug(f"Publishing event: {event_type_str}")

        # Count handlers called
        handlers_called = 0

        # Call synchronous handlers
        for handler in self._handlers.get(event_type, []):
            handler_start = time.perf_counter() if self._metrics_cache else None
            handler_name = handler.__name__
            handlers_called += 1

            try:
                handler(event)

                # Record handler metrics
                if self._metrics_cache and handler_start is not None:
                    duration_ms = (time.perf_counter() - handler_start) * 1000
                    await self._metrics_cache.record_handler_execution(
                        event_type=event_type_str,
                        handler_name=handler_name,
                        duration_ms=duration_ms,
                        error=None,
                    )

            except Exception as e:
                logger.error(f"Error in sync handler for {event_type_str}: {e}", exc_info=True)

                # Record error metrics
                if self._metrics_cache and handler_start is not None:
                    duration_ms = (time.perf_counter() - handler_start) * 1000
                    await self._metrics_cache.record_handler_execution(
                        event_type=event_type_str,
                        handler_name=handler_name,
                        duration_ms=duration_ms,
                        error=e,
                    )

        # Call async handlers concurrently for better performance
        async_handlers = self._async_handlers.get(event_type, [])
        if async_handlers:
            handlers_called += len(async_handlers)
            # Execute all async handlers concurrently with per-handler metrics
            await asyncio.gather(
                *[
                    self._call_async_handler_with_metrics(handler, event, event_type_str)
                    for handler in async_handlers
                ],
                return_exceptions=True,  # Maintain error isolation
            )

        # Record event publication metrics
        if self._metrics_cache and start_time is not None:
            total_duration_ms = (time.perf_counter() - start_time) * 1000
            await self._metrics_cache.record_event_publication(
                event_type=event_type_str,
                duration_ms=total_duration_ms,
                handlers_called=handlers_called,
            )

    async def _call_async_handler(self, handler: Callable, event: Any) -> None:
        """Helper to call async handler with error handling."""
        try:
            await handler(event)
        except Exception as e:
            event_type_str = getattr(event, "event_type", type(event).__name__)
            logger.error(f"Error in async handler for {event_type_str}: {e}", exc_info=True)

    async def _call_async_handler_with_metrics(
        self, handler: Callable, event: Any, event_type_str: str
    ) -> None:
        """Helper to call async handler with error handling and performance metrics."""
        handler_name = handler.__name__
        handler_start = time.perf_counter() if self._metrics_cache else None

        try:
            await handler(event)

            # Record success metrics
            if self._metrics_cache and handler_start is not None:
                duration_ms = (time.perf_counter() - handler_start) * 1000
                await self._metrics_cache.record_handler_execution(
                    event_type=event_type_str,
                    handler_name=handler_name,
                    duration_ms=duration_ms,
                    error=None,
                )

        except Exception as e:
            logger.error(f"Error in async handler for {event_type_str}: {e}", exc_info=True)

            # Record error metrics
            if self._metrics_cache and handler_start is not None:
                duration_ms = (time.perf_counter() - handler_start) * 1000
                await self._metrics_cache.record_handler_execution(
                    event_type=event_type_str,
                    handler_name=handler_name,
                    duration_ms=duration_ms,
                    error=e,
                )

    def subscribe(self, event_type: type, handler: Callable) -> None:
        """
        Subscribe to events of a given type.

        Args:
            event_type: Event class to subscribe to (e.g., TaskCompleted)
            handler: Function to call when event is published
                     Can be sync or async - auto-detected

        Example:
            async def handle_task_completed(event: TaskCompleted):
                await invalidate_context(event.user_uid)

            event_bus.subscribe(TaskCompleted, handle_task_completed)
        """
        if asyncio.iscoroutinefunction(handler):
            if event_type not in self._async_handlers:
                self._async_handlers[event_type] = []
            self._async_handlers[event_type].append(handler)
            handler_type = "async"
        else:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler)
            handler_type = "sync"

        logger.debug(
            f"{handler_type.capitalize()} handler registered for {event_type.__name__}: "
            f"{handler.__name__}"
        )

    def unsubscribe(self, event_type: type, handler: Callable) -> None:
        """
        Unsubscribe from events.

        Args:
            event_type: Event class to unsubscribe from
            handler: Handler function to remove
        """
        if asyncio.iscoroutinefunction(handler):
            if event_type in self._async_handlers:
                try:
                    self._async_handlers[event_type].remove(handler)
                    logger.debug(f"Unsubscribed handler from {event_type.__name__}")
                except ValueError:
                    logger.warning(f"Handler not found for {event_type.__name__}")
        else:
            if event_type in self._handlers:
                try:
                    self._handlers[event_type].remove(handler)
                    logger.debug(f"Unsubscribed handler from {event_type.__name__}")
                except ValueError:
                    logger.warning(f"Handler not found for {event_type.__name__}")

    def get_handler_count(self, event_type: type) -> int:
        """
        Get number of handlers subscribed to an event type.

        Useful for debugging and testing.
        """
        sync_count = len(self._handlers.get(event_type, []))
        async_count = len(self._async_handlers.get(event_type, []))
        return sync_count + async_count

    def get_event_history(self) -> list[Any]:
        """
        Get event history (if capture_history=True).

        Useful for debugging and testing event flow.
        """
        return self._event_history.copy()

    def clear_event_history(self) -> None:
        """Clear event history."""
        self._event_history.clear()

    def get_all_event_types(self) -> set[type]:
        """Get all event types that have subscribers."""
        return set(self._handlers.keys()) | set(self._async_handlers.keys())

    async def get_performance_metrics(self) -> dict[str, Any] | None:
        """
        Get cached performance metrics for debugging.

        Note: Returns cache data (last 100 items). Query Prometheus for complete metrics.

        Returns:
            Cached metrics dict or None if cache disabled
        """
        if not self._metrics_cache:
            return None

        return {
            "summary": await self._metrics_cache.get_summary(),
            "slow_handlers": await self._metrics_cache.get_slow_handlers(),
            "event_metrics": await self._metrics_cache.get_event_metrics(),
            "handler_metrics": await self._metrics_cache.get_handler_metrics(),
        }

    async def get_slow_handlers(self, threshold_ms: float | None = None) -> list[dict[str, Any]]:
        """
        Get list of slow event handlers from cache.

        Args:
            threshold_ms: Custom threshold (default 100ms)

        Returns:
            List of slow handlers with cached metrics
        """
        if not self._metrics_cache:
            return []

        threshold = threshold_ms if threshold_ms is not None else 100.0
        return await self._metrics_cache.get_slow_handlers(threshold)

    def get_pending_task_count(self) -> int:
        """
        Get count of pending background tasks.

        Useful for debugging and testing to ensure tasks complete.

        Returns:
            Number of background tasks still running
        """
        return len(self._background_tasks)

    async def wait_for_pending_tasks(self, timeout_seconds: float | None = None) -> None:
        """
        Wait for all pending background tasks to complete.

        Useful for graceful shutdown and testing.

        Args:
            timeout_seconds: Maximum time to wait in seconds (None = wait forever)

        Raises:
            asyncio.TimeoutError: If timeout is exceeded
        """
        if not self._background_tasks:
            return

        async with asyncio.timeout(timeout_seconds):
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

    def cancel_all_tasks(self) -> int:
        """
        Cancel all pending background tasks.

        Useful for emergency shutdown or testing cleanup.

        Returns:
            Number of tasks cancelled
        """
        count = len(self._background_tasks)
        for task in self._background_tasks:
            task.cancel()
        return count
