"""Case workspace: many pages of one patient -> sorted documents -> reviewed ER overview.

Flow on screen (mirrors the pipeline):
  sidebar   pick or create a case · choose the OCR engine · process
  header    patient, case, key numbers
  tabs      ER summary · Pages · Medication (doctor review) · Labs & findings · Documents · Export · Evaluation
"""
from __future__ import annotations

import json
import re
from datetime import datetime

import pandas as pd
import streamlit as st

from src import config, store
from src.case import CONFIDENCE_MIN, SHARPNESS_MIN, process_case, summary_text
from src.evaluate import score_case
from src.report import er_report
from src.export import LANGUAGES, patient_plan_pdf, to_csv, to_fhir
from views.components import (DOC_TYPE_LABELS, FACT_LABELS, STATUS_LABELS, card, cave_panel, chip, cleaned_page,
                              doc_chip, esc, highlight, html_block, inject_css, legend, logo, med_table, ocr_cache,
                              section, sources, strip, thumbnail, busy_box, correction_list)
from src import mistral

inject_css()
MED_STATUSES = ["active", "new", "paused", "stopped"]

# ================================================================== sidebar: case + processing

cases = store.list_cases()
st.session_state.setdefault("case_id", None)


def _open_case():
    st.session_state.case_id = st.session_state.case_pick


def _new_case():
    st.session_state.case_id = None
    st.session_state.case_pick = None


def _process(case_dir_pages, case_out, engine, fresh, extractor):
    anim = st.empty()
    text = ("Unterlagen werden gelesen und mit Mistral Large 3 ausgewertet …" if extractor == "llm"
            else "Unterlagen werden gelesen, sortiert und abgeglichen …")
    anim.markdown(busy_box(text), unsafe_allow_html=True)
    bar = st.progress(0.0, text="Starte …")

    def _progress(msg: str):
        m = re.match(r"\[(\d+)/(\d+)\]", msg)
        if m:
            bar.progress(int(m.group(1)) / int(m.group(2)), text=f"Seite {m.group(1)} von {m.group(2)} gelesen")
        elif m := re.match(r"\[KI (\d+)/(\d+)\]", msg):
            bar.progress(int(m.group(1)) / int(m.group(2)),
                         text=f"Mistral Large 3 wertet Seite {m.group(1)} von {m.group(2)} aus")

    try:
        process_case(case_dir_pages, case_out, engine, fresh, progress=_progress, extractor=extractor)
    except mistral.MistralError as e:
        anim.empty()
        bar.empty()
        st.error(f"Mistral OCR nicht erreichbar: {e}. Bitte Tesseract wählen oder die Zugangsdaten in .env prüfen.")
        st.stop()
    anim.empty()
    bar.empty()


def _scan_patient_id():
    """Barcode photo uploaded -> decode -> fill the PatientenID field."""
    from src.patient_barcode import patient_id_from_image
    f = st.session_state.get(f"pid_scan_{st.session_state.pid_scan_n}")
    if f is None:
        return
    try:
        pid, texts = patient_id_from_image(f.getvalue())
    except Exception as e:                       # unreadable image
        st.session_state.pid_scan_msg = ("warn", f"Bild konnte nicht gelesen werden: {e}")
        return
    if pid:
        st.session_state.patient_id = pid
        st.session_state.pid_scan_n += 1         # fresh uploader for the next scan
        st.session_state.pid_scan_msg = ("ok", f"PatientenID aus Barcode übernommen: {pid}")
    elif texts:
        st.session_state.pid_scan_msg = ("warn", f"Barcode gelesen, aber keine PatientenID erkannt: {texts[0][:80]}")
    else:
        st.session_state.pid_scan_msg = ("warn", "Kein Barcode gefunden. Näher heran, scharf und gut beleuchtet "
                                                 "fotografieren oder die ID manuell eingeben.")


