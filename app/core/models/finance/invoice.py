"""
Invoice Domain Models
=====================

Three-tier architecture for Invoice entity within Finance domain:
- Tier 1: Request models (Pydantic) for API validation
- Tier 2: DTOs for data transfer between layers
- Tier 3: Pure models for domain logic

Invoices support both:
- Outgoing: Sent to clients (income)
- Incoming: Received from vendors (bills)
"""

from __future__ import annotations

__version__ = "1.0"

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

# ============================================================================
# DOMAIN ENUMS
# ============================================================================


class InvoiceType(str, Enum):
    """Invoice direction type."""

    OUTGOING = "outgoing"  # Sent to clients (income)
    INCOMING = "incoming"  # Received from vendors (bills)


class InvoiceStatus(str, Enum):
    """Invoice lifecycle status."""

    DRAFT = "draft"
    SENT = "sent"  # Outgoing only
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


# ============================================================================
# LINE ITEM (Embedded Value Object)
# ============================================================================


@dataclass(frozen=True)
class LineItem:
    """
    Immutable line item within an invoice.

    Represents a single billable item with quantity and unit price.
    """

    description: str
    quantity: float
    unit_price: float

    @property
    def amount(self) -> float:
        """Calculate line item total."""
        return self.quantity * self.unit_price

    def to_dict(self) -> dict[str, Any]:
        """Serialize line item to dictionary."""
        return {
            "description": self.description,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "amount": self.amount,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LineItem:
        """Create line item from dictionary."""
        return cls(
            description=data["description"],
            quantity=float(data["quantity"]),
            unit_price=float(data["unit_price"]),
        )


# ============================================================================
# TIER 1: REQUEST MODELS (Pydantic)
# ============================================================================


class LineItemInput(BaseModel):
    """Line item input for invoice creation."""

    description: str = Field(..., min_length=1, max_length=500)
    quantity: float = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)


class InvoiceCreateRequest(BaseModel):
    """Request model for creating a new invoice."""

    invoice_type: Literal["outgoing", "incoming"]
    counterparty: str = Field(..., min_length=1, max_length=200)
    invoice_date: date
    due_date: date | None = None
    items: list[LineItemInput] = Field(..., min_length=1)
    notes: str | None = Field(None, max_length=2000)


class InvoiceUpdateRequest(BaseModel):
    """Request model for updating an invoice."""

    counterparty: str | None = Field(None, min_length=1, max_length=200)
    due_date: date | None = None
    items: list[LineItemInput] | None = None
    notes: str | None = Field(None, max_length=2000)
    status: Literal["draft", "sent", "pending", "paid", "overdue", "cancelled"] | None = None


# ============================================================================
# TIER 2: DTO (Mutable Transfer Object)
# ============================================================================


