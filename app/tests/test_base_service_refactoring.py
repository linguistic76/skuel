"""
Test Suite for BaseService Refactoring
===================================================

Tests all utilities extracted from base_service.py to ensure:
1. Extracted utilities work correctly in isolation
2. BaseService wrappers maintain backward compatibility
3. Type safety and protocol constraints work
4. Edge cases are handled properly

Extracted modules tested:
- core.utils.decorators (with_error_handling, requires_graph_intelligence)
- core.utils.validation_helpers (4 validators)
- core.utils.dto_converters (3 converters)
- core.models.graph (Relationship, GraphPath)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

import pytest

# Test extracted utilities
from core.models.graph_models import GraphPath, Relationship
from core.utils.decorators import requires_graph_intelligence, with_error_handling
from core.utils.dto_converters import from_domain_model, to_domain_model, to_domain_models
from core.utils.result_simplified import Result
from core.utils.validation_helpers import (
    validate_date_range,
    validate_enum,
    validate_positive,
    validate_required,
)

# ============================================================================
# TEST FIXTURES AND MOCK DATA
# ============================================================================


class MockStatus(str, Enum):
    """Mock enum for validation tests."""

    ACTIVE = "active"
    PENDING = "pending"
    COMPLETED = "completed"


@dataclass
class MockDTO:
    """Mock DTO for converter tests."""

    uid: str
    title: str
    count: int

    @classmethod
    def from_dict(cls, data: dict) -> MockDTO:
        return cls(uid=data["uid"], title=data["title"], count=data["count"])


@dataclass(frozen=True)
class MockDomainModel:
    """Mock domain model for converter tests."""

    uid: str
    title: str
    count: int

    @classmethod
    def from_dto(cls, dto: MockDTO) -> MockDomainModel:
        return cls(uid=dto.uid, title=dto.title, count=dto.count)

    def to_dto(self) -> MockDTO:
        return MockDTO(uid=self.uid, title=self.title, count=self.count)


class MockServiceWithLogger:
    """Mock service with logger for decorator tests."""

    def __init__(self):
        self.logger = MockLogger()
        self.graph_intel = None  # For requires_graph_intelligence tests


class MockLogger:
    """Mock logger for decorator tests."""

    def __init__(self):
        self.errors = []

    def error(self, message: str):
        self.errors.append(message)


# ============================================================================
# TESTS: core.utils.decorators
# ============================================================================


class TestDecorators:
    """Test decorator utilities extracted from base_service.py."""

    def test_with_error_handling_async_success(self):
        """Decorator allows successful async operations to pass through."""

        @with_error_handling("test_operation")
        async def successful_operation(self, value: int) -> Result[int]:
            return Result.ok(value * 2)

        service = MockServiceWithLogger()

        # Need to actually await the coroutine
        import asyncio

        result = asyncio.run(successful_operation(service, 5))

        assert result.is_ok
        assert result.value == 10

    def test_with_error_handling_catches_value_error(self):
        """Decorator converts ValueError to validation error."""

        @with_error_handling("test_operation")
        def failing_operation(self, value: int) -> Result[int]:
            if value < 0:
                raise ValueError("Value must be positive")
            return Result.ok(value)

        service = MockServiceWithLogger()
        result = failing_operation(service, -5)

        assert result.is_error
        # Check error message contains the ValueError message
        assert "must be positive" in result.error.message.lower()

    def test_with_error_handling_catches_generic_exception(self):
        """Decorator converts generic exceptions to system errors."""

        @with_error_handling("test_operation")
        def failing_operation(self, value: int) -> Result[int]:
            raise RuntimeError("Something went wrong")

        service = MockServiceWithLogger()
        result = failing_operation(service, 5)

        assert result.is_error
        assert result.error.code == "SYSTEM_ERROR"
        assert "Something went wrong" in result.error.message

    def test_with_error_handling_logs_errors(self):
        """Decorator logs errors when service has logger."""

        @with_error_handling("test_operation")
        def failing_operation(self, value: int) -> Result[int]:
            raise ValueError("Test error")

        service = MockServiceWithLogger()
        _ = failing_operation(service, 5)  # Result intentionally unused - testing logging

        assert len(service.logger.errors) == 1
        assert "Failed to test_operation" in service.logger.errors[0]

    def test_requires_graph_intelligence_blocks_without_intel(self):
        """Decorator blocks when graph_intel is None."""

        @requires_graph_intelligence("test_method")
        async def method_needs_intel(self) -> Result[str]:
            return Result.ok("success")

        service = MockServiceWithLogger()
        service.graph_intel = None

        # Need to actually await the coroutine
        import asyncio

        result = asyncio.run(method_needs_intel(service))

        assert result.is_error
        assert "GraphIntelligenceService not available" in result.error.message

    def test_requires_graph_intelligence_allows_with_intel(self):
        """Decorator allows when graph_intel is present."""

        @requires_graph_intelligence("test_method")
        async def method_needs_intel(self) -> Result[str]:
            return Result.ok("success")

        service = MockServiceWithLogger()
        service.graph_intel = "mock_intelligence_service"  # Present

        import asyncio

        result = asyncio.run(method_needs_intel(service))

        assert result.is_ok
        assert result.value == "success"


# ============================================================================
# TESTS: core.utils.validation_helpers
# ============================================================================


class TestValidationHelpers:
    """Test validation utilities extracted from base_service.py."""

    # validate_required tests
    def test_validate_required_accepts_valid_value(self):
        """validate_required accepts non-empty values."""
        result = validate_required("test_value", "field_name")
        assert result.is_ok
        assert result.value == "test_value"

    def test_validate_required_rejects_none(self):
        """validate_required rejects None."""
        result = validate_required(None, "field_name")
        assert result.is_error
        assert "required" in result.error.message.lower()

    def test_validate_required_rejects_empty_string(self):
        """validate_required rejects empty/whitespace strings."""
        result = validate_required("   ", "field_name")
        assert result.is_error
        assert "required" in result.error.message.lower()

    def test_validate_required_accepts_non_string_values(self):
        """validate_required accepts non-string values (numbers, objects)."""
        result = validate_required(42, "count")
        assert result.is_ok
        assert result.value == 42

    # validate_positive tests
    def test_validate_positive_accepts_positive_number(self):
        """validate_positive accepts positive numbers."""
        result = validate_positive(42, "count")
        assert result.is_ok
        assert result.value == 42.0

    def test_validate_positive_converts_string_to_float(self):
        """validate_positive converts string numbers to float."""
        result = validate_positive("42.5", "amount")
        assert result.is_ok
        assert result.value == 42.5

    def test_validate_positive_rejects_zero(self):
        """validate_positive rejects zero."""
        result = validate_positive(0, "count")
        assert result.is_error
        assert "must be positive" in result.error.message.lower()

    def test_validate_positive_rejects_negative(self):
        """validate_positive rejects negative numbers."""
        result = validate_positive(-5, "count")
        assert result.is_error
        assert "must be positive" in result.error.message.lower()

    def test_validate_positive_rejects_none(self):
        """validate_positive rejects None."""
        result = validate_positive(None, "count")
        assert result.is_error
        assert "required" in result.error.message.lower()

    def test_validate_positive_rejects_non_numeric(self):
        """validate_positive rejects non-numeric values."""
        result = validate_positive("not_a_number", "count")
        assert result.is_error
        assert "must be a number" in result.error.message.lower()

    # validate_enum tests
    def test_validate_enum_accepts_valid_enum(self):
        """validate_enum accepts valid enum members."""
        result = validate_enum(MockStatus.ACTIVE, MockStatus, "status")
        assert result.is_ok
        assert result.value == MockStatus.ACTIVE

    def test_validate_enum_converts_string_to_enum(self):
        """validate_enum converts valid string to enum."""
        result = validate_enum("active", MockStatus, "status")
        assert result.is_ok
        assert result.value == MockStatus.ACTIVE

    def test_validate_enum_accepts_none_for_optional(self):
        """validate_enum accepts None (optional enum)."""
        result = validate_enum(None, MockStatus, "status")
        assert result.is_ok
        assert result.value is None

    def test_validate_enum_rejects_invalid_string(self):
        """validate_enum rejects invalid enum values."""
        result = validate_enum("invalid_status", MockStatus, "status")
        assert result.is_error
        assert "invalid" in result.error.message.lower()

    def test_validate_enum_includes_valid_values_in_error(self):
        """validate_enum includes valid values in error message."""
        result = validate_enum("invalid", MockStatus, "status")
        assert result.is_error
        assert "active" in result.error.message
        assert "pending" in result.error.message
        assert "completed" in result.error.message

    # validate_date_range tests
    def test_validate_date_range_accepts_valid_range(self):
        """validate_date_range accepts end > start."""
        start = date(2025, 1, 1)
        end = date(2025, 12, 31)
        result = validate_date_range(start, end)
        assert result.is_ok

    def test_validate_date_range_accepts_same_date(self):
        """validate_date_range accepts end == start."""
        same_date = date(2025, 1, 1)
        result = validate_date_range(same_date, same_date)
        assert result.is_ok

    def test_validate_date_range_rejects_end_before_start(self):
        """validate_date_range rejects end < start."""
        start = date(2025, 12, 31)
        end = date(2025, 1, 1)
        result = validate_date_range(start, end)
        assert result.is_error
        assert "cannot be before" in result.error.message.lower()

    def test_validate_date_range_handles_datetime_objects(self):
        """validate_date_range converts datetime to date."""
        start = datetime(2025, 1, 1, 10, 30)
        end = datetime(2025, 12, 31, 14, 45)
        result = validate_date_range(start, end)
        assert result.is_ok

    def test_validate_date_range_accepts_none_values(self):
        """validate_date_range accepts None (optional dates)."""
        result = validate_date_range(None, None)
        assert result.is_ok

        result = validate_date_range(date(2025, 1, 1), None)
        assert result.is_ok

    def test_validate_date_range_uses_field_prefix(self):
        """validate_date_range uses field_prefix in error messages."""
        start = date(2025, 12, 31)
        end = date(2025, 1, 1)
        result = validate_date_range(start, end, field_prefix="event_")
        assert result.is_error
        assert "event_end_date" in result.error.message


# ============================================================================
# TESTS: core.utils.dto_converters
# ============================================================================


class TestDTOConverters:
    """Test DTO conversion utilities extracted from base_service.py."""

    def test_to_domain_model_from_dict(self):
        """to_domain_model converts dict to domain model."""
        data = {"uid": "test_1", "title": "Test", "count": 42}
        model = to_domain_model(data, MockDTO, MockDomainModel)

        assert isinstance(model, MockDomainModel)
        assert model.uid == "test_1"
        assert model.title == "Test"
        assert model.count == 42

    def test_to_domain_model_from_dto(self):
        """to_domain_model converts DTO to domain model."""
        dto = MockDTO(uid="test_2", title="Test DTO", count=99)
        model = to_domain_model(dto, MockDTO, MockDomainModel)

        assert isinstance(model, MockDomainModel)
        assert model.uid == "test_2"
        assert model.title == "Test DTO"
        assert model.count == 99

    def test_to_domain_model_from_object_with_dict(self):
        """to_domain_model converts object with __dict__ to domain model."""

        class ObjectWithDict:
            def __init__(self):
                self.uid = "test_3"
                self.title = "Test Object"
                self.count = 77

        obj = ObjectWithDict()
        model = to_domain_model(obj, MockDTO, MockDomainModel)

        assert isinstance(model, MockDomainModel)
        assert model.uid == "test_3"
        assert model.title == "Test Object"
        assert model.count == 77

    def test_to_domain_models_batch_conversion(self):
        """to_domain_models converts list of dicts to domain models."""
        data_list = [
            {"uid": "test_1", "title": "First", "count": 1},
            {"uid": "test_2", "title": "Second", "count": 2},
            {"uid": "test_3", "title": "Third", "count": 3},
        ]

        models = to_domain_models(data_list, MockDTO, MockDomainModel)

        assert len(models) == 3
        assert all(isinstance(m, MockDomainModel) for m in models)
        assert models[0].uid == "test_1"
        assert models[1].title == "Second"
        assert models[2].count == 3

    def test_to_domain_models_empty_list(self):
        """to_domain_models handles empty list."""
        models = to_domain_models([], MockDTO, MockDomainModel)
        assert len(models) == 0

    def test_from_domain_model_with_to_dto_method(self):
        """from_domain_model uses to_dto() method."""
        model = MockDomainModel(uid="test_4", title="Test Model", count=88)
        dto = from_domain_model(model, MockDTO)

        assert isinstance(dto, MockDTO)
        assert dto.uid == "test_4"
        assert dto.title == "Test Model"
        assert dto.count == 88

    def test_from_domain_model_fallback_to_dict(self):
        """from_domain_model falls back to __dict__ if no to_dto()."""

        @dataclass
        class ModelWithoutToDTO:
            uid: str
            title: str
            count: int

        model = ModelWithoutToDTO(uid="test_5", title="No DTO", count=55)
        dto = from_domain_model(model, MockDTO)

        assert isinstance(dto, MockDTO)
        assert dto.uid == "test_5"
        assert dto.title == "No DTO"
        assert dto.count == 55


# ============================================================================
# TESTS: core.models.graph
# ============================================================================


class TestGraphModels:
    """Test graph model dataclasses extracted from base_service.py."""

    def test_relationship_creation(self):
        """Relationship dataclass can be created."""
        rel = Relationship(
            from_uid="node_1",
            rel_type="REQUIRES",
            to_uid="node_2",
            properties={"confidence": 0.9},
        )

        assert rel.from_uid == "node_1"
        assert rel.rel_type == "REQUIRES"
        assert rel.to_uid == "node_2"
        assert rel.properties["confidence"] == 0.9

    def test_relationship_without_properties(self):
        """Relationship can be created without properties."""
        rel = Relationship(from_uid="a", rel_type="CONNECTS", to_uid="b")

        assert rel.from_uid == "a"
        assert rel.rel_type == "CONNECTS"
        assert rel.to_uid == "b"
        assert rel.properties is None

    def test_relationship_is_frozen(self):
        """Relationship is immutable (frozen=True)."""
        rel = Relationship(from_uid="a", rel_type="TEST", to_uid="b")

        with pytest.raises((AttributeError, TypeError)):  # Frozen dataclass error
            rel.from_uid = "changed"  # type: ignore[misc]

    def test_graph_path_creation(self):
        """GraphPath dataclass can be created."""
        path = GraphPath(
            nodes=["node_1", "node_2", "node_3"],
            relationships=[
                Relationship("node_1", "NEXT", "node_2"),
                Relationship("node_2", "NEXT", "node_3"),
            ],
            total_cost=10.5,
        )

        assert len(path.nodes) == 3
        assert len(path.relationships) == 2
        assert path.total_cost == 10.5

    def test_graph_path_default_cost(self):
        """GraphPath has default total_cost of 0.0."""
        path = GraphPath(nodes=["a", "b"], relationships=[Relationship("a", "TO", "b")])

        assert path.total_cost == 0.0

    def test_graph_path_empty(self):
        """GraphPath can represent empty path."""
        path = GraphPath(nodes=[], relationships=[])

        assert len(path.nodes) == 0
        assert len(path.relationships) == 0
        assert path.total_cost == 0.0

    def test_graph_path_is_frozen(self):
        """GraphPath is immutable (frozen=True)."""
        path = GraphPath(nodes=["a"], relationships=[])

        # Frozen prevents attribute reassignment, not list mutation
        with pytest.raises((AttributeError, TypeError)):  # Frozen dataclass error
            path.total_cost = 999.0  # type: ignore[misc]  # Can't reassign attributes


# ============================================================================
# TESTS: Backward Compatibility (BaseService integration)
# ============================================================================


class TestBackwardCompatibility:
    """Test that BaseService wrappers maintain backward compatibility."""

    def test_all_extracted_utilities_importable(self):
        """All extracted utilities can be imported without errors."""
        # This test passing means all imports at top of file worked
        assert with_error_handling is not None
        assert requires_graph_intelligence is not None
        assert validate_required is not None
        assert validate_positive is not None
        assert validate_enum is not None
        assert validate_date_range is not None
        assert to_domain_model is not None
        assert to_domain_models is not None
        assert from_domain_model is not None
        assert Relationship is not None
        assert GraphPath is not None

    def test_base_service_imports_do_not_fail(self):
        """BaseService can import all extracted utilities."""
        # This will fail if imports are broken
        from core.services.base_service import BaseService

        assert BaseService is not None

    def test_extracted_files_compile(self):
        """All extracted files compile successfully."""
        import os
        import py_compile

        files = [
            "/home/mike/skuel/app/core/utils/decorators.py",
            "/home/mike/skuel/app/core/utils/validation_helpers.py",
            "/home/mike/skuel/app/core/utils/dto_converters.py",
            # graph.py was removed - only compile existing files
        ]

        for file in files:
            if os.path.exists(file):
                py_compile.compile(file, doraise=True)

    def test_result_error_factory_integration(self):
        """Validators integrate with Errors factory correctly."""
        result = validate_required(None, "test_field")

        assert result.is_error
        # Error has proper structure
        assert hasattr(result.error, "message")
        assert hasattr(result.error, "code")
        assert "required" in result.error.message.lower()
        assert "test_field" in result.error.message


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestIntegration:
    """Test integration between extracted utilities."""

    def test_decorator_with_validator_pipeline(self):
        """Decorators work with validators in a pipeline."""

        @with_error_handling("validate_input")
        def process_with_validation(self, value: Any, field: str) -> Result[Any]:
            # Use validator inside decorated function
            validation = validate_required(value, field)
            if validation.is_error:
                return validation
            return Result.ok(validation.value.upper())

        service = MockServiceWithLogger()

        # Valid input
        result = process_with_validation(service, "test", "name")
        assert result.is_ok
        assert result.value == "TEST"

        # Invalid input
        result = process_with_validation(service, None, "name")
        assert result.is_error

    def test_converter_with_validator_pipeline(self):
        """Converters work with validators in a data pipeline."""
        # Validate input
        count_result = validate_positive(42, "count")
        assert count_result.is_ok

        # Convert to domain model
        data = {"uid": "test", "title": "Test", "count": int(count_result.value)}
        model = to_domain_model(data, MockDTO, MockDomainModel)

        # Convert back to DTO
        dto = from_domain_model(model, MockDTO)

        assert dto.count == 42

    def test_graph_models_with_converters(self):
        """Graph models can be used with converter utilities."""
        # Create relationship
        rel = Relationship(from_uid="a", rel_type="TEST", to_uid="b")

        # Convert to dict (for storage/transport)
        rel_dict = {
            "from_uid": rel.from_uid,
            "rel_type": rel.rel_type,
            "to_uid": rel.to_uid,
            "properties": rel.properties,
        }

        # Recreate from dict
        new_rel = Relationship(**rel_dict)

        assert new_rel.from_uid == rel.from_uid
        assert new_rel.rel_type == rel.rel_type
        assert new_rel.to_uid == rel.to_uid