with st.sidebar:
    st.button("＋ Neuer Fall", type="primary" if st.session_state.case_id else "secondary",
              use_container_width=True, on_click=_new_case)
    def _label(c):
        when = ""
        if c.get("created_at"):
            when = datetime.fromisoformat(c["created_at"]).strftime("%d.%m. %H:%M") + "  ·  "
        return f"{c['label']}  ·  {when}{c['n_pages']} S."
    labels = {c["id"]: _label(c) for c in cases}
    ids = list(labels)
    st.selectbox("Gespeicherten Fall öffnen", ids, format_func=labels.get, key="case_pick",
                 index=ids.index(st.session_state.case_id) if st.session_state.case_id in ids else None,
                 placeholder="Fall auswählen …", on_change=_open_case)

    st.markdown("### Verarbeitung")
    engine = st.radio("Texterkennung", ["tesseract", "mistral"], horizontal=True,
                      index=1 if config.OCR_ENGINE == "mistral" else 0,
                      format_func={"tesseract": "Tesseract", "mistral": "Mistral OCR"}.get,
                      help="Tesseract läuft offline auf diesem Rechner. Mistral (Azure, EU-Region "
                           "Schweden) liest Tabellen, Handschrift und schlechte Fotos besser.")
    if engine == "mistral" and not mistral.ocr_available():
        st.warning("Mistral OCR: MISTRAL_CHAT_ENDPOINT und MISTRAL_API_KEY in .env eintragen.")
    extractor = st.radio("Auswertung", ["rules", "llm"], horizontal=True,
                         index=1 if config.EXTRACTOR == "llm" else 0,
                         format_func={"rules": "Regeln", "llm": "KI (Mistral Large 3)"}.get,
                         help="Regeln laufen lokal. Die KI sendet erkannte Textzeilen an Mistral (Azure, EU). "
                              "Nur fiktive Daten verwenden und markierte Korrekturen am Original prüfen.")
    if extractor == "llm" and not mistral.chat_available():
        st.warning("Mistral-Auswertung: MISTRAL_CHAT_ENDPOINT und MISTRAL_API_KEY in .env eintragen. "
                   "Ohne KI-Ergebnis werden die Regeln verwendet.")
    fresh = st.toggle("Texterkennung neu ausführen", value=False,
                      help="Aus: gespeicherte Ergebnisse verwenden (schnell, offline).")
    run = st.button("▶ Fall erneut verarbeiten", use_container_width=True,
                    disabled=not st.session_state.case_id)

    private = [c for c in cases if c["private"]]
    with st.expander(f"Verlauf löschen ({len(private)})"):
        st.caption("Löscht alle hochgeladenen Fälle mit Fotos, Texterkennung und Prüfungen. Testfälle bleiben.")
        sure = st.checkbox("Ja, endgültig löschen", key="del_all_ok")
        if st.button("Alle hochgeladenen Fälle löschen", disabled=not (sure and private), use_container_width=True):
            n = store.delete_all_private()
            if st.session_state.case_id not in {c["id"] for c in cases if not c["private"]}:
                st.session_state.case_id = None
            st.session_state.pop("case_pick", None)
            st.session_state.pop("del_all_ok", None)
            st.toast(f"{n} Fälle gelöscht", icon="🗑")
            st.rerun()

    st.divider()
    st.caption("Healthcare Hackathon Bayern 2026 · Demo mit fiktiven Daten")

case_id = st.session_state.case_id

# ================================================================== start screen: waits for an upload

if not case_id:
    html_block("""
<div class="gw-hero">
  <div class="gw-hero-row">""" + logo(84) + """<div class="gw-hero-title">Unterlagen einlesen</div></div>
  <div class="gw-hero-sub">Fotos oder PDFs der mitgebrachten Unterlagen hochladen. Get Well OCR liest, sortiert
  und prüft sie und erstellt die Übergabe für die Notaufnahme. Jede Angabe bleibt mit ihrer Quellseite verknüpft.</div>
</div>""")
    files_up = st.file_uploader("Unterlagen", type=store.UPLOAD_TYPES, accept_multiple_files=True,
                                label_visibility="collapsed",
                                help="Mehrere Dateien möglich. Die Reihenfolge der Dateien ist die Seitenreihenfolge.")
    st.session_state.setdefault("pid_scan_n", 0)
    c1, c_cam, c2 = st.columns([3, 1, 2], vertical_alignment="bottom")
    label = c1.text_input("PatientenID (optional)", key="patient_id", placeholder="z. B. 12345678",
                          help="Manuell eingeben oder über 📷 den Barcode vom KIS-Etikett / Patientenarmband scannen.")
    with c_cam.popover("Scan", icon=":material/photo_camera:", use_container_width=True,
                       help="Barcode des KIS-Etiketts fotografieren oder Bild hochladen"):
        st.caption("Foto vom Barcode (KIS-Etikett, Armband). Am Handy öffnet sich die Kamera.")
        st.file_uploader("Barcode-Bild", type=["png", "jpg", "jpeg", "heic", "heif", "webp"],
                         key=f"pid_scan_{st.session_state.pid_scan_n}", on_change=_scan_patient_id,
                         label_visibility="collapsed")
    go = c2.button("Unterlagen auswerten", type="primary", use_container_width=True)
    if msg := st.session_state.pop("pid_scan_msg", None):
        (st.success if msg[0] == "ok" else st.warning)(msg[1])
    if go:
        if not files_up:
            st.error("Bitte zuerst Fotos oder PDFs auswählen.")
        else:
            try:
                new_id = store.create_case(label.strip() or "Neuer Fall", [(f.name, f.getvalue()) for f in files_up])
            except RuntimeError as e:
                st.error(str(e))
                st.stop()
            _process(store.pages_dir(store.PRIVATE_ROOT / new_id), store.out_dir(new_id), engine, False, extractor)
            st.session_state.case_id = new_id
            st.session_state.pop("case_pick", None)      # picker shows the new case on the next run
            st.session_state.pop("patient_id", None)
            st.rerun()
    html_block("""
<div class="gw-steps">
  <div><span class="n">1</span><b>Fotografieren</b><br>Alle Seiten mit dem Handy, in beliebiger Reihenfolge.
       Unscharfe Seiten werden zum erneuten Fotografieren markiert.</div>
  <div><span class="n">2</span><b>Prüfen</b><br>Medikation, Diagnosen und CAVE aus allen Dokumenten,
       Widersprüche markiert. Die Ärztin bestätigt.</div>
  <div><span class="n">3</span><b>Übergeben</b><br>Übergabetext zum Kopieren, FHIR, JSON und Medikationsplan
       für Patient:innen in vier Sprachen.</div>
</div>
<div class="gw-muted" style="margin-top:1rem">Nur fiktive oder anonymisierte Dokumente verwenden.</div>""")
    st.stop()

