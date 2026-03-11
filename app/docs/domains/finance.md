---
title: Finance Domain
created: 2025-12-04
updated: 2026-01-17
status: current
category: domains
tags: [finance, domain, standalone, admin-only, bookkeeping]
---

# Finance Domain

*Last updated: 2026-01-17*

**Type:** Standalone Bookkeeping Domain (admin-only access)
**UID Prefix:** `expense:`, `budget:`
**Entity Labels:** `Expense`, `Budget`
**Access:** Admin-only (all routes require ADMIN role)

## Architecture Overview

**January 2026 Simplification:** Finance is a **standalone bookkeeping domain**. It does not use BaseService, BaseAnalyticsService, or unified relationship configuration. Finance focuses on fundamental bookkeeping: tracking expenses, creating budgets, and aligning budgets with actual expenses.

```
FinanceService (Standalone Facade)
    ├── FinanceCoreService      (CRUD operations)
    ├── FinanceBudgetService    (Budget management)
    ├── FinanceReportingService (Reports & summaries)
    └── FinanceInvoiceService   (Invoice operations, optional)
```

**Key Characteristics:**
- **No cross-domain intelligence** - Finance does not relate to other domains
- **No relationship configuration** - No `EXPENSE_CONFIG` or unified registry entry
- **No BaseService inheritance** - FinanceCoreService is standalone
- **No intelligence service** - Removed in January 2026 simplification
- **Simple bookkeeping focus** - Expenses, budgets, and financial reporting

## Security Model

**All Finance routes require ADMIN role.** This is enforced at the route level:

```python
# API routes use @require_admin decorator
@rt("/api/expenses")
@require_admin(get_user_service)
async def list_expenses(request, current_user):
    # Admin sees ALL finance data (no ownership checks)
    ...
```

**Why admin-only?**
- Finance data is sensitive
- Simplifies development (no multi-tenant complexity)
- Admin can see all users' expenses for oversight

## Event-Driven Architecture

FinanceCoreService publishes domain events on all state changes:

| Event | Trigger |
|-------|---------|
| `ExpenseCreated` | New expense created |
| `ExpenseUpdated` | Expense fields updated |
| `ExpensePaid` | Status changed to PAID |
| `ExpenseDeleted` | Expense deleted |

```python
# Event publishing example (from FinanceCoreService)
if result.is_ok and self.event_bus:
    event = ExpenseCreated(
        expense_uid=expense.uid,
        user_uid=expense.user_uid,
        amount=expense.amount,
        ...
    )
    await self.event_bus.publish_async(event)
```

## Key Files

| Component | Location |
|-----------|----------|
| **Models** |
| Expense Domain Model | `/core/models/finance/finance_pure.py` |
| Expense DTO | `/core/models/finance/finance_dto.py` |
| Request Models | `/core/models/finance/finance_request.py` |
| Converters | `/core/models/finance/finance_converters.py` |
| **Services** |
| Facade Service | `/core/services/finance_service.py` |
| Core Service (CRUD) | `/core/services/finance/finance_core_service.py` |
| Budget Service | `/core/services/finance/finance_budget_service.py` |
| Reporting Service | `/core/services/finance/finance_reporting_service.py` |
| **Routes** |
| Route Factory | `/adapters/inbound/finance_routes.py` |
| API Routes | `/adapters/inbound/finance_api.py` |
| UI Routes | `/adapters/inbound/finance_ui.py` |
| **Events** |
| Finance Events | `/core/events/finance_events.py` |
| **Tests** |
| Integration Tests | `/tests/integration/test_finance_core_operations.py` |

## Model Fields (ExpensePure)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `uid` | `str` | Yes | Unique identifier (e.g., `expense.coffee`) |
| `user_uid` | `str` | Yes | Owner user UID |
| `amount` | `float` | Yes | Expense amount (must be > 0) |
| `currency` | `str` | Yes | Currency code (default: USD) |
| `description` | `str` | Yes | Expense description |
| `expense_date` | `date` | Yes | When expense occurred |
| `category` | `ExpenseCategory` | Yes | PERSONAL, 2222, SKUEL |
| `subcategory` | `str?` | No | Sub-category within category |
| `status` | `ExpenseStatus` | Yes | PENDING, PAID, CANCELLED, etc. |
| `payment_method` | `PaymentMethod` | No | CASH, CREDIT_CARD, DEBIT_CARD, etc. |
| `vendor` | `str?` | No | Merchant/vendor name |
| `receipt_url` | `str?` | No | URL/path to receipt |
| `tax_deductible` | `bool` | No | Tax deductibility flag |
| `reimbursable` | `bool` | No | Reimbursement eligibility |
| `tax_amount` | `float` | No | Tax amount (default: 0.0) |
| `is_recurring` | `bool` | No | Whether this is a recurring expense |
| `recurrence_pattern` | `RecurrencePattern?` | No | Recurrence frequency |
| `budget_uid` | `str?` | No | Associated budget UID |
| `budget_category` | `str?` | No | Budget category |

