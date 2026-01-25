#!/usr/bin/env python3
"""
Comprehensive Edge Case Tests for Result Pattern
=================================================

Tests edge cases and advanced features not covered in basic tests.
"""

from datetime import UTC, datetime

import pytest

from core.utils.result_simplified import ErrorCategory, ErrorContext, Errors, ErrorSeverity, Result


class TestResultEdgeCases:
    """Test Result pattern edge cases."""

    def test_none_as_valid_success_value(self):
        """Test that None is a valid success value for Optional[T]."""
        result = Result.ok(None)
        assert result.is_ok
        assert result.value is None
        assert result.error is None

    def test_false_as_valid_success_value(self):
        """Test that False is a valid success value."""
        result = Result.ok(False)
        assert result.is_ok
        assert result.value is False
        assert not result.value  # Value is falsy but result is success

    def test_zero_as_valid_success_value(self):
        """Test that 0 is a valid success value."""
        result = Result.ok(0)
        assert result.is_ok
        assert result.value == 0
        assert result.value == 0  # Falsy but valid

    def test_empty_string_as_valid_success_value(self):
        """Test that empty string is a valid success value."""
        result = Result.ok("")
        assert result.is_ok
        assert result.value == ""

    def test_empty_list_as_valid_success_value(self):
        """Test that empty list is a valid success value."""
        result = Result.ok([])
        assert result.is_ok
        assert result.value == []

    def test_accessing_value_on_error_raises(self):
        """Test that accessing value on error result raises ValueError."""
        result = Result.fail("Error occurred")
        with pytest.raises(ValueError, match="Attempted to access value on error result"):
            _ = result.value

    def test_result_cannot_have_both_value_and_error(self):
        """Test that Result cannot be created with both value and error."""
        error = Errors.system("Test error")
        with pytest.raises(ValueError, match="cannot have both value and error"):
            Result(_value=42, _error=error)

    def test_result_must_have_value_or_error(self):
        """Test that Result must have either value or error."""
        from core.utils.result_simplified import _MISSING

        with pytest.raises(ValueError, match="must have either value or error"):
            Result(_value=_MISSING, _error=None)

    def test_and_then_with_non_result_return_raises(self):
        """Test that and_then raises if function doesn't return Result."""
        result = Result.ok(42)

        def not_returning_result(x):
            return x * 2  # Returns int, not Result

        chained = result.and_then(not_returning_result)
        assert chained.is_error
        assert "must return Result" in chained.error.message
        assert chained.error.code == "AND_THEN_FUNCTION_ERROR"

    def test_and_then_propagates_error(self):
        """Test that and_then propagates error without calling function."""
        call_count = 0

        def should_not_be_called(x):
            nonlocal call_count
            call_count += 1
            return Result.ok(x * 2)

        result = Result.fail("Original error")
        chained = result.and_then(should_not_be_called)

        assert chained.is_error
        assert chained.error.message == "Original error"
        assert call_count == 0  # Function should not be called

    def test_and_then_chains_multiple_results(self):
        """Test chaining multiple Result-returning operations."""

        def add_one(x):
            return Result.ok(x + 1)

        def multiply_two(x):
            return Result.ok(x * 2)

        def as_string(x):
            return Result.ok(str(x))

        result = (
            Result.ok(5)
            .and_then(add_one)  # 6
            .and_then(multiply_two)  # 12
            .and_then(as_string)
        )  # "12"

        assert result.is_ok
        assert result.value == "12"

    def test_and_then_stops_at_first_error(self):
        """Test that and_then chain stops at first error."""

        def add_one(x):
            return Result.ok(x + 1)

        def fail_always(x):
            return Result.fail("Intentional failure")

        def should_not_run(x):
            pytest.fail("This should not be called")

        result = Result.ok(5).and_then(add_one).and_then(fail_always).and_then(should_not_run)

        assert result.is_error
        assert result.error.message == "Intentional failure"

    def test_map_exception_handling(self):
        """Test that map catches exceptions and wraps them."""

        def raises_error(x):
            raise ValueError("Map function failed")

        result = Result.ok(42).map(raises_error)

        assert result.is_error
        assert result.error.code == "MAP_FUNCTION_ERROR"
        assert "Map function failed" in result.error.message
        assert result.error.details["original_value"] == "42"
        assert result.error.stack_trace is not None

    def test_map_propagates_error(self):
        """Test that map propagates error without calling function."""
        call_count = 0

        def should_not_be_called(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result = Result.fail("Original error")
        mapped = result.map(should_not_be_called)

        assert mapped.is_error
        assert mapped.error.message == "Original error"
        assert call_count == 0

    def test_map_error_transforms_error(self):
        """Test map_error transforms ErrorContext."""
        result = Result.fail(Errors.database("query", "Query failed"))

        def add_retry_info(error):
            new_details = {**error.details, "retry_count": 3, "max_retries": 5}
            return ErrorContext(
                category=error.category,
                message=f"{error.message} (retry 3/5)",
                code=error.code,
                severity=error.severity,
                details=new_details,
                user_message=error.user_message,
                source_location=error.source_location,
            )

        transformed = result.map_error(add_retry_info)

        assert transformed.is_error
        assert "retry 3/5" in transformed.error.message
        assert transformed.error.details["retry_count"] == 3

    def test_map_error_preserves_original_on_exception(self):
        """Test that map_error preserves original error if transformation fails."""
        result = Result.fail(Errors.system("Original error"))

        def bad_transform(error):
            raise ValueError("Transform failed")

        transformed = result.map_error(bad_transform)

        assert transformed.is_error
        assert transformed.error.message == "Original error"

    def test_map_error_preserves_original_on_wrong_return_type(self):
        """Test that map_error preserves error if function returns wrong type."""
        result = Result.fail(Errors.system("Original error"))

        def returns_string(error):
            return "Not an ErrorContext"

        transformed = result.map_error(returns_string)

        assert transformed.is_error
        assert transformed.error.message == "Original error"

    def test_inspect_runs_side_effect_on_success(self):
        """Test inspect runs side effect on success."""
        side_effects = []

        def log_value(v):
            side_effects.append(v)

        result = Result.ok(42).inspect(log_value)

        assert result.is_ok
        assert result.value == 42
        assert side_effects == [42]

    def test_inspect_skips_side_effect_on_error(self):
        """Test inspect skips side effect on error."""
        side_effects = []

        def log_value(v):
            side_effects.append(v)

        result = Result.fail("Error").inspect(log_value)

        assert result.is_error
        assert side_effects == []

    def test_inspect_continues_on_exception(self):
        """Test inspect continues chain even if side effect raises."""

        def raises_error(v):
            raise ValueError("Side effect failed")

        result = Result.ok(42).inspect(raises_error)

        # Result should still be success despite side effect failure
        assert result.is_ok
        assert result.value == 42

    def test_inspect_error_runs_side_effect_on_error(self):
        """Test inspect_error runs side effect on error."""
        side_effects = []

        def log_error(e):
            side_effects.append(e.code)

        result = Result.fail(Errors.validation("Bad input")).inspect_error(log_error)

        assert result.is_error
        assert "VALIDATION" in side_effects[0]

    def test_inspect_error_skips_side_effect_on_success(self):
        """Test inspect_error skips side effect on success."""
        side_effects = []

        def log_error(e):
            side_effects.append(e)

        result = Result.ok(42).inspect_error(log_error)

        assert result.is_ok
        assert side_effects == []

    def test_chaining_inspect_and_map(self):
        """Test chaining inspect with map operations."""
        operations = []

        result = (
            Result.ok(5)
            .inspect(lambda v: operations.append(f"start:{v}"))
            .map(lambda x: x * 2)
            .inspect(lambda v: operations.append(f"after_double:{v}"))
            .map(lambda x: x + 1)
            .inspect(lambda v: operations.append(f"final:{v}"))
        )

        assert result.is_ok
        assert result.value == 11
        assert operations == ["start:5", "after_double:10", "final:11"]

    def test_log_if_error_with_different_severities(self):
        """Test log_if_error handles different severity levels."""
        # This test just ensures the method doesn't crash
        # Actual logging is tested via mocks in real scenarios

        errors = [
            Errors.validation("Low severity", field="test"),
            Errors.database("query", "Medium/High severity"),
            Errors.system("Critical severity"),
        ]

        for error in errors:
            result = Result.fail(error).log_if_error("Test prefix")
            assert result.is_error


class TestErrorFactories:
    """Test error factory methods."""

    def test_validation_error_with_field(self):
        """Test validation error with field specified."""
        error = Errors.validation("Invalid email", field="email", value="bad@")

        assert error.category == ErrorCategory.VALIDATION
        assert error.code == "VALIDATION_FIELD_EMAIL"
        assert error.details["field"] == "email"
        assert error.details["value"] == "bad@"
        assert error.severity == ErrorSeverity.LOW

    def test_validation_error_without_field(self):
        """Test validation error without field."""
        error = Errors.validation("General validation error")

        assert error.code == "VALIDATION_GENERIC"
        assert "field" not in error.details

    def test_validation_error_custom_user_message(self):
        """Test validation error with custom user message."""
        error = Errors.validation(
            "Technical validation message", user_message="Please check your input"
        )
        assert error.user_message == "Please check your input"
        assert error.message == "Technical validation message"

    def test_not_found_with_identifier(self):
        """Test not found error with identifier."""
        error = Errors.not_found("Task", identifier="task-123")

        assert error.category == ErrorCategory.NOT_FOUND
        assert error.code == "NOT_FOUND_TASK"
        assert error.details["identifier"] == "task-123"
        assert "task-123" in error.message

    def test_not_found_without_identifier(self):
        """Test not found error without identifier."""
        error = Errors.not_found("User")

        assert error.code == "NOT_FOUND_USER"
        assert "identifier" not in error.details or error.details["identifier"] is None

    def test_database_error_with_query(self):
        """Test database error with query included."""
        long_query = "MATCH (n:Node) WHERE n.property = $value RETURN n" * 10
        error = Errors.database(
            operation="query", message="Query execution failed", query=long_query
        )

        assert error.category == ErrorCategory.DATABASE
        assert error.code == "DB_QUERY"
        assert error.severity == ErrorSeverity.HIGH
        # Query should be truncated to 200 chars
        assert len(error.details["query"]) <= 200

    def test_database_error_with_extra_details(self):
        """Test database error with extra context."""
        error = Errors.database(
            operation="connection",
            message="Connection timeout",
            host="neo4j://localhost:7687",
            timeout=30,
            retry_count=3,
        )

        assert error.details["host"] == "neo4j://localhost:7687"
        assert error.details["timeout"] == 30
        assert error.details["retry_count"] == 3

    def test_integration_error_with_status_code(self):
        """Test integration error with HTTP status code."""
        error = Errors.integration(
            service="openai", message="API rate limit exceeded", status_code=429
        )

        assert error.category == ErrorCategory.INTEGRATION
        assert error.code == "INTEGRATION_OPENAI"
        assert error.details["status_code"] == 429
        assert error.severity == ErrorSeverity.MEDIUM

    def test_integration_error_with_extra_details(self):
        """Test integration error with additional context."""
        error = Errors.integration(
            service="stripe",
            message="Payment processing failed",
            status_code=402,
            transaction_id="txn_123",
            amount=99.99,
        )

        assert error.details["transaction_id"] == "txn_123"
        assert error.details["amount"] == 99.99

    def test_business_error_with_rule(self):
        """Test business logic error."""
        error = Errors.business(
            rule="age_requirement",
            message="User must be 18 or older",
            current_age=16,
            required_age=18,
        )

        assert error.category == ErrorCategory.BUSINESS
        assert error.code == "BUSINESS_AGE_REQUIREMENT"
        assert error.details["rule"] == "age_requirement"
        assert error.details["current_age"] == 16
        assert error.user_message == "User must be 18 or older"

    def test_system_error_with_exception(self):
        """Test system error with exception context."""
        try:
            raise ValueError("Something broke")
        except ValueError as e:
            error = Errors.system("Unexpected system failure", exception=e)

        assert error.category == ErrorCategory.SYSTEM
        assert error.code == "SYSTEM_ERROR"
        assert error.severity == ErrorSeverity.CRITICAL
        assert error.details["exception_type"] == "ValueError"
        assert error.details["exception_message"] == "Something broke"
        assert error.stack_trace is not None

    def test_system_error_without_exception(self):
        """Test system error without exception."""
        error = Errors.system("Generic system error", component="auth_service")

        assert error.code == "SYSTEM_ERROR"
        assert error.details["component"] == "auth_service"
        assert "exception_type" not in error.details


class TestErrorContext:
    """Test ErrorContext functionality."""

    def test_error_context_string_representation(self):
        """Test ErrorContext __str__ method."""
        error = ErrorContext(
            category=ErrorCategory.DATABASE,
            code="DB_QUERY_FAILED",
            message="Query execution timeout",
            severity=ErrorSeverity.HIGH,
            source_location="tasks_service.py:get_tasks:42",
        )

        error_str = str(error)
        assert "[high]" in error_str
        assert "database:DB_QUERY_FAILED" in error_str
        assert "Query execution timeout" in error_str
        assert "tasks_service.py:get_tasks:42" in error_str

    def test_error_context_string_without_location(self):
        """Test ErrorContext __str__ without source location."""
        error = ErrorContext(
            category=ErrorCategory.VALIDATION,
            code="VALIDATION_FAILED",
            message="Invalid input",
            severity=ErrorSeverity.LOW,
        )

        error_str = str(error)
        assert "validation:VALIDATION_FAILED" in error_str
        assert "Invalid input" in error_str

    def test_error_context_to_dict(self):
        """Test ErrorContext serialization to dict."""
        error = ErrorContext(
            category=ErrorCategory.INTEGRATION,
            code="API_TIMEOUT",
            message="External API timeout",
            severity=ErrorSeverity.MEDIUM,
            details={"service": "openai", "timeout": 30},
            source_location="test.py:test_func:10",
            user_message="Service temporarily unavailable",
            stack_trace="Traceback...\n",
        )

        error_dict = error.to_dict()

        assert error_dict["category"] == "integration"
        assert error_dict["code"] == "API_TIMEOUT"
        assert error_dict["message"] == "External API timeout"
        assert error_dict["severity"] == "medium"
        assert error_dict["details"]["service"] == "openai"
        assert error_dict["source_location"] == "test.py:test_func:10"
        assert error_dict["user_message"] == "Service temporarily unavailable"
        assert error_dict["stack_trace"] == "Traceback...\n"
        assert "timestamp" in error_dict

    def test_error_context_timestamp(self):
        """Test that ErrorContext captures timestamp."""
        error = ErrorContext(category=ErrorCategory.SYSTEM, code="TEST", message="Test error")

        assert isinstance(error.timestamp, datetime)
        assert error.timestamp.tzinfo == UTC

    def test_capture_current_location(self):
        """Test source location capture."""
        location = ErrorContext.capture_current_location()

        assert location is not None
        # Note: When called from pytest, location may show pytest internals
        # Just verify it captured something (file:function:line format)
        assert ":" in location
        assert location != "unknown"

    def test_error_severity_levels(self):
        """Test all error severity levels."""
        severities = [
            ErrorSeverity.LOW,
            ErrorSeverity.MEDIUM,
            ErrorSeverity.HIGH,
            ErrorSeverity.CRITICAL,
        ]

        for severity in severities:
            error = ErrorContext(
                category=ErrorCategory.SYSTEM, code="TEST", message="Test", severity=severity
            )
            assert error.severity == severity

    def test_error_categories(self):
        """Test all error categories."""
        categories = [
            ErrorCategory.VALIDATION,
            ErrorCategory.DATABASE,
            ErrorCategory.INTEGRATION,
            ErrorCategory.BUSINESS,
            ErrorCategory.NOT_FOUND,
            ErrorCategory.SYSTEM,
        ]

        for category in categories:
            error = ErrorContext(category=category, code="TEST", message="Test")
            assert error.category == category


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
