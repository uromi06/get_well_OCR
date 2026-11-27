"""The ER handover text: the one output the doctor copies into the hospital system.

Format agreed with the ER doctor (plain text, no formatting needed in the receiving system):

    The patient provided the following documents:   type, date, issuer, pages
    CAVE                                              (added: allergies, anticoagulation, implants, directive)
    Diagnoses
    Current medication                                table, reconciled across ALL documents
    To clarify                                        conflicts between documents
    Labs (abnormal)
    Patient history                                   chronological, per document
    Contact / power of attorney

Every fact keeps its source page [S. x], so the doctor can check it in the app.
Labels are translated (de/en); the facts stay in the language of the documents.
v1 = assembled by rules. The "Patient history" section is where the language model
writes a short narrative tomorrow (from the same confirmed facts only).
"""
from __future__ import annotations

from datetime import datetime

LABELS = {
    "de": {"intro": "Die Patientin / der Patient hat folgende Dokumente mitgebracht:",
           "no_date": "ohne Datum", "pages": "S.", "from": "von", "dated": "vom",
           "not_used": "Nicht berücksichtigt", "retake": "unlesbar, bitte neu fotografieren",
           "irrelevant": "nicht medizinisch",
           "cave": "CAVE:", "dx": "Diagnosen:",
           "meds": "Aktuelle Medikation (abgeglichen aus {n} Dokumenten, neueste Quelle: {src}):",
           "meds_plain": "Aktuelle Medikation:",
           "cols": ["Wirkstoff", "Stärke", "Mo-Mi-Ab-Na", "Status", "Quelle"],
           "status": {"active": "", "new": "neu", "paused": "pausiert", "stopped": "abgesetzt"},
           "stopped": "Abgesetzt / pausiert:", "clarify": "Zu klären (Widersprüche zwischen Dokumenten):",
           "warn": "Hinweise:", "labs": "Labor (auffällige Werte, neuester Wert):",
           "history": "Anamnese / Verlauf (nach Datum):", "contact": "Kontakt / Vorsorgevollmacht:",
           "unconfirmed": "ENTWURF: Medikation noch nicht ärztlich bestätigt.",
           "confirmed": "Medikation ärztlich geprüft{by}.",
           "footer": "Erstellt mit Get Well OCR am {ts}. Alle Angaben mit Quellseite [S. x] im Original prüfbar."},
    "en": {"intro": "The patient provided the following documents:",
           "no_date": "undated", "pages": "p.", "from": "from", "dated": "dated",
           "not_used": "Not used", "retake": "unreadable, please retake photo", "irrelevant": "not medical",
           "cave": "CAVE:", "dx": "Diagnoses:",
           "meds": "Current medication (reconciled from {n} documents, newest source: {src}):",
           "meds_plain": "Current medication:",
           "cols": ["Drug", "Strength", "Mo-No-Ev-Ni", "Status", "Source"],
           "status": {"active": "", "new": "new", "paused": "paused", "stopped": "stopped"},
           "stopped": "Stopped / paused:", "clarify": "To clarify (conflicts between documents):",
           "warn": "Warnings:", "labs": "Labs (abnormal, latest value):",
           "history": "Patient history (by date):", "contact": "Contact / power of attorney:",
           "unconfirmed": "DRAFT: medication not yet confirmed by a doctor.",
           "confirmed": "Medication reviewed by a doctor{by}.",
           "footer": "Created with Get Well OCR on {ts}. Every item can be checked on its source page [p. x]."},
}
TYPE_NAMES = {
    "de": {"discharge_letter": "Arztbrief / Entlassungsbrief", "medication_plan": "Medikationsplan",
           "lab_report": "Laborbefund", "referral": "Einweisung", "imaging_report": "Befundbericht (Bildgebung/Funktion)",
           "surgery_report": "OP-Bericht", "advance_directive": "Patientenverfügung / Vorsorgevollmacht",
           "nursing_transfer": "Pflegeüberleitungsbogen", "fax_note": "Fax / Kurzmitteilung",
           "specialist_letter": "Facharztbrief", "other_medical": "Sonstiges medizinisches Dokument",
           "unknown": "Dokument (Typ unklar)"},
    "en": {"discharge_letter": "discharge letter", "medication_plan": "medication plan",
           "lab_report": "lab report", "referral": "referral", "imaging_report": "imaging / function report",
           "surgery_report": "surgery report", "advance_directive": "advance directive / power of attorney",
           "nursing_transfer": "nursing transfer form", "fax_note": "fax / short note",
           "specialist_letter": "specialist letter", "other_medical": "other medical document",
           "unknown": "document (type unclear)"},
}


def _date(iso: str | None, L: dict) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y") if iso else L["no_date"]


def _src(pages, L) -> str:
    return f"[{L['pages']} " + ", ".join(str(p) for p in sorted(set(pages))) + "]" if pages else ""


def _page_range(pages) -> str:
    pages = sorted(pages)
    return f"{pages[0]}–{pages[-1]}" if len(pages) > 1 and pages[-1] - pages[0] == len(pages) - 1 \
        else ", ".join(map(str, pages))


def _table(rows: list[list[str]]) -> list[str]:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    fmt = lambda r: "  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip()
    return [fmt(rows[0]), "  ".join("-" * w for w in widths), *[fmt(r) for r in rows[1:]]]


