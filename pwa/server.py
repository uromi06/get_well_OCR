"""Get Well OCR PWA: the installable phone/web app plus the JSON API behind it.

Run from the project folder:   uvicorn pwa.server:app --host 0.0.0.0 --port 8000

  /                 the PWA (pwa/static: HTML, JS, manifest, service worker)
  /health, /ocr     the existing endpoints from api.py, unchanged
  /api/...          case endpoints for the PWA (login required), built on src/ like the Streamlit app

Runs next to the Streamlit app and uses the same case files, so both show the same cases.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import api as ocr_api
from src import config, mistral, store
from src.case import CONFIDENCE_MIN, SHARPNESS_MIN
from src.export import LANGUAGES, patient_plan_pdf, to_csv, to_fhir
from src.report import er_report
from views.components import DOC_TYPE_COLORS, DOC_TYPE_LABELS, FACT_COLORS_BGR, FACT_LABELS, STATUS_LABELS

from . import auth, cases

STATIC = Path(__file__).parent / "static"
Engine = Literal["tesseract", "mistral"]

app = FastAPI(title="Get Well OCR PWA", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")

# The existing API endpoints, exactly as in api.py (same functions, same behaviour)
for route in ocr_api.app.routes:
    if getattr(route, "path", None) in ("/health", "/ocr"):
        app.router.routes.append(route)


def _case_or_404(case_id: str) -> dict:
    c = cases.find_case(case_id)
    if c is None:
        raise HTTPException(404, "Fall nicht gefunden.")
    return c


def _result_or_409(case_id: str) -> dict:
    result = store.load_result(case_id)
    if result is None:
        raise HTTPException(409, "Fall ist noch nicht verarbeitet.")
    return result


# ================================================================== login


class Login(BaseModel):
    username: str
    password: str


@app.post("/api/login")
def login(body: Login, request: Request, response: Response) -> dict:
    if auth.credentials() is None:
        raise HTTPException(503, "Login ist nicht eingerichtet: APP_USERNAME und APP_PASSWORD fehlen auf dem Server.")
    if not auth.check_login(body.username, body.password):
        time.sleep(0.7)                       # slows down guessing
        raise HTTPException(401, "Benutzername oder Passwort falsch.")
    response.set_cookie(auth.COOKIE, auth.make_token(body.username), max_age=auth.MAX_AGE, httponly=True,
                        samesite="strict", secure=request.url.scheme == "https", path="/")
    return {"user": body.username}


@app.post("/api/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@app.get("/api/me")
def me(user: str = Depends(auth.require_user)) -> dict:
    return {"user": user}


@app.get("/api/meta")
def meta() -> dict:
    """Labels and options for the UI (no login needed, nothing patient-related)."""
    def hexcol(bgr):
        return "#%02x%02x%02x" % (bgr[2], bgr[1], bgr[0])
    return {
        "login_configured": auth.credentials() is not None,
        "engines": [{"id": "tesseract", "label": "Tesseract", "available": True},
                    {"id": "mistral", "label": "Mistral OCR", "available": mistral.ocr_available()}],
        # The PWA reads with Mistral OCR by default; Tesseract only if Mistral is not set up on this server
        "default_engine": "mistral" if mistral.ocr_available() else "tesseract",
        "chat_available": mistral.chat_available(),
        "doc_types": {k: {"label": v, "color": DOC_TYPE_COLORS.get(k, "#94a3b8")}
                      for k, v in DOC_TYPE_LABELS.items() if k},
        "statuses": STATUS_LABELS,
        "facts": {k: {"label": FACT_LABELS[k], "color": hexcol(c)} for k, c in FACT_COLORS_BGR.items()},
        "plan_languages": LANGUAGES,
        "upload_types": store.UPLOAD_TYPES,
        "max_files": ocr_api.MAX_FILES,
        "max_file_mb": ocr_api.MAX_FILE_BYTES // (1024 * 1024),
        "sharpness_min": SHARPNESS_MIN,
        "confidence_min": CONFIDENCE_MIN,
    }


# ================================================================== cases


@app.get("/api/cases")
def list_cases(_: str = Depends(auth.require_user)) -> list[dict]:
    out = []
    for c in store.list_cases():
        info = cases.case_info(c)
        info["job"] = cases.job(c["id"])
        out.append(info)
    return sorted(out, key=lambda c: (c["created_at"] or "", c["id"]), reverse=True)


@app.post("/api/cases")
def create_case(files: list[UploadFile] = File(...), label: str = Form(""), engine: Engine = Form("tesseract"),
                _: str = Depends(auth.require_user)) -> dict:
    if engine == "mistral" and not mistral.ocr_available():
        raise HTTPException(400, "Mistral OCR ist auf dem Server nicht eingerichtet.")
    if len(files) > ocr_api.MAX_FILES:
        raise HTTPException(413, f"Höchstens {ocr_api.MAX_FILES} Dateien pro Fall.")
    uploads = []
    for f in files:
        name = f.filename or "upload"
        suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if suffix not in store.UPLOAD_TYPES:
            raise HTTPException(415, f"{name}: Dateityp nicht erlaubt ({', '.join(store.UPLOAD_TYPES)}).")
        data = f.file.read(ocr_api.MAX_FILE_BYTES + 1)
        if len(data) > ocr_api.MAX_FILE_BYTES:
            raise HTTPException(413, f"{name}: größer als {ocr_api.MAX_FILE_BYTES // (1024 * 1024)} MB.")
        uploads.append((name, data))
    try:
        case_id = store.create_case(label.strip() or "Neuer Fall", uploads)
    except RuntimeError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        raise HTTPException(422, f"Dateien konnten nicht gelesen werden ({e}).") from e
    c = _case_or_404(case_id)
    return {"case": cases.case_info(c), "job": cases.start_processing(c, engine, fresh=False)}


class Process(BaseModel):
    engine: Engine = "tesseract"
    fresh: bool = False


@app.post("/api/cases/{case_id}/process")
def process(case_id: str, body: Process, _: str = Depends(auth.require_user)) -> dict:
    if body.engine == "mistral" and not mistral.ocr_available():
        raise HTTPException(400, "Mistral OCR ist auf dem Server nicht eingerichtet.")
    return cases.start_processing(_case_or_404(case_id), body.engine, body.fresh)


@app.get("/api/cases/{case_id}/job")
def job_status(case_id: str, _: str = Depends(auth.require_user)) -> dict:
    _case_or_404(case_id)
    return cases.job(case_id) or {"state": "idle"}


@app.get("/api/cases/{case_id}")
def get_case(case_id: str, _: str = Depends(auth.require_user)) -> dict:
    c = _case_or_404(case_id)
    result = store.load_result(case_id)
    body = {"case": cases.case_info(c), "job": cases.job(case_id), "result": result}
    if result:
        review = cases.current_review(case_id, result)
        body.update(review=review, corrections=cases.audit(review), ready=cases.is_ready(review),
                    score=cases.score(c, result))
    return body


@app.delete("/api/cases/{case_id}")
def delete_case(case_id: str, _: str = Depends(auth.require_user)) -> dict:
    c = _case_or_404(case_id)
    if not c["private"]:
        raise HTTPException(403, "Testfälle können nicht gelöscht werden.")
    store.delete_case(case_id)
    return {"deleted": case_id}


@app.delete("/api/cases")
def delete_all(confirm: bool = False, _: str = Depends(auth.require_user)) -> dict:
    if not confirm:
        raise HTTPException(400, "Zum Löschen confirm=true mitschicken.")
    return {"deleted": store.delete_all_private()}


# ================================================================== pages


@app.get("/api/cases/{case_id}/pages/{page_no}")
def page_detail(case_id: str, page_no: int, _: str = Depends(auth.require_user)) -> dict:
    _case_or_404(case_id)
    result = _result_or_409(case_id)
    p = next((x for x in result["pages"] if x["page"] == page_no), None)
    if p is None:
        raise HTTPException(404, "Seite nicht gefunden.")
    ocr = cases.ocr_cache(case_id, p["file"], result["engine"])
    doc = next((d for d in result["documents"] if d["doc_id"] == p["doc_id"]), None)
    return {"page": p, "document": doc, "engine": result["engine"],
            "ocr": {"steps": ocr["steps"], "text": "\n".join(l["text"] for l in ocr["lines"])} if ocr else None}


@app.get("/api/cases/{case_id}/pages/{page_no}/image")
def page_image(case_id: str, page_no: int, variant: Literal["thumb", "photo", "marked"] = "thumb",
               _: str = Depends(auth.require_user)) -> Response:
    c = _case_or_404(case_id)
    result = store.load_result(case_id)
    f = cases.page_file(c, result, page_no)
    if f is None:
        raise HTTPException(404, "Seite nicht gefunden.")
    mtime = f.stat().st_mtime
    if variant == "thumb":
        data = cases.thumbnail(str(f), mtime)
    elif variant == "marked" and result:
        p = next(x for x in result["pages"] if x["page"] == page_no)
        ocr = cases.ocr_cache(case_id, p["file"], result["engine"])
        data = (cases.marked_page(str(f), mtime, json.dumps({"lines": ocr["lines"]}), json.dumps(p.get("facts", [])))
                if ocr else cases.photo(str(f)))
    else:
        data = cases.photo(str(f))
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})


# ================================================================== review


class ReviewIn(BaseModel):
    meds: list[dict]
    conflicts_ok: list[int] = []
    reviewer: str = ""


@app.put("/api/cases/{case_id}/review")
def save_review(case_id: str, body: ReviewIn, _: str = Depends(auth.require_user)) -> dict:
    _case_or_404(case_id)
    result = _result_or_409(case_id)
    review = cases.current_review(case_id, result)
    n_conflicts = len(result["summary"]["conflicts"])
    review.update(meds=cases.clean_meds(body.meds),
                  conflicts_ok=sorted({i for i in body.conflicts_ok if 0 <= i < n_conflicts}),
                  reviewer=body.reviewer.strip()[:120])
    store.save_review(case_id, review)
    return {"review": review, "corrections": cases.audit(review), "ready": cases.is_ready(review)}


# ================================================================== report and exports


def _report(case_id: str, lang: str, sources: bool) -> tuple[dict, dict, str]:
    result = _result_or_409(case_id)
    review = cases.current_review(case_id, result)
    text = er_report(result, cases.confirmed_meds(review), lang, confirmed=cases.is_ready(review),
                     reviewer=review.get("reviewer", ""), resolved=review["conflicts_ok"],
                     show_sources=sources)
    return result, review, text


@app.get("/api/cases/{case_id}/report", response_class=PlainTextResponse)
def report(case_id: str, lang: Literal["de", "en"] = "de", sources: bool = False,
           _: str = Depends(auth.require_user)) -> str:
    _case_or_404(case_id)
    return _report(case_id, lang, sources)[2]


def _download(data: bytes | str, name: str, media: str) -> Response:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/cases/{case_id}/export/{kind}")
def export(case_id: str, kind: Literal["txt", "json", "fhir", "csv", "pdf"], lang: str = "de",
           sources: bool = False, plan_lang: str = "de", name: str = "",
           _: str = Depends(auth.require_user)) -> Response:
    _case_or_404(case_id)
    result, review, text = _report(case_id, lang if lang in ("de", "en") else "de", sources)
    if not cases.is_ready(review):
        raise HTTPException(409, "Export erst nach Bestätigung aller Medikamente.")
    stamp = f"{datetime.now():%Y%m%d-%H%M}"
    meds = cases.confirmed_meds(review)
    if kind == "txt":
        return _download(text, f"{case_id}_summary_{stamp}.txt", "text/plain; charset=utf-8")
    if kind == "json":
        payload = {**result, "review": {"reviewer": review.get("reviewer"), "updated_at": review.get("updated_at"),
                                        "medications": review["meds"], "corrections": cases.audit(review),
                                        "conflicts_acknowledged": review["conflicts_ok"]}}
        return _download(json.dumps(payload, ensure_ascii=False, indent=2), f"{case_id}_{stamp}.json",
                         "application/json")
    if kind == "fhir":
        return _download(to_fhir(case_id, meds, result["summary"]["diagnoses"]), f"{case_id}_fhir_{stamp}.json",
                         "application/fhir+json")
    if kind == "csv":
        return _download(to_csv(review["meds"]), f"{case_id}_medikation_{stamp}.csv", "text/csv")
    plan_lang = plan_lang if plan_lang in LANGUAGES else "de"
    who = name or ((result.get("patient") or {}).get("name") or "")
    plan = [m for m in meds if m["status"] in ("active", "new")]
    return _download(patient_plan_pdf(plan, plan_lang, who), f"{case_id}_plan_{plan_lang}.pdf", "application/pdf")


# ================================================================== the PWA itself


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)


@app.middleware("http")
async def headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path in ("/", "/index.html", "/sw.js") or path.endswith((".js", ".css", ".webmanifest")):
        # always revalidate (cheap 304 via ETag): a deploy reaches phones on the next start, never a stale copy
        response.headers["Cache-Control"] = "no-cache"
    if path.startswith("/vendor/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"   # versioned third-party files
    if path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")  # patient data never in a browser cache
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


app.mount("/", StaticFiles(directory=STATIC, html=True), name="pwa")
