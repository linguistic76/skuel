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
  - ADR-062-chargekeep-billing-layer
---

# ADR-052: Firefly III Replaces SKUEL Expense/Budget/Reporting

## Status

Accepted — implementation in progress. **Phases 1 + 2** (Docker stack + `firefly_client` REST adapter) landed in commit `c3258630`. **Phase 4 (custom finance UI) is CANCELLED** and **Phase 5 (demolition) is expanded to the whole native finance surface** — see "Amendments" below. The billing side (originally Stripe-direct, now ChargeKeep) is owned by [ADR-062](ADR-062-chargekeep-billing-layer.md); the phased sequence + spike gate live in [`roadmap/finance-billing-migration.md`](../roadmap/finance-billing-migration.md).

> **Amendments (2026-05-24).** This ADR's body has been revised so it no longer contradicts the resolution captured in ADR-062 + the roadmap. Three reversals of the original 2026-04-12 text:
> 1. **Billing is ChargeKeep, not Stripe-direct.** The `POST /webhooks/stripe` consumer and `stripe_firefly_sync_service` are replaced by a ChargeKeep webhook consumer (ADR-062). Firefly-as-ledger is unchanged.
> 2. **No custom SKUEL finance UI.** The "thin read-through facade" (`firefly_expense_service.py`, a rewired `finance_ui.py`) is dropped. Admins use Firefly's **native UI** (two Firefly users, two sign-ins); subscription/revenue metrics come from ChargeKeep's dashboard.
> 3. **The local invoice module is NOT kept** — invoicing moves to ChargeKeep (Firefly can't invoice; ChargeKeep can). The WeasyPrint renderer is deleted too. Consequently Phase 5 demolishes the **entire** native finance surface, and `firefly_client` is trimmed to **write-only** (revenue-sync).

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

1. SKUEL's invoice module is **built but unused today** — the SaaS-payment side is greenfield (no billing code exists; role upgrades are manual via admin). *Originally* the invoice module was kept "for future non-Stripe billing"; under [ADR-062](ADR-062-chargekeep-billing-layer.md) that role is taken by **ChargeKeep's** invoicing, so the local module is deleted instead of kept.
2. Finance is **isolated** in SKUEL — no cross-domain relationships, no intelligence service, no ZPD/LifePath wiring. The replacement is a clean seam.

**Firefly III cannot replace** invoicing, A/R, or customer entities — but **ChargeKeep can** (ADR-062). So nothing finance-shaped stays native: Firefly is the accounting ledger, ChargeKeep is billing + invoicing, and SKUEL holds only a thin revenue-sync write + a billing webhook consumer.

## Decision

**Replace SKUEL's expense + budget + reporting modules with Firefly III as the accounting ledger. Build no custom SKUEL finance UI — admins use Firefly's native web UI. Demolish the entire native finance surface (expense/budget/reporting *and* invoice).**

Firefly III runs as a Docker sidecar to SKUEL. Two Firefly user accounts live on one instance — one for Mike's personal finances (`personal`), one for SKUEL business finances (`skuel`) — each with its own Personal Access Token. (Firefly's "multiple administrations" feature is WIP; two users is the shipped workaround.) Admins manage expenses/budgets/reports **directly in Firefly's own web UI** (two sign-ins); SKUEL renders no finance pages.

SKUEL's only write into Firefly is **revenue sync**: ChargeKeep billing events (ADR-062) push deposit transactions into the `skuel` book, idempotent via the ChargeKeep event id (`external_id`). Because the read-through UI is cancelled, only the `skuel`-book PAT lives in SKUEL — the `personal` book is Firefly-UI-only.

### Scope — DELETE from SKUEL (Phase 5 — expanded by the 2026-05-24 no-UI resolution)

With no custom finance UI and invoicing moved to ChargeKeep, demolition covers the **whole** native finance surface, not just the original ~3,400-LOC slice:

| File / path | Notes |
|---|---|
| `core/models/finance/finance_pure.py` (ExpensePure, BudgetPure) | |
| `core/models/finance/finance_dto.py`, `finance_converters.py`, `finance_intelligence.py`, `finance_request.py` | |
| `core/models/finance/invoice.py` (InvoicePure + line items) | invoicing → ChargeKeep |
| `core/services/finance_service.py` facade + `core/services/finance/` sub-services (core, budget, reporting, categories, **invoice**) + `finance_types.py` | |
| Expense/budget/invoice backend code in `misc_backends.py` + the finance Neo4j backend(s) | |
| `adapters/inbound/finance_api.py`, `finance_ui.py`, `finance_routes.py` (the `/finance` routes + DomainConfig wiring) | |
| `ui/finance/` package (layout, section_views, invoice_views, components, types) | |
| `adapters/outbound/invoice_renderer.py` (WeasyPrint) | invoicing → ChargeKeep |
| `core/events/finance_events.py` — exported but **no live subscribers** (verified) | |
| Finance tests | |

**Cross-domain ripple to unwire during demolition (verified against current code):**
- `core/services/analytics/analytics_metrics_service.calculate_finance_metrics()` consumes `self.finance.get_user_items_in_range()` (already guards `if not self.finance`) — drop the finance-metrics path or repoint it at Firefly.
- Admin nav `ui/admin/layout.py` links `/finance`; `ui/analytics/dashboard.py` + `domain_metrics.py` expose a "Finance" metrics option — remove both.
- `services_bootstrap/` (`_core_services.py:45`, `_container.py:150`, `compose.py:1163,1380`) wire `finance` into the container and into analytics — unwire.

### Scope — KEEP (trimmed to write-only)

- `adapters/outbound/firefly_client.py` + `core/ports/finance_protocols.py` — **trim to write-only**: keep `create_transaction`, `find_transaction_by_external_id`, `health_check`; delete the read methods (`list_transactions`, `list_budgets`, `list_categories`, `list_accounts`, `category_insight`, `budget_insight`) that existed only for the cancelled read-through UI.

### Scope — CREATE

| File | Purpose |
|---|---|
| `adapters/outbound/firefly_client.py` | **Done (Phase 2).** Async httpx-backed FireflyClient implementing `FireflyOperations`. |
| `core/ports/finance_protocols.py` | **Done (Phase 2).** `FireflyOperations` protocol + TypedDicts. |
| ~~`core/services/finance/firefly_expense_service.py`~~ | **CANCELLED (Phase 4).** No custom finance UI → no read-facade; `finance_ui.py` is deleted, not rewired. |
| Billing webhook + revenue sync | **Owned by [ADR-062](ADR-062-chargekeep-billing-layer.md)** (`billing_protocols.py`, `chargekeep_client.py`, `webhook_routes.py`). Replaces this ADR's original `stripe_firefly_sync_service.py` + `stripe_webhook_routes.py`. |
| `docker-compose.yml` Firefly stack | **Done (Phase 1).** `firefly`, `firefly-db`, `firefly-importer` under `finance` profile. |

## Architecture

**Hexagonal placement.** `firefly_client.py` is an outbound adapter (sibling of `chargekeep_client.py`, ADR-062). It is the sole Firefly-aware file — the billing webhook consumer depends on the `FireflyOperations` Protocol in `core/ports/finance_protocols.py`, not the concrete client.

**Two-book design.** `FireflyOperations` methods take a `book: FireflyBook` argument (`"personal"` or `"skuel"`). Firefly holds both books; SKUEL only ever writes to `"skuel"` (revenue sync), so only that PAT is configured in SKUEL.

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

**Read path.** None in SKUEL — admins read expenses/budgets/reports in **Firefly's native web UI** (two sign-ins). SKUEL renders no finance pages.

**Write path (revenue sync).** ChargeKeep fires a paid-subscription event (ADR-062) → `POST /webhooks/chargekeep` → signature verification → `firefly_client.create_transaction(book="skuel", type="deposit", external_id=<event id>, …)`. Idempotent via `external_id` lookup. (This replaces the original Stripe-direct `charge.succeeded` design.)

**Invoice path.** ChargeKeep issues invoices/receipts (ADR-062). The local `FinanceInvoiceService` + WeasyPrint renderer are deleted in Phase 5.