case = next((c for c in cases if c["id"] == case_id), None)
if case is None:                      # deleted or moved meanwhile
    st.session_state.case_id = None
    st.rerun()
out = store.out_dir(case_id)
files = store.page_files(case["dir"])

if run:
    _process(case["pages_dir"], out, engine, fresh, extractor)
    st.session_state.pop(f"review_{case_id}", None)
    st.toast("Fall verarbeitet", icon="✅")

result = store.load_result(case_id)

# ================================================================== header

patient = (result or {}).get("patient") or {}
pname = patient.get("name") or case["label"]
birth = f"geb. {patient['birth']}" if patient.get("birth") else ""
processed = (result or {}).get("processed_at", "")
extractor_label = "KI-Auswertung" if (result or {}).get("extractor") == "llm" else "Regeln"
age = ""
if patient.get("birth"):
    try:
        bd = datetime.strptime(patient["birth"], "%d.%m.%Y")
        now = datetime.now()
        age = f"{now.year - bd.year - ((now.month, now.day) < (bd.month, bd.day))} Jahre"
    except ValueError:
        pass
who = ", ".join(x for x in [f"<b>{esc(age)}</b>" if age else "", esc(birth)] if x)
html_block(f"""
<div class="gw-patient">
  <div><div class="name">{esc(pname)}</div>
       <div class="who">{who or 'Patientendaten nicht erkannt'}</div></div>
  <div class="side">
    <span class="gw-tag {'fict' if not case['private'] else ''}">{'Fiktive Daten' if not case['private'] else 'Privater Fall'}</span>
    {f'<span class="gw-tag">{esc(result["engine"])}</span>' if result else ''}
    {f'<span class="gw-tag">{esc(extractor_label)}</span>' if result else ''}<br>
    Fall {esc(case_id)}, {case['n_pages']} Seiten<br>
    {('verarbeitet ' + esc(processed.replace('T', ' ')[:16])) if processed else 'noch nicht verarbeitet'}
  </div>
</div>""")

if not result:
    st.info(f"{case['n_pages']} Seiten bereit. Links auf **▶ Fall verarbeiten** klicken.")
    cols = st.columns(6)
    for i, f in enumerate(files):
        with cols[i % 6]:
            st.image(thumbnail(str(f), f.stat().st_mtime), caption=f"S. {i + 1}", use_container_width=True)
    st.stop()

summary, pages, docs = result["summary"], result["pages"], result["documents"]
retake = [p for p in pages if p["status"] == "retake"]
answers = json.loads(case["answers"].read_text(encoding="utf-8")) if case["answers"] else None
score = score_case(result, answers) if answers else None

# ------------------------------------------------------------------ doctor review state (persisted)

def _machine_rows() -> list[dict]:
    conflict_names = {m["name"] for m in summary["medications"]
                      if any(m["name"] in c["text"] for c in summary["conflicts"] + summary["warnings"])}
    return [{"confirmed": False, "name": m["name"], "strength": m.get("strength") or "",
             "dosing": m.get("dosing") or "", "status": m["status"],
             "flag": "⚠ prüfen" if m["name"] in conflict_names or m.get("unknown") else "",
             "ai_fix": bool(m.get("ai_corrected")),
             "sources": ", ".join(str(s) for s in m["sources"])} for m in summary["medications"]]


