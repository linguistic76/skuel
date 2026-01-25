"""
Configuration Data Loaders
===========================

Utilities for loading domain configuration data from /data/config/

These loaders provide typed access to YAML/JSON configuration files
that define domain-specific defaults, categories, and templates.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)

# Base path for domain configuration data
DATA_CONFIG_PATH = Path(__file__).parent.parent.parent / "data" / "config"


class ConfigLoader:
    """Base class for configuration loaders."""

    @staticmethod
    def _load_yaml(filename: str) -> Result[dict[str, Any]]:
        """
        Load YAML file from data/config directory.

        Args:
            filename: Name of YAML file (e.g., "finance_categories.yaml")

        Returns:
            Result[Dict] with parsed YAML data
        """
        try:
            config_path = DATA_CONFIG_PATH / filename

            if not config_path.exists():
                return Result.fail(
                    Errors.not_found(
                        resource="Configuration file", identifier=f"{filename} at {config_path}"
                    )
                )

            with config_path.open("r") as f:
                data = yaml.safe_load(f)

            logger.debug(f"Loaded configuration from {filename}")
            return Result.ok(data)

        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error in {filename}: {e}")
            return Result.fail(
                Errors.validation(message=f"Invalid YAML in {filename}: {e}", field="yaml_content")
            )
        except Exception as e:
            logger.error(f"Failed to load {filename}: {e}")
            return Result.fail(
                Errors.system(
                    f"Failed to load configuration: {filename}", details={"error": str(e)}
                )
            )


class FinanceCategoriesLoader(ConfigLoader):
    """Loader for finance categories configuration."""

    _cache: dict[str, Any] | None = None

    @classmethod
    @lru_cache(maxsize=1)
    def load(cls) -> Result[dict[str, Any]]:
        """
        Load finance categories from finance_categories.yaml.

        Returns cached result on subsequent calls for performance.

        Returns:
            Result[Dict] with structure:
            {
                "main_categories": [...],
                "subcategories": {...},
                "expense_statuses": [...],
                "budget_periods": [...]
            }
        """
        if cls._cache is not None:
            return Result.ok(cls._cache)

        result = cls._load_yaml("finance_categories.yaml")
        if result.is_ok:
            cls._cache = result.value
            logger.info("Finance categories loaded and cached")

        return result

    @classmethod
    def get_main_categories(cls) -> Result[list[dict[str, str]]]:
        """
        Get main budget categories.

        Returns:
            Result[List[Dict]] with each category having:
            - name: str
            - code: str
            - description: str
        """
        result = cls.load()
        if not result.is_ok:
            return Result.fail(result)

        categories = result.value.get("main_categories", [])
        return Result.ok(categories)

    @classmethod
    def get_subcategories(cls, main_code: str) -> Result[list[dict[str, Any]]]:
        """
        Get subcategories for a main category.

        Args:
            main_code: Main category code (e.g., "PERSONAL", "HOUSE", "SKUEL")

        Returns:
            Result[List[Dict]] with subcategories
        """
        result = cls.load()
        if not result.is_ok:
            return Result.fail(result)

        subcategories = result.value.get("subcategories", {})
        category_subs = subcategories.get(main_code, [])

        if not category_subs:
            available = ", ".join(subcategories.keys())
            return Result.fail(
                Errors.not_found(
                    resource=f"Subcategories for {main_code}",
                    identifier=f"Available categories: {available}",
                )
            )

        return Result.ok(category_subs)

    @classmethod
    def get_all_subcategories(cls) -> Result[dict[str, list[dict[str, Any]]]]:
        """
        Get all subcategories organized by main category.

        Returns:
            Result[Dict[str, List]] mapping main_code -> subcategories
        """
        result = cls.load()
        if not result.is_ok:
            return Result.fail(result)

        subcategories = result.value.get("subcategories", {})
        return Result.ok(subcategories)

    @classmethod
    def find_subcategory_by_code(cls, subcategory_code: str) -> Result[dict[str, Any] | None]:
        """
        Find a subcategory by its code across all main categories.

        Args:
            subcategory_code: Subcategory code (e.g., "food", "utilities")

        Returns:
            Result[Optional[Dict]] with subcategory details or None if not found
        """
        result = cls.get_all_subcategories()
        if not result.is_ok:
            return Result.fail(result)

        all_subcategories = result.value

        for main_code, subs in all_subcategories.items():
            for sub in subs:
                if sub.get("code") == subcategory_code:
                    # Add main category for context
                    return Result.ok({**sub, "main_category": main_code})

        return Result.ok(None)

    @classmethod
    def get_expense_statuses(cls) -> Result[list[str]]:
        """
        Get valid expense statuses.

        Returns:
            Result[List[str]] with expense statuses (e.g., ["pending", "paid"])
        """
        result = cls.load()
        if not result.is_ok:
            return Result.fail(result)

        statuses = result.value.get("expense_statuses", ["pending", "paid"])
        return Result.ok(statuses)

    @classmethod
    def get_budget_periods(cls) -> Result[list[str]]:
        """
        Get valid budget periods.

        Returns:
            Result[List[str]] with budget periods (e.g., ["monthly", "quarterly", "yearly"])
        """
        result = cls.load()
        if not result.is_ok:
            return Result.fail(result)

        periods = result.value.get("budget_periods", ["monthly"])
        return Result.ok(periods)

    @classmethod
    def validate_category(cls, main_code: str, subcategory_code: str) -> Result[bool]:
        """
        Validate that a subcategory belongs to a main category.

        Args:
            main_code: Main category code
            subcategory_code: Subcategory code

        Returns:
            Result[bool] - True if valid, False otherwise
        """
        result = cls.get_subcategories(main_code)
        if result.is_error:
            return Result.ok(False)

        subcategories = result.value
        for sub in subcategories:
            if sub.get("code") == subcategory_code:
                return Result.ok(True)

        return Result.ok(False)

    @classmethod
    def reload(cls) -> Result[dict[str, Any]]:
        """
        Force reload of finance categories from disk.

        Clears cache and reloads configuration.

        Returns:
            Result[Dict] with fresh data
        """
        cls._cache = None
        cls.load.cache_clear()
        return cls.load()


# Convenience functions for common operations


def load_finance_categories() -> Result[dict[str, Any]]:
    """
    Load finance categories configuration.

    Convenience function for FinanceCategoriesLoader.load()
    """
    return FinanceCategoriesLoader.load()


def get_finance_main_categories() -> Result[list[dict[str, str]]]:
    """
    Get main finance categories.

    Convenience function for FinanceCategoriesLoader.get_main_categories()
    """
    return FinanceCategoriesLoader.get_main_categories()


def get_finance_subcategories(main_code: str) -> Result[list[dict[str, Any]]]:
    """
    Get subcategories for a main category.

    Convenience function for FinanceCategoriesLoader.get_subcategories()
    """
    return FinanceCategoriesLoader.get_subcategories(main_code)


def validate_finance_category(main_code: str, subcategory_code: str) -> Result[bool]:
    """
    Validate finance category combination.

    Convenience function for FinanceCategoriesLoader.validate_category()
    """
    return FinanceCategoriesLoader.validate_category(main_code, subcategory_code)


# Export public API
__all__ = [
    "ConfigLoader",
    "FinanceCategoriesLoader",
    "get_finance_main_categories",
    "get_finance_subcategories",
    "load_finance_categories",
    "validate_finance_category",
]
