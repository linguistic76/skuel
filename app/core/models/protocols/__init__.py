"""
Model Protocols for SKUEL's Type System
========================================

Explicit protocols for SKUEL's three-tier architecture:
- Tier 1: Pydantic (External validation)
- Tier 2: DTOs (Mutable transfer) - DTOConvertible, DTOProtocol
- Tier 3: Domain Models (Immutable core) - DomainModelConvertible, DomainModelProtocol

These protocols formalize the implicit conventions used across all 16 DTOs
and 13 domain models in the codebase.

Protocol Types:
- Conversion protocols (conversion_protocols.py): Used in service layer for conversions
- Domain model protocol (domain_model_protocol.py): Used in generic backends for type safety
- Knowledge carrier protocol (knowledge_carrier_protocol.py): Unified knowledge integration
"""

from .conversion_protocols import DomainModelConvertible, DTOConvertible
from .domain_model_protocol import (
    DomainModelClassProtocol,
    DomainModelProtocol,
    DTOProtocol,
)
from .knowledge_carrier_protocol import (
    ActivityCarrier,
    CurriculumCarrier,
    KnowledgeCarrier,
)

__all__ = [
    # Conversion protocols
    "DTOConvertible",
    "DTOProtocol",
    "DomainModelClassProtocol",
    "DomainModelConvertible",
    "DomainModelProtocol",
    # Knowledge carrier protocols
    "ActivityCarrier",
    "CurriculumCarrier",
    "KnowledgeCarrier",
]
