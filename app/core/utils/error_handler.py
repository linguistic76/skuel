"""
Error Handler Utility
=====================

Provides consistent error handling patterns across the application.
Wraps repository and service methods with proper error handling.
"""

import asyncio
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from neo4j.exceptions import (
    ConstraintError,
    CypherSyntaxError,
    Neo4jError,
    ServiceUnavailable,
    SessionExpired,
)

from core.errors import DatabaseError, NotFoundError, ValidationError
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

T = TypeVar("T")
logger = get_logger(__name__)


def handle_repository_errors(func: Callable) -> Callable:
    """
    Decorator for repository methods to handle Neo4j-specific errors.
    Converts Neo4j errors to domain errors.
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except ConstraintError as e:
            logger.error(f"Constraint violation in {func.__name__}: {e}")
            raise Errors.validation(f"Constraint violation: {e!s}") from e
        except CypherSyntaxError as e:
            logger.error(f"Cypher syntax error in {func.__name__}: {e}")
            raise Errors.database("operation", f"Query syntax error: {e!s}") from e
        except (SessionExpired, ServiceUnavailable) as e:
            logger.error(f"Neo4j connection error in {func.__name__}: {e}")
            raise Errors.database("operation", f"Database connection error: {e!s}") from e
        except Neo4jError as e:
            logger.error(f"Neo4j error in {func.__name__}: {e}")
            raise Errors.database("operation", f"Database error: {e!s}") from e
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            raise Errors.database("operation", f"Unexpected error: {e!s}") from e

    return wrapper


def handle_service_errors(func: Callable) -> Callable:
    """
    Decorator for service methods to handle errors and return Result objects.
    Ensures consistent error handling patterns.
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Result[Any]:
        try:
            result = await func(*args, **kwargs)
            # If the function already returns a Result, pass it through
            if isinstance(result, Result):
                return result
            # Otherwise wrap in Result.ok
            return Result.ok(result)
        except NotFoundError as e:
            logger.warning(f"Not found in {func.__name__}: {e}")
            return Result.fail(e)
        except ValidationError as e:
            logger.warning(f"Validation error in {func.__name__}: {e}")
            return Result.fail(e)
        except DatabaseError as e:
            logger.error(f"Database error in {func.__name__}: {e}")
            return Result.fail(e)
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            return Result.fail(Errors.database("operation", f"Unexpected error: {e!s}"))

    return wrapper


class ErrorContext:
    """
    Context manager for error handling with detailed context.
    Provides structured error reporting.
    """

    def __init__(self, operation: str, **context: Any) -> None:
        self.operation = operation
        self.context = context
        self.logger = get_logger(self.__class__.__name__)

    async def __aenter__(self) -> None:
        self.logger.debug(f"Starting {self.operation}", extra=self.context)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type:
            self.logger.error(
                f"Error in {self.operation}: {exc_val}",
                extra={**self.context, "error_type": exc_type.__name__},
            )

            # Convert to appropriate domain error
            if isinstance(exc_val, Neo4jError):
                if "not found" in str(exc_val).lower():
                    raise NotFoundError(str(exc_val)) from exc_val
                elif "constraint" in str(exc_val).lower():
                    raise ValidationError(str(exc_val)) from exc_val
                else:
                    raise DatabaseError(str(exc_val)) from exc_val

            # Re-raise if already a domain error
            if isinstance(exc_val, NotFoundError | ValidationError | DatabaseError):
                raise

            # Wrap unexpected errors
            raise DatabaseError(f"Error in {self.operation}: {exc_val}") from exc_val
        else:
            self.logger.debug(f"Completed {self.operation}", extra=self.context)


def with_retry(max_attempts: int = 3, delay: float = 1.0):
    """
    Decorator to retry operations on transient failures.
    Useful for database operations that might fail due to temporary issues.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_error = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except (SessionExpired, ServiceUnavailable) as e:
                    last_error = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"Retrying {func.__name__} after error (attempt {attempt + 1}/{max_attempts}): {e}"
                        )
                        await asyncio.sleep(delay * (attempt + 1))
                    else:
                        logger.error(f"Max retries reached for {func.__name__}: {e}")
                except Exception:
                    # Don't retry on non-transient errors
                    raise

            # If we get here, all retries failed
            raise Errors.database(
                "operation", f"Operation failed after {max_attempts} attempts: {last_error}"
            )

        return wrapper

    return decorator


def validate_required_fields(**field_requirements: Any):
    """
    Decorator to validate required fields before executing a method.

    Usage:
        @validate_required_fields(uid=str, title=str, body=str)
        async def create_unit(self, uid, title, body, ...):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract arguments
            import inspect

            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()

            # Validate required fields
            for field_name, field_type in field_requirements.items():
                value = bound.arguments.get(field_name)

                if value is None:
                    raise Errors.validation(f"Required field '{field_name}' is missing")

                if field_type and not isinstance(value, field_type):
                    raise Errors.validation(
                        f"Field '{field_name}' must be of type {field_type.__name__}"
                    )

                # Additional validation for strings
                if field_type is str and not value.strip():
                    raise Errors.validation(f"Field '{field_name}' cannot be empty")

            return await func(*args, **kwargs)

        return wrapper

    return decorator


class TransactionManager:
    """
    Manager for Neo4j transactions with proper error handling.
    Ensures transactions are properly committed or rolled back.
    """

    def __init__(self, driver, operation_name: str = "transaction") -> None:
        self.driver = driver
        self.operation_name = operation_name
        self.logger = get_logger(self.__class__.__name__)

    async def execute_write(self, work_func: Callable, **params: Any) -> Any:
        """Execute a write transaction with error handling"""
        async with (
            ErrorContext(f"write_{self.operation_name}", **params),
            self.driver.session() as session,
        ):
            try:
                result = await session.execute_write(work_func, **params)
                self.logger.debug(f"Write transaction completed: {self.operation_name}")
                return result
            except Exception as e:
                self.logger.error(f"Write transaction failed: {self.operation_name}: {e}")
                raise

    async def execute_read(self, work_func: Callable, **params: Any) -> Any:
        """Execute a read transaction with error handling"""
        async with (
            ErrorContext(f"read_{self.operation_name}", **params),
            self.driver.session() as session,
        ):
            try:
                result = await session.execute_read(work_func, **params)
                self.logger.debug(f"Read transaction completed: {self.operation_name}")
                return result
            except Exception as e:
                self.logger.error(f"Read transaction failed: {self.operation_name}: {e}")
                raise
