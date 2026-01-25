"""
Comprehensive tests for Result chaining functionality.

Tests all new chaining methods: and_then, map_error, inspect, inspect_error
"""

import pytest

from core.utils.result_simplified import ErrorCategory, ErrorContext, Errors, Result


class TestAndThen:
    """Test and_then for chaining Result-returning functions."""

    def test_and_then_success_chain(self):
        """Test successful chaining with and_then"""
        result = (
            Result.ok(5).and_then(lambda x: Result.ok(x * 2)).and_then(lambda x: Result.ok(x + 3))
        )

        assert result.is_ok
        assert result.value == 13

    def test_and_then_early_failure(self):
        """Test error propagation stops chain"""
        error = Errors.validation("Invalid")

        result = (
            Result.ok(5).and_then(lambda _: Result.fail(error)).and_then(lambda x: Result.ok(x + 3))
        )  # Should not execute

        assert result.is_error
        assert result.error.category == ErrorCategory.VALIDATION
        assert result.error.message == "Invalid"

    def test_and_then_type_safety(self):
        """Test that and_then validates Result return"""
        result = Result.ok(5).and_then(lambda x: x * 2)  # Returns int, not Result

        assert result.is_error
        assert "must return Result" in result.error.message
        assert result.error.code == "AND_THEN_FUNCTION_ERROR"

    def test_and_then_propagates_initial_error(self):
        """Test that and_then propagates existing error"""
        error = Errors.not_found("user", "user-123")

        result = Result.fail(error).and_then(lambda x: Result.ok(x * 2))  # Should not execute

        assert result.is_error
        assert result.error.message == "user not found: user-123"

    def test_and_then_exception_handling(self):
        """Test that exceptions in and_then are captured"""

        def failing_func(x):
            raise ValueError("Unexpected error")

        result = Result.ok(5).and_then(failing_func)

        assert result.is_error
        assert result.error.code == "AND_THEN_FUNCTION_ERROR"
        assert "ValueError" in result.error.stack_trace

    def test_and_then_with_none_value(self):
        """Test and_then works with None as valid value"""
        result = Result.ok(None).and_then(lambda _: Result.ok("handled none"))

        assert result.is_ok
        assert result.value == "handled none"


class TestMapVsAndThen:
    """Demonstrate and test difference between map and and_then."""

    def test_map_transforms_value(self):
        """map: transforms value (func returns T)"""
        result = Result.ok(5).map(lambda x: x * 2)

        assert result.is_ok
        assert result.value == 10

    def test_and_then_chains_results(self):
        """and_then: chains Result-returning functions"""

        def double_if_positive(x):
            if x > 0:
                return Result.ok(x * 2)
            return Result.fail(Errors.validation("Must be positive"))

        # Positive case
        result = Result.ok(5).and_then(double_if_positive)
        assert result.is_ok
        assert result.value == 10

        # Negative case
        error_result = Result.ok(-5).and_then(double_if_positive)
        assert error_result.is_error
        assert "Must be positive" in error_result.error.message

    def test_map_with_result_prevents_double_wrap(self):
        """Demonstrate: Result prevents double-wrapping automatically"""

        def returns_result(x):
            return Result.ok(x * 2)

        # Result.ok() detects double-wrap and returns original
        result = Result.ok(5).map(returns_result)

        assert result.is_ok
        # Double-wrap prevention unwraps automatically
        assert result.value == 10
        assert not isinstance(result.value, Result)

    def test_combining_map_and_and_then(self):
        """Show how to combine map and and_then"""

        def validate(x: int) -> Result[int]:
            if x > 0:
                return Result.ok(x)
            return Result.fail(Errors.validation("Must be positive"))

        result = (
            Result.ok("5")
            .map(int)  # Transform string to int
            .and_then(validate)  # Validate (returns Result)
            .map(lambda x: x * 2)
        )  # Transform value

        assert result.is_ok
        assert result.value == 10


