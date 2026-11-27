/* Get Well OCR PWA: plain JavaScript, no build step.
 * Screens (from the "Arztbrief-Scanner PWA" design): Übersicht · Scannen · Analyse · Ergebnis (copy-ready),
 * plus the working tabs of a case: Prüfen, Seiten, Labor, Dokumente, Export, Auswertung.
 * Everything goes through /api (same-origin cookie). Patient data is never stored in the browser.
 */
"use strict";

const $app = document.getElementById("app");
const S = { meta: null, user: null, caseData: null, pollTimer: null, saveTimer: null, scan: null, install: null };

// ------------------------------------------------------------------ helpers

const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const enc = encodeURIComponent;
const sources = (pages) => (pages && pages.length ? `<span class="src">S. ${esc(pages.join(", "))}</span>` : "");
const docLabel = (t) => (S.meta?.doc_types?.[t]?.label) || "Dokument";
const docChip = (t) => `<span class="chip" style="background:${esc(S.meta?.doc_types?.[t]?.color || "#5A6B82")}">${esc(docLabel(t))}</span>`;
const statusLabel = (s) => S.meta?.statuses?.[s] || s;

const ICON = {
  rotate: `<svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/></svg>`,
  plus: `<svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#3070B3" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>`,
  eye: `<svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#5A6B82" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>`,
  eyeOff: `<svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#5A6B82" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.6 5.1A10.8 10.8 0 0 1 12 5c6.5 0 10 7 10 7a17.6 17.6 0 0 1-3.2 4.1M6.6 6.6C3.8 8.4 2 12 2 12s3.5 7 10 7a9.7 9.7 0 0 0 5.4-1.6"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/><path d="M3 3l18 18"/></svg>`,
  doc: `<svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#3070B3" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h4"/></svg>`,
  docSmall: `<svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg>`,
  search: `<svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#5A6B82" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>`,
  scan: `<svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2"/><path d="M8 12h8"/></svg>`,
  back: `<svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#14315C" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 6l-6 6 6 6"/></svg>`,
  close: `<svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>`,
  bolt: `<svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2L5 14h6l-1 8 8-12h-6z"/></svg>`,
  more: `<svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="#14315C"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>`,
  check: `<svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#2F6B45" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5 9-10"/></svg>`,
  fail: `<svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#A3162B" stroke-width="3" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>`,
  info: `<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5v.5"/></svg>`,
  server: `<svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#5A6B82" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="7" rx="2"/><rect x="4" y="13" width="16" height="7" rx="2"/><path d="M8 7.5h.01M8 16.5h.01"/></svg>`,
  copy: `<svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/></svg>`,
};

function toast(msg, error = false) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast" + (error ? " error" : "");
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), error ? 6000 : 2200);
}

async function api(path, opts = {}) {
  const init = { credentials: "same-origin", headers: {}, ...opts };
  if (opts.json !== undefined) {
    init.body = JSON.stringify(opts.json);
    init.headers["Content-Type"] = "application/json";
  }
  let res;
  try {
    res = await fetch(path, init);
  } catch {
    document.getElementById("offline").hidden = false;
    throw new Error("Keine Verbindung zum Server.");
  }
  document.getElementById("offline").hidden = true;
  if (res.status === 401 && !path.startsWith("/api/login")) {
    S.user = null;
    go("#/login");
    throw new Error("Bitte anmelden.");
  }
  const type = res.headers.get("content-type") || "";
  const body = type.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) throw new Error((body && body.detail) || `Fehler ${res.status}`);
  return body;
}

function go(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}

function stopTimers() {
  clearTimeout(S.pollTimer);
  S.pollTimer = null;
}

function age(birth) {
  const m = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(birth || "");
  if (!m) return "";
  const bd = new Date(+m[3], +m[2] - 1, +m[1]);
  const now = new Date();
  let a = now.getFullYear() - bd.getFullYear();
  if (now.getMonth() < bd.getMonth() || (now.getMonth() === bd.getMonth() && now.getDate() < bd.getDate())) a--;
  return `${a} J.`;
}

const dayKey = (d) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
function dayLabel(iso) {
  if (!iso) return "Testfälle";
  const d = new Date(iso), today = new Date(), y = new Date();
  y.setDate(today.getDate() - 1);
  if (dayKey(d) === dayKey(today)) return "Heute";
  if (dayKey(d) === dayKey(y)) return "Gestern";
  return d.toLocaleDateString("de-DE", { day: "2-digit", month: "long", year: "numeric" });
}
const timeLabel = (iso) => (iso ? new Date(iso).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" }) : "");

async function copyText(text, btn, label = "Kopieren", doneLabel = "✓ Kopiert") {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement("textarea");            // fallback for plain http
    ta.value = text; document.body.appendChild(ta); ta.select();
    const ok = document.execCommand("copy"); ta.remove();
    if (!ok) return toast("Kopieren nicht möglich.", true);
  }
  if (btn) {
    const keep = btn.innerHTML;
    btn.classList.add("done");
    btn.innerHTML = btn.classList.contains("cta") ? keep.replace(label, doneLabel) : doneLabel;
    clearTimeout(btn._t);
    btn._t = setTimeout(() => { btn.classList.remove("done"); btn.innerHTML = keep; }, 1600);
  }
}

function sheet(title, html, bind) {
  const back = document.createElement("div");
  back.className = "sheet-backdrop";
  back.innerHTML = `<div class="sheet" role="dialog" aria-modal="true" aria-label="${esc(title)}"><h2>${esc(title)}</h2>${html}
    <button class="btn" data-close>Schließen</button></div>`;
  const close = () => back.remove();
  back.addEventListener("click", (e) => { if (e.target === back || e.target.closest("[data-close]")) close(); });
  document.body.appendChild(back);
  bind && bind(back.querySelector(".sheet"), close);
  back.querySelector("button, a, input, select")?.focus();
}

// ------------------------------------------------------------------ router

window.addEventListener("hashchange", route);

