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
import re
import time
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
    attempts = 3                      # timeouts, rate limits and 5xx are retried; other errors fail at once
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            if (e.code == 429 or e.code >= 500) and attempt < attempts:
                time.sleep(2 * attempt)
                continue
            raise MistralError(f"Mistral returned HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            if isinstance(e.reason, TimeoutError) and attempt < attempts:
                continue
            raise MistralError(f"Mistral not reachable: {e.reason}") from e
        except (TimeoutError, ConnectionError) as e:      # read timeout / reset after the connection was open
            if attempt < attempts:
                continue
            raise MistralError(f"Mistral did not answer in time ({type(e).__name__}).") from e
        except ValueError as e:
            raise MistralError("Mistral returned invalid JSON.") from e


def ocr_available() -> bool:
    # Document AI if configured, else Mistral Large 3 reads the page image via the chat endpoint
    return bool(config.MISTRAL_OCR_ENDPOINT and config.MISTRAL_OCR_KEY) or chat_available()


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


VISION_OCR_PROMPT = (
    "Transkribiere den gesamten Text dieser Dokumentseite exakt als Markdown, Tabellen als Markdown-Tabellen, "
    "Überschriften mit #. Übernimm jedes Zeichen so, wie es auf der Seite steht: Dezimalkommas bleiben Kommas "
    "(4,8 nicht 4.8), Datumsangaben, Einheiten, Abkürzungen und Schreibfehler unverändert. Nichts hinzufügen, "
    "nichts korrigieren, nichts zusammenfassen, keine Kommentare. Unleserliches als [unleserlich]."
)


def _ocr_document_ai(img: np.ndarray) -> str:
    data = _post(config.MISTRAL_OCR_ENDPOINT, config.MISTRAL_OCR_KEY, {
        "model": config.MISTRAL_OCR_MODEL,
        "document": {"type": "image_url", "image_url": _jpeg_data_uri(img)},
        "include_image_base64": False,
    })
    pages = data.get("pages") or []
    if not pages:
        raise MistralError("Mistral OCR returned no pages: " + json.dumps(data)[:300])
    return "\n".join(p.get("markdown", "") for p in pages)


def _ocr_vision(img: np.ndarray) -> str:
    """Mistral Large 3 reads the page image (same endpoint and key as the chat features)."""
    data = _post(config.MISTRAL_CHAT_ENDPOINT, config.MISTRAL_API_KEY, {
        "model": config.MISTRAL_CHAT_MODEL, "temperature": 0, "max_tokens": 4000,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": VISION_OCR_PROMPT},
            {"type": "image_url", "image_url": {"url": _jpeg_data_uri(img)}}]}],
    }, timeout=90)
    try:
        text = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        raise MistralError("Unexpected OCR response: " + json.dumps(data)[:300]) from e
    return re.sub(r"^```(?:markdown|md)?\s*|\s*```$", "", text)      # drop a code fence if the model adds one


def ocr_markdown(img: np.ndarray, use_cache: bool = True) -> str:
    """Send one page image to Mistral, return its Markdown text.

    Uses Mistral Document AI when MISTRAL_OCR_ENDPOINT is set and that deployment exists; otherwise
    (or if it answers 'not found') Mistral Large 3 reads the image via MISTRAL_CHAT_ENDPOINT + MISTRAL_API_KEY.
    """
    cache = config.CACHE_DIR / f"mistral_ocr_{hashlib.sha1(img.tobytes()).hexdigest()[:16]}.json"
    if use_cache and cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        if "markdown" in data:                                   # vision / new cache format
            return data["markdown"]
        return "\n".join(p.get("markdown", "") for p in data.get("pages") or [])   # old Document AI cache
    md, how = None, "vision"
    if config.MISTRAL_OCR_ENDPOINT and config.MISTRAL_OCR_KEY:
        try:
            md, how = _ocr_document_ai(img), "document-ai"
        except MistralError as e:
            # no Document AI deployment on this resource -> fall back to Mistral Large 3
            if not chat_available() or not re.search(r"HTTP 404|DeploymentNotFound|NOT FOUND", str(e), re.I):
                raise
    if md is None:
        md = _ocr_vision(img)
    cache.write_text(json.dumps({"markdown": md, "via": how}, ensure_ascii=False), encoding="utf-8")
    return md


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

def chat(messages: list[dict], temperature: float = 0.0, max_tokens: int = 700, use_cache: bool = True,
         json_mode: bool = False) -> str:
    key = hashlib.sha1(json.dumps([config.MISTRAL_CHAT_MODEL, messages, temperature] + (["json"] if json_mode else []),
                                  ensure_ascii=False)
                       .encode("utf-8")).hexdigest()[:16]
    cache = config.CACHE_DIR / f"mistral_chat_{key}.json"
    if use_cache and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))["text"]
    payload = {"model": config.MISTRAL_CHAT_MODEL, "messages": messages,
               "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    data = _post(config.MISTRAL_CHAT_ENDPOINT, config.MISTRAL_API_KEY, payload)
    try:
        text = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as e:
        raise MistralError("Unexpected chat response: " + json.dumps(data)[:300]) from e
    cache.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")
    return text
