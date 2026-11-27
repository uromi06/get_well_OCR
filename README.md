<div align="center">

# 🩺 Get Well OCR

### From a bag of paper to a safe ER handover in minutes

**Healthcare Hackathon Bayern 2026 · Challenge #3 "From paper to PC"**

![Python](https://img.shields.io/badge/Python-3.12-0F5E7A?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-0F5E7A?logo=streamlit&logoColor=white)
![OCR](https://img.shields.io/badge/OCR-Tesseract%20%7C%20Azure%20DI-0F5E7A)
![Offline](https://img.shields.io/badge/AI-runs%20offline-2E7550)
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
    B --> C["📖 Read<br/>Tesseract or<br/>Azure DI"]
    C --> Q{"🔍 Sharp and<br/>readable?"}
    Q -- "no" --> R["📸 Please retake"]
    Q -- "yes" --> D["🗂️ Classify<br/>rules + offline<br/>language model"]
    D --> E["💊 Extract<br/>meds, diagnoses,<br/>labs, CAVE"]
    E --> F["🔀 Merge<br/>newest wins,<br/>conflicts flagged"]
    F --> G["👩‍⚕️ Doctor<br/>confirms"]
    G --> H["📋 ER handover<br/>JSON · FHIR<br/>patient plan PDF"]

    style R fill:#FBEFF1,stroke:#B4182D,color:#14232E
    style G fill:#EAF4EE,stroke:#2E7550,color:#14232E
    style H fill:#E7F1F5,stroke:#0F5E7A,color:#14232E
```

| Step | What happens | Why it matters |
|---|---|---|
| 🧼 **Clean** | Turns sideways pages upright, evens out shadows, removes noise, straightens tilted photos | Bad phone photos are the normal case in an ER |
| 🔍 **Quality gate** | Blurry or unreadable pages are sent back: *"please retake"* | The system never guesses on pages it cannot read |
| 🗂️ **Classify** | Keyword rules **and** a small multilingual model (runs on a laptop) | When they disagree, the doctor is asked |
| 🔀 **Merge** | One medication list from all documents: new, stopped, changed | Old plans don't overwrite new letters |
| ⚠️ **Conflicts** | Contradictions are shown, never silently resolved | *"Allergies: none"* vs. *"penicillin allergy"* |
| 👩‍⚕️ **Review** | Doctor confirms or corrects; every change is logged | Exports unlock only after confirmation |

---

## 📊 Results (fictional 20-page test case)

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

### 🧪 Stress test: 480 deliberately damaged pages

<img src="docs/img/robustness.png" alt="Robustness chart: facts found and pages sent back per damage type and level">

Six kinds of damage (blur, noise, skew, shadow, WhatsApp compression, fax) at four levels each. **Shadows and compression barely matter.** Heavy blur and fax are **sent back for a retake** instead of producing silent mistakes.

---

## 🖥️ The app

<img src="docs/img/medication_review.png" alt="Medication review table">

| Tab | For |
|---|---|
| 🩺 **ER overview** | CAVE, safety warnings, conflicts to clarify, medication, diagnoses, contact person |
| 📄 **Pages** | All photos, document type per page, highlighted sources |
| 💊 **Medication** | Doctor reviews, corrects and confirms; correction log |
| 🧪 **Labs & findings** | Latest values with trend |
| 🗂️ **Documents** | Timeline, pages grouped into documents |
| ⬇️ **Export** | ER handover text (DE/EN), JSON, FHIR R4, CSV, patient plan PDF in 🇩🇪 🇬🇧 🇹🇷 🇨🇳 |

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
4. creates `.env` from `.env.example`

Later starts take a few seconds. Options: `--setup-only`, `--self-test` (also checks German OCR on a test page), `--port 8600`, `--no-browser`; anything else is passed to `streamlit run`. `python start.py` works on any OS too.

Pipeline and test scripts (after the first start):

```bash
source .venv/bin/activate              # Windows: .\.venv\Scripts\Activate.ps1
python scripts/process_case.py         # runs the test case, prints the scorecard
```

<details>
<summary><b>🔧 Requirements and options</b></summary>

- Python 3.12 and Tesseract 5 with the **German** language pack. `start.sh` / `start.bat` install both. Manual install on Windows: [UB Mannheim build](https://github.com/UB-Mannheim/tesseract/wiki)
- Optional: Azure Document Intelligence (EU region). Put endpoint and key in `.env` (**never commit it**)
- The classifier model (`multilingual-e5-small`, ~120 MB) downloads once, then runs offline

```powershell
python scripts\process_case.py --classifier rules|model|hybrid
python scripts\process_case.py --engine azure
python scripts\process_case.py --pages data\cases\case01_hard\pages_photo
python scripts\make_stress_set.py ; python scripts\run_stress.py --quick
```
</details>

<details>
<summary><b>📁 Project structure</b></summary>

```
get_well_OCR/
├── start.sh / start.bat    One-command launcher: sets up the environment, starts the app
├── app.py                  Streamlit entry point
├── views/                  Screens (case workspace, single page, UI components)
├── src/                    Pipeline: no UI code, reusable by a backend API
│   ├── preprocess.py       Image cleanup (orientation, lighting, noise, deskew)
│   ├── extract.py          OCR: Tesseract or Azure Document Intelligence
│   ├── case.py             Multi-page pipeline: quality, classify, extract, merge
│   ├── doc_classifier.py   Offline language model for document types
│   ├── report.py           ER handover text
│   ├── export.py           JSON, CSV, FHIR, patient plan PDF
│   └── store.py            Case folders, uploads, doctor review
├── scripts/                Run, evaluate, generate test data
└── data/cases/             Fictional test cases + answer files (see its README)
```
</details>

<details>
<summary><b>🧪 Test data</b></summary>

All patients are **fictional** (every page is marked *FIKTIV*). Main case: *Helga Beispiel, 78*, shortness of breath, 20 pages across 15 documents, with planted traps: an outdated medication plan, a false *"no allergies"*, a blurry duplicate, an irrelevant insurance letter. Details in [`data/cases/README.md`](data/cases/README.md).
</details>

---

## 🔒 Privacy by design

- 🧪 **Fictional data only** in this repository
- 💻 **Runs offline** on a laptop: OCR and classification need no cloud
- 🇪🇺 Optional Azure services **in an EU region** only
- 🗑️ Uploaded cases can be **deleted completely** with one click
- 👩‍⚕️ **Nothing is exported** before a doctor has confirmed it

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