key = f"review_{case_id}"
if key not in st.session_state:
    saved = store.load_review(case_id)
    fresh_review = not saved or saved.get("processed_at") != result.get("processed_at")
    st.session_state[key] = ({"processed_at": result.get("processed_at"), "meds": _machine_rows(),
                              "machine": _machine_rows(), "conflicts_ok": [], "reviewer": ""}
                             if fresh_review else saved)
review = st.session_state[key]


def _save_review():
    store.save_review(case_id, review)


def _audit() -> list[dict]:
    machine = {m["name"]: m for m in review["machine"]}
    changes = []
    for row in review["meds"]:
        before = machine.get(row["name"])
        for field in ("strength", "dosing", "status"):
            if before and str(before[field]) != str(row[field]):
                changes.append({"medication": row["name"], "field": field, "machine": before[field],
                                "doctor": row[field]})
    return changes


n_unconfirmed = sum(not r["confirmed"] for r in review["meds"])
n_open_conflicts = len(summary["conflicts"]) - len(review["conflicts_ok"])

n_conf = len(review["meds"]) - n_unconfirmed
cells = [(len(pages), "Seiten fotografiert", ""), (len(docs), "Dokumente erkannt", ""),
         (len(retake), "neu fotografieren", "bad" if retake else "good"),
         (max(n_open_conflicts, 0), "Widersprüche offen", "warn" if n_open_conflicts > 0 else "good"),
         (f"{n_conf}/{len(review['meds'])}", "Medikamente bestätigt", "good" if n_unconfirmed == 0 else "")]
cells.append((f"{score['needles_found']}/{score['needles_total']}", "kritische Fakten (Testfall)",
              "good" if score["needles_found"] == score["needles_total"] else "warn") if score
             else (len(summary["warnings"]), "Sicherheitshinweise", "warn" if summary["warnings"] else ""))
html_block(strip(cells))

if retake:
    st.warning("**Bitte neu fotografieren:** " + ", ".join(
        f"Seite {p['page']} ({'zu unscharf' if p['quality'] == 'too_blurry' else 'Text unlesbar'})" for p in retake))

tabs = st.tabs(["🩺 Notaufnahme-Übersicht", "📄 Seiten", "💊 Medikation", "🧪 Labor & Befunde",
                "🗂 Dokumente", "⬇ Export"] + (["📊 Auswertung"] if score else []))

# ================================================================== tab: ER summary

with tabs[0]:
    left, right = st.columns([1, 1], gap="large")
    with left:
        html_block(cave_panel([f"<b>{esc(c['text'])}</b>{sources(c['sources'])}" for c in summary["cave"]]))
        if summary["warnings"]:
            html_block(card("Sicherheitshinweise", [f"{esc(w['text'])}{sources(w['sources'])}"
                                                    for w in summary["warnings"]], "warn"))
        if summary.get("corrections"):
            # most important first: implausible values, document corrections, then med/lab typos, ICD typos last
            corr = sorted(summary["corrections"], key=lambda c: (
                {"implausible": 0, "document_correction": 1}.get(c["kind"], 2), c.get("field") == "icd10"))
            html_block(correction_list(corr[:6]))
            if len(corr) > 6:
                with st.expander(f"Weitere {len(corr) - 6} KI-Korrekturen"):
                    html_block(correction_list(corr[6:]))
        if summary.get("extract_errors"):
            fallback_pages = ", ".join(str(e["page"]) for e in summary["extract_errors"])
            st.warning(f"Regelbasierte Auswertung für folgende Seiten, weil Mistral fehlgeschlagen ist: {fallback_pages}.")
        st.markdown("#### Zu klären")
        if not summary["conflicts"]:
            st.caption("Die Dokumente widersprechen sich nicht.")
        else:
            st.caption("Diese Angaben widersprechen sich zwischen den Dokumenten. Abhaken, wenn geklärt.")
        for i, c in enumerate(summary["conflicts"]):
            done = i in review["conflicts_ok"]
            t, b = st.columns([5, 1], vertical_alignment="center")
            t.markdown(f'<div class="gw-conflict{" done" if done else ""}">{esc(c["text"])}{sources(c["sources"])}</div>',
                       unsafe_allow_html=True)
            ok = b.checkbox("✓", value=done, key=f"cf_{case_id}_{i}", help="Als geklärt markieren")
            if ok != done:
                review["conflicts_ok"] = sorted(set(review["conflicts_ok"]) ^ {i})
                _save_review()
                st.rerun()
    with right:
        st.markdown("#### Medikation")
        order = {"new": 0, "active": 0, "paused": 1, "stopped": 2}
        html_block(med_table(sorted(review["meds"], key=lambda r: (order.get(r["status"], 0), r["name"]))))
        st.caption("Abgeglichen aus allen Dokumenten. Prüfen und bestätigen im Tab 💊 Medikation.")
        html_block(section("Diagnosen", [
            f"{esc(d['text'])}{' <span class=gw-muted>' + esc(d['icd10']) + '</span>' if d['icd10'] else ''}"
            f"{sources(d['sources'])}"
            + ("".join(f"<br><span class='gw-muted'>– {esc(x)}</span>" for x in d.get("details", [])))
            for d in summary["diagnoses"][:12]]))
        html_block(card("Kontakt / Vorsorgevollmacht", [f"{esc(c['text'])}{sources(c['sources'])}"
                                                        for c in summary["contacts"]], "ok",
                        "Keine Kontaktperson gefunden."))
    st.markdown("##### Übergabetext (Entwurf)")
    st.caption("Format der Notaufnahme. Endgültige Fassung mit bestätigter Medikation im Tab ⬇ Export.")
    st.code(er_report(result, review["meds"], "de", confirmed=n_unconfirmed == 0, reviewer=review.get("reviewer", ""),
                      resolved=review["conflicts_ok"]), language=None, wrap_lines=True)

