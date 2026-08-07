/**
 * SKUEL Service Worker
 *
 * Strategy: Network-first for HTML/HTMX (content must be fresh),
 * cache-first for static assets (CSS, JS, vendor libs).
 */

// Bumped v6 -> v7 for the Tailwind v3 -> v4 migration: output.css is not in
// PRECACHE_URLS but cacheFirst() below caches every /static/ fetch into
// STATIC_CACHE, so the regenerated output.css at the same URL needs a version
// bump or PWA clients keep the v3 stylesheet indefinitely.
// Bumped v5 -> v6 to purge the stale static cache holding the pre-redesign
// search.css + skuel.js (the /search facets moved from a left rail back to a
// horizontal bar with a "More filters" disclosure + mobile filter drawer).
// Bumped v4 -> v5 to purge the stale static cache holding the pre-fix skuel.js
// (the /search "Ask" verb read facets off $el instead of $root — PR #556). The
// `activate` handler below deletes any cache whose key != the current versioned
// names, so any client that had registered the service worker drops the stale
// skuel.js on the next activation and re-precaches the fixed file.
// CRITICAL: this cache-first strategy hides ALL app-asset (JS/CSS) updates
// between version bumps — EVERY change to a PRECACHE_URLS file must bump
// CACHE_VERSION here, or clients keep serving the stale asset indefinitely.
// (The SW now registers correctly via the dedicated /service-worker.js route in
// adapters/inbound/pwa_routes.py — the former catch-all 404 shadowing is fixed;
// TECHNICAL_DEBT.md item 11's cache-invalidation half remains this manual bump.)
const CACHE_VERSION = 'skuel-v6';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`;

const PRECACHE_URLS = [
  '/offline.html',
  '/static/css/main.css',
  '/static/css/hierarchy.css',
  '/static/js/skuel.js',
  '/static/js/focus_trap.js',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png',
  '/static/vendor/alpinejs/alpine.3.14.8.min.js',
  '/static/vendor/htmx.org/htmx.1.9.10.min.js',
  '/static/vendor/htmx.org/ext/sse.js',
  '/static/vendor/htmx.org/ext/ws.js',
  '/static/vendor/htmx.org/ext/response-targets.js',
  '/static/vendor/chart.js/chart.umd.js',
  '/static/vendor/chart.js/chartjs-adapter-date-fns.3.min.js',
];

// Install: pre-cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

// Activate: clean old cache versions
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== STATIC_CACHE && key !== RUNTIME_CACHE)
          .map((key) => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

// Fetch handler
self.addEventListener('fetch', (event) => {
  const { request } = event;

  // Only handle GET requests
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // Static assets: cache-first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // HTML navigation and HTMX fragments: network-first
  if (request.headers.get('accept')?.includes('text/html') ||
      request.headers.get('HX-Request')) {
    event.respondWith(networkFirst(request));
    return;
  }

  // Everything else: network-first
  event.respondWith(networkFirst(request));
});

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response('', { status: 503, statusText: 'Service Unavailable' });
  }
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(RUNTIME_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;

    // Navigation requests get the offline fallback page
    if (request.mode === 'navigate') {
      const offlinePage = await caches.match('/offline.html');
      if (offlinePage) return offlinePage;
    }

    return new Response('', { status: 503, statusText: 'Service Unavailable' });
  }
}
