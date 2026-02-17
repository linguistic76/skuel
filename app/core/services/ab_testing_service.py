"""
A/B Testing Service
===================

Simple A/B testing infrastructure for comparing search strategies.

**Use Case:**
Compare semantic search vs. standard search to measure:
- Result relevance (user clicks)
- Time to find desired content
- User satisfaction

**Design Philosophy:**
- Simple hash-based assignment (deterministic based on user_uid)
- No database storage needed (stateless)
- Configuration-driven (enable/disable via config)
- Metrics tracked via existing search metrics infrastructure

**Example:**
```python
ab_service = ABTestingService(config.ab_testing)

# Check if user is in treatment group
group = ab_service.get_test_group("semantic_search_v1", user_uid)

if group == TestGroup.TREATMENT:
    # Use semantic search
    result = await vector_search.semantic_enhanced_search(...)
else:
    # Use standard search
    result = await ku_service.search(...)
```
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any


class TestGroup(str, Enum):
    """A/B test group assignment."""

    CONTROL = "control"  # Standard behavior
    TREATMENT = "treatment"  # New feature being tested


@dataclass(frozen=True)
class ABTestConfig:
    """
    Configuration for a single A/B test.

    Attributes:
        test_id: Unique identifier for the test
        enabled: Whether the test is active
        treatment_percentage: Percentage of users in treatment group (0.0-1.0)
        description: Human-readable description
    """

    test_id: str
    enabled: bool = False
    treatment_percentage: float = 0.5  # 50/50 split by default
    description: str = ""


class ABTestingService:
    """
    Simple A/B testing service using deterministic hash-based assignment.

    **Key Features:**
    - Deterministic: Same user always gets same group for a test
    - Stateless: No database storage required
    - Fast: Simple hash calculation
    - Configurable: Enable/disable via config

    **Example:**
    ```python
    config = ABTestConfig(
        test_id="semantic_search_v1",
        enabled=True,
        treatment_percentage=0.5,  # 50% in treatment
        description="Compare semantic vs standard search",
    )
    service = ABTestingService({"semantic_search_v1": config})

    # Get assignment for user
    group = service.get_test_group("semantic_search_v1", user_uid)
    is_treatment = service.is_in_treatment("semantic_search_v1", user_uid)
    ```
    """

    def __init__(self, test_configs: dict[str, ABTestConfig] | None = None) -> None:
        """
        Initialize A/B testing service with test configurations.

        Args:
            test_configs: Dict mapping test_id -> ABTestConfig
        """
        self.test_configs = test_configs or {}

    def get_test_group(self, test_id: str, user_uid: str) -> TestGroup:
        """
        Get test group assignment for a user (deterministic).

        Uses MD5 hash of test_id + user_uid for assignment.
        Same user always gets same group for a given test.

        Args:
            test_id: Unique identifier for the test
            user_uid: User UID (e.g., "user.alice")

        Returns:
            TestGroup.CONTROL or TestGroup.TREATMENT

        Example:
            >>> service.get_test_group("semantic_search_v1", "user.alice")
            TestGroup.TREATMENT
        """
        # Check if test exists and is enabled
        config = self.test_configs.get(test_id)
        if not config or not config.enabled:
            # Test disabled -> everyone in control group
            return TestGroup.CONTROL

        # Deterministic hash-based assignment
        hash_input = f"{test_id}:{user_uid}".encode()
        hash_value = hashlib.md5(hash_input).hexdigest()
        hash_int = int(hash_value[:8], 16)  # Use first 8 hex chars
        hash_fraction = hash_int / 0xFFFFFFFF  # Normalize to 0.0-1.0

        # Assign based on treatment percentage
        if hash_fraction < config.treatment_percentage:
            return TestGroup.TREATMENT
        return TestGroup.CONTROL

    def is_in_treatment(self, test_id: str, user_uid: str) -> bool:
        """
        Check if user is in treatment group (convenience method).

        Args:
            test_id: Test identifier
            user_uid: User UID

        Returns:
            True if user is in treatment group, False otherwise
        """
        return self.get_test_group(test_id, user_uid) == TestGroup.TREATMENT

    def is_in_control(self, test_id: str, user_uid: str) -> bool:
        """
        Check if user is in control group (convenience method).

        Args:
            test_id: Test identifier
            user_uid: User UID

        Returns:
            True if user is in control group, False otherwise
        """
        return self.get_test_group(test_id, user_uid) == TestGroup.CONTROL

    def get_test_metadata(self, test_id: str) -> dict[str, Any] | None:
        """
        Get metadata for a test.

        Args:
            test_id: Test identifier

        Returns:
            Dict with test metadata, or None if test doesn't exist
        """
        config = self.test_configs.get(test_id)
        if not config:
            return None

        return {
            "test_id": config.test_id,
            "enabled": config.enabled,
            "treatment_percentage": config.treatment_percentage,
            "description": config.description,
        }

    def add_test(self, config: ABTestConfig) -> None:
        """
        Add or update a test configuration.

        Args:
            config: Test configuration
        """
        self.test_configs[config.test_id] = config

    def remove_test(self, test_id: str) -> None:
        """
        Remove a test configuration.

        Args:
            test_id: Test identifier
        """
        self.test_configs.pop(test_id, None)

    def list_active_tests(self) -> list[str]:
        """
        Get list of currently active test IDs.

        Returns:
            List of test IDs where enabled=True
        """
        return [test_id for test_id, config in self.test_configs.items() if config.enabled]


__all__ = ["ABTestingService", "ABTestConfig", "TestGroup"]
