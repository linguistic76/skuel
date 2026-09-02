---
updated: 2026-09-02
---

# Finance & Billing Migration — Intention + Plan

*Drafted: 2026-05-24 · Status: **Planning (not started)** · Owner: Mike*

This doc sets the intention for finishing the finance migration (ADR-052 Phases 3–5)
and folds in a new decision: **lean on ChargeKeep as the subscription/billing layer**
instead of hand-building it on Stripe. The formal decision record is
[ADR-062: ChargeKeep as the Billing Layer](../decisions/ADR-062-chargekeep-billing-layer.md)
(status: **Proposed**, gated on a spike).

> **Not for implementation yet.** This is the map and the sequence. Phase 3a (the
> ChargeKeep spike) is the gate that unlocks everything after it.

---

## Where we are today

| Piece | State |
|---|---|
| Firefly III Docker sidecar | ✅ Built (ADR-052 Phase 1) |
| `adapters/outbound/firefly_client.py` + `FireflyOperations` protocol | ✅ Built + 17 tests, but **unwired** (Phase 2; registered as staged in `scripts/health/dead_modules.py`) |
| ADR-052 Phase 5 demolition | ◐ **Partial — blocked on the ChargeKeep invoicing gate** (table destaled 2026-08-21): most of the demolition landed (`finance_ui.py` is 85 lines serving only `/finance/invoices`; `ui/finance/` is down to the invoice module; `core/services/finance/` holds only `finance_invoice_service.py`; Phase 4 CANCELLED per ADR-052). **Still open**: the invoice route/service/views + WeasyPrint renderer (`adapters/outbound/invoice_renderer.py`) are inside Phase 5's deletion scope and remain until the ChargeKeep invoice-quality check passes — Phase 5 is not complete until they go |
| **Any** SaaS billing / subscription / Stripe / webhook code | ❌ **Does not exist.** Role upgrades are manual: admin → `admin_api.py` → `user_service.update_role()` |

**Key fact: the subscription side is greenfield.** Phase 3 is not rewiring an existing
payment flow — it is building the *first* one. Clean seam, no legacy to demolish there.

## The layer map

The three tools stack; they do not compete.

| Layer | Tool | Role |
|---|---|---|
| Card rails / money movement | **Stripe** | Always underneath. ChargeKeep and FastStripe both use it. |
| Billing orchestration: hosted checkout, recurring subscriptions, dunning, customer portal, **invoicing** | **ChargeKeep** (owned, lifetime) | "Become a MEMBER, manage your card, get an invoice." |
| Accounting ledger: expenses, budgets, P&L, revenue | **Firefly III** | Where money in/out is recorded for accounting. Two books: `personal`, `skuel`. |
| Admin finance UI | **Firefly's native UI** (two sign-ins) + **ChargeKeep dashboard** | **No custom SKUEL finance hub** (resolved 2026-05-24). SKUEL only syncs revenue + optionally links out; users hit ChargeKeep checkout. |

## Tooling decisions

- **ChargeKeep = the billing layer.** It is a Stripe-verified partner sitting on top of
  your Stripe account, providing checkout + recurring subscriptions + customer portal +
  **invoicing/receipts** + affiliates + a REST API + webhooks. Adopting it means SKUEL
  builds *one webhook consumer + a role map*, not a payment system. It is the
  **Leverage Maintained Software** principle applied exactly as written, at $0 marginal
  cost (lifetime sub). Critically, ChargeKeep's invoicing can absorb the **one module
  ADR-052 was forced to keep local** (WeasyPrint invoices) — Firefly couldn't do
  invoicing, ChargeKeep can.