class TestMapError:
    """Test map_error for error context transformation."""

    def test_map_error_adds_context(self):
        """Test map_error adds operation context"""
        error = Errors.validation("Invalid email")

        result = Result.fail(error).map_error(
            lambda e: ErrorContext(
                category=e.category,
                code=e.code,
                message=e.message,
                severity=e.severity,
                details={**e.details, "operation": "user_creation", "step": 1},
                source_location=e.source_location,
                user_message=e.user_message,
            )
        )

        assert result.is_error
        assert result.error.details["operation"] == "user_creation"
        assert result.error.details["step"] == 1

    def test_map_error_preserves_original_on_exception(self):
        """Test that map_error preserves original error if transformation fails"""
        error = Errors.validation("Test error")

        def failing_transform(e):
            raise ValueError("Transform failed")

        result = Result.fail(error).map_error(failing_transform)

        # Original error should be preserved
        assert result.is_error
        assert result.error.message == "Test error"

    def test_map_error_on_success_is_noop(self):
        """Test that map_error doesn't affect success results"""
        result = Result.ok(5).map_error(lambda _: Errors.system("Should not execute"))

        assert result.is_ok
        assert result.value == 5

    def test_map_error_type_validation(self):
        """Test that map_error validates ErrorContext return"""
        error = Errors.validation("Test")

        result = Result.fail(error).map_error(lambda _: "not an ErrorContext")

        # Original error preserved
        assert result.is_error
        assert result.error.message == "Test"


class TestInspect:
    """Test inspect for side effects on values."""

    def test_inspect_logs_without_breaking_chain(self):
        """Test inspect for logging without breaking chain"""
        log_output = []

        result = (
            Result.ok(5)
            .inspect(lambda x: log_output.append(f"Got {x}"))
            .map(lambda x: x * 2)
            .inspect(lambda x: log_output.append(f"Transformed to {x}"))
        )

        assert result.is_ok
        assert result.value == 10
        assert log_output == ["Got 5", "Transformed to 10"]

    def test_inspect_on_error_is_noop(self):
        """Test that inspect doesn't execute on error"""
        log_output = []
        error = Errors.validation("Test")

        result = Result.fail(error).inspect(lambda x: log_output.append(f"Should not execute: {x}"))

        assert result.is_error
        assert len(log_output) == 0

    def test_inspect_exception_handling(self):
        """Test that exceptions in inspect don't break chain"""

        def failing_inspect(x):
            raise ValueError("Inspect failed")

        # Should not fail, just log warning
        result = Result.ok(5).inspect(failing_inspect).map(lambda x: x * 2)

        assert result.is_ok
        assert result.value == 10

    def test_inspect_with_multiple_side_effects(self):
        """Test multiple inspects for different side effects"""
        logs = []
        metrics = {"processed": 0}

        result = (
            Result.ok(5)
            .inspect(lambda x: logs.append(f"Processing {x}"))
            .inspect(lambda x: metrics.update({"processed": x}))
            .map(lambda x: x * 2)
        )

        assert result.is_ok
        assert logs == ["Processing 5"]
        assert metrics["processed"] == 5


class TestInspectError:
    """Test inspect_error for side effects on errors."""

    def test_inspect_error_logs_errors(self):
        """Test inspect_error for error logging"""
        log_output = []

        error = Errors.validation("Test error")
        result = (
            Result.fail(error)
            .inspect_error(lambda e: log_output.append(f"Error: {e.message}"))
            .map(lambda x: x * 2)
        )  # Should not execute

        assert result.is_error
        assert log_output == ["Error: Test error"]

    def test_inspect_error_on_success_is_noop(self):
        """Test that inspect_error doesn't execute on success"""
        log_output = []

        result = Result.ok(5).inspect_error(lambda _: log_output.append("Should not execute"))

        assert result.is_ok
        assert len(log_output) == 0

    def test_inspect_error_exception_handling(self):
        """Test that exceptions in inspect_error don't break chain"""

        def failing_inspect(e):
            raise ValueError("Inspect failed")

        error = Errors.validation("Test")
        result = Result.fail(error).inspect_error(failing_inspect)

        # Error should be preserved
        assert result.is_error
        assert result.error.message == "Test"

    def test_inspect_error_with_multiple_handlers(self):
        """Test multiple inspect_error calls for different handlers"""
        logs = []
        metrics = {"errors": 0}

        error = Errors.validation("Test")
        result = (
            Result.fail(error)
            .inspect_error(lambda e: logs.append(f"Error: {e.message}"))
            .inspect_error(lambda _: metrics.update({"errors": metrics["errors"] + 1}))
        )

        assert result.is_error
        assert logs == ["Error: Test"]
        assert metrics["errors"] == 1


