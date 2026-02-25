from __future__ import annotations

"""
Simplified Result Pattern with Rich Error Context
==================================================

A streamlined Result[T] pattern that provides excellent debugging capabilities
while maintaining simplicity. Replaces 37 error categories with 6 focused ones,
and complex error classes with a single rich context structure.

Key Improvements:
- 6 clear error categories (down from 37)
- Single ErrorContext class with rich debugging info
- Searchable error codes for log analysis
- Clear separation between developer and user messages
- Source location tracking for debugging
- ~200 lines instead of 900
"""

import logging
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable


def _utcnow() -> datetime:
    """Factory function for datetime.now(timezone.utc)"""
    return datetime.now(UTC)


logger = logging.getLogger(__name__)

# Type variables
T = TypeVar("T")
U = TypeVar("U")

# ============================================================================
# ERROR CATEGORIES - Simplified to 6 core categories
# ============================================================================


class ErrorCategory(Enum):
    """
    Core error categories that map to how errors should be handled.

    Each category represents a different failure mode requiring
    different handling strategies.
    """

    VALIDATION = "validation"  # Bad input data, user can fix
    DATABASE = "database"  # Database issues, may retry
    INTEGRATION = "integration"  # External service issues
    BUSINESS = "business"  # Domain rule violations
    NOT_FOUND = "not_found"  # Resource doesn't exist
    SYSTEM = "system"  # Unexpected system errors
    FORBIDDEN = "forbidden"  # Access denied (authenticated but not authorized)


class ErrorSeverity(Enum):
    """Error severity for logging and alerting decisions."""

    LOW = "low"  # Degraded functionality, can continue
    MEDIUM = "medium"  # Significant issue, feature unavailable
    HIGH = "high"  # Critical issue, major functionality broken
    CRITICAL = "critical"  # System-wide failure


# ============================================================================
# ERROR CONTEXT - Rich debugging information
# ============================================================================


@dataclass
class ErrorContext:
    """
    Rich error context providing excellent debugging capabilities.

    This single class replaces dozens of specific error classes while
    providing better debugging information through structured context.
    """

    category: ErrorCategory
    message: str  # Developer-facing error message
    code: str  # Searchable error code (e.g., "DB_CONN_TIMEOUT")
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    details: dict[str, Any] = field(default_factory=dict)  # Structured debugging data
    source_location: str | None = None  # Where error originated (file:function:line)
    user_message: str | None = None  # Safe message for end users
    timestamp: datetime = field(default_factory=_utcnow)
    stack_trace: str | None = None  # Captured stack trace if needed

    def __str__(self) -> str:
        """Clear error representation for logs."""
        location = f" at {self.source_location}" if self.source_location else ""
        return (
            f"[{self.severity.value}] {self.category.value}:{self.code} - {self.message}{location}"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "category": self.category.value,
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "details": self.details,
            "source_location": self.source_location,
            "user_message": self.user_message,
            "timestamp": self.timestamp.isoformat(),
            "stack_trace": self.stack_trace,
        }

    @classmethod
    def capture_current_location(cls) -> str:
        """Capture current source location from stack."""
        import inspect

        frame = inspect.currentframe()
        if frame and frame.f_back and frame.f_back.f_back:
            caller = frame.f_back.f_back
            return f"{caller.f_code.co_filename}:{caller.f_code.co_name}:{caller.f_lineno}"
        return "unknown"


# ============================================================================
# RESULT CLASS - Simple and powerful
# ============================================================================

# Sentinel value to distinguish "no value provided" from "None is the value"
_MISSING = object()


