/* Aghaz Limited — service worker
   Network-first so live data stays realtime; falls back to cache when offline.
   Never intercepts POST (forms) or cross-origin (CDN / Cloudinary) requests. */
const CACHE = "aghaz-v1";
const SHELL = [
  "/static/ui.js",
  "/static/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png"
];

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => {})));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;                 // leave POST/PUT (forms) alone
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;       // let CDN & Cloudinary go direct

  // Network-first: keeps attendance/leave data live; cache is only an offline fallback
  e.respondWith(
    fetch(req)
      .then((res) => {
        if (url.pathname.startsWith("/static/")) {
          const clone = res.clone();
          caches.open(CACHE).then((c) => c.put(req, clone));
        }
        return res;
      })
      .catch(() => caches.match(req))
  );
});
