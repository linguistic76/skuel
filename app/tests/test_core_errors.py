#!/usr/bin/env python3
"""
Comprehensive Tests for Core Error Classes
===========================================

Tests all exception classes in core/errors.py.
"""

import pytest

from core.errors import (
    ApplicationError,
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    ConflictError,
    DatabaseError,
    NotFoundError,
    ServiceError,
    ValidationError,
)


class TestApplicationError:
    """Test base ApplicationError class."""

    def test_basic_error(self):
        """Test creating basic ApplicationError."""
        error = ApplicationError("Something went wrong")

        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.code == "ApplicationError"  # Default to class name
        assert error.details is None

    def test_error_with_code(self):
        """Test ApplicationError with custom code."""
        error = ApplicationError("Error occurred", code="CUSTOM_ERROR")

        assert error.message == "Error occurred"
        assert error.code == "CUSTOM_ERROR"

    def test_error_with_details(self):
        """Test ApplicationError with details."""
        details = {"user_id": "123", "action": "login"}
        error = ApplicationError("Login failed", details=details)

        assert error.message == "Login failed"
        assert error.details == details
        assert error.details["user_id"] == "123"

    def test_error_with_all_params(self):
        """Test ApplicationError with all parameters."""
        details = {"context": "testing"}
        error = ApplicationError("Full error", code="TEST_ERROR", details=details)

        assert error.message == "Full error"
        assert error.code == "TEST_ERROR"
        assert error.details == details

    def test_error_is_exception(self):
        """Test that ApplicationError is an Exception."""
        error = ApplicationError("Test")
        assert isinstance(error, Exception)

    def test_error_can_be_raised(self):
        """Test that ApplicationError can be raised and caught."""
        with pytest.raises(ApplicationError) as exc_info:
            raise ApplicationError("Test error", code="TEST")

        assert exc_info.value.message == "Test error"
        assert exc_info.value.code == "TEST"


class TestValidationError:
    """Test ValidationError class."""

    def test_basic_validation_error(self):
        """Test creating basic ValidationError."""
        error = ValidationError("Invalid input")

        assert error.message == "Invalid input"
        assert error.code == "ValidationError"
        assert error.field is None

    def test_validation_error_with_field(self):
        """Test ValidationError with field specified."""
        error = ValidationError("Email format invalid", field="email")

        assert error.message == "Email format invalid"
        assert error.field == "email"

    def test_validation_error_with_code_and_details(self):
        """Test ValidationError with code and details."""
        error = ValidationError(
            "Value out of range",
            field="age",
            code="RANGE_ERROR",
            details={"min": 0, "max": 120, "provided": -5},
        )

        assert error.message == "Value out of range"
        assert error.field == "age"
        assert error.code == "RANGE_ERROR"
        assert error.details["provided"] == -5

    def test_validation_error_inheritance(self):
        """Test that ValidationError inherits from ApplicationError."""
        error = ValidationError("Test")
        assert isinstance(error, ApplicationError)
        assert isinstance(error, Exception)

    def test_validation_error_can_be_raised(self):
        """Test ValidationError can be raised and caught."""
        with pytest.raises(ValidationError) as exc_info:
            raise ValidationError("Bad data", field="username")

        assert exc_info.value.field == "username"


