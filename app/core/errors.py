"""
Core Error Classes
==================

Custom exception classes for the application.
"""

__version__ = "1.0"


from typing import Any


class ApplicationError(Exception):
    """Base exception for all application errors"""

    def __init__(self, message: str, code: str | None = None, details: Any | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        """
        Convert error to machine-readable dictionary.

        Returns standardized error payload for boundary handling,
        logging, telemetry, and client rendering.
        """
        base_payload: dict[str, Any] = {
            "message": self.message,
            "code": self.code,
            "details": self.details,
        }

        # Include subclass-specific fields
        extra_fields = {
            key: value
            for key, value in self.__dict__.items()
            if key not in {"message", "code", "details"} and not key.startswith("_")
        }

        return {**base_payload, **extra_fields}


class ValidationError(ApplicationError):
    """Raised when validation fails"""

    def __init__(self, message: str, field: str | None = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.field = field


class NotFoundError(ApplicationError):
    """Raised when a resource is not found"""

    def __init__(
        self,
        message: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.resource_type = resource_type
        self.resource_id = resource_id


class DatabaseError(ApplicationError):
    """Raised when database operations fail"""

    def __init__(self, message: str, operation: str | None = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.operation = operation

    @classmethod
    def query_failed(cls, details: str) -> "DatabaseError":
        """Create error for failed query"""
        return cls(f"Database query failed: {details}", operation="query")

    @classmethod
    def connection_failed(cls, details: str) -> "DatabaseError":
        """Create error for failed connection"""
        return cls(f"Database connection failed: {details}", operation="connect")

    @classmethod
    def transaction_failed(cls, details: str) -> "DatabaseError":
        """Create error for failed transaction"""
        return cls(f"Database transaction failed: {details}", operation="transaction")

    @classmethod
    def operation_failed(cls, details: str) -> "DatabaseError":
        """Create error for failed database operation"""
        return cls(f"Database operation failed: {details}", operation="operation")


class AuthenticationError(ApplicationError):
    """Raised when authentication fails"""

    pass


class AuthorizationError(ApplicationError):
    """Raised when authorization fails"""

    pass


class ConflictError(ApplicationError):
    """Raised when there's a conflict (e.g., duplicate resource)"""

    pass


class ServiceError(ApplicationError):
    """Raised when a service operation fails"""

    def __init__(self, message: str, service_name: str | None = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.service_name = service_name


class ConfigurationError(ApplicationError):
    """Raised when configuration is invalid or missing"""

    pass
