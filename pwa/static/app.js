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
      <label class="field">Benutzername<input type="text" name="u" autocomplete="username" required></label>
      <label class="field">Passwort<input type="password" name="p" autocomplete="current-password" required></label>
      <button class="cta" type="submit">Anmelden</button>
      <p class="muted" style="text-align:center">Nur fiktive oder anonymisierte Dokumente verwenden.</p>
    </form>`;
  const f = document.getElementById("f");
  f.u.focus();
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
  $app.innerHTML = `<div class="screen"><div class="head"><div class="muted">Fälle werden geladen …</div></div></div>`;
  const list = await api("/api/cases");
  const initials = (S.user || "?").split(/[\s._-]+/).filter(Boolean).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  $app.innerHTML = `
    <div class="screen">
      <div class="head">
        <div class="head-row">
          <div><div class="eyebrow">Get Well OCR</div><h1 class="title">Fälle</h1></div>
          <button class="avatar" id="me" aria-label="Profil und Einstellungen">${esc(initials)}</button>
        </div>
        <div class="search">
          <label for="q" class="sr-only">Fälle durchsuchen</label>${ICON.search}
          <input id="q" type="search" placeholder="Patient, Klinik oder Dokument">
        </div>
      </div>
      <div class="body" id="list"></div>
      <div class="foot">
        <a class="cta" href="#/scan">${ICON.scan}Unterlagen scannen</a>
        <label class="link-btn">oder Fotos / PDF importieren
          <input id="import" type="file" multiple hidden accept="${esc(S.meta.upload_types.map((t) => "." + t).join(","))},image/*,application/pdf"></label>
      </div>
    </div>`;

  const render = (q) => {
    const needle = q.trim().toLowerCase();
    const shown = list.filter((c) => !needle || [c.patient, c.label, c.issuer, docLabel(c.doc_type)].some((v) => (v || "").toLowerCase().includes(needle)));
    let html = "", last = null;
    for (const c of shown) {
      const group = dayLabel(c.created_at);
      if (group !== last) { html += `<span class="section-label">${esc(group)}</span>`; last = group; }
      const running = c.job && c.job.state === "running";
      const sub = c.processed
        ? [c.issuer, c.doc_type ? docLabel(c.doc_type) : null].filter(Boolean).join(" · ") || `${c.n_docs} Dokumente`
        : `${c.n_pages} Seiten · noch nicht ausgewertet`;
      const right = running ? `<span class="pill">Analyse …</span>`
        : c.created_at ? `<span class="time">${esc(timeLabel(c.created_at))}</span>` : `<span class="pill">Testfall</span>`;
      html += `<a class="case-item" href="${running ? `#/analyse/${enc(c.id)}` : `#/case/${enc(c.id)}`}">
          <div class="doc-icon">${ICON.doc}</div>
          <div class="main"><span class="name">${esc(c.patient || c.label)}</span><span class="sub">${esc(sub)}</span></div>
          ${right}</a>`;
    }
    document.getElementById("list").innerHTML = html || `<div class="empty">${needle ? "Nichts gefunden." : "Noch keine Fälle. Unterlagen scannen, um zu beginnen."}</div>`;
  };
  document.getElementById("q").oninput = (e) => render(e.target.value);
  document.getElementById("import").onchange = (e) => { if (e.target.files.length) uploadAndAnalyse([...e.target.files]); };
  document.getElementById("me").onclick = () => profileSheet(list);
  render("");
}

function profileSheet(list) {
  const priv = list.filter((c) => c.private).length;
  sheet(`Angemeldet als ${S.user}`, `
    ${S.install ? `<button class="btn primary" id="install">App installieren</button>` : ""}
    <button class="btn" id="logout">Abmelden</button>
    <details><summary>Verlauf löschen (${priv})</summary>
      <div style="display:flex;flex-direction:column;gap:10px;margin-top:10px">
        <p class="muted" style="margin:0">Löscht alle hochgeladenen Fälle mit Fotos, Texterkennung und Prüfungen. Testfälle bleiben.</p>
        <label class="check"><input type="checkbox" id="sure"> Ja, endgültig löschen</label>
        <button class="btn danger" id="delall" disabled>Alle hochgeladenen Fälle löschen</button>
      </div></details>
    <p class="muted" style="margin:0">Healthcare Hackathon Bayern 2026 · Demo mit fiktiven Daten</p>`, (el, close) => {
    el.querySelector("#logout").onclick = () => { close(); logout(); };
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

// ------------------------------------------------------------------ 2 · Scannen

function stopCamera() {
  if (S.scan && S.scan.stream) S.scan.stream.getTracks().forEach((t) => t.stop());
  if (S.scan) S.scan.stream = null;
}

function viewScan() {
  if (!S.scan) S.scan = { shots: [], stream: null, torch: false };
  const sc = S.scan;
  $app.innerHTML = `
    <div class="screen scan">
      <div class="bar">
        <button class="round" id="cancel" aria-label="Scan abbrechen">${ICON.close}</button>
        <span class="page-no" id="pageno">Seite ${sc.shots.length + 1}</span>
        <button class="round" id="torch" aria-label="Licht einschalten" disabled>${ICON.bolt}</button>
      </div>
      <div class="viewfinder-wrap">
        <div class="viewfinder">
          <video id="video" playsinline muted autoplay hidden></video>
          <div class="paper" id="paper">${[45, 30, 100, 92, 96, 70, 100, 88, 94, 60, 100, 82].map((w) => `<i style="width:${w}%"></i>`).join("")}</div>
          <div class="flash" id="flash"></div>
          <div class="corner tl"></div><div class="corner tr"></div><div class="corner bl"></div><div class="corner br"></div>
        </div>
      </div>
      <div style="display:flex;justify-content:center;padding-bottom:14px"><span class="hint"><span class="dot"></span><span id="hint">Kamera wird gestartet …</span></span></div>
      <div class="shots" id="shots"></div>
      <div class="controls">
        <label class="gallery">Galerie<input id="gallery" type="file" multiple hidden accept="image/*,application/pdf,.heic,.heif"></label>
        <button class="shutter" id="shutter" aria-label="Foto aufnehmen"><span></span></button>
        <button class="done-btn" id="done" disabled>Fertig</button>
      </div>
      <input id="native" type="file" accept="image/*" capture="environment" hidden>
    </div>`;

  const video = document.getElementById("video");
  const renderShots = () => {
    document.getElementById("shots").innerHTML = sc.shots.map((s, i) => s.url
      ? `<img src="${s.url}" alt="Seite ${i + 1}">` : `<img src="/icons/icon-192.png" alt="Datei ${i + 1}">`).join("");
    document.getElementById("pageno").textContent = `Seite ${sc.shots.length + 1}`;
    const done = document.getElementById("done");
    done.disabled = !sc.shots.length;
    done.textContent = sc.shots.length ? `Fertig (${sc.shots.length})` : "Fertig";
  };
  const add = (files) => {
    for (const f of files) {
      if (sc.shots.length >= S.meta.max_files) { toast(`Höchstens ${S.meta.max_files} Seiten.`, true); break; }
      sc.shots.push({ file: f, url: f.type.startsWith("image/") && !/hei[cf]$/i.test(f.name) ? URL.createObjectURL(f) : null });
    }
    renderShots();
  };
  const discard = () => { sc.shots.forEach((s) => s.url && URL.revokeObjectURL(s.url)); stopCamera(); S.scan = null; };

  document.getElementById("cancel").onclick = () => {
    if (sc.shots.length && !confirm(`${sc.shots.length} aufgenommene Seite(n) verwerfen?`)) return;
    discard(); go("#/");
  };
  document.getElementById("gallery").onchange = (e) => { add([...e.target.files]); e.target.value = ""; };
  document.getElementById("native").onchange = (e) => { add([...e.target.files]); e.target.value = ""; };
  document.getElementById("done").onclick = () => {
    const files = sc.shots.map((s) => s.file);
    discard();
    uploadAndAnalyse(files);
  };
  document.getElementById("shutter").onclick = async () => {
    if (!sc.stream || !video.videoWidth) return document.getElementById("native").click();   // no live camera: phone camera app
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth; canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    const blob = await new Promise((r) => canvas.toBlob(r, "image/jpeg", 0.92));
    const flash = document.getElementById("flash");
    flash.classList.add("go"); requestAnimationFrame(() => requestAnimationFrame(() => flash.classList.remove("go")));
    add([new File([blob], `seite-${String(sc.shots.length + 1).padStart(2, "0")}.jpg`, { type: "image/jpeg" })]);
  };

  // Live camera: needs HTTPS (or localhost). Otherwise the shutter opens the phone's camera app.
  const hint = document.getElementById("hint");
  const fallback = (why) => { hint.textContent = why; };
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    fallback("Auslöser öffnet die Kamera-App");
  } else {
    navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 2560 }, height: { ideal: 1920 } }, audio: false })
      .then((stream) => {
        if (!location.hash.startsWith("#/scan")) { stream.getTracks().forEach((t) => t.stop()); return; }
        sc.stream = stream;
        video.srcObject = stream;
        video.hidden = false;
        document.getElementById("paper").hidden = true;
        hint.textContent = "Seite ins Bild halten · ruhig halten";
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
      })
      .catch(() => fallback("Auslöser öffnet die Kamera-App"));
  }
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

function uploadAndAnalyse(files) {
  go("#/analyse/upload");                       // stops other timers; the upload below keeps running
  const preview = files.find((f) => f.type.startsWith("image/") && !/hei[cf]$/i.test(f.name));
  const previewUrl = preview ? URL.createObjectURL(preview) : null;
  const engine = S.meta.default_engine;
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
        const out = await api(`/api/cases/${enc(id)}/review`, { method: "PUT", json: { meds: rv.meds, conflicts_ok: rv.conflicts_ok, reviewer: rv.reviewer || "", history_ai: rv.history_ai || null } });
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
  const chat = S.meta.chat_available;
  let lang = "de", withSrc = false;
  const putReview = async () => {
    const out = await api(`/api/cases/${enc(id)}/review`, { method: "PUT", json: { meds: rv.meds, conflicts_ok: rv.conflicts_ok, reviewer: rv.reviewer || "", history_ai: rv.history_ai || null } });
    Object.assign(rv, out.review);
  };
  const loadReport = async () => {
    const box = document.getElementById("report");
    box.textContent = "…";
    try { box.textContent = await api(`/api/cases/${enc(id)}/report?lang=${lang}&sources=${withSrc}`); } catch (e) { box.textContent = e.message; }
  };
  const checkHtml = (hist) => (hist.unsupported && hist.unsupported.length
    ? `<div class="note warn">${ICON.info}<span>Nicht in den geprüften Fakten belegt: ${esc(hist.unsupported.join(", "))}. Bitte korrigieren oder entfernen.</span></div>`
    : `<div class="note ok">${ICON.info}<span>Alle Zahlen und Daten im Text sind in den geprüften Fakten belegt.</span></div>`);
  const histHtml = () => {
    if (!chat) return `<p class="muted" style="margin:0">Mistral Large 3 ist nicht eingerichtet. Der Übergabetext enthält dann die Anamnese als Liste nach Datum.</p>`;
    const hist = rv.history_ai;
    return `<p class="muted" style="margin:0">Das Modell bekommt nur die geprüften Fakten dieses Falls, keine Fotos und keinen Rohtext. Jede Zahl und jedes Datum im Ergebnis wird gegen die Fakten geprüft.</p>
      <button class="btn" id="ai" ${ready ? "" : "disabled"}>Anamnese mit Mistral formulieren</button>
      ${hist ? `<label class="field">Text (bearbeitbar)<textarea id="aitext">${esc(hist.text)}</textarea></label><div id="aicheck">${checkHtml(hist)}</div>
        <label class="check"><input type="checkbox" id="aiok" ${hist.accepted ? "checked" : ""}> Text geprüft und für den Übergabetext freigegeben</label>` : ""}`;
  };
  const dl = (kind, extra = "") => `/api/cases/${enc(id)}/export/${kind}?lang=${lang}&sources=${withSrc}${extra}`;
  el.innerHTML = `<div class="body" style="padding-top:0;padding-bottom:28px">
    ${ready ? "" : `<div class="note warn">${ICON.info}<span>Noch ${rv.meds.filter((m) => !m.confirmed).length} Medikament(e) nicht bestätigt (Tab „Prüfen“). Exporte werden erst nach vollständiger ärztlicher Prüfung freigegeben.</span></div>`}
    <label class="field">Geprüft von<input type="text" id="reviewer" value="${esc(rv.reviewer || "")}" placeholder="Name der Ärztin / des Arztes"></label>
    <section class="card"><h2 style="font-size:15px">Anamnese als Fließtext (Mistral Large 3)</h2><div id="hist" style="display:flex;flex-direction:column;gap:10px">${histHtml()}</div></section>
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
  const bindHist = () => {
    const ai = document.getElementById("ai");
    if (ai) ai.onclick = async () => {
      ai.disabled = true; ai.textContent = "Mistral Large 3 formuliert …";
      try { const out = await api(`/api/cases/${enc(id)}/history`, { method: "POST" }); Object.assign(rv, out.review); } catch (e) { toast(e.message, true); }
      document.getElementById("hist").innerHTML = histHtml(); bindHist(); loadReport();
    };
    const text = document.getElementById("aitext");
    let tTimer;
    if (text) text.oninput = () => {
      rv.history_ai.text = text.value; rv.history_ai.accepted = false;
      document.getElementById("aiok").checked = false;
      clearTimeout(tTimer);
      tTimer = setTimeout(async () => {
        try { await putReview(); document.getElementById("aicheck").innerHTML = checkHtml(rv.history_ai); loadReport(); } catch (e) { toast(e.message, true); }
      }, 700);
    };
    const ok = document.getElementById("aiok");
    if (ok) ok.onchange = async () => { rv.history_ai.accepted = ok.checked; try { await putReview(); loadReport(); } catch (e) { toast(e.message, true); } };
  };
  bindHist();
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
