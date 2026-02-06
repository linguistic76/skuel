# Hyperview Mobile Strategy

**Status:** Groundwork phase (Feb 2026)
**ADR:** [ADR-039](/docs/decisions/ADR-039-hyperview-mobile-strategy.md)

## Vision

SKUEL serves two formats from one backend:

| Platform | Format | Client | Framework |
|----------|--------|--------|-----------|
| **Web** | HTML | Browser | HTMX |
| **Mobile** | HXML | React Native | Hyperview |

Both formats follow the same philosophy: **server-driven hypermedia**. The server renders the UI, the client renders it natively. No client-side business logic.

## Architecture

```
                    FastHTML Backend
                    ┌─────────────┐
                    │  Services   │  (domain logic, Neo4j, etc.)
                    │  (shared)   │
                    └──────┬──────┘
                           │
                    ┌──────┴──────┐
                    │   Routes    │  (same route handlers)
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              │                         │
       ┌──────┴──────┐          ┌──────┴──────┐
       │ HTML Render │          │ HXML Render │
       │  (FastHTML)  │          │ (core/hxml) │
       └──────┬──────┘          └──────┬──────┘
              │                         │
       ┌──────┴──────┐          ┌──────┴──────┐
       │   Browser   │          │ React Native│
       │   + HTMX    │          │ + Hyperview │
       └─────────────┘          └─────────────┘
```

## Content Negotiation

```python
from core.hxml import is_hyperview_client

@rt("/daily-plan")
async def daily_plan(request: Request):
    plan = await service.get_daily_plan(user_uid)

    if is_hyperview_client(request):
        return hxml_daily_plan(plan)  # Returns HXML
    else:
        return html_daily_plan(plan)  # Returns HTML (current)
```

The `Accept` header determines the response format:
- `text/html` (default) -> HTML response
- `application/vnd.hyperview+xml` -> HXML response

## HXML vs HTML

| Concept | HTML | HXML |
|---------|------|------|
| Container | `<div>` | `<view>` |
| Text | Bare text anywhere | `<text>` wrapper required |
| Links | `<a href="...">` | `<behavior trigger="press" href="...">` |
| Styles | CSS cascade | Explicit per-element, no cascade |
| Pages | `<html><body>` | `<doc><screen>` |

## Current Files

| File | Purpose |
|------|---------|
| `core/hxml/__init__.py` | Package exports |
| `core/hxml/elements.py` | HXML element builders (Doc, Screen, View, Text, Style, Behavior) |
| `core/hxml/negotiation.py` | Content negotiation (is_hyperview_client) |

## Roadmap

1. **Groundwork** (current) - Element builders, content negotiation, documentation
2. **Proof of Concept** - One screen served as HXML, tested with Hyperview demo client
3. **React Native Client** - Minimal app shell with Hyperview renderer
4. **Feature Parity** - Key screens available in both HTML and HXML

## References

- [Hyperview Documentation](https://hyperview.org/)
- [Hyperview GitHub](https://github.com/Instawork/hyperview) (~1,600 stars, MIT license)
- [HTMX](https://htmx.org/) — web equivalent of Hyperview's philosophy
