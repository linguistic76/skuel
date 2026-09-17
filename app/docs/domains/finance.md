---
title: Finance Domain
created: 2025-12-04
updated: 2026-09-17
status: current
category: domains
tags: [finance, firefly, chargekeep, billing, invoicing, admin-only, adr-052, adr-062]
---

# Finance Domain

*Last updated: 2026-05-25*

**Type:** Admin-only, mid-migration. A legacy in-graph finance module is **still live**; it is being replaced by maintained external software — [Firefly III](https://www.firefly-iii.org/) for accounting and **ChargeKeep** for SaaS billing/invoicing.
**Access:** All routes require the `ADMIN` role.

> **This doc describes what is wired *today*.** The target architecture and the
> sequence to reach it live in
> [`roadmap/finance-billing-migration.md`](../roadmap/finance-billing-migration.md),
> [ADR-052](../decisions/ADR-052-firefly-iii-finance-integration.md), and
> [ADR-062](../decisions/ADR-062-chargekeep-billing-layer.md). Where those describe the
> *plan*, the **Current state** table below describes the *running code* — and most of
> the plan is not built yet.

Finance is the polystore exception to SKUEL's Neo4j commitment — see
[ADR-044 § *Scope: this commitment governs the domain graph, not the finance/billing edge*](../decisions/ADR-044-neo4j-committed-architectural-choice.md).

---

## Current state (2026-05-25)

The expense half of the migration has landed as a demolition (see *Phase 5 demolition* below); the invoice half is still the legacy module, and it is the only `/finance` page left.

| Piece | State today |
|---|---|
| **Legacy SKUEL finance module** — invoices only (Neo4j-backed) | ✅ **Invoices present and live** at `/finance/invoices` (`finance_ui.py`, `@require_admin`). The expense / budget / reporting / categories half **is gone** — see *Phase 5 demolition* below. |
| **Firefly III Docker sidecar** (`finance` profile) | ✅ Built (ADR-052 Phase 1) — `firefly` + `firefly-db` (MariaDB), its own store. |
| `firefly_client.py` + `FireflyOperations` protocol (+17 unit tests) | ✅ Built (ADR-052 Phase 2), but **unwired** — no running code path calls it yet. |
| **SaaS billing / subscriptions / checkout / webhooks** | ❌ **Greenfield — does not exist.** Role upgrades (`REGISTERED → MEMBER → …`) are **manual**: admin → `admin_api.py` → `user_service.update_role()`. |

So the Firefly read-facade UI and Stripe→Firefly sync sketched in ADR-052, and ChargeKeep
in ADR-062, are **plans, not running code.** Read the roadmap for the phased sequence; the
ChargeKeep spike (Phase 3a) is the gate that unlocks everything after it.

---

## The direction (ADR-052 + ADR-062)

Two external systems will own finance; SKUEL keeps only thin adapters plus a webhook
consumer. **The split is the point — do not reunify it.**

| Concern | Target store | SKUEL's piece | Status |
|---------|--------------|---------------|--------|
| Expenses, budgets, categories, reporting | **Firefly III** — own MariaDB sidecar at `http://firefly:8080` | `firefly_client` (trimmed to write-only revenue sync) | ADR-052 **Accepted** — adapter built, unwired |
| SaaS billing: checkout, subscriptions, customer portal, **invoicing** | **ChargeKeep** — SaaS | `webhook_routes.py` consumer → role map + revenue→Firefly | ADR-062 **Proposed** (spike-gated) |
| Card rails / money movement | **Stripe** (underneath ChargeKeep) | — | — |

### Revisions to ADR-052 (decided 2026-05-24 — see roadmap)

ADR-052 as originally written is partly superseded. The current plan:

- **No custom SKUEL finance UI.** Admins use Firefly's native UI (two Firefly user
  accounts, two sign-ins) + ChargeKeep's dashboard. The planned `firefly_expense_service`
  read-facade is **cancelled** (Phase 4); `finance_ui.py` is deleted, not rewired.
- **Invoices move to ChargeKeep.** ADR-052 kept the local WeasyPrint invoice module because
  Firefly can't invoice — ChargeKeep can, so the local module is slated for deletion (Phase 5).
- **Billing is ChargeKeep, not Stripe-direct.** ADR-052's `POST /webhooks/stripe` design is
  superseded by `POST /webhooks/chargekeep` behind a swappable `BillingProvider` port
  (ChargeKeep now; FastStripe-direct as the fallback if the spike rejects ChargeKeep).
- **Revenue sync (planned):** ChargeKeep `payment.succeeded` →
  `firefly_client.create_transaction(book="skuel", type="deposit", external_id=<event id>)`,
  idempotent via `external_id`. This is the *only* surviving use of `firefly_client`.

---

## Firefly III — operational notes (sidecar is built)

The Firefly stack exists and runs, even though SKUEL doesn't yet read from it.

### Two books, one instance

