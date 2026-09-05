---
title: "Decision Points — Per-user Intelligence Tier"
updated: 2026-09-05
status: "decision needed"
trigger: "billing model defined — which UserRole levels get the FULL tier"
check: "business decision; get_user_intelligence_tier stays in PLANNED_METHODS until wired"
---

# Decision Points

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

These items are blocked on business decisions, not engineering complexity. The code stubs exist; they need a decision to wire up.

---

## 4. Per-user Intelligence Tier

**Why deferred**: The system-wide `INTELLIGENCE_TIER` env var toggle (CORE vs FULL) works correctly. Per-user tier control requires a billing model — specifically, which features are free vs paid — and that model has not been defined.

**The problem**: `core/services/intelligence_tier_service.py` implements the pure function `get_user_intelligence_tier(system_tier, user_role)` — system tier is the ceiling, REGISTERED gets CORE, MEMBER+ get the system tier.
It is not wired anywhere (registered in the bloat detector's PLANNED tier). Currently all users get the same tier controlled by the env var.

**What to do**:

1. Define the billing model: which `UserRole` levels get FULL tier? (e.g., MEMBER and above?)
2. Wire the tier resolution into the AI-gating points below `services_bootstrap/` — replace the
   env-var-only check with `get_user_intelligence_tier(system_tier, user.user_role)`.
3. Update route middleware to resolve the user's role at service-selection time (requires auth
   context before route handlers run).

**Enable when**: Billing model defined — specifically, which subscription tier gets AI features.

---
