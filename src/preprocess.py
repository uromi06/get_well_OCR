"""Image cleanup before OCR. This is where your imaging background shines.

Each step is a small function, so you can switch steps on and off and measure
how much each one helps (the ablation study for your pitch).
"""
from pathlib import Path

import cv2
import numpy as np

ALL_STEPS = ("gray", "page", "orient", "flatten", "denoise", "contrast", "upscale", "deskew")


# ------------------------------------------------------------------ page detection (phone photos)
# A phone photo shows the sheet plus table, hands, other papers. Find the sheet's four corners,
# cut it out and straighten the perspective ("scan" look). If no clear sheet is found, the photo
# is left untouched: a wrong crop would cut off text, which is worse than no crop.

PAGE_MIN_AREA = 0.25      # sheet must cover at least 25 % of the photo
PAGE_FULL_FRAME = 0.92    # sheet already fills the photo: nothing to crop
PAGE_DETECT_SIZE = 1000   # detection runs on a copy this long (fast, ignores small text)


def _order_corners(pts: np.ndarray) -> np.ndarray:
    """top-left, top-right, bottom-right, bottom-left"""
    pts = pts.reshape(4, 2).astype(np.float32)
    s, d = pts.sum(axis=1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]],
                    dtype=np.float32)


def _quad_ok(quad: np.ndarray, img_area: float) -> bool:
    if quad is None or len(quad) != 4 or not cv2.isContourConvex(quad.astype(np.int32)):
        return False
    area = cv2.contourArea(quad.astype(np.float32))
    if area < PAGE_MIN_AREA * img_area:
        return False
    tl, tr, br, bl = _order_corners(quad)
    w = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    h = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    ratio = max(w, h) / max(min(w, h), 1)
    return ratio <= 3.0                       # A4 is 1.41; receipts are longer, but not 5:1


def _best_quad(contours, img_area: float):
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        peri = cv2.arcLength(c, True)
        for eps in (0.02, 0.03, 0.05):        # corners hidden by fingers/shadows need a looser fit
            approx = cv2.approxPolyDP(c, eps * peri, True)
            if len(approx) == 4 and _quad_ok(approx, img_area):
                return approx.reshape(4, 2)
    return None


def _side_contrast(lab: np.ndarray, quad: np.ndarray) -> float:
    """Weakest of the four sides: how different is the photo just inside vs. just outside the side.

    A real sheet edge has paper on one side and table on the other, on all four sides. A wrong
    quad (e.g. a shadow line across the page) has paper on both sides of at least one side.
    Sides that run along the photo border (outside is off-photo) are not judged.
    """
    h, w = lab.shape[:2]
    centre = quad.mean(axis=0)
    d = 0.015 * max(h, w)
    weakest = None
    for i in range(4):
        p, q = quad[i], quad[(i + 1) % 4]
        diffs = []
        for t in np.linspace(0.1, 0.9, 15):
            pt = p + t * (q - p)
            n = np.array([-(q - p)[1], (q - p)[0]], dtype=np.float32)
            n /= max(np.linalg.norm(n), 1e-6)
            if np.dot(centre - pt, n) < 0:
                n = -n                          # n points into the sheet
            a, b = pt + n * d, pt - n * d
            if not (0 <= b[0] < w and 0 <= b[1] < h):
                continue
            a = np.clip(a, 0, [w - 1, h - 1]).astype(int)
            b = b.astype(int)
            diffs.append(float(np.linalg.norm(lab[a[1], a[0]].astype(float) - lab[b[1], b[0]].astype(float))))
        if len(diffs) >= 5:
            med = float(np.median(diffs))
            weakest = med if weakest is None else min(weakest, med)
    return weakest if weakest is not None else 0.0


PAGE_MIN_CONTRAST = 18    # weakest side must differ this much (Lab units) between inside and outside