# ================================================================== tab: pages

with tabs[1]:
    f1, f2 = st.columns([2, 3])
    show = f1.segmented_control("Anzeigen", ["Alle", "Neu fotografieren"], default="Alle", key=f"pf_{case_id}")
    types = sorted({p["doc_type"] for p in pages if p["doc_type"]}, key=lambda t: DOC_TYPE_LABELS.get(t, t))
    type_filter = f2.multiselect("Dokumenttyp", types, format_func=lambda t: DOC_TYPE_LABELS.get(t, t),
                                 key=f"tf_{case_id}")
    visible = [p for p in pages if (show != "Neu fotografieren" or p["status"] == "retake")
               and (not type_filter or p["doc_type"] in type_filter)]
    sel_key = f"sel_{case_id}"
    st.session_state.setdefault(sel_key, pages[0]["page"])

    cols = st.columns(6)
    for i, p in enumerate(visible):
        f = case["pages_dir"] / p["file"]
        with cols[i % 6]:
            st.image(thumbnail(str(f), f.stat().st_mtime), use_container_width=True)
            badge = (chip("NEU FOTOGRAFIEREN", "#b91c1c") if p["status"] == "retake" else doc_chip(p["doc_type"]))
            html_block(f'<div class="gw-thumbcap"><b>S. {p["page"]}</b> · {p["doc_id"] or "–"}<br>{badge}</div>')
            if st.button("Öffnen", key=f"open_{case_id}_{p['page']}", use_container_width=True,
                         type="primary" if st.session_state[sel_key] == p["page"] else "secondary"):
                st.session_state[sel_key] = p["page"]
                st.rerun()

    st.divider()
    page_no = st.session_state[sel_key]
    p = next(x for x in pages if x["page"] == page_no)
    f = case["pages_dir"] / p["file"]
    ocr = ocr_cache(out, p["file"], result["engine"])
    st.markdown(f"#### Seite {page_no} · {DOC_TYPE_LABELS.get(p['doc_type'], 'nicht zugeordnet')}")
    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        view = st.segmented_control("Ansicht", ["Foto", "Aufbereitet + Markierungen"],
                                    default="Aufbereitet + Markierungen" if p["status"] == "done" else "Foto",
                                    key=f"view_{case_id}")
        if result["engine"] == "mistral":
            st.caption("Mistral OCR liefert keine Positionen: Fundstellen sind rechts als Text aufgelistet.")
        if view == "Foto" or not ocr:
            st.image(str(f), use_container_width=True)
        else:
            clean, _ = cleaned_page(str(f), f.stat().st_mtime)
            st.image(highlight(clean, ocr["lines"], p.get("facts", [])), use_container_width=True)
            html_block(legend())
    with c2:
        if p["status"] == "retake":
            reason = (f"zu unscharf (Schärfe {p['sharpness']} < {SHARPNESS_MIN})" if p["quality"] == "too_blurry"
                      else f"Text kaum lesbar (Lesesicherheit {p['mean_confidence']:.2f} < {CONFIDENCE_MIN})")
            html_block(card("Bitte neu fotografieren", [esc(reason), "Seite wurde nicht ausgewertet."], "cave"))
        doc = next((d for d in docs if d["doc_id"] == p["doc_id"]), None)
        info = [f"Dokument: <b>{esc(doc['title'])}</b> ({esc(doc['doc_id'])}), Seiten {', '.join(map(str, doc['pages']))}"
                if doc else "Dokument: –",
                f"Datum: {esc(doc['date'] or 'nicht erkannt')}" if doc else "",
                f"Bildschärfe: {p['sharpness']}  ·  Lesesicherheit: "
                f"{p['mean_confidence'] if p['mean_confidence'] is not None else '–'}"]
        if ocr:
            info.append("Aufbereitung: " + esc(", ".join(s for s in ocr["steps"] if s != "gray")))
        html_block(card("Seiteninformation", [i for i in info if i], "info"))
        facts = p.get("facts", [])
        html_block(card(f"Gefunden auf dieser Seite ({len(facts)})",
                        [f"{chip(FACT_LABELS.get(x['kind'], x['kind']))} {esc(x['label'])}" for x in facts[:30]],
                        "info", "Keine strukturierten Fakten."))
        if p.get("corrections"):
            html_block(correction_list(p["corrections"]))
        if ocr:
            with st.expander("Erkannter Text"):
                st.text("\n".join(l["text"] for l in ocr["lines"]))

