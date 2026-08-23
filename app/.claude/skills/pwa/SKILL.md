---
title: PWA Skill
description: Expert guide for SKUEL's Progressive Web App — service worker, manifest, offline support, caching strategies
trigger: Use when working on service worker, web app manifest, offline support, caching, PWA installability, push notifications, or when the user mentions PWA, service worker, offline, installable, or mobile strategy.
---

# PWA (Progressive Web App) Skill

## Quick Reference

SKUEL is a PWA — installable from the browser, works offline, no app store. One format (HTML), one backend, open web standards.

**ADR:** [ADR-050](/docs/decisions/ADR-050-pwa-mobile-strategy.md)
**Architecture:** [PWA Architecture](/docs/architecture/PWA_ARCHITECTURE.md)

## File Map

| File | Purpose |
|------|---------|
| `static/manifest.json` | Web app manifest (installability) |
| `static/service-worker.js` | Caching + offline support |
| `static/offline.html` | Offline fallback (self-contained) |
| `static/icons/` | App icons (192px, 512px, maskable, favicons) |
| `ui/theme.py` | `pwa_headers()` — meta tags + manifest link |
| `ui/layouts/base_page.py` | Integrates `pwa_headers()` + SW registration + offline banner |
| `adapters/inbound/pwa_routes.py` | Root-level routes for manifest, SW, offline |

## Service Worker Caching Strategies

```
/static/*  ──→  Cache-first   (fast loads, assets rarely change)
HTML pages ──→  Network-first (fresh content when online, cache when offline)
HTMX frags ──→  Network-first (partial updates need server state)
Offline    ──→  /offline.html (self-contained fallback)
```

### Key Constants

```javascript
const CACHE_VERSION = 'skuel-v1';   // Bump to bust all caches on deploy
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`;
```

### Pre-cached Assets (install event)

```javascript
const PRECACHE_URLS = [
  '/offline.html',
  '/static/css/main.css',
  '/static/css/hierarchy.css',
  '/static/js/skuel.js',
  '/static/js/focus_trap.js',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png',
];
```

## Common Tasks

### Adding a new static asset to offline cache

1. Add the path to `PRECACHE_URLS` in `static/service-worker.js`
2. Bump `CACHE_VERSION` (e.g., `'skuel-v1'` → `'skuel-v2'`)

### Changing any `/static/` file — bump `CACHE_VERSION`

`cacheFirst()` caches **every** `/static/` response, not just `PRECACHE_URLS`
entries. So editing any file served under `/static/` — page-local bundles like
`today.js` and the generated `output.css` included — requires bumping
`CACHE_VERSION` in the same change, or installed clients keep serving the stale
asset indefinitely. PRECACHE_URLS membership is not the trigger.

### Forcing cache refresh on deploy

Change `CACHE_VERSION` in `static/service-worker.js`. The `activate` handler automatically deletes old caches.

### Adding PWA headers to a new page type

```python
from ui.theme import pwa_headers

# In any <head> builder:
Head(
    *pwa_headers(),
    # ... other elements
)
```

`pwa_headers()` returns: theme-color meta, apple-mobile-web-app meta, manifest link, icon links.

### Updating the manifest

Edit `static/manifest.json`. Key fields:
- `name` / `short_name` — app name
- `start_url` — entry point when installed
- `display` — `standalone` (no browser chrome) or `minimal-ui`
- `theme_color` — browser chrome / status bar color
- `icons` — array of icon objects (need 192px + 512px minimum)

### Replacing placeholder icons

Replace files in `static/icons/` with branded versions. Required sizes:
- `icon-192x192.png` — standard icon
- `icon-512x512.png` — high-res / splash screen
- `icon-512x512-maskable.png` — adaptive icon with safe zone padding
- `favicon-32x32.png` and `favicon-16x16.png` — browser tab

## Root-Level Routes

The service worker must be served from root scope (`/service-worker.js`, not `/static/service-worker.js`) to control the entire app. Three routes in `adapters/inbound/pwa_routes.py`, registered in Section 4 of `_wire_all_routes()`:

```python
# adapters/inbound/pwa_routes.py
from starlette.responses import FileResponse

_static_dir = Path.cwd() / "static"

def create_pwa_routes(rt):
    @rt("/manifest.json")
    async def pwa_manifest(request):
        return FileResponse(_static_dir / "manifest.json", media_type="application/manifest+json")

    @rt("/service-worker.js")
    async def pwa_service_worker(request):
        return FileResponse(_static_dir / "service-worker.js", media_type="application/javascript")

    @rt("/offline.html")
    async def pwa_offline(request):
        return FileResponse(_static_dir / "offline.html", media_type="text/html")
```

## Offline Status Indicator

When the browser loses connectivity, a fixed yellow banner appears at the bottom of every page: "You are offline. Some features may be unavailable." It auto-dismisses when connectivity returns.

**Implementation:**
- Alpine.js component `offlineIndicator` in `static/js/skuel.js` — listens to `online`/`offline` window events
- Banner rendered in `ui/layouts/base_page.py` with `x-data="offlineIndicator"` / `x-show="isOffline"`
- Separate from the service worker's `/offline.html` fallback (which handles uncached navigation requests)

## Testing

1. **Manifest:** Chrome DevTools → Application → Manifest
2. **Service Worker:** DevTools → Application → Service Workers (registered + active)
3. **Offline:** DevTools → Network → Offline checkbox
   - Cached pages load from cache
   - Uncached pages show offline fallback
4. **HTMX:** Verify partial updates still work with SW active
5. **Lighthouse:** Run PWA audit — should pass installability + offline

## Design Decisions

- **Network-first for HTML** — SKUEL is server-rendered, not SPA. Content must be fresh when online.
- **Cache-first for static** — CSS/JS/vendor assets are versioned and rarely change mid-session.
- **No app store** — aligns with open web standards, Linux mobile support (postmarketOS, Mobian).
- **No second rendering format** — PWA uses the same HTML as web.

## Deep Dive Resources

- [PWA Architecture](/docs/architecture/PWA_ARCHITECTURE.md) — full architecture doc
- [ADR-050](/docs/decisions/ADR-050-pwa-mobile-strategy.md) — decision record
- [MDN: Progressive Web Apps](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps)
- [MDN: Service Worker API](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API)
