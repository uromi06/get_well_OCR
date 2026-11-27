"""Multi-page case pipeline: many photos of one patient -> one ER overview.

  1. read_page      cleanup + OCR + quality check (blurry -> "retake"), cached
  2. classify       document type per page (rules on German keywords)
  3. group          pages -> documents ("Seite 2 von 3" continues the previous one)
  4. extract        medications, diagnoses, labs, CAVE facts, contacts per page
  5. merge          current medication, conflicts, latest labs, timeline
  6. summarize      ER overview in the app's JSON shape, every fact with its source page

Rule-based extraction is the default and the fallback for optional Mistral extraction.
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import cv2
from rapidfuzz import fuzz, process

from . import config
from .drugs import DRUGS
from .extract import read_text
from .parse import DOSING, ICD10, ICD10_OCR_FIX, STRENGTH, merge_rows
from .preprocess import load_image, preprocess, to_gray

SHARPNESS_MIN = 150          # below: ask for a new photo (blurry page ~ 30, sharp pages ~ 700+)
CONFIDENCE_MIN = 0.60        # mean OCR confidence below this: text unreadable (fax, heavy noise) -> retake
                             # normal pages ~0.9; without this check unreadable pages fail SILENTLY

# ------------------------------------------------------------------ 1. read

def sharpness(gray) -> float:
    small = cv2.resize(gray, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(small, cv2.CV_64F).var())


def read_page(path: Path, page: int, engine: str, cache_dir: Path, fresh=False) -> dict:
    cache = cache_dir / f"{path.stem}_{engine}.json"
    if cache.exists() and not fresh:
        return json.loads(cache.read_text(encoding="utf-8"))
    img = load_image(path)
    sharp = sharpness(to_gray(img))
    clean, steps = preprocess(img)
    lines = merge_rows(read_text(clean, engine))
    confs = [l.confidence for l in lines if l.confidence is not None]
    result = {
        "page": page, "file": path.name, "sharpness": round(sharp),
        "mean_confidence": round(sum(confs) / len(confs), 2) if confs else None,
        "steps": steps,
        "lines": [{"text": l.text, "conf": l.confidence,
                   "bbox": l.bbox.model_dump() if l.bbox else None} for l in lines],
    }
    cache.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def page_quality(p: dict) -> str:
    """Two gates: sharp enough to read, and the reader is confident about what it read."""
    if p["sharpness"] < SHARPNESS_MIN:
        return "too_blurry"
    if p["mean_confidence"] is None or p["mean_confidence"] < CONFIDENCE_MIN:
        return "unreadable"
    return "ok"


def page_text(p: dict) -> str:
    return "\n".join(l["text"] for l in p["lines"])

# ------------------------------------------------------------------ 2. classify

TYPE_RULES = {   # type: [(keyword, weight)]  — keywords in lower case
    "medication_plan":   [("medikationsplan", 5), ("handelsname", 2), ("einheit", 1)],
    "lab_report":        [("laborbefund", 5), ("referenzbereich", 3), ("probeneingang", 2)],
    "referral":          [("einweisung", 5), ("verordnung von krankenhausbehandlung", 5), ("fragestellung", 1)],
    "imaging_report":    [("befundbericht", 4), ("echokardiographie", 5), ("ct thorax", 4), ("röntgen", 3), ("lvef", 1)],
    "surgery_report":    [("operationsbericht", 5), ("op-datum", 3), ("operateur", 2), ("implantate", 1)],
    "advance_directive": [("patientenverfügung und", 6), ("vorsorgevollmacht (auszug)", 6), ("bevollmächtige", 2),
                          ("wiederbelebung", 1)],
    "nursing_transfer":  [("pflegeüberleitung", 6), ("pflegegrad", 3), ("bezugsperson", 2)],
    "fax_note":          [("telefax", 5), ("kurzmitteilung", 4)],
    "irrelevant":        [("krankenkasse", 3), ("gesundheitskarte", 4), ("bonusprogramm", 4), ("zuzahlung", 2)],
    "discharge_letter":  [("entlassungsbrief", 6), ("arztbrief", 5), ("aufenthalt", 2), ("medikation bei entlassung", 3),
                          ("verlauf", 1)],
    "specialist_letter": [("diabetolog", 4), ("bericht", 1), ("therapieempfehlung", 2)],
    "other_medical":     [("verlaufsbogen", 5), ("dmp", 2)],
}
TYPE_TITLES = {"discharge_letter": "Arztbrief / Entlassungsbrief", "medication_plan": "Medikationsplan",
               "lab_report": "Laborbefund", "referral": "Einweisung", "imaging_report": "Bildgebung / Funktionsbefund",
               "surgery_report": "OP-Bericht", "advance_directive": "Patientenverfügung / Vollmacht",
               "nursing_transfer": "Pflegeüberleitung", "fax_note": "Fax / Kurzmitteilung",
               "irrelevant": "Nicht medizinisch", "specialist_letter": "Facharztbericht",
               "other_medical": "Sonstiges medizinisches Dokument", "unknown": "Unklar"}
CONTINUATION = re.compile(r"Seite\s*([2-9])\s*von\s*(\d)", re.IGNORECASE)


def classify(text: str) -> tuple[str, float]:
    lines = text.lower().splitlines()
    head, body = "\n".join(lines[:10]), "\n".join(lines)
    scores = {}
    for doc_type, rules in TYPE_RULES.items():
        scores[doc_type] = sum(w * (3 if k in head else 1) for k, w in rules if k in body)
    best = max(scores, key=scores.get)
    total = sum(scores.values())
    return (best, round(scores[best] / total, 2)) if scores[best] > 0 else ("unknown", 0.0)

# ------------------------------------------------------------------ 3. group + dates

DATE = re.compile(r"(?<!\d)(\d{2})\.(\d{2})\.(\d{4})(?!\d)")


def find_date(text: str) -> str | None:
    """First date on the page that is not a birth date ("geb. 14.03.1948")."""
    for m in DATE.finditer(text):
        before = text[max(0, m.start() - 12):m.start()].lower()
        if "geb" in before:
            continue
        try:
            d = datetime(int(m[3]), int(m[2]), int(m[1]))
        except ValueError:
            continue
        if 1990 <= d.year and d <= datetime.now():   # OCR misreads like 2926 or future dates are skipped
            return d.strftime("%Y-%m-%d")
    return None


ISSUER_WORDS = re.compile(r"klinik|praxis|mvz|labor|pflegedienst|krankenhaus|zentrum|institut|krankenkasse|apotheke",
                          re.IGNORECASE)
DOCTOR = re.compile(r"(?:Prof\.\s*)?Dr\.\s*med\.\s*[A-ZÄÖÜ]\.\s*[A-ZÄÖÜ][\wäöüß-]+")


def find_issuer(text: str) -> str | None:
    """Who wrote the document: institution in the letterhead, else the first doctor named."""
    for line in text.splitlines()[:6]:
        if ISSUER_WORDS.search(line) and len(line) >= 8 and not re.match(r"^\W*\d", line):
            line = re.sub(r"\s*[({]fiktiv[)}]?\s*", " ", line, flags=re.IGNORECASE)
            line = re.sub(r"[-–—·]\s*\d{2}\.\d{2}\.\d{4}.*$", "", line)          # trailing date
            return line.strip(" -—·")
    m = DOCTOR.search(text)
    return m.group(0) if m else None


RULES_CONFIDENT = 0.5      # rules share of the keyword score above which rules are trusted


def classify_page(text: str, mode: str | None = None) -> dict:
    """Combine keyword rules and the embedding model.

    rules : keywords only (explainable baseline)
    model : embedding model only
    hybrid: rules when they are confident, else the model; if both have an opinion and
            disagree, the document is flagged 'check' for the doctor.
    """
    mode = mode or config.CLASSIFIER
    r_type, r_conf = classify(text)
    out = {"rules": {"type": r_type, "confidence": r_conf}, "model": None, "check": False}
    if mode == "rules":
        out.update(type=r_type, confidence=r_conf, used="rules")
        return out
    from .doc_classifier import classify_embedding
    m = classify_embedding(text)
    out["model"] = m
    if mode == "model":
        out.update(type=m["type"], confidence=m["similarity"], used="model")
    elif r_type != "unknown" and r_conf >= RULES_CONFIDENT:
        out.update(type=r_type, confidence=r_conf, used="rules")
    else:
        out.update(type=m["type"], confidence=m["similarity"], used="model")
    out["check"] = r_type != "unknown" and r_type != m["type"]
    return out


def group_documents(pages: list[dict]) -> list[dict]:
    docs = []
    for p in pages:
        if p["quality"] != "ok":
            continue
        text = page_text(p)
        cont = CONTINUATION.search(text)
        if cont and docs and docs[-1]["pages"][-1] == p["page"] - 1:
            docs[-1]["pages"].append(p["page"])
            p["doc_type"], p["doc_id"] = docs[-1]["type"], docs[-1]["doc_id"]
            continue
        c = classify_page(text)
        doc_type, conf = c["type"], c["confidence"]
        doc = {"doc_id": f"D{len(docs) + 1:02d}", "type": doc_type, "title": TYPE_TITLES.get(doc_type, doc_type),
               "type_confidence": conf, "classified_by": c["used"], "type_check": c["check"],
               "rules_type": c["rules"]["type"], "model_type": c["model"]["type"] if c["model"] else None, "date": find_date(text), "issuer": find_issuer(text), "pages": [p["page"]]}
        docs.append(doc)
        p["doc_type"], p["doc_id"] = doc_type, doc["doc_id"]
    return docs

# ------------------------------------------------------------------ 4. extract

from .drugs import ALIASES
DRUG_LOWER = {d.lower(): d for d in DRUGS}
DRUG_LOWER.update({a.lower(): inn for a, inn in ALIASES.items()})
SINGLE_WORD = [k for k in DRUG_LOWER if " " not in k and "/" not in k]
MULTI_WORD = re.compile("|".join(sorted((re.escape(k) for k in DRUG_LOWER if " " in k or "/" in k),
                                        key=len, reverse=True)), re.IGNORECASE)
# sections in letters: medication and diagnoses are listed under these headings
MED_HEADINGS = re.compile(r"^\W*(Therapie|Medikation\w*|Aktuelle Medikation|Entlassungsmedikation|"
                          r"Medikation bei Entlassung|Dauermedikation|Medikamente)\b\s*:?\s*$", re.IGNORECASE)
DX_HEADINGS = re.compile(r"^\W*((Haupt|Neben|Dauer)?[Dd]iagnosen?|Vorerkrankungen|Diagnoseliste)\b\s*:?\s*$")
ANY_HEADING = re.compile(r"^\W*(Anamnese|Befund\w*|Verlauf|Procedere|Empfehlung\w*|Beurteilung|Epikrise|"
                         r"Therapie|Medikation\w*|Diagnosen?|Allergien|Labor\w*|Mit freundlichen|Sozialanamnese|"
                         r"Körperlicher Untersuchungsbefund|Aufnahmebefund|Histologie|Pathologie|Operation|Status|Untersuchung)\b",
                         re.IGNORECASE)
BULLET = re.compile(r"^\s*(\d{1,2}[.)]|[*•·°»\-–—>])\s*")
NUMBERED = re.compile(r"^\s*\d{1,2}[.)]\s+")
ALLERGY_HEADING = re.compile(r"^\W*(Allergien|Unverträglichkeiten|Allergien\s*/\s*Unverträglichkeiten)\s*:?\s*$",
                             re.IGNORECASE)
DASH_BETWEEN_DIGITS = re.compile(r"(?<=[\d½])\s*[–—]\s*(?=[\d½])")
CORRECTION = re.compile(r"irrtümlich|fälschlich|Korrektur\b|korrigiert", re.IGNORECASE)
CORRECT_VALUE = re.compile(r"\b(?:korrekte[nrs]?|richtige[nrs]?|richtig ist|neue Dosis)\b[^.]*?(\d+(?:[.,]\d+)?)\s*"
                           r"(mg|µg|ug|g|IE)\b\s*((?:\d|½)\s*-\s*(?:\d|½)\s*-\s*(?:\d|½)(?:\s*-\s*(?:\d|½))?)?",
                           re.IGNORECASE)   # "Korrektur" itself is NOT the corrected value
AS_NEEDED_RX = re.compile(r"\bb\.\s?B\.|\bbei Bedarf\b|\bbei (schwer\w*|starke\w*)?\s*(Hypo\w*|Schmerz\w*|Atemnot|"
                          r"Übelkeit|Unruhe|Fieber|Schlaflosigkeit)", re.IGNORECASE)
ANTICOAGULANTS = {"Apixaban", "Rivaroxaban", "Edoxaban", "Dabigatran", "Phenprocoumon"}
STATUS_WORDS = {"stopped": ["abgesetzt", "beendet", "gestoppt", "abgeseizt"], "paused": ["pausiert"],
                "new": ["angesetzt", "begonnen", "neu"]}
SWITCH = re.compile(r"(?:Umstellung|umgestellt)\s+von\s+(\w+)\s+auf\s+(\w+)", re.IGNORECASE)
UNITS = {"mmol/l", "mg/dl", "ml/min", "ml/min/1,73m2", "pg/ml", "g/dl", "%", "/nl", "mg/l", "µmol/l", "ng/ml", "mu/l"}
LVEF = re.compile(r"LVEF[^\d%]{0,30}?(\d{2})\s*%")
LAB_NAMES = ["Natrium", "Kalium", "Kreatinin", "eGFR", "Harnstoff", "Hämoglobin", "Leukozyten", "CRP",
             "NT-proBNP", "HbA1c", "INR", "TSH"]
LAB_LINE = re.compile(r"^\W*(" + "|".join(re.escape(n) for n in LAB_NAMES) + r")\b\D*?(\d+(?:[.,]\d+)?)\s*(\S+)?(.*)$")
WORD = re.compile(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\-]+")


def find_drugs(line: str) -> list[tuple[str, int]]:
    """Known drug names in a line (OCR-tolerant), with their character position."""
    found, taken = [], []
    for m in MULTI_WORD.finditer(line):                # "Insulin lispro", "Sacubitril/Valsartan"
        found.append((DRUG_LOWER[m.group(0).lower()], m.start()))
        taken.append((m.start(), m.end()))
    for m in WORD.finditer(line):
        if any(a <= m.start() < b for a, b in taken):
            continue
        tok = m.group(0).lower().strip("-")
        if len(tok) < 3:
            continue
        if tok in DRUG_LOWER:
            found.append((DRUG_LOWER[tok], m.start()))
            continue
        if len(tok) >= 6:
            best = process.extractOne(tok, SINGLE_WORD, scorer=fuzz.ratio, score_cutoff=85)
            if best:
                found.append((DRUG_LOWER[best[0]], m.start()))
    out, seen = [], set()
    for name, pos in sorted(found, key=lambda x: x[1]):   # "Enoxaparin (Clexane®)" -> one mention
        if name not in seen:
            out.append((name, pos))
            seen.add(name)
    return out


def line_status(line: str) -> str | None:
    """Status word in this piece of text. Picks the closest match, so 'angesetzt' (new)
    is not confused with 'abgesetzt' (stopped). Tolerates OCR typos like 'abgeseizt'."""
    best, best_score = None, 0
    for t in (t.lower() for t in WORD.findall(line)):
        for status, words in STATUS_WORDS.items():
            for w in words:
                score = 100 if t == w else (fuzz.ratio(t, w) if len(w) > 4 else 0)
                if score > best_score:
                    best, best_score = status, score
    return best if best_score >= 85 else None


def fix_icd(text: str) -> str:
    return ICD10_OCR_FIX.sub(lambda m: f"(I{m.group(2)})", text)


def extract_page(p: dict) -> dict:
    facts = {"meds": [], "diagnoses": [], "labs": [], "cave": [], "contacts": [], "negatives": [], "findings": []}
    doc_type, page = p.get("doc_type"), p["page"]
    previous = ""
    section = None                                   # "meds" | "dx" | "allergy" | None, from the headings
    numbered_dx = False
    allergy_items = 0
    lines = p["lines"]

    # corrections ("Dosis irrtümlich mit 8 mg angegeben. Die korrekte Dosis beträgt 16 mg 1-0-0"):
    # the corrected value is authoritative, the wrong one must not become a medication or a conflict
    consumed = set()
    for i, l in enumerate(lines):
        if not CORRECTION.search(l["text"]):
            continue
        block_idx = [i] if CORRECT_VALUE.search(l["text"]) else [i] + ([i + 1] if i + 1 < len(lines) else [])
        block = " ".join(lines[j]["text"] for j in block_idx)
        drugs_in_block = find_drugs(block)
        right = CORRECT_VALUE.search(block)
        if drugs_in_block and right:
            drug = drugs_in_block[0][0]
            wrong = re.search(r"irrtümlich[^.]*?(\d+(?:[.,]\d+)?\s*(?:mg|µg|g|IE))", block, re.IGNORECASE)
            facts["meds"].append({"name": drug, "strength": f"{right.group(1)} {right.group(2)}",
                                  "dosing": re.sub(r"\s+", "", right.group(3)) if right.group(3) else None,
                                  "status": None, "confidence": l["conf"], "correction": True,
                                  "page": page, "doc_id": p.get("doc_id"), "source_text": block})
            right_dosing = re.sub(r"\s+", "", right.group(3)) if right.group(3) else ""
            note = f"{drug}: korrekt {right.group(1)} {right.group(2)} {right_dosing}".strip()
            note += f" (zuvor irrtümlich {wrong.group(1)} angegeben)" if wrong else " (laut Korrektur im Dokument)"
            facts["findings"].append({"fact": "Korrektur: " + note, "page": page, "doc_id": p.get("doc_id"),
                                      "source_text": block})
            consumed.update(block_idx)

    for idx, l in enumerate(lines):
        text, conf = l["text"], l["conf"]
        low = text.lower()
        src = {"page": page, "doc_id": p.get("doc_id"), "source_text": text}
        text = DASH_BETWEEN_DIGITS.sub("-", text)          # "0 – 0 – 1 – 0" -> "0-0-1-0"
        if MED_HEADINGS.match(text):
            section = "meds"
            continue
        if DX_HEADINGS.match(text):
            section, numbered_dx = "dx", False
            continue
        if ALLERGY_HEADING.match(text):
            section, allergy_items = "allergy", 0
            continue
        if ANY_HEADING.match(text) and not BULLET.match(text):
            section = None

        # allergies listed under an "Allergien" heading: a short list. A non-bullet line after the
        # first item (e.g. the next heading "Histologie (...)") ends the section.
        if section == "allergy" and text.strip():
            if allergy_items and not BULLET.match(text):
                section = None
            else:
                allergy_items += 1
        if section == "allergy" and text.strip():
            item = BULLET.sub("", text).strip(" -·:;,|")
            if re.search(r"keine|nicht bekannt|k\.\s?A\.", item, re.IGNORECASE):
                facts["negatives"].append({"category": "allergy", "fact": "Allergien: keine bekannt", **src})
            elif re.search(r"[A-Za-zÄÖÜäöü]{4,}", item) and len(item) <= 80:
                facts["cave"].append({"category": "allergy", "fact": f"Allergie: {item}", **src})
            continue

        # medications (table rows and prose); lines of a correction note were handled above
        drugs = find_drugs(text) if idx not in consumed else []
        switched = {m.group(1).lower() for m in SWITCH.finditer(text)}
        for i, (drug, pos) in enumerate(drugs):
            end = drugs[i + 1][1] if i + 1 < len(drugs) else len(text)
            segment = text[pos:end]
            segment = re.sub(r"^(\S+)\s*\([^)]{1,30}\)", r"\1", segment)   # "Enoxaparin (Clexane®) 40 mg"
            window = 70 if "|" in segment else 35     # table rows: dose sits a few columns further right
            near = re.sub(r"(\d)\s*pg\b", r"\1 µg", segment[:window])   # OCR reads µg as pg
            s, d = STRENGTH.search(near), DOSING.search(near)
            if s and s.group(2).lower() == "ml":     # "eGFR unter 30 ml/min" is not a dose
                s = None
            status = "stopped" if drug.lower() in switched else line_status(segment)
            dosing = re.sub(r"\s+", "", d.group(0)) if d else ("bei Bedarf" if AS_NEEDED_RX.search(segment) else
                                                               "Insulinpumpe" if "pumpe" in segment.lower() else None)
            facts["meds"].append({"name": drug, "strength": f"{s.group(1)} {s.group(2)}" if s else None,
                                  "dosing": dosing, "status": status, "confidence": conf, **src})

        # unknown drug in a medication section: keep it, flagged, instead of losing it silently
        if section == "meds" and not drugs and BULLET.match(text):
            item = BULLET.sub("", text)
            s, d = STRENGTH.search(item), DOSING.search(item)
            name = re.split(r"\s+\d|:|\(|\s(?:über|per|bei|nach|zur)\s", item)[0].strip(" ,;")
            if (s or d or AS_NEEDED_RX.search(item)) and re.search(r"[A-Za-zÄÖÜäöü]{3,}", name) and len(name) <= 40:
                facts["meds"].append({"name": name, "strength": f"{s.group(1)} {s.group(2)}" if s else None,
                                      "dosing": re.sub(r"\s+", "", d.group(0)) if d else
                                      ("bei Bedarf" if AS_NEEDED_RX.search(item) else None),
                                      "status": line_status(item), "confidence": conf, "unknown": True, **src})

        # diagnoses listed under a "Diagnosen" heading, without an ICD code
        #   "1. Main diagnosis"            -> new diagnosis
        #   line without bullet            -> continuation of the line above (wrapped text)
        #   "- Z.n. ..." under a numbered  -> detail of that diagnosis
        if section == "dx" and doc_type != "lab_report" and not ICD10.search(fix_icd(text)):
            sec_dx = [d for d in facts["diagnoses"] if d.get("from_section")]
            label = BULLET.sub("", text).strip(" -–—·:;,|")
            if NUMBERED.match(text):
                numbered_dx = True
                if len(label) >= 4:
                    facts["diagnoses"].append({"text": label, "icd10": None, "details": [], "from_section": True, **src})
            elif BULLET.match(text):
                if numbered_dx and sec_dx:
                    sec_dx[-1]["details"].append(label)
                elif len(label) >= 4:
                    facts["diagnoses"].append({"text": label, "icd10": None, "details": [], "from_section": True, **src})
            elif sec_dx and label:
                target = sec_dx[-1]
                if target["details"]:
                    target["details"][-1] += " " + label
                else:
                    target["text"] += " " + label

        # diagnoses: every ICD code on the line, with the words in front of it
        fixed, prev = fix_icd(text), 0
        for m in ICD10.finditer(fixed):
            label = fixed[prev:m.start()].strip(" -·:;,()|")
            if len(label) < 4 and prev == 0:         # code wrapped onto its own line
                label = previous.strip(" -·:;,()|")
            label = re.sub(r"^(\d+\.\s*)?((Haupt|Neben)?[Dd]iagnosen?[^:]*:\s*)?", "", label)
            label = re.sub(r"\(\s*[1l|]\d{2}(\.\d{1,2})?\s*\)", "", label).strip(" -·:;,()|")
            prev = m.end()
            if len(label) >= 4 and doc_type != "lab_report":
                facts["diagnoses"].append({"text": label, "icd10": m.group(1), **src})
        previous = text
        lv = LVEF.search(text)
        if lv:
            facts["findings"].append({"fact": f"LVEF {lv.group(1)} %", **src})

        # labs (lab report tables only)
        if doc_type == "lab_report":
            m = LAB_LINE.match(text)
            if m:
                flag = re.search(r"\b([HL])\s*$", text)
                unit = (m.group(3) or "").strip("|")
                facts["labs"].append({"name": m.group(1), "value": m.group(2),
                                      "unit": unit if unit.lower() in UNITS else "",
                                      "flag": flag.group(1) if flag else "", **src})

        # CAVE facts
        if "allergi" in low:
            if "keine" in low:
                facts["negatives"].append({"category": "allergy", "fact": "Allergien: keine bekannt", **src})
            else:
                sub = re.search(r"([A-Za-zÄÖÜäöü]+)[-\s]?Allergi", text)
                if sub and len(sub.group(1)) >= 5 and sub.group(1)[0].isupper():
                    facts["cave"].append({"category": "allergy", "fact": f"Allergie: {sub.group(1)}", **src})
        if "schrittmacher" in low:
            facts["cave"].append({"category": "implant", "fact": "Herzschrittmacher in situ", **src})
        if re.search(r"\btep\b|endoprothese", low):
            facts["cave"].append({"category": "implant", "fact": "Gelenkendoprothese (TEP)", **src})
        if doc_type == "advance_directive" and re.match(r"^\W*[\[(]?\s*[xX]", text):
            if "reanimation" in low or "wiederbelebung" in low:
                facts["cave"].append({"category": "directive", "fact": "Patientenverfügung: keine Reanimation", **src})
            if "intubation" in low or "beatmung" in low and "nicht-invasiv" not in low:
                facts["cave"].append({"category": "directive", "fact": "Patientenverfügung: keine Intubation/invasive Beatmung", **src})
        if re.search(r"tochter|sohn|ehemann|ehefrau|betreuer|bevollmächtig", low) and \
                doc_type in ("advance_directive", "nursing_transfer"):
            phone = re.search(r"Tel\.?\s*([\d\s/-]{6,})", text)
            who = re.search(r"(Tochter|Sohn|Ehemann|Ehefrau|Betreuer\w*)\s+([A-ZÄÖÜ][\w]+\s+[A-ZÄÖÜ][\w]+)?", text)
            label = " ".join(x for x in [who.group(1) if who else "Bezugsperson",
                                          who.group(2) if who and who.group(2) else "",
                                          f"Tel. {phone.group(1).strip()}" if phone else ""] if x)
            facts["contacts"].append({"fact": label, **src})
    return facts

# ------------------------------------------------------------------ 5. merge

def _norm(s):
    return (s or "").replace(" ", "").replace(",", ".").lower()


def merge(pages: list[dict], docs: list[dict]) -> dict:
    doc_by_id = {d["doc_id"]: d for d in docs}
    relevant = [d for d in docs if d["type"] != "irrelevant"]
    dates = sorted(d["date"] for d in relevant if d["date"])
    newest = dates[-1] if dates else None
    cutoff = f"{int(newest[:4]) - 1}{newest[4:]}" if newest else None   # facts older than 1 year = history
    all_facts = {k: [] for k in ("meds", "diagnoses", "labs", "cave", "contacts", "negatives", "findings")}
    for p in pages:
        if p.get("doc_id") and doc_by_id[p["doc_id"]]["type"] == "irrelevant":
            continue
        for k, v in p.get("facts", {}).items():
            for f in v:
                f["date"] = doc_by_id[f["doc_id"]]["date"] if f.get("doc_id") else None
            all_facts[k].extend(v)

    # --- medication: newest concrete mention wins, explicit "stopped" anywhere newer wins
    meds = {}
    for m in all_facts["meds"]:
        meds.setdefault(m["name"], []).append(m)
    current, conflicts, history = [], [], []
    for name, mentions in meds.items():
        recent = [m for m in mentions if not cutoff or (m["date"] or newest) >= cutoff]
        if not recent:
            history.append({"name": name, "sources": sorted({m["page"] for m in mentions})})
            continue
        concrete = sorted([m for m in recent if m["strength"] or m["dosing"]],
                          key=lambda m: (m["date"] or "", bool(m["strength"]) + bool(m["dosing"])))
        # an undated note (fax, handwritten) is treated as the newest information: safer to ask than to miss a stop
        stops = sorted([m for m in recent if m["status"] in ("stopped", "paused")], key=lambda m: m["date"] or "9999")
        news = [m for m in recent if m["status"] == "new"]
        latest = concrete[-1] if concrete else recent[-1]
        corrections = [m for m in recent if m.get("correction")]
        if corrections:                              # an explicit correction in a document wins
            latest = corrections[-1]
        status = "active"
        if stops and (stops[-1]["date"] or "9999") >= (latest["date"] or ""):
            status = stops[-1]["status"]
        elif news:
            status = "new"
        sources = sorted({m["page"] for m in recent})
        current.append({"name": name, "strength": latest["strength"], "dosing": latest["dosing"],
                        "status": status, "sources": sources, "unknown": any(m.get("unknown") for m in mentions),
                        "ai_corrected": any(m.get("ai_corrected") for m in mentions)})
        variants = {(_norm(m["strength"]), _norm(m["dosing"])) for m in concrete if m["strength"]}
        if len({v[0] for v in variants}) > 1 and not corrections:
            detail = " vs. ".join(f"{m['strength'] or '?'} {m['dosing'] or ''} (S. {m['page']}, {m['date'] or 'ohne Datum'})"
                                  for m in concrete if m["strength"])
            conflicts.append({"text": f"{name}: unterschiedliche Angaben – {detail}",
                              "sources": sorted({m['page'] for m in concrete})})
        if stops and concrete and (concrete[-1]["date"] or "") <= (stops[-1]["date"] or "9999") and \
                any(m["page"] != stops[-1]["page"] for m in concrete):
            conflicts.append({"text": f"{name}: noch in einer Medikationsliste, aber laut S. {stops[-1]['page']} "
                                      f"{'abgesetzt' if stops[-1]['status'] == 'stopped' else 'pausiert'}",
                              "sources": sorted({stops[-1]['page'], concrete[-1]['page']})})
    anticoag_seen = {m["name"] for m in current if m["name"] in ANTICOAGULANTS}
    if len(anticoag_seen) > 1:
        conflicts.append({"text": "Mehrere Antikoagulanzien dokumentiert: " + ", ".join(sorted(anticoag_seen)) +
                                  ". Aktuelles Präparat klären, Doppel-Antikoagulation ausschließen.",
                          "sources": sorted({s for m in current if m["name"] in anticoag_seen for s in m["sources"]})})

    # --- labs: latest value per parameter, with trend
    labs = {}
    for l in sorted(all_facts["labs"], key=lambda l: l["date"] or ""):
        labs.setdefault(l["name"], []).append(l)
    lab_out = []
    for name, vals in labs.items():
        last = vals[-1]
        trend = " → ".join(v["value"] for v in vals) if len(vals) > 1 else ""
        lab_out.append({"name": name, "value": last["value"], "unit": last["unit"], "flag": last["flag"],
                        "trend": trend, "sources": sorted({v["page"] for v in vals})})

    # --- safety checks (simple rules, for the doctor to verify)
    lab_val = {l["name"]: float(l["value"].replace(",", ".")) for l in lab_out}
    active = {m["name"] for m in current if m["status"] in ("active", "new")}
    warnings = []
    if "Metformin" in active and lab_val.get("eGFR", 99) < 30:
        warnings.append({"text": f"Metformin bei eGFR {lab_val['eGFR']:.0f} (< 30): Kontraindikation prüfen",
                         "sources": sorted({*next(m for m in current if m['name'] == 'Metformin')['sources'],
                                            *next(l for l in lab_out if l['name'] == 'eGFR')['sources']})})
    if lab_val.get("Kalium", 0) > 5.0 and active & {"Ramipril", "Lisinopril", "Enalapril", "Candesartan", "Valsartan", "Spironolacton"}:
        warnings.append({"text": f"Kalium {lab_val['Kalium']:.1f} mmol/l unter RAAS-Hemmer",
                         "sources": next(l for l in lab_out if l['name'] == 'Kalium')['sources']})

    # --- CAVE: de-duplicate, keep all source pages
    cave = {}
    for c in all_facts["cave"]:
        cave.setdefault(c["fact"], set()).add(c["page"])
    cave_out = [{"text": k, "sources": sorted(v)} for k, v in cave.items()]
    for m in current:
        if m["name"] in ANTICOAGULANTS and m["status"] in ("active", "new"):
            cave_out.insert(0, {"text": f"Antikoagulation: {m['name']} {m['strength'] or ''} {m['dosing'] or ''}".strip(),
                                "sources": m["sources"]})
    allergy_yes = [c for c in all_facts["cave"] if c["category"] == "allergy"]
    allergy_no = [n for n in all_facts["negatives"] if n["category"] == "allergy"]
    if allergy_yes and allergy_no:
        conflicts.append({"text": "Allergie-Angaben widersprüchlich: " + allergy_yes[0]["fact"] +
                                  f" (S. {allergy_yes[0]['page']}) vs. 'keine bekannt' (S. {allergy_no[0]['page']})",
                          "sources": sorted({allergy_yes[0]["page"], allergy_no[0]["page"]})})

    findings = {}
    for f in all_facts["findings"]:
        findings.setdefault(f["fact"], set()).add(f["page"])

    contacts = {}
    for c in all_facts["contacts"]:
        contacts.setdefault(c["fact"], set()).add(c["page"])

    diags = {}
    for d in sorted(all_facts["diagnoses"], key=lambda d: d["date"] or "", reverse=True):
        key = d["icd10"] or re.sub(r"\W+", "", d["text"].lower())[:40]
        if key not in diags:
            diags[key] = {"text": d["text"], "icd10": d["icd10"], "date": d["date"], "sources": set(), "details": []}
        diags[key]["sources"].add(d["page"])
        diags[key]["ai_corrected"] = diags[key].get("ai_corrected", False) or bool(d.get("ai_corrected"))
        for det in d.get("details", []):
            if det not in diags[key]["details"]:
                diags[key]["details"].append(det)

    return {
        "cave": cave_out,
        "findings": [{"text": k, "sources": sorted(v)} for k, v in findings.items()],
        "contacts": [{"text": k, "sources": sorted(v)} for k, v in contacts.items()],
        "diagnoses": [{**d, "sources": sorted(d["sources"])} for d in diags.values()],
        "medications": sorted(current, key=lambda m: (m["status"] == "stopped", m["name"])),
        "medication_history": history,
        "conflicts": conflicts,
        "warnings": warnings,
        "labs": lab_out,
        "timeline": [{"date": d["date"], "text": d["title"], "doc_id": d["doc_id"], "pages": d["pages"]}
                     for d in sorted(relevant, key=lambda d: d["date"] or "")],
        "ignored": [{"doc_id": d["doc_id"], "pages": d["pages"], "reason": "nicht medizinisch relevant"}
                    for d in docs if d["type"] == "irrelevant"],
    }

# ------------------------------------------------------------------ 6. summary text

def _src(sources):
    return "[S. " + ", ".join(str(s) for s in sources) + "]"


def summary_text(s: dict) -> str:
    out = []
    if s["cave"]:
        out.append("CAVE: " + "; ".join(f"{c['text']} {_src(c['sources'])}" for c in s["cave"]))
    if s["warnings"]:
        out.append("Hinweise: " + "; ".join(f"{w['text']} {_src(w['sources'])}" for w in s["warnings"]))
    if s["findings"]:
        out.append("Befunde: " + "; ".join(f"{f['text']} {_src(f['sources'])}" for f in s["findings"]))
    if s["diagnoses"]:
        out.append("Diagnosen: " + "; ".join(f"{d['text']}{' (' + d['icd10'] + ')' if d['icd10'] else ''} {_src(d['sources'])}" for d in s["diagnoses"][:8]))
    meds = [m for m in s["medications"] if m["status"] != "stopped"]
    if meds:
        out.append("Aktuelle Medikation: " + "; ".join(
            " ".join(x for x in [m["name"], m["strength"] or "", m["dosing"] or "",
                                 "(neu)" if m["status"] == "new" else "", _src(m["sources"])] if x) for m in meds))
    stopped = [m for m in s["medications"] if m["status"] == "stopped"]
    if stopped:
        out.append("Abgesetzt: " + "; ".join(f"{m['name']} {_src(m['sources'])}" for m in stopped))
    if s["conflicts"]:
        out.append("Widersprüche: " + "; ".join(f"{c['text']} {_src(c['sources'])}" for c in s["conflicts"]))
    flagged = [l for l in s["labs"] if l["flag"]]
    if flagged:
        out.append("Labor: " + "; ".join(f"{l['name']} {l['value']} {l['unit']} {l['flag']}"
                                         f"{' (' + l['trend'] + ')' if l['trend'] else ''} {_src(l['sources'])}"
                                         for l in flagged))
    if s["contacts"]:
        out.append("Kontakt: " + "; ".join(f"{c['text']} {_src(c['sources'])}" for c in s["contacts"]))
    return "\n".join(out)

# ------------------------------------------------------------------ run everything

PATIENT_LINE = re.compile(r"Pat(?:ient(?:in)?)?\.?:\s*([A-ZÄÖÜ][\wäöüß-]+(?:\s+[A-ZÄÖÜ][\wäöüß-]+)+),\s*geb\.?\s*(\d{2}\.\d{2}\.\d{4})")


def find_patient(pages: list[dict]) -> dict:
    """Most frequent 'Pat.: Name, geb. dd.mm.yyyy' across all pages (OCR typos are outvoted)."""
    votes = {}
    for p in pages:
        for m in PATIENT_LINE.finditer(page_text(p)):
            votes[(m.group(1).strip(), m.group(2))] = votes.get((m.group(1).strip(), m.group(2)), 0) + 1
    if not votes:
        return {"name": None, "birth": None}
    (name, birth), _ = max(votes.items(), key=lambda kv: kv[1])
    name = re.sub(r"^(Frau|Herrn?|Fr\.|Hr\.)\s+", "", name)
    return {"name": name, "birth": birth}


def page_facts(p: dict) -> list[dict]:
    """Compact list of what was found on a page (for highlighting in the app)."""
    out = []
    for kind, items in p.get("facts", {}).items():
        for f in items:
            label = f.get("name") or f.get("fact") or f.get("text") or ""
            if kind == "labs":
                label = f"{f['name']} {f['value']} {f['unit']}".strip()
            elif kind == "meds":
                label = " ".join(x for x in [f["name"], f.get("strength"), f.get("dosing"), f.get("status")] if x)
            elif kind == "diagnoses":
                label = f"{f['text']} ({f['icd10']})" if f['icd10'] else f['text']
            out.append({"kind": kind, "label": label, "source_text": f.get("source_text")})
    for c in p.get("corrections", []):
        out.append({"kind": "corrections", "label": f"{c['original']} → {c['corrected']}",
                    "source_text": c["source_text"]})
    return out


def process_case(folder: Path, out_dir: Path, engine="tesseract", fresh=False, progress=print,
                 extractor: str | None = None) -> dict:
    extractor = extractor or config.EXTRACTOR
    if extractor == "llm":
        from .llm_extract import extract_page_llm
        from .mistral import MistralError
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    cache_dir = out_dir / "ocr"
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Pages are read in parallel (config.OCR_WORKERS); threads are enough because Tesseract runs as its
    # own process and OpenCV releases the GIL. Progress is reported here, in the calling thread
    # (Streamlit widgets must not be touched from worker threads), and the page order stays as before.
    pages: list[dict | None] = [None] * len(files)
    with ThreadPoolExecutor(max_workers=min(config.OCR_WORKERS, max(1, len(files)))) as pool:
        futures = {pool.submit(read_page, f, i, engine, cache_dir, fresh): i
                   for i, f in enumerate(files, 1)}
        for done, fut in enumerate(as_completed(futures), 1):
            i = futures[fut]
            page = fut.result()
            page["quality"] = page_quality(page)     # recomputed, so threshold changes need no new OCR
            pages[i - 1] = page
            progress(f"[{done}/{len(files)}] {files[i - 1].name}  quality={page['quality']}")
    docs = group_documents(pages)
    ok_pages = [p for p in pages if p["quality"] == "ok"]
    extract_errors = []
    for i, p in enumerate(ok_pages, 1):
        corr = []
        if extractor == "llm":
            progress(f"[KI {i}/{len(ok_pages)}] Seite {p['page']}")
            try:
                facts, corr = extract_page_llm(p)
            except MistralError as e:
                facts = extract_page(p)
                p["extract_error"] = str(e)
                extract_errors.append({"page": p["page"], "error": str(e)})
        else:
            facts = extract_page(p)
        p["facts"], p["corrections"] = facts, corr
    summary = merge(pages, docs)
    summary["corrections"] = [{**c, "sources": [p["page"]]}
                              for p in sorted(ok_pages, key=lambda p: p["page"]) for c in p["corrections"]]
    if extract_errors:
        summary["extract_errors"] = extract_errors
    summary["text_de"] = summary_text(summary)
    result = {
        "case_id": folder.parent.name if folder.name.startswith("pages") else folder.name,
        "status": "ready", "engine": engine, "extractor": extractor,
        "processed_at": datetime.now().isoformat(timespec="seconds"),
        "patient": find_patient([p for p in pages if p["quality"] == "ok"]),
        "pages": [{"page": p["page"], "file": p["file"], "doc_id": p.get("doc_id"), "doc_type": p.get("doc_type"),
                   "status": "done" if p["quality"] == "ok" else "retake", "quality": p["quality"],
                   "sharpness": p["sharpness"], "mean_confidence": p["mean_confidence"],
                   "facts": page_facts(p), "corrections": p.get("corrections", []),
                   "extract_error": p.get("extract_error")} for p in pages],
        "documents": docs,
        "summary": summary,
    }
    (out_dir / "case_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
