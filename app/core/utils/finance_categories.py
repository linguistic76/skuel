"""
Finance Categories Loader
==========================

Loads and manages the hierarchical finance category structure from YAML config.

This module provides:
- Category hierarchy loading from finance_categories.yaml
- Category validation and lookup
- Subcategory mapping
- Tag-based categorization helpers

Version: 1.0.0 (October 6, 2025)
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from core.utils.logging import get_logger

logger = get_logger("skuel.utils.finance_categories")


@dataclass(frozen=True)
class CategoryInfo:
    """Immutable category information."""

    name: str
    code: str
    description: str | None = None
    tags: tuple[str, ...] = ()
    parent_code: str | None = None


@dataclass(frozen=True)
class CategoryHierarchy:
    """Immutable finance category hierarchy."""

    main_categories: tuple[CategoryInfo, ...]
    subcategories: dict[str, tuple[CategoryInfo, ...]]
    all_categories: dict[str, CategoryInfo]  # code -> CategoryInfo lookup
    tag_to_category: dict[str, str]  # tag -> category code mapping


class FinanceCategoriesLoader:
    """
    Loads and manages finance categories from YAML configuration.

    Usage:
        loader = FinanceCategoriesLoader()
        hierarchy = loader.get_hierarchy()

        # Get main categories
        main_cats = hierarchy.main_categories

        # Get subcategories for PERSONAL
        personal_subs = hierarchy.subcategories.get('PERSONAL', ())

        # Look up category by code
        category = hierarchy.all_categories.get('food')

        # Find category by tag
        category_code = hierarchy.tag_to_category.get('groceries')
    """

    _instance = None
    _hierarchy: CategoryHierarchy | None = None

    def __new__(cls) -> "FinanceCategoriesLoader":
        """Singleton pattern - one instance per process."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize loader (idempotent)."""
        if self._hierarchy is None:
            self._load_categories()

    @property
    def config_path(self) -> Path:
        """Get path to finance_categories.yaml."""
        # From /core/utils/finance_categories.py
        # Navigate to /data/config/finance_categories.yaml
        return Path(__file__).parent.parent.parent / "data" / "config" / "finance_categories.yaml"

    def _load_categories(self) -> None:
        """Load categories from YAML file."""
        try:
            with self.config_path.open("r") as f:
                data = yaml.safe_load(f)

            # Parse main categories
            main_cats = [
                CategoryInfo(
                    name=cat_data["name"],
                    code=cat_data["code"],
                    description=cat_data.get("description"),
                )
                for cat_data in data.get("main_categories", [])
            ]

            # Parse subcategories
            subcategories = {}
            all_categories = {}
            tag_to_category = {}

            # Add main categories to all_categories
            for cat in main_cats:
                all_categories[cat.code] = cat

            # Parse subcategories for each main category
            subcats_data = data.get("subcategories", {})
            for parent_code, subs in subcats_data.items():
                if not isinstance(subs, list):
                    continue  # Skip malformed entries

                sub_list = []
                for sub_data in subs:
                    if not isinstance(sub_data, dict):
                        continue

                    tags = tuple(sub_data.get("tags", []))
                    sub_info = CategoryInfo(
                        name=sub_data["name"],
                        code=sub_data["code"],
                        tags=tags,
                        parent_code=parent_code,
                    )
                    sub_list.append(sub_info)
                    all_categories[sub_info.code] = sub_info

                    # Map tags to category code
                    for tag in tags:
                        tag_to_category[tag] = sub_info.code

                subcategories[parent_code] = tuple(sub_list)

            # Create immutable hierarchy
            self._hierarchy = CategoryHierarchy(
                main_categories=tuple(main_cats),
                subcategories=subcategories,
                all_categories=all_categories,
                tag_to_category=tag_to_category,
            )

            logger.info(f"Loaded {len(all_categories)} finance categories from {self.config_path}")

        except FileNotFoundError:
            logger.error(f"Finance categories file not found: {self.config_path}")
            # Create empty hierarchy
            self._hierarchy = CategoryHierarchy(
                main_categories=(), subcategories={}, all_categories={}, tag_to_category={}
            )

        except Exception as e:
            logger.error(f"Failed to load finance categories: {e}")
            # Create empty hierarchy
            self._hierarchy = CategoryHierarchy(
                main_categories=(), subcategories={}, all_categories={}, tag_to_category={}
            )

    def get_hierarchy(self) -> CategoryHierarchy:
        """Get the loaded category hierarchy."""
        if self._hierarchy is None:
            self._load_categories()

        # _load_categories() guarantees _hierarchy is set
        assert self._hierarchy is not None
        return self._hierarchy

    def get_category(self, code: str) -> CategoryInfo | None:
        """
        Get category information by code.

        Args:
            code: Category code (e.g., 'food', 'PERSONAL', 'mortgage')

        Returns:
            CategoryInfo or None if not found
        """
        hierarchy = self.get_hierarchy()
        return hierarchy.all_categories.get(code)

    def get_category_by_tag(self, tag: str) -> CategoryInfo | None:
        """
        Find category by tag.

        Args:
            tag: Tag name (e.g., 'groceries', 'gas', 'hosting')

        Returns:
            CategoryInfo or None if tag not found
        """
        hierarchy = self.get_hierarchy()
        category_code = hierarchy.tag_to_category.get(tag)
        if category_code:
            return hierarchy.all_categories.get(category_code)
        return None

    def get_subcategories(self, parent_code: str) -> tuple[CategoryInfo, ...]:
        """
        Get all subcategories for a main category.

        Args:
            parent_code: Main category code (e.g., 'PERSONAL', 'HOUSE', 'SKUEL')

        Returns:
            Tuple of CategoryInfo objects
        """
        hierarchy = self.get_hierarchy()
        return hierarchy.subcategories.get(parent_code, ())

    def get_main_category_codes(self) -> list[str]:
        """Get list of main category codes."""
        hierarchy = self.get_hierarchy()
        return [cat.code for cat in hierarchy.main_categories]

    def get_all_category_codes(self) -> list[str]:
        """Get list of all category codes (main + subcategories)."""
        hierarchy = self.get_hierarchy()
        return list(hierarchy.all_categories.keys())

    def validate_category_code(self, code: str) -> bool:
        """Check if category code is valid."""
        hierarchy = self.get_hierarchy()
        return code in hierarchy.all_categories

    def suggest_category_from_description(self, description: str) -> str | None:
        """
        Suggest category based on expense description.

        Uses tag matching to find the best category.

        Args:
            description: Expense description (e.g., "Whole Foods groceries")

        Returns:
            Category code or None if no match
        """
        description_lower = description.lower()
        hierarchy = self.get_hierarchy()

        # Check tags for matches
        for tag, category_code in hierarchy.tag_to_category.items():
            if tag in description_lower:
                return category_code

        return None

    def get_category_path(self, code: str) -> str | None:
        """
        Get full category path (e.g., "PERSONAL.food" or "HOUSE.mortgage").

        Args:
            code: Category code

        Returns:
            Full path string or None if not found
        """
        category = self.get_category(code)
        if not category:
            return None

        if category.parent_code:
            return f"{category.parent_code}.{category.code}"
        else:
            return category.code


