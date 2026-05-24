# ChargeKeep Spike — Action Items for Mike

*Created: 2026-05-24 · Status: **Waiting on Mike** · Unblocks: [ADR-062](../decisions/ADR-062-chargekeep-billing-layer.md)*

This is the hands-on half of the Phase 3a spike — the part that needs your ChargeKeep account
and that I can't do from here. The desk-research half is done and written up in
[`finance-billing-migration.md` → Phase 3a findings](finance-billing-migration.md#phase-3a--desk-research-findings-2026-05-24).

**Why this matters:** completing the one task below flips [ADR-062](../decisions/ADR-062-chargekeep-billing-layer.md)
from *Proposed* to **Accepted** (build ChargeKeep-first) or **Rejected** (fall back to
Stripe-direct). Nothing downstream gets built until then.

---

## TL;DR

Do **one** thing — capture a real ChargeKeep webhook with a throwaway inspector — and send me
**three** answers. No credential sharing required.

## The task: capture a live webhook (~5 min)

1. Open **[webhook.site](https://webhook.site)** in a browser → it shows a **unique URL** at the
   top. Copy it.
2. In ChargeKeep → **Settings → Events / Webhooks** (the "Event Subscriptions" area) → **add a
   webhook/subscription** pointing at that webhook.site URL, for the **New Payment** event
   (also add **New Subscription** if offered).
3. Trigger one event — make a small **test-mode** (or real $1) payment through one of your
   ChargeKeep checkout forms.
4. Go back to the webhook.site tab — your event will appear on the left. Open it.

## The three things to send me

1. 🔴 **The event dropdown list.** While adding the webhook in step 2, what event types does
   ChargeKeep offer? **Most important: is there a "cancelled", "expired", or "ended" event?**
   (Public Zapier data shows only *New Lead / New Subscription / New Payment* — I need to know
   if the native dashboard exposes more.)
2. 🔴 **Is there a "signing secret" field** when you set up the webhook? If yes, note it exists
   (don't paste the secret itself) and tell me the name of any **signature header** you see on
   the captured request.
3. 🔴 **The captured request from webhook.site** — paste both the **Headers** block and the
   **JSON Body**. (I'm looking for: a signature header, the contact/customer id, and whether the
   `customField1..5` values ride along.)

That's the whole gate. Everything below is a bonus if you happen to be in the dashboard anyway.

## Bonus checks (helpful, not blocking)

- **Stripe connection** (Settings → integrations): confirm ChargeKeep is wired to **your own
  Stripe account** so payouts land in your Stripe (clean to reconcile into Firefly).
- **Auth header**: generate a **test API key** (API panel) and note whether calls use
  `Authorization: Bearer …` or `X-API-Key`.
- **Custom field on checkout**: in the payment-form builder, can you add a **prefillable hidden
  field** (maps to `customField1..5`) to carry a SKUEL `user_uid`?
- **Customer portal**: confirm the hosted "manage subscription / update card / cancel" portal
  exists and is brandable.
- **Invoice PDF**: generate a sample invoice/receipt — is the branding / line items / tax good
  enough to replace SKUEL's local WeasyPrint invoice module? (PDF is fine — finance is the
  sanctioned PDF exception.)

## What each answer unlocks

| Your finding | What it decides |
|---|---|
| A **cancel/expire event exists** | Downgrade (MEMBER→REGISTERED) is event-driven; **no reconciliation job needed.** |
| **No cancel event** | We add a small **nightly reconciliation job** that polls active subscriptions and downgrades lapsed MEMBERs. Still fine. |
| **Signing secret exists** | Webhook handler verifies the signature (standard, secure). |
| **No signing** | Fall back to an IP allowlist or a secret path segment on the webhook URL (weaker but workable). |
| **`customField` rides on the payload** | Clean customer→user mapping via `user_uid`. |
| **It doesn't** | Map via the **contact id captured at checkout-return**, stored as `chargekeep_customer_id` on `User` (the robust default anyway). |

## Alternative (if you'd rather I probe the API)

Drop a ChargeKeep **API key** into the local `.env`. I'll read it via `get_credential()`, never
echo it, and run **read-only** calls (list event subscriptions, products) — no writes. The
webhook.site route is faster and needs no key, so start there; this is the fallback.

## Links

- [`finance-billing-migration.md`](finance-billing-migration.md) — full plan + findings
- [ADR-062: ChargeKeep as the Billing Layer](../decisions/ADR-062-chargekeep-billing-layer.md) *(Proposed)*
- [webhook.site](https://webhook.site) · [ChargeKeep API](https://www.chargekeep.com/api) · [ChargeKeep on Zapier](https://zapier.com/apps/chargekeep/integrations)
