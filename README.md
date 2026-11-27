# Get Well OCR

**From a stack of paper to an ER-ready overview in minutes.**
Healthcare Hackathon Bayern, Munich 2026 · Challenge #3 (TUM Venture Labs & Klinikum rechts der Isar)

Patients arrive in the emergency room with bags of paper: discharge letters, medication plans, lab reports, faxes. Get Well OCR lets staff photograph all pages with a phone, reads and sorts them, extracts medications, diagnoses, allergies and lab values, lets the doctor confirm everything, and produces a short ER summary where every line links back to its source page.

> **Data rule:** fictional or anonymised documents only. No real patient data in this repo.

## Pipeline

```
Capture (phone photos, many pages)
  → Clean (deskew, denoise, upscale, quality check)
  → Read (Azure Document Intelligence, EU region; Tesseract offline fallback)
  → Classify & group pages into documents
  → Extract (medications, diagnoses, labs, allergies, dates)
  → Merge across documents (current medication, conflicts, timeline)
  → Doctor review (flags, corrections)
  → ER summary with sources · JSON · FHIR · patient plan PDF (DE/EN/TR/ZH)
```

## Quick start (Windows)

```powershell
.\setup_windows.ps1             # creates .venv, installs packages, creates .env
python scripts\check_setup.py   # everything should say [ OK ]
streamlit run app.py            # http://localhost:8501
```

### HTTP API

```powershell
uvicorn api:app --port 8000     # docs: http://localhost:8000/docs
curl.exe -F "files=@page1.jpg" -F "files=@page2.jpg" http://localhost:8000/ocr
```

`POST /ocr` takes one or more photos/PDFs (`files`, multipart, in page order; optional `engine` = `tesseract` | `azure`)
and returns the extracted text: `text` (all pages) plus per page `text`, `lines` (with confidence and position) and `quality`.
Nothing is stored. `GET /health` for monitoring.

Put the Azure endpoint and key in `.env` (never commit it).

## Test data

`data/cases/case01/` is a **fictional** 20-page ER case (78-year-old patient, shortness of breath) with
`case01_answers.json` (13 critical facts, 5 conflicts, 4 traps) for scoring, and
`case01_mock_api.json`, the response format the app frontend builds against.
Regenerate with `python scripts\generate_case.py`.

## Folder layout

| Path | What |
|---|---|
| `app.py` | Streamlit prototype |
| `src/` | Pipeline modules (preprocess, extract, parse, review, export, schema) |
| `scripts/` | Setup check, case generator, cleanup comparison |
| `data/cases/` | Fictional test cases |
| `data/private/` | Git-ignored, never commit |

## Team

[Names and roles]