# ============================================================================
# Module-level convenience functions
# ============================================================================


@lru_cache(maxsize=1)
def get_categories_loader() -> FinanceCategoriesLoader:
    """
    Get singleton categories loader instance.

    Cached to ensure only one instance exists.
    """
    return FinanceCategoriesLoader()


def load_finance_categories() -> CategoryHierarchy:
    """
    Load finance categories from YAML config.

    This is the primary public API for loading categories.

    Returns:
        CategoryHierarchy with all loaded categories,

    Example:
        from core.utils.finance_categories import load_finance_categories

        categories = load_finance_categories()

        # Get main categories
        for cat in categories.main_categories:
            print(f"{cat.code}: {cat.name}")

        # Get subcategories
        personal_subs = categories.subcategories.get('PERSONAL', ())
        for sub in personal_subs:
            print(f"  {sub.code}: {sub.name} - {sub.tags}")
    """
    loader = get_categories_loader()
    return loader.get_hierarchy()


def get_category(code: str) -> CategoryInfo | None:
    """
    Get category by code.

    Convenience wrapper around loader.get_category().
    """
    loader = get_categories_loader()
    return loader.get_category(code)


def validate_category(code: str) -> bool:
    """
    Check if category code is valid.

    Convenience wrapper around loader.validate_category_code().
    """
    loader = get_categories_loader()
    return loader.validate_category_code(code)


def suggest_category(description: str) -> str | None:
    """
    Suggest category based on expense description.

    Convenience wrapper around loader.suggest_category_from_description().
    """
    loader = get_categories_loader()
    return loader.suggest_category_from_description(description)