- **FastStripe = residual only.** [stripe.fast.ai](https://stripe.fast.ai/) is the right
  choice over the official `stripe-python` SDK (AnswerDotAI/FastHTML alignment,
  async-native, lightweight, pinned-snapshot determinism — matches SKUEL's
  environment-agnostic value). But with ChargeKeep owning the billing flow, SKUEL's
  direct-Stripe surface shrinks to near-zero — likely just payout/balance reads for
  reconciliation into Firefly, or as the fallback if the spike rejects ChargeKeep.
- **Firefly = unchanged.** Stays the accounting ledger per ADR-052.

## Phased plan

**Phase 3a — ChargeKeep spike (THE GATE).** Time-boxed (~1–2 days). Validate the API and
webhooks against the checklist below. Output: a go/no-go that flips ADR-062 from Proposed
to Accepted (ChargeKeep-first) or Rejected (fall back to Stripe-direct/FastStripe per
ADR-052 as originally written). **Nothing after this phase starts until the gate passes.**

**Phase 3b — Billing port + ChargeKeep adapter + role grant.**
- `core/ports/billing_protocols.py` <!-- planned --> — `BillingProvider` Protocol + event TypedDicts
  (keeps the source swappable: ChargeKeep now, Stripe-direct later if ever needed).
- `adapters/outbound/chargekeep_client.py` <!-- planned --> — outbound adapter implementing `BillingProvider`
  (httpx; FastStripe only if we ever call Stripe directly).
- `adapters/inbound/webhook_routes.py` <!-- planned --> — `POST /webhooks/chargekeep`: signature verify →
  map ChargeKeep customer → SKUEL user → `user_service.update_role(MEMBER)` on **New Payment**
  (the real-money signal; New Subscription also fires on unpaid trials). Idempotent +
  replay-safe. **MEMBER is the only billing-driven role** — TEACHER/ADMIN are admin
  promotions, never purchased, so webhooks never touch them.
- **Downgrade path (no cancel event — see findings):** a **nightly reconciliation job**
  polls ChargeKeep for active subscriptions and reverts any MEMBER whose subscription has
  lapsed to REGISTERED — *unless* the in-account check finds a native cancel/expire webhook,
  in which case use that instead.
- `User` model gains a `chargekeep_customer_id` link (set on first checkout via metadata
  pass-through).
- **Reuse SKUEL's `Result[T]` + `Errors` factory; the webhook authenticates by signature
  verification** (signed external callback, not a browser form). If it needs a
  `CSRF_EXEMPT` entry, that is a deliberate ruling:
  `test_csrf_exempt_holds_exactly_the_by_design_entries` asserts the exact table contents,
  so the tripwire must be updated in the same change with the reason documented — never a
  silent addition.

**Phase 3c — Revenue → Firefly sync.** ChargeKeep `payment.succeeded` webhook →
`firefly_client.create_transaction(book="skuel", type="deposit", external_id=<event id>)`.
The `external_id` idempotency key and `find_transaction_by_external_id` already exist on
`FireflyOperations` — no protocol change needed.

**Phase 4 — ~~UI rewire~~ CANCELLED.** *(Open question 5 resolved 2026-05-24: no custom finance
UI.)* `firefly_expense_service.py` is **not** created and `finance_ui.py` is **not** rewired —
it is deleted in Phase 5. Admins use Firefly's **native UI** (two Firefly user accounts, two
sign-ins); subscription/revenue metrics come from **ChargeKeep's dashboard**. `firefly_client`
survives only for the Phase 3c revenue-sync *write*.

**Phase 5 — Demolition (expanded by the open-question-5 resolution).** With no custom finance
UI, delete **all** of it — not just ADR-052's ~3,400-LOC legacy slice:
- **Whole UI:** `adapters/inbound/finance_ui.py` + the `ui/finance/` package (layout,
  section_views, invoice_views, components, types) + the `/finance` routes / DomainConfig wiring.
- **Legacy services + models:** `finance_service.py` facade + `finance/` sub-services
  (core, budget, reporting, **invoice**), `finance_pure.py`, `invoice.py`, `finance_dto`,
  `finance_converters`, expense/budget backend in `misc_backends.py`, expense/budget/invoice
  endpoints in `finance_api.py`, the finance Neo4j backend(s), and their tests.
