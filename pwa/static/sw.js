/* Service worker: keeps the app shell (HTML, JS, CSS, icons) available offline.
 * API calls and page images are never cached: patient data stays on the server only.
 * Bump VERSION when the shell changes, so phones pick up the new files.
 */
const VERSION = "gwo-pwa-v11";
// OpenCV.js (~10 MB) gets its own cache: loaded on the first scan, kept across app updates
const VENDOR = "gwo-vendor-opencv-4.10.0";
const SHELL = ["/", "/index.html", "/app.js", "/styles.css", "/manifest.webmanifest",
  "/icons/icon.svg", "/icons/icon-192.png", "/icons/icon-512.png", "/icons/icon-maskable-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION && k !== VENDOR).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname === "/ocr" || url.pathname === "/health") return; // network only

  // Third-party libraries (versioned file names): cache first, download only once
  if (url.pathname.startsWith("/vendor/")) {
    event.respondWith(caches.open(VENDOR).then((c) => c.match(event.request).then((hit) => hit ||
      fetch(event.request).then((res) => { if (res.ok) c.put(event.request, res.clone()); return res; }))));
    return;
  }

  // App shell: network first (fresh after a deploy), cached copy when offline
  // cache: "no-cache" = always ask the server (a cheap 304 if unchanged), never a stale browser-cache copy
  event.respondWith(
    fetch(event.request, { cache: "no-cache" })
      .then((res) => {
        if (res.ok && SHELL.includes(url.pathname)) {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(event.request, copy));
        }
        return res;
      })
      .catch(() => caches.match(event.request).then((hit) => hit || caches.match("/index.html"))));
});