@dataclass
class Result[T]:
    """
    A Result monad for handling success/failure in a type-safe way.

    Prevents double-wrapping and provides rich error context for debugging.

    NOTE: None is a valid success value (for Optional[T] returns).
    Uses sentinel _MISSING to distinguish unset from None.
    """

    _value: Any = _MISSING
    _error: ErrorContext | None = None

    def __post_init__(self) -> None:
        """Validate that we have exactly one of value or error."""
        has_value = self._value is not _MISSING
        has_error = self._error is not None

        if not has_value and not has_error:
            raise ValueError("Result must have either value or error")
        if has_value and has_error:
            raise ValueError("Result cannot have both value and error")

    @property
    def is_ok(self) -> bool:
        """Check if the result represents success."""
        return self._error is None

    @property
    def is_error(self) -> bool:
        """
        Check if the result represents failure.

        Provides symmetry: .is_ok / .is_error (both use full words).
        Returns True if this Result contains an error, False otherwise.
        """
        return self._error is not None

    @property
    def value(self) -> T:
        """Get the success value. Raises if result is error."""
        if self._error:
            raise ValueError(f"Attempted to access value on error result: {self._error}")
        return self._value  # type: ignore[no-any-return]

    @property
    def error(self) -> ErrorContext | None:
        """Get the error context if present."""
        return self._error

    def expect_error(self, msg: str = "Expected error but result is Ok") -> ErrorContext:
        """
        Get the error context, raising ValueError if result is Ok.

        This method provides type-safe error access - MyPy knows the return
        type is ErrorContext (not Optional), eliminating the need for assertions.

        Use this when you've already checked .is_error and want to access the error.

        Args:
            msg: Custom error message if result is Ok

        Returns:
            ErrorContext (guaranteed non-None)

        Raises:
            ValueError: If result is Ok (no error present)

        Example:
            if result.is_error:
                error = result.expect_error()  # Type: ErrorContext
                return Result.fail(error)
        """
        if self._error is None:
            raise ValueError(msg)
        return self._error

    def expect(self, msg: str = "Expected Ok value but result is Err") -> T:
        """
        Get the Ok value, raising ValueError if result is Err.

        This is an alternative to the .value property that makes the
        expectation explicit and provides better error messages.

        Args:
            msg: Custom error message if result is Err

        Returns:
            The Ok value

        Raises:
            ValueError: If result is Err

        Example:
            # Instead of try/except on .value:
            user = result.expect("User must exist for this operation")
        """
        if self._error is not None:
            raise ValueError(f"{msg}: {self._error}")
        return self._value  # type: ignore[no-any-return]

    @classmethod
    def ok(cls, value: T) -> Result[T]:
        """Create a success result."""
        # Prevent double-wrapping
        if isinstance(value, Result):
            logger.warning("Attempted to double-wrap Result, returning original")
            return value
        return cls(_value=value, _error=None)

    @classmethod
    def fail(cls, error: ErrorContext | str | Result[Any]) -> Result[T]:
        """
        Create a failure result.

        Can accept:
        - ErrorContext for full control
        - String for quick failures (creates SYSTEM error)
        - Another Result object (for error propagation across types)

        The third option enables clean error propagation:
            result = await other_method()  # Returns Result[OtherType]
            if result.is_error:
                return Result.fail(result)  # Clean propagation!
        """
        if isinstance(error, str):
            # Quick failure with string message
            error = ErrorContext(
                category=ErrorCategory.SYSTEM,
                code="GENERIC_ERROR",
                message=error,
                source_location=ErrorContext.capture_current_location(),
            )
        elif isinstance(error, Result):
            # Error propagation from another Result type
            error = error.expect_error()

        return cls(_value=_MISSING, _error=error)

    def map(self, func: Callable[[T], U]) -> Result[U]:
        """
        Transform the value if successful, propagate error if not.

        Use this when func returns a plain value (not Result).

        Example:
            def double(x): return x * 2
            Result.ok(5).map(double)  # Result[int] with value 10
        """
        if self.is_ok:
            try:
                return Result.ok(func(self.value))
            except Exception as e:
                return Result.fail(
                    ErrorContext(
                        category=ErrorCategory.SYSTEM,
                        code="MAP_FUNCTION_ERROR",
                        message=f"Error in map function: {e!s}",
                        details={"original_value": str(self.value)},
                        source_location=ErrorContext.capture_current_location(),
                        stack_trace=traceback.format_exc(),
                    )
                )
        return self  # type: ignore[return-value]

    def and_then(self, func: Callable[[T], Result[U]]) -> Result[U]:
        """
        Chain a Result-returning function (monadic bind / flatMap).

        This is THE key method for functional composition. If this Result
        is Ok, calls func with the value and returns its Result. If this
        Result is Err, propagates the error without calling func.

        Use this when func returns a Result (not a plain value).

        Example:
            def get_user(uid: str) -> Result[User]: ...
            def get_prefs(user: User) -> Result[Prefs]: ...

            Result.ok("user-123")
                .and_then(get_user)
                .and_then(get_prefs)

        Args:
            func: Function that takes T and returns Result[U]

        Returns:
            Result[U] from func, or propagated error
        """
        if self.is_ok:
            try:
                result = func(self.value)
                if not isinstance(result, Result):
                    raise TypeError(
                        f"and_then function must return Result, got {type(result).__name__}. "
                        f"Use .map() for functions that return plain values."
                    )
                return result
            except Exception as e:
                return Result.fail(
                    ErrorContext(
                        category=ErrorCategory.SYSTEM,
                        code="AND_THEN_FUNCTION_ERROR",
                        message=f"Error in and_then function: {e!s}",
                        details={"original_value": str(self.value)},
                        source_location=ErrorContext.capture_current_location(),
                        stack_trace=traceback.format_exc(),
                    )
                )
        return self  # type: ignore[return-value]

    async def aflat_map(self, func: Callable[[T], Result[U]]) -> Result[U]:
        """
        Async version of and_then for chaining async Result-returning operations.

        If this Result is Ok, awaits func with the value and returns its Result.
        If this Result is Err, propagates the error without calling func.

        Works with both sync and async functions - if func is async, awaits it.

        Example:
            async def get_user(uid: str) -> Result[User]: ...
            def check_valid(user: User) -> Result[User]: ...

            result = await Result.ok("user-123")
                .aflat_map(get_user)
                .aflat_map(check_valid)

        Args:
            func: Function (sync or async) that takes T and returns Result[U]

        Returns:
            Result[U] from func, or propagated error
        """
        if self.is_ok:
            try:
                import inspect

                # Handle both sync and async functions
                result = func(self.value)
                if inspect.iscoroutine(result):
                    result = await result

                if not isinstance(result, Result):
                    raise TypeError(
                        f"aflat_map function must return Result, got {type(result).__name__}. "
                        f"Use async map for functions that return plain values."
                    )
                return result
            except Exception as e:
                return Result.fail(
                    ErrorContext(
                        category=ErrorCategory.SYSTEM,
                        code="AFLAT_MAP_FUNCTION_ERROR",
                        message=f"Error in aflat_map function: {e!s}",
                        details={"original_value": str(self.value)},
                        source_location=ErrorContext.capture_current_location(),
                        stack_trace=traceback.format_exc(),
                    )
                )
        return self  # type: ignore[return-value]

    def map_error(self, func: Callable[[ErrorContext], ErrorContext]) -> Result[T]:
        """
        Transform the error context if present, leave value unchanged.

        Useful for adding context to errors as they propagate up the call stack.

        Example:
            def add_operation_context(e):
                return ErrorContext(
                    **{k: v for k, v in e.to_dict().items() if k != 'details'},
                    details={**e.details, "operation": "user_creation"}
                )

            result.map_error(add_operation_context)

        Args:
            func: Function that transforms ErrorContext

        Returns:
            Result with transformed error, or original if success
        """
        if self.is_error and self._error:
            try:
                new_error = func(self._error)
                if not isinstance(new_error, ErrorContext):
                    logger.warning(  # type: ignore[unreachable]
                        f"map_error function must return ErrorContext, "
                        f"got {type(new_error).__name__}. Preserving original error."
                    )
                    return self
                return Result.fail(new_error)
            except Exception as e:
                # If transformation fails, preserve original error
                logger.warning(f"map_error function raised exception: {e}")
                return self
        return self

    def inspect(self, func: Callable[[T], None]) -> Result[T]:
        """
        Run a side effect on the value if Ok, return self for chaining.

        Useful for logging or other side effects without breaking the chain.

        Example:
            def log_value(v):
                logger.info(f"Processing {v}")

            result
                .inspect(log_value)
                .map(transform_value)

        Args:
            func: Function that performs side effect with value

        Returns:
            Self for chaining
        """
        if self.is_ok:
            try:
                func(self.value)
            except Exception as e:
                logger.warning(f"inspect function raised exception: {e}")
        return self

    def inspect_error(self, func: Callable[[ErrorContext], None]) -> Result[T]:
        """
        Run a side effect on the error if Err, return self for chaining.

        Useful for error logging without breaking the chain.

        Example:
            def log_error(e):
                logger.error(f"Failed: {e}")

            result
                .inspect_error(log_error)
                .map_error(add_context)

        Args:
            func: Function that performs side effect with error

        Returns:
            Self for chaining
        """
        if self.is_error and self._error:
            try:
                func(self._error)
            except Exception as e:
                logger.warning(f"inspect_error function raised exception: {e}")
        return self

    def or_else(self, default: T) -> T:
        """
        Get the value or return a default.

        Example:
            user = result.or_else(default_user)
        """
        return self.value if self.is_ok else default

    def log_if_error(self, prefix: str = "") -> Result[T]:
        """Log the error if present and return self for chaining."""
        if self.is_error and self._error is not None:
            log_msg = f"{prefix}: {self.error}" if prefix else str(self.error)

            if self._error.severity == ErrorSeverity.CRITICAL:
                logger.critical(log_msg, extra={"error_context": self._error.to_dict()})
            elif self._error.severity == ErrorSeverity.HIGH:
                logger.error(log_msg, extra={"error_context": self._error.to_dict()})
            elif self._error.severity == ErrorSeverity.MEDIUM:
                logger.warning(log_msg, extra={"error_context": self._error.to_dict()})
            else:
                logger.info(log_msg, extra={"error_context": self._error.to_dict()})

        return self


