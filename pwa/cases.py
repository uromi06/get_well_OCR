"""Case logic for the PWA, built only from the existing pipeline in src/ (nothing there is changed).

The review rules (machine rows, correction log, which review is still valid) are the same as in
views/case_workspace.py, so a case looks the same in the Streamlit app and in the PWA, and both
read and write the same files (data/private/cases, outputs/cases/<id>/review.json).
"""
from __future__ import annotations

import io
import json
import re
import threading
from functools import lru_cache
from pathlib import Path

from PIL import Image

from src import mistral, store
from src.case import process_case
from src.evaluate import score_case
from src.preprocess import load_image, preprocess

MED_STATUSES = ["active", "new", "paused", "stopped"]

# ------------------------------------------------------------------ cases


def find_case(case_id: str) -> dict | None:
    return next((c for c in store.list_cases() if c["id"] == case_id), None)


def case_info(c: dict) -> dict:
    """The JSON-safe part of a store.list_cases() entry, plus who and what it is for the case list."""
    result = store.load_result(c["id"])
    info = {"id": c["id"], "label": c["label"], "created_at": c["created_at"], "n_pages": c["n_pages"],
            "private": c["private"], "test_case": c["answers"] is not None, "processed": result is not None,
            "processed_at": None, "patient": None, "issuer": None, "doc_type": None, "n_docs": 0}
    if result:
        docs = [d for d in result.get("documents", []) if d.get("type") not in ("irrelevant", "unknown")]
        first = docs[0] if docs else None
        info.update(processed_at=result.get("processed_at"), patient=(result.get("patient") or {}).get("name"),
                    issuer=first.get("issuer") if first else None, doc_type=first.get("type") if first else None,
                    n_docs=len(result.get("documents", [])))
    return info


# ------------------------------------------------------------------ processing jobs (in memory)

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def job(case_id: str) -> dict | None:
    with _lock:
        return dict(_jobs[case_id]) if case_id in _jobs else None


def start_processing(c: dict, engine: str, fresh: bool) -> dict:
    """Run process_case in a background thread; progress is read with job(case_id)."""
    with _lock:
        if _jobs.get(c["id"], {}).get("state") == "running":
            return dict(_jobs[c["id"]])
        _jobs[c["id"]] = {"state": "running", "done": 0, "total": c["n_pages"], "error": None, "engine": engine,
                           "extractor": "llm", "ai_done": 0, "ai_total": 0}

    def progress(msg: str):
        m = re.match(r"\[(\d+)/(\d+)\]", msg)
        if m:
            with _lock:
                _jobs[c["id"]].update(done=int(m.group(1)), total=int(m.group(2)))
        m = re.match(r"\[KI (\d+)/(\d+)\]", msg)      # AI extraction, page by page
        if m:
            with _lock:
                _jobs[c["id"]].update(ai_done=int(m.group(1)) - 1, ai_total=int(m.group(2)))

    def run():
        try:
            # The PWA reads and extracts with Mistral; a page whose AI extraction fails falls back to the rules
            process_case(c["pages_dir"], store.out_dir(c["id"]), engine, fresh, progress=progress, extractor="llm")
            state, error = "done", None
        except mistral.MistralError as e:
            state, error = "error", f"Mistral nicht erreichbar: {e}. Bitte später erneut versuchen."
        except Exception as e:          # shown to the user, the thread must not die silently
            state, error = "error", f"Verarbeitung fehlgeschlagen: {e}"
        with _lock:
            _jobs[c["id"]].update(state=state, error=error)

    threading.Thread(target=run, name=f"process-{c['id']}", daemon=True).start()
    return job(c["id"])


# ------------------------------------------------------------------ review (same rules as the Streamlit view)