class TestNotFoundError:
    """Test NotFoundError class."""

    def test_basic_not_found_error(self):
        """Test creating basic NotFoundError."""
        error = NotFoundError("Resource not found")

        assert error.message == "Resource not found"
        assert error.resource_type is None
        assert error.resource_id is None

    def test_not_found_error_with_resource_type(self):
        """Test NotFoundError with resource type."""
        error = NotFoundError("User not found", resource_type="User")

        assert error.message == "User not found"
        assert error.resource_type == "User"

    def test_not_found_error_with_resource_id(self):
        """Test NotFoundError with resource ID."""
        error = NotFoundError("Task not found", resource_type="Task", resource_id="task-123")

        assert error.message == "Task not found"
        assert error.resource_type == "Task"
        assert error.resource_id == "task-123"

    def test_not_found_error_with_all_params(self):
        """Test NotFoundError with all parameters."""
        error = NotFoundError(
            "Goal not found",
            resource_type="Goal",
            resource_id="goal-456",
            code="GOAL_NOT_FOUND",
            details={"search_criteria": {"status": "active"}},
        )

        assert error.message == "Goal not found"
        assert error.resource_type == "Goal"
        assert error.resource_id == "goal-456"
        assert error.code == "GOAL_NOT_FOUND"
        assert error.details["search_criteria"]["status"] == "active"

    def test_not_found_error_inheritance(self):
        """Test that NotFoundError inherits from ApplicationError."""
        error = NotFoundError("Test")
        assert isinstance(error, ApplicationError)

    def test_not_found_error_can_be_raised(self):
        """Test NotFoundError can be raised and caught."""
        with pytest.raises(NotFoundError) as exc_info:
            raise NotFoundError("Event not found", resource_type="Event", resource_id="evt-789")

        assert exc_info.value.resource_type == "Event"
        assert exc_info.value.resource_id == "evt-789"


class TestDatabaseError:
    """Test DatabaseError class and factory methods."""

    def test_basic_database_error(self):
        """Test creating basic DatabaseError."""
        error = DatabaseError("Database operation failed")

        assert error.message == "Database operation failed"
        assert error.operation is None

    def test_database_error_with_operation(self):
        """Test DatabaseError with operation specified."""
        error = DatabaseError("Connection failed", operation="connect")

        assert error.message == "Connection failed"
        assert error.operation == "connect"

    def test_database_error_with_all_params(self):
        """Test DatabaseError with all parameters."""
        error = DatabaseError(
            "Query timeout",
            operation="query",
            code="DB_TIMEOUT",
            details={"timeout_seconds": 30, "query": "MATCH (n) RETURN n"},
        )

        assert error.message == "Query timeout"
        assert error.operation == "query"
        assert error.code == "DB_TIMEOUT"
        assert error.details["timeout_seconds"] == 30

    def test_query_failed_factory(self):
        """Test DatabaseError.query_failed factory method."""
        error = DatabaseError.query_failed("Syntax error in Cypher query")

        assert "Database query failed: Syntax error" in error.message
        assert error.operation == "query"
        assert isinstance(error, DatabaseError)

    def test_connection_failed_factory(self):
        """Test DatabaseError.connection_failed factory method."""
        error = DatabaseError.connection_failed("Could not connect to Neo4j")

        assert "Database connection failed: Could not connect" in error.message
        assert error.operation == "connect"

    def test_transaction_failed_factory(self):
        """Test DatabaseError.transaction_failed factory method."""
        error = DatabaseError.transaction_failed("Deadlock detected")

        assert "Database transaction failed: Deadlock" in error.message
        assert error.operation == "transaction"

    def test_operation_failed_factory(self):
        """Test DatabaseError.operation_failed factory method."""
        error = DatabaseError.operation_failed("Index creation failed")

        assert "Database operation failed: Index creation" in error.message
        assert error.operation == "operation"

    def test_database_error_inheritance(self):
        """Test that DatabaseError inherits from ApplicationError."""
        error = DatabaseError("Test")
        assert isinstance(error, ApplicationError)

    def test_database_error_can_be_raised(self):
        """Test DatabaseError can be raised and caught."""
        with pytest.raises(DatabaseError) as exc_info:
            raise DatabaseError.query_failed("SELECT failed")

        assert exc_info.value.operation == "query"