- **Invoice renderer:** `adapters/outbound/invoice_renderer.py` (WeasyPrint) — invoices are now
  ChargeKeep (open question 'c' confirmed).
- **Trim `firefly_client` / `FireflyOperations` to write-only:** keep `create_transaction`,
  `find_transaction_by_external_id`, `health_check`; delete the read methods (`list_transactions`,
  `list_budgets`, `list_categories`, `list_accounts`, `category_insight`, `budget_insight`) —
  they only existed for the now-cancelled read-through UI.
- Only the **skuel-book PAT** is needed (revenue-sync write); the personal book is
  Firefly-UI-only, so SKUEL holds no personal PAT. Update `services_bootstrap` accordingly.

## ChargeKeep spike checklist (Phase 3a gate)

Each line is a go/no-go input. Use a ChargeKeep test/sandbox; do **not** wire to SKUEL yet.

- [ ] **Stripe account model.** Does ChargeKeep transact on *your* connected Stripe account
      (clean — payouts land in your Stripe, easy to reconcile into Firefly) or its own
      merchant of record? This decides the revenue-sync design.
- [ ] **Webhook catalog + signatures.** Confirm events exist for `subscription.active`,
      `subscription.cancelled`/`expired`, `payment.succeeded`, `payment.failed`, `refund`.
      Confirm signature-verification mechanism (shared secret / HMAC header).
- [ ] **External-id pass-through.** Can a checkout/subscription carry custom metadata
      (SKUEL `user_uid`) so the webhook maps cleanly customer → SKUEL user *without* a
      fragile email match?
- [ ] **Plan → tier mapping.** Model **one** ChargeKeep plan = MEMBER (the only paid tier;
      decided 2026-05-24). REGISTERED is the free trial; TEACHER/ADMIN are admin-granted and
      never purchased, so they stay out of ChargeKeep entirely. Confirm one product/plan
      covers the subscription (monthly/annual variants optional).
- [ ] **Invoicing quality.** Branding, line items, tax fields, PDF receipt. Good enough to
      delete the local WeasyPrint module? (PDF is fine — it's the sanctioned finance
      exception in CLAUDE.md.)
- [ ] **Cancellation/downgrade semantics.** Webhook timing on cancel; grace period; what
      role the user reverts to.
- [ ] **Customer portal.** Does ChargeKeep's hosted portal (update card, cancel, pause)
      cover self-service so SKUEL builds none of it?
- [ ] **API/SDK shape + reliability.** Auth, rate limits, error shapes, webhook
      retry/replay behavior. (~500 endpoints advertised — verify the ~10 we need are solid.)
- [ ] **Affiliate program.** Note only — relevant to SKUEL growth later, not this migration.

## Phase 3a — desk-research findings (2026-05-24)