def machine_rows(summary: dict) -> list[dict]:
    conflict_names = {m["name"] for m in summary["medications"]
                      if any(m["name"] in c["text"] for c in summary["conflicts"] + summary["warnings"])}
    return [{"confirmed": False, "name": m["name"], "strength": m.get("strength") or "",
             "dosing": m.get("dosing") or "", "status": m["status"],
             "flag": "⚠ prüfen" if m["name"] in conflict_names or m.get("unknown") else "",
             "sources": ", ".join(str(s) for s in m["sources"])} for m in summary["medications"]]


def current_review(case_id: str, result: dict) -> dict:
    """The saved review if it belongs to this processing run, else a fresh one (not saved yet)."""
    saved = store.load_review(case_id)
    if saved and saved.get("processed_at") == result.get("processed_at"):
        return saved
    rows = machine_rows(result["summary"])
    return {"processed_at": result.get("processed_at"), "meds": rows, "machine": [dict(r) for r in rows],
            "conflicts_ok": [], "reviewer": ""}


def audit(review: dict) -> list[dict]:
    machine = {m["name"]: m for m in review["machine"]}
    changes = []
    for row in review["meds"]:
        before = machine.get(row["name"])
        for field in ("strength", "dosing", "status"):
            if before and str(before[field]) != str(row[field]):
                changes.append({"medication": row["name"], "field": field, "machine": before[field],
                                "doctor": row[field]})
    return changes


def clean_meds(rows: list) -> list[dict]:
    """Validate medication rows sent by the PWA (same fields as the Streamlit table)."""
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        name = str(r.get("name") or "").strip()
        if not name:
            continue
        status = r.get("status") if r.get("status") in MED_STATUSES else "active"
        out.append({"confirmed": bool(r.get("confirmed")), "name": name,
                    "strength": str(r.get("strength") or ""), "dosing": str(r.get("dosing") or ""),
                    "status": status, "flag": str(r.get("flag") or ""), "sources": str(r.get("sources") or "")})
    return out


def confirmed_meds(review: dict) -> list[dict]:
    return [{"name": r["name"], "strength": r["strength"] or None, "dosing": r["dosing"] or None,
             "status": r["status"], "form": None, "as_needed": False,
             "sources": [int(s) for s in re.findall(r"\d+", r["sources"])]} for r in review["meds"]]


def is_ready(review: dict) -> bool:
    return all(r["confirmed"] for r in review["meds"])


def score(c: dict, result: dict) -> dict | None:
    if not c["answers"]:
        return None
    return score_case(result, json.loads(c["answers"].read_text(encoding="utf-8")))


# ------------------------------------------------------------------ page images


def page_file(c: dict, result: dict | None, page_no: int) -> Path | None:
    files = store.page_files(c["dir"])
    if result:
        p = next((x for x in result["pages"] if x["page"] == page_no), None)
        if p:
            f = c["pages_dir"] / p["file"]
            return f if f.exists() else None
    return files[page_no - 1] if 1 <= page_no <= len(files) else None


def ocr_cache(case_id: str, file_name: str, engine: str) -> dict | None:
    f = store.out_dir(case_id) / "ocr" / f"{Path(file_name).stem}_{engine}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def _jpeg(img: Image.Image, quality: int = 85) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


@lru_cache(maxsize=400)
def thumbnail(path: str, mtime: float, width: int = 360) -> bytes:
    img = Image.open(path)
    img.thumbnail((width, width * 2))
    return _jpeg(img, 80)


@lru_cache(maxsize=40)
def marked_page(path: str, mtime: float, ocr_json: str, facts_json: str) -> bytes:
    """Cleaned page with the OCR lines boxed that facts came from (same drawing as the Streamlit app)."""
    from views.components import highlight     # pure OpenCV function; nothing Streamlit-specific runs
    clean, _ = preprocess(load_image(path))
    marked = highlight(clean, json.loads(ocr_json)["lines"], json.loads(facts_json))
    img = Image.fromarray(marked)
    img.thumbnail((1600, 3200))
    return _jpeg(img)


def photo(path: str) -> bytes:
    img = Image.open(path)
    img.thumbnail((1600, 3200))
    return _jpeg(img)
