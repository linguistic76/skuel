"""
Ku Domain Enums
===============

Enums specific to the atomic Knowledge Unit (Ku) domain.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from enum import Enum


class KuCategory(str, Enum):
    """What kind of knowledge unit is this Ku?

    Categories classify the nature of the atomic knowledge:
    - STATE: Observable conditions (buzzing, calm, heightened_arousal)
    - CONCEPT: Abstract ideas (caffeine, attention, neuroplasticity)
    - PRINCIPLE: Guiding truths (truth_oriented_collaboration)
    - INTAKE: Consumables (coffee_consumption, food)
    - SUBSTANCE: Chemical/physical agents (caffeine, melatonin)
    - PRACTICE: Actionable methods (meditation, breathwork)
    - VALUE: Desired qualities (calmness, honesty, courage)
    """

    STATE = "state"
    CONCEPT = "concept"
    PRINCIPLE = "principle"
    INTAKE = "intake"
    SUBSTANCE = "substance"
    PRACTICE = "practice"
    VALUE = "value"
