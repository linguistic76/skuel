/**
 * SKUEL Service Worker
 *
 * Strategy: Network-first for HTML/HTMX (content must be fresh),
 * cache-first for static assets (CSS, JS, vendor libs).
 */

// Bumped v10 -> v11 for skuel.js: searchFilters now tracks the NOUS topic and
// drives a knowledge mode from it, which is what makes the four knowledge
// context filters reachable again after the Type dropdown lost its Ku option.
// A client serving the v10 bundle would pair the new markup (the Nous select's
// x-model / x-bind:disabled, the panel's x-on:change.capture) with a component
// that has neither `nousTopic` nor `adoptScope` — an Alpine expression error, a
// Type control disabled by nothing, and every context filter (plus a stale
// sub-topic) still riding requests it no longer belongs to.
// Bumped v9 -> v10 for skuel.js: the /search Type dropdown is now the 6 Activity
// Domains, and searchFilters' entityTypeFilters map dropped path_step,
// learning_path and user_entry to match. A client serving the v9 bundle would
// keep revealing knowledge facets for types the page no longer returns.
// Bumped v8 -> v9 for today.js: the write queue is now keyed per task, so a
// re-complete after Undo waits for that reopen instead of racing it. A client
// serving the v8 bundle would keep firing the unqueued third write.
// Bumped v7 -> v8 for today.js: Today's Undo now POSTs the prior status to
// reopen the task instead of only un-hiding the card. today.js is a page-local
// bundle (not precached), but cacheFirst() caches it like any other /static/
// asset, so PWA clients would keep serving the lying version indefinitely.
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
// between version bumps — EVERY change to a file served under /static/ must
// bump CACHE_VERSION here, or clients keep serving the stale asset
// indefinitely. PRECACHE_URLS membership is NOT the trigger: cacheFirst()
// below caches every /static/ response, so page-local bundles that were never
// precached (output.css, today.js) go stale exactly the same way.
// (The SW now registers correctly via the dedicated /service-worker.js route in
// adapters/inbound/pwa_routes.py — the former catch-all 404 shadowing is fixed;
// TECHNICAL_DEBT.md item 11's cache-invalidation half remains this manual bump.)
const CACHE_VERSION = 'skuel-v11';
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
