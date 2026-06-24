"""
Async Retry Utility
===================

Exponential-backoff retry decorator for async functions that call external
services (LLMs, Neo4j, HTTP). Uses stdlib asyncio only — no extra deps.

Usage:
    from core.utils.retry import async_retry
    from core.utils.exception_types import OPENAI_EXCEPTIONS

    @async_retry(exceptions=OPENAI_EXCEPTIONS)
    async def call_llm(...) -> ...:
        ...

See: /docs/patterns/ERROR_HANDLING.md
"""

import asyncio
import functools
import random
from collections.abc import Callable
from typing import Any, TypeVar

from core.utils.logging import get_logger

_logger = get_logger("skuel.utils.retry")

F = TypeVar("F", bound=Callable[..., Any])

_UNSET: tuple[type[BaseException], ...] = (Exception,)


def async_retry(
    *,
    exceptions: tuple[type[BaseException], ...] = _UNSET,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
) -> Callable[[F], F]:
    """Decorator: retry *exceptions* up to *max_attempts* with exponential backoff.

    Args:
        exceptions: Exception types that trigger a retry. Pass a tuple from
            ``core.utils.exception_types`` (e.g. ``OPENAI_EXCEPTIONS``).
        max_attempts: Total attempts (including the first). Default 3.
        base_delay: Seconds before the first retry. Doubles each round.
        max_delay: Ceiling on the computed backoff.
        jitter: Add ±25 % random noise to prevent thundering-herd. Default True.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        break
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    if jitter:
                        delay *= 0.75 + random.random() * 0.5  # ±25 %
                    _logger.warning(
                        "Retrying %s (attempt %d/%d) after %.1fs: %s",
                        func.__qualname__,
                        attempt,
                        max_attempts,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
            raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator


__all__ = ["async_retry"]
