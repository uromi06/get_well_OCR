"""Reading text from the image (OCR).

Engines are interchangeable: every engine takes an image and returns OCRLine
objects with text, position and confidence. Switch with OCR_ENGINE in .env or
in the app sidebar.

Azure results are cached to disk, so a document you have read once can be
shown again instantly and offline (important for a live demo).
"""
import hashlib
import json

import cv2
import numpy as np

from . import config
from .schema import BoundingBox, OCRLine


# ---------- helpers ----------

def _image_hash(img: np.ndarray) -> str:
    return hashlib.sha1(img.tobytes()).hexdigest()[:16]


def _png_bytes(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("Could not encode image")
    return buf.tobytes()


# ---------- Tesseract (free, offline) ----------

def read_tesseract(img: np.ndarray) -> list[OCRLine]:
    import pytesseract
    if config.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD

    h, w = img.shape[:2]
    data = pytesseract.image_to_data(img, lang=config.TESSERACT_LANG,
                                     output_type=pytesseract.Output.DICT)
    # Group words into lines
    lines: dict[tuple, dict] = {}
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        x, y, bw, bh = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        conf = float(data["conf"][i])
        entry = lines.setdefault(key, {"words": [], "box": [x, y, x + bw, y + bh], "confs": []})
        entry["words"].append(word)
        b = entry["box"]
        entry["box"] = [min(b[0], x), min(b[1], y), max(b[2], x + bw), max(b[3], y + bh)]
        if conf >= 0:
            entry["confs"].append(conf / 100)

    out = []
    for entry in lines.values():
        x0, y0, x1, y1 = entry["box"]
        conf = sum(entry["confs"]) / len(entry["confs"]) if entry["confs"] else None
        out.append(OCRLine(text=" ".join(entry["words"]),
                           bbox=BoundingBox(x0=x0 / w, y0=y0 / h, x1=x1 / w, y1=y1 / h),
                           confidence=conf))
    out.sort(key=lambda l: (l.bbox.y0, l.bbox.x0))
    return out


# ---------- Azure Document Intelligence (cloud, EU region) ----------

def read_azure(img: np.ndarray, use_cache: bool = True) -> list[OCRLine]:
    cache_file = config.CACHE_DIR / f"azure_{_image_hash(img)}.json"
    if use_cache and cache_file.exists():
        return [OCRLine(**d) for d in json.loads(cache_file.read_text(encoding="utf-8"))]

    if not (config.AZURE_DI_ENDPOINT and config.AZURE_DI_KEY):
        raise RuntimeError("Azure endpoint/key missing. Fill them in your .env file.")

    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential

    client = DocumentIntelligenceClient(config.AZURE_DI_ENDPOINT,
                                        AzureKeyCredential(config.AZURE_DI_KEY))
    # "prebuilt-read" = plain OCR with positions. If the SDK version complains
    # about the argument name, check the azure-ai-documentintelligence docs.
    poller = client.begin_analyze_document("prebuilt-read", body=_png_bytes(img),
                                           content_type="application/octet-stream")
    result = poller.result()

    out = []
    for p_idx, page in enumerate(result.pages or []):
        pw, ph = page.width or 1, page.height or 1
        words = page.words or []
        for line in page.lines or []:
            poly = line.polygon or []
            xs, ys = poly[0::2], poly[1::2]
            bbox = (BoundingBox(page=p_idx, x0=min(xs) / pw, y0=min(ys) / ph,
                                x1=max(xs) / pw, y1=max(ys) / ph) if xs else None)
            # Line confidence = mean confidence of the words inside it
            confs = [wd.confidence for wd in words
                     if wd.content in line.content and wd.confidence is not None]
            conf = sum(confs) / len(confs) if confs else None
            out.append(OCRLine(text=line.content, bbox=bbox, confidence=conf))

    cache_file.write_text(json.dumps([l.model_dump() for l in out], ensure_ascii=False, indent=1),
                          encoding="utf-8")
    return out


# ---------- Mistral Document AI (cloud, EU region, hackathon endpoint) ----------

def read_mistral(img: np.ndarray) -> list[OCRLine]:
    """Mistral OCR returns Markdown without positions or confidences.

    So: no highlight boxes on the page for this engine, and a fixed confidence
    (the page-quality gate then relies on the sharpness check).
    """
    from .mistral import markdown_to_lines, ocr_markdown
    return [OCRLine(text=t, bbox=None, confidence=0.95) for t in markdown_to_lines(ocr_markdown(img))]


# ---------- single entry point ----------

ENGINES = {"tesseract": read_tesseract, "mistral": read_mistral, "azure": read_azure}


def read_text(img: np.ndarray, engine: str | None = None) -> list[OCRLine]:
    engine = (engine or config.OCR_ENGINE).lower()
    if engine not in ENGINES:
        raise ValueError(f"Unknown engine '{engine}'. Choose from {list(ENGINES)}")
    return ENGINES[engine](img)
