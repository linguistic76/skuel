"""
Facade Delegation Mixin
=======================

Auto-generates delegation methods for facade services.

Phase 2 Consolidation (January 2026):
Instead of writing 30+ one-line delegation methods:

```python
class TasksService:
    async def create_task(self, *args, **kwargs):
        return await self.core.create_task(*args, **kwargs)

    async def get_task(self, *args, **kwargs):
        return await self.core.get_task(*args, **kwargs)

    async def search_tasks(self, *args, **kwargs):
        return await self.search.search(*args, **kwargs)

    # ... 30 more methods
```

Services now declare delegations:

```python
class TasksService(FacadeDelegationMixin):
    _delegations = {
        "create_task": ("core", "create_task"),
        "get_task": ("core", "get_task"),
        "search_tasks": ("search", "search"),
    }
```

Methods are auto-generated at class definition time via __init_subclass__.
IDE completion works because methods exist on the class (not __getattr__).

See Also:
    - /docs/patterns/ROUTE_FACTORIES.md - Similar pattern for routes
    - /core/services/tasks_service.py - Example usage
"""

from __future__ import annotations

import inspect
import sys
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Callable

# Sentinel for detecting missing attributes without hasattr()
_NOT_FOUND = object()


class FacadeDelegationMixin:
    """
    Mixin that auto-generates delegation methods from _delegations specification.

    How it works:
    1. Subclass defines _delegations: dict mapping method names to (sub_service, target_method)
    2. __init_subclass__ generates async methods that delegate to sub-services
    3. Methods are created at class definition time (IDE-visible, not __getattr__)

    Class Attributes:
        _delegations: Mapping of {facade_method: (sub_service, target_method)}
            - facade_method: Name of the method on this facade
            - sub_service: Attribute name of the sub-service (e.g., "core", "search")
            - target_method: Method name on the sub-service to call

    Example:
        ```python
        class TasksService(FacadeDelegationMixin, BaseTasksService):
            _delegations = {
                # CRUD delegations to core
                "create_task": ("core", "create_task"),
                "get_task": ("core", "get_task"),
                "update_task": ("core", "update_task"),
                "delete_task": ("core", "delete_task"),
                # Search delegations
                "search_tasks": ("search", "search"),
                "get_tasks_for_goal": ("search", "get_tasks_for_goal"),
                # Relationship delegations
                "link_to_knowledge": ("relationships", "link_to_knowledge"),
            }
        ```

    Generated methods are async and pass through all args/kwargs:
        ```python
        async def create_task(self, *args, **kwargs):
            return await self.core.create_task(*args, **kwargs)
        ```

    Note:
        - Methods are only generated if they don't already exist on the class
        - This allows manual override for methods needing custom logic
        - Sub-services must be set on the instance before delegation methods are called
    """

    # Delegation specification: {facade_method: (sub_service, target_method)}
    _delegations: ClassVar[dict[str, tuple[str, str]]] = {}

    # Strict mode for signature resolution - raises errors instead of falling back to generic
    # Enable during development to catch annotation/signature issues early
    _strict_delegation_signatures: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """
        Generate delegation methods when subclass is defined.

        Called automatically by Python when a class inherits from FacadeDelegationMixin.
        Creates async methods for each entry in _delegations that doesn't already exist.
        """
        super().__init_subclass__(**kwargs)

        # Get raw annotations and module globals for manual resolution
        # (get_type_hints() fails on complex generics like BaseService[T, U])
        raw_annotations = getattr(cls, "__annotations__", {})

        # Get the module where the class is defined for resolving string annotations
        module = sys.modules.get(cls.__module__, None)
        module_globals = getattr(module, "__dict__", {}) if module else {}

        for facade_method, (sub_service, target_method) in cls._delegations.items():
            # Check for collision with existing methods
            existing = getattr(cls, facade_method, _NOT_FOUND)
            if existing is not _NOT_FOUND and facade_method not in FacadeDelegationMixin.__dict__:
                # Check if existing method is a delegation (from parent class using this mixin)
                is_existing_delegation = (
                    getattr(existing, "__delegation__", _NOT_FOUND) is not _NOT_FOUND
                )
                if not is_existing_delegation:
                    # Method exists in parent but is NOT a delegation - skip to allow manual override
                    # This enables customization: define method in parent to override delegation behavior
                    continue

            # Try to find target method's signature from type annotations
            target_signature = None
            target_func = None
            annotation = raw_annotations.get(sub_service)
            if annotation is not None:
                try:
                    # Resolve string annotation using eval with module globals
                    if isinstance(annotation, str):
                        sub_service_type = eval(annotation, module_globals)
                    else:
                        sub_service_type = annotation

                    # Get the target method and its signature
                    target_func = getattr(sub_service_type, target_method, None)
                    if target_func is not None:
                        # Guard against sync method delegation - async only
                        if not inspect.iscoroutinefunction(target_func):
                            raise TypeError(
                                f"{cls.__name__}.{facade_method} cannot delegate to sync method "
                                f"{sub_service}.{target_method}() - target must be async"
                            )
                        target_signature = inspect.signature(target_func)
                except TypeError:
                    raise  # Re-raise sync method guard errors
                except Exception as e:
                    if cls._strict_delegation_signatures:
                        raise RuntimeError(
                            f"Failed to resolve signature for {sub_service}.{target_method}"
                        ) from e
                    # Can't resolve annotation or get signature, use generic

            # Create the delegation method
            delegator = cls._create_delegator(
                sub_service, target_method, facade_method, target_signature, target_func
            )
            setattr(cls, facade_method, delegator)

    @staticmethod
    def _create_delegator(
        sub_service: str,
        target_method: str,
        facade_method: str,
        target_signature: inspect.Signature | None = None,
        target_func: Callable[..., Any] | None = None,
    ) -> Callable[..., Any]:
        """
        Create an async delegation method.

        Args:
            sub_service: Attribute name of the sub-service (e.g., "core")
            target_method: Method name on the sub-service
            facade_method: Name for the generated method (for docstring)
            target_signature: Optional signature to preserve from target method
            target_func: Optional reference to the target function (for __wrapped__)

        Returns:
            Async function that delegates to the sub-service method
        """

        async def delegator(self: Any, *args: Any, **kwargs: Any) -> Any:
            """Auto-generated delegation method."""
            service = getattr(self, sub_service, None)
            if service is None:
                raise AttributeError(
                    f"{self.__class__.__name__}.{facade_method}() requires "
                    f"'{sub_service}' sub-service to be initialized"
                )
            method = getattr(service, target_method, None)
            if method is None:
                raise AttributeError(
                    f"{sub_service}.{target_method}() not found on {service.__class__.__name__}"
                )
            return await method(*args, **kwargs)

        # Set better docstring and name
        delegator.__doc__ = f"Delegates to self.{sub_service}.{target_method}()"
        delegator.__name__ = facade_method
        delegator.__qualname__ = facade_method

        # Add delegation metadata for introspection/debugging
        delegator.__delegation__ = {  # type: ignore[attr-defined]
            "sub_service": sub_service,
            "target_method": target_method,
        }

        # Preserve method signature if available (for inspect.signature() compatibility)
        if target_signature is not None:
            delegator.__signature__ = target_signature  # type: ignore[attr-defined]

        # Preserve wrapped function reference for tooling (debuggers, decorators, tracebacks)
        if target_func is not None:
            delegator.__wrapped__ = target_func  # type: ignore[attr-defined]

        return delegator

    def validate_delegations(self) -> None:
        """
        Validate that all delegations can be resolved.

        Call this during service __init__ to fail fast if sub-services
        or target methods are missing. Catches configuration errors at
        bootstrap rather than at first call.

        Raises:
            RuntimeError: If a sub-service is missing or a target method doesn't exist

        Example:
            ```python
            class TasksService(FacadeDelegationMixin):
                _delegations = {...}

                def __init__(self, core, search, relationships):
                    self.core = core
                    self.search = search
                    self.relationships = relationships
                    self.validate_delegations()  # Fail fast if misconfigured
            ```
        """
        errors: list[str] = []

        for facade_method, (sub_service, target_method) in self._delegations.items():
            service = getattr(self, sub_service, None)
            if service is None:
                errors.append(f"  - {facade_method}: sub-service '{sub_service}' not found")
                continue

            if getattr(service, target_method, None) is None:
                errors.append(
                    f"  - {facade_method}: '{sub_service}.{target_method}()' "
                    f"not found on {service.__class__.__name__}"
                )

        if errors:
            raise RuntimeError(
                f"Delegation validation failed for {self.__class__.__name__}:\n" + "\n".join(errors)
            )

    def get_delegations(self) -> dict[str, dict[str, Any]]:
        """
        Get all delegations for runtime introspection.

        Returns a dictionary mapping facade method names to their delegation info.
        Useful for debugging, documentation generation, and testing.

        Returns:
            Dict mapping facade methods to delegation info:
            {
                "create_task": {
                    "sub_service": "core",
                    "target_method": "create_task",
                    "signature": "(request: TaskCreateRequest, user_uid: str) -> Result[Task]",
                    "exists": True,
                },
                ...
            }

        Example:
            ```python
            tasks_service = TasksService(...)
            delegations = tasks_service.get_delegations()

            # Check if method is delegated
            if "create_task" in delegations:
                print(
                    f"create_task delegates to {delegations['create_task']['sub_service']}"
                )

            # Get all delegated methods
            print(f"Total delegated methods: {len(delegations)}")
            ```

        See Also:
            - /docs/reference/BASESERVICE_METHOD_INDEX.md - Auto-generated from this method
            - validate_delegations() - Checks delegation integrity at init time
        """
        result: dict[str, dict[str, Any]] = {}

        for facade_method, (sub_service, target_method) in self._delegations.items():
            # Get the actual method object
            method = getattr(self.__class__, facade_method, None)

            # Extract signature if available
            signature_str = None
            if method is not None:
                try:
                    sig = inspect.signature(method)
                    signature_str = str(sig)
                except (ValueError, TypeError):
                    signature_str = None

            # Check if sub-service and target method exist
            service_exists = getattr(self, sub_service, None) is not None
            method_exists = False
            if service_exists:
                service = getattr(self, sub_service)
                method_exists = getattr(service, target_method, None) is not None

            result[facade_method] = {
                "sub_service": sub_service,
                "target_method": target_method,
                "signature": signature_str,
                "exists": service_exists and method_exists,
                "sub_service_exists": service_exists,
                "target_method_exists": method_exists,
            }

        return result


