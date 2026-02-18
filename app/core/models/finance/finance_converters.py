"""
Finance Model Converters
========================

Conversion functions between the three tiers:
- Request (Pydantic) <-> DTO <-> Pure (Domain)
"""

import uuid
from datetime import datetime
from typing import Any

from .finance_dto import (
    BudgetDTO,
    BudgetPeriod,
    ExpenseCategory,
    ExpenseDTO,
    ExpenseStatus,
    PaymentMethod,
    RecurrencePattern,
)
from .finance_pure import BudgetPure, ExpensePure
from .finance_request import (
    BudgetCreateRequest,
    BudgetUpdateRequest,
    ExpenseCreateRequest,
    ExpenseUpdateRequest,
)

# ============================================================================
# EXPENSE CONVERTERS
# ============================================================================


def expense_create_request_to_dto(
    request: ExpenseCreateRequest, user_uid: str | None = None
) -> ExpenseDTO:
    """Convert ExpenseCreateRequest to ExpenseDTO"""
    return ExpenseDTO(
        uid=str(uuid.uuid4()),  # Generate new UID
        amount=request.amount,
        currency=request.currency,
        description=request.description,
        expense_date=request.expense_date,
        category=ExpenseCategory(request.category),
        subcategory=request.subcategory,
        payment_method=PaymentMethod(request.payment_method),
        vendor=request.vendor,
        status=ExpenseStatus.PENDING,
        tax_deductible=request.tax_deductible,
        reimbursable=request.reimbursable,
        tax_amount=request.tax_amount,
        receipt_url=request.receipt_url,
        notes=request.notes,
        tags=request.tags,
        is_recurring=request.is_recurring,
        recurrence_pattern=RecurrencePattern(request.recurrence_pattern)
        if request.recurrence_pattern
        else None,
        recurrence_end_date=request.recurrence_end_date,
        budget_uid=request.budget_uid,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        created_by=user_uid,
    )


def expense_update_request_to_dto(
    request: ExpenseUpdateRequest, existing: ExpenseDTO
) -> ExpenseDTO:
    """Apply ExpenseUpdateRequest to existing ExpenseDTO"""
    # Update only provided fields
    if request.amount is not None:
        existing.amount = request.amount
    if request.description is not None:
        existing.description = request.description
    if request.expense_date is not None:
        existing.expense_date = request.expense_date
    if request.category is not None:
        existing.category = ExpenseCategory(request.category)
    if request.subcategory is not None:
        existing.subcategory = request.subcategory
    if request.payment_method is not None:
        existing.payment_method = PaymentMethod(request.payment_method)
    if request.vendor is not None:
        existing.vendor = request.vendor
    if request.status is not None:
        existing.status = ExpenseStatus(request.status)
    if request.tax_deductible is not None:
        existing.tax_deductible = request.tax_deductible
    if request.reimbursable is not None:
        existing.reimbursable = request.reimbursable
    if request.tax_amount is not None:
        existing.tax_amount = request.tax_amount
    if request.receipt_url is not None:
        existing.receipt_url = request.receipt_url
    if request.notes is not None:
        existing.notes = request.notes
    if request.tags is not None:
        existing.tags = request.tags
    if request.budget_uid is not None:
        existing.budget_uid = request.budget_uid

    existing.updated_at = datetime.now()
    return existing


