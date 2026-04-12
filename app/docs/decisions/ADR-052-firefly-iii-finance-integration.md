---
adr: 052
title: Firefly III Replaces SKUEL Expense/Budget/Reporting
status: Accepted
date: 2026-04-12
deciders: Mike
tags:
  - finance
  - infrastructure
  - leverage-maintained-software
  - adapters
related:
  - ADR-044-neo4j-committed-architectural-choice
  - ADR-049-huggingface-embeddings-migration
---

# ADR-052: Firefly III Replaces SKUEL Expense/Budget/Reporting

## Status

Accepted — implementation in progress. Phases 1 + 2 (docker stack + REST client adapter) landed in commit `c3258630`. Phases 3–5 (Stripe sync, UI rewire, demolition of legacy code) pending.

---

## Context

SKUEL shipped a fully functional, admin-only finance module (~5,400 LOC across `core/models/finance/`, `core/services/finance/`, `adapters/inbound/finance_*`, `ui/finance/`) covering:

- Expense CRUD, categorization, payment-method enums
- Budgets with period tracking, utilization, alerts
- Reporting (monthly summaries, tax, category breakdown, health score)
- Invoice generation + WeasyPrint PDF rendering

Per CLAUDE.md's **Leverage Maintained Software** principle, every custom subsystem is a maintenance liability for a non-technical founder. [Firefly III](https://www.firefly-iii.org/) is an established, actively maintained (AGPL-v3, Laravel) self-hosted personal finance manager with:

- Comprehensive [REST API](https://api-docs.firefly-iii.org/) — transactions, budgets, categories, accounts, insights
- OAuth2 + Personal Access Token auth
- Multi-currency, rules, recurring transactions
- Companion Data Importer for CSV/bank feeds
- Docker deployment in minutes

**Two facts made the swap viable:**

1. SKUEL's invoice module is **built but unused today** — SaaS user payments flow through Stripe, which issues its own invoices/receipts. The invoice module is preserved for future non-Stripe billing scenarios.
2. Finance is **isolated** in SKUEL — no cross-domain relationships, no intelligence service, no ZPD/LifePath wiring. The replacement is a clean seam.

**Firefly III cannot replace:** invoicing, A/R, customer entities. That's why SKUEL keeps the invoice module locally.

## Decision

**Replace SKUEL's expense + budget + reporting modules with Firefly III. Keep the invoice module local.**

Firefly III runs as a Docker sidecar to SKUEL. Two Firefly user accounts live on one instance — one for Mike's personal finances, one for SKUEL business finances — each with its own Personal Access Token. (Firefly's "multiple administrations" feature is WIP; two users is the shipped workaround.) SKUEL's `/finance/` admin hub becomes a thin read-through facade: expense/budget/report pages fetch from Firefly REST; invoice pages remain local.

Stripe webhooks push payout/charge events into the SKUEL Firefly user account as revenue transactions, idempotent via Stripe event IDs.

### Scope — DELETE from SKUEL (Phase 5, pending)

| File / path | Approx LOC |
|---|---|
| `core/models/finance/finance_pure.py` (ExpensePure, BudgetPure) | 486 |
| `core/models/finance/finance_dto.py` (expense/budget halves) | 318 |
| `core/models/finance/finance_converters.py` (expense/budget halves) | ~200 |
| `core/services/finance/finance_core_service.py` | 495 |
| `core/services/finance/finance_budget_service.py` | 315 |
| `core/services/finance/finance_reporting_service.py` | 273 |
| `core/services/finance/finance_categories.py` | 348 |
| Expense/Budget backend code in `misc_backends.py` | ~200 |
| Expense/budget/report sections of `ui/finance/section_views.py` | ~500 |
| Expense/budget endpoints in `adapters/inbound/finance_api.py` | ~250 |
| Expense/budget tests | ~20 |

**Net delete: ~3,400 LOC.**

### Scope — KEEP

- `core/models/finance/invoice.py` (InvoicePure + line items)
- `core/services/finance/finance_invoice_service.py`
- `adapters/outbound/invoice_renderer.py` (WeasyPrint PDF)
- `ui/finance/invoice_views.py`, invoice API routes
- `FinanceService` facade — slimmed to invoice-only delegation

### Scope — CREATE

| File | Purpose |
|---|---|
| `adapters/outbound/firefly_client.py` | **Done (Phase 2).** Async httpx-backed FireflyClient implementing `FireflyOperations`. |
| `core/ports/finance_protocols.py` | **Done (Phase 2).** `FireflyOperations` protocol + 7 TypedDicts. |
| `core/services/finance/firefly_expense_service.py` | **Pending (Phase 4).** Thin read-facade returning existing `FinanceDashboardContext` / `FinanceBudgetsContext` TypedDicts, backed by `firefly_client`. |
| `core/services/finance/stripe_firefly_sync_service.py` | **Pending (Phase 3).** Stripe webhook handler → Firefly revenue transactions. |
| `adapters/inbound/stripe_webhook_routes.py` | **Pending (Phase 3).** `POST /webhooks/stripe` + signature verification. |
| `docker-compose.yml` Firefly stack | **Done (Phase 1).** `firefly`, `firefly-db`, `firefly-importer` under `finance` profile. |