# ============================================================================
# COMMON DELEGATION SPECIFICATIONS
# ============================================================================
# These can be imported and used as starting points for domain facades.


# Standard CRUD delegations to "core" sub-service
CRUD_DELEGATIONS: dict[str, tuple[str, str]] = {
    "create": ("core", "create"),
    "get": ("core", "get"),
    "get_many": ("core", "get_many"),
    "update": ("core", "update"),
    "delete": ("core", "delete"),
    "list": ("core", "list"),
}

# Standard search delegations to "search" sub-service
SEARCH_DELEGATIONS: dict[str, tuple[str, str]] = {
    "search": ("search", "search"),
    "get_by_status": ("search", "get_by_status"),
    "get_by_category": ("search", "get_by_category"),
    "list_categories": ("search", "list_categories"),
    "get_by_relationship": ("search", "get_by_relationship"),
}

# Standard relationship delegations to "relationships" sub-service
RELATIONSHIP_DELEGATIONS: dict[str, tuple[str, str]] = {
    "link_to_knowledge": ("relationships", "link_to_knowledge"),
    "link_to_goal": ("relationships", "link_to_goal"),
    "get_cross_domain_context": ("relationships", "get_cross_domain_context"),
    "get_with_semantic_context": ("relationships", "get_with_semantic_context"),
}


