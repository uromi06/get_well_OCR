"""Mistral models on Azure AI Foundry: OCR (Document AI) and chat (Mistral Large 3).

Both are plain HTTPS calls with the standard library, so no extra package is needed.
Endpoints, model names and the key come from .env (see .env.example). Results are cached
in cache/, so a page or a prompt that was sent once works again offline (live demo).

Data rule: fictional or anonymised documents only. The endpoint is in an EU region
(Sweden Central), nothing is stored on our side except the local cache.
"""
from __future__ import annotations

import base64
import hashlib
import json
import urllib.error
import urllib.request

import cv2
import numpy as np

from . import config


class MistralError(RuntimeError):
    pass


def _post(url: str, key: str, payload: dict, timeout: int = 120) -> dict:
    if not url or not key:
        raise MistralError("Mistral endpoint or key missing in .env (MISTRAL_*_ENDPOINT, MISTRAL_API_KEY).")
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST", headers={
        "Content-Type": "application/json",
        # Azure AI Foundry accepts either header, depending on the deployment type: send both
        "Authorization": f"Bearer {key}",
        "api-key": key,
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        raise MistralError(f"Mistral returned HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise MistralError(f"Mistral not reachable: {e.reason}") from e


def ocr_available() -> bool:
    return bool(config.MISTRAL_OCR_ENDPOINT and config.MISTRAL_OCR_KEY)


def chat_available() -> bool:
    return bool(config.MISTRAL_CHAT_ENDPOINT and config.MISTRAL_API_KEY)

# ------------------------------------------------------------------ OCR

def _jpeg_data_uri(img: np.ndarray) -> str:
    # the cleaned page is large (upscaled 2x): shrink to ~2000 px, JPEG keeps uploads small
    h, w = img.shape[:2]
    scale = min(1.0, 2200 / max(h, w))
    if scale < 1.0:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise MistralError("Could not encode the page image.")
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def ocr_markdown(img: np.ndarray, use_cache: bool = True) -> str:
    """Send one page image to Mistral Document AI, return its Markdown text."""
    cache = config.CACHE_DIR / f"mistral_ocr_{hashlib.sha1(img.tobytes()).hexdigest()[:16]}.json"
    if use_cache and cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
    else:
        data = _post(config.MISTRAL_OCR_ENDPOINT, config.MISTRAL_OCR_KEY, {
            "model": config.MISTRAL_OCR_MODEL,
            "document": {"type": "image_url", "image_url": _jpeg_data_uri(img)},
            "include_image_base64": False,
        })
        cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    pages = data.get("pages") or []
    if not pages:
        raise MistralError("Mistral OCR returned no pages: " + json.dumps(data)[:300])
    return "\n".join(p.get("markdown", "") for p in pages)


def markdown_to_lines(md: str) -> list[str]:
    """Markdown -> plain text lines our extraction rules understand.

    '## Diagnosen' -> 'Diagnosen', '**Kalium**' -> 'Kalium', table rows '| a | b |' -> 'a | b',
    table separator rows and images are dropped, list bullets are kept.
    """
    out = []
    for raw in md.splitlines():
        line = raw.strip()
        if not line or line.startswith("![") or set(line) <= set("|-: "):
            continue
        line = line.lstrip("#").strip()
        line = line.replace("**", "").replace("__", "")
        if line.startswith("|"):
            line = " | ".join(c.strip() for c in line.strip("|").split("|"))
        out.append(line)
    return out

# ------------------------------------------------------------------ chat

def chat(messages: list[dict], temperature: float = 0.0, max_tokens: int = 700, use_cache: bool = True) -> str:
    key = hashlib.sha1(json.dumps([config.MISTRAL_CHAT_MODEL, messages, temperature], ensure_ascii=False)
                       .encode("utf-8")).hexdigest()[:16]
    cache = config.CACHE_DIR / f"mistral_chat_{key}.json"
    if use_cache and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))["text"]
    data = _post(config.MISTRAL_CHAT_ENDPOINT, config.MISTRAL_API_KEY, {
        "model": config.MISTRAL_CHAT_MODEL, "messages": messages,
        "temperature": temperature, "max_tokens": max_tokens,
    })
    try:
        text = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as e:
        raise MistralError("Unexpected chat response: " + json.dumps(data)[:300]) from e
    cache.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")
    return text
