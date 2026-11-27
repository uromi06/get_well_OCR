"""Case storage: one folder per case, plain files, no database.

    data/cases/<id>/pages_photo/          fictional test cases (in git)
    data/private/cases/<id>/pages_photo/  cases created from uploads (never in git)
    outputs/cases/<id>/                   pipeline output: ocr/, case_result.json, review.json

Used by the Streamlit app now and by the FastAPI backend later. No UI code here.
"""
from __future__ import annotations

import io
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from . import config

PUBLIC_ROOT = config.DATA_DIR / "cases"
PRIVATE_ROOT = config.DATA_DIR / "private" / "cases"
IMAGE_TYPES = (".jpg", ".jpeg", ".png")
UPLOAD_TYPES = ["jpg", "jpeg", "png", "pdf", "heic", "heif"]


def pages_dir(case_dir: Path) -> Path:
    for name in ("pages_photo", "pages"):
        if (case_dir / name).is_dir():
            return case_dir / name
    return case_dir / "pages_photo"


def page_files(case_dir: Path) -> list[Path]:
    d = pages_dir(case_dir)
    return sorted(p for p in d.iterdir() if p.suffix.lower() in IMAGE_TYPES) if d.exists() else []


def list_cases() -> list[dict]:
    cases = []
    for root, private in ((PUBLIC_ROOT, False), (PRIVATE_ROOT, True)):
        if not root.exists():
            continue
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            files = page_files(d)
            if not files:
                continue
            answers = d / f"{d.name}_answers.json"
            meta = d / "case.json"
            info = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
            label, created = info.get("label", d.name), info.get("created_at")
            cases.append({"id": d.name, "label": label, "created_at": created, "dir": d, "pages_dir": pages_dir(d),
                          "n_pages": len(files), "private": private,
                          "answers": answers if answers.exists() else None})
    return cases


def out_dir(case_id: str) -> Path:
    return config.OUTPUT_DIR / "cases" / case_id


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40] or "case"


def _to_images(name: str, data: bytes) -> list:
    """Uploaded file -> list of PIL images (PDF: one per page, HEIC from iPhones supported)."""
    from PIL import Image, ImageOps
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(data)
        return [pdf[i].render(scale=200 / 72).to_pil() for i in range(len(pdf))]
    if suffix in (".heic", ".heif"):
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError as e:
            raise RuntimeError("iPhone HEIC photos need:  pip install pillow-heif") from e
    img = Image.open(io.BytesIO(data))
    return [ImageOps.exif_transpose(img)]     # respect the phone's rotation flag


def create_case(label: str, uploads: list[tuple[str, bytes]]) -> str:
    """Save uploaded photos/PDFs as numbered JPG pages in a new private case. Returns the case id."""
    case_id = f"{datetime.now():%Y%m%d-%H%M}-{slug(label)}"
    case_dir = PRIVATE_ROOT / case_id
    target = case_dir / "pages_photo"
    target.mkdir(parents=True, exist_ok=True)
    n = 0
    for name, data in uploads:              # keep the upload order = page order
        for img in _to_images(name, data):
            n += 1
            img.convert("RGB").save(target / f"{case_id}_p{n:02d}.jpg", quality=92)
    (case_dir / "case.json").write_text(json.dumps(
        {"id": case_id, "label": label, "created_at": datetime.now().isoformat(timespec="seconds"),
         "pages": n}, ensure_ascii=False, indent=2), encoding="utf-8")
    return case_id


def delete_case(case_id: str) -> None:
    """Delete a private case and all its outputs (photos, OCR, results, review)."""
    case_dir = PRIVATE_ROOT / case_id
    if case_dir.exists():
        shutil.rmtree(case_dir)
    if out_dir(case_id).exists():
        shutil.rmtree(out_dir(case_id))


def delete_all_private() -> int:
    """Delete every uploaded case (photos, OCR, results, review). Test cases in data/cases stay."""
    n = 0
    if PRIVATE_ROOT.exists():
        for d in [p for p in PRIVATE_ROOT.iterdir() if p.is_dir()]:
            delete_case(d.name)
            n += 1
    return n


def load_result(case_id: str) -> dict | None:
    f = out_dir(case_id) / "case_result.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def load_review(case_id: str) -> dict | None:
    f = out_dir(case_id) / "review.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def save_review(case_id: str, review: dict) -> None:
    review["updated_at"] = datetime.now().isoformat(timespec="seconds")
    out_dir(case_id).mkdir(parents=True, exist_ok=True)
    (out_dir(case_id) / "review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