def merge_delegations(*delegation_dicts: dict[str, tuple[str, str]]) -> dict[str, tuple[str, str]]:
    """
    Merge multiple delegation dictionaries.

    Useful for combining standard delegations with domain-specific ones.

    Example:
        ```python
        class TasksService(FacadeDelegationMixin):
            _delegations = merge_delegations(
                CRUD_DELEGATIONS,
                SEARCH_DELEGATIONS,
                {
                    "complete_task": ("core", "complete_task"),
                    "get_blocked_tasks": ("search", "get_blocked_tasks"),
                },
            )
        ```

    Args:
        *delegation_dicts: Delegation dictionaries to merge

    Returns:
        Merged dictionary (later dicts override earlier ones)
    """
    result: dict[str, tuple[str, str]] = {}
    for d in delegation_dicts:
        result.update(d)
    return result


# ============================================================================
# DOMAIN-PREFIXED DELEGATION FACTORIES
# ============================================================================
# These factories generate delegation specs with domain-prefixed method names.
# Use these to reduce boilerplate while maintaining domain-specific API names.


def create_core_delegations(domain: str, plural: str | None = None) -> dict[str, tuple[str, str]]:
    """
    Generate core CRUD delegations with domain-prefixed method names.

    All Activity Domain facades share this pattern:
    - get_{domain} -> core.get_{domain}
    - get_user_{plural} -> core.get_user_{plural}
    - get_user_items_in_range -> core.get_user_items_in_range

    Args:
        domain: Singular domain name (e.g., "task", "goal", "habit")
        plural: Plural form (defaults to domain + "s")

    Returns:
        Delegation dictionary for core operations

    Example:
        ```python
        _delegations = merge_delegations(
            create_core_delegations("task"),  # Generates get_task, get_user_tasks, etc.
            # ... domain-specific delegations
        )
        ```
    """
    p = plural or f"{domain}s"
    return {
        f"get_{domain}": ("core", f"get_{domain}"),
        f"get_user_{p}": ("core", f"get_user_{p}"),
        "get_user_items_in_range": ("core", "get_user_items_in_range"),
    }