# ============================================================================
# ERROR FACTORIES - Convenient error creation
# ============================================================================


class Errors:
    """
    Factory functions for creating common errors with rich context.

    Error Category Decision Tree:
    =============================

    When to use each error category:

    1. **Errors.database(operation, message)** - Database/Neo4j Operations
       - Neo4j connection failures
       - Query execution errors
       - Transaction failures
       - Graph traversal errors
       Examples:
         - "Neo4j connection timeout"
         - "Cypher syntax error"
         - "Transaction rollback"

    2. **Errors.validation(message, field, value)** - Single Field Validation
       - Bad user input on a single field
       - Data format errors
       - Range validation (single field only)
       - Type coercion failures
       Examples:
         - "Email format invalid"
         - "Age must be between 0 and 120"
         - "Required field 'username' missing"
         - "Invalid enum value"

    3. **Errors.business(rule, message, **context)** - Domain Rules & Multi-Entity Constraints
       - Multi-field constraints (e.g., title + date uniqueness)
       - State-dependent operations (e.g., "account must be active")
       - Temporal constraints (e.g., "no overlapping budgets")
       - Workflow rules (e.g., "cannot delete user with active tasks")
       - State machine transitions (e.g., "cannot go from archived to draft")
       Examples:
         - "Journal with this title already exists on this date"
         - "Account is inactive"
         - "Overlapping budget exists for this period"
         - "Cannot delete user with 5 active tasks"
         - "Prerequisites not met"

    4. **Errors.not_found(resource, identifier)** - Resource Not Found
       - Entity lookup failed
       - Relationship not found
       - Path not found
       Examples:
         - "User 'abc123' not found"
         - "Task with uid 'task-456' not found"
         - "No path exists between nodes"

    5. **Errors.integration(service, message, status_code)** - External Service Failures
       - External API errors
       - Third-party service failures
       - Network communication errors
       Examples:
         - "OpenAI API returned 429 (rate limit)"
         - "Deepgram transcription failed"
         - "HTTP request timeout"

    6. **Errors.system(message, exception)** - Unexpected System Errors
       - Truly unexpected exceptions
       - Unknown error conditions
       - Programming errors
       - Last resort fallback
       Examples:
         - "Unexpected NoneType in calculation"
         - "Index out of bounds"
         - "Unhandled exception type"

    7. **Errors.unavailable(feature, reason)** - Unavailable Optional Features
       - Optional service not configured (embeddings, LLM)
       - Feature disabled by configuration
       - Soft degradation (not an actual error)
       - Use when system works but feature isn't available
       Examples:
         - "Semantic search unavailable: Embeddings service not configured"
         - "AI insights unavailable: LLM service not configured"
         - "Feature X disabled in configuration"

    Decision Flow:
    -------------
    1. Is it a database/Neo4j operation? → Errors.database()
    2. Is it bad input on a single field? → Errors.validation()
    3. Is it a domain rule with multiple entities/state? → Errors.business()
    4. Is it a missing resource? → Errors.not_found()
    5. Is it an external service failure? → Errors.integration()
    6. Is it an optional feature not configured? → Errors.unavailable()
    7. Is it truly unexpected? → Errors.system()

    Common Misclassifications:
    -------------------------
    ❌ Multi-field uniqueness as validation → ✅ Should be business
       Example: "Journal title + date unique" is a business rule, not validation

    ❌ State-dependent checks as validation → ✅ Should be business
       Example: "Account must be active" is a business rule, not validation

    ❌ Optional service missing as system error → ✅ Should be unavailable
       Example: "Embeddings not configured" is unavailable, not system error

    ❌ All exceptions as system → ✅ Should categorize by type
       Example: ValueError → validation, Neo4jError → database
    """

    @staticmethod
    def validation(
        message: str, field: str | None = None, value: Any = None, user_message: str | None = None
    ) -> ErrorContext:
        """Create a validation error."""
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)

        return ErrorContext(
            category=ErrorCategory.VALIDATION,
            code=f"VALIDATION_{'FIELD_' + field.upper() if field else 'GENERIC'}",
            message=message,
            severity=ErrorSeverity.LOW,
            details=details,
            user_message=user_message or message,
            source_location=ErrorContext.capture_current_location(),
        )

    @staticmethod
    def not_found(resource: str, identifier: Any = None) -> ErrorContext:
        """Create a not found error."""
        details = {"resource": resource}
        if identifier:
            details["identifier"] = str(identifier)

        return ErrorContext(
            category=ErrorCategory.NOT_FOUND,
            code=f"NOT_FOUND_{resource.upper()}",
            message=f"{resource} not found" + (f": {identifier}" if identifier else ""),
            severity=ErrorSeverity.LOW,
            details=details,
            user_message=f"The requested {resource} could not be found",
            source_location=ErrorContext.capture_current_location(),
        )

    @staticmethod
    def database(
        operation: str, message: str, query: str | None = None, **details: Any
    ) -> ErrorContext:
        """Create a database error."""
        error_details = {"operation": operation}
        if query:
            error_details["query"] = query[:200]  # Truncate long queries
        error_details.update(details)

        return ErrorContext(
            category=ErrorCategory.DATABASE,
            code=f"DB_{operation.upper()}",
            message=message,
            severity=ErrorSeverity.HIGH,
            details=error_details,
            user_message="A database error occurred. Please try again later.",
            source_location=ErrorContext.capture_current_location(),
            stack_trace=traceback.format_exc(),
        )

    @staticmethod
    def integration(
        service: str, message: str, status_code: int | None = None, **details: Any
    ) -> ErrorContext:
        """Create an integration/external service error."""
        error_details: dict[str, Any] = {"service": service}
        if status_code:
            error_details["status_code"] = status_code
        error_details.update(details)

        return ErrorContext(
            category=ErrorCategory.INTEGRATION,
            code=f"INTEGRATION_{service.upper()}",
            message=message,
            severity=ErrorSeverity.MEDIUM,
            details=error_details,
            user_message=f"Error communicating with {service}",
            source_location=ErrorContext.capture_current_location(),
        )

    @staticmethod
    def business(rule: str, message: str, **details: Any) -> ErrorContext:
        """Create a business logic error."""
        return ErrorContext(
            category=ErrorCategory.BUSINESS,
            code=f"BUSINESS_{rule.upper()}",
            message=message,
            severity=ErrorSeverity.MEDIUM,
            details={"rule": rule, **details},
            user_message=message,  # Business errors often have user-safe messages
            source_location=ErrorContext.capture_current_location(),
        )

    @staticmethod
    def system(message: str, exception: Exception | None = None, **details: Any) -> ErrorContext:
        """Create a system error for unexpected failures."""
        error_details = details.copy()
        if exception:
            error_details["exception_type"] = type(exception).__name__
            error_details["exception_message"] = str(exception)

        return ErrorContext(
            category=ErrorCategory.SYSTEM,
            code="SYSTEM_ERROR",
            message=message,
            severity=ErrorSeverity.CRITICAL,
            details=error_details,
            user_message="An unexpected error occurred",
            source_location=ErrorContext.capture_current_location(),
            stack_trace=traceback.format_exc() if exception else None,
        )

    @staticmethod
    def forbidden(
        action: str, reason: str | None = None, required_role: str | None = None
    ) -> ErrorContext:
        """
        Create a forbidden/authorization error (HTTP 403).

        Use for authenticated users who lack permission for an action.
        For unauthenticated users, use require_authenticated_user() which raises 401.

        Args:
            action: What the user tried to do (e.g., "access admin panel", "delete user")
            reason: Why access was denied (optional)
            required_role: The role required for this action (optional)
        """
        details: dict[str, Any] = {"action": action}
        if required_role:
            details["required_role"] = required_role

        message = reason or f"Access denied for action: {action}"

        return ErrorContext(
            category=ErrorCategory.FORBIDDEN,
            code=f"FORBIDDEN_{action.upper().replace(' ', '_')}",
            message=message,
            severity=ErrorSeverity.MEDIUM,
            details=details,
            user_message=message,
            source_location=ErrorContext.capture_current_location(),
        )

    @staticmethod
    def unavailable(feature: str, reason: str, **details: Any) -> ErrorContext:
        """
        Create an unavailable feature error (soft failure).

        Use when an optional feature can't be used because a service isn't configured.
        This is NOT an error - the system is working correctly, but this specific
        feature isn't available.

        Distinguishes between:
        - Error: Something broke (use Errors.system() or Errors.integration())
        - Unavailable: Feature not configured (use this method)

        Args:
            feature: Name of the unavailable feature (e.g., "semantic_search", "ai_insights")
            reason: Why it's unavailable (e.g., "Embeddings service not configured")
            **details: Additional context

        Example:
            Errors.unavailable(
                feature="semantic_search",
                reason="Embeddings service not configured",
                operation="find_similar_tasks"
            )
        """
        return ErrorContext(
            category=ErrorCategory.SYSTEM,
            code=f"UNAVAILABLE_{feature.upper()}",
            message=f"{feature} unavailable: {reason}",
            severity=ErrorSeverity.MEDIUM,  # Feature unavailable, not critical
            details={"feature": feature, "reason": reason, **details},
            user_message=f"This feature is currently unavailable: {feature}",
            source_location=ErrorContext.capture_current_location(),
        )


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