# ================================================================== tab: medication review

with tabs[2]:
    st.markdown("##### Medikationsabgleich")
    st.caption("Aus allen Dokumenten zusammengeführt: neuestes Dokument gilt, Absetzungen haben Vorrang. "
               "Bitte jede Zeile prüfen, bei Bedarf korrigieren und bestätigen. Änderungen werden protokolliert.")
    b1, b2, _ = st.columns([1, 1, 4])
    if b1.button("Alle bestätigen", key=f"all_{case_id}"):
        for r in review["meds"]:
            r["confirmed"] = True
        _save_review()
        st.session_state[f"ed_ver_{case_id}"] = st.session_state.get(f"ed_ver_{case_id}", 0) + 1
        st.rerun()
    if b2.button("Auf Maschinenstand zurücksetzen", key=f"reset_{case_id}"):
        review["meds"] = [dict(r) for r in review["machine"]]
        _save_review()
        st.session_state[f"ed_ver_{case_id}"] = st.session_state.get(f"ed_ver_{case_id}", 0) + 1
        st.rerun()

    edited = st.data_editor(
        pd.DataFrame(review["meds"]), key=f"ed_{case_id}_{st.session_state.get(f'ed_ver_{case_id}', 0)}",
        hide_index=True, use_container_width=True, num_rows="dynamic",
        column_order=["confirmed", "flag", "name", "strength", "dosing", "status", "sources"],
        column_config={
            "confirmed": st.column_config.CheckboxColumn("✔", help="Ärztlich bestätigt", width="small"),
            "flag": st.column_config.TextColumn("Hinweis", disabled=True, width="small"),
            "name": st.column_config.TextColumn("Wirkstoff", required=True),
            "strength": st.column_config.TextColumn("Stärke"),
            "dosing": st.column_config.TextColumn("Dosierung", help="Mo-Mi-Ab-Na, z. B. 1-0-1-0"),
            "status": st.column_config.SelectboxColumn("Status", options=MED_STATUSES, required=True),
            "sources": st.column_config.TextColumn("Quelle (Seiten)", disabled=True),
        })
    rows = edited.fillna("").to_dict("records")
    for r in rows:
        r["confirmed"] = bool(r.get("confirmed"))
        r["ai_fix"] = bool(r.get("ai_fix"))
        r["status"] = r.get("status") or "active"
    if rows != review["meds"]:
        review["meds"] = rows
        _save_review()
        st.rerun()

    changes = _audit()
    if changes:
        with st.expander(f"Korrekturprotokoll ({len(changes)})"):
            st.dataframe(pd.DataFrame(changes), hide_index=True, use_container_width=True)
    if summary["medication_history"]:
        st.caption("Nur in älteren Dokumenten (> 1 Jahr) erwähnt, nicht übernommen: " + ", ".join(
            f"{h['name']} (S. {', '.join(map(str, h['sources']))})" for h in summary["medication_history"]))

# ================================================================== tab: labs & findings