def create_relationship_delegations(
    domain: str, include_semantic: bool = True
) -> dict[str, tuple[str, str]]:
    """
    Generate relationship delegations with domain-prefixed method names.

    All Activity Domain facades share this pattern:
    - get_{domain}_cross_domain_context -> relationships.get_cross_domain_context
    - get_{domain}_with_semantic_context -> relationships.get_with_semantic_context

    Args:
        domain: Singular domain name (e.g., "task", "goal", "habit")
        include_semantic: Whether to include semantic context delegation (default True)
            Set to False for domains like Principles that don't use it.

    Returns:
        Delegation dictionary for relationship operations

    Example:
        ```python
        _delegations = merge_delegations(
            create_relationship_delegations("task"),
            # ... domain-specific delegations
        )
        ```
    """
    delegations: dict[str, tuple[str, str]] = {
        f"get_{domain}_cross_domain_context": ("relationships", "get_cross_domain_context"),
    }
    if include_semantic:
        delegations[f"get_{domain}_with_semantic_context"] = (
            "relationships",
            "get_with_semantic_context",
        )
    return delegations


def create_intelligence_delegations(domain: str) -> dict[str, tuple[str, str]]:
    """
    Generate intelligence context delegation with domain-prefixed method name.

    All Activity Domain facades share this pattern:
    - get_{domain}_with_context -> intelligence.get_{domain}_with_context

    Args:
        domain: Singular domain name (e.g., "task", "goal", "habit")

    Returns:
        Delegation dictionary for intelligence context operation

    Example:
        ```python
        _delegations = merge_delegations(
            create_intelligence_delegations("task"),
            # ... domain-specific delegations
        )
        ```

    Note:
        This only generates the common `get_{domain}_with_context` delegation.
        Domain-specific intelligence methods should be added separately.
    """
    return {
        f"get_{domain}_with_context": ("intelligence", f"get_{domain}_with_context"),
    }