def expense_dto_to_pure(dto: ExpenseDTO) -> ExpensePure:
    """Convert ExpenseDTO to ExpensePure"""
    return ExpensePure(
        uid=dto.uid,
        user_uid=dto.created_by or "",  # ExpenseDTO has created_by, not user_uid
        amount=dto.amount,
        currency=dto.currency,
        description=dto.description,
        expense_date=dto.expense_date,
        category=dto.category,
        subcategory=dto.subcategory,
        payment_method=dto.payment_method,
        account_uid=dto.account_uid,
        vendor=dto.vendor,
        status=dto.status,
        tax_deductible=dto.tax_deductible,
        reimbursable=dto.reimbursable,
        tax_amount=dto.tax_amount,
        receipt_url=dto.receipt_url,
        notes=dto.notes,
        is_recurring=dto.is_recurring,
        recurrence_pattern=dto.recurrence_pattern,
        recurrence_end_date=dto.recurrence_end_date,
        parent_expense_uid=dto.parent_expense_uid,
        budget_uid=dto.budget_uid,
        budget_category=dto.budget_category,
        tags=dto.tags.copy() if dto.tags else [],
        metadata=dto.metadata.copy() if dto.metadata else {},
        created_at=dto.created_at,
        updated_at=dto.updated_at,
        created_by=dto.created_by,
    )


def expense_pure_to_dto(pure: ExpensePure) -> ExpenseDTO:
    """Convert ExpensePure to ExpenseDTO"""
    return ExpenseDTO(
        uid=pure.uid,
        amount=pure.amount,
        currency=pure.currency,
        description=pure.description,
        expense_date=pure.expense_date,
        category=pure.category,
        subcategory=pure.subcategory,
        payment_method=pure.payment_method,
        account_uid=pure.account_uid,
        vendor=pure.vendor,
        status=pure.status,
        tax_deductible=pure.tax_deductible,
        reimbursable=pure.reimbursable,
        tax_amount=pure.tax_amount,
        receipt_url=pure.receipt_url,
        notes=pure.notes,
        is_recurring=pure.is_recurring,
        recurrence_pattern=pure.recurrence_pattern,
        recurrence_end_date=pure.recurrence_end_date,
        parent_expense_uid=pure.parent_expense_uid,
        budget_uid=pure.budget_uid,
        budget_category=pure.budget_category,
        tags=pure.tags.copy() if pure.tags else [],
        metadata=pure.metadata.copy() if pure.metadata else {},
        created_at=pure.created_at,
        updated_at=pure.updated_at,
        created_by=pure.created_by,
    )


def expense_dto_to_response(dto: ExpenseDTO) -> dict[str, Any]:
    """Convert ExpenseDTO to API response format"""
    return {
        "uid": dto.uid,
        "amount": dto.amount,
        "currency": dto.currency,
        "description": dto.description,
        "expense_date": dto.expense_date.isoformat(),
        "category": dto.category.value,
        "subcategory": dto.subcategory,
        "payment_method": dto.payment_method.value,
        "vendor": dto.vendor,
        "status": dto.status.value,
        "tax_deductible": dto.tax_deductible,
        "reimbursable": dto.reimbursable,
        "tax_amount": dto.tax_amount,
        "total_amount": dto.amount + dto.tax_amount,
        "receipt_url": dto.receipt_url,
        "notes": dto.notes,
        "tags": dto.tags,
        "is_recurring": dto.is_recurring,
        "recurrence_pattern": dto.recurrence_pattern.value if dto.recurrence_pattern else None,
        "recurrence_end_date": dto.recurrence_end_date.isoformat()
        if dto.recurrence_end_date
        else None,
        "budget_uid": dto.budget_uid,
        "is_business_expense": dto.category in [ExpenseCategory.TWO222, ExpenseCategory.SKUEL]
        or dto.tax_deductible,
        "is_recent": (datetime.now().date() - dto.expense_date).days <= 30,
        "is_future": dto.expense_date > datetime.now().date(),
        "created_at": dto.created_at.isoformat(),
        "updated_at": dto.updated_at.isoformat(),
        "created_by": dto.created_by,
    }


# ============================================================================
# BUDGET CONVERTERS
# ============================================================================


