---
title: PWA Architecture
updated: 2026-03-16
status: current
category: architecture
tags: [pwa, service-worker, offline, mobile]
related_skills: [fasthtml, pwa]
related_adrs: [ADR-050]
---
# PWA Architecture

**ADR:** [ADR-050: PWA Mobile Strategy](/docs/decisions/ADR-050-pwa-mobile-strategy.md)
## Related Skills

For implementation guidance, see:
- [@fasthtml](../../.claude/skills/fasthtml/SKILL.md)


## Overview

SKUEL is a Progressive Web App (PWA). Users can install it from the browser on any platform — desktop, Android, Linux mobile (postmarketOS, Mobian), iOS. No app store required.

PWA extends SKUEL's existing HTML/HTMX architecture with three capabilities:

| Capability | Mechanism |
|------------|-----------|
| **Installability** | Web app manifest (`/manifest.json`) |
| **Offline support** | Service worker (`/service-worker.js`) |
| **App-like UX** | `display: standalone`, theme color, splash screen |

## Architecture Diagram

```
Browser / Installed PWA
┌──────────────────────────────┐
│  HTML/HTMX (same as web)     │
│  ┌────────────────────────┐  │
│  │   Service Worker        │  │
│  │   ┌──────────────────┐ │  │
│  │   │ Static Cache     │ │  │  cache-first: /static/*
│  │   │ (CSS, JS, icons) │ │  │
│  │   ├──────────────────┤ │  │
│  │   │ Runtime Cache    │ │  │  network-first: HTML, HTMX
│  │   │ (pages, frags)   │ │  │
│  │   └──────────────────┘ │  │
│  └────────────────────────┘  │
└──────────────────────────────┘
              │
              ▼
      FastHTML Backend
      (unchanged — same server)
```

## Service Worker Strategy

**File:** `/static/service-worker.js`

### Caching Strategies

| Request Type | Strategy | Rationale |
|-------------|----------|-----------|
| `/static/*` (CSS, JS, vendor, icons) | **Cache-first** | Versioned assets rarely change; fast loads |
| HTML navigation | **Network-first** | Content must be fresh when online |
| HTMX fragments (`HX-Request` header) | **Network-first** | Partial updates need server state |
| Everything else | **Network-first** | Default to freshness |

### Cache Names

```javascript
// One constant to bump; the other two DERIVE from it. The live value is in
// static/service-worker.js — deliberately not repeated here, since a version
// transcribed into a doc goes stale on the next bump.
const CACHE_VERSION = 'skuel-vN';                    // Bump to bust all caches
const STATIC_CACHE = `${CACHE_VERSION}-static`;      // Pre-cached + static assets
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`;    // Network-first responses
```

### Pre-cached Assets

These are cached during the `install` event:

- `/offline.html` — offline fallback page
- `/static/css/main.css`, `/static/css/hierarchy.css`
- `/static/js/skuel.js`, `/static/js/focus_trap.js`
- `/static/icons/icon-192x192.png`, `/static/icons/icon-512x512.png`

### Offline Behavior

When offline and no cached version exists for a navigation request, the service worker serves `/offline.html` — a self-contained page with no external dependencies that tells the user they're offline.

When offline and a cached version exists, the cached version is served transparently.

### Offline Status Indicator

In addition to the service worker's `/offline.html` fallback for uncached navigation, SKUEL shows a fixed yellow banner at the bottom of every page when the browser is offline. This uses the `offlineIndicator` Alpine.js component (`static/js/skuel.js`) which listens to `online`/`offline` window events and reactively shows/hides the banner. The banner is rendered in `ui/layouts/base_page.py`.

### Cache Busting on Deploy

Change `CACHE_VERSION` in `service-worker.js`. The `activate` event handler deletes all caches that don't match the current version names.

**When a bump is mandatory, not optional:** `cacheFirst()` caches *every*
`/static/` response, not just `PRECACHE_URLS` entries. So **any** change to a
file served under `/static/` — including page-local bundles that were never
precached (`output.css`, `today.js`) — must bump `CACHE_VERSION` in the same
change, or installed clients keep serving the stale asset indefinitely.
PRECACHE_URLS membership is not the trigger.

## Web App Manifest

**File:** `/static/manifest.json`
**Served at:** `/manifest.json` (root-level route in bootstrap.py)

```json
{
  "name": "SKUEL",
  "short_name": "SKUEL",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#2563eb",
  "icons": [...]
}
```

### Icons

| File | Size | Purpose |
|------|------|---------|
| `icon-192x192.png` | 192x192 | Standard app icon |
| `icon-512x512.png` | 512x512 | High-res / splash |
| `icon-512x512-maskable.png` | 512x512 | Adaptive icon (safe zone) |
| `favicon-32x32.png` | 32x32 | Browser tab |
| `favicon-16x16.png` | 16x16 | Browser tab (small) |

**Location:** `/static/icons/`

Current icons are blue placeholders with "S". Replace with branded icons when ready.

## Integration Points

### Base Page (`ui/layouts/base_page.py`)

`build_head()` includes `*pwa_headers()` from `ui/theme.py`:
- `<meta name="theme-color">` — browser chrome color
- `<meta name="apple-mobile-web-app-capable">` — iOS install support
- `<link rel="manifest">` — manifest link
- `<link rel="apple-touch-icon">` — iOS home screen icon
- Favicon links

`BasePage()` body includes service worker registration:
```javascript
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/service-worker.js');
}
```

### Bootstrap Routes (`scripts/dev/bootstrap.py`)

Three root-level routes serve PWA files from `/static/`:

| Route | File | Media Type |
|-------|------|------------|
| `/manifest.json` | `static/manifest.json` | `application/manifest+json` |
| `/service-worker.js` | `static/service-worker.js` | `application/javascript` |
| `/offline.html` | `static/offline.html` | `text/html` |

The service worker **must** be served from the root scope (`/`) to control the entire app. Serving from `/static/service-worker.js` would limit its scope to `/static/`.

### Theme (`ui/theme.py`)

`pwa_headers()` generates all PWA-related `<meta>` and `<link>` tags. It accepts `app_name` and `theme_color` parameters.

## File Map

| File | Purpose |
|------|---------|
| `static/manifest.json` | Web app manifest |
| `static/service-worker.js` | Service worker (caching, offline) |
| `static/offline.html` | Offline fallback page |
| `static/icons/` | App icons (5 files) |
| `ui/theme.py` | `pwa_headers()` function |
| `ui/layouts/base_page.py` | PWA header integration + SW registration + offline banner |
| `scripts/dev/bootstrap.py` | Root-level PWA routes |

## Adding New Static Assets to Offline Cache

To make a new static asset available offline, add it to `PRECACHE_URLS` in `static/service-worker.js`:

```javascript
const PRECACHE_URLS = [
  '/offline.html',
  '/static/css/main.css',
  // Add new asset here:
  '/static/css/new-feature.css',
];
```

Then bump `CACHE_VERSION` to force re-caching.

## Testing Checklist

1. **Installability:** Chrome DevTools -> Application -> Manifest shows valid manifest
2. **Service worker:** DevTools -> Application -> Service Workers shows registered + active
3. **Offline:** DevTools -> Network -> Offline checkbox; cached pages load, uncached shows offline page
4. **HTMX:** With SW active, HTMX partial updates still work (network-first ensures fresh content)
5. **Lighthouse:** Run Lighthouse PWA audit — should pass installability and offline checks
