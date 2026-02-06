---
title: ADR-039: Hyperview as Mobile Strategy
updated: 2026-02-06
status: current
category: decisions
tags: [adr, decisions, mobile, hyperview, hypermedia]
related: []
---

# ADR-039: Hyperview as Mobile Strategy

**Status:** Accepted (groundwork phase)

**Date:** 2026-02-06

**Decision Type:** Pattern/Practice

**Related ADRs:**
- Related to: ADR-022 (graph-native authentication)

---

## Context

**What is the issue we're facing?**

SKUEL is a web application using FastHTML + HTMX — a server-driven hypermedia architecture where the server renders HTML and HTMX handles dynamic updates. This works well for desktop and mobile browsers, but native mobile apps offer superior performance, offline capability, and platform integration.

The traditional approach to native mobile would require a REST/GraphQL API + React Native/Swift/Kotlin client — a separate codebase with duplicated logic and a fundamentally different architecture (client-driven JSON vs server-driven hypermedia).

[Hyperview](https://hyperview.org/) (by Instawork, MIT license) solves this by bringing the HTMX philosophy to native mobile. Instead of HTML, the server serves HXML — a purpose-built XML format for describing native mobile UIs. A React Native client renders HXML into native components, just as a browser renders HTML.

**Key alignment with SKUEL:**
- Same server-driven hypermedia philosophy as HTMX
- One backend serves both formats (HTML for web, HXML for mobile)
- Zero client-side business logic — all logic stays in Python
- Respects and supports open-source ecosystem
- ~1,600 GitHub stars, actively maintained (last release Feb 2025)

---

## Decision

**Adopt Hyperview as SKUEL's mobile strategy.**

The FastHTML backend will serve HXML responses alongside HTML, determined by content negotiation. One backend, two rendering formats, zero duplicated logic.

**Implementation phases:**
1. **Groundwork (current):** HXML element builders, content negotiation utility, strategy documentation
2. **Proof of concept:** One screen (e.g., daily plan) served as HXML, tested with Hyperview demo client
3. **React Native client:** Minimal app shell with Hyperview renderer
4. **Feature parity:** All key screens available in both HTML and HXML

**Key technical decisions:**
- Content negotiation via `Accept: application/vnd.hyperview+xml` header
- HXML builders in `core/hxml/` mirror FastHTML's composable FT pattern
- Routes remain unchanged — response format selected at the rendering layer
- Services and domain logic are completely format-agnostic (already true)

**Files:**
- `core/hxml/elements.py` — HXML element builders
- `core/hxml/negotiation.py` — Content negotiation utility
- `docs/architecture/HYPERVIEW_STRATEGY.md` — Strategy documentation

---

## Alternatives Considered

### Alternative 1: Progressive Web App (PWA)
**Description:** Enhance the existing web app with service workers, manifest, and offline capability.

**Pros:**
- Zero additional client code
- Works immediately in browsers
- No app store deployment

**Cons:**
- Inconsistent offline support across browsers (especially iOS)
- Limited device hardware access
- Not truly native — performance and UX gaps
- iOS PWA support significantly behind Android

**Why rejected:** PWA is complementary (and can be added later) but doesn't achieve native app quality. Hyperview provides genuine native rendering while maintaining the server-driven architecture.

### Alternative 2: Traditional React Native + REST API
**Description:** Build a standard React Native app consuming JSON API endpoints.

**Pros:**
- Large ecosystem and community
- Full control over client-side behavior
- Rich animation and gesture libraries

**Cons:**
- Duplicates business logic between Python backend and JS client
- Requires separate API layer (REST/GraphQL) alongside HTML routes
- Two codebases to maintain
- Fundamentally different architecture from HTMX approach

**Why rejected:** Contradicts SKUEL's "One Path Forward" philosophy. Would create two parallel architectures (server-driven HTML + client-driven JSON) instead of one unified hypermedia approach.

### Alternative 3: No Mobile Strategy (web-only)
**Description:** Rely on responsive web design for mobile access.

**Pros:**
- Simplest — no additional work
- Already functional

**Cons:**
- No offline capability
- No native platform integration
- Lower engagement than native apps
- Mobile browser limitations

**Why rejected:** SKUEL is a daily-use application. Native mobile access is a legitimate need, not a luxury.

---

## Consequences

### Positive Consequences
- One backend, two formats — minimal code duplication
- Server-driven architecture maintained for both web and mobile
- Instant deployment to mobile (no app store review for content changes)
- Aligns with SKUEL's hypermedia-first philosophy
- Supports open-source ecosystem (Hyperview is MIT licensed)

### Negative Consequences
- Requires building a React Native client app (initial investment)
- HXML has a smaller community than HTML/React Native
- Two rendering formats to maintain (HTML + HXML)
- App store deployment required for initial install

### Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Hyperview project abandoned | Low | High | MIT license allows forking; groundwork is minimal investment |
| HXML limitations for complex UI | Medium | Medium | Hyperview supports custom components for edge cases |
| React Native ecosystem churn | Medium | Low | Hyperview abstracts away most RN complexity |

---

## Implementation Details

### Code Location
- Primary: `core/hxml/` package
- Strategy doc: `docs/architecture/HYPERVIEW_STRATEGY.md`
- Tests: `tests/unit/test_hxml_elements.py` (future)

### Testing Strategy
- [ ] Unit tests for HXML element builders
- [ ] Integration test: content negotiation returns correct format
- [ ] Manual testing with Hyperview demo client (Phase 2)

---

## Future Considerations

### When to Revisit
- If Hyperview project becomes unmaintained (check annually)
- If React Native is superseded by a better cross-platform framework
- If SKUEL's mobile needs change significantly

### Evolution Path
1. Groundwork (Feb 2026) — element builders, content negotiation
2. Proof of concept — one HXML screen with demo client
3. React Native app — minimal shell, Hyperview renderer
4. Feature parity — all key screens in both formats

---

## References
- [Hyperview Documentation](https://hyperview.org/)
- [Hyperview GitHub](https://github.com/Instawork/hyperview)
- [HTMX — the web equivalent](https://htmx.org/)
- [Hypermedia Systems (book)](https://hypermedia.systems/)
