"""
Life Path Enums - Vision Theme Classification
===============================================

Enums for life path vision capture and theme categorization.
"""

from enum import StrEnum


class ThemeCategory(StrEnum):
    """
    Categories for extracted vision themes.

    Maps to SKUEL's domain structure for LP recommendation
    during the vision capture flow.
    """

    PERSONAL_GROWTH = "personal_growth"
    CAREER = "career"
    HEALTH = "health"
    RELATIONSHIPS = "relationships"
    FINANCIAL = "financial"
    CREATIVE = "creative"
    SPIRITUAL = "spiritual"
    INTELLECTUAL = "intellectual"
    IMPACT = "impact"
    LIFESTYLE = "lifestyle"
