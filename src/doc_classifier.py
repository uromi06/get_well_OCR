"""Document type classification with a text-embedding model (offline, on the laptop).

Zero-shot nearest-prototype classification:
  1. Every document type gets a short German description (its "prototype").
  2. The model turns each description and each page into a vector (embedding).
  3. A page gets the type whose description is most similar (cosine similarity).
No training data needed, so it does not learn the layout of our synthetic documents.

Backends
  e5     intfloat/multilingual-e5-small (118 M parameters, ~120 MB, CPU is enough, German works).
         Downloaded once from Hugging Face into the local cache, then runs fully offline.
  tfidf  character n-gram statistics (scikit-learn). No download, weaker; used when the model
         is not installed, and for testing.

Used in src/case.py together with the keyword rules ("hybrid"): when both agree the
type is certain; when they disagree the document is flagged for the doctor to check.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from . import config

# Descriptions are written generally (what such a document usually contains), NOT copied
# from the test case, so the evaluation stays fair.
PROTOTYPES = {
    "discharge_letter": "Arztbrief oder Entlassungsbrief eines Krankenhauses: stationärer Aufenthalt, Diagnosen, "
                        "Anamnese, Verlauf, Befunde, Epikrise, Medikation bei Entlassung, Empfehlungen an den Hausarzt.",
    "medication_plan": "Bundeseinheitlicher Medikationsplan: Tabelle mit Wirkstoff, Handelsname, Stärke, Form, "
                       "Dosierung morgens mittags abends zur Nacht, Einheit, Hinweise und Grund der Einnahme.",
    "lab_report": "Laborbefund: Tabelle mit Laborwerten wie Natrium, Kalium, Kreatinin, eGFR, Hämoglobin, CRP, "
                  "Einheiten, Referenzbereich, Markierung hoch oder niedrig, Probeneingang, Labor freigegeben.",
    "referral": "Einweisung oder Überweisung ins Krankenhaus vom Hausarzt: Verordnung von Krankenhausbehandlung, "
                "Diagnose, Fragestellung, Grund der Einweisung, aktuelle Beschwerden.",
    "imaging_report": "Radiologischer oder kardiologischer Befundbericht: Röntgen, CT, MRT, Ultraschall oder "
                      "Echokardiographie, Technik, Befund, Beurteilung, Messwerte wie Pumpfunktion.",
    "surgery_report": "Operationsbericht: OP-Datum, Operateur, Narkose, Indikation, Operationsverlauf, Zugang, "
                      "Implantate, Prothese, Naht, postoperatives Vorgehen.",
    "advance_directive": "Patientenverfügung und Vorsorgevollmacht: Wünsche zu Wiederbelebung, Beatmung, "
                         "künstlicher Ernährung, Bevollmächtigte Person, Unterschrift des Patienten.",
    "nursing_transfer": "Pflegeüberleitungsbogen vom Pflegedienst oder Pflegeheim: Pflegegrad, Mobilität, "
                        "Ernährung, Ausscheidung, Hilfsmittel, Bezugsperson, Allergien, pflegerische Hinweise.",
    "fax_note": "Kurze Mitteilung per Fax oder handschriftliche Notiz einer Praxis: Telefax, kurze Information "
                "über eine Änderung, zum Beispiel Medikament abgesetzt, mit Gruß und Unterschrift.",
    "specialist_letter": "Facharztbrief einer Praxis an den Hausarzt, z. B. Diabetologie, Neurologie, Nephrologie: "
                         "Vorstellung, Befund, Beurteilung, Therapieempfehlung.",
    "other_medical": "Sonstiges medizinisches Formular: Verlaufsbogen, Disease-Management-Programm, "
                     "Dokumentationsbogen mit Messwerten wie Blutzucker, HbA1c, Blutdruck, Gewicht.",
    "irrelevant": "Nicht medizinisches Schreiben: Brief der Krankenkasse, Versichertenkarte, Bonusprogramm, "
                  "Beitrag, Zuzahlung, Werbung, Rechnung, Terminerinnerung ohne Befund.",
}
TYPES = list(PROTOTYPES)
PAGE_CHARS = 1500          # first part of the page is enough (letterhead + title + start)


@lru_cache(maxsize=1)
def _e5():
    from sentence_transformers import SentenceTransformer   # optional dependency
    return SentenceTransformer(config.CLASSIFIER_MODEL)


@lru_cache(maxsize=1)
def _tfidf():
    from sklearn.feature_extraction.text import TfidfVectorizer
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=True, sublinear_tf=True)
    vec.fit(list(PROTOTYPES.values()))
    return vec


def available_backend() -> str:
    """'e5' if the model can be loaded, else 'tfidf'."""
    if config.CLASSIFIER_BACKEND == "tfidf":
        return "tfidf"
    try:
        _e5()
        return "e5"
    except Exception:
        return "tfidf"


def _embed(texts: list[str], backend: str) -> np.ndarray:
    if backend == "e5":
        # e5 expects a prefix; "query:" for symmetric tasks like classification
        return _e5().encode([f"query: {t}" for t in texts], normalize_embeddings=True)
    m = _tfidf().transform(texts).toarray()
    return m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)


@lru_cache(maxsize=2)
def _prototype_matrix(backend: str) -> np.ndarray:
    return _embed(list(PROTOTYPES.values()), backend)


def classify_embedding(text: str, backend: str | None = None) -> dict:
    """Return {'type', 'similarity', 'margin', 'backend'} for one page of text.

    margin = best similarity minus second best: small margin = model is unsure.
    """
    backend = backend or available_backend()
    page = _embed([" ".join(text.split())[:PAGE_CHARS]], backend)[0]
    sims = _prototype_matrix(backend) @ page
    order = np.argsort(sims)[::-1]
    return {"type": TYPES[order[0]], "similarity": round(float(sims[order[0]]), 3),
            "margin": round(float(sims[order[0]] - sims[order[1]]), 3), "backend": backend,
            "runner_up": TYPES[order[1]]}