class TestAuthenticationError:
    """Test AuthenticationError class."""

    def test_basic_authentication_error(self):
        """Test creating basic AuthenticationError."""
        error = AuthenticationError("Invalid credentials")

        assert error.message == "Invalid credentials"
        assert error.code == "AuthenticationError"

    def test_authentication_error_with_details(self):
        """Test AuthenticationError with details."""
        error = AuthenticationError(
            "Token expired", code="TOKEN_EXPIRED", details={"token_age": 3600, "max_age": 1800}
        )

        assert error.message == "Token expired"
        assert error.code == "TOKEN_EXPIRED"
        assert error.details["token_age"] == 3600

    def test_authentication_error_inheritance(self):
        """Test that AuthenticationError inherits from ApplicationError."""
        error = AuthenticationError("Test")
        assert isinstance(error, ApplicationError)

    def test_authentication_error_can_be_raised(self):
        """Test AuthenticationError can be raised and caught."""
        with pytest.raises(AuthenticationError) as exc_info:
            raise AuthenticationError("Login failed")

        assert exc_info.value.message == "Login failed"


class TestAuthorizationError:
    """Test AuthorizationError class."""

    def test_basic_authorization_error(self):
        """Test creating basic AuthorizationError."""
        error = AuthorizationError("Access denied")

        assert error.message == "Access denied"
        assert error.code == "AuthorizationError"

    def test_authorization_error_with_details(self):
        """Test AuthorizationError with details."""
        error = AuthorizationError(
            "Insufficient permissions",
            code="PERMISSION_DENIED",
            details={
                "user_role": "viewer",
                "required_role": "admin",
                "resource": "system_settings",
            },
        )

        assert error.message == "Insufficient permissions"
        assert error.code == "PERMISSION_DENIED"
        assert error.details["required_role"] == "admin"

    def test_authorization_error_inheritance(self):
        """Test that AuthorizationError inherits from ApplicationError."""
        error = AuthorizationError("Test")
        assert isinstance(error, ApplicationError)

    def test_authorization_error_can_be_raised(self):
        """Test AuthorizationError can be raised and caught."""
        with pytest.raises(AuthorizationError) as exc_info:
            raise AuthorizationError("Forbidden")

        assert exc_info.value.message == "Forbidden"


class TestConflictError:
    """Test ConflictError class."""

    def test_basic_conflict_error(self):
        """Test creating basic ConflictError."""
        error = ConflictError("Resource already exists")

        assert error.message == "Resource already exists"
        assert error.code == "ConflictError"

    def test_conflict_error_with_details(self):
        """Test ConflictError with details."""
        error = ConflictError(
            "Duplicate email address",
            code="DUPLICATE_EMAIL",
            details={"field": "email", "value": "user@example.com", "existing_id": "user-123"},
        )

        assert error.message == "Duplicate email address"
        assert error.code == "DUPLICATE_EMAIL"
        assert error.details["field"] == "email"

    def test_conflict_error_inheritance(self):
        """Test that ConflictError inherits from ApplicationError."""
        error = ConflictError("Test")
        assert isinstance(error, ApplicationError)

    def test_conflict_error_can_be_raised(self):
        """Test ConflictError can be raised and caught."""
        with pytest.raises(ConflictError) as exc_info:
            raise ConflictError("Username taken")

        assert exc_info.value.message == "Username taken"


class TestServiceError:
    """Test ServiceError class."""

    def test_basic_service_error(self):
        """Test creating basic ServiceError."""
        error = ServiceError("Service operation failed")

        assert error.message == "Service operation failed"
        assert error.service_name is None

    def test_service_error_with_service_name(self):
        """Test ServiceError with service name."""
        error = ServiceError("Analysis failed", service_name="TaskAnalyticsService")

        assert error.message == "Analysis failed"
        assert error.service_name == "TaskAnalyticsService"

    def test_service_error_with_all_params(self):
        """Test ServiceError with all parameters."""
        error = ServiceError(
            "Embedding generation failed",
            service_name="OpenAIEmbeddingsService",
            code="EMBEDDING_ERROR",
            details={"model": "text-embedding-3-small", "text_length": 5000, "error": "rate_limit"},
        )

        assert error.message == "Embedding generation failed"
        assert error.service_name == "OpenAIEmbeddingsService"
        assert error.code == "EMBEDDING_ERROR"
        assert error.details["model"] == "text-embedding-3-small"

    def test_service_error_inheritance(self):
        """Test that ServiceError inherits from ApplicationError."""
        error = ServiceError("Test")
        assert isinstance(error, ApplicationError)

    def test_service_error_can_be_raised(self):
        """Test ServiceError can be raised and caught."""
        with pytest.raises(ServiceError) as exc_info:
            raise ServiceError("Sync failed", service_name="KnowledgeSyncService")

        assert exc_info.value.service_name == "KnowledgeSyncService"