**Net add: ~1,200 LOC. Net delta: ~−2,200 LOC.**

## Architecture

**Hexagonal placement.** `firefly_client.py` is an outbound adapter (like `invoice_renderer.py`). It is the sole Firefly-aware file — services and UI depend on the `FireflyOperations` Protocol in `core/ports/finance_protocols.py`, not the concrete client.

**Two-book design.** Every `FireflyOperations` method takes a `book: FireflyBook` argument (`"personal"` or `"skuel"`) which picks the Personal Access Token. One Firefly instance, two users.

**Deployment topology:**

```
docker-compose.yml  (--profile finance)
├── app (SKUEL FastHTML)
├── neo4j
├── prometheus + grafana  (--profile monitoring)
├── firefly               ← fireflyiii/core:latest, port 8081
├── firefly-db            ← mariadb:11, isolated volume
└── firefly-importer      ← fireflyiii/data-importer (optional)
```

**Read path.** Admin visits `/finance/expenses` → `finance_ui.py` calls `firefly_expense_service.list_expenses(book="skuel", …)` → `firefly_client.list_transactions(book, start, end)` → renders MonsterUI table.

**Write path (Stripe sync).** Stripe fires `charge.succeeded` → `POST /webhooks/stripe` → signature verification → `stripe_firefly_sync_service.handle_charge_succeeded(event)` → `firefly_client.create_transaction(book="skuel", type="deposit", external_id=event.id, …)`. Idempotent via `external_id` lookup.

**Invoice path.** `/finance/invoices` is unchanged — SKUEL's local `FinanceInvoiceService` + Neo4j + WeasyPrint.

## Consequences

### Positive

- **~2,200 LOC net deleted.** Expense/budget/reporting maintenance offloaded upstream.
- **Established software.** Firefly III has a committed maintainer, regular releases, active community. SKUEL does not.
- **Clean hexagonal boundary.** The Firefly dependency is isolated to one adapter file; nothing in the UI or service layer knows about Firefly's wire format.
- **Powerful features for free.** Rules, recurring transactions, multi-currency, CSV bank import — things SKUEL would never have built.

### Negative

- **New required dependency.** The app now needs Firefly running to render the finance hub pages. `INTELLIGENCE_TIER=core` is unaffected (finance is admin-only, orthogonal to the intelligence tier).
- **Two PATs to manage.** Each of the two Firefly user accounts has its own Personal Access Token. SKUEL's `.env` holds both.
- **No cross-user view.** Firefly has no "all books" view. SKUEL's `/finance` shows two tabs (Personal / SKUEL), each hitting a different PAT. Revisit when Firefly III ships "multiple administrations".
- **Historical data migration burden.** If real expense data exists in Neo4j at Phase 5 time, a one-off `scripts/migrations/export_expenses_to_firefly.py` is required.

### Neutral

- **Invoice module preserved as-is.** No behavior change for PDF invoice generation.

## Alternatives Considered

1. **Keep everything.** Rejected — explicit violation of Leverage Maintained Software.
2. **Replace invoices too (e.g., Invoice Ninja).** Rejected — adds a second self-hosted service for a module that already works. Invoices are one small module; the surface area isn't worth it.
3. **Migrate to a SaaS (e.g., Stripe Dashboard only).** Rejected — personal finances are not a SaaS-shaped problem, and the founder wants self-hosted data ownership.
4. **Build a lightweight custom wrapper around a CSV/SQLite backend.** Rejected — that IS a maintenance liability. The point is to delete code, not rewrite it lighter.

## Verification

- `docker compose --profile finance up firefly firefly-db` → health checks pass.
- Register two Firefly users via the web UI at `http://localhost:8081`, generate a PAT for each.
- `curl -H "Authorization: Bearer <PAT>" http://localhost:8081/api/v1/about` → returns version JSON.
- `uv run pytest tests/unit/test_firefly_client.py` → 17 tests via `httpx.MockTransport`.
- Stripe CLI: `stripe trigger charge.succeeded` → transaction visible in Firefly UI and SKUEL `/finance/expenses`.
- Invoice smoke test: `/finance/invoices/new` → create → download PDF → WeasyPrint path unchanged.

## References

- [Firefly III Documentation](https://docs.firefly-iii.org/)
- [Firefly III REST API Docs](https://api-docs.firefly-iii.org/)
- `docs/domains/finance.md` — domain overview reflecting the split
- `adapters/outbound/firefly_client.py` — the Firefly REST adapter
- `core/ports/finance_protocols.py` — `FireflyOperations` protocol
- `memory/feedback_leverage_maintained_software.md` — the principle this ADR applies
