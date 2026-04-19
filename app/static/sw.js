// Renarin service worker.
// Precaches the four main views + static assets on install.
// GETs: cache first, network fallback.
// Mutating methods (PATCH/POST/PUT/DELETE): network only — never cache, never replay.

const CACHE_NAME = 'renarin-v1';
const PRECACHE_URLS = [
  '/',
  '/needs-attention',
  '/drafts',
  '/archive',
  '/static/style.css',
  '/static/htmx.min.js',
  '/static/todo.js',
  '/static/manifest.json',
  '/static/icon.svg',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      // Use {cache: 'reload'} to bypass HTTP cache during install.
      Promise.all(
        PRECACHE_URLS.map((url) =>
          fetch(new Request(url, { cache: 'reload' }))
            .then((resp) => (resp.ok ? cache.put(url, resp) : null))
            .catch(() => null)
        )
      )
    )
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;

  // Never cache or replay mutating requests. Writes must go to the live server.
  if (req.method !== 'GET') {
    event.respondWith(fetch(req));
    return;
  }

  // Skip cross-origin requests.
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) {
    return;
  }

  // Never cache edit or partial endpoints (they hold live state).
  if (url.pathname.startsWith('/edit/') || url.pathname.startsWith('/partials/')) {
    event.respondWith(fetch(req));
    return;
  }

  event.respondWith(
    caches.match(req).then((cached) => {
      const networked = fetch(req)
        .then((resp) => {
          // Opportunistically refresh cache for precached paths.
          if (resp && resp.ok && PRECACHE_URLS.includes(url.pathname)) {
            const copy = resp.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, copy)).catch(() => {});
          }
          return resp;
        })
        .catch(() => cached);
      return cached || networked;
    })
  );
});
