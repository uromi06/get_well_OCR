"""Patient history as short prose, written by Mistral Large 3 from the CONFIRMED facts only.

Safety design
  1. The model never sees the page images or OCR text, only the structured facts that are
     already in the ER overview (diagnoses, CAVE, medication confirmed by the doctor, findings,
     document timeline). It can phrase them, it cannot discover anything new.
  2. Temperature 0, explicit instruction: no new facts, no recommendations, no speculation.
  3. Check after generation: every number and date in the text must appear in the facts.
     Anything else is listed as "nicht belegt" (not supported) and shown to the doctor.
  4. The text is labelled as AI-written and must be accepted by the doctor before export.
"""
from __future__ import annotations

import json
import re

from .mistral import chat

SYSTEM = (
    "Du bist ärztliche Schreibassistenz in einer Notaufnahme. Du formulierst aus einer Liste geprüfter "
    "Fakten eine kurze Anamnese auf Deutsch. Regeln: Verwende ausschließlich die gegebenen Fakten. "
    "Erfinde nichts, ergänze keine Werte, Daten, Diagnosen oder Medikamente. Keine Empfehlungen, keine "
    "Bewertung, keine Spekulation. Übernimm Zahlen, Dosierungen und Daten exakt. Schreibe 4 bis 7 Sätze "
    "Fließtext im Stil eines Arztbriefs, chronologisch, ohne Aufzählungszeichen und ohne Überschrift."
)


def history_facts(result: dict, meds: list[dict] | None = None) -> dict:
    s = result["summary"]
    meds = meds if meds is not None else s["medications"]
    patient = dict(result.get("patient") or {})
    if patient.get("birth"):
        from datetime import datetime
        try:
            bd, now = datetime.strptime(patient["birth"], "%d.%m.%Y"), datetime.now()
            patient["alter"] = now.year - bd.year - ((now.month, now.day) < (bd.month, bd.day))
        except ValueError:
            pass
    return {
        "patient": patient,
        "diagnosen": [{"text": d["text"], "icd10": d.get("icd10"), "details": d.get("details", [])}
                      for d in s["diagnoses"]],
        "cave": [c["text"] for c in s["cave"]],
        "befunde": [f["text"] for f in s.get("findings", [])],
        "medikation": [{k: m.get(k) for k in ("name", "strength", "dosing", "status")} for m in meds],
        "dokumente": [{"datum": t["date"], "dokument": t["text"]} for t in s["timeline"]],
        "labor_auffaellig": [{"name": l["name"], "wert": l["value"], "einheit": l["unit"], "verlauf": l["trend"]}
                             for l in s["labs"] if l["flag"]],
    }


NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _norm_numbers(text: str) -> set[str]:
    out = set()
    for n in NUMBER.findall(text):
        out.add(n.replace(",", "."))
        out.add(n.lstrip("0") or "0")
    return out


def unsupported_numbers(text: str, facts: dict) -> list[str]:
    """Numbers/dates in the generated text that do not occur anywhere in the facts."""
    blob = json.dumps(facts, ensure_ascii=False)
    # facts store ISO dates (2026-10-14); the text will say 14.10.2026 -> accept both forms
    blob += " " + " ".join(f"{d[8:10]}.{d[5:7]}.{d[:4]}" for d in re.findall(r"\d{4}-\d{2}-\d{2}", blob))
    known = _norm_numbers(blob)
    missing = []
    for n in NUMBER.findall(text):
        parts = re.split(r"[.,]", n)
        if n.replace(",", ".") in known or (n.lstrip("0") or "0") in known:
            continue
        if len(parts) == 3 and all(p in known or p.lstrip("0") in known for p in parts):   # a date
            continue
        missing.append(n)
    return sorted(set(missing))


def write_history(result: dict, meds: list[dict] | None = None) -> dict:
    """Returns {'text', 'unsupported': [...], 'facts'}. Raises MistralError if the endpoint fails."""
    facts = history_facts(result, meds)
    text = chat([{"role": "system", "content": SYSTEM},
                 {"role": "user", "content": "Fakten (JSON):\n" + json.dumps(facts, ensure_ascii=False, indent=1)}])
    text = re.sub(r"^\s*#+.*\n", "", text).strip()          # drop a heading if the model adds one
    return {"text": text, "unsupported": unsupported_numbers(text, facts), "facts": facts}
