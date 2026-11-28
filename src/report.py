"""The ER handover text: the one output the doctor copies into the hospital system.

Format agreed with the ER doctor (plain text, no formatting needed in the receiving system):

    The patient provided the following documents:   type, date, issuer, pages
    CAVE                                              (added: allergies, anticoagulation, implants, directive)
    Diagnoses
    Current medication                                table, reconciled across ALL documents
    To clarify                                        conflicts between documents
    Labs (abnormal)
    Contact / power of attorney

Every fact keeps its source page [S. x], so the doctor can check it in the app.
Labels are translated (de/en); the facts stay in the language of the documents.
No patient history section: the ER does not need the full history, relevant past conditions are
listed under Diagnoses (implants, directives under CAVE).
"""
from __future__ import annotations

import re
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
           "warn": "Hinweise:", "safety": "Gefährliche Dosis/Kombination (KI-Prüfung, ärztlich bewerten):",
           "labs": "Labor (auffällige Werte, neuester Wert):", "contact": "Kontakt / Vorsorgevollmacht:",
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
           "warn": "Warnings:", "safety": "Dangerous dose/combination (AI check, for clinical review):",
           "labs": "Labs (abnormal, latest value):", "contact": "Contact / power of attorney:",
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


def safety_label(a: dict) -> str:
    """'Ibuprofen + Apixaban – Blutungsgefahr: NSAR plus orales Antikoagulans. Ibuprofen absetzen'"""
    danger = f" – {a['danger']}" if a.get("danger") else ""     # older results have no danger field
    return (f"{' + '.join(a['drugs'])}{danger}: {a['issue']}"
            + (f". {a['action']}" if a.get("action") else ""))


def _date(iso: str | None, L: dict) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y") if iso else L["no_date"]


SHOW_SOURCES = False     # set per call; module default for the handover: no page references


def _src(pages, L) -> str:
    if not SHOW_SOURCES or not pages:
        return ""
    return f"[{L['pages']} " + ", ".join(str(p) for p in sorted(set(pages))) + "]"


def _clean(text: str) -> str:
    """Remove page references inside generated texts, e.g. '(S. 2, 2026-09-18)' or 'laut S. 3'."""
    if SHOW_SOURCES:
        return text
    text = re.sub(r"\s*\((?:S\.|p\.)\s*\d+[^)]*\)", "", text)
    text = re.sub(r"\blaut S\.\s*\d+", "laut Dokument", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _page_range(pages) -> str:
    pages = sorted(pages)
    return f"{pages[0]}–{pages[-1]}" if len(pages) > 1 and pages[-1] - pages[0] == len(pages) - 1 \
        else ", ".join(map(str, pages))


def _table(rows: list[list[str]]) -> list[str]:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    fmt = lambda r: "  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip()
    return [fmt(rows[0]), "  ".join("-" * w for w in widths), *[fmt(r) for r in rows[1:]]]


def er_report(result: dict, meds: list[dict] | None = None, lang: str = "de",
              confirmed: bool = False, reviewer: str = "", resolved: list[int] | None = None,
              show_sources: bool = False) -> str:
    """Plain-text ER handover.

    meds         doctor-reviewed rows (defaults to the machine list)
    resolved     indices of conflicts the doctor marked as clarified: left out of the text
    show_sources add [S. x] page references (off by default: the app shows them, the text stays clean)
    """
    global SHOW_SOURCES
    SHOW_SOURCES = show_sources
    resolved = set(resolved or [])
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
        pages = f" [{L['pages']} {_page_range(d['pages'])}]" if show_sources else ""
        out.append(f"- {T.get(d['type'], d['type'])} {L['dated'] if d['date'] else ''} {_date(d['date'], L)}"
                   f"{issuer}{pages}".replace("  ", " "))
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
        for d in s["diagnoses"]:
            out.append(f"- {d['text']}{' (' + d['icd10'] + ')' if d['icd10'] else ''} {_src(d['sources'], L)}".rstrip())
            out += [f"    - {det}" for det in d.get("details", [])]

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
    for f in s.get("findings", []):
        if f["text"].startswith("Korrektur"):
            out.append(f"{f['text']} {_src(f['sources'], L)}".rstrip())
    out.append(L["confirmed"].format(by=f": {reviewer}" if reviewer else "") if confirmed else L["unconfirmed"])

    # --- conflicts and warnings ------------------------------------------------------------
    open_conflicts = [c for i, c in enumerate(s["conflicts"]) if i not in resolved]
    if open_conflicts:
        out += ["", L["clarify"], *[f"- {_clean(c['text'])} {_src(c['sources'], L)}".rstrip() for c in open_conflicts]]
    if s["warnings"]:
        out += ["", L["warn"], *[f"- {_clean(w['text'])} {_src(w['sources'], L)}".rstrip() for w in s["warnings"]]]
    if s.get("safety"):
        out += ["", L["safety"], *[
            f"- {safety_label(a)} {_src(a['sources'], L)}".rstrip() for a in s["safety"]]]

    # --- labs ------------------------------------------------------------------------------
    flagged = [l for l in s["labs"] if l["flag"]]
    if flagged:
        out += ["", L["labs"]]
        out += [" ".join(x for x in ["-", l["name"], l["value"], l["unit"], l["flag"]] if x) +
                (f" (Verlauf {l['trend']})" if l["trend"] and lang == "de" else
                 f" (trend {l['trend']})" if l["trend"] else "") + f" {_src(l['sources'], L)}" for l in flagged]

    # --- contact ---------------------------------------------------------------------------
    if s["contacts"]:
        out += ["", L["contact"], *[f"- {c['text']} {_src(c['sources'], L)}" for c in s["contacts"]]]

    footer = L["footer"] if show_sources else L["footer"].split(".")[0] + "."
    out += ["", footer.format(ts=datetime.now().strftime("%d.%m.%Y %H:%M"))]
    return "\n".join(line.rstrip() for line in out)
