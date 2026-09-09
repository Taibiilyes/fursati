/* فرصتي — عامل الخدمة: عمل أوفلاين + تخزين مؤقت ذكي */
const CACHE = "fursati-v3";
const CORE = [
  "/offline",
  "/static/css/style.css",
  "/static/manifest.json",
  "/static/icons/icon-192.png",
  "/static/img/hero.jpg"
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(CORE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin && !url.hostname.includes("fonts.g")) return;

  // صفحات التطبيق: الشبكة أولاً ثم المخزن ثم صفحة عدم الاتصال
  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req)
        .then((r) => {
          const copy = r.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
          return r;
        })
        .catch(() =>
          caches.match(req).then((m) => m || caches.match("/offline"))
        )
    );
    return;
  }

  // الملفات الثابتة: المخزن أولاً ثم الشبكة
  if (url.pathname.startsWith("/static/") || url.hostname.includes("fonts.g")) {
    e.respondWith(
      caches.match(req).then(
        (m) =>
          m ||
          fetch(req).then((r) => {
            const copy = r.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
            return r;
          })
      )
    );
  }
});