@dataclass
class InvoiceDTO:
    """
    Mutable data transfer object for Invoice.

    Used for database operations and layer transitions.
    """

    uid: str
    user_uid: str
    invoice_type: str
    counterparty: str
    invoice_date: date
    items: list[dict[str, Any]]
    status: str = "draft"
    due_date: date | None = None
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def subtotal(self) -> float:
        """Calculate subtotal from items."""
        return sum(
            float(item.get("quantity", 0)) * float(item.get("unit_price", 0)) for item in self.items
        )

    @property
    def total(self) -> float:
        """Calculate total (subtotal for now, no tax)."""
        return self.subtotal

    def to_dict(self) -> dict[str, Any]:
        """Serialize DTO to dictionary for database storage."""
        return {
            "uid": self.uid,
            "user_uid": self.user_uid,
            "invoice_type": self.invoice_type,
            "counterparty": self.counterparty,
            "invoice_date": self.invoice_date.isoformat() if self.invoice_date else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "items": self.items,
            "status": self.status,
            "notes": self.notes,
            "subtotal": self.subtotal,
            "total": self.total,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InvoiceDTO:
        """Create DTO from dictionary."""
        invoice_date = data.get("invoice_date")
        if isinstance(invoice_date, str):
            invoice_date = date.fromisoformat(invoice_date)

        due_date = data.get("due_date")
        if isinstance(due_date, str):
            due_date = date.fromisoformat(due_date)

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        return cls(
            uid=data["uid"],
            user_uid=data["user_uid"],
            invoice_type=data["invoice_type"],
            counterparty=data["counterparty"],
            invoice_date=invoice_date,
            due_date=due_date,
            items=data.get("items", []),
            status=data.get("status", "draft"),
            notes=data.get("notes"),
            created_at=created_at,
            updated_at=updated_at,
        )


# ============================================================================
# TIER 3: PURE MODEL (Frozen Domain Entity)
# ============================================================================


@dataclass(frozen=True)
class InvoicePure:
    """
    Pure immutable invoice domain model.

    Represents an invoice with embedded line items.
    All fields are immutable - use factory methods to create modified copies.
    """

    # Identity
    uid: str
    user_uid: str

    # Invoice data
    invoice_type: InvoiceType
    counterparty: str
    invoice_date: date
    items: tuple[LineItem, ...] = field(default_factory=tuple)
    status: InvoiceStatus = InvoiceStatus.DRAFT
    due_date: date | None = None
    notes: str | None = None

    # Timestamps
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        """Handle mutable defaults for frozen dataclass."""
        if self.items is None:
            object.__setattr__(self, "items", ())

    @property
    def subtotal(self) -> float:
        """Calculate subtotal from line items."""
        return sum(item.amount for item in self.items)

    @property
    def total(self) -> float:
        """Calculate total (subtotal for now, no tax)."""
        return self.subtotal

    @property
    def item_count(self) -> int:
        """Number of line items."""
        return len(self.items)

    def is_overdue(self) -> bool:
        """Check if invoice is past due date."""
        if not self.due_date:
            return False
        return date.today() > self.due_date and self.status not in (
            InvoiceStatus.PAID,
            InvoiceStatus.CANCELLED,
        )

    def is_outgoing(self) -> bool:
        """Check if this is an outgoing invoice (to client)."""
        return self.invoice_type == InvoiceType.OUTGOING

    def is_incoming(self) -> bool:
        """Check if this is an incoming invoice (from vendor)."""
        return self.invoice_type == InvoiceType.INCOMING

    def days_until_due(self) -> int | None:
        """Days remaining until due date."""
        if not self.due_date:
            return None
        delta = self.due_date - date.today()
        return delta.days

    def with_status(self, new_status: InvoiceStatus) -> InvoicePure:
        """Create a copy with updated status."""
        return InvoicePure(
            uid=self.uid,
            user_uid=self.user_uid,
            invoice_type=self.invoice_type,
            counterparty=self.counterparty,
            invoice_date=self.invoice_date,
            items=self.items,
            status=new_status,
            due_date=self.due_date,
            notes=self.notes,
            created_at=self.created_at,
            updated_at=datetime.now(),
        )

    @classmethod
    def from_dto(cls, dto: InvoiceDTO) -> InvoicePure:
        """Create pure model from DTO."""
        items = tuple(LineItem.from_dict(item) for item in dto.items)

        invoice_type = (
            InvoiceType(dto.invoice_type) if isinstance(dto.invoice_type, str) else dto.invoice_type
        )

        status = InvoiceStatus(dto.status) if isinstance(dto.status, str) else dto.status

        return cls(
            uid=dto.uid,
            user_uid=dto.user_uid,
            invoice_type=invoice_type,
            counterparty=dto.counterparty,
            invoice_date=dto.invoice_date,
            items=items,
            status=status,
            due_date=dto.due_date,
            notes=dto.notes,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )

    def to_dto(self) -> InvoiceDTO:
        """Convert pure model to DTO."""
        return InvoiceDTO(
            uid=self.uid,
            user_uid=self.user_uid,
            invoice_type=self.invoice_type.value,
            counterparty=self.counterparty,
            invoice_date=self.invoice_date,
            items=[item.to_dict() for item in self.items],
            status=self.status.value,
            due_date=self.due_date,
            notes=self.notes,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


# ============================================================================
# CONVERTER FUNCTIONS
# ============================================================================


def invoice_create_request_to_dto(
    request: InvoiceCreateRequest,
    user_uid: str,
) -> InvoiceDTO:
    """Convert create request to DTO with generated UID."""
    items = [
        {
            "description": item.description,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
        }
        for item in request.items
    ]

    return InvoiceDTO(
        uid=f"invoice:{uuid.uuid4()}",
        user_uid=user_uid,
        invoice_type=request.invoice_type,
        counterparty=request.counterparty,
        invoice_date=request.invoice_date,
        due_date=request.due_date,
        items=items,
        status="draft",
        notes=request.notes,
        created_at=datetime.now(),
        updated_at=None,
    )


def invoice_update_request_to_dto(
    request: InvoiceUpdateRequest,
    existing: InvoiceDTO,
) -> InvoiceDTO:
    """Apply update request to existing DTO."""
    if request.counterparty is not None:
        existing.counterparty = request.counterparty

    if request.due_date is not None:
        existing.due_date = request.due_date

    if request.items is not None:
        existing.items = [
            {
                "description": item.description,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
            }
            for item in request.items
        ]

    if request.notes is not None:
        existing.notes = request.notes

    if request.status is not None:
        existing.status = request.status

    existing.updated_at = datetime.now()

    return existing


def invoice_dto_to_pure(dto: InvoiceDTO) -> InvoicePure:
    """Convert DTO to pure model."""
    return InvoicePure.from_dto(dto)


def invoice_pure_to_dto(pure: InvoicePure) -> InvoiceDTO:
    """Convert pure model to DTO."""
    return pure.to_dto()


def invoice_dto_to_response(dto: InvoiceDTO) -> dict[str, Any]:
    """Convert DTO to API response format."""
    return {
        "uid": dto.uid,
        "user_uid": dto.user_uid,
        "invoice_type": dto.invoice_type,
        "counterparty": dto.counterparty,
        "invoice_date": dto.invoice_date.isoformat() if dto.invoice_date else None,
        "due_date": dto.due_date.isoformat() if dto.due_date else None,
        "items": dto.items,
        "item_count": len(dto.items),
        "subtotal": dto.subtotal,
        "total": dto.total,
        "status": dto.status,
        "notes": dto.notes,
        "is_overdue": (
            dto.due_date is not None
            and date.today() > dto.due_date
            and dto.status not in ("paid", "cancelled")
        ),
        "created_at": dto.created_at.isoformat() if dto.created_at else None,
        "updated_at": dto.updated_at.isoformat() if dto.updated_at else None,
    }


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def create_invoice(
    user_uid: str,
    invoice_type: InvoiceType | str,
    counterparty: str,
    invoice_date: date,
    items: list[LineItem] | list[dict[str, Any]],
    due_date: date | None = None,
    notes: str | None = None,
    status: InvoiceStatus = InvoiceStatus.DRAFT,
) -> InvoicePure:
    """
    Factory function to create an invoice.

    Args:
        user_uid: Owner user UID
        invoice_type: Outgoing (to client) or incoming (from vendor)
        counterparty: Client or vendor name
        invoice_date: Date of invoice
        items: Line items (as LineItem objects or dicts)
        due_date: Optional payment due date
        notes: Optional notes
        status: Initial status (default: DRAFT)

    Returns:
        New InvoicePure instance
    """
    # Convert invoice type
    if isinstance(invoice_type, str):
        invoice_type = InvoiceType(invoice_type)

    # Convert items to LineItem objects
    line_items: list[LineItem] = []
    for item in items:
        if isinstance(item, LineItem):
            line_items.append(item)
        elif isinstance(item, dict):
            line_items.append(LineItem.from_dict(item))
        else:
            raise ValueError(f"Invalid item type: {type(item)}")

    return InvoicePure(
        uid=f"invoice:{uuid.uuid4()}",
        user_uid=user_uid,
        invoice_type=invoice_type,
        counterparty=counterparty,
        invoice_date=invoice_date,
        items=tuple(line_items),
        status=status,
        due_date=due_date,
        notes=notes,
        created_at=datetime.now(),
        updated_at=None,
    )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "InvoiceCreateRequest",
    # DTO (Tier 2)
    "InvoiceDTO",
    # Pure Model (Tier 3)
    "InvoicePure",
    "InvoiceStatus",
    # Enums
    "InvoiceType",
    "InvoiceUpdateRequest",
    # Value Objects
    "LineItem",
    # Request Models (Tier 1)
    "LineItemInput",
    # Factory
    "create_invoice",
    # Converters
    "invoice_create_request_to_dto",
    "invoice_dto_to_pure",
    "invoice_dto_to_response",
    "invoice_pure_to_dto",
    "invoice_update_request_to_dto",
]