"""
# Simple validation error
result = Result.fail(Errors.validation(
    "Email format invalid",
    field="email",
    value="not-an-email",
    user_message="Please enter a valid email address"
))

# Database error with context
result = Result.fail(Errors.database(
    operation="connection",
    message="Connection timeout after 30s",
    query="MATCH (n:User) RETURN n",
    host="neo4j://localhost:7687",
    timeout=30
))

# System error for unexpected failures
result = Result.fail(Errors.system(
    message="Unexpected error during processing",
    operation="process_data",
    details={"context": "additional info"}
))

# Chaining with logging
result = (some_operation()
    .map(transform_data)
    .log_if_error("Failed to process user data")
)

# Type-safe error access (NEW - recommended pattern)
if result.is_error:
    error = result.expect_error()  # Type: ErrorContext (not Optional!)
    return Result.fail(error)

# Type-safe value access (NEW - explicit expectation)
user = await get_user(uid)
if user.is_ok:
    return user.expect("User must exist")  # Raises if somehow Err

# Pattern matching by category
if result.is_error:
    error = result.expect_error()  # No assertion needed
    match error.category:
        case ErrorCategory.VALIDATION:
            return Response(400, error.user_message)
        case ErrorCategory.NOT_FOUND:
            return Response(404, error.user_message)
        case ErrorCategory.DATABASE:
            # Maybe retry or fallback
            return Response(503, "Service temporarily unavailable")
        case _:
            return Response(500, "Internal server error")

# Old pattern (still works, but verbose)
if result.is_error:
    return Result.fail(result)
"""
