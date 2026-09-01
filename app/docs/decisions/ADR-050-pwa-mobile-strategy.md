---
title: "ADR-050: PWA as Mobile Strategy"
updated: 2026-09-01
status: current
category: decisions
tags: [adr, decisions, mobile, pwa, service-worker]
---

# ADR-050: PWA as Mobile Strategy

**Status:** Accepted

**Date:** 2026-03-16

**Decision Type:** Pattern/Practice

---

## Context

ADR-039 chose Hyperview for mobile: "one backend, two formats" (HTML for web, HXML for mobile). In practice, HXML requires a parallel rendering layer for every UI component — a React Native client, two markup formats to maintain, and app store deployment. For a solo analog-to-digital founder, this is an expensive path with no current consumers (zero routes serve HXML, zero tests exist).

SKUEL's design principles have since crystallized:
- **Open web standards** as the aligning factor — HTML is the format
- **No app store dependency** — not designing for Apple/Google ecosystems
- **Linux mobile support** — PWAs work natively on postmarketOS/Mobian browsers and F-Droid-friendly browsers
- **No design divergence** — one format (HTML), not two (HTML + HXML)

PWA extends SKUEL's existing HTML/HTMX architecture with installability, offline support, and push notifications using pure web standards. No new rendering layer. No React Native dependency.

---

## Decision

**Adopt Progressive Web App (PWA) as SKUEL's mobile strategy. Remove Hyperview groundwork.**

Implementation:
- Web app manifest (`/manifest.json`) for installability
- Service worker with network-first strategy for HTML/HTMX, cache-first for static assets
- Offline fallback page when network is unavailable and no cache exists
- PWA meta tags in base page head

**Hyperview groundwork removed:**
- `core/hxml/` package (element builders)
- `adapters/inbound/negotiation.py` (content negotiation) <!-- historical -->
- `docs/architecture/HYPERVIEW_STRATEGY.md` (strategy doc) <!-- historical -->

---

## Alternatives Considered

### Alternative 1: Hyperview (HXML)
**Description:** Server-rendered HXML for native mobile via React Native + Hyperview client.

**Why superseded:**
- Requires maintaining two rendering formats (HTML + HXML) for every UI component
- Requires React Native client app and app store deployment
- ~158 lines of groundwork code with zero consumers after months
- Contradicts "open web standards" and "no app store dependency" principles
- Locks into Apple/Google ecosystems for distribution

### Alternative 2: Capacitor / Cordova wrapper
**Description:** Wrap the web app in a native shell for app store distribution.

**Why rejected:** Still requires app store deployment. Adds a wrapper layer with no benefit over a PWA. Does not align with open web standards.

### Alternative 3: No mobile strategy (responsive web only)
**Description:** Rely entirely on responsive CSS in mobile browsers.

**Why rejected:** PWA adds installability and offline support with minimal effort on top of what responsive web already provides. The incremental cost is low; the user experience improvement is meaningful.

---

## Consequences

### Positive
- One format (HTML) for all platforms — zero rendering duplication
- No app store dependency — install directly from the browser
- Works on Linux mobile (postmarketOS, Mobian) and F-Droid browsers
- Leverages existing HTMX/FastHTML architecture unchanged
- Offline support via service worker caching
- Push notifications available via Web Push API (future)

### Negative
- iOS PWA support has limitations (no push notifications before iOS 16.4, limited background sync)
- No access to some native device APIs (NFC, Bluetooth, etc.)
- Less discoverable than app store listings

### Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| iOS PWA limitations | Medium | Low | SKUEL targets open platforms; iOS is not the primary audience |
| Browser drops PWA support | Very Low | High | PWA is a W3C standard with broad industry adoption |
| Offline data conflicts | Low | Medium | Network-first strategy ensures fresh data when online |

---

## Implementation Details

### Files
- `static/manifest.json` — Web app manifest
- `static/service-worker.js` — Service worker (network-first HTML, cache-first static)
- `static/offline.html` — Offline fallback page
- `static/icons/` — App icons (192px, 512px, maskable, favicons)
- `ui/layouts/base_page.py` — PWA headers + service worker registration
- `ui/theme.py` — `pwa_headers()` function (pre-existing)

### Service Worker Strategy
- **HTML/HTMX requests:** Network-first, cache response for offline fallback
- **Static assets (`/static/*`):** Cache-first for performance
- **Offline navigation:** Falls back to `/offline.html`
- **Cache versioning:** `CACHE_VERSION` string for cache busting on deploy

---

## References
- [MDN: Progressive Web Apps](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps)
- [web.dev: Web App Manifest](https://web.dev/learn/pwa/web-app-manifest)
- [W3C: Web App Manifest Spec](https://www.w3.org/TR/appmanifest/)
- [MDN: Service Worker API](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API)
