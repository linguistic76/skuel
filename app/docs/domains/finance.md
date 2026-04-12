---
title: Finance Domain
created: 2025-12-04
updated: 2026-04-12
status: current
category: domains
tags: [finance, firefly, invoicing, admin-only, adr-052]
---

# Finance Domain

*Last updated: 2026-04-12*

**Type:** Admin-only hybrid — expense/budget/reporting delegated to [Firefly III](https://www.firefly-iii.org/); invoicing remains local.
**Access:** All routes require the `ADMIN` role.

## The Split (ADR-052)

Finance is deliberately split across two worlds. The split is the point — do not reunify it.

| Concern | Where it lives | Why |
|---------|---------------|-----|
| **Expenses, budgets, categories, reporting, insights** | [Firefly III](https://docs.firefly-iii.org/) — Docker sidecar at `http://firefly:8080` | Mature, maintained, AGPL. SKUEL's Leverage Maintained Software principle. |
| **Invoices (A/R, customer-facing PDFs)** | Local: `core/services/finance/finance_invoice_service.py` + `adapters/outbound/invoice_renderer.py` (WeasyPrint) | Firefly III has no invoicing. SKUEL keeps it for future non-Stripe billing. |

**See:** [ADR-052: Firefly III Finance Integration](../decisions/ADR-052-firefly-iii-finance-integration.md)

---

## Firefly III — Expenses, Budgets, Reporting

### Two Books, One Instance

One Firefly III instance, two user accounts: `mike-personal@…` and `mike-skuel@…`. Each has its own Personal Access Token stored in `.env`:

```bash
FIREFLY_BASE_URL=http://firefly:8080
FIREFLY_PAT_PERSONAL=<token from the personal Firefly user>
FIREFLY_PAT_SKUEL=<token from the SKUEL business Firefly user>
```

SKUEL's finance hub shows two tabs — Personal / SKUEL — each hitting a different PAT. Firefly's "multiple administrations" feature is WIP; two users is the shipped workaround.

### How SKUEL Talks To Firefly

```
finance_ui.py
    ↓
firefly_expense_service (thin read facade, returns TypedDict contexts)
    ↓
FireflyOperations  (protocol — core/ports/finance_protocols.py)
    ↓
FireflyClient  (adapter — adapters/outbound/firefly_client.py, httpx)
    ↓
Firefly III REST API
```

The `FireflyOperations` Protocol is the hexagonal seam. Nothing outside `firefly_client.py` knows Firefly's wire format. Services/UI consume strongly-typed TypedDicts (`FireflyTransaction`, `FireflyBudget`, `FireflyCategory`, `FireflyAccountBalance`).

### Stripe → Firefly Sync

Stripe webhooks flow through SKUEL to record SaaS revenue in the SKUEL Firefly book:

```
Stripe (charge.succeeded, payout.paid, invoice.payment_succeeded)
    ↓
POST /webhooks/stripe  (signature verified via stripe SDK)
    ↓
stripe_firefly_sync_service.handle_*(event)
    ↓
firefly_client.create_transaction(book="skuel", external_id=event.id, ...)
```

`external_id = Stripe event ID` makes the sync idempotent — replaying a webhook never creates duplicates. SKUEL also publishes a `StripePaymentRecorded` event after a successful Firefly POST so the audit trail lives in the SKUEL event bus.

### Firefly Docs — Read These For Anything Non-Trivial

SKUEL does not re-document Firefly. When you need to understand a behavior, start here:

- **User guide:** <https://docs.firefly-iii.org/>
- **REST API reference:** <https://api-docs.firefly-iii.org/>
- **Rules engine:** <https://docs.firefly-iii.org/references/firefly-iii/rules/>
- **Budgets:** <https://docs.firefly-iii.org/how-to/firefly-iii/budgets/>
- **Data importer (CSV/bank):** <https://docs.firefly-iii.org/references/data-importer/>

### Running Firefly Locally

Firefly services are gated behind the `finance` Docker Compose profile so they don't start with the default `docker compose up`:

```bash
# First-time setup — generate the Laravel app key
printf "base64:%s\n" "$(head -c 32 /dev/urandom | base64)"
# Paste the output into FIREFLY_APP_KEY in .env (no inline comments — Docker
# Compose treats everything after = as the value).

# Bring up the Firefly stack
docker compose --profile finance up -d firefly-db firefly

# Create users + PATs in the Firefly web UI
open http://localhost:8081
# Register mike-personal@… and mike-skuel@…; for each user:
#   Profile → OAuth → Personal Access Tokens → Create New Token → copy once
```

### Security Model

All Finance UI and API routes require the `ADMIN` role — enforced at the route level via `@require_admin(get_user_service)`. Admin sees ALL finance data; there is no ownership filtering. Finance data is sensitive, and the admin-only constraint deliberately eliminates multi-tenant complexity.

---

## Local Invoice Module (Kept)

Invoices are not in Firefly. They live in SKUEL because:

1. Firefly III does not support invoicing, A/R, or customer entities.
2. SaaS user payments currently flow through **Stripe**, which issues its own invoices/receipts — so the SKUEL invoice module is **built but unused in production today**. It is preserved for future non-Stripe billing scenarios.

### Invoice Files

| Component | Location |
|-----------|----------|
| Domain model | `core/models/finance/invoice.py` |
| Service | `core/services/finance/finance_invoice_service.py` |
| PDF renderer | `adapters/outbound/invoice_renderer.py` (WeasyPrint) |
| UI views | `ui/finance/invoice_views.py` |
| API routes | invoice routes in `adapters/inbound/finance_api.py` |
| UI routes | invoice routes in `adapters/inbound/finance_ui.py` |

Invoice routes remain unchanged by ADR-052 — `/finance/invoices`, `/finance/invoices/new`, `/finance/invoices/{uid}` all work exactly as before, render via WeasyPrint, and persist to Neo4j.

---

## Key SKUEL Files

| Component | Location |
|-----------|----------|
| **Firefly adapter** | `adapters/outbound/firefly_client.py` |
| **Firefly protocol + DTOs** | `core/ports/finance_protocols.py` |
| **Firefly exceptions** | `core/utils/exception_types.py` (`FIREFLY_EXCEPTIONS` tuple) |
| **Firefly unit tests** | `tests/unit/test_firefly_client.py` (17 tests, mocked httpx) |
| **Docker stack** | `docker-compose.yml` (`finance` profile) |
| **Environment** | `.env.example` — `FIREFLY_*`, `STRIPE_WEBHOOK_SECRET` |
| **Invoice service** | `core/services/finance/finance_invoice_service.py` |
| **Invoice renderer** | `adapters/outbound/invoice_renderer.py` |
| **Invoice UI** | `ui/finance/invoice_views.py` |

---

## What Changed From The Legacy Finance Module

If you're reading older docs or commits, the finance domain used to have:

- `ExpensePure`, `BudgetPure` domain models (deleted in Phase 5)
- `FinanceCoreService`, `FinanceBudgetService`, `FinanceReportingService` (deleted in Phase 5)
- `FinanceCategoriesService` + `SEL_CATEGORIES` hierarchy (deleted — Firefly uses its own categories and tags)
- `ExpenseCreated`/`ExpenseUpdated`/`ExpensePaid`/`ExpenseDeleted` events (deleted)
- `Expense` and `Budget` Neo4j labels (dropped from the graph)

The now-legacy `docs/architecture/FINANCE_CATEGORIES_GUIDE.md` describes a category system that no longer exists — Firefly III's native categories + tags replace it. The guide is kept for archaeological purposes only; don't build against it.

**See also:**
- [ADR-052: Firefly III Finance Integration](../decisions/ADR-052-firefly-iii-finance-integration.md) — the decision and consequences
- [Leverage Maintained Software](/home/mike/.claude/projects/-home-mike-skuel-app/memory/) — the principle this change applies
