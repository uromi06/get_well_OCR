"""Shared UI building blocks for the Streamlit views.

Kept separate from src/ on purpose: src/ is the pipeline and must never import
Streamlit, so the same code can sit behind the FastAPI backend later.
"""
from __future__ import annotations

import html
import io
import json
from pathlib import Path

import cv2
import numpy as np
import streamlit as st
from PIL import Image

from src import config
from src.preprocess import load_image, preprocess

# ------------------------------------------------------------------ look and feel

DOC_TYPE_LABELS = {
    "discharge_letter": "Arztbrief", "medication_plan": "Medikationsplan", "lab_report": "Labor",
    "referral": "Einweisung", "imaging_report": "Bildgebung", "surgery_report": "OP-Bericht",
    "advance_directive": "Patientenverfügung", "nursing_transfer": "Pflegeüberleitung",
    "fax_note": "Fax / Notiz", "specialist_letter": "Facharztbrief", "other_medical": "Sonstiges",
    "irrelevant": "Nicht relevant", "unknown": "Unklar", None: "–",
}
DOC_TYPE_COLORS = {
    "discharge_letter": "#2563eb", "medication_plan": "#7c3aed", "lab_report": "#0891b2",
    "referral": "#0d9488", "imaging_report": "#4f46e5", "surgery_report": "#9333ea",
    "advance_directive": "#be123c", "nursing_transfer": "#c2410c", "fax_note": "#a16207",
    "specialist_letter": "#0369a1", "other_medical": "#64748b", "irrelevant": "#94a3b8", "unknown": "#94a3b8",
}
STATUS_LABELS = {"active": "aktiv", "new": "neu", "paused": "pausiert", "stopped": "abgesetzt"}
FACT_COLORS_BGR = {  # highlight colours on the page image (OpenCV uses BGR)
    "meds": (235, 99, 37), "diagnoses": (92, 81, 225), "labs": (178, 145, 8),
    "cave": (60, 20, 220), "contacts": (60, 130, 13), "findings": (180, 60, 150), "negatives": (120, 120, 120),
    "corrections": (18, 140, 245),
}
FACT_LABELS = {"meds": "Medikation", "diagnoses": "Diagnose", "labs": "Labor", "cave": "CAVE",
               "contacts": "Kontakt", "findings": "Befund", "negatives": "Negativbefund",
               "corrections": "KI-Korrektur"}

