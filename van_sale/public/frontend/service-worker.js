const CACHE_NAME = 'van-sale-static-v1';
const API_CACHE_NAME = 'van-sale-api-v1';
const STATIC_ASSETS = ['/', '/index.html', '/manifest.webmanifest'];
const CACHEABLE_API_PATTERNS = [
  '/api/method/van_sale.api.get_driver_stock_dashboard',
  '/api/method/van_sale.api.get_app_context',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const isApi = request.url.includes('/api/');
  if (isApi) {
    const isCacheableApi = request.method === 'GET' && CACHEABLE_API_PATTERNS.some((pattern) => request.url.includes(pattern));
    if (!isCacheableApi) {
      return;
    }

    event.respondWith(
      fetch(request)
        .then((response) => {
          const clone = response.clone();
          caches.open(API_CACHE_NAME).then((cache) => cache.put(request, clone));
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      const fetchPromise = fetch(request)
        .then((response) => {
          const respClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, respClone));
          return response;
        })
        .catch(() => cached);
      return cached || fetchPromise;
    })
  );
});
