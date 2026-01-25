#!/usr/bin/env python3
"""
Fluent API Mock Helpers
=======================

Helpers for mocking SKUEL's fluent relationship API in tests.

The fluent API pattern:
    backend.relate() \
        .from_node(from_uid) \
        .via(relationship_type) \
        .to_node(to_uid) \
        .with_metadata(**props) \
        .create()

This requires special mocking because each method in the chain returns self,
and the final .create() is async.
"""

from unittest.mock import AsyncMock, Mock

from core.utils.result_simplified import Result


def create_fluent_relationship_mock(create_result=None, delete_result=None):
    """
    Create a properly mocked fluent relationship API.

    This helper creates a mock that supports method chaining for SKUEL's
    RelationshipBuilder fluent API. Each method in the chain returns the
    mock itself, allowing proper method chaining, and the final .create()
    or .delete() methods return Result objects.

    Args:
        create_result: Result to return from .create() call.
                      Defaults to Result.ok(True)
        delete_result: Result to return from .delete() call.
                      Defaults to Result.ok(1)

    Returns:
        Mock function that when called returns a mock RelationshipBuilder
        supporting fluent chaining:
        - .from_node(uid) -> self
        - .via(type) -> self
        - .to_node(uid) -> self
        - .with_metadata(**props) -> self
        - .create() -> async Result[bool]
        - .delete() -> async Result[int]

    Example:
        >>> backend = Mock()
        >>> backend.relate = create_fluent_relationship_mock()
        >>>
        >>> # Test code can now use fluent API:
        >>> result = await backend.relate() \
        ...     .from_node("task:123") \
        ...     .via("REQUIRES_KNOWLEDGE") \
        ...     .to_node("ku.python.async") \
        ...     .create()
        >>> assert result.is_ok
    """
    if create_result is None:
        create_result = Result.ok(True)

    if delete_result is None:
        delete_result = Result.ok(1)

    # Create the mock builder that supports chaining
    mock_builder = Mock()
    mock_builder.from_node = Mock(return_value=mock_builder)
    mock_builder.via = Mock(return_value=mock_builder)
    mock_builder.to_node = Mock(return_value=mock_builder)
    mock_builder.with_metadata = Mock(return_value=mock_builder)
    mock_builder.create = AsyncMock(return_value=create_result)
    mock_builder.delete = AsyncMock(return_value=delete_result)

    # Return a mock function that returns the builder when called
    return Mock(return_value=mock_builder)


def create_fluent_relationship_mock_with_sequence(create_results=None):
    """
    Create a fluent relationship mock that returns different results for sequential calls.

    Useful when testing multiple relationship creations in a single test.

    Args:
        create_results: List of Result objects to return from sequential .create() calls.
                       If None, defaults to [Result.ok(True)] repeated.

    Returns:
        Mock function supporting fluent API with side_effect for .create()

    Example:
        >>> backend = Mock()
        >>> backend.relate = create_fluent_relationship_mock_with_sequence(
        ...     [
        ...         Result.ok(True),
        ...         Result.fail(Errors.database("create", "Connection lost")),
        ...         Result.ok(True),
        ...     ]
        ... )
        >>>
        >>> # First call succeeds
        >>> result1 = await backend.relate().from_node("a").to_node("b").create()
        >>> assert result1.is_ok
        >>>
        >>> # Second call fails
        >>> result2 = await backend.relate().from_node("c").to_node("d").create()
        >>> assert result2.is_error
        >>>
        >>> # Third call succeeds
        >>> result3 = await backend.relate().from_node("e").to_node("f").create()
        >>> assert result3.is_ok
    """
    if create_results is None:
        create_results = [Result.ok(True)]

    mock_builder = Mock()
    mock_builder.from_node = Mock(return_value=mock_builder)
    mock_builder.via = Mock(return_value=mock_builder)
    mock_builder.to_node = Mock(return_value=mock_builder)
    mock_builder.with_metadata = Mock(return_value=mock_builder)
    mock_builder.create = AsyncMock(side_effect=create_results)
    mock_builder.delete = AsyncMock(return_value=Result.ok(1))

    return Mock(return_value=mock_builder)
