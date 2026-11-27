<div align="center">

<img src="assets/logo.svg" alt="" height="72">

# Get Well OCR

### From a bag of paper to a safe ER handover in minutes

**Healthcare Hackathon Bayern 2026 · Challenge #3 "From paper to PC"**

![Python](https://img.shields.io/badge/Python-3.12-0F5E7A?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-0F5E7A?logo=streamlit&logoColor=white)
![OCR](https://img.shields.io/badge/OCR-Tesseract%20%7C%20Mistral%20OCR%20%7C%20Azure%20DI-0F5E7A)
![LLM](https://img.shields.io/badge/LLM-Mistral%20Large%203%20(grounded)-0F5E7A)
![Offline](https://img.shields.io/badge/offline%20mode-Tesseract-2E7550)
![Data](https://img.shields.io/badge/data-fictional%20only-B4182D)

</div>

---

## 🚑 The problem

A patient arrives in the emergency room at night with a **bag full of paper**: discharge letters, an old medication plan, lab results, a fax from the GP. The doctor has minutes, not hours.

The critical facts are scattered: the **penicillin allergy** is only in a letter from 2022, the **blood thinner was switched**, and the nursing form says *"no allergies"*.

## 💡 What Get Well OCR does

> Photograph every page with a phone. Get Well OCR reads, sorts and cross-checks them, shows what is **dangerous** first, flags **contradictions**, and writes the ER handover. **Every line links to its source page.**

<table>
<tr>
<td width="50%"><img src="docs/img/overview.jpg" alt="ER overview with CAVE panel and reconciled medication"></td>
<td width="50%"><img src="docs/img/page_sources.jpg" alt="Source page with highlighted facts"></td>
</tr>
<tr>
<td align="center"><b>ER overview:</b> CAVE first, medication reconciled across all documents</td>
<td align="center"><b>Every fact is traceable:</b> highlighted on the original page</td>
</tr>
</table>

---

## 🔄 How it works

```mermaid
flowchart LR
    A["📱 Capture<br/>phone photos<br/>or PDF"] --> B["🧼 Clean<br/>orientation, lighting,<br/>noise, deskew"]
    B --> C["📖 Read<br/>Tesseract (offline)<br/>or Mistral OCR"]
    C --> Q{"🔍 Sharp and<br/>readable?"}
    Q -- "no" --> R["📸 Please retake"]
    Q -- "yes" --> D["🗂️ Classify<br/>rules + offline<br/>language model"]
    D --> E["💊 Extract<br/>meds, diagnoses,<br/>labs, CAVE"]
    E --> F["🔀 Merge<br/>newest wins,<br/>conflicts flagged"]
    F --> G["👩‍⚕️ Doctor<br/>confirms"]
    G --> L["✍️ Optional history text<br/>Mistral Large 3 from<br/>confirmed facts only"]
    L --> V{"🔎 Every number and<br/>date in the facts?"}
    V -- "no" --> W["⚠️ Flagged:<br/>not supported"]
    W --> L
    V -- "yes" --> A2["👩‍⚕️ Doctor<br/>approves text"]
    A2 --> H["📋 ER handover<br/>JSON · FHIR<br/>patient plan PDF"]
    G --> H

    style R fill:#FBEFF1,stroke:#B4182D,color:#14232E
    style W fill:#FBEFF1,stroke:#B4182D,color:#14232E
    style G fill:#EAF4EE,stroke:#2E7550,color:#14232E
    style A2 fill:#EAF4EE,stroke:#2E7550,color:#14232E
    style H fill:#E7F1F5,stroke:#0F5E7A,color:#14232E
```

| Step | What happens | Why it matters |
|---|---|---|
| 🧼 **Clean** | Turns sideways pages upright, evens out shadows, removes noise, straightens tilted photos | Bad phone photos are the normal case in an ER |
| 📖 **Read** | Tesseract on the laptop, or Mistral OCR (Azure, EU region): Mistral Large 3 reads the page image, much better on tables, handwriting and poor photos | Choose offline privacy or higher accuracy per case |
| 🔍 **Quality gate** | Blurry or unreadable pages are sent back: *"please retake"* | The system never guesses on pages it cannot read |
| 🗂️ **Classify** | Keyword rules **and** a small multilingual model (runs on a laptop) | When they disagree, the doctor is asked |
| 💊 **Extract** | Rules (regular expressions, offline) **or** Mistral Large 3: it understands the medical content, keeps what matters, and fixes OCR typos. Every fix and every implausible value is listed for the doctor and linked to its source line | The AI never changes a value silently. If it fails on a page, that page falls back to the rules |
| 🔀 **Merge** | One medication list from all documents: new, stopped, changed | Old plans don't overwrite new letters |
| ⚠️ **Conflicts** | Contradictions are shown, never silently resolved | *"Allergies: none"* vs. *"penicillin allergy"* |
| 👩‍⚕️ **Review** | Doctor confirms or corrects; every change is logged | Exports unlock only after confirmation |
| ✍️ **History text** | Mistral Large 3 turns the **confirmed** facts into a short history in doctor's-letter style. It never sees photos or raw OCR text, runs at temperature 0, and every number and date it writes is checked against the facts | The language model can phrase, not invent. Anything unsupported is flagged, and the doctor must approve the text |

---

## 📊 Results (fictional 20-page test case, Tesseract offline)

<table>
<tr><td>

| Metric | Result |
|---|---|
| 🎯 Critical facts found | **13 / 13** |
| 🗂️ Pages classified correctly | **19 / 19** |
| ⚠️ Document conflicts flagged | **6** (5 planted + 1) |
| 📸 Blurry page detected | **✓** retake requested |
| 📄 Harder case (handwriting, sideways pages) | **13 / 14** |

</td><td>

| Classifier | Pages correct |
|---|---|
| Keyword rules | 19 / 19 |
| Language model alone | 14 / 19 |
| **Hybrid (both)** | **19 / 19** |

<sub>The model has never seen our documents.<br/>Disagreements are shown to the doctor.</sub>

</td></tr>
</table>

### 🤖 Rules vs. AI extraction (same test case)

| OCR → extraction | Critical facts | Conflicts (5 planted) | AI corrections |
|---|---|---|---|
| Tesseract → rules | 13 / 13 | 7 | – |
| Tesseract → Mistral Large 3 | 13 / 13 | 6 | 32 (e.g. Bisoprolol "25mg" → 2,5 mg, INR "16" → 1,6) |
| Mistral OCR → Mistral Large 3 | 13 / 13 | **5** | 2 |

Reproduce with `python scripts/compare_extractors.py [--engine mistral]`.

### 🧪 Stress test: the 20-page case, deliberately damaged

<img src="docs/img/robustness.png" alt="Robustness chart: critical facts found and pages sent back for skew, fax and noise at damage levels 0 to 4">

Three kinds of damage (skew, noise, fax) at four levels each, from clean (0) to almost unreadable (4).

- **Skew and noise:** at least 9 of 13 critical facts are still found at the worst level.
- **Fax:** from level 3 on, **every page is sent back for a retake**, so no facts are read instead of wrong ones. The system stops rather than guessing.

---

## 🖥️ The app

<img src="docs/img/medication_review.jpg" alt="Medication review table">

Login first (see [Quick start](#-quick-start)). The **start screen** takes photos or PDFs, lets you choose the OCR engine (Tesseract or Mistral OCR), the extraction (*Auswertung*: rules or AI) and pick an earlier case. *Delete history* removes every uploaded case; the test cases stay.

| Tab | For |
|---|---|
| 🩺 **ER overview** | CAVE, safety warnings, AI corrections to check, conflicts to clarify, medication, diagnoses, contact person |
| 📄 **Pages** | All photos, document type per page, highlighted sources (Mistral OCR returns no positions: sources are listed as text instead) |
| 💊 **Medication** | Doctor reviews, corrects and confirms; correction log |
| 🧪 **Labs & findings** | Latest values with trend |
| 🗂️ **Documents** | Timeline, pages grouped into documents |
| ⬇️ **Export** | Optional history text by Mistral Large 3 (after all medication is confirmed), ER handover text (DE/EN), JSON, FHIR R4, CSV, patient plan PDF in 🇩🇪 🇬🇧 🇹🇷 🇨🇳 |

---

## 🚀 Quick start

```bash
git clone https://github.com/uromi06/get_well_OCR.git
cd get_well_OCR
./start.sh          # macOS / Linux
start.bat           # Windows (or double-click it)
```

That's it. On the first start the launcher sets up everything by itself, then opens **http://localhost:8501**:

1. finds Python 3.10 to 3.13 (prefers 3.12), or installs 3.12 (brew / winget / apt)
2. creates `.venv` and installs `requirements.txt` (later starts reinstall only when the file changed)
3. installs Tesseract with German (brew / winget / apt / dnf), or downloads missing language data into `.tessdata/`
4. uses the committed `.env`: login, Mistral keys and endpoints are already included

> 🔑 **Nothing to configure.** The login (`APP_USERNAME` / `APP_PASSWORD`) and the team keys for Mistral are in the committed [`.env`](.env). Mistral OCR, AI extraction and the AI history text work right after cloning. To use your own keys, edit `.env` (all options: [`.env.example`](.env.example)).

Later starts take a few seconds. Options: `--setup-only`, `--self-test` (also checks German OCR on a test page), `--port 8600`, `--no-browser`; anything else is passed to `streamlit run`. `python start.py` works on any OS too.

Pipeline and test scripts (after the first start):

```bash
source .venv/bin/activate              # Windows: .\.venv\Scripts\Activate.ps1
python scripts/process_case.py         # runs the test case, prints the scorecard
```

<details>
<summary><b>🔧 Requirements and options</b></summary>

- Python 3.12 and Tesseract 5 with the **German** language pack. `start.sh` / `start.bat` install both. Manual install on Windows: [UB Mannheim build](https://github.com/UB-Mannheim/tesseract/wiki)
- Login: `APP_USERNAME` and `APP_PASSWORD` in `.env` (required)
- Mistral on Azure AI Foundry (EU region, Sweden Central): `MISTRAL_API_KEY` and `MISTRAL_CHAT_ENDPOINT` are set in the committed `.env`. OCR uses Mistral Large 3 on the same endpoint; `MISTRAL_OCR_ENDPOINT` is only needed for a Mistral Document AI deployment
- Defaults in `.env`: `OCR_ENGINE=tesseract|mistral`, `EXTRACTOR=rules|llm`, `OCR_WORKERS=2` (both modes can also be switched in the sidebar)
- Optional: Azure Document Intelligence (EU region), endpoint and key in `.env`
- The classifier model (`multilingual-e5-small`, ~120 MB) downloads once, then runs offline

```powershell
python scripts\process_case.py --classifier rules|model|hybrid
python scripts\process_case.py --engine mistral|azure
python scripts\process_case.py --pages data\cases\case01_hard\pages_photo
python scripts\compare_extractors.py --engine tesseract|mistral
python scripts\make_stress_set.py ; python scripts\run_stress.py --quick
```
</details>

<details>
<summary><b>📁 Project structure</b></summary>

```
get_well_OCR/
├── start.sh / start.bat    One-command launcher: sets up the environment, starts the app
├── app.py                  Streamlit entry point (login gate, one screen)
├── api.py                  HTTP API (FastAPI): upload pages, get the text back
├── assets/                 Logo and wordmark
├── views/                  Screens (case workspace, UI components)
├── src/                    Pipeline: no UI code, reusable by the API
│   ├── preprocess.py       Image cleanup (orientation, lighting, noise, deskew)
│   ├── extract.py          OCR: Tesseract, Mistral OCR or Azure Document Intelligence
│   ├── mistral.py          Mistral OCR and Mistral Large 3 calls (cached for offline demos)
│   ├── llm_extract.py      AI extraction with Mistral Large 3: facts + flagged corrections per page
│   ├── case.py             Multi-page pipeline: quality, classify, extract, merge
│   ├── doc_classifier.py   Offline language model for document types
│   ├── history.py          AI-written history from confirmed facts, with grounding check
│   ├── report.py           ER handover text
│   ├── export.py           JSON, CSV, FHIR, patient plan PDF
│   ├── store.py            Case folders, uploads, doctor review, delete history
│   └── auth.py             Login for the web app
├── scripts/                Run, evaluate, generate test data
├── deploy/                 CD to AWS (GitHub Actions → ECR → EC2), see deploy/CD.md
└── data/cases/             Fictional test cases + answer files (see its README)
```
</details>

<details>
<summary><b>🧪 Test data</b></summary>

All patients are **fictional** (every page is marked *FIKTIV*). Main case: *Helga Beispiel, 78*, shortness of breath, 20 pages across 15 documents, with planted traps: an outdated medication plan, a false *"no allergies"*, a blurry duplicate, an irrelevant insurance letter. Details in [`data/cases/README.md`](data/cases/README.md).
</details>

---

## 🔒 Privacy and safety by design

| Mode | What leaves the laptop |
|---|---|
| 💻 **Tesseract (offline)** | Nothing. OCR, classification and extraction run locally |
| 🇪🇺 **Mistral OCR** | Page images, sent to Mistral Large 3 on Azure AI Foundry in an EU region (Sweden Central) |
| 🤖 **AI extraction** | The OCR text lines of each page, sent to Mistral Large 3 in the same EU region |
| ✍️ **AI history text** | Only the doctor-confirmed facts (no photos, no raw text), sent to Mistral Large 3 in the same EU region |

- 🧪 **Fictional data only** in this repository and in the cloud modes
- 🔑 The web app opens **only after login**
- 🗃️ Mistral results are cached locally, so the demo also works without a connection
- 🗑️ One click **deletes every uploaded case** (photos, OCR, results, review)
- 👩‍⚕️ **Nothing is exported** before a doctor has confirmed it, and the AI history text must be approved separately

---

## ☁️ Deployment

Every push to `main` builds a Docker image, smoke-tests it and, after manual approval, deploys it to AWS EC2 (API on port 8000, Streamlit app with login on port 8501), with automatic rollback. Setup and details: [`deploy/CD.md`](deploy/CD.md).

---

## 👥 Team

| | Name | GitHub | Role |
|---|---|---|---|
| 🩺 | **Maxwell** | | ER doctor, clinical requirements |
| 🧠 | **Urmi** | [@uromi06](https://github.com/uromi06) | AI pipeline |
| 👤 | **Peter** | | *role* |
| 👤 | **Lennart** | [@KTV02](https://github.com/KTV02) | *role* |
| 👤 | **Hoang** | [@HoangStud13](https://github.com/HoangStud13) | *role* |
| 👤 | **Subhangee** | | *role* |

<div align="center">
<sub>Made with ☕ at the Healthcare Hackathon Bayern 2026, Munich</sub>
</div>