with tabs[3]:
    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        st.markdown("##### Laborwerte (neuester Wert, Verlauf)")
        if summary["labs"]:
            flag_txt = {"H": "▲ hoch", "L": "▼ niedrig", "": ""}
            st.dataframe(pd.DataFrame([{"Parameter": l["name"], "Wert": l["value"], "Einheit": l["unit"],
                                        "": flag_txt.get(l["flag"], l["flag"]), "Verlauf": l["trend"],
                                        "Quelle": ", ".join(f"S. {s}" for s in l["sources"])}
                                       for l in summary["labs"]]), hide_index=True, use_container_width=True)
        else:
            st.caption("Keine Laborwerte erkannt.")
    with c2:
        html_block(card("Befunde", [f"{esc(f['text'])}{sources(f['sources'])}" for f in summary.get("findings", [])]))
        if summary.get("ignored"):
            html_block(card("Ignoriert (nicht medizinisch)",
                            [f"{esc(i['doc_id'])}: Seiten {', '.join(map(str, i['pages']))}" for i in summary["ignored"]]))

# ================================================================== tab: documents

with tabs[4]:
    st.markdown("##### Zeitstrahl")
    st.dataframe(pd.DataFrame([{"Datum": t["date"] or "–", "Dokument": t["text"], "ID": t["doc_id"],
                                "Seiten": ", ".join(map(str, t["pages"]))} for t in summary["timeline"]]),
                 hide_index=True, use_container_width=True)
    st.markdown("##### Dokumente")
    for d in docs:
        with st.expander(f"{'⚠ ' if d.get('type_check') else ''}{d['doc_id']} · {d['title']} · {d['date'] or 'ohne Datum'} · "
                         f"{len(d['pages'])} Seite(n)"):
            how = {"rules": "Schlüsselwörter", "model": "Sprachmodell (Embedding)"}.get(d.get("classified_by"), "Regeln")
            html_block(doc_chip(d["type"]) + f'<span class="gw-muted"> zugeordnet durch {how}, '
                                             f'Sicherheit {d["type_confidence"]:.0%}</span>')
            if d.get("type_check"):
                st.warning(f"Regeln und Modell sind uneinig: Regeln = {DOC_TYPE_LABELS.get(d['rules_type'])}, "
                           f"Modell = {DOC_TYPE_LABELS.get(d['model_type'])}. Bitte Dokumenttyp prüfen.")
            cols = st.columns(6)
            for i, pg in enumerate(d["pages"]):
                f = case["pages_dir"] / pages[pg - 1]["file"]
                cols[i % 6].image(thumbnail(str(f), f.stat().st_mtime), caption=f"S. {pg}", use_container_width=True)

# ================================================================== tab: export

