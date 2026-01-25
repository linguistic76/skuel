#!/usr/bin/env python3
"""Test the simplified Result implementation."""

from core.utils.result_simplified import ErrorCategory, Errors, ErrorSeverity, Result


def test_basic_success():
    """Test basic success result."""
    result = Result.ok(42)
    assert result.is_ok
    assert not result.is_error
    assert result.value == 42
    assert result.error is None
    print("✅ Basic success test passed")


def test_basic_failure():
    """Test basic failure result."""
    result = Result.fail("Something went wrong")
    assert not result.is_ok
    assert result.is_error
    assert result.error.message == "Something went wrong"
    assert result.error.category == ErrorCategory.SYSTEM
    print("✅ Basic failure test passed")


def test_validation_error():
    """Test validation error with rich context."""
    result = Result.fail(
        Errors.validation(
            "Invalid email format",
            field="email",
            value="not-an-email",
            user_message="Please enter a valid email address",
        )
    )

    assert result.error.category == ErrorCategory.VALIDATION
    assert result.error.code == "VALIDATION_FIELD_EMAIL"
    assert result.error.details["field"] == "email"
    assert result.error.user_message == "Please enter a valid email address"
    assert result.error.severity == ErrorSeverity.LOW
    print("✅ Validation error test passed")


def test_database_error():
    """Test database error with context."""
    result = Result.fail(
        Errors.database(
            operation="connection",
            message="Connection timeout after 30s",
            query="MATCH (n:User) RETURN n",
            host="neo4j://localhost:7687",
            timeout=30,
        )
    )

    assert result.error.category == ErrorCategory.DATABASE
    assert result.error.code == "DB_CONNECTION"
    assert result.error.details["timeout"] == 30
    assert result.error.severity == ErrorSeverity.HIGH
    print("✅ Database error test passed")


def test_not_found_error():
    """Test not found error."""
    result = Result.fail(Errors.not_found("User", "user-123"))

    assert result.error.category == ErrorCategory.NOT_FOUND
    assert result.error.code == "NOT_FOUND_USER"
    assert result.error.details["identifier"] == "user-123"
    print("✅ Not found error test passed")


def test_integration_error():
    """Test integration/external service error."""
    result = Result.fail(
        Errors.integration(
            service="openai", message="Rate limit exceeded", status_code=429, retry_after=60
        )
    )

    assert result.error.category == ErrorCategory.INTEGRATION
    assert result.error.code == "INTEGRATION_OPENAI"
    assert result.error.details["status_code"] == 429
    assert result.error.details["retry_after"] == 60
    print("✅ Integration error test passed")


def test_business_error():
    """Test business logic error."""
    result = Result.fail(
        Errors.business(
            rule="credit_limit", message="Credit limit exceeded", current_balance=1000, limit=500
        )
    )

    assert result.error.category == ErrorCategory.BUSINESS
    assert result.error.code == "BUSINESS_CREDIT_LIMIT"
    assert result.error.details["current_balance"] == 1000
    print("✅ Business error test passed")


def test_map_success():
    """Test map operation on success."""

    def double_value(x):
        return x * 2

    result = Result.ok(10)
    mapped = result.map(double_value)

    assert mapped.is_ok
    assert mapped.value == 20
    print("✅ Map success test passed")


def test_map_failure():
    """Test map operation on failure."""

    def double_value(x):
        return x * 2

    result = Result.fail("Original error")
    mapped = result.map(double_value)

    assert mapped.is_error
    assert mapped.error.message == "Original error"
    print("✅ Map failure test passed")


def test_double_wrap_prevention():
    """Test that double-wrapping is prevented."""
    result1 = Result.ok(42)
    result2 = Result.ok(result1)  # Should return result1, not wrap it

    assert result2 is result1
    assert result2.value == 42
    print("✅ Double-wrap prevention test passed")


def test_or_else():
    """Test or_else method."""
    success = Result.ok(42)
    failure = Result.fail("Error")

    assert success.or_else(0) == 42
    assert failure.or_else(0) == 0
    print("✅ Or_else test passed")


def test_error_string_representation():
    """Test error string representation."""
    error = Errors.database(operation="query", message="Query failed")

    error_str = str(error)
    assert "[high]" in error_str.lower()
    assert "database:DB_QUERY" in error_str
    assert "Query failed" in error_str
    print("✅ Error string representation test passed")


def test_error_to_dict():
    """Test error serialization to dict."""
    error = Errors.validation("Invalid input", field="username")

    error_dict = error.to_dict()
    assert error_dict["category"] == "validation"
    assert error_dict["code"] == "VALIDATION_FIELD_USERNAME"
    assert error_dict["details"]["field"] == "username"
    assert "timestamp" in error_dict
    print("✅ Error to_dict test passed")


def test_source_location_capture():
    """Test that source location is captured."""
    error = Errors.system("Test error")

    assert error.source_location is not None
    assert "test_result_simplified.py" in error.source_location
    assert "test_source_location_capture" in error.source_location
    print("✅ Source location capture test passed")


def test_pattern_matching():
    """Test error handling with pattern matching."""
    errors = [
        Result.fail(Errors.validation("Bad input")),
        Result.fail(Errors.not_found("Resource", "123")),
        Result.fail(Errors.database("query", "Failed")),
    ]

    expected_codes = [400, 404, 503]

    for i, result in enumerate(errors):
        if result.is_error:
            status_code = None
            match result.error.category:
                case ErrorCategory.VALIDATION:
                    status_code = 400
                case ErrorCategory.NOT_FOUND:
                    status_code = 404
                case ErrorCategory.DATABASE:
                    status_code = 503
                case _:
                    status_code = 500

            assert status_code == expected_codes[i]

    print("✅ Pattern matching test passed")


def main():
    """Run all tests."""
    print("Testing Simplified Result Implementation")
    print("=" * 40)

    tests = [
        test_basic_success,
        test_basic_failure,
        test_validation_error,
        test_database_error,
        test_not_found_error,
        test_integration_error,
        test_business_error,
        test_map_success,
        test_map_failure,
        test_double_wrap_prevention,
        test_or_else,
        test_error_string_representation,
        test_error_to_dict,
        test_source_location_capture,
        test_pattern_matching,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"❌ {test.__name__} failed: {e}")
            import traceback

            traceback.print_exc()

    print("\n" + "=" * 40)
    print("All tests passed! 🎉")


if __name__ == "__main__":
    main()
