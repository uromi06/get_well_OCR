"""Accuracy against the answer files (ground truth).

Medications are matched by fuzzy name similarity (OCR can drop or swap a
letter), then strength and dosing are checked exactly. Diagnoses are matched
by ICD-10 code.

Usage from code:
    from src.evaluate import score_document
    scores = score_document(prediction, truth)
"""
import re

from rapidfuzz import fuzz

from .schema import ExtractionResult

NAME_MATCH_THRESHOLD = 85  # 0-100


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", "", (s or "").lower().replace(",", ".").replace("ug", "µg"))


def _f1(tp: int, n_pred: int, n_true: int) -> dict:
    precision = tp / n_pred if n_pred else 0.0
    recall = tp / n_true if n_true else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def score_document(pred: ExtractionResult, truth: ExtractionResult) -> dict:
    # --- medications ---
    unused = list(pred.medications)
    matched, strength_ok, dosing_ok = 0, 0, 0
    for t in truth.medications:
        best, best_score = None, 0
        for p in unused:
            s = fuzz.token_set_ratio(t.name.lower(), p.name.lower())
            if s > best_score:
                best, best_score = p, s
        if best is not None and best_score >= NAME_MATCH_THRESHOLD:
            matched += 1
            unused.remove(best)
            strength_ok += _norm(best.strength) == _norm(t.strength)
            dosing_ok += _norm(best.dosing) == _norm(t.dosing)

    med = _f1(matched, len(pred.medications), len(truth.medications))

    # --- diagnoses (by ICD code) ---
    true_codes = {_norm(d.icd10) for d in truth.diagnoses if d.icd10}
    pred_codes = {_norm(d.icd10) for d in pred.diagnoses if d.icd10}
    dx = _f1(len(true_codes & pred_codes), len(pred_codes), len(true_codes))

    return {
        "document_id": truth.document_id,
        "med_precision": med["precision"],
        "med_recall": med["recall"],
        "med_f1": med["f1"],
        "strength_accuracy": strength_ok / matched if matched else 0.0,
        "dosing_accuracy": dosing_ok / matched if matched else 0.0,
        "dx_f1": dx["f1"],
    }


# ---------------------------------------------------------------- whole-case scoring

# needle id -> words that must ALL appear in the case summary (used when the answer
# file has no "match" list of its own)
DEFAULT_NEEDLE_MATCH = {
    "N1": ["Apixaban"], "N2": ["Penicillin"], "N3": ["Schrittmacher"], "N4": ["TEP"],
    "N5": ["Reanimation", "Intubation"], "N6": ["Tochter"], "N7": ["eGFR", "28"],
    "N8": ["Kalium", "5,3"], "N9": ["Phenprocoumon", "Apixaban", "Antikoagul"],
    "N10": ["Glimepirid", "abgesetzt"], "N11": ["Metformin", "eGFR"], "N12": ["LVEF", "40"],
    "N13": ["Torasemid", "20 mg"], "N14": ["Ramipril", "pausiert"],
}


def score_case(result: dict, answers: dict) -> dict:
    """Score a case_result.json against <case>_answers.json. Returns numbers plus details."""
    import json
    # Raw OCR in corrections and error messages is not an extracted fact.
    summary = json.dumps({k: v for k, v in result["summary"].items()
                          if k not in ("text_de", "corrections", "extract_errors")}, ensure_ascii=False).lower()
    needles = []
    for n in answers["needles"]:
        keys = n.get("match") or DEFAULT_NEEDLE_MATCH.get(n["id"], [])
        needles.append({"id": n["id"], "fact": n["fact"], "found": all(k.lower() in summary for k in keys)})
    # medication status: a drug that is mentioned but filed as stopped (or vice versa) is a
    # dangerous error the word search above cannot see
    def _on(status):
        return status not in ("stopped", "paused")
    got = {m["name"].lower(): m.get("status") for m in result["summary"].get("medications", [])}
    status_wrong = []
    for m in answers.get("current_medication", []):
        mine = got.get(m["name"].lower(), "missing")
        if mine == "missing" or _on(mine) != _on(m["status"]):
            status_wrong.append({"name": m["name"], "truth": m["status"], "predicted": mine or "active"})
    for n in needles:                       # N1 "Apixaban is the current anticoagulant" needs Apixaban active
        if n["id"] == "N1" and any(w["name"] == "Apixaban" for w in status_wrong):
            n["found"] = False
    truth = {p: d["type"] for d in answers["documents"] for p in d["pages"]}
    pred = {p["page"]: p["doc_type"] for p in result["pages"]}
    judged = [p for p in truth if pred.get(p)]
    wrong = [{"page": p, "predicted": pred[p], "truth": truth[p]} for p in judged if pred[p] != truth[p]]
    n_meds = len(answers.get("current_medication", []))
    return {
        "meds_status_correct": n_meds - len(status_wrong), "meds_total": n_meds, "meds_status_wrong": status_wrong,
        "needles_found": sum(n["found"] for n in needles), "needles_total": len(needles),
        "pages_classified": len(judged), "pages_correct": len(judged) - len(wrong),
        "retake": [p["page"] for p in result["pages"] if p["status"] == "retake"],
        "conflicts_flagged": len(result["summary"]["conflicts"]), "conflicts_truth": len(answers["conflicts"]),
        "needles": needles, "misclassified": wrong,
    }