## Consequences

### Positive

- **More than ~3,400 LOC net deleted** — expanded by the no-UI + invoice-to-ChargeKeep resolution: the whole `ui/finance/` package, `finance_ui.py`, and the invoice module/WeasyPrint renderer go on top of the original expense/budget/reporting slice. Expense/budget/reporting/invoice maintenance offloaded upstream (Firefly + ChargeKeep).
- **Established software.** Firefly III has a committed maintainer, regular releases, active community. SKUEL does not.
- **Clean hexagonal boundary.** The Firefly dependency is isolated to one (write-only) adapter file; nothing in the service layer knows about Firefly's wire format.
- **Powerful features for free.** Rules, recurring transactions, multi-currency, CSV bank import — things SKUEL would never have built, all in Firefly's native UI.

### Negative

- **New required dependency for revenue sync.** SKUEL writes revenue into Firefly via `firefly_client`; the SaaS upgrade flow needs Firefly reachable. `INTELLIGENCE_TIER=core` is unaffected (finance/billing is admin- and payment-scoped, orthogonal to the intelligence tier). SKUEL renders no finance pages, so a Firefly outage no longer blanks an admin hub.
- **One PAT in SKUEL.** Only the `skuel`-book PAT is held by SKUEL (revenue-sync write). The `personal`-book PAT lives only in the operator's Firefly session, never in SKUEL's `.env`.
- **No cross-user view — now Firefly's concern.** Firefly has no "all books" view; admins sign into each Firefly user separately. SKUEL no longer renders a combined hub.
- **Historical data migration burden.** If real expense/budget data exists in Neo4j at Phase 5 time, a one-off export-to-Firefly migration is required before deletion.

### Neutral

- **Invoicing moves to ChargeKeep** (ADR-062). The local WeasyPrint PDF path is deleted; PDF invoices/receipts are issued by ChargeKeep's hosted billing. (PDF remains the sanctioned finance exception in CLAUDE.md — just produced upstream now.)

## Alternatives Considered

1. **Keep everything.** Rejected — explicit violation of Leverage Maintained Software.
2. **Replace invoices too (e.g., Invoice Ninja).** Rejected *at the time* — adds a second self-hosted service for a module that already works. *Superseded 2026-05-24:* invoicing **is** replaced — but by **ChargeKeep** (already-owned hosted billing, no new self-hosted service), which folds invoicing into the same layer that handles checkout/subscriptions. See [ADR-062](ADR-062-chargekeep-billing-layer.md).
3. **Migrate to a SaaS (e.g., Stripe Dashboard only).** Rejected — personal finances are not a SaaS-shaped problem, and the founder wants self-hosted data ownership.
4. **Build a lightweight custom wrapper around a CSV/SQLite backend.** Rejected — that IS a maintenance liability. The point is to delete code, not rewrite it lighter.

## Verification

- `docker compose --profile finance up firefly firefly-db` → health checks pass.
- Register two Firefly users via the web UI at `http://localhost:8081`, generate a PAT for each.
- `curl -H "Authorization: Bearer <PAT>" http://localhost:8081/api/v1/about` → returns version JSON.
- `uv run pytest tests/unit/test_firefly_client.py` → 17 tests via `httpx.MockTransport`.
- Revenue sync (ADR-062): a ChargeKeep paid-subscription test event → deposit visible in Firefly's `skuel` book; replaying the same event creates no duplicate (`external_id` dedupe).
- Post-demolition: SKUEL exposes no `/finance` routes (404); `./dev quality` is green with the finance code removed and its container/analytics/nav wiring unwired.

## References

- [Firefly III Documentation](https://docs.firefly-iii.org/)
- [Firefly III REST API Docs](https://api-docs.firefly-iii.org/)
- `docs/domains/finance.md` — domain overview reflecting the split
- `adapters/outbound/firefly_client.py` — the Firefly REST adapter
- `core/ports/finance_protocols.py` — `FireflyOperations` protocol
- `memory/feedback_leverage_maintained_software.md` — the principle this ADR applies
