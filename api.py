"""Get Well OCR: HTTP API (first endpoint: upload pages, get the extracted text back).

Run from the project folder:   uvicorn api:app --host 0.0.0.0 --port 8000
Interactive docs:              http://localhost:8000/docs

Stateless for now: uploads are processed in memory and not stored.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Literal

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from src import config
from src.case import page_quality, sharpness
from src.extract import read_text
from src.parse import merge_rows
from src.preprocess import preprocess, to_gray
from src.schema import BoundingBox
from src.store import UPLOAD_TYPES, _to_images

MAX_FILES = 50
MAX_FILE_BYTES = 25 * 1024 * 1024   # per file

app = FastAPI(title="Get Well OCR API", version="0.1.0")


class Line(BaseModel):
    text: str
    confidence: float | None = None
    bbox: BoundingBox | None = None


class Page(BaseModel):
    page: int                       # running number over all uploaded pages, starting at 1
    file: str                       # original file name
    file_page: int                  # page inside that file (PDFs can have several)
    quality: Literal["ok", "too_blurry", "unreadable"]
    sharpness: int
    mean_confidence: float | None
    steps: list[str]                # cleanup steps that were applied
    text: str
    lines: list[Line]


class OCRResponse(BaseModel):
    engine: str
    page_count: int
    text: str                       # all pages, separated by a blank line
    pages: list[Page]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "default_engine": config.OCR_ENGINE}


# Plain "def" on purpose: FastAPI runs it in a worker thread, so slow OCR doesn't block the server.
@app.post("/ocr", response_model=OCRResponse)
def ocr(
    files: list[UploadFile] = File(..., description="Photos or PDFs, in page order"),
    engine: Literal["tesseract", "azure"] | None = Form(None, description="Default: OCR_ENGINE from .env"),
) -> OCRResponse:
    engine = engine or config.OCR_ENGINE
    if engine == "azure" and not (config.AZURE_DI_ENDPOINT and config.AZURE_DI_KEY):
        raise HTTPException(400, "Azure endpoint/key not configured on the server.")
    if len(files) > MAX_FILES:
        raise HTTPException(413, f"At most {MAX_FILES} files per request.")

    # 1. Check and decode all uploads first (cheap), 2. then OCR the pages in parallel
    todo: list[tuple[str, int, np.ndarray]] = []
    for upload in files:
        name = upload.filename or "upload"
        suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if suffix not in UPLOAD_TYPES:
            raise HTTPException(415, f"{name}: unsupported type. Allowed: {', '.join(UPLOAD_TYPES)}")
        data = upload.file.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(413, f"{name}: larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
        try:
            images = _to_images(name, data)
        except Exception as e:
            raise HTTPException(422, f"{name}: could not read file ({e}).") from e

        for file_page, pil in enumerate(images, start=1):
            todo.append((name, file_page, cv2.cvtColor(np.array(pil.convert("RGB")), cv2.COLOR_RGB2BGR)))

    def read_one(number: int, job: tuple[str, int, np.ndarray]) -> Page:
        name, file_page, img = job
        clean, steps = preprocess(img)
        try:
            lines = merge_rows(read_text(clean, engine))
        except Exception as e:
            raise HTTPException(502, f"{name} page {file_page}: OCR failed ({e}).") from e
        confs = [l.confidence for l in lines if l.confidence is not None]
        info = {"sharpness": round(sharpness(to_gray(img))),
                "mean_confidence": round(sum(confs) / len(confs), 2) if confs else None}
        return Page(
            page=number, file=name, file_page=file_page,
            quality=page_quality(info), steps=steps, **info,
            text="\n".join(l.text for l in lines),
            lines=[Line(text=l.text, confidence=l.confidence, bbox=l.bbox) for l in lines],
        )

    # map keeps the page order; an HTTPException from one page is raised again here
    with ThreadPoolExecutor(max_workers=min(config.OCR_WORKERS, max(1, len(todo)))) as pool:
        pages = list(pool.map(read_one, range(1, len(todo) + 1), todo))

    return OCRResponse(engine=engine, page_count=len(pages),
                       text="\n\n".join(p.text for p in pages), pages=pages)
