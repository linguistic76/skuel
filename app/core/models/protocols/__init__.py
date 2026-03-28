"""
Model Protocols for SKUEL's Type System
========================================

Explicit protocols for SKUEL's three-tier architecture:
- Tier 1: Pydantic (External validation)
- Tier 2: DTOs (Mutable transfer) - DTOConvertible, DTOProtocol
- Tier 3: Domain Models (Immutable core) - DomainModelConvertible, DomainModelProtocol

Protocol Types:
- Conversion protocols (conversion_protocols.py): Used in service layer for conversions
- Domain model protocol (domain_model_protocol.py): Used in generic backends for type safety
"""

from .conversion_protocols import DomainModelConvertible, DTOConvertible
from .domain_model_protocol import (
    DomainModelClassProtocol,
    DomainModelProtocol,
    DTOProtocol,
)

__all__ = [
    "DTOConvertible",
    "DTOProtocol",
    "DomainModelClassProtocol",
    "DomainModelConvertible",
    "DomainModelProtocol",
]