async function route() {
  stopTimers();
  if (S.scan && !location.hash.startsWith("#/scan")) stopCamera();
  const hash = location.hash || "#/";
  try {
    if (!S.meta) S.meta = await api("/api/meta");
    if (hash === "#/login") return viewLogin();
    if (!S.user) {
      try { S.user = (await api("/api/me")).user; } catch { return; }
    }
    let m;
    if (hash === "#/" || hash === "") return viewHome();
    if (hash === "#/scan") return viewScan();
    if ((m = /^#\/analyse\/([^/?]+)$/.exec(hash))) return viewAnalyse(decodeURIComponent(m[1]));
    if ((m = /^#\/case\/([^/?]+)\/page\/(\d+)$/.exec(hash))) return viewPage(decodeURIComponent(m[1]), +m[2]);
    if ((m = /^#\/case\/([^/?]+)(?:\?tab=(\w+))?$/.exec(hash))) return viewCase(decodeURIComponent(m[1]), m[2] || "result");
    go("#/");
  } catch (e) {
    $app.innerHTML = `<div class="screen"><div class="head"><div class="note cave">${ICON.info}<span>${esc(e.message)}</span></div>
      <a class="btn" href="#/">Zur Übersicht</a></div></div>`;
  }
}

// ------------------------------------------------------------------ login

function viewLogin() {
  const notSet = S.meta && !S.meta.login_configured;
  $app.innerHTML = `
    <form class="login" id="f">
      <div class="brand"><img src="/icons/icon-192.png" alt=""><div><div class="eyebrow">Get Well OCR</div><h1 class="title">Anmelden</h1></div></div>
      ${notSet ? `<div class="note cave">${ICON.info}<span>Login ist auf dem Server nicht eingerichtet (APP_USERNAME / APP_PASSWORD).</span></div>` : ""}
      <label class="field">Benutzername<input type="text" name="u" autocomplete="username" autocapitalize="none" autocorrect="off" spellcheck="false" required></label>
      <div class="field"><label for="pw">Passwort</label>
        <div class="pw-wrap"><input type="password" id="pw" name="p" autocomplete="current-password" autocapitalize="none" autocorrect="off" spellcheck="false" required>
          <button type="button" class="pw-toggle" id="pwtoggle" aria-label="Passwort anzeigen" aria-pressed="false">${ICON.eye}</button></div></div>
      <button class="cta" type="submit">Anmelden</button>
      <p class="muted" style="text-align:center">Nur fiktive oder anonymisierte Dokumente verwenden.</p>
    </form>`;
  const f = document.getElementById("f");
  f.u.focus();
  const toggle = document.getElementById("pwtoggle");
  toggle.onclick = () => {
    const show = f.p.type === "password";
    f.p.type = show ? "text" : "password";
    toggle.innerHTML = show ? ICON.eyeOff : ICON.eye;
    toggle.setAttribute("aria-pressed", String(show));
    toggle.setAttribute("aria-label", show ? "Passwort verbergen" : "Passwort anzeigen");
    f.p.focus();
  };
  f.onsubmit = async (ev) => {
    ev.preventDefault();
    const btn = f.querySelector("button");
    btn.disabled = true;
    try {
      S.user = (await api("/api/login", { method: "POST", json: { username: f.u.value, password: f.p.value } })).user;
      go("#/");
    } catch (e) {
      toast(e.message, true);
      btn.disabled = false;
    }
  };
}

async function logout() {
  try { await api("/api/logout", { method: "POST" }); } catch {}
  S.user = null;
  go("#/login");
}

// ------------------------------------------------------------------ 1 · Übersicht

async function viewHome() {
  $app.innerHTML = `<div class="screen home"><div class="home-top"><span class="org">Fälle werden geladen …</span></div></div>`;
  const list = await api("/api/cases");
  const initials = (S.user || "?").split(/[\s._-]+/).filter(Boolean).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  $app.innerHTML = `
    <div class="screen home">
      <div class="home-top">
        <span class="org">Get Well OCR</span>
        <button class="avatar" id="me" aria-label="Profil und Einstellungen">${esc(initials)}</button>
      </div>
      <div class="hero-wrap">
        <div class="hero">
          <div class="hero-doc" aria-hidden="true">
            <div class="leaf">${[60, 100, 85, 92, 70].map((w) => `<i style="width:${w}%"></i>`).join("")}</div>
            <span class="hc tl"></span><span class="hc tr"></span><span class="hc bl"></span><span class="hc br"></span>
          </div>
          <div class="hero-text"><h1>Unterlagen scannen</h1><p>Wichtiges ist in Sekunden kopierbereit.</p></div>
          <a class="cta flat" href="#/scan">Kamera öffnen</a>
          <label class="link-btn">oder Fotos / PDF importieren
            <input id="import" type="file" multiple hidden accept="${esc(S.meta.upload_types.map((t) => "." + t).join(","))},image/*,application/pdf"></label>
        </div>
      </div>
      <div class="recent">
        <div class="recent-head"><h2>Zuletzt</h2><button class="text-btn" id="all" aria-expanded="false">Alle</button></div>
        <div class="search" id="searchbox" hidden>
          <label for="q" class="sr-only">Fälle durchsuchen</label>${ICON.search}
          <input id="q" type="search" placeholder="Patient, Klinik oder Dokument">
        </div>
        <div id="list"></div>
      </div>
    </div>`;

  let all = false;
  const SHORT = 4;                                       // "Zuletzt" shows a few, "Alle" the whole list with search
  const render = () => {
    const needle = all ? document.getElementById("q").value.trim().toLowerCase() : "";
    const found = list.filter((c) => !needle || [c.patient, c.label, c.issuer, docLabel(c.doc_type)].some((v) => (v || "").toLowerCase().includes(needle)));
    const shown = all ? found : found.slice(0, SHORT);
    document.getElementById("list").innerHTML = shown.map((c) => {
      const running = c.job && c.job.state === "running";
      const sub = c.processed
        ? [c.doc_type ? docLabel(c.doc_type) : null, c.issuer].filter(Boolean).join(" · ") || `${c.n_docs} Dokumente`
        : `${c.n_pages} Seiten · noch nicht ausgewertet`;
      const day = dayLabel(c.created_at);
      const when = !c.created_at ? "Testfall" : day === "Heute" ? timeLabel(c.created_at) : day === "Gestern" ? day
        : new Date(c.created_at).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" });
      const right = running ? `<span class="pill">Analyse …</span>` : `<span class="time">${esc(when)}</span>`;
      return `<a class="recent-row" href="${running ? `#/analyse/${enc(c.id)}` : `#/case/${enc(c.id)}`}">
          <span class="main"><span class="name">${esc(c.patient || c.label)}</span><span class="sub">${esc(sub)}</span></span>${right}</a>`;
    }).join("") || `<div class="empty">${needle ? "Nichts gefunden." : "Noch keine Fälle. Kamera öffnen, um zu beginnen."}</div>`;
    document.getElementById("all").hidden = !all && list.length <= SHORT;
  };
  document.getElementById("all").onclick = (e) => {
    all = !all;
    e.currentTarget.textContent = all ? "Weniger" : "Alle";
    e.currentTarget.setAttribute("aria-expanded", String(all));
    document.getElementById("searchbox").hidden = !all;
    if (!all) document.getElementById("q").value = "";
    render();
  };
  document.getElementById("q").oninput = render;
  document.getElementById("import").onchange = (e) => { if (e.target.files.length) uploadAndAnalyse([...e.target.files]); };
  document.getElementById("me").onclick = () => profileSheet(list);
  render();
}

function profileSheet(list) {
  const priv = list.filter((c) => c.private).length;
  sheet(`Angemeldet als ${S.user}`, `
    ${S.install ? `<button class="btn primary" id="install">App installieren</button>` : ""}
    <label class="check"><input type="checkbox" id="cropset" ${localStorage.getItem("gwo-crop") !== "off" ? "checked" : ""}> Blatt beim Scannen automatisch zuschneiden</label>
    <button class="btn" id="logout">Abmelden</button>
    <details><summary>Verlauf löschen (${priv})</summary>
      <div style="display:flex;flex-direction:column;gap:10px;margin-top:10px">
        <p class="muted" style="margin:0">Löscht alle hochgeladenen Fälle mit Fotos, Texterkennung und Prüfungen. Testfälle bleiben.</p>
        <label class="check"><input type="checkbox" id="sure"> Ja, endgültig löschen</label>
        <button class="btn danger" id="delall" disabled>Alle hochgeladenen Fälle löschen</button>
      </div></details>
    <p class="muted" style="margin:0">Healthcare Hackathon Bayern 2026 · Demo mit fiktiven Daten</p>`, (el, close) => {
    el.querySelector("#logout").onclick = () => { close(); logout(); };
    el.querySelector("#cropset").onchange = (e) => localStorage.setItem("gwo-crop", e.target.checked ? "on" : "off");
    const inst = el.querySelector("#install");
    if (inst) inst.onclick = async () => { S.install.prompt(); await S.install.userChoice; S.install = null; close(); };
    const sure = el.querySelector("#sure"), del = el.querySelector("#delall");
    sure.onchange = () => (del.disabled = !(sure.checked && priv));
    del.onclick = async () => {
      try { const r = await api("/api/cases?confirm=true", { method: "DELETE" }); toast(`${r.deleted} Fälle gelöscht`); close(); viewHome(); }
      catch (e) { toast(e.message, true); }
    };
  });
}

// ------------------------------------------------------------------ Blatt-Erkennung (OpenCV.js)
// Finds the sheet of paper in a camera frame or photo and cuts it out, straightened like a scan.
// OpenCV.js (~10 MB, pwa/static/vendor) is loaded only when the scan screen opens; the service worker
// keeps it afterwards. Without it everything works as before, just without frame and crop.

const DOC = { cv: null, loading: null };

// Resolves to true once DOC.cv is ready. Never resolve a promise WITH the cv object: it has its own
// then() (Emscripten module), so the promise would adopt it again and again and freeze the page.
function loadOpenCV() {
  if (DOC.cv) return Promise.resolve(true);
  if (DOC.loading) return DOC.loading;
  DOC.loading = new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "/vendor/opencv.js";
    s.async = true;
    s.onerror = () => reject(new Error("OpenCV.js konnte nicht geladen werden"));
    s.onload = async () => {
      try {
        let c = window.cv;
        if (c instanceof Promise) c = await new Promise((ok, fail) => c.then((m) => ok({ m }), fail)).then((x) => x.m);
        if (!c || !c.Mat) {                               // older builds: wait for the WebAssembly runtime
          await new Promise((ok, fail) => {
            const t0 = Date.now();
            c.onRuntimeInitialized = ok;
            (function poll() { if (c.Mat) return ok(); if (Date.now() - t0 > 20000) return fail(new Error("OpenCV.js startet nicht")); setTimeout(poll, 100); })();
          });
        }
        DOC.cv = c;
        resolve(true);
      } catch (e) { reject(e); }
    };
    document.head.appendChild(s);
  });
  DOC.loading.catch(() => { DOC.loading = null; });
  return DOC.loading;
}

// Corners in order top-left, top-right, bottom-right, bottom-left
function orderCorners(pts) {
  const bySum = [...pts].sort((a, b) => a.x + a.y - (b.x + b.y));
  const byDiff = [...pts].sort((a, b) => a.y - a.x - (b.y - b.x));
  return [bySum[0], byDiff[0], bySum[3], byDiff[3]];
}

/* The sheet of paper in the picture: a 4-cornered shape covering minArea..90 % of it whose four sides
 * really lie on edges in the picture. source: video, image, canvas or ImageBitmap with its size sw x sh.
 * Returns corners in source pixels, or null.
 *
 * Just taking the biggest outline is wrong in a real room: all the edges of the background grow together
 * and their outline is almost the whole picture. So every candidate must be (1) nearly convex, (2) a real
 * quadrilateral with sane angles and (3) supported by edge pixels along each of its sides. The outline of
 * a messy blob fails (3): its sides bridge gaps where there is no edge. Inner outlines count too
 * (RETR_LIST): the white of the page between its border and the text stays a clean shape even when the
 * border touches the background clutter. */
function findSheet(source, sw, sh, minArea = 0.2) {
  const cv = DOC.cv;
  if (!cv || !sw || !sh) return null;
  const scale = Math.min(1, 400 / Math.max(sw, sh));
  const w = Math.round(sw * scale), h = Math.round(sh * scale);
  const small = findSheet.canvas || (findSheet.canvas = document.createElement("canvas"));
  small.width = w; small.height = h;
  small.getContext("2d", { willReadFrequently: true }).drawImage(source, 0, 0, w, h);
  const mats = [];
  const keep = (m) => (mats.push(m), m);
  try {
    const src = keep(cv.imread(small));
    const gray = keep(new cv.Mat());
    cv.cvtColor(src, gray, cv.COLOR_RGBA2GRAY);
    cv.GaussianBlur(gray, gray, new cv.Size(5, 5), 0);
    const k3 = keep(cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(3, 3)));
    const k5 = keep(cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(5, 5)));
    // [mask to take outlines from, mask the sides must lie on]
    const pairs = [];
    for (const [lo, hi] of [[40, 120], [10, 30]]) {     // normal edges, then faint ones (white paper on a light table)
      const edges = keep(new cv.Mat());
      cv.Canny(gray, edges, lo, hi);
      cv.dilate(edges, edges, k3);
      if (cv.countNonZero(edges) > 0.45 * w * h) continue;   // edges everywhere (noise, carpet): says nothing
      const support = keep(new cv.Mat());
      cv.dilate(edges, support, k5);                    // a few pixels of tolerance for the side check
      // Close outlines that run out of the picture (sheet held close): the picture border acts as an edge
      cv.rectangle(edges, new cv.Point(0, 0), new cv.Point(w - 1, h - 1), new cv.Scalar(255), 1);
      pairs.push([edges, support]);
    }
    // And the paper itself: light and colourless (the smallest of R, G, B is high). Opening cuts thin
    // bridges to other light things, closing fills the text. Works close up, where the sheet fills the
    // picture and its outline is hidden by hand and picture border. Its sides must lie on the rim of that area.
    {
      const ch = keep(new cv.MatVector());
      cv.split(src, ch);
      const r = keep(ch.get(0)), g = keep(ch.get(1)), bl = keep(ch.get(2));
      const white = keep(new cv.Mat());
      cv.min(r, g, white);
      cv.min(white, bl, white);
      cv.GaussianBlur(white, white, new cv.Size(5, 5), 0);
      const paper = keep(new cv.Mat());
      cv.threshold(white, paper, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU);
      const k9 = keep(cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(9, 9)));
      cv.morphologyEx(paper, paper, cv.MORPH_OPEN, k5);
      cv.morphologyEx(paper, paper, cv.MORPH_CLOSE, k9);
      const rim = keep(new cv.Mat());
      cv.morphologyEx(paper, rim, cv.MORPH_GRADIENT, k3);
      cv.dilate(rim, rim, k5);
      pairs.push([paper, rim]);
    }
    const sideSupport = (mask, a, b) => {               // share of the side a-b (without its ends) lying on the mask
      let hit = 0;
      const n = 24;
      for (let i = 0; i < n; i++) {
        const t = 0.1 + 0.8 * (i / (n - 1));
        const x = Math.round(a.x + (b.x - a.x) * t), y = Math.round(a.y + (b.y - a.y) * t);
        if (x >= 0 && y >= 0 && x < w && y < h && mask.ucharAt(y, x)) hit++;
      }
      return hit / n;
    };
    const angleOk = (q) => q.every((p, i) => {          // every corner between 50 and 130 degrees
      const a = q[(i + 3) % 4], b = q[(i + 1) % 4];
      const v1 = [a.x - p.x, a.y - p.y], v2 = [b.x - p.x, b.y - p.y];
      const cos = (v1[0] * v2[0] + v1[1] * v2[1]) / (Math.hypot(...v1) * Math.hypot(...v2) || 1);
      return Math.abs(cos) < 0.64;
    });
    // A side along the picture border: the sheet goes on outside the picture there
    const onBorder = (a, b) => (a.x <= 3 && b.x <= 3) || (a.y <= 3 && b.y <= 3) || (a.x >= w - 4 && b.x >= w - 4) || (a.y >= h - 4 && b.y >= h - 4);
    const brighterInside = (q) => {                     // paper is lighter than what is around it
      const m = cv.Mat.zeros(h, w, cv.CV_8UC1), pts = cv.matFromArray(4, 1, cv.CV_32SC2, q.flatMap((p) => [p.x, p.y]));
      cv.fillConvexPoly(m, pts, new cv.Scalar(255));
      const inside = cv.mean(gray, m)[0];
      cv.bitwise_not(m, m);
      const outside = cv.mean(gray, m)[0];
      m.delete(); pts.delete();
      return inside > outside + 8;
    };
    let best = null, bestScore = 0, bestCut = null, bestCutScore = 0;
    const lo = minArea * w * h, hi = 0.97 * w * h;
    for (const [mask, support] of pairs) {
      const contours = keep(new cv.MatVector());
      const hierarchy = keep(new cv.Mat());
      cv.findContours(mask, contours, hierarchy, cv.RETR_LIST, cv.CHAIN_APPROX_SIMPLE);
      for (let i = 0; i < contours.size(); i++) {
        const c = contours.get(i);
        const area = cv.contourArea(c);
        if (area >= lo && area <= hi) {
          const hull = new cv.Mat(), approx = new cv.Mat();
          cv.convexHull(c, hull);                         // the hull forgives a finger over the edge
          const hullArea = cv.contourArea(hull);
          if (hullArea <= hi && area >= 0.75 * hullArea) {  // nearly convex: a sheet, not a branching blob
            const peri = cv.arcLength(hull, true);
            for (const eps of [0.02, 0.03, 0.04, 0.055]) {  // looser until it has 4 corners
              cv.approxPolyDP(hull, approx, eps * peri, true);
              if (approx.rows <= 4) break;
            }
            if (approx.rows === 4 && cv.contourArea(approx) >= 0.88 * hullArea) {
              const d = approx.data32S;
              const q = orderCorners([0, 1, 2, 3].map((k) => ({ x: d[2 * k], y: d[2 * k + 1] })));
              if (angleOk(q)) {
                // Sides inside the picture must lie on edges; one may be half hidden by a hand. Sides on
                // the picture border are free, but then at least two real sides must be there, the sheet
                // must be lighter than the rest and must not be the whole picture.
                const real = q.map((p, k) => [p, q[(k + 1) % 4]]).filter(([a, b]) => !onBorder(a, b));
                const sup = real.map(([a, b]) => sideSupport(support, a, b));
                const mean = sup.reduce((a, v) => a + v, 0) / (sup.length || 1);
                const cut = real.length < 4;
                const ok = cut
                  ? hullArea >= 0.25 * w * h && real.length >= 2 && mean >= 0.7 && Math.min(...sup) >= 0.5 && brighterInside(q)
                  : hullArea <= 0.92 * w * h && mean >= 0.7 && Math.min(...sup) >= 0.35;
                if (ok) {
                  const score = hullArea * mean;
                  if (cut) { if (score > bestCutScore) { bestCutScore = score; bestCut = q; } }
                  else if (score > bestScore) { bestScore = score; best = q; }
                }
              }
            }
          }
          hull.delete(); approx.delete();
        }
        c.delete();
      }
    }
    best = best || bestCut;                             // a sheet seen whole beats one that leaves the picture
    if (!best) return null;
    // A little margin outwards (2 % of the size, clamped to the picture): better a strip of table than cut-off text
    const cx = best.reduce((a, p) => a + p.x, 0) / 4, cy = best.reduce((a, p) => a + p.y, 0) / 4;
    return best.map((p) => ({
      x: Math.min(sw - 1, Math.max(0, (cx + (p.x - cx) * 1.02) / scale)),
      y: Math.min(sh - 1, Math.max(0, (cy + (p.y - cy) * 1.02) / scale)),
    }));
  } catch {
    return null;
  } finally {
    mats.forEach((m) => m.delete());
  }
}

/* Cut the sheet out of a full-size canvas and straighten it. Returns a new canvas. */
function warpSheet(canvas, q) {
  const cv = DOC.cv;
  const d = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  let W = Math.max(d(q[2], q[3]), d(q[1], q[0])), H = Math.max(d(q[1], q[2]), d(q[0], q[3]));
  const s = Math.min(1, 2500 / Math.max(W, H));
  W = Math.round(W * s); H = Math.round(H * s);
  const mats = [];
  const keep = (m) => (mats.push(m), m);
  try {
    const src = keep(cv.imread(canvas));
    const from = keep(cv.matFromArray(4, 1, cv.CV_32FC2, q.flatMap((p) => [p.x, p.y])));
    const to = keep(cv.matFromArray(4, 1, cv.CV_32FC2, [0, 0, W - 1, 0, W - 1, H - 1, 0, H - 1]));
    const M = keep(cv.getPerspectiveTransform(from, to));
    const dst = keep(new cv.Mat());
    cv.warpPerspective(src, dst, M, new cv.Size(W, H), cv.INTER_LINEAR, cv.BORDER_REPLICATE);
    const out = document.createElement("canvas");
    cv.imshow(out, dst);
    return out;
  } finally {
    mats.forEach((m) => m.delete());
  }
}

const canvasToFile = (canvas, name) => new Promise((ok) => canvas.toBlob((b) => ok(new File([b], name, { type: "image/jpeg" })), "image/jpeg", 0.92));

/* Photo from the gallery or the phone's camera app: crop it if a sheet is clearly found, else keep it. */
async function cropPhotoFile(file) {
  if (!DOC.cv || !/^image\/(jpeg|png|webp)$/.test(file.type)) return file;
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    const s = Math.min(1, 3200 / Math.max(bmp.width, bmp.height));
    const c = document.createElement("canvas");
    c.width = Math.round(bmp.width * s); c.height = Math.round(bmp.height * s);
    c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
    bmp.close && bmp.close();
    const q = findSheet(c, c.width, c.height, 0.3);    // stricter than live: nobody checked the frame
    if (!q) return file;
    return await canvasToFile(warpSheet(c, q), file.name.replace(/\.\w+$/, "") + "-zugeschnitten.jpg");
  } catch {
    return file;
  }
}

window.GWO_DOC = { loadOpenCV, findSheet, warpSheet, cropPhotoFile };   // for testing in the console

// ------------------------------------------------------------------ 2 · Scannen

function stopCamera() {
  if (S.scan && S.scan.stream) S.scan.stream.getTracks().forEach((t) => t.stop());
  if (S.scan) { S.scan.stream = null; S.scan.quad = null; }
  cancelAnimationFrame(stopCamera.raf);
}

function viewScan() {
  if (!S.scan) S.scan = { shots: [], urls: new Set(), stream: null, torch: false, quad: null, quadAt: 0, retake: null, before: null,
    auto: localStorage.getItem("gwo-auto") === "on", engine: S.meta.default_engine };
  const sc = S.scan;
  const cropOn = () => localStorage.getItem("gwo-crop") !== "off";
  $app.innerHTML = `
    <div class="screen scan">
      <div class="bar">
        <button class="round" id="cancel" aria-label="Scan abbrechen">${ICON.close}</button>
        <button class="auto-toggle" id="auto" aria-pressed="${sc.auto}">${sc.auto ? "Auto-Aufnahme an" : "Manuell"}</button>
        <button class="round" id="torch" aria-label="Licht einschalten" disabled>${ICON.bolt}</button>
      </div>
      <div class="viewfinder-wrap">
        <div class="viewfinder">
          <video id="video" playsinline muted autoplay hidden></video>
          <canvas id="overlay" class="overlay" aria-hidden="true"></canvas>
          <div class="paper" id="paper">${[45, 30, 100, 92, 96, 70, 100, 88, 94, 60].map((w) => `<i style="width:${w}%"></i>`).join("")}</div>
        </div>
      </div>
      <div class="status" id="status">
        <span class="hint"><span class="dot"></span><span id="hint">Kamera wird gestartet …</span></span>
        <button class="retry" id="camretry" hidden>Kamera starten</button>
        <div class="snack" id="snack" role="status" hidden>
          <span class="tick">${ICON.check}</span><span id="snacktext"></span>
          <button id="undo">Rückgängig</button>
        </div>
      </div>
      <div class="shots" id="shots"></div>
      <div class="controls">
        <label class="gallery">Galerie<input id="gallery" type="file" multiple hidden accept="image/*,application/pdf,.heic,.heif"></label>
        <button class="shutter" id="shutter" aria-label="Seite aufnehmen"><span></span></button>
        <button class="done-btn" id="done" disabled>Weiter</button>
      </div>
      <input id="native" type="file" accept="image/*" capture="environment" hidden>
      <div class="flash" id="flash" aria-hidden="true"></div>
      <div id="layer"></div>
    </div>`;

  const video = document.getElementById("video");
  const hint = document.getElementById("hint");
  const layer = document.getElementById("layer");
  const buzz = (ms) => { try { navigator.vibrate && navigator.vibrate(ms); } catch {} };
  let found = false, camText = "";                      // camText: what the camera start has to say, if anything

  const showHint = () => {
    hint.textContent = sc.retake !== null ? `Seite ${sc.retake + 1} neu aufnehmen`
      : camText ? camText
      : !sc.stream ? "Auslöser öffnet die Kamera-App"
      : !found ? "Seite ins Bild halten"
      : sc.auto ? "Blatt erkannt · wird automatisch aufgenommen"
      : sc.shots.length ? "Nächste Seite oder „Weiter“" : "Blatt erkannt · jetzt auslösen";
  };
  const thumb = (s, i, cls) => `<button class="shot ${cls}" data-i="${i}" aria-label="Seite ${i + 1} ansehen">
      ${s.url ? `<img src="${s.url}" alt="">` : `<span class="file">${ICON.docSmall}</span>`}<span class="num">${i + 1}</span></button>`;
  const renderShots = (fresh = -1) => {
    document.getElementById("shots").innerHTML = sc.shots.map((s, i) => thumb(s, i, i === fresh ? "new" : "")).join("");
    const done = document.getElementById("done");
    done.disabled = !sc.shots.length;
    done.textContent = sc.shots.length ? `Weiter (${sc.shots.length})` : "Weiter";
    showHint();
  };
  const makeShot = (f) => {
    const url = f.type.startsWith("image/") && !/hei[cf]$/i.test(f.name) ? URL.createObjectURL(f) : null;
    if (url) sc.urls.add(url);                          // all released together when the scan ends (undo may need them)
    return { file: f, url };
  };
  // Short message with "Rückgängig": puts the list of pages back as it was before
  const hideSnack = () => {
    clearTimeout(hideSnack.timer);
    const el = document.getElementById("snack");
    if (!el) return;
    el.hidden = true;
    document.getElementById("status").classList.remove("has-snack");
    sc.before = null;
  };
  const snack = (text, before) => {
    document.getElementById("snacktext").textContent = text;
    document.getElementById("snack").hidden = false;
    document.getElementById("status").classList.add("has-snack");
    sc.before = before;
    clearTimeout(hideSnack.timer);
    hideSnack.timer = setTimeout(hideSnack, 3000);
  };
  document.getElementById("undo").onclick = () => {
    if (!sc.before) return;
    sc.shots = sc.before;
    hideSnack();
    renderShots();
  };
  const add = (files) => {
    const before = sc.shots.slice();
    if (sc.retake !== null && files.length) {            // replace the page chosen with "Neu aufnehmen"
      const i = sc.retake;
      sc.retake = null;
      sc.shots[i] = makeShot(files[0]);
      renderShots(i);
      return snack(`Seite ${i + 1} ersetzt`, before);
    }
    let n = 0;
    for (const f of files) {
      if (sc.shots.length >= S.meta.max_files) { toast(`Höchstens ${S.meta.max_files} Seiten.`, true); break; }
      sc.shots.push(makeShot(f));
      n++;
    }
    renderShots(n === 1 ? sc.shots.length - 1 : -1);
    if (n) snack(n === 1 ? `Seite ${sc.shots.length} gespeichert` : `${n} Seiten hinzugefügt`, before);
  };
  const discard = () => { sc.urls.forEach((u) => URL.revokeObjectURL(u)); clearTimeout(hideSnack.timer); stopCamera(); S.scan = null; };

  document.getElementById("cancel").onclick = () => {
    if (sc.shots.length && !confirm(`${sc.shots.length} aufgenommene Seite(n) verwerfen?`)) return;
    discard(); go("#/");
  };
  document.getElementById("auto").onclick = (e) => {
    sc.auto = !sc.auto;
    localStorage.setItem("gwo-auto", sc.auto ? "on" : "off");
    e.currentTarget.textContent = sc.auto ? "Auto-Aufnahme an" : "Manuell";
    e.currentTarget.setAttribute("aria-pressed", String(sc.auto));
    showHint();
  };
  // Photos from the gallery or the phone's camera app: cut out the sheet too, if one is clearly found
  const addPhotos = async (files) => {
    if (!cropOn()) return add(files);
    camText = "Blatt wird zugeschnitten …"; showHint();
    try { await Promise.race([loadOpenCV(), new Promise((_, no) => setTimeout(no, 15000))]); } catch {}
    const out = [];
    for (const f of files) out.push(await cropPhotoFile(f));
    if (document.getElementById("hint") !== hint) return;   // left the screen meanwhile
    camText = "";
    add(out);
  };
  document.getElementById("gallery").onchange = (e) => { addPhotos([...e.target.files]); e.target.value = ""; };
  document.getElementById("native").onchange = (e) => { addPhotos([...e.target.files]); e.target.value = ""; };

  const capture = async () => {
    if (!sc.stream || !video.videoWidth) return document.getElementById("native").click();   // no live camera: phone camera app
    buzz(35);
    let canvas = document.createElement("canvas");
    canvas.width = video.videoWidth; canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    const quad = sc.quad && Date.now() - sc.quadAt < 700 ? sc.quad : null;   // only a frame seen just now
    if (cropOn() && quad && DOC.cv) {
      try { canvas = warpSheet(canvas, quad); } catch { /* keep the full picture */ }
    }
    const flash = document.getElementById("flash");
    flash.classList.add("go"); requestAnimationFrame(() => requestAnimationFrame(() => flash.classList.remove("go")));
    add([await canvasToFile(canvas, `seite-${String((sc.retake ?? sc.shots.length) + 1).padStart(2, "0")}.jpg`)]);
  };
  document.getElementById("shutter").onclick = capture;

  // ---------- one page large: retake, rotate or delete it
  const rotate = async (i) => {
    const bmp = await createImageBitmap(sc.shots[i].file);
    const c = document.createElement("canvas");
    c.width = bmp.height; c.height = bmp.width;
    const ctx = c.getContext("2d");
    ctx.translate(c.width, 0); ctx.rotate(Math.PI / 2); ctx.drawImage(bmp, 0, 0);
    sc.shots[i] = makeShot(await canvasToFile(c, sc.shots[i].file.name.replace(/\.\w+$/, "") + ".jpg"));
  };
  const openPage = (i) => {
    const s = sc.shots[i];
    layer.innerHTML = `
      <div class="pageview" role="dialog" aria-modal="true" aria-label="Seitenvorschau">
        <div class="bar">
          <button class="round" data-act="close" aria-label="Vorschau schließen">${ICON.close}</button>
          <span class="page-no">Seite ${i + 1} von ${sc.shots.length}</span>
          <button class="round" data-act="rotate" aria-label="Seite drehen" ${s.url ? "" : "disabled"}>${ICON.rotate}</button>
        </div>
        <div class="big">${s.url ? `<img src="${s.url}" alt="Seite ${i + 1}">` : `<div class="file">${ICON.docSmall}<span>${esc(s.file.name)}</span></div>`}</div>
        <div class="two">
          <button class="ghost" data-act="retake">Neu aufnehmen</button>
          <button class="del" data-act="delete">Löschen</button>
        </div>
      </div>`;
    layer.querySelector("[data-act=close]").focus();
    layer.querySelector(".pageview").onclick = async (e) => {
      const act = e.target.closest("[data-act]")?.dataset.act;
      if (!act) return;
      if (act === "rotate") {
        try { await rotate(i); renderShots(); openPage(i); } catch { toast("Drehen nicht möglich.", true); }
        return;
      }
      layer.innerHTML = "";
      if (act === "retake") { sc.retake = i; showHint(); }
      if (act === "delete") {
        const before = sc.shots.slice();
        buzz([20, 40, 20]);
        sc.shots.splice(i, 1);
        sc.retake = null;
        renderShots();
        snack(`Seite ${i + 1} gelöscht`, before);
      }
    };
  };
  document.getElementById("shots").onclick = (e) => { const b = e.target.closest(".shot"); if (b) openPage(+b.dataset.i); };

  // ---------- "Weiter": check the pages in a sheet, then send them off
  const engines = S.meta.engines.filter((e) => e.available);
  const openReview = () => {
    const n = sc.shots.length;
    layer.innerHTML = `
      <div class="review-back">
        <div class="review" role="dialog" aria-modal="true" aria-label="Aufgenommene Seiten">
          <span class="grip" aria-hidden="true"></span>
          <div class="review-head"><h1>${n} ${n === 1 ? "Seite" : "Seiten"} aufgenommen</h1><button class="text-btn" data-act="edit">Bearbeiten</button></div>
          <div class="review-pages">${sc.shots.map((s, i) => `<button class="tile" data-page="${i}" aria-label="Seite ${i + 1} ansehen">
              ${s.url ? `<img src="${s.url}" alt="">` : `<span class="file">${ICON.docSmall}</span>`}</button>`).join("")}
            ${n < S.meta.max_files ? `<button class="tile add" data-act="edit" aria-label="Weitere Seite aufnehmen">${ICON.plus}</button>` : ""}</div>
          <div class="review-row">
            <span class="badge">${ICON.server}</span>
            <span class="main"><span class="name" id="engname">${esc(engineLabel(sc.engine))}</span><span class="sub">Texterkennung</span></span>
            ${engines.length > 1 ? `<button class="text-btn" data-act="engine">Ändern</button>` : ""}
          </div>
          <div class="review-actions">
            <button class="cta flat" data-act="go">Auswerten</button>
            <button class="text-btn tall" data-act="edit">Weitere Seite scannen</button>
          </div>
        </div>
      </div>`;
    layer.querySelector("[data-act=go]").focus();
    layer.querySelector(".review-back").onclick = (e) => {
      if (e.target.classList.contains("review-back")) { layer.innerHTML = ""; return; }
      const page = e.target.closest("[data-page]");
      if (page) return openPage(+page.dataset.page);
      const act = e.target.closest("[data-act]")?.dataset.act;
      if (act === "edit") layer.innerHTML = "";
      if (act === "engine") {
        sc.engine = engines[(engines.findIndex((x) => x.id === sc.engine) + 1) % engines.length].id;
        document.getElementById("engname").textContent = engineLabel(sc.engine);
      }
      if (act === "go") {
        const files = sc.shots.map((s) => s.file), engine = sc.engine;
        discard();
        uploadAndAnalyse(files, engine);
      }
    };
  };
  document.getElementById("done").onclick = openReview;

  // Live frame around the sheet: detect every ~150 ms on a small copy, draw on the overlay canvas.
  // The video is shown with object-fit: cover, so video pixels are mapped onto the visible box.
  const overlay = document.getElementById("overlay");
  let misses = 0, lastRun = 0;
  let lastQ = null, stillSince = 0, armed = true;       // auto capture: sheet held still, once per sheet
  const drawQuad = (q) => {
    const bw = overlay.clientWidth, bh = overlay.clientHeight, dpr = window.devicePixelRatio || 1;
    if (overlay.width !== Math.round(bw * dpr)) { overlay.width = Math.round(bw * dpr); overlay.height = Math.round(bh * dpr); }
    const ctx = overlay.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, bw, bh);
    if (!q) return;
    const vw = video.videoWidth, vh = video.videoHeight, s = Math.max(bw / vw, bh / vh);
    const ox = (bw - vw * s) / 2, oy = (bh - vh * s) / 2;
    const pts = q.map((p) => [p.x * s + ox, p.y * s + oy]);
    ctx.beginPath();
    pts.forEach(([x, y], i) => ctx[i ? "lineTo" : "moveTo"](x, y));
    ctx.closePath();
    ctx.lineJoin = "round";
    ctx.fillStyle = "rgba(90, 162, 230, 0.10)";
    ctx.fill();
    ctx.strokeStyle = "rgba(90, 162, 230, 0.22)"; ctx.lineWidth = 11; ctx.stroke();   // soft halo
    ctx.strokeStyle = "#5AA2E6"; ctx.lineWidth = 3; ctx.stroke();
    for (const [x, y] of pts) {                         // corner handles
      ctx.beginPath(); ctx.arc(x, y, 6, 0, 2 * Math.PI);
      ctx.fillStyle = "#fff"; ctx.fill();
      ctx.strokeStyle = "#5AA2E6"; ctx.lineWidth = 3; ctx.stroke();
    }
  };
  const tick = (now) => {
    if (!sc.stream || !location.hash.startsWith("#/scan")) return;
    stopCamera.raf = requestAnimationFrame(tick);
    if (document.hidden || !DOC.cv || !video.videoWidth || now - lastRun < 150) return;
    lastRun = now;
    const q = findSheet(video, video.videoWidth, video.videoHeight, 0.1);   // a sheet held up to a webcam is small
    if (q) {
      misses = 0;
      // smooth the corners so the frame does not jitter
      sc.quad = sc.quad ? q.map((p, i) => ({ x: sc.quad[i].x * 0.5 + p.x * 0.5, y: sc.quad[i].y * 0.5 + p.y * 0.5 })) : q;
      sc.quadAt = Date.now();
      const diag = Math.hypot(video.videoWidth, video.videoHeight);
      const moved = lastQ ? Math.max(...q.map((p, i) => Math.hypot(p.x - lastQ[i].x, p.y - lastQ[i].y))) / diag : 1;
      if (moved > 0.02) stillSince = now;
      if (moved > 0.12) armed = true;                   // clearly another sheet or position
      lastQ = q;
      if (sc.auto && armed && now - stillSince > 1000 && !layer.firstElementChild) { armed = false; capture(); }
    } else if (++misses > 4) {
      sc.quad = null; lastQ = null; armed = true;       // sheet gone: the next one may be taken automatically
    }
    if (found !== !!sc.quad) { found = !!sc.quad; showHint(); }
    drawQuad(sc.quad);
  };

  // Live camera: needs HTTPS (or localhost). Otherwise the shutter opens the phone's camera app.
  // Started in steps that each say what happens: preferred settings first, then any camera at all; if the
  // browser does not answer (permission question hidden or dismissed, camera busy) a "Kamera starten"
  // button appears, because a tap makes the browser ask again. The shutter always works without camera.
  const retry = document.getElementById("camretry");
  const onScan = () => location.hash.startsWith("#/scan") && document.getElementById("hint") === hint;
  const useStream = (stream) => {
    if (!onScan() || sc.stream) { stream.getTracks().forEach((t) => t.stop()); return; }   // left the screen, or a second answer
    sc.stream = stream;
    video.srcObject = stream;
    video.hidden = false;
    video.play().catch(() => {});
    document.getElementById("paper").hidden = true;
    retry.hidden = true;
    camText = ""; showHint();
    cancelAnimationFrame(stopCamera.raf);
    stopCamera.raf = requestAnimationFrame(tick);
    loadOpenCV().catch(() => {});                       // only now: the big download must not delay the camera
    const track = stream.getVideoTracks()[0];
    const caps = track.getCapabilities ? track.getCapabilities() : {};
    const torch = document.getElementById("torch");
    if (caps.torch) {
      torch.disabled = false;
      torch.onclick = async () => {
        sc.torch = !sc.torch;
        try { await track.applyConstraints({ advanced: [{ torch: sc.torch }] }); torch.classList.toggle("on", sc.torch); }
        catch { toast("Licht lässt sich nicht einschalten.", true); }
      };
    }
  };
  const startCamera = async () => {
    if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      camText = ""; showHint();                         // plain http on a phone: no live camera allowed
      return;
    }
    retry.hidden = true;
    camText = "Kamera wird gestartet …"; showHint();
    const slow = setTimeout(() => {
      if (onScan() && !sc.stream) { camText = "Kamera antwortet nicht · Freigabe in der Adressleiste prüfen"; showHint(); retry.hidden = false; }
    }, 5000);
    const wishes = [
      { video: { facingMode: { ideal: "environment" }, width: { ideal: 2560 }, height: { ideal: 1920 } }, audio: false },
      { video: true, audio: false },                    // any camera, any size
    ];
    let error = null;
    for (const wish of wishes) {
      try { useStream(await navigator.mediaDevices.getUserMedia(wish)); error = null; break; }
      catch (e) { error = e; if (e && (e.name === "NotAllowedError" || e.name === "NotFoundError")) break; }
    }
    clearTimeout(slow);
    if (!error || !onScan() || sc.stream) return;
    console.warn("Kamera:", error.name, error.message);
    camText = ({
      NotAllowedError: "Kamera nicht freigegeben · in der Adressleiste erlauben",
      NotReadableError: "Kamera wird von einem anderen Programm benutzt",
      NotFoundError: "Keine Kamera gefunden · Auslöser öffnet die Dateiauswahl",
    })[error.name] || `Kamera startet nicht (${error.name || "Fehler"})`;
    showHint();
    retry.hidden = error.name === "NotFoundError";
  };
  retry.onclick = startCamera;
  startCamera();
  renderShots();
}

// ------------------------------------------------------------------ 3 · Analyse

function analyseScreen({ title, lead, steps, previewUrl, engine, action }) {
  const icon = { done: ICON.check, fail: ICON.fail, run: "", todo: "" };
  return `
    <div class="screen analyse">
      <div class="nav"><a class="icon-btn" href="#/" aria-label="Zurück zur Übersicht">${ICON.back}</a><span class="label">Neuer Fall</span></div>
      <div class="body">
        <div class="doc-preview">${previewUrl ? `<img src="${previewUrl}" alt="">` : [55, 35, 100, 85, 92, 70, 100, 78, 90].map((w, i) => `<i class="${[2, 3, 6].includes(i) ? "hl" : ""}" style="width:${w}%"></i>`).join("")}<div class="scanline"></div></div>
        <div><h1>${esc(title)}</h1><p class="lead">${esc(lead)}</p></div>
        <div class="steps">${steps.map((s) => `<div class="step ${s.state}"><span class="state">${icon[s.state]}</span>${esc(s.label)}${s.detail ? `<span class="detail">${esc(s.detail)}</span>` : ""}</div>`).join("")}</div>
      </div>
      <div class="foot">
        ${engine ? `<div class="trust">${ICON.server}Texterkennung: ${esc(engine)}</div>` : ""}
        ${action}
      </div>
    </div>`;
}

const engineLabel = (id) => (S.meta.engines.find((e) => e.id === id) || {}).label || id;

function uploadAndAnalyse(files, chosenEngine) {
  go("#/analyse/upload");                       // stops other timers; the upload below keeps running
  const preview = files.find((f) => f.type.startsWith("image/") && !/hei[cf]$/i.test(f.name));
  const previewUrl = preview ? URL.createObjectURL(preview) : null;
  const engine = chosenEngine || S.meta.default_engine;
  const draw = (pct) => {
    $app.innerHTML = analyseScreen({
      title: "Unterlagen werden hochgeladen", lead: `${files.length} Seite(n) · ${pct} %`, previewUrl, engine: engineLabel(engine),
      steps: [{ label: "Hochladen", state: "run", detail: `${pct} %` }, { label: "Text erkannt (OCR)", state: "todo" },
        { label: "Wichtige Infos extrahieren", state: "todo" }, { label: "Copy-ready aufbereiten", state: "todo" }],
      action: `<button class="cta soft" disabled>Ergebnis ansehen</button>`,
    });
  };
  draw(0);
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f, f.name));
  fd.append("label", "Neuer Fall");
  fd.append("engine", engine);
  const xhr = new XMLHttpRequest();             // XHR for the upload progress
  xhr.open("POST", "/api/cases");
  xhr.withCredentials = true;
  xhr.upload.onprogress = (e) => { if (e.lengthComputable && location.hash === "#/analyse/upload") draw(Math.round((100 * e.loaded) / e.total)); };
  xhr.onload = () => {
    let body = {};
    try { body = JSON.parse(xhr.responseText); } catch {}
    if (xhr.status === 401) return go("#/login");
    if (xhr.status >= 400) {
      toast(body.detail || `Fehler ${xhr.status}`, true);
      $app.innerHTML = analyseScreen({ title: "Hochladen fehlgeschlagen", lead: body.detail || `Fehler ${xhr.status}`, previewUrl, engine: null,
        steps: [{ label: "Hochladen", state: "fail" }], action: `<a class="cta" href="#/scan">Erneut scannen</a>` });
      return;
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    location.replace(`#/analyse/${enc(body.case.id)}`);
  };
  xhr.onerror = () => toast("Keine Verbindung zum Server.", true);
  xhr.send(fd);
}

async function viewAnalyse(id) {
  if (id === "upload") return;                  // uploadAndAnalyse draws this screen itself
  const preview = `/api/cases/${enc(id)}/pages/1/image?variant=thumb`;
  const tick = async () => {
    let job;
    try { job = await api(`/api/cases/${enc(id)}/job`); } catch (e) { return toast(e.message, true); }
    if (!location.hash.startsWith(`#/analyse/${enc(id)}`)) return;
    const engine = engineLabel(job.engine || S.meta.default_engine);
    if (job.state === "running") {
      const ocrDone = job.done >= job.total;
      $app.innerHTML = analyseScreen({
        title: "Unterlagen werden ausgewertet", lead: ocrDone ? "Fakten werden abgeglichen …" : `Seite ${job.done} von ${job.total} gelesen`,
        previewUrl: preview, engine,
        steps: [{ label: "Hochgeladen", state: "done" }, { label: "Text erkannt (OCR)", state: ocrDone ? "done" : "run", detail: `${job.done}/${job.total}` },
          { label: "Wichtige Infos extrahieren", state: ocrDone ? "run" : "todo" }, { label: "Copy-ready aufbereiten", state: "todo" }],
        action: `<button class="cta soft" disabled>Ergebnis ansehen</button>`,
      });
      S.pollTimer = setTimeout(tick, 1500);
    } else if (job.state === "error") {
      $app.innerHTML = analyseScreen({ title: "Auswertung fehlgeschlagen", lead: job.error || "", previewUrl: preview, engine,
        steps: [{ label: "Hochgeladen", state: "done" }, { label: "Auswertung", state: "fail" }],
        action: `<a class="cta" href="#/case/${enc(id)}">Zum Fall</a>` });
    } else {
      $app.innerHTML = analyseScreen({ title: "Fertig ausgewertet", lead: "Bitte das Ergebnis prüfen, bevor es übernommen wird.", previewUrl: preview, engine,
        steps: ["Hochgeladen", "Text erkannt (OCR)", "Wichtige Infos extrahieren", "Copy-ready aufbereitet"].map((label) => ({ label, state: "done" })),
        action: `<a class="cta" href="#/case/${enc(id)}">Ergebnis ansehen</a>` });
    }
  };
  tick();
}

// ------------------------------------------------------------------ 4 · Fall: Ergebnis + Arbeits-Tabs

const TABS = [["result", "Ergebnis"], ["review", "Prüfen"], ["pages", "Seiten"], ["labs", "Labor"], ["docs", "Dokumente"], ["export", "Export"], ["eval", "Auswertung"]];

async function loadCase(id) {
  S.caseData = await api(`/api/cases/${enc(id)}`);
  return S.caseData;
}

function caseMenu(d) {
  sheet("Verarbeitung", `
    <label class="field">Texterkennung<select id="engine">${S.meta.engines.map((e) =>
      `<option value="${e.id}" ${e.id === ((d.result && d.result.engine) || S.meta.default_engine) ? "selected" : ""} ${e.available ? "" : "disabled"}>${esc(e.label)}${e.available ? "" : " (nicht eingerichtet)"}</option>`).join("")}</select></label>
    <label class="check"><input type="checkbox" id="fresh"> Texterkennung neu ausführen (sonst gespeicherte Ergebnisse)</label>
    <button class="btn primary" id="reprocess">Fall erneut verarbeiten</button>
    ${d.case.private ? `<button class="btn danger" id="delcase">Fall und alle Daten löschen</button>` : ""}`, (el, close) => {
    el.querySelector("#reprocess").onclick = async () => {
      try {
        await api(`/api/cases/${enc(d.case.id)}/process`, { method: "POST", json: { engine: el.querySelector("#engine").value, fresh: el.querySelector("#fresh").checked } });
        close(); go(`#/analyse/${enc(d.case.id)}`);
      } catch (e) { toast(e.message, true); }
    };
    const del = el.querySelector("#delcase");
    if (del) del.onclick = async () => {
      if (!confirm("Fall mit allen Fotos, Texterkennung und Prüfungen endgültig löschen?")) return;
      try { await api(`/api/cases/${enc(d.case.id)}`, { method: "DELETE" }); close(); toast("Fall gelöscht"); go("#/"); }
      catch (e) { toast(e.message, true); }
    };
  });
}

async function viewCase(id, tab) {
  $app.innerHTML = `<div class="screen"><div class="head"><div class="muted">Fall wird geladen …</div></div></div>`;
  const d = await loadCase(id);
  if (d.job && d.job.state === "running") return location.replace(`#/analyse/${enc(id)}`);
  const r = d.result;
  const nav = `<div class="nav"><a class="icon-btn" href="#/" aria-label="Zurück zur Übersicht">${ICON.back}</a><span class="label"></span>
      ${r ? `<a class="btn" href="#/case/${enc(id)}?tab=pages">${ICON.docSmall}Original</a>` : ""}
      <button class="icon-btn" id="menu" aria-label="Verarbeitung und Löschen">${ICON.more}</button></div>`;
  if (!r) {
    $app.innerHTML = `<div class="screen">${nav}<div class="patient-head"><h1>${esc(d.case.label)}</h1>
      <span class="meta">${d.case.n_pages} Seiten · noch nicht ausgewertet</span></div>
      <div class="body"><div class="note info">${ICON.info}<span>Über das Menü oben rechts auswerten.</span></div></div></div>`;
    document.getElementById("menu").onclick = () => caseMenu(d);
    return;
  }
  const p = r.patient || {};
  const firstDoc = r.documents.find((x) => !["irrelevant", "unknown"].includes(x.type));
  const meta = [p.birth ? `geb. ${p.birth}${age(p.birth) ? ` (${age(p.birth)})` : ""}` : null, firstDoc && firstDoc.issuer,
    `${r.pages.length} Seiten, ${r.documents.length} Dokumente`].filter(Boolean).join(" · ");
  const unconfirmed = d.review.meds.filter((m) => !m.confirmed).length;
  const retake = r.pages.filter((x) => x.status === "retake");
  const tabs = TABS.filter(([k]) => k !== "eval" || d.score);
  if (!tabs.some(([k]) => k === tab)) tab = "result";
  const wide = ["labs", "docs", "pages"].includes(tab);
  $app.innerHTML = `
    <div class="screen ${wide ? "wide" : ""}">
      ${nav}
      <div class="patient-head"><h1>${esc(p.name || d.case.label)}</h1><span class="meta">${esc(meta)}</span></div>
      <nav class="tabs" aria-label="Bereiche">${tabs.map(([k, l]) => `<a href="#/case/${enc(id)}?tab=${k}" class="${k === tab ? "on" : ""}" ${k === tab ? 'aria-current="page"' : ""}>${l}${k === "review" && unconfirmed ? ` <span class="count">${unconfirmed}</span>` : ""}</a>`).join("")}</nav>
      ${retake.length ? `<div style="padding:0 20px 12px"><div class="note cave">${ICON.info}<span><b>Bitte neu fotografieren:</b> ${retake.map((x) => `Seite ${x.page} (${x.quality === "too_blurry" ? "zu unscharf" : "Text unlesbar"})`).join(", ")}</span></div></div>` : ""}
      <div id="tab"></div>
    </div>`;
  document.getElementById("menu").onclick = () => caseMenu(d);
  const el = document.getElementById("tab");
  ({ result: tabResult, review: tabReview, pages: tabPages, labs: tabLabs, docs: tabDocs, export: tabExport, eval: tabEval })[tab](el, d);
}

// ---------- tab: Ergebnis (copy-ready)

function tabResult(el, d) {
  const s = d.result.summary, id = d.case.id, rv = d.review;
  const meds = rv.meds.filter((m) => m.status !== "stopped");
  const stopped = rv.meds.filter((m) => m.status === "stopped");
  const flagged = s.labs.filter((l) => l.flag);
  const medLine = (m) => [m.name, m.strength].filter(Boolean).join(" ");
  const blocks = [];
  if (s.cave.length) blocks.push({ key: "cave", title: "CAVE", cave: true,
    html: `<div class="card-text">${s.cave.map((c) => `${esc(c.text)}${sources(c.sources)}`).join("\n")}</div>`,
    text: "CAVE:\n" + s.cave.map((c) => c.text).join("\n") });
  blocks.push({ key: "diag", title: "Diagnosen",
    html: s.diagnoses.length ? `<div class="card-text">${s.diagnoses.slice(0, 12).map((x) => `${esc(x.text)}${x.icd10 ? ` (${esc(x.icd10)})` : ""}${sources(x.sources)}`).join("\n")}</div>` : `<div class="muted">Keine Diagnosen erkannt.</div>`,
    text: "Diagnosen:\n" + s.diagnoses.slice(0, 12).map((x) => x.text + (x.icd10 ? ` (${x.icd10})` : "")).join("\n") });
  blocks.push({ key: "med", title: "Medikation", badge: rv.meds.length && !d.ready ? `<span class="flag">${rv.meds.filter((m) => !m.confirmed).length} nicht bestätigt</span>` : "",
    html: meds.length ? `<div class="rows">${meds.map((m) => `<div><span>${esc(medLine(m))}${m.status === "new" ? ' <span class="pill">neu</span>' : m.status === "paused" ? ' <span class="pill warn">pausiert</span>' : ""}</span><span class="right">${esc(m.dosing || "–")}</span></div>`).join("")}</div>
      ${stopped.length ? `<div class="muted">Abgesetzt: ${esc(stopped.map(medLine).join(", "))}</div>` : ""}` : `<div class="muted">Keine Medikamente erkannt.</div>`,
    text: "Medikation:\n" + meds.map((m) => `${medLine(m)} ${m.dosing || ""}`.trim()).join("\n") + (stopped.length ? `\nAbgesetzt: ${stopped.map(medLine).join(", ")}` : "") });
  if (flagged.length) blocks.push({ key: "lab", title: "Auffällige Laborwerte",
    html: `<div class="rows">${flagged.map((l) => `<div><span>${esc(l.name)}</span><span class="right">${esc(l.value)} ${esc(l.unit)} ${l.flag === "H" ? "▲" : l.flag === "L" ? "▼" : ""}</span></div>`).join("")}</div>`,
    text: "Laborwerte:\n" + flagged.map((l) => `${l.name} ${l.value} ${l.unit}${l.flag ? ` (${l.flag === "H" ? "hoch" : "niedrig"})` : ""}`).join("\n") });
  if ((s.findings || []).length) blocks.push({ key: "bef", title: "Befunde",
    html: `<div class="card-text">${s.findings.map((f) => `${esc(f.text)}${sources(f.sources)}`).join("\n")}</div>`,
    text: "Befunde:\n" + s.findings.map((f) => f.text).join("\n") });
  if (s.contacts.length) blocks.push({ key: "kontakt", title: "Kontakt / Vorsorgevollmacht",
    html: `<div class="card-text">${s.contacts.map((c) => `${esc(c.text)}${sources(c.sources)}`).join("\n")}</div>`,
    text: "Kontakt:\n" + s.contacts.map((c) => c.text).join("\n") });

  el.innerHTML = `
    <div class="body" style="padding-top:0">
      <div class="note warn">${ICON.info}<span>Automatischer Auszug aus den Unterlagen. Bitte vor Übernahme in die Akte prüfen${d.ready ? "" : " und die Medikation im Tab „Prüfen“ bestätigen"}.</span></div>
      ${s.conflicts.length > d.review.conflicts_ok.length ? `<a class="note info" href="#/case/${enc(id)}?tab=review">${ICON.info}<span>${(() => { const n = s.conflicts.length - d.review.conflicts_ok.length; return `${n} ${n === 1 ? "Widerspruch" : "Widersprüche"}`; })()} zwischen den Dokumenten offen · zum Prüfen</span></a>` : ""}
      ${blocks.map((b) => `<section class="card" ${b.cave ? 'style="border-color:#F0C4CB"' : ""}>
          <div class="card-head"><h2 ${b.cave ? 'style="color:#A3162B"' : ""}>${esc(b.title)}</h2>${b.badge || ""}<span style="flex:1"></span>
            <button class="chip-btn" data-copy="${b.key}" aria-label="${esc(b.title)} kopieren">Kopieren</button></div>
          ${b.html}</section>`).join("")}
    </div>
    <div class="foot">
      <button class="cta" id="all">${ICON.copy}<span>Übergabetext kopieren</span></button>
      <a class="link-btn" href="#/case/${enc(id)}?tab=export">Export, FHIR und Medikationsplan</a>
    </div>`;
  el.querySelectorAll("[data-copy]").forEach((btn) => {
    const b = blocks.find((x) => x.key === btn.dataset.copy);
    btn.onclick = () => copyText(b.text, btn);
  });
  document.getElementById("all").onclick = async (e) => {
    const btn = e.currentTarget;
    try { copyText(await api(`/api/cases/${enc(id)}/report?lang=de`), btn, "Übergabetext kopieren", "✓ Übergabetext kopiert"); }
    catch (err) { toast(err.message, true); }
  };
}

// ---------- tab: Prüfen (Widersprüche + Medikation)

function tabReview(el, d) {
  const id = d.case.id, s = d.result.summary, rv = d.review;
  let corrections = d.corrections;
  const statuses = ["active", "new", "paused", "stopped"];
  const save = () => {
    clearTimeout(S.saveTimer);
    const st = document.getElementById("savestate");
    if (st) st.textContent = "Wird gespeichert …";
    S.saveTimer = setTimeout(async () => {
      try {
        const out = await api(`/api/cases/${enc(id)}/review`, { method: "PUT", json: { meds: rv.meds, conflicts_ok: rv.conflicts_ok, reviewer: rv.reviewer || "" } });
        Object.assign(rv, out.review);
        corrections = out.corrections;
        d.ready = out.ready;
        renderLog();
        const st2 = document.getElementById("savestate");
        if (st2) st2.textContent = "✓ Gespeichert";
      } catch (e) { toast(e.message, true); }
    }, 500);
  };
  const medHtml = (m, i) => `<div class="card med ${m.confirmed ? "confirmed" : ""}" data-i="${i}">
      <div class="top">
        <label class="check"><input type="checkbox" data-f="confirmed" ${m.confirmed ? "checked" : ""}> bestätigt</label>
        ${m.flag ? `<span class="flag">${esc(m.flag)}</span>` : ""}
        <span style="flex:1"></span><span class="muted">${esc(m.sources ? "S. " + m.sources : "")}</span>
        <button class="icon-btn" data-del="${i}" aria-label="Zeile löschen" style="width:36px;height:36px;color:#A3162B">${ICON.close}</button>
      </div>
      <label class="field full">Wirkstoff<input type="text" data-f="name" value="${esc(m.name)}"></label>
      <label class="field">Stärke<input type="text" data-f="strength" value="${esc(m.strength)}"></label>
      <label class="field">Dosierung<input type="text" data-f="dosing" value="${esc(m.dosing)}" placeholder="1-0-1-0"></label>
      <label class="field full">Status<select data-f="status">${statuses.map((x) => `<option value="${x}" ${x === m.status ? "selected" : ""}>${esc(statusLabel(x))}</option>`).join("")}</select></label>
    </div>`;
  const renderMeds = () => { document.getElementById("meds").innerHTML = rv.meds.map(medHtml).join("") || `<div class="empty">Keine Medikamente erkannt.</div>`; };
  const renderLog = () => {
    const log = document.getElementById("log");
    if (!log) return;
    log.innerHTML = corrections.length ? `<details class="card"><summary>Korrekturprotokoll (${corrections.length})</summary>
      <div class="rows">${corrections.map((c) => `<div><span>${esc(c.medication)} · ${esc(c.field)}</span><span class="right">${esc(c.machine)} → <b>${esc(c.doctor)}</b></span></div>`).join("")}</div></details>` : "";
  };
  el.innerHTML = `
    <div class="body" style="padding-top:0">
      <span class="section-label">Zu klären</span>
      ${s.conflicts.length ? `<p class="muted" style="margin:0">Diese Angaben widersprechen sich zwischen den Dokumenten. Abhaken, wenn geklärt.</p>` : `<p class="muted" style="margin:0">Die Dokumente widersprechen sich nicht.</p>`}
      <div style="display:flex;flex-direction:column;gap:8px" id="conflicts">${s.conflicts.map((c, i) => `<label class="conflict ${rv.conflicts_ok.includes(i) ? "done" : ""}">
          <input type="checkbox" data-conflict="${i}" ${rv.conflicts_ok.includes(i) ? "checked" : ""}><span>${esc(c.text)}${sources(c.sources)}</span></label>`).join("")}</div>
      <div class="card-head" style="margin-top:14px"><span class="section-label" style="margin:0">Medikationsabgleich</span><span class="saved" id="savestate"></span></div>
      <p class="muted" style="margin:0">Aus allen Dokumenten zusammengeführt: neuestes Dokument gilt, Absetzungen haben Vorrang. Jede Zeile prüfen, bei Bedarf korrigieren und bestätigen. Änderungen werden protokolliert.</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn primary" id="all">Alle bestätigen</button><button class="btn" id="reset">Auf Maschinenstand zurücksetzen</button><button class="btn" id="add">＋ Zeile</button></div>
      <div style="display:flex;flex-direction:column;gap:10px" id="meds"></div>
      <div id="log"></div>
      ${(s.medication_history || []).length ? `<p class="muted">Nur in älteren Dokumenten (> 1 Jahr) erwähnt, nicht übernommen: ${s.medication_history.map((x) => `${esc(x.name)} (S. ${esc(x.sources.join(", "))})`).join(", ")}</p>` : ""}
      <div style="height:28px"></div>
    </div>`;
  renderMeds();
  renderLog();
  document.getElementById("conflicts").onchange = (e) => {
    const i = e.target.dataset.conflict; if (i === undefined) return;
    const n = +i;
    rv.conflicts_ok = e.target.checked ? [...new Set([...rv.conflicts_ok, n])].sort((a, b) => a - b) : rv.conflicts_ok.filter((x) => x !== n);
    e.target.closest(".conflict").classList.toggle("done", e.target.checked);
    save();
  };
  const meds = document.getElementById("meds");
  const onField = (e) => {
    const f = e.target.dataset.f; if (!f) return;
    const card = e.target.closest(".med");
    const m = rv.meds[+card.dataset.i];
    m[f] = f === "confirmed" ? e.target.checked : e.target.value;
    if (f === "confirmed") card.classList.toggle("confirmed", m.confirmed);
    save();
  };
  meds.oninput = onField;
  meds.onchange = onField;
  meds.onclick = (e) => { const b = e.target.closest("button[data-del]"); if (!b) return; rv.meds.splice(+b.dataset.del, 1); renderMeds(); save(); };
  document.getElementById("all").onclick = () => { rv.meds.forEach((m) => (m.confirmed = true)); renderMeds(); save(); };
  document.getElementById("reset").onclick = () => { rv.meds = rv.machine.map((m) => ({ ...m })); renderMeds(); save(); };
  document.getElementById("add").onclick = () => {
    rv.meds.push({ confirmed: false, name: "", strength: "", dosing: "", status: "active", flag: "", sources: "" });
    renderMeds();
    meds.lastElementChild.querySelector("[data-f=name]").focus();
  };
}

// ---------- tab: Seiten

function tabPages(el, d) {
  const pages = d.result.pages, id = d.case.id;
  const types = [...new Set(pages.map((p) => p.doc_type).filter(Boolean))];
  let show = "all", type = "";
  el.innerHTML = `<div class="body" style="padding-top:0">
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <div class="seg" id="show"><button data-v="all" class="on">Alle</button><button data-v="retake">Neu fotografieren</button></div>
        <select id="type" style="max-width:240px;height:40px;border-radius:12px"><option value="">Alle Dokumenttypen</option>
          ${types.map((t) => `<option value="${esc(t)}">${esc(docLabel(t))}</option>`).join("")}</select></div>
      <div class="thumbs" id="grid"></div><div style="height:28px"></div></div>`;
  const render = () => {
    const visible = pages.filter((p) => (show !== "retake" || p.status === "retake") && (!type || p.doc_type === type));
    document.getElementById("grid").innerHTML = visible.map((p) => `
      <a class="thumb" href="#/case/${enc(id)}/page/${p.page}">
        <img loading="lazy" src="/api/cases/${enc(id)}/pages/${p.page}/image?variant=thumb" alt="Seite ${p.page}">
        <div class="cap"><b>S. ${p.page} · ${esc(p.doc_id || "–")}</b>
          ${p.status === "retake" ? `<span class="chip" style="background:#A3162B">neu fotografieren</span>` : docChip(p.doc_type)}</div></a>`).join("")
      || `<div class="empty">Keine Seiten.</div>`;
  };
  document.getElementById("show").onclick = (e) => {
    const b = e.target.closest("button"); if (!b) return;
    show = b.dataset.v;
    document.querySelectorAll("#show button").forEach((x) => x.classList.toggle("on", x === b));
    render();
  };
  document.getElementById("type").onchange = (e) => { type = e.target.value; render(); };
  render();
}

async function viewPage(id, n) {
  $app.innerHTML = `<div class="screen"><div class="head"><div class="muted">Seite wird geladen …</div></div></div>`;
  const d = S.caseData && S.caseData.case.id === id && S.caseData.result ? S.caseData : await loadCase(id);
  if (!d.result) return go(`#/case/${enc(id)}`);
  const info = await api(`/api/cases/${enc(id)}/pages/${n}`);
  const p = info.page, doc = info.document, pages = d.result.pages;
  const idx = pages.findIndex((x) => x.page === n);
  const prev = pages[idx - 1], next = pages[idx + 1];
  const reason = p.status === "retake"
    ? (p.quality === "too_blurry" ? `zu unscharf (Schärfe ${p.sharpness} < ${S.meta.sharpness_min})`
      : `Text kaum lesbar (Lesesicherheit ${(p.mean_confidence ?? 0).toFixed(2)} < ${S.meta.confidence_min})`) : "";
  const facts = p.facts || [];
  const legend = Object.entries(S.meta.facts).filter(([k]) => k !== "negatives").map(([, f]) => `<span class="chip" style="background:${esc(f.color)}">${esc(f.label)}</span>`).join(" ");
  $app.innerHTML = `
    <div class="screen wide">
      <div class="nav"><a class="icon-btn" href="#/case/${enc(id)}?tab=pages" aria-label="Zurück zu den Seiten">${ICON.back}</a>
        <span class="label">Seite ${n} · ${esc(p.doc_type ? docLabel(p.doc_type) : "nicht zugeordnet")}</span>
        ${prev ? `<a class="btn" href="#/case/${enc(id)}/page/${prev.page}" aria-label="Vorherige Seite">‹ ${prev.page}</a>` : ""}
        ${next ? `<a class="btn" href="#/case/${enc(id)}/page/${next.page}" aria-label="Nächste Seite">${next.page} ›</a>` : ""}</div>
      <div class="body grid2" style="padding-bottom:28px">
        <div style="display:flex;flex-direction:column;gap:10px">
          <div class="seg" id="variant" style="align-self:flex-start"><button data-v="photo">Foto</button><button data-v="marked" ${info.ocr ? "" : "disabled"}>Aufbereitet + Markierungen</button></div>
          ${info.engine === "mistral" ? `<p class="muted" style="margin:0">Mistral OCR liefert keine Positionen: Fundstellen sind als Text aufgelistet.</p>` : ""}
          <img id="img" class="page-img" alt="Seite ${n}">
          <div id="legend" style="display:flex;gap:6px;flex-wrap:wrap">${legend}</div>
        </div>
        <div style="display:flex;flex-direction:column;gap:10px">
          ${reason ? `<div class="note cave">${ICON.info}<span><b>Bitte neu fotografieren:</b> ${esc(reason)}. Seite wurde nicht ausgewertet.</span></div>` : ""}
          <section class="card"><h2 style="font-size:15px">Seiteninformation</h2><div class="rows">
            <div><span>Dokument</span><span class="right">${doc ? `${esc(doc.title)} (${esc(doc.doc_id)})` : "–"}</span></div>
            ${doc ? `<div><span>Seiten</span><span class="right">${esc(doc.pages.join(", "))}</span></div><div><span>Datum</span><span class="right">${esc(doc.date || "nicht erkannt")}</span></div>` : ""}
            <div><span>Bildschärfe</span><span class="right">${esc(p.sharpness)}</span></div>
            <div><span>Lesesicherheit</span><span class="right">${esc(p.mean_confidence ?? "–")}</span></div>
            ${info.ocr ? `<div><span>Aufbereitung</span><span class="right" style="white-space:normal">${esc(info.ocr.steps.filter((x) => x !== "gray").join(", "))}</span></div>` : ""}
          </div></section>
          <section class="card"><h2 style="font-size:15px">Gefunden auf dieser Seite (${facts.length})</h2>
            ${facts.length ? `<div style="display:flex;flex-direction:column;gap:6px">${facts.slice(0, 30).map((f) => `<div><span class="chip" style="background:${esc(S.meta.facts[f.kind]?.color || "#5A6B82")}">${esc(S.meta.facts[f.kind]?.label || f.kind)}</span> ${esc(f.label)}</div>`).join("")}</div>` : `<div class="muted">Keine strukturierten Fakten.</div>`}</section>
          ${info.ocr ? `<details class="card"><summary>Erkannter Text</summary><pre class="mono">${esc(info.ocr.text)}</pre></details>` : ""}
        </div>
      </div>
    </div>`;
  const setVariant = (v) => {
    document.querySelectorAll("#variant button").forEach((b) => b.classList.toggle("on", b.dataset.v === v));
    document.getElementById("img").src = `/api/cases/${enc(id)}/pages/${n}/image?variant=${v}`;
    document.getElementById("legend").hidden = v !== "marked";
  };
  document.getElementById("variant").onclick = (e) => { const b = e.target.closest("button"); if (b && !b.disabled) setVariant(b.dataset.v); };
  setVariant(p.status === "done" && info.ocr ? "marked" : "photo");
}

// ---------- tab: Labor & Befunde

function tabLabs(el, d) {
  const s = d.result.summary;
  const flag = { H: "▲ hoch", L: "▼ niedrig" };
  el.innerHTML = `<div class="body grid2" style="padding-top:0;padding-bottom:28px">
    <div style="display:flex;flex-direction:column;gap:10px"><span class="section-label">Laborwerte (neuester Wert, Verlauf)</span>
      ${s.labs.length ? `<div class="table-wrap"><table><tr><th>Parameter</th><th>Wert</th><th>Einheit</th><th></th><th>Verlauf</th><th>Quelle</th></tr>
        ${s.labs.map((l) => `<tr><td>${esc(l.name)}</td><td>${esc(l.value)}</td><td>${esc(l.unit)}</td><td class="${esc(l.flag)}">${esc(flag[l.flag] || l.flag || "")}</td><td>${esc(l.trend)}</td><td>${esc(l.sources.map((x) => "S. " + x).join(", "))}</td></tr>`).join("")}
      </table></div>` : `<div class="empty">Keine Laborwerte erkannt.</div>`}</div>
    <div style="display:flex;flex-direction:column;gap:10px">
      <section class="card"><h2 style="font-size:15px">Befunde</h2>${(s.findings || []).length ? `<div class="card-text">${s.findings.map((f) => `${esc(f.text)}${sources(f.sources)}`).join("\n")}</div>` : `<div class="muted">Keine Angaben gefunden.</div>`}</section>
      ${(s.ignored || []).length ? `<section class="card"><h2 style="font-size:15px">Ignoriert (nicht medizinisch)</h2><div class="card-text">${s.ignored.map((i) => `${esc(i.doc_id)}: Seiten ${esc(i.pages.join(", "))}`).join("\n")}</div></section>` : ""}
    </div></div>`;
}

// ---------- tab: Dokumente

function tabDocs(el, d) {
  const s = d.result.summary, id = d.case.id;
  const how = { rules: "Schlüsselwörter", model: "Sprachmodell (Embedding)" };
  el.innerHTML = `<div class="body" style="padding-top:0;padding-bottom:28px">
    <span class="section-label">Zeitstrahl</span>
    <div class="table-wrap"><table><tr><th>Datum</th><th>Dokument</th><th>ID</th><th>Seiten</th></tr>
      ${s.timeline.map((t) => `<tr><td>${esc(t.date || "–")}</td><td>${esc(t.text)}</td><td>${esc(t.doc_id)}</td><td>${esc(t.pages.join(", "))}</td></tr>`).join("")}</table></div>
    <span class="section-label">Dokumente</span>
    ${d.result.documents.map((doc) => `<details class="card">
      <summary>${doc.type_check ? "⚠ " : ""}${esc(doc.doc_id)} · ${esc(doc.title)} · ${esc(doc.date || "ohne Datum")} · ${doc.pages.length} Seite(n)</summary>
      <div style="display:flex;flex-direction:column;gap:10px;margin-top:6px">
        <div>${docChip(doc.type)} <span class="muted">zugeordnet durch ${esc(how[doc.classified_by] || "Regeln")}, Sicherheit ${Math.round((doc.type_confidence || 0) * 100)} %</span></div>
        ${doc.type_check ? `<div class="note warn">${ICON.info}<span>Regeln und Modell sind uneinig: Regeln = ${esc(docLabel(doc.rules_type))}, Modell = ${esc(docLabel(doc.model_type))}. Bitte Dokumenttyp prüfen.</span></div>` : ""}
        <div class="thumbs">${doc.pages.map((pg) => `<a class="thumb" href="#/case/${enc(id)}/page/${pg}"><img loading="lazy" src="/api/cases/${enc(id)}/pages/${pg}/image?variant=thumb" alt="Seite ${pg}"><div class="cap">S. ${pg}</div></a>`).join("")}</div>
      </div></details>`).join("")}</div>`;
}

// ---------- tab: Export

function tabExport(el, d) {
  const id = d.case.id, rv = d.review;
  const patient = (d.result.patient || {}).name || "";
  const ready = rv.meds.every((m) => m.confirmed);
  let lang = "de", withSrc = false;
  const putReview = async () => {
    const out = await api(`/api/cases/${enc(id)}/review`, { method: "PUT", json: { meds: rv.meds, conflicts_ok: rv.conflicts_ok, reviewer: rv.reviewer || "" } });
    Object.assign(rv, out.review);
  };
  const loadReport = async () => {
    const box = document.getElementById("report");
    box.textContent = "…";
    try { box.textContent = await api(`/api/cases/${enc(id)}/report?lang=${lang}&sources=${withSrc}`); } catch (e) { box.textContent = e.message; }
  };
  const dl = (kind, extra = "") => `/api/cases/${enc(id)}/export/${kind}?lang=${lang}&sources=${withSrc}${extra}`;
  el.innerHTML = `<div class="body" style="padding-top:0;padding-bottom:28px">
    ${ready ? "" : `<div class="note warn">${ICON.info}<span>Noch ${rv.meds.filter((m) => !m.confirmed).length} Medikament(e) nicht bestätigt (Tab „Prüfen“). Exporte werden erst nach vollständiger ärztlicher Prüfung freigegeben.</span></div>`}
    <label class="field">Geprüft von<input type="text" id="reviewer" value="${esc(rv.reviewer || "")}" placeholder="Name der Ärztin / des Arztes"></label>
    <section class="card"><div class="card-head"><h2>Übergabetext für das Krankenhaussystem</h2><button class="chip-btn" id="copy">Kopieren</button></div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center"><div class="seg" id="lang"><button data-v="de" class="on">Deutsch</button><button data-v="en">English</button></div>
        <label class="check"><input type="checkbox" id="withsrc"> Quellseiten [S. x] anzeigen</label></div>
      <pre class="mono" id="report"></pre>
      <div style="display:flex;gap:8px;flex-wrap:wrap" id="downloads"></div></section>
    <section class="card"><h2 style="font-size:15px">Medikationsplan für Patient:innen</h2>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <select id="plang" style="max-width:200px">${Object.entries(S.meta.plan_languages).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select>
        <input type="text" id="pname" value="${esc(patient)}" placeholder="Name auf dem Plan" style="max-width:280px">
        <a class="btn primary" id="pdf">PDF erstellen</a></div></section>
  </div>`;
  const renderDownloads = () => {
    const off = ready ? "" : ' aria-disabled="true"';
    document.getElementById("downloads").innerHTML = [["txt", "Übergabetext (.txt)"], ["json", "Fall (JSON)"], ["fhir", "FHIR R4 (Entwurf)"], ["csv", "Medikation (CSV)"]]
      .map(([k, l]) => `<a class="btn" href="${dl(k)}" download${off}>${l}</a>`).join("");
    const pdf = document.getElementById("pdf");
    pdf.href = dl("pdf", `&plan_lang=${enc(document.getElementById("plang").value)}&name=${enc(document.getElementById("pname").value)}`);
    pdf.setAttribute("download", "");
    if (!ready) pdf.setAttribute("aria-disabled", "true");
  };
  let rTimer;
  document.getElementById("reviewer").oninput = (e) => {
    rv.reviewer = e.target.value;
    clearTimeout(rTimer);
    rTimer = setTimeout(async () => { try { await putReview(); loadReport(); } catch (err) { toast(err.message, true); } }, 600);
  };
  document.getElementById("lang").onclick = (e) => {
    const b = e.target.closest("button"); if (!b) return;
    lang = b.dataset.v;
    document.querySelectorAll("#lang button").forEach((x) => x.classList.toggle("on", x === b));
    loadReport(); renderDownloads();
  };
  document.getElementById("withsrc").onchange = (e) => { withSrc = e.target.checked; loadReport(); renderDownloads(); };
  document.getElementById("copy").onclick = (e) => copyText(document.getElementById("report").textContent, e.currentTarget);
  document.getElementById("plang").onchange = renderDownloads;
  document.getElementById("pname").oninput = renderDownloads;
  renderDownloads();
  loadReport();
}

// ---------- tab: Auswertung (Testfälle mit Lösungsdatei)

function tabEval(el, d) {
  const sc = d.score;
  el.innerHTML = `<div class="body" style="padding-top:0;padding-bottom:28px">
    <p class="muted" style="margin:0">Nur für Testfälle mit Lösungsdatei: zeigt, was das System gefunden hat.</p>
    <div class="stats">
      <div class="${sc.needles_found === sc.needles_total ? "good" : "warn"}"><b>${sc.needles_found}/${sc.needles_total}</b>Kritische Fakten</div>
      <div><b>${sc.pages_correct}/${sc.pages_classified}</b>Seiten richtig</div>
      <div><b>${sc.conflicts_flagged}</b>Widersprüche (Lösung ${sc.conflicts_truth})</div>
      <div class="${sc.retake.length ? "bad" : "good"}"><b>${sc.retake.length}</b>Neu fotografieren</div></div>
    <section class="card"><div class="rows">${sc.needles.map((n) => `<div><span>${esc(n.fact)}</span><span class="right">${n.found ? '<span class="pill ok">gefunden</span>' : '<span class="pill warn">fehlt</span>'}</span></div>`).join("")}</div></section>
    ${sc.misclassified.length ? `<span class="section-label">Falsch zugeordnet</span><section class="card"><div class="rows">${sc.misclassified.map((w) => `<div><span>Seite ${w.page}: ${esc(docLabel(w.predicted))}</span><span class="right">richtig: ${esc(docLabel(w.truth))}</span></div>`).join("")}</div></section>` : ""}
  </div>`;
}

// ------------------------------------------------------------------ PWA: service worker + install

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}
window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); S.install = e; });
window.addEventListener("online", () => (document.getElementById("offline").hidden = true));
window.addEventListener("offline", () => (document.getElementById("offline").hidden = false));

route();
