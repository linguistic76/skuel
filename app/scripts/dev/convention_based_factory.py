"""
Auto-Generated Convention-Based Backend Factory
==============================================

Generated from naming convention analysis.
Creates universal backends automatically based on domain naming patterns.
"""

from typing import TypeVar

from neo4j import AsyncDriver

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend

T = TypeVar("T")

# Auto-discovered domain mappings
DOMAIN_MAPPINGS = {
    "finance": {
        "class": "ExpensePure",
        "label": "Expense",
        "import": "core.models.finance.finance_pure",
    },
    "progress": {"class": "Progress", "label": "Progress", "import": "core.models.progress"},
    "knowledge": {"class": "Ku", "label": "Ku", "import": "core.models.knowledge"},
    "habit": {"class": "Habit", "label": "Habit", "import": "core.models.habit"},
    "user": {"class": "UserPreferences", "label": "UserPreferences", "import": "core.models.user"},
    "relationships": {
        "class": "Relationship",
        "label": "Relationship",
        "import": "core.models.relationships",
    },
    "transcription": {
        "class": "TranscriptionPure",
        "label": "Transcription",
        "import": "core.models.transcription.transcription_pure",
    },
    "principle": {"class": "Principle", "label": "Principle", "import": "core.models.principle"},
    "event": {"class": "Event", "label": "Event", "import": "core.models.event"},
    "search": {
        "class": "FacetExtraction",
        "label": "FacetExtraction",
        "import": "core.models.search",
    },
    "learning": {
        "class": "Ls",
        "label": "Ls",
        "import": "core.models.learning",
    },
    "goal": {"class": "Goal", "label": "Goal", "import": "core.models.goal"},
    "task": {"class": "Task", "label": "Task", "import": "core.models.task"},
}


class ConventionBasedFactory:
    """Auto-generates backends based on naming conventions."""

    @staticmethod
    def create_backend(domain: str, driver: AsyncDriver) -> UniversalNeo4jBackend:
        """Create universal backend for any domain by convention."""
        if domain not in DOMAIN_MAPPINGS:
            raise ValueError(f"Unknown domain: {domain}. Available: {list(DOMAIN_MAPPINGS.keys())}")

        mapping = DOMAIN_MAPPINGS[domain]

        # Dynamic import
        import importlib

        module = importlib.import_module(mapping["import"])
        entity_class = getattr(module, mapping["class"])

        return UniversalNeo4jBackend(
            driver=driver, label=mapping["label"], entity_class=entity_class
        )

    @staticmethod
    def create_all_backends(driver: AsyncDriver) -> dict[str, UniversalNeo4jBackend]:
        """Create all backends at once."""
        return {
            domain: ConventionBasedFactory.create_backend(domain, driver)
            for domain in DOMAIN_MAPPINGS
        }


# Convenience functions
def create_tasks_backend(driver: AsyncDriver) -> UniversalNeo4jBackend:
    return ConventionBasedFactory.create_backend("task", driver)


def create_events_backend(driver: AsyncDriver) -> UniversalNeo4jBackend:
    return ConventionBasedFactory.create_backend("event", driver)


# Add more convenience functions for each domain...
