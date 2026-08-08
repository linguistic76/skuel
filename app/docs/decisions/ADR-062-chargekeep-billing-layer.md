---
title: "ADR-062: ChargeKeep as the SaaS Billing Layer"
updated: 2026-05-24
status: proposed
category: decisions
tags: [adr, decisions, finance, billing, subscriptions, stripe, chargekeep, leverage-maintained-software]
related:
  - ADR-052-firefly-iii-finance-integration
  - ADR-044-neo4j-committed-architectural-choice
---

# ADR-062: ChargeKeep as the SaaS Billing Layer

**Status:** Proposed — gated on a ChargeKeep spike (Phase 3a). Flips to **Accepted**
(ChargeKeep-first) or **Rejected** (fall back to Stripe-direct per ADR-052 as written)
once the spike checklist passes/fails.
**Date:** 2026-05-24
**Deciders:** Mike
**Related:**
[ADR-052 Firefly III Finance Integration](ADR-052-firefly-iii-finance-integration.md)

> Working plan + phased sequence + spike checklist:
> [`roadmap/finance-billing-migration.md`](../roadmap/finance-billing-migration.md).

---

## Context

ADR-052 replaced SKUEL's home-grown expense/budget/reporting module with Firefly III and
sketched the SaaS-payment side as **Stripe-direct**: "SaaS user payments flow through
Stripe, which issues its own invoices/receipts," with a hand-built `POST /webhooks/stripe`
consumer and the local WeasyPrint invoice module **kept** because "Firefly III cannot
replace invoicing."

Two things have changed the calculus:

1. **There is no billing code yet.** Phases 3–5 of ADR-052 are unstarted. SaaS role
   upgrades (`REGISTERED → MEMBER → TEACHER`) happen *manually* via admin
   (`admin_api.py` → `user_service.update_role()`). The subscription side is greenfield —
   we are choosing what to build, not rewiring something live.

2. **The founder owns a lifetime ChargeKeep subscription with full feature access.**
   ChargeKeep is a Stripe-verified partner that sits on top of a Stripe account and provides
   the entire billing-orchestration layer: hosted/embeddable checkout, recurring
   subscriptions (trials, coupons, dunning), a customer self-service portal, **invoicing +
   PDF receipts**, affiliates, a REST API (~500 endpoints), and webhooks.

SKUEL's **Leverage Maintained Software** principle (a non-technical founder; every custom
subsystem is a maintenance liability) says: do not hand-build a payment system if maintained
software you already own can do it. FastHTML's own Stripe tutorial reinforces this — it ships
only "the bare minimum" and warns to "exercise extra caution when writing code that handles
money."

ChargeKeep can also absorb the **one module ADR-052 was forced to keep local**: invoicing.
Firefly cannot invoice; ChargeKeep can.

## Decision

**Adopt ChargeKeep as SKUEL's billing-orchestration layer (checkout, recurring
subscriptions, customer portal, invoicing). SKUEL builds only a thin webhook consumer that
maps ChargeKeep events to SKUEL role grants and Firefly revenue transactions.** This amends
ADR-052's "Stripe-direct" payment design; Firefly-as-ledger is unchanged.

