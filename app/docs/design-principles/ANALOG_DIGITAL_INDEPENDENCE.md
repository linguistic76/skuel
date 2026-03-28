---
title: "Design Principle: Analog-Digital Independence"
updated: 2026-03-28
status: current
category: design-principles
tags: [design, principles, analog, digital, intelligence-tier]
related: [docs/architecture/ANALOG_DIGITAL_ARCHITECTURE.md, docs/architecture/GRACEFUL_DEGRADATION_ARCHITECTURE.md]
---

# Analog-Digital Independence

> The Analog layer is not a degraded version of the Digital layer — it is the foundation.

## Statement

SKUEL separates runtime into two independent layers. The **Analog layer** (graph structure, CRUD, ingestion, keyword search, analytics, user context) is complete on its own — fully functional at $0 with no API keys. The **Digital layer** (embeddings, vector search, LLM feedback, Askesis) enhances the Analog layer with machine understanding. Neither layer depends on the other for correctness.

## Why This Matters

API dependencies are fragile, expensive, and outside SKUEL's control. An app that stops working when OpenAI has an outage is not an app — it's a client. The Analog layer ensures SKUEL always works. The Digital layer makes it smarter.

For the current single-user phase, this means SKUEL is always available for learning, tracking, and organizing — even if API budgets are paused or services are down.

## In Practice

- **Toggle:** `INTELLIGENCE_TIER=core` (Analog only, $0) vs `INTELLIGENCE_TIER=full` (Analog + Digital)
- **Required at bootstrap (Analog):** Neo4j only
- **Required at bootstrap (Digital):** OpenAI, Deepgram, HuggingFace — but only when `INTELLIGENCE_TIER=full`
- **Feature completeness:** Search works (keyword), analytics work (graph queries), user context works (MEGA-QUERY) — all without AI
- **No conditional logic in services:** Services don't check `if ai_available`. The intelligence tier is set at bootstrap; services that need AI are simply not instantiated in core tier.

## Enforcement

- **`INTELLIGENCE_TIER` env var:** Binary toggle, no partial states
- **Service composition:** `services_bootstrap/compose.py` conditionally wires AI services based on tier
- **Testing:** Core-tier test suite runs without any API keys configured

## See Also

- `/docs/architecture/ANALOG_DIGITAL_ARCHITECTURE.md` — full architecture document
- `/docs/architecture/GRACEFUL_DEGRADATION_ARCHITECTURE.md` — implementation details
- `/docs/decisions/ADR-043-intelligence-tier-toggle.md` — decision record
- `CLAUDE.md` § "Analog + Digital Runtime Architecture"