One Firefly III instance, two user accounts — one for Mike's personal finances, one for
SKUEL business finances — each with its own Personal Access Token. (Firefly's "multiple
administrations" feature is WIP; two users is the shipped workaround.) Post-Phase-5, SKUEL
only needs the **skuel-book PAT** for the revenue-sync write; the personal book is
Firefly-UI-only.

### Running Firefly locally

Firefly services are gated behind the `finance` Docker Compose profile, so they don't start
with the default `docker compose up`:

```bash
# First-time setup — generate the Laravel app key
printf "base64:%s\n" "$(head -c 32 /dev/urandom | base64)"
# Paste into FIREFLY_APP_KEY in .env (no inline comments — Compose treats everything
# after = as the value).

# Bring up the Firefly stack
docker compose --profile finance up -d firefly-db firefly

# Create users + PATs in the Firefly web UI
open http://localhost:8081
# For each user: Profile → OAuth → Personal Access Tokens → Create New Token → copy once
```

### Hexagonal seam

`firefly_client.py` is an outbound adapter (sibling of `invoice_renderer.py`) — **not**
behind `UniversalNeo4jBackend`. The `FireflyOperations` Protocol (`core/ports/finance_protocols.py`)
is the seam; nothing outside `firefly_client.py` knows Firefly's wire format. Services
consume strongly-typed TypedDicts (`FireflyTransaction`, `FireflyBudget`, `FireflyCategory`,
`FireflyAccountBalance`).

### Firefly docs — read these for anything non-trivial

SKUEL does not re-document Firefly:
- **User guide:** <https://docs.firefly-iii.org/>
- **REST API reference:** <https://api-docs.firefly-iii.org/>
- **Rules engine:** <https://docs.firefly-iii.org/references/firefly-iii/rules/>
- **Data importer (CSV/bank):** <https://docs.firefly-iii.org/references/data-importer/>

---

## Security model

All Finance UI and API routes require the `ADMIN` role — enforced at the route level via
`@require_admin(get_user_service)`. Admin sees ALL finance data; there is no ownership
filtering. Finance data is sensitive, and the admin-only constraint deliberately eliminates
multi-tenant complexity. This holds for both the legacy module today and the (planned)
billing webhook flow.

---

## Phase 5 demolition — what is gone, what is still open

Phase 5 is **partial** (roadmap table destaled 2026-08-21). The expense side landed in
#143 + #144 (ADR-052 Phase 5, 1/2 + 2/2, 2026-05-31); the invoice side waits on the
ChargeKeep invoicing gate.

**Gone (#144):** the expense / budget / reporting / categories models + services + Neo4j
label — the former `finance_pure.py`, `finance_core_service.py`, `finance_budget_service.py`,
`finance_reporting_service.py`, `finance_categories.py`, the expense-backed cross-domain
analytics, the `Expense` label (`NonKuDomain.FINANCE` now maps to `NeoLabel.INVOICE`), the
expense sections/components of `ui/finance/`, and the `/finance` dashboard hub (only
`/finance/invoices` survives). `FinanceService` wraps the one remaining sub-service.

**Still open — deleted when the ChargeKeep invoice-quality check passes:**

- **The local invoice module:** `core/models/finance/invoice.py`,
  `core/services/finance/finance_invoice_service.py`, `adapters/outbound/invoice_renderer.py`
  (WeasyPrint) — invoices move to ChargeKeep.
- **The invoice UI:** `adapters/inbound/finance_ui.py` + the `ui/finance/` package (layout,
  invoice_views, types) + the route wiring (`finance_routes.py`).
- Invoice endpoints in `adapters/inbound/finance_api.py`; the `UniversalNeo4jBackend[InvoicePure]`
  backend; their tests.
- `firefly_client` / `FireflyOperations` **trimmed to write-only** — keep `create_transaction`,
  `find_transaction_by_external_id`, `health_check`; drop the read methods that only existed
  for the now-cancelled read-through UI.

The legacy [`FINANCE_CATEGORIES_GUIDE.md`](../architecture/FINANCE_CATEGORIES_GUIDE.md)
documents the YAML category system in this deletion set — kept for archaeology only; don't
build against it.

---

## Key SKUEL files (today)

| Component | Location | Note |
|-----------|----------|------|
| **Finance facade** | `core/services/finance_service.py` | Live (invoice-only); backs `/finance/invoices` |
| **Finance models** | `core/models/finance/` (`invoice.py`) | Live; the expense/budget/reporting models are gone (Phase 5) |
| **Finance UI** | `adapters/inbound/finance_ui.py`, `ui/finance/invoice_views.py` | Live (invoices only); the invoice side waits on the ChargeKeep gate |
| **Finance API** | `adapters/inbound/finance_api.py` | Live; Phase-5 deletion target |
| **Firefly adapter** | `adapters/outbound/firefly_client.py` | Built, unwired |
| **Firefly protocol + DTOs** | `core/ports/finance_protocols.py` | Built |
| **Firefly exceptions** | `core/utils/exception_types.py` (`FIREFLY_EXCEPTIONS`) | — |
| **Firefly unit tests** | `tests/unit/test_firefly_client.py` (17 tests, mocked httpx) | — |
| **Docker stack** | `docker-compose.yml` (`finance` profile) | Built |
| **Billing port / ChargeKeep adapter / webhook route** | — | **Not created** (greenfield); planned locations in [`roadmap/finance-billing-migration.md` § Code-touch inventory](../roadmap/finance-billing-migration.md) |

---

## See also

- [`roadmap/finance-billing-migration.md`](../roadmap/finance-billing-migration.md) — the phased plan, ChargeKeep spike checklist, and current-state map
- [ADR-052: Firefly III Finance Integration](../decisions/ADR-052-firefly-iii-finance-integration.md) — accounting-side decision
- [ADR-062: ChargeKeep as the SaaS Billing Layer](../decisions/ADR-062-chargekeep-billing-layer.md) — billing-side decision (Proposed)
- [ADR-044 § Scope](../decisions/ADR-044-neo4j-committed-architectural-choice.md) — why finance lives outside the Neo4j graph
- `/docs/design-principles/LEVERAGE_MAINTAINED_SOFTWARE.md` — the principle this migration applies