Verdict: **AMBER — thesis holds, gate not yet cleared.** The capabilities we need exist, but
the integration-critical specifics are *not in ChargeKeep's public docs* and must be
confirmed inside the account (the hands-on checklist below). Source:
[chargekeep.com/api](https://www.chargekeep.com/api), [help center](https://www.chargekeep.com/help/).

**Confirmed from docs (green):**
- Products/plans, subscriptions, invoicing, payments, CRM contacts, customer portal, and an
  affiliate program all exist. Stripe-verified partner — Stripe moves the money underneath.
- A webhook/event system *is* programmable: `POST /api/services/Platform/Event/Subscribe`,
  `/GetSubscriptions`, `/Unsubscribe`. Its catalog, mirrored publicly via ChargeKeep's Zapier
  app, exposes **three creation triggers**: *New Lead*, *New Subscription* (fires on paid
  activation **or** trial start), *New Payment* (successful payment). Matching write actions
  exist (Add/Update Contact, Create Product, Add/Update Subscription, Create Invoice, Get
  Contact Details).
- Endpoints for our flow exist: `CRM/Contact/CreateOrUpdateContact`, `CRM/Product/CreateProduct`,
  `CRM/OrderSubscription/Update`, `CRM/Invoice/Create`, `CRM/Invoice/AddBankCardPayment`.

**Concerns surfaced (re-shape the design):**
- **RPC/CRM-style API, not resource-REST.** Endpoints are `POST /api/services/<Module>/<Verb>`
  modelled around a CRM. There is no clean SDK and FastStripe ergonomics do not apply here —
  `chargekeep_client.py` will be a **hand-rolled httpx adapter** against RPC calls. (FastStripe
  stays for any *direct Stripe* reads, not for ChargeKeep.)
- **No cancellation / expiration / failure / refund event exists** in the public
  (Zapier-mirrored) catalog — only the three *creation* triggers above. 🔴 **This is the
  gate's hardest finding.** The role-*grant* side is covered (MEMBER on New Subscription /
  New Payment), but there is **no event to drive the *downgrade*** (MEMBER → REGISTERED on
  cancel/lapse). Two ways out, in preference order: (a) confirm in-account that the *native*
  `Event/Subscribe` API exposes a cancel/expire event Zapier just doesn't surface; or
  (b) accept a **nightly reconciliation job** that polls active subscriptions and downgrades
  lapsed MEMBERs (a day's grace on access is acceptable). Note: *New Subscription* also fires
  on **trial start**, so gate the MEMBER grant on *New Payment* (real money) to avoid granting
  on an unpaid trial.
- **Webhook signing scheme still undocumented.** Confirm a signing secret + signature header
  exist in-account (check 3 below); if delivery is unsigned, fall back to an IP allowlist or a
  shared-secret path segment.
- **Weak metadata.** Only `trackingInfo.customField1..5` (five strings) + UTM on a contact;
  whether these ride on webhook payloads is unconfirmed. **Design implication:** do *not* rely
  on webhook metadata for the customer→user map. Instead **capture the ChargeKeep contact id at
  checkout-return and persist `chargekeep_customer_id` on `User`**; webhooks then key on that id.
  Email match is a fragile fallback only.
- **Hosted checkout is dashboard-configured, not API-created.** Fine for a single MEMBER plan
  (build one embeddable form/link once). Must confirm the form can carry a prefilled hidden
  field (→ `customField`) *or* that the checkout-return hands us the contact id.

**Account-only checks to clear the gate (hands-on, Mike):**
1. API panel → generate a **test API key**; record the exact auth header (`Authorization: Bearer …`
   vs `X-API-Key`).
2. Events/Webhooks UI → **does the *native* API expose more than Zapier's three creation
   triggers?** Specifically hunt for a **subscription cancelled/expired** event — its presence
   removes the need for the reconciliation job. (New Subscription / New Payment already
   confirmed via Zapier.)
3. Confirm whether a webhook **signing secret** can be set (and the signature header name), or
   whether delivery is unsigned (weaker — would need IP allowlist / shared-secret).
4. In the checkout/payment-form builder → can you add a **prefillable hidden/custom field**
   (maps to `customField1..5`) to carry SKUEL `user_uid`?
5. Trigger one test event → **capture the raw webhook JSON**; check it includes the contact id
   and the `customField`s.
6. Settings/integrations → confirm ChargeKeep transacts on **your connected Stripe account**
   (payouts land in your Stripe → clean Firefly reconciliation).
7. Confirm the **customer portal** link (update card / cancel) exists and is brandable.
8. Generate a sample **invoice/receipt PDF** → judge branding/line-items/tax vs. the local
   WeasyPrint module (decides whether Phase 5 deletes it).

Closing #2 (native cancel event?), #3 (signing), and #5 (raw payload shape) flips ADR-062 from
Proposed to Accepted (with or without the reconciliation job) or Rejected.

## Open questions (product, not just engineering)

1. ~~Is TEACHER a paid tier?~~ **Resolved 2026-05-24: no.** Only MEMBER is paid
   (one ChargeKeep plan). TEACHER and ADMIN are admin-granted promotions, never purchased.
   Billing webhooks only ever grant/revoke MEMBER.
2. **Refunds / chargebacks → role revocation?** Auto-downgrade on refund, or manual review?
3. **Is monetization imminent or longer-horizon?** Drives whether Phase 3 is next-up or
   parked behind learning-loop work. The spike (3a) is cheap regardless.
4. **Vendor-longevity hedge.** ChargeKeep is AppSumo-tier. The `BillingProvider` port is the
   insurance: if ChargeKeep ever folds, swap the adapter to FastStripe-direct without
   touching routes/services. Worth keeping the port even though only one impl ships.
5. ~~Custom UI over Firefly?~~ **RESOLVED 2026-05-24: eliminate SKUEL's custom finance UI.**
   - **Expenses / budgets / reports / tax →** Firefly's **native UI**, via **two Firefly user
     accounts** (personal + skuel) on the one sidecar — two sign-ins. No SKUEL aggregate view;
     keeping the books separate is *desirable* for tax/accounting hygiene, so a merged view would
     be an anti-feature (answers 'a': two sign-ins is the cleaner choice).
   - **Subscription / revenue metrics →** ChargeKeep's own dashboard (MRR, active subs, churn).
     A SKUEL widget reading Firefly would duplicate it — **dropped** (answers 'b'). A single MRR
     stat on SKUEL's admin home is trivially addable later *from ChargeKeep*, and is not a custom
     finance UI.
   - **Invoices →** ChargeKeep (answers 'c'). The local WeasyPrint invoice module is deleted
     (Phase 5).
   - SKUEL keeps **no finance UI** — optionally a single nav link to the Firefly sidecar URL
     (a launcher, not an interface).
   Honours **Leverage Maintained Software** + **Consolidation over parallel systems**, and
   supersedes ADR-052's 'thin read-through facade' framing. `firefly_client` is kept solely for
   the revenue-sync write (see Phases 4–5).

## Code-touch inventory (for when we build)

| Concern | Location |
|---|---|
| New billing port | `core/ports/billing_protocols.py` (new) <!-- planned --> |
| ChargeKeep adapter | `adapters/outbound/chargekeep_client.py` (new) <!-- planned --> |
| Webhook route | `adapters/inbound/webhook_routes.py` (new) <!-- planned --> — register in bootstrap |
| Firefly read-facade | `core/services/finance/firefly_expense_service.py` (new) <!-- planned --> |
| Role grant | `core/services/user/` `update_role` (exists) |
| User ↔ customer link | `core/models/user/user.py` (+`chargekeep_customer_id`) |
| Revenue sync | reuse `firefly_client.create_transaction` (exists) |
| Service composition | `services_bootstrap/_core_services.py`, `_backends.py`, `_container.py`, `_event_wiring.py`, `compose.py` |
| Secrets | ChargeKeep API key + webhook secret via `get_credential()` (SKUEL019); Firefly PATs already there |

## Cleanup spotted while planning

- ~~`core/ports/finance_protocols.py:7,12` cites **ADR-051** for the Firefly integration; the
  Firefly ADR is **ADR-052**. Fix the two references (one-line doc correction) whenever this
  area is next touched.~~ **Resolved 2026-05-25:** both references now correctly cite
  **ADR-052** (verified — no ADR-051 reference remains in `finance_protocols.py`).

## References

- [ADR-052: Firefly III Replaces SKUEL Expense/Budget/Reporting](../decisions/ADR-052-firefly-iii-finance-integration.md)
- [ADR-062: ChargeKeep as the Billing Layer](../decisions/ADR-062-chargekeep-billing-layer.md) *(Proposed)*
- FastStripe — https://stripe.fast.ai/ · FastHTML Stripe example (by_example tutorial, "Again, with Credits!")
- ChargeKeep — https://www.chargekeep.com/help/ · API at https://www.chargekeep.com/api
- `/docs/design-principles/LEVERAGE_MAINTAINED_SOFTWARE.md` — the principle this applies
