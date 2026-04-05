// ── QuizMaster Pro — Service Worker ──────────────────────────────────────────
// Version: bump this string to force cache refresh on deploy
const CACHE_VERSION = 'qm-v1.1.0';  // bumped: mocktest system added
const STATIC_CACHE  = `${CACHE_VERSION}-static`;
const API_CACHE     = `${CACHE_VERSION}-api`;

// Files to pre-cache on install (app shell)
const PRECACHE_URLS = [
  '/',
  '/quiz',
  '/mocktest',
  '/leaderboard',
  '/about',
  '/contact',
  '/offline',
  '/static/css/style.css',
  '/static/css/admin.css',
  '/static/css/mocktest.css',
  '/static/js/main.js',
  '/static/manifest.json',
  '/static/icons/icon-192x192.svg',
  '/static/icons/icon-512x512.svg',
  '/static/icons/favicon.svg',
];

// ── INSTALL: pre-cache app shell ──────────────────────────────────────────────
self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(STATIC_CACHE).then(cache => {
      console.log('[SW] Pre-caching app shell');
      return cache.addAll(PRECACHE_URLS).catch(err => {
        // Non-fatal: log but don't block install
        console.warn('[SW] Pre-cache partial failure:', err);
      });
    })
  );
});

// ── ACTIVATE: clean up old caches ────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k !== STATIC_CACHE && k !== API_CACHE)
          .map(k => { console.log('[SW] Deleting old cache:', k); return caches.delete(k); })
      )
    ).then(() => self.clients.claim())
  );
});

// ── FETCH: network-first for API, cache-first for static ─────────────────────
self.addEventListener('fetch', event => {
  const req = event.request;
  const url = new URL(req.url);

  // Skip non-GET and cross-origin requests
  if (req.method !== 'GET' || url.origin !== self.location.origin) return;

  // ── API / dynamic routes: network-first, fall back to cache ──────────────
  const isApiRoute = url.pathname.startsWith('/chat') ||
                     url.pathname.startsWith('/notifications') ||
                     url.pathname.startsWith('/mocktest/submit') ||
                     url.pathname.startsWith('/mocktest/autosave') ||
                     url.pathname.startsWith('/quiz/submit') ||
                     url.pathname.startsWith('/comments') ||
                     url.pathname.startsWith('/api/');

  if (isApiRoute) {
    event.respondWith(
      fetch(req).catch(() => caches.match(req))
    );
    return;
  }

  // ── Static assets: cache-first ─────────────────────────────────────────────
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(req).then(cached => {
        if (cached) return cached;
        return fetch(req).then(response => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(STATIC_CACHE).then(c => c.put(req, clone));
          }
          return response;
        });
      })
    );
    return;
  }

  // ── HTML pages: network-first, fall back to offline page ─────────────────
  event.respondWith(
    fetch(req)
      .then(response => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(STATIC_CACHE).then(c => c.put(req, clone));
        }
        return response;
      })
      .catch(() =>
        caches.match(req).then(cached => {
          if (cached) return cached;
          // Fall back to offline page for navigation requests
          if (req.mode === 'navigate') {
            return caches.match('/offline');
          }
        })
      )
  );
});

// ── PUSH NOTIFICATIONS (future) ───────────────────────────────────────────────
self.addEventListener('push', event => {
  if (!event.data) return;
  const data = event.data.json();
  self.registration.showNotification(data.title || 'QuizMaster Pro', {
    body:    data.body || '',
    icon:    '/static/icons/icon-192x192.svg',
    badge:   '/static/icons/icon-72x72.svg',
    vibrate: [200, 100, 200],
    data:    { url: data.url || '/' }
  });
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    clients.openWindow(event.notification.data.url || '/')
  );
});
