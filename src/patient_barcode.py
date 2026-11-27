"""Read the patient ID from a KIS patient label barcode (wristband, label sticker, admission sheet).

KIS labels usually carry Code 128 / Code 39 (1D) or a DataMatrix / QR code. The content is either the
bare ID or a small structured string, e.g. "PID:12345678", "PID=12345678;FALL=…", an HL7 PID segment
("PID|1||12345678^^^KIS^PI||Mustermann^Max…") or a GS1 string. `extract_patient_id` handles these.

Decoding uses zxing-cpp (all common 1D and 2D symbologies, no system libraries); OpenCV's QR reader
and pylibdmtx are fallbacks when zxing-cpp is not installed.
"""
from __future__ import annotations

import io
import re

from PIL import Image, ImageOps

_KEY = r"(?:PAT(?:IENT(?:EN)?)?[-_ ]?ID|PID|PATNR|PAT[-_ ]?NR|PATIENTENNUMMER|MRN)"
_KEYED = re.compile(_KEY + r"\s*[:=#]?\s*([A-Z0-9][A-Z0-9\-/.]{2,29})", re.I)


def _open(data: bytes) -> Image.Image:
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass
    return ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")


def decode(data: bytes) -> list[str]:
    """All barcode texts found in the image (empty list if none)."""
    img = _open(data)
    # phone photos are large; try the original first, then a downscaled copy (helps 1D codes)
    variants = [img]
    if max(img.size) > 1600:
        small = img.copy()
        small.thumbnail((1600, 1600))
        variants.append(small)
    texts: list[str] = []
    try:
        import zxingcpp
        for v in variants:
            texts = [r.text for r in zxingcpp.read_barcodes(v) if r.text]
            if texts:
                return texts
    except ImportError:
        pass
    try:                                   # fallback: QR via OpenCV
        import cv2
        import numpy as np
        ok, found, _, _ = cv2.QRCodeDetector().detectAndDecodeMulti(np.array(img)[:, :, ::-1])
        texts = [t for t in (found if ok else []) if t]
        if texts:
            return texts
    except Exception:
        pass
    try:                                   # fallback: DataMatrix via pylibdmtx
        from pylibdmtx.pylibdmtx import decode as dm
        texts = [r.data.decode("utf-8", "replace") for r in dm(variants[-1], timeout=3000)]
    except Exception:
        pass
    return texts


def extract_patient_id(text: str) -> str | None:
    """Patient ID from one barcode text, or None."""
    t = text.strip().replace("\x1d", "|")          # GS1 group separator
    if not t:
        return None
    # HL7 v2 PID segment: PID-3 (patient identifier list), first component
    m = re.search(r"(?:^|[\r\n|])PID\|[^|\r\n]*\|[^|\r\n]*\|([^|^\r\n]+)", t)
    if m:
        return m.group(1).strip()
    m = _KEYED.search(t)
    if m:
        return m.group(1).strip(".-/")
    # bare ID: the whole content is a single token
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\-/.]{2,29}", t) and re.search(r"\d", t):
        return t
    # structured but unlabelled: first long digit run (KIS IDs are typically 6-12 digits)
    m = re.search(r"(?<!\d)\d{6,12}(?!\d)", t)
    return m.group(0) if m else None


def patient_id_from_image(data: bytes) -> tuple[str | None, list[str]]:
    """(patient ID or None, raw barcode texts) for an uploaded photo."""
    texts = decode(data)
    for t in texts:
        if pid := extract_patient_id(t):
            return pid, texts
    return None, texts