## Validation Rules

FinanceCoreService enforces these business rules:

### Create Validation
- Amount must be positive (> 0)
- `user_uid` is REQUIRED (fail-fast validation)

### Update Validation
- Amount must be positive (if being updated)
- Amount increase cannot exceed 10x (data entry error prevention)
- Category cannot change after 30 days (accounting period locked)

```python
# Example validation
if expense.amount <= 0:
    return Result.fail(
        Errors.validation(
            message="Expense amount must be positive",
            field="amount",
            value=expense.amount,
        )
    )
```

## Categories

Finance uses a hierarchical category system with three top-level categories:

```
ExpenseCategory
├── PERSONAL
│   ├── food, dining, groceries
│   ├── transport, fuel, parking
│   ├── health, fitness, medical
│   ├── entertainment, streaming
│   └── ... (see EXPENSE_SUBCATEGORIES)
├── 2222 (Business)
│   ├── office, equipment
│   ├── marketing, advertising
│   ├── travel, conferences
│   └── ...
└── SKUEL (Project-specific)
    ├── infrastructure, hosting
    ├── tools, subscriptions
    ├── contractors
    └── ...
```

See [Finance Categories Guide](../architecture/FINANCE_CATEGORIES_GUIDE.md) for complete subcategory list.

## Budget Model (BudgetPure)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `uid` | `str` | Yes | Unique identifier |
| `user_uid` | `str` | Yes | Owner user UID |
| `name` | `str` | Yes | Budget name |
| `period` | `BudgetPeriod` | Yes | WEEKLY, MONTHLY, QUARTERLY, YEARLY |
| `amount_limit` | `float` | Yes | Budget limit |
| `currency` | `str` | Yes | Currency code |
| `start_date` | `date` | Yes | Budget start date |
| `end_date` | `date?` | No | Budget end date |
| `categories` | `list[ExpenseCategory]` | No | Categories covered |
| `amount_spent` | `float` | No | Current amount spent |
| `expense_count` | `int` | No | Number of expenses |
| `alert_threshold` | `float` | No | Alert threshold (default: 0.8) |
| `is_exceeded` | `bool` | No | Whether budget is exceeded |

## API Endpoints

All endpoints require ADMIN role:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/expenses` | List all expenses |
| POST | `/api/expenses` | Create expense |
| GET | `/api/expenses/{uid}` | Get expense by UID |
| PUT | `/api/expenses/{uid}` | Update expense |
| DELETE | `/api/expenses/{uid}` | Delete expense |
| GET | `/api/expenses/date-range` | Expenses in date range |
| GET | `/api/budgets` | List all budgets |
| POST | `/api/budgets` | Create budget |
| GET | `/finance` | Finance dashboard (UI) |

## Finance Domain Philosophy

Finance is intentionally **standalone** and **simple**:

1. **No Cross-Domain Intelligence** - Finance does not need to relate expenses to goals, knowledge, or other domains
2. **Pure Bookkeeping** - Track expenses, manage budgets, generate reports
3. **Admin-Only** - Simplifies security model (no ownership verification complexity)
4. **Event-Driven** - Publishes events for audit trail, but no event handlers that trigger cross-domain actions

**What Finance DOES NOT have:**
- Intelligence service (no AI-powered insights)
- Search service (admin queries expenses directly)
- Relationship configuration (no graph relationships to other domains)
- BaseService inheritance (standalone CRUD)
- Facade pattern (no sub-services — single FinanceService class)

**What Finance HAS:**
- Clean CRUD operations for expenses and budgets
- Business validation (amount limits, locked periods)
- Financial reporting and summaries
- Event publishing for audit trail

## Test Coverage

30 integration tests covering:
- CRUD operations (create, get, list, update, delete)
- Filtering (by status, category, payment method, date range)
- Validation (positive amounts, reasonable increases, locked periods)
- Event publishing (created, updated, paid, deleted events)

Run tests:
```bash
uv run pytest tests/integration/test_finance_core_operations.py -v
```

## See Also

- [Finance Categories Guide](../architecture/FINANCE_CATEGORIES_GUIDE.md)
- [Entity Type Architecture](../architecture/ENTITY_TYPE_ARCHITECTURE.md)
- [User Roles (ADR-018)](../decisions/ADR-018-user-roles-four-tier-system.md)
- [Event-Driven Architecture](../patterns/event_driven_architecture.md)