The decision is **gated on a spike** (roadmap Phase 3a). If the spike fails ChargeKeep on a
critical line (no per-event webhooks, no metadata pass-through, unusable invoicing, or
its-own-merchant-of-record fund flow that can't reconcile to Firefly), this ADR is Rejected
and ADR-052's Stripe-direct path stands.

### What SKUEL builds (ChargeKeep-first)

- `core/ports/billing_protocols.py` — a `BillingProvider` Protocol + event TypedDicts.
  **The source of billing events is abstracted**: ChargeKeep ships now; Stripe-direct stays
  swappable behind the same port if ChargeKeep is ever rejected or sunset.
- `adapters/outbound/chargekeep_client.py` — outbound adapter implementing `BillingProvider`.
- `adapters/inbound/webhook_routes.py` — `POST /webhooks/chargekeep`: verify signature →
  map ChargeKeep customer → SKUEL user (via metadata `user_uid`) → `update_role(MEMBER)` on
  `subscription.active`; revert to `REGISTERED` on `subscription.cancelled`. Idempotent,
  replay-safe.
- Revenue sync: `payment.succeeded` → `firefly_client.create_transaction(book="skuel",
  type="deposit", external_id=<event id>)` — reuses the existing idempotent `FireflyOperations`.
- `User` gains `chargekeep_customer_id` (set on first checkout via metadata pass-through).

### Tool roles after this ADR

| Layer | Tool |
|---|---|
| Card rails | **Stripe** (underneath ChargeKeep) |
| Checkout / subscriptions / portal / invoicing | **ChargeKeep** |
| Accounting ledger (expenses, budgets, revenue) | **Firefly III** |
| Direct Stripe reads (reconciliation), or fallback if ChargeKeep rejected | **FastStripe** ([stripe.fast.ai](https://stripe.fast.ai/)) |

**FastStripe over the official `stripe-python` SDK:** chosen for AnswerDotAI/FastHTML
alignment, async-native fit with SKUEL's "async at I/O" rule, lightweight deps
(`fastcore`/`fastspec`/`httpx`), and pinned-snapshot determinism (matches "code is
environment-agnostic"). Its surface is small under ChargeKeep-first — residual reads or
the fallback adapter only.

## Architecture

**Hexagonal placement.** `chargekeep_client.py` is an outbound adapter (sibling of
`firefly_client.py` / `invoice_renderer.py`); routes and services depend on the
`BillingProvider` Protocol in `core/ports/billing_protocols.py`, never the concrete client.

**Flow.**
```
User upgrades → ChargeKeep hosted checkout (uses SKUEL's Stripe underneath)
   ├─ event New Payment        → verify → map customer→user → update_role(MEMBER)
   ├─ event New Payment        → firefly_client.create_transaction(book="skuel", deposit, external_id)
   ├─ (no cancel event)        → nightly reconcile: lapsed subscription → MEMBER→REGISTERED
   └─ ChargeKeep issues the invoice/receipt + hosts the customer portal

Tier model: MEMBER is the only paid tier (one ChargeKeep plan). REGISTERED is the free
trial; TEACHER and ADMIN are admin-granted promotions, never purchased — billing never
touches them.
```

**Idempotency.** Webhooks are replay-safe via ChargeKeep event id; Firefly deposits dedupe
on `external_id` (existing `find_transaction_by_external_id`).

## Consequences

### Positive
- **Minimal SKUEL code in the money path** — one webhook consumer + a role map. No
  checkout-session code, no subscription state machine, no dunning, no customer-portal UI.
- **Deletes more than ADR-052 projected** — invoices move to ChargeKeep (decided 2026-05-24),
  so the local WeasyPrint invoice module is removed on top of ADR-052's ~3,400-LOC cut; and with
  the custom finance UI eliminated (roadmap open question 5), the whole `finance_ui.py` +
  `ui/finance/` package + legacy finance services go too, and `firefly_client` is trimmed to
  write-only. Pending only the spike's invoice-quality confirmation (check 8).
- **$0 marginal cost** — lifetime subscription already owned.
- **Clean swap insurance** — `BillingProvider` port isolates the vendor; FastStripe-direct
  can replace it adapter-only if ChargeKeep is rejected or sunset.

### Negative
- **Smaller vendor in the critical money path.** ChargeKeep is AppSumo-tier, not Stripe
  Billing or Chargebee. Mitigated by the spike gate + the swappable port.
- **No downgrade event (likely).** ChargeKeep's public (Zapier-mirrored) catalog exposes only
  *creation* triggers — New Lead / New Subscription / New Payment — and **no cancellation,
  expiration, failure, or refund event.** Role *grant* is event-driven; role *revocation*
  (MEMBER → REGISTERED) likely needs a **nightly reconciliation job** polling active
  subscriptions, unless the in-account native webhook API exposes a cancel event. Open spike
  item. Also: New Subscription fires on unpaid trial start, so the grant must key on **New
  Payment**, not New Subscription.
- **New required dependency** for the SaaS upgrade flow (orthogonal to `INTELLIGENCE_TIER`;
  finance/billing is admin- and payment-scoped).
- **Two secrets to manage** — ChargeKeep API key + webhook signing secret (via
  `get_credential()`, SKUEL019). Firefly PATs already exist.
- **Amends an Accepted ADR.** ADR-052's Stripe-direct payment design is superseded *for the
  billing layer only*; its Firefly-ledger decision stands.

### Neutral
- **Firefly unchanged** as the ledger. Phases 1–2 (Docker stack + `firefly_client`) already
  landed.

## Alternatives considered

1. **Stripe-direct via FastStripe (ADR-052 as written).** Rejected as the *default* — more
   code in the money path, keeps the local invoice module, ignores owned maintained
   software. Retained as the **fallback** if the spike rejects ChargeKeep.
2. **Official `stripe-python` SDK.** Rejected vs FastStripe on ecosystem/async/footprint
   grounds (see above).
3. **Chargebee / heavier billing SaaS.** Rejected — recurring cost for capability we already
   own via ChargeKeep.
4. **Keep manual admin role-granting indefinitely.** Rejected — does not scale past a
   founder-operated beta; the spike is cheap insurance regardless of launch timing.

## Verification (post-spike, when implemented)

- Spike checklist in `roadmap/finance-billing-migration.md` passes (webhook catalog +
  signatures, metadata pass-through, fund-flow model, invoicing quality, cancellation
  semantics).
- ChargeKeep sandbox: trigger `subscription.active` → SKUEL user role flips to MEMBER;
  `subscription.cancelled` → reverts to REGISTERED.
- `payment.succeeded` → deposit visible in Firefly `skuel` book; replaying the same event
  creates no duplicate (external-id dedupe).
- Webhook signature-verification rejects an unsigned/tampered payload.

## References

- [ADR-052 Firefly III Finance Integration](ADR-052-firefly-iii-finance-integration.md)
- `roadmap/finance-billing-migration.md` — phased plan + spike checklist
- FastStripe — https://stripe.fast.ai/
- ChargeKeep — https://www.chargekeep.com/help/ , API https://www.chargekeep.com/api
- `core/ports/finance_protocols.py` — existing `FireflyOperations` (reused for revenue sync)
- `memory/feedback_leverage_maintained_software.md` — the principle this ADR applies