class TestComplexChains:
    """Test complex chaining scenarios."""

    def test_full_chain_success(self):
        """Test a complete chain with map, and_then, inspect"""
        logs = []

        def validate(x: int) -> Result[int]:
            if x > 0:
                return Result.ok(x)
            return Result.fail(Errors.validation("Must be positive"))

        result = (
            Result.ok("5")
            .inspect(lambda x: logs.append(f"Input: {x}"))
            .map(int)
            .inspect(lambda x: logs.append(f"Parsed: {x}"))
            .and_then(validate)
            .inspect(lambda x: logs.append(f"Validated: {x}"))
            .map(lambda x: x * 2)
            .inspect(lambda x: logs.append(f"Final: {x}"))
        )

        assert result.is_ok
        assert result.value == 10
        assert logs == ["Input: 5", "Parsed: 5", "Validated: 5", "Final: 10"]

    def test_full_chain_with_error(self):
        """Test chain stops at first error"""
        logs = []

        def validate(x: int) -> Result[int]:
            if x > 0:
                return Result.ok(x)
            return Result.fail(Errors.validation("Must be positive"))

        result = (
            Result.ok("-5")
            .inspect(lambda x: logs.append(f"Input: {x}"))
            .map(int)
            .inspect(lambda x: logs.append(f"Parsed: {x}"))
            .and_then(validate)
            .inspect(lambda _: logs.append("Should not execute"))
            .map(lambda x: x * 2)
        )

        assert result.is_error
        assert "Must be positive" in result.error.message
        # Chain stopped after validation failure
        assert logs == ["Input: -5", "Parsed: -5"]

    def test_chain_with_error_handling(self):
        """Test chain with error context enrichment"""

        def validate(x: int) -> Result[int]:
            if x > 0:
                return Result.ok(x)
            return Result.fail(Errors.validation("Must be positive", value=x))

        result = (
            Result.ok("-5")
            .map(int)
            .and_then(validate)
            .map_error(
                lambda e: ErrorContext(
                    category=e.category,
                    code=e.code,
                    message=e.message,
                    severity=e.severity,
                    details={**e.details, "operation": "process_input"},
                    source_location=e.source_location,
                    user_message=e.user_message,
                )
            )
            .inspect_error(lambda _: None)
        )  # Log error

        assert result.is_error
        assert result.error.details["operation"] == "process_input"
        assert result.error.details["value"] == "-5"

    def test_chain_with_or_else_fallback(self):
        """Test using or_else to provide fallback"""

        def risky_operation(x: int) -> Result[int]:
            if x > 10:
                return Result.ok(x * 2)
            return Result.fail(Errors.validation("Too small"))

        # Success case
        value1 = Result.ok(15).and_then(risky_operation).or_else(100)
        assert value1 == 30

        # Fallback case
        value2 = Result.ok(5).and_then(risky_operation).or_else(100)
        assert value2 == 100


class TestRealWorldScenarios:
    """Test real-world service patterns."""

    def test_service_layer_pattern(self):
        """Simulate typical service layer chaining"""

        # Simulated service methods
        def get_user(uid: str) -> Result[dict]:
            if uid == "valid":
                return Result.ok({"uid": uid, "name": "Test"})
            return Result.fail(Errors.not_found("user", uid))

        def get_preferences(user: dict) -> Result[dict]:
            return Result.ok({"theme": "dark", "user_uid": user["uid"]})

        def validate_preferences(prefs: dict) -> Result[dict]:
            if prefs.get("theme") in ["light", "dark"]:
                return Result.ok(prefs)
            return Result.fail(Errors.validation("Invalid theme"))

        # Success chain
        result = get_user("valid").and_then(get_preferences).and_then(validate_preferences)

        assert result.is_ok
        assert result.value["theme"] == "dark"

        # Not found error
        result = get_user("invalid")
        assert result.is_error
        assert result.error.category == ErrorCategory.NOT_FOUND

    def test_service_with_logging(self):
        """Simulate service with logging at each step"""
        logs = []

        def get_data(uid: str) -> Result[dict]:
            return Result.ok({"uid": uid, "value": 42})

        def transform_data(data: dict) -> dict:
            return {**data, "doubled": data["value"] * 2}

        result = (
            get_data("test-123")
            .inspect(lambda d: logs.append(f"Retrieved: {d['uid']}"))
            .map(transform_data)
            .inspect(lambda d: logs.append(f"Transformed: {d['doubled']}"))
            .inspect_error(lambda e: logs.append(f"Error: {e.message}"))
        )

        assert result.is_ok
        assert result.value["doubled"] == 84
        assert logs == ["Retrieved: test-123", "Transformed: 84"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
