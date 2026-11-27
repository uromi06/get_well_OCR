"""Central settings: folder paths and values read from the .env file."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# Folders
DATA_DIR = ROOT / "data"
SYNTHETIC_DIR = DATA_DIR / "synthetic"      # clean generated documents (PDF)
DEGRADED_DIR = DATA_DIR / "degraded"        # blurred / skewed / fax-like versions (PNG)
GROUND_TRUTH_DIR = DATA_DIR / "ground_truth"  # answer files (JSON), one per document
CACHE_DIR = ROOT / "cache"                  # saved OCR responses -> offline demo
OUTPUT_DIR = ROOT / "outputs"
FIGURE_DIR = OUTPUT_DIR / "figures"

# OCR
OCR_ENGINE = os.getenv("OCR_ENGINE", "tesseract").lower()
# Only used if the file really exists; otherwise Tesseract is looked up on PATH
_tess = os.getenv("TESSERACT_CMD", "").strip()
TESSERACT_CMD = _tess if _tess and Path(_tess).is_file() else ""
TESSERACT_LANG = "deu+eng"
# Pages read at the same time (one Tesseract process each, Tesseract itself uses one core per page).
# Match it to the CPU cores; 2 fits the t3.large.
OCR_WORKERS = max(1, int(os.getenv("OCR_WORKERS", "2") or 2))

# Mistral on Azure AI Foundry (EU region, provided by the hackathon)
#   OCR:  Mistral Document AI, returns Markdown per page
#   Chat: Mistral Large 3 (OpenAI-compatible chat completions), writes the patient history text
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "").strip()
MISTRAL_CHAT_ENDPOINT = os.getenv("MISTRAL_CHAT_ENDPOINT", "").strip()
MISTRAL_CHAT_MODEL = os.getenv("MISTRAL_CHAT_MODEL", "Mistral-Large-3").strip()
MISTRAL_OCR_ENDPOINT = os.getenv("MISTRAL_OCR_ENDPOINT", "").strip()
MISTRAL_OCR_MODEL = os.getenv("MISTRAL_OCR_MODEL", "mistral-document-ai-2512").strip()
MISTRAL_OCR_KEY = os.getenv("MISTRAL_OCR_KEY", "").strip() or MISTRAL_API_KEY

AZURE_DI_ENDPOINT = os.getenv("AZURE_DI_ENDPOINT", "")
AZURE_DI_KEY = os.getenv("AZURE_DI_KEY", "")

# Review: fields below this confidence are flagged for the doctor to check
LOW_CONFIDENCE = 0.80

# Document classification: "rules" (keywords), "model" (embedding model), "hybrid" (both, flag disagreement)
CLASSIFIER = os.getenv("CLASSIFIER", "hybrid").lower()
CLASSIFIER_BACKEND = os.getenv("CLASSIFIER_BACKEND", "e5").lower()      # e5 | tfidf
CLASSIFIER_MODEL = os.getenv("CLASSIFIER_MODEL", "intfloat/multilingual-e5-small")

for _d in (SYNTHETIC_DIR, DEGRADED_DIR, GROUND_TRUTH_DIR, CACHE_DIR, FIGURE_DIR):
    _d.mkdir(parents=True, exist_ok=True)
