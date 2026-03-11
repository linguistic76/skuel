"""
Choice Enums - Decision Type Classification
=============================================

Enums for choice/decision type classification.
"""

from enum import StrEnum


class ChoiceType(StrEnum):
    """
    Type of decision being made.

    Determines the decision framework and option evaluation approach.
    """

    BINARY = "binary"
    MULTIPLE = "multiple"
    RANKING = "ranking"
    ALLOCATION = "allocation"
    STRATEGIC = "strategic"
    OPERATIONAL = "operational"