with tabs[5]:
    ready = n_unconfirmed == 0
    if not ready:
        st.warning(f"Noch {n_unconfirmed} Medikament(e) nicht bestätigt (Tab 💊). "
                   "Exporte werden erst nach vollständiger ärztlicher Prüfung freigegeben.")
    reviewer = st.text_input("Geprüft von", value=review.get("reviewer", ""), key=f"rv_{case_id}",
                             placeholder="Name der Ärztin / des Arztes")
    if reviewer != review.get("reviewer", ""):
        review["reviewer"] = reviewer
        _save_review()

    confirmed_meds = [{"name": r["name"], "strength": r["strength"] or None, "dosing": r["dosing"] or None,
                       "status": r["status"], "form": None, "as_needed": False,
                       "sources": [int(s) for s in re.findall(r"\d+", r["sources"])]} for r in review["meds"]]
    confirmed_summary = {**summary, "medications": confirmed_meds}

    # ---- patient history as prose, written by Mistral Large 3 from the confirmed facts only
    st.markdown("##### Anamnese als Fließtext (Mistral Large 3)")
    hist = review.get("history_ai")
    if not mistral.chat_available():
        st.caption("Mistral Large 3 ist nicht eingerichtet (MISTRAL_CHAT_ENDPOINT und MISTRAL_API_KEY in .env). "
                   "Der Übergabetext enthält dann die Anamnese als Liste nach Datum.")
    else:
        st.caption("Das Modell bekommt nur die geprüften Fakten dieses Falls, keine Fotos und keinen Rohtext. "
                   "Jede Zahl und jedes Datum im Ergebnis wird gegen die Fakten geprüft.")
        if st.button("✨ Anamnese mit Mistral formulieren", disabled=not ready, key=f"ai_{case_id}",
                     help="Erst möglich, wenn alle Medikamente bestätigt sind."):
            from src.history import write_history
            with st.spinner("Mistral Large 3 formuliert …"):
                try:
                    h = write_history(result, confirmed_meds)
                    review["history_ai"] = {"text": h["text"], "unsupported": h["unsupported"], "accepted": False}
                    _save_review()
                    st.rerun()
                except mistral.MistralError as e:
                    st.error(f"Mistral nicht erreichbar: {e}")
        if hist:
            from src.history import history_facts, unsupported_numbers
            new_text = st.text_area("Text (bearbeitbar)", hist["text"], height=170, key=f"aitext_{case_id}")
            if new_text != hist["text"]:
                hist.update(text=new_text, accepted=False,
                            unsupported=unsupported_numbers(new_text, history_facts(result, confirmed_meds)))
                _save_review()
            if hist["unsupported"]:
                st.warning("Nicht in den geprüften Fakten belegt: " + ", ".join(hist["unsupported"]) +
                           ". Bitte korrigieren oder entfernen.")
            else:
                st.success("Alle Zahlen und Daten im Text sind in den geprüften Fakten belegt.")
            accepted = st.checkbox("Text geprüft und für den Übergabetext freigegeben",
                                   value=bool(hist.get("accepted")), key=f"aiok_{case_id}")
            if accepted != bool(hist.get("accepted")):
                hist["accepted"] = accepted
                _save_review()
                st.rerun()
    history_text = hist["text"] if hist and hist.get("accepted") else None

    rep_lang = st.segmented_control("Sprache des Übergabetexts", ["de", "en"], default="de",
                                    format_func={"de": "Deutsch", "en": "English"}.get, key=f"rl_{case_id}") or "de"
    with_src = st.toggle("Quellseiten [S. x] im Text anzeigen", value=False, key=f"src_{case_id}")
    er_text = er_report(result, confirmed_meds, rep_lang, confirmed=ready, reviewer=review.get("reviewer", ""),
                        resolved=review["conflicts_ok"], show_sources=with_src, history_text=history_text)
    stamp = f"{datetime.now():%Y%m%d-%H%M}"

    st.markdown("##### Übergabetext für das Krankenhaussystem")
    st.code(er_text, language=None, wrap_lines=True)
    payload = {**result, "review": {"reviewer": review.get("reviewer"), "updated_at": review.get("updated_at"),
                                    "medications": review["meds"], "corrections": _audit(),
                                    "conflicts_acknowledged": review["conflicts_ok"]}}
    c = st.columns(4)
    c[0].download_button("Übergabetext (.txt)", er_text.encode("utf-8"), f"{case_id}_summary_{stamp}.txt",
                         disabled=not ready, use_container_width=True)
    c[1].download_button("Fall (JSON)", json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
                         f"{case_id}_{stamp}.json", "application/json", disabled=not ready, use_container_width=True)
    c[2].download_button("FHIR R4 (Entwurf)", to_fhir(case_id, confirmed_meds, summary["diagnoses"]).encode("utf-8"),
                         f"{case_id}_fhir_{stamp}.json", "application/fhir+json", disabled=not ready,
                         use_container_width=True)
    c[3].download_button("Medikation (CSV)", to_csv(review["meds"]), f"{case_id}_medikation_{stamp}.csv",
                         "text/csv", disabled=not ready, use_container_width=True)

    st.markdown("##### Medikationsplan für Patient:innen")
    p1, p2, p3 = st.columns([2, 2, 1])
    lang = p1.selectbox("Sprache", list(LANGUAGES), format_func=LANGUAGES.get, key=f"lang_{case_id}")
    who = p2.text_input("Name auf dem Plan", value=patient.get("name") or "", key=f"pn_{case_id}")
    plan_meds = [mm for mm in confirmed_meds if mm["status"] in ("active", "new")]
    p3.download_button("PDF erstellen", patient_plan_pdf(plan_meds, lang, who) if ready else b"",
                       f"{case_id}_plan_{lang}.pdf", "application/pdf", disabled=not ready,
                       use_container_width=True)
    if case["private"]:
        st.divider()
        if st.button("🗑 Fall und alle Daten löschen", key=f"del_{case_id}"):
            store.delete_case(case_id)
            st.session_state.case_id = None
            st.session_state.case_pick = None
            st.rerun()

# ================================================================== tab: evaluation (test cases only)

if score:
    with tabs[6]:
        st.caption("Nur für Testfälle mit Lösungsdatei: zeigt, was das System gefunden hat.")
        e = st.columns(4)
        e[0].metric("Kritische Fakten", f"{score['needles_found']}/{score['needles_total']}")
        e[1].metric("Seiten richtig zugeordnet", f"{score['pages_correct']}/{score['pages_classified']}")
        e[2].metric("Widersprüche", f"{score['conflicts_flagged']} (Lösung: {score['conflicts_truth']})")
        e[3].metric("Neu fotografieren", len(score["retake"]))
        st.dataframe(pd.DataFrame([{"": "✅" if n["found"] else "❌", "ID": n["id"], "Kritischer Fakt": n["fact"]}
                                   for n in score["needles"]]), hide_index=True, use_container_width=True)
        if score["misclassified"]:
            st.dataframe(pd.DataFrame(score["misclassified"]), hide_index=True)