def find_page(img: np.ndarray):
    """Four corners of the sheet in the photo (in full-size pixels) and the detector used, or (None, None).

    Several detectors propose a four-cornered outline on a small copy (edges at two sensitivities,
    bright paper area by brightness and by low colour). A proposal only counts if all four sides
    are real edges (paper inside, something else outside). Of those, the largest wins.
    """
    h, w = img.shape[:2]
    scale = min(PAGE_DETECT_SIZE / max(h, w), 1.0)
    small = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else img
    if small.ndim == 2:
        small = cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)
    area = small.shape[0] * small.shape[1]
    gray = to_gray(small)
    # text would make many small edges: close it into the paper, keep only the outline
    solid = cv2.morphologyEx(cv2.GaussianBlur(gray, (5, 5), 0), cv2.MORPH_CLOSE,
                             np.ones((9, 9), np.uint8), iterations=2)
    lab = cv2.cvtColor(cv2.GaussianBlur(small, (9, 9), 0), cv2.COLOR_BGR2LAB)

    masks = []
    for lo, hi in ((20, 60), (50, 150)):
        e = cv2.dilate(cv2.Canny(solid, lo, hi), np.ones((3, 3), np.uint8), iterations=2)
        masks.append(("edges", e))
    masks.append(("brightness", cv2.threshold(solid, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    low_colour = ((hsv[..., 1] < 50) & (solid > cv2.threshold(solid, 0, 255, cv2.THRESH_OTSU)[0] * 0.8))
    masks.append(("colour", low_colour.astype(np.uint8) * 255))

    best = None
    for name, m in masks:
        if name != "edges":
            m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8), iterations=2)
            m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        quad = _best_quad(cnts, area)
        if quad is None and cnts and name != "edges":   # curled corners: the min-area box
            big = max(cnts, key=cv2.contourArea)
            box = cv2.boxPoints(cv2.minAreaRect(big))
            quad = box if _quad_ok(box, area) else None
        if quad is None:
            continue
        quad = _order_corners(quad)
        if _side_contrast(lab, quad) < PAGE_MIN_CONTRAST:
            continue
        size = cv2.contourArea(quad)
        if best is None or size > best[0]:
            best = (size, quad, name)
    if best is None:
        return None, None
    return best[1] / scale, best[2]


def crop_to_page(img: np.ndarray) -> tuple[np.ndarray, str]:
    """Cut the sheet out of a phone photo and straighten it. Returns (image, log text)."""
    corners, method = find_page(img)
    if corners is None:
        return img, "page edges not found (photo kept as is)"
    h, w = img.shape[:2]
    share = cv2.contourArea(corners) / float(h * w)
    if share >= PAGE_FULL_FRAME:
        return img, f"page fills the photo ({share:.0%}), no crop"
    tl, tr, br, bl = corners
    out_w = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    out_h = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    target = np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(corners, target)
    warped = cv2.warpPerspective(img, m, (out_w, out_h), flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_REPLICATE)
    return warped, f"page cropped + straightened ({method}, {share:.0%} of photo)"


def load_image(path: str | Path, page: int = 0, dpi: int = 300) -> np.ndarray:
    """Load a PNG/JPG, or render one page of a PDF. Returns a BGR image."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(path))
        pil = pdf[page].render(scale=dpi / 72).to_pil().convert("RGB")
        return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Could not read image: {path}")
    return img


def to_gray(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def denoise(gray: np.ndarray, strength: float = 10) -> np.ndarray:
    """Non-local means denoising: removes speckle/fax noise but keeps letter edges."""
    return cv2.fastNlMeansDenoising(gray, None, h=strength)


def enhance_contrast(gray: np.ndarray) -> np.ndarray:
    """CLAHE: local contrast boost, helps with faded or unevenly lit photos."""
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def estimate_skew(gray: np.ndarray, max_angle: float = 10.0, step: float = 0.25) -> float:
    """Find the rotation that makes text lines most horizontal.

    Tries angles and picks the one whose horizontal projection profile is
    sharpest (highest variance), the same idea as optimising a sharpness metric.
    """
    small = cv2.resize(gray, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    binary = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    h, w = binary.shape
    center = (w / 2, h / 2)
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-max_angle, max_angle + step, step):
        m = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(binary, m, (w, h), flags=cv2.INTER_NEAREST)
        score = float(np.var(rotated.sum(axis=1)))
        if score > best_score:
            best_angle, best_score = float(angle), score
    return best_angle


def deskew(gray: np.ndarray) -> tuple[np.ndarray, float]:
    angle = estimate_skew(gray)
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    fixed = cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC,
                           borderMode=cv2.BORDER_CONSTANT, borderValue=255)
    return fixed, angle


def estimate_noise(gray: np.ndarray) -> float:
    """Noise standard deviation (Immerkaer 1996, fast Laplacian-based estimate).

    Clean scans give about 0-2, phone photos 2-6, heavy noise 15+.
    """
    kernel = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=float)
    h, w = gray.shape
    response = cv2.filter2D(gray.astype(float), -1, kernel)[1:-1, 1:-1]
    return float(np.abs(response).sum() * np.sqrt(0.5 * np.pi) / (6 * (w - 2) * (h - 2)))


def _text_score(gray: np.ndarray) -> float:
    """Quick read on a small copy: sum of confidences of real words (higher = upright)."""
    import pytesseract
    small = cv2.resize(gray, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    d = pytesseract.image_to_data(small, config="--psm 3", output_type=pytesseract.Output.DICT)
    return sum(float(c) for t, c in zip(d["text"], d["conf"]) if len(t.strip()) >= 3 and float(c) > 50)


def fix_orientation(gray: np.ndarray) -> tuple[np.ndarray, int]:
    """Turn sideways or upside-down pages upright (phone held upright for a landscape page).

    Deskew only handles small angles; this handles 90 / 180 / 270 degrees.
    1. Tesseract's orientation detection (OSD) suggests a rotation (fast, full resolution).
    2. Confident (>= 2): turn. Unsure: a quick read of both versions decides.
    Returns the image and the rotation applied (0 if none).
    """
    try:
        import re
        import pytesseract
        from . import config
        if config.TESSERACT_CMD and Path(config.TESSERACT_CMD).exists():
            pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
        osd = pytesseract.image_to_osd(gray, config="--psm 0 -c min_characters_to_try=30")
        rotate = int(re.search(r"Rotate: (\d+)", osd).group(1))
        conf = float(re.search(r"Orientation confidence: ([\d.]+)", osd).group(1))
        if rotate == 0:
            return gray, 0
        turn = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}[rotate]
        turned = cv2.rotate(gray, turn)
        if conf >= 2.0 or _text_score(turned) > 1.1 * _text_score(gray):
            return turned, rotate
    except Exception:            # no OSD data, too little text, Tesseract missing: leave as is
        pass
    return gray, 0


def flatten_illumination(gray: np.ndarray) -> np.ndarray:
    """Flat-field correction: divide by the smooth background (shadows, lamp gradients).

    Same idea as bias-field correction in MRI. Phone photos are brighter in one
    corner than another; Tesseract then loses whole table blocks. Dividing by a
    heavily smoothed copy of the page makes the paper evenly white.
    """
    small = cv2.resize(gray, (0, 0), fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    background = cv2.resize(cv2.medianBlur(small, 31), (gray.shape[1], gray.shape[0]),
                            interpolation=cv2.INTER_LINEAR)
    flat = gray.astype(np.float32) / np.maximum(background.astype(np.float32), 1.0) * 235.0
    return np.clip(flat, 0, 255).astype(np.uint8)


def upscale(gray: np.ndarray, factor: float = 2.0) -> np.ndarray:
    """Bigger letters help OCR on low-resolution images (fax, small photos)."""
    return cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)


# Tuned on the synthetic robustness set (see run_evaluation.py)
NOISE_SKIP = 3.0        # below this sigma: image is clean, don't denoise
NOISE_NO_CONTRAST = 5.0  # above this sigma: CLAHE amplifies noise, skip it
UPSCALE_BELOW = 3000     # upscale 2x if the page is shorter than this (in pixels)


def preprocess(img: np.ndarray, steps=ALL_STEPS) -> tuple[np.ndarray, list[str]]:
    """Run the chosen cleanup steps in order. Returns the image and a log.

    Adaptive: each step first measures the image and only acts when it helps.
    v1 lesson: a fixed denoise + contrast boost destroyed noisy pages, because
    CLAHE re-amplified the leftover noise.
    """
    log = []
    if "page" in steps:                      # on the colour photo: paper vs. table is easiest in colour
        img, msg = crop_to_page(img)
        log.append(msg)
    out = to_gray(img)
    log.append("gray")
    sigma = estimate_noise(out)
    log.append(f"noise sigma {sigma:.1f}")
    if "flatten" in steps:
        out = flatten_illumination(out)
        log.append("flatten lighting")
    if "orient" in steps:
        out, turned = fix_orientation(out)
        if turned:
            log.append(f"turned upright ({turned} deg)")
    if "denoise" in steps:
        if sigma >= NOISE_SKIP:
            strength = max(10.0, 0.9 * sigma)
            out = denoise(out, strength=strength)
            log.append(f"denoise (h={strength:.0f})")
        else:
            log.append("denoise skipped (clean)")
    if "contrast" in steps:
        if "flatten" in steps:
            log.append("contrast skipped (already flattened)")
        elif sigma < NOISE_NO_CONTRAST:
            out = enhance_contrast(out)
            log.append("contrast")
        else:
            log.append("contrast skipped (noisy)")
    if "upscale" in steps and out.shape[0] < UPSCALE_BELOW:
        out = upscale(out)
        log.append("upscale 2x")
    if "deskew" in steps:
        out, angle = deskew(out)
        log.append(f"deskew ({angle:+.2f} deg)")
    return out, log