class TestConfigurationError:
    """Test ConfigurationError class."""

    def test_basic_configuration_error(self):
        """Test creating basic ConfigurationError."""
        error = ConfigurationError("Missing configuration")

        assert error.message == "Missing configuration"
        assert error.code == "ConfigurationError"

    def test_configuration_error_with_details(self):
        """Test ConfigurationError with details."""
        error = ConfigurationError(
            "Missing required API key",
            code="MISSING_API_KEY",
            details={
                "key_name": "OPENAI_API_KEY",
                "config_file": ".env",
                "required_for": "embeddings_service",
            },
        )

        assert error.message == "Missing required API key"
        assert error.code == "MISSING_API_KEY"
        assert error.details["key_name"] == "OPENAI_API_KEY"

    def test_configuration_error_inheritance(self):
        """Test that ConfigurationError inherits from ApplicationError."""
        error = ConfigurationError("Test")
        assert isinstance(error, ApplicationError)

    def test_configuration_error_can_be_raised(self):
        """Test ConfigurationError can be raised and caught."""
        with pytest.raises(ConfigurationError) as exc_info:
            raise ConfigurationError("Invalid database URI")

        assert exc_info.value.message == "Invalid database URI"


class TestErrorInteroperability:
    """Test interoperability between different error types."""

    def test_catching_base_error(self):
        """Test that all errors can be caught as ApplicationError."""
        errors = [
            ValidationError("Test"),
            NotFoundError("Test"),
            DatabaseError("Test"),
            AuthenticationError("Test"),
            AuthorizationError("Test"),
            ConflictError("Test"),
            ServiceError("Test"),
            ConfigurationError("Test"),
        ]

        for error in errors:
            with pytest.raises(ApplicationError):
                raise error

    def test_catching_specific_error_types(self):
        """Test that specific error types can be caught separately."""
        # ValidationError
        with pytest.raises(ValidationError):
            raise ValidationError("Bad input")

        # NotFoundError
        with pytest.raises(NotFoundError):
            raise NotFoundError("Not found")

        # DatabaseError
        with pytest.raises(DatabaseError):
            raise DatabaseError("DB failed")

    def test_error_hierarchy_discrimination(self):
        """Test that we can discriminate between error types."""

        def process_error(error: ApplicationError) -> str:
            if isinstance(error, ValidationError):
                return "validation"
            elif isinstance(error, NotFoundError):
                return "not_found"
            elif isinstance(error, DatabaseError):
                return "database"
            elif isinstance(error, ServiceError):
                return "service"
            else:
                return "generic"

        assert process_error(ValidationError("Test")) == "validation"
        assert process_error(NotFoundError("Test")) == "not_found"
        assert process_error(DatabaseError("Test")) == "database"
        assert process_error(ServiceError("Test")) == "service"
        assert process_error(ApplicationError("Test")) == "generic"

    def test_multiple_exception_handling(self):
        """Test handling multiple exception types in try/except."""

        def raise_random_error(error_type: str):
            if error_type == "validation":
                raise ValidationError("Bad input")
            elif error_type == "not_found":
                raise NotFoundError("Missing")
            elif error_type == "database":
                raise DatabaseError("DB error")

        # Catch specific types
        try:
            raise_random_error("validation")
        except ValidationError as e:
            assert e.message == "Bad input"

        try:
            raise_random_error("not_found")
        except NotFoundError as e:
            assert e.message == "Missing"

        # Catch any ApplicationError
        try:
            raise_random_error("database")
        except ApplicationError as e:
            assert isinstance(e, DatabaseError)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