def er_report(result: dict, meds: list[dict] | None = None, lang: str = "de",
              confirmed: bool = False, reviewer: str = "") -> str:
    """Plain-text ER handover. `meds` = doctor-reviewed rows (defaults to the machine list)."""
    L, T = LABELS[lang], TYPE_NAMES[lang]
    s, docs = result["summary"], result["documents"]
    doc_pages = {d["doc_id"]: d["pages"] for d in docs}
    meds = meds if meds is not None else s["medications"]
    out = []

    # --- documents -----------------------------------------------------------------------
    out.append(L["intro"])
    relevant = [d for d in docs if d["type"] != "irrelevant"]
    for d in sorted(relevant, key=lambda d: d["date"] or "0000", reverse=True):
        issuer = f", {d['issuer']}" if d.get("issuer") else ""
        out.append(f"- {T.get(d['type'], d['type'])} {L['dated'] if d['date'] else ''} {_date(d['date'], L)}"
                   f"{issuer} [{L['pages']} {_page_range(d['pages'])}]".replace("  ", " "))
    skipped = [f"{L['pages']} {p['page']} ({L['retake']})" for p in result["pages"] if p["status"] == "retake"]
    skipped += [f"{L['pages']} {_page_range(d['pages'])} ({L['irrelevant']})" for d in docs if d["type"] == "irrelevant"]
    if skipped:
        out.append(f"{L['not_used']}: " + "; ".join(skipped))

    # --- CAVE ------------------------------------------------------------------------------
    if s["cave"]:
        out += ["", L["cave"], *[f"- {c['text']} {_src(c['sources'], L)}" for c in s["cave"]]]

    # --- diagnoses -------------------------------------------------------------------------
    if s["diagnoses"]:
        out += ["", L["dx"]]
        out += [f"- {d['text']}{' (' + d['icd10'] + ')' if d['icd10'] else ''} {_src(d['sources'], L)}" for d in s["diagnoses"]]

    # --- medication ------------------------------------------------------------------------
    current = [m for m in meds if m["status"] in ("active", "new")]
    stopped = [m for m in meds if m["status"] in ("stopped", "paused")]
    src_pages = {p for m in meds for p in (m["sources"] if isinstance(m["sources"], list)
                                           else [int(x) for x in str(m["sources"]).split(",") if x.strip()])}
    src_docs = [d for d in relevant if set(d["pages"]) & src_pages]
    newest = max((d for d in src_docs if d["date"]), key=lambda d: d["date"], default=None)
    out.append("")
    out.append(L["meds"].format(n=len(src_docs), src=f"{T.get(newest['type'], '')} {_date(newest['date'], L)}")
               if newest else L["meds_plain"])

    def pages_of(m):
        return m["sources"] if isinstance(m["sources"], list) else \
            [int(x) for x in str(m["sources"]).split(",") if x.strip()]

    rows = [L["cols"]] + [[m["name"], m.get("strength") or "–", m.get("dosing") or "–",
                           L["status"].get(m["status"], m["status"]), _src(pages_of(m), L)] for m in current]
    out += _table(rows) if current else ["–"]
    if stopped:
        out += [L["stopped"]] + [f"- {m['name']} ({L['status'][m['status']]}) {_src(pages_of(m), L)}"
                                 for m in stopped]
    out.append(L["confirmed"].format(by=f": {reviewer}" if reviewer else "") if confirmed else L["unconfirmed"])

    # --- conflicts and warnings ------------------------------------------------------------
    if s["conflicts"]:
        out += ["", L["clarify"], *[f"- {c['text']} {_src(c['sources'], L)}" for c in s["conflicts"]]]
    if s["warnings"]:
        out += ["", L["warn"], *[f"- {w['text']} {_src(w['sources'], L)}" for w in s["warnings"]]]

    # --- labs ------------------------------------------------------------------------------
    flagged = [l for l in s["labs"] if l["flag"]]
    if flagged:
        out += ["", L["labs"]]
        out += [" ".join(x for x in ["-", l["name"], l["value"], l["unit"], l["flag"]] if x) +
                (f" (Verlauf {l['trend']})" if l["trend"] and lang == "de" else
                 f" (trend {l['trend']})" if l["trend"] else "") + f" {_src(l['sources'], L)}" for l in flagged]

    # --- history: per document, oldest first -----------------------------------------------
    hist = []
    for d in sorted(relevant, key=lambda d: d["date"] or "9999"):
        pages = set(doc_pages[d["doc_id"]])
        facts = [f"{x['text']}" for x in s["diagnoses"] if set(x["sources"]) & pages]
        facts += [x["text"] for x in s.get("findings", []) if set(x["sources"]) & pages]
        facts += [x["text"] for x in s["cave"] if set(x["sources"]) & pages and "Antikoagulation" not in x["text"]]
        facts = list(dict.fromkeys(facts))[:4]
        if facts:
            hist.append(f"- {_date(d['date'], L)} {T.get(d['type'], d['type'])}"
                        f"{' (' + d['issuer'] + ')' if d.get('issuer') else ''}: " + "; ".join(facts) +
                        f" {_src(d['pages'], L)}")
    if hist:
        out += ["", L["history"], *hist]

    # --- contact ---------------------------------------------------------------------------
    if s["contacts"]:
        out += ["", L["contact"], *[f"- {c['text']} {_src(c['sources'], L)}" for c in s["contacts"]]]

    out += ["", L["footer"].format(ts=datetime.now().strftime("%d.%m.%Y %H:%M"))]
    return "\n".join(out)