CSS = """
<style>
@import url("https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400&display=swap");
:root {
  --paper:#FFFFFF; --panel:#F2F5F9; --line:#D8E0EA; --ink:#102B49; --ink-2:#44566E; --ink-3:#7A889B;
  --navy:#102B49; --navy-2:#1B3D63; --lime:#B9EC54;
  --cave:#B4182D; --cave-bg:#FBEFF1; --amber:#9A6212; --amber-bg:#FBF4E6;
  --action:#102B49; --action-bg:#E9EFF6; --ok:#2E7550; --ok-bg:#EAF4EE;
}
.stApp, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5,
.stApp input, .stApp textarea, .stApp button, .stApp table, .stApp td, .stApp th, .stApp div {
  font-family: "Atkinson Hyperlegible", system-ui, -apple-system, "Segoe UI", sans-serif;
}
[data-testid="stIconMaterial"], .material-symbols-rounded, span[class*="material"] {
  font-family: "Material Symbols Rounded" !important;
}
.stApp {background: var(--paper);}
.block-container {padding-top: 2.6rem; padding-bottom: 3rem; max-width: 1360px;}
h1, h2, h3, h4, h5 {color: var(--ink); letter-spacing: -0.005em;}
code {font-family: "Atkinson Hyperlegible", monospace !important;}
.stCode code, pre code {font-family: ui-monospace, "Cascadia Mono", Consolas, monospace !important; font-size:.86rem;}
/* patient header: the name is the headline, like the top of a paper chart */
.gw-patient {display:flex; justify-content:space-between; align-items:flex-end; gap:1.5rem; flex-wrap:wrap;
             padding:.2rem 0 1rem 0; border-bottom:2px solid var(--ink); margin-bottom:1rem;}
.gw-patient .name {font-size:2.1rem; font-weight:700; color:var(--ink); line-height:1.1;}
.gw-patient .who {font-size:1.05rem; color:var(--ink-2); margin-top:.3rem;}
.gw-patient .who b {color:var(--ink);}
.gw-patient .side {text-align:right; color:var(--ink-3); font-size:.85rem; line-height:1.6;}
.gw-tag {display:inline-block; padding:.08rem .5rem; border-radius:4px; font-size:.78rem; font-weight:700;
         border:1px solid var(--line); color:var(--ink-2); background:white; margin-left:.3rem;}
.gw-tag.fict {color:var(--cave); border-color:#E7B7BF; background:var(--cave-bg);}
/* status strip: one line, every label fully readable */
.gw-strip {display:grid; grid-template-columns:repeat(6, minmax(0,1fr)); border:1px solid var(--line);
           border-radius:10px; background:white; margin-bottom:1rem; overflow:hidden;}
.gw-strip > div {padding:.7rem .95rem; border-left:1px solid var(--line);}
.gw-strip > div:first-child {border-left:none;}
.gw-strip .v {font-size:1.55rem; font-weight:700; color:var(--ink); font-variant-numeric:tabular-nums; line-height:1.15;}
.gw-strip .l {font-size:.84rem; color:var(--ink-2); line-height:1.3;}
.gw-strip .bad .v {color:var(--cave);} .gw-strip .warn .v {color:var(--amber);} .gw-strip .good .v {color:var(--ok);}
@media (max-width: 900px) {.gw-strip {grid-template-columns:repeat(3, minmax(0,1fr));}
  .gw-strip > div:nth-child(4) {border-left:none;} .gw-strip > div:nth-child(n+4) {border-top:1px solid var(--line);}}
/* CAVE: the one loud element */
.gw-cave {border-left:6px solid var(--cave); background:var(--cave-bg); border-radius:0 10px 10px 0;
          padding:.9rem 1.1rem 1rem 1.1rem; margin-bottom:1rem;}
.gw-cave .stamp {display:inline-block; color:var(--cave); border:2px solid var(--cave); border-radius:4px;
                 padding:0 .45rem; font-weight:700; font-size:1.05rem; letter-spacing:.06em; margin-bottom:.55rem;}
.gw-cave ul {margin:0; padding-left:1.1rem;} .gw-cave li {margin:.28rem 0; color:var(--ink); font-size:1.02rem;}
.gw-cave li b {color:var(--ink);}
/* quiet sections */
.gw-sec {margin:0 0 1.1rem 0;}
.gw-sec h4 {font-size:1.02rem; margin:0 0 .45rem 0; color:var(--ink); font-weight:700;}
.gw-sec ul {margin:0; padding-left:1.1rem;} .gw-sec li {margin:.22rem 0; color:var(--ink); line-height:1.45;}
.gw-sec .empty {color:var(--ink-3); font-size:.92rem;}
.gw-note {border-left:4px solid var(--amber); background:var(--amber-bg); border-radius:0 8px 8px 0;
          padding:.6rem .9rem; margin-bottom:1rem;}
.gw-note h4 {color:var(--amber); font-size:1rem; margin:0 0 .3rem 0;}
.gw-note ul {margin:0; padding-left:1.1rem;} .gw-note li {color:var(--ink); margin:.2rem 0;}
.gw-fix s {color:var(--ink-2); text-decoration-color:var(--amber);}
.gw-fix .gw-fix-kind {display:inline-block; padding:0 .35rem; border:1px solid var(--amber);
  border-radius:4px; color:var(--amber); font-size:.75rem; font-weight:700;}
.gw-fix .gw-muted {color:var(--ink-2);}
.gw-contact {border-left:4px solid var(--ok); background:var(--ok-bg); border-radius:0 8px 8px 0; padding:.6rem .9rem;}
.gw-contact h4 {color:var(--ok); font-size:1rem; margin:0 0 .3rem 0;}
/* medication table */
.gw-meds {width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; background:white;
          border:1px solid var(--line); border-radius:10px; overflow:hidden;}
.gw-meds th {text-align:left; font-size:.8rem; font-weight:700; color:var(--ink-2); background:var(--panel);
             padding:.45rem .6rem; border-bottom:1px solid var(--line);}
.gw-meds td {padding:.45rem .5rem; border-bottom:1px solid #EDF1F4; color:var(--ink); font-size:.95rem; vertical-align:top;}
.gw-meds tr:last-child td {border-bottom:none;}
.gw-meds td.n {font-weight:700;}
.gw-meds td.k, .gw-meds th.k {white-space:nowrap;}
.gw-meds td.src {line-height:1.9;}
.gw-meds tr.off td.n, .gw-meds tr.off td.k:not(.src) {color:var(--ink-3); text-decoration:line-through;}
.gw-meds tr.off td.src {text-decoration:none;}
.gw-st {font-size:.75rem; font-weight:700; padding:.05rem .4rem; border-radius:4px;}
.gw-st.new {background:var(--action-bg); color:var(--action);} .gw-st.paused, .gw-st.stopped {background:#EEF0F2; color:var(--ink-2);}
.gw-st.unk {background:var(--amber-bg); color:var(--amber);}
.gw-ok {color:var(--ok); font-weight:700;}
/* page references: small tabs like the edge of a paper page */
.gw-src {display:inline-block; padding:0 .32rem; margin-left:.25rem; border-radius:3px; font-size:.74rem;
         font-weight:700; background:var(--action-bg); color:var(--action); white-space:nowrap;
         font-variant-numeric:tabular-nums;}
.gw-chip {display:inline-block; padding:.08rem .45rem; margin:0 .25rem .25rem 0; border-radius:4px;
          font-size:.76rem; font-weight:700; background:var(--panel); color:var(--ink-2); white-space:nowrap;}
.gw-muted {color:var(--ink-3); font-size:.88rem;}
.gw-thumbcap {font-size:.82rem; line-height:1.35; margin-top:.2rem; color:var(--ink-2);}
.gw-conflict {padding:.55rem .8rem; border-left:4px solid var(--amber); background:var(--amber-bg);
              border-radius:0 8px 8px 0; font-size:.95rem; line-height:1.45; color:var(--ink);}
.gw-conflict.done {border-left-color:var(--ok); background:var(--ok-bg); color:var(--ink-3);}
.gw-card {border-radius:10px; padding:.85rem 1rem; margin-bottom:.8rem; border:1px solid var(--line); background:white;}
.gw-card h4 {margin:0 0 .45rem 0; font-size:1rem; color:var(--ink);}
.gw-card ul {margin:0; padding-left:1.1rem;} .gw-card li {margin:.18rem 0; line-height:1.45; color:var(--ink);}
.gw-card.gw-cavecard {border-color:#E7B7BF; background:var(--cave-bg);} .gw-card.gw-cavecard h4 {color:var(--cave);}
/* start screen */
.gw-hero {padding:1.4rem 0 1.1rem 0; max-width:780px;}
.gw-hero-title {font-size:2.6rem; font-weight:700; color:var(--ink); line-height:1.1; letter-spacing:-0.01em;}
.gw-hero-sub {font-size:1.12rem; color:var(--ink-2); margin-top:.7rem; line-height:1.55; max-width:64ch;}
[data-testid="stFileUploaderDropzone"] {min-height:230px; border:2px dashed #9DB9C6 !important;
  background:var(--action-bg) !important; border-radius:14px !important; display:flex; align-items:center;}
[data-testid="stFileUploaderDropzone"]:hover {border-color:var(--action) !important;}
[data-testid="stFileUploaderDropzoneInstructions"] span {font-size:1.05rem; color:var(--ink);}
.gw-steps {display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:1.6rem; margin-top:1.8rem;
           padding-top:1.3rem; border-top:1px solid var(--line); max-width:1100px;}
.gw-steps > div {color:var(--ink-2); line-height:1.5; font-size:.95rem;}
.gw-steps b {color:var(--ink); font-size:1.05rem;}
.gw-steps .n {display:inline-flex; align-items:center; justify-content:center; width:1.7rem; height:1.7rem;
              border-radius:50%; background:var(--ink); color:white; font-weight:700; font-size:.9rem;
              margin-right:.55rem; vertical-align:middle;}
@media (max-width: 800px) {.gw-steps {grid-template-columns:1fr;} .gw-hero-title {font-size:2rem;}}
/* Streamlit widgets in our palette */
.stTabs [data-baseweb="tab-list"] {gap:1.2rem; border-bottom:1px solid var(--line);}
.stTabs [data-baseweb="tab"] {font-size:1rem; padding:.5rem 0;}
/* sidebar: navy panel, white text (TUM Venture Labs tone) */
[data-testid="stSidebar"], [data-testid="stSidebar"] > div, [data-testid="stSidebarContent"] {background:var(--navy) !important; border-right:none;}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3,
[data-testid="stSidebar"] label, [data-testid="stSidebar"] p, [data-testid="stSidebar"] span,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {color:#FFFFFF !important;}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {opacity:.65;}
[data-testid="stSidebar"] [data-baseweb="select"] span, [data-testid="stSidebar"] input {color:var(--ink) !important;}
[data-testid="stSidebar"] button[kind="secondary"] {background:transparent; border:1px solid rgba(255,255,255,.45);}
[data-testid="stSidebar"] button[kind="secondary"]:hover {border-color:var(--lime);}
[data-testid="stSidebar"] button[kind="secondary"] p {color:#FFFFFF !important;}
[data-testid="stSidebar"] button[kind="primary"] {background:var(--lime); border-color:var(--lime);}
[data-testid="stSidebar"] button[kind="primary"] p {color:var(--navy) !important; font-weight:700;}
[data-testid="stSidebar"] hr {border-color:rgba(255,255,255,.18);}
[data-testid="stSidebar"] [data-testid="stExpander"] summary, [data-testid="stSidebar"] [data-testid="stExpander"] details {background:transparent !important;}
[data-testid="stSidebar"] [data-testid="stExpander"] summary:hover p {color:var(--lime) !important;}
[data-testid="stSidebarCollapseButton"] svg, [data-testid="stSidebarHeader"] svg {color:#FFFFFF;}
[data-testid="stSidebar"] [data-testid="stRadioGroup"] {background:#FFFFFF; border-radius:10px; padding:.45rem .7rem;}
[data-testid="stSidebar"] [data-testid="stRadioGroup"] p {color:var(--navy) !important; font-weight:600;}
[data-testid="stSidebar"] [data-testid="stCheckbox"] label > div:first-of-type {background:rgba(255,255,255,.28) !important;
  border-color:rgba(255,255,255,.6) !important;}
[data-testid="stSidebar"] [data-testid="stCheckbox"] label[data-selected="true"] > div:first-of-type {
  background:var(--lime) !important; border-color:var(--lime) !important;}
[data-testid="stSidebar"] [data-testid="stCheckbox"] label > div:first-of-type > div {background:#FFFFFF !important;}
[data-testid="stSidebar"] [data-testid="stTooltipIcon"] svg {color:rgba(255,255,255,.7);}
/* logo: the lime scan line sweeps once over the page on load; loops while a case is processed */
.gw-logo .scan {transform-box:view-box; animation:gw-scan 1.9s ease-in-out 0.2s 1 both;}
.gw-logo.busy .scan {animation:gw-scan 1.3s ease-in-out 0s infinite alternate;}
@keyframes gw-scan {0% {transform:translateY(-12px); opacity:.2;} 55% {transform:translateY(11px); opacity:1;}
                    100% {transform:translateY(0); opacity:1;}}
.gw-hero-row {display:flex; align-items:center; gap:1.4rem;}
.gw-busy {display:flex; align-items:center; gap:1rem; padding:.9rem 1.1rem; border-radius:12px;
          background:var(--action-bg); color:var(--ink); font-size:1.02rem; margin:.6rem 0;}
@media (prefers-reduced-motion: reduce) {.gw-logo .scan, .gw-logo.busy .scan {animation:none;}}
*:focus-visible {outline:3px solid var(--action) !important; outline-offset:2px;}
@media (prefers-reduced-motion: reduce) {* {transition:none !important; animation:none !important;}}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def esc(text) -> str:
    return html.escape(str(text if text is not None else ""))


def chip(text, color: str | None = None) -> str:
    style = f' style="background:{color};color:white"' if color else ""
    return f'<span class="gw-chip"{style}>{esc(text)}</span>'


def doc_chip(doc_type) -> str:
    return chip(DOC_TYPE_LABELS.get(doc_type, doc_type), DOC_TYPE_COLORS.get(doc_type, "#64748b"))


def sources(pages) -> str:
    return "".join(f'<span class="gw-src" title="Quelle: Seite {esc(p)}">S.&nbsp;{esc(p)}</span>' for p in pages or [])


def card(title: str, items: list[str], kind: str = "info", empty: str = "Keine Angaben gefunden.") -> str:
    """items are already-escaped HTML snippets."""
    body = "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>" if items else f'<span class="gw-muted">{esc(empty)}</span>'
    cls = {"cave": "gw-card gw-cavecard", "warn": "gw-note", "ok": "gw-contact"}.get(kind, "gw-card")
    return f'<div class="{cls}"><h4>{esc(title)}</h4>{body}</div>'


def correction_list(items: list[dict]) -> str:
    labels = {"ocr_typo": "OCR-Fehler", "implausible": "unplausibel",
              "document_correction": "Korrektur im Dokument"}
    rows = []
    for item in items:
        kind = item["kind"]
        corrected = item["corrected"] or "kein Vorschlag"
        badge = f'<span class="gw-fix-kind">{esc(labels.get(kind, kind))}</span>'
        rows.append(f'<li><s>{esc(item["original"])}</s> → <b>{esc(corrected)}</b> {badge}'
                    f'{sources([item["page"]])}<br><span class="gw-muted">{esc(item["reason"])}</span></li>')
    return '<div class="gw-note gw-fix"><h4>KI-Korrekturen – bitte prüfen</h4><ul>' + "".join(rows) + "</ul></div>"


def html_block(markup: str):
    st.markdown(markup, unsafe_allow_html=True)

# ------------------------------------------------------------------ images (cached)

@st.cache_data(show_spinner=False, max_entries=400)
def thumbnail(path: str, mtime: float, width: int = 360) -> bytes:
    img = Image.open(path)
    img.thumbnail((width, width * 2))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=80)
    return buf.getvalue()


@st.cache_data(show_spinner="Seite wird aufbereitet …", max_entries=60)
def cleaned_page(path: str, mtime: float) -> tuple[np.ndarray, list[str]]:
    return preprocess(load_image(path))


def highlight(clean: np.ndarray, lines: list[dict], facts: list[dict]) -> np.ndarray:
    """Draw boxes around the OCR lines that facts came from, coloured by fact type."""
    out = cv2.cvtColor(clean, cv2.COLOR_GRAY2BGR) if clean.ndim == 2 else clean.copy()
    h, w = out.shape[:2]
    by_text = {}
    for f in facts:
        if f.get("source_text"):
            if f["kind"] == "corrections":
                by_text[f["source_text"]] = f["kind"]
            else:
                by_text.setdefault(f["source_text"], f["kind"])
    pad = max(4, w // 300)
    for line in lines:
        kind = by_text.get(line["text"])
        if not kind or not line.get("bbox"):
            continue
        b = line["bbox"]
        p0 = (max(int(b["x0"] * w) - pad, 0), max(int(b["y0"] * h) - pad, 0))
        p1 = (min(int(b["x1"] * w) + pad, w - 1), min(int(b["y1"] * h) + pad, h - 1))
        overlay = out.copy()
        cv2.rectangle(overlay, p0, p1, FACT_COLORS_BGR.get(kind, (0, 0, 255)), -1)
        out = cv2.addWeighted(overlay, 0.18, out, 0.82, 0)
        cv2.rectangle(out, p0, p1, FACT_COLORS_BGR.get(kind, (0, 0, 255)), max(2, w // 600))
    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)


def ocr_cache(out_dir: Path, file_name: str, engine: str) -> dict | None:
    f = out_dir / "ocr" / f"{Path(file_name).stem}_{engine}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def legend() -> str:
    def hexcol(bgr):
        return "#%02x%02x%02x" % (bgr[2], bgr[1], bgr[0])
    return "".join(chip(FACT_LABELS[k], hexcol(c)) for k, c in FACT_COLORS_BGR.items() if k != "negatives")


def section(title: str, items: list[str], empty: str = "Nichts gefunden.") -> str:
    body = "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>" if items else f'<div class="empty">{esc(empty)}</div>'
    return f'<div class="gw-sec"><h4>{esc(title)}</h4>{body}</div>'


def cave_panel(items: list[str]) -> str:
    body = "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>" if items else \
        '<div class="gw-muted">Keine CAVE-Angaben in den Dokumenten gefunden. Bitte trotzdem erfragen.</div>'
    return f'<div class="gw-cave"><span class="stamp">CAVE</span>{body}</div>'


def strip(cells: list[tuple]) -> str:
    """cells: (value, label, tone) with tone in '', 'bad', 'warn', 'good'."""
    return '<div class="gw-strip">' + "".join(
        f'<div class="{tone}"><div class="v">{esc(v)}</div><div class="l">{esc(l)}</div></div>'
        for v, l, tone in cells) + "</div>"


def med_table(rows: list[dict]) -> str:
    labels = {"new": "neu", "paused": "pausiert", "stopped": "abgesetzt"}
    out = ['<div style="overflow-x:auto"><table class="gw-meds"><thead><tr><th>Wirkstoff</th><th class="k">Stärke</th><th class="k">Dosierung</th>'
           '<th></th><th>Quelle</th></tr></thead><tbody>']
    for r in rows:
        off = r["status"] in ("stopped", "paused")
        tags = ""
        if r["status"] in labels:
            tags += f'<span class="gw-st {r["status"]}">{labels[r["status"]]}</span> '
        if r.get("flag"):
            tags += '<span class="gw-st unk">prüfen</span> '
        if r.get("ai_fix"):
            tags += '<span class="gw-st unk" title="KI-Hinweis zur Quellzeile; bitte am Dokument prüfen">KI-korrigiert</span> '
        if r.get("confirmed"):
            tags += '<span class="gw-ok" title="ärztlich bestätigt">✓</span>'
        pages = [x.strip() for x in str(r["sources"]).split(",") if x.strip()]
        out.append(f'<tr class="{"off" if off else ""}"><td class="n">{esc(r["name"])}</td>'
                   f'<td class="k">{esc(r["strength"] or "–")}</td><td class="k">{esc(r["dosing"] or "–")}</td><td>{tags}</td>'
                   f'<td class="src k"><span class="gw-src">S.&nbsp;{esc(", ".join(pages))}</span></td></tr>')
    out.append("</tbody></table></div>")
    return "".join(out)


LOGO_SVG = """<svg class="gw-logo{cls}" xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 48 48"
 role="img" aria-label="Get Well OCR"><rect width="48" height="48" rx="11" fill="#102B49"/>
<path d="M16 9h11l7 7v20a2 2 0 0 1-2 2H16a2 2 0 0 1-2-2V11a2 2 0 0 1 2-2Z M27 9v7h7" fill="none" stroke="#FFF"
 stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M21 31.5h6 M24 28.5v6" fill="none" stroke="#FFF" stroke-width="2.2" stroke-linecap="round"/>
<g class="scan"><path d="M10 24h28" fill="none" stroke="#B9EC54" stroke-width="3" stroke-linecap="round"/></g></svg>"""


def logo(size: int = 48, busy: bool = False) -> str:
    """The Get Well OCR mark as inline SVG. busy=True: the scan line keeps moving (processing)."""
    return LOGO_SVG.replace("{cls}", " busy" if busy else "").replace("{size}", str(size))


def busy_box(text: str) -> str:
    return f'<div class="gw-busy">{logo(40, busy=True)}<div>{esc(text)}</div></div>'