def budget_create_request_to_dto(
    request: BudgetCreateRequest, _user_uid: str | None = None
) -> BudgetDTO:
    """Convert BudgetCreateRequest to BudgetDTO"""
    return BudgetDTO(
        uid=str(uuid.uuid4()),
        name=request.name,
        period=BudgetPeriod(request.period),
        amount_limit=request.amount_limit,
        currency=request.currency,
        start_date=request.start_date,
        end_date=request.end_date,
        categories=[ExpenseCategory(cat) for cat in request.categories],
        amount_spent=0.0,
        expense_count=0,
        alert_threshold=request.alert_threshold,
        is_exceeded=False,
        notes=request.notes,
        tags=request.tags,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def budget_update_request_to_dto(request: BudgetUpdateRequest, existing: BudgetDTO) -> BudgetDTO:
    """Apply BudgetUpdateRequest to existing BudgetDTO"""
    if request.name is not None:
        existing.name = request.name
    if request.amount_limit is not None:
        existing.amount_limit = request.amount_limit
        existing.is_exceeded = existing.amount_spent > request.amount_limit
    if request.end_date is not None:
        existing.end_date = request.end_date
    if request.categories is not None:
        existing.categories = [ExpenseCategory(cat) for cat in request.categories]
    if request.alert_threshold is not None:
        existing.alert_threshold = request.alert_threshold
    if request.notes is not None:
        existing.notes = request.notes
    if request.tags is not None:
        existing.tags = request.tags

    existing.updated_at = datetime.now()
    return existing


def budget_dto_to_pure(dto: BudgetDTO) -> BudgetPure:
    """
    Convert BudgetDTO to BudgetPure.

    NOTE: BudgetDTO is missing user_uid field.
    TODO [CLEANUP]: Add user_uid field to BudgetDTO (should come from service layer context)
    """
    return BudgetPure(
        uid=dto.uid,
        user_uid="",  # BudgetDTO missing user_uid - service layer must provide it
        name=dto.name,
        period=dto.period,
        amount_limit=dto.amount_limit,
        currency=dto.currency,
        start_date=dto.start_date,
        end_date=dto.end_date,
        categories=dto.categories.copy() if dto.categories else [],
        amount_spent=dto.amount_spent,
        expense_count=dto.expense_count,
        alert_threshold=dto.alert_threshold,
        is_exceeded=dto.is_exceeded,
        notes=dto.notes,
        tags=dto.tags.copy() if dto.tags else [],
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def budget_pure_to_dto(pure: BudgetPure) -> BudgetDTO:
    """Convert BudgetPure to BudgetDTO"""
    return BudgetDTO(
        uid=pure.uid,
        name=pure.name,
        period=pure.period,
        amount_limit=pure.amount_limit,
        currency=pure.currency,
        start_date=pure.start_date,
        end_date=pure.end_date,
        categories=pure.categories.copy() if pure.categories else [],
        amount_spent=pure.amount_spent,
        expense_count=pure.expense_count,
        alert_threshold=pure.alert_threshold,
        is_exceeded=pure.is_exceeded,
        notes=pure.notes,
        tags=pure.tags.copy() if pure.tags else [],
        created_at=pure.created_at,
        updated_at=pure.updated_at,
    )


def budget_dto_to_response(dto: BudgetDTO) -> dict[str, Any]:
    """Convert BudgetDTO to API response format"""
    utilization = (dto.amount_spent / dto.amount_limit * 100) if dto.amount_limit > 0 else 0

    return {
        "uid": dto.uid,
        "name": dto.name,
        "period": dto.period.value,
        "amount_limit": dto.amount_limit,
        "currency": dto.currency,
        "start_date": dto.start_date.isoformat(),
        "end_date": dto.end_date.isoformat() if dto.end_date else None,
        "categories": [cat.value for cat in dto.categories],
        "amount_spent": dto.amount_spent,
        "amount_remaining": max(0, dto.amount_limit - dto.amount_spent),
        "expense_count": dto.expense_count,
        "alert_threshold": dto.alert_threshold,
        "is_exceeded": dto.is_exceeded,
        "is_near_limit": utilization >= (dto.alert_threshold * 100),
        "utilization_percentage": utilization,
        "notes": dto.notes,
        "tags": dto.tags,
        "created_at": dto.created_at.isoformat(),
        "updated_at": dto.updated_at.isoformat(),
    }
