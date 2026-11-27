r"""Baseline comparison: plain "OCR text -> LLM summary" vs. the Get Well OCR pipeline.

The question a jury asks: "Couldn't you just paste the OCR text into an LLM?"
This script answers it with numbers, on the same fictional case and the same OCR text.

  Baseline      all pages' OCR text -> Mistral Large 3, asked for the same ER handover structure
  Get Well OCR  classify -> extract -> merge across documents -> ER handover (rules, no LLM needed)

Both texts get the SAME automatic checks:
  - critical facts found (the 13 "needles" of the answer file)
  - traps: outdated medication listed as current, wrong dose, "no allergies" taken at face value,
    allergy contradiction mentioned, insurance letter ignored, blurry page flagged
  - source page for each fact
  - numbers that appear nowhere in the documents (invented values)

Run:   python scripts\compare_baseline.py                      (case01, Tesseract text)
       python scripts\compare_baseline.py --case case01_hard
       add --fresh to ask Mistral again instead of using the cached answer

Writes outputs/baseline/<case>_baseline.txt, <case>_ours.txt and <case>_comparison.md
(the table for the pitch slide). Needs MISTRAL_API_KEY / MISTRAL_CHAT_ENDPOINT in .env.
Fictional data only.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config, mistral  # noqa: E402
from src.case import process_case  # noqa: E402
from src.evaluate import DEFAULT_NEEDLE_MATCH  # noqa: E402
from src.report import er_report  # noqa: E402

BASELINE_PROMPT = (
    "Du bist Ärztin in der Notaufnahme. Unten steht der OCR-Text aller Unterlagen, die eine Patientin "
    "mitgebracht hat (Seite für Seite, mit Seitennummer). Erstelle daraus eine Übergabe-Zusammenfassung "
    "für die Notaufnahme auf Deutsch mit diesen Abschnitten: Mitgebrachte Dokumente, CAVE (Allergien, "
    "Antikoagulation, Implantate, Patientenverfügung), Diagnosen, Aktuelle Medikation (Wirkstoff, Stärke, "
    "Dosierung), Labor, Anamnese, Kontakt. Sei vollständig und präzise."
)

STOP_WORDS = re.compile(r"abgesetzt|pausiert|beendet|gestoppt|nicht mehr|ehemals|früher|alt\b|umgestellt",
                        re.IGNORECASE)
HEADING = re.compile(r"^\s*(#+\s*)?\**\s*(mitgebrachte|dokumente|cave|diagnosen|aktuelle medikation|medikation|"
                     r"labor|anamnese|kontakt|zu klären|widersprüche|hinweise|befunde|abgesetzt)", re.IGNORECASE)


# ------------------------------------------------------------------ input

def ocr_pages(out_dir: Path, engine: str) -> list[tuple[int, str]]:
    files = sorted((out_dir / "ocr").glob(f"*_{engine}.json"))
    pages = []
    for f in files:
        p = json.loads(f.read_text(encoding="utf-8"))
        pages.append((p["page"], "\n".join(l["text"] for l in p["lines"])))
    return sorted(pages)


def baseline_summary(pages: list[tuple[int, str]], fresh: bool) -> str:
    text = "\n\n".join(f"--- Seite {n} ---\n{t}" for n, t in pages)
    return mistral.chat([{"role": "user", "content": BASELINE_PROMPT + "\n\n" + text}],
                        temperature=0.0, max_tokens=2500, use_cache=not fresh)

# ------------------------------------------------------------------ checks (same for both texts)

def current_med_lines(text: str) -> list[str]:
    """Lines of the 'current medication' section that are not marked as stopped."""
    lines, in_meds, out = text.splitlines(), False, []
    for line in lines:
        if HEADING.match(line):
            low = line.lower()
            in_meds = "medikation" in low and "abgesetzt" not in low
            continue
        if in_meds and line.strip() and not STOP_WORDS.search(line):
            out.append(line)
    return out


def listed_as_current(text: str, drug: str) -> bool:
    return any(drug.lower() in l.lower() for l in current_med_lines(text))


def dose_line(text: str, drug: str) -> str:
    return next((l for l in current_med_lines(text) if drug.lower() in l.lower()), "")


def numbers_not_in_documents(text: str, documents: str) -> list[str]:
    # not facts: page references and the "created on <date time>" footer (same treatment for both texts)
    text = re.sub(r"\[(?:S\.|p\.)[^\]]*\]|\((?:S\.|Seite)\s*[\d,\s–-]+\)|(?:Seite|S\.)\s*\d+(?:[–-]\d+)?", " ", text)
    text = "\n".join(l for l in text.splitlines() if not re.match(r"\s*(Erstellt|Created) ", l))
    doc_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", documents))
    doc_numbers |= {n.replace(",", ".") for n in doc_numbers} | {n.replace(".", ",") for n in doc_numbers}
    found = []
    for n in re.findall(r"(?<![\w.,])\d+(?:[.,]\d+)?(?![\w])", text):
        if n not in doc_numbers and len(n.replace(",", "").replace(".", "")) >= 2:
            found.append(n)
    return sorted(set(found))


def check(text: str, answers: dict, documents: str) -> dict:
    low = text.lower()
    needles = {}
    for n in answers["needles"]:
        keys = n.get("match") or DEFAULT_NEEDLE_MATCH.get(n["id"], [])
        needles[n["id"]] = all(k.lower() in low for k in keys)
    allergy_neg_unqualified = any(re.search(r"allergi\w*:?\s*(keine|nicht bekannt)", l, re.IGNORECASE)
                                  and "penicillin" not in l.lower() for l in text.splitlines())
    traps = {
        "Phenprocoumon (alt) NICHT als aktuell gelistet": not listed_as_current(text, "Phenprocoumon"),
        "Glimepirid (laut Fax abgesetzt) NICHT als aktuell": not listed_as_current(text, "Glimepirid"),
        "Sitagliptin (2021) NICHT als aktuell": not listed_as_current(text, "Sitagliptin"),
        "Torasemid mit aktueller Dosis 20 mg": "20" in dose_line(text, "Torasemid"),
        "Metformin mit aktueller Dosis 500 mg (nicht 1000)": "500" in dose_line(text, "Metformin")
                                                              and "1000" not in dose_line(text, "Metformin"),
        "Penicillin-Allergie genannt": "penicillin" in low,
        "'Keine Allergien' NICHT ungeprüft übernommen": not allergy_neg_unqualified,
        "Allergie-Widerspruch benannt": "penicillin" in low and bool(re.search(r"widersprüch|vs\.|keine bekannt",
                                                                                low)),
        "Krankenkassenbrief ignoriert": not re.search(r"bonusprogramm|gesundheitskarte|zuzahlung", low),
        "Unscharfe Seite 20 erkannt": bool(re.search(r"(seite|s\.)\s*20[^\n]{0,80}(unscharf|unlesbar|neu fotograf)",
                                                     low)),
    }
    fact_lines = [l for l in text.splitlines() if l.strip().startswith(("-", "*", "•")) or re.match(r"^\w", l)]
    with_source = [l for l in fact_lines if re.search(r"\[(S\.|p\.)\s*\d|\(S(eite|\.)\s*\d|Seite\s+\d", l)]
    return {
        "needles": needles, "traps": traps,
        "source_share": round(len(with_source) / max(len(fact_lines), 1), 2),
        "invented_numbers": numbers_not_in_documents(text, documents),
    }

# ------------------------------------------------------------------ report

def table(b: dict, o: dict, answers: dict) -> str:
    def mark(x):
        return "✅" if x else "❌"
    nb, no = sum(b["needles"].values()), sum(o["needles"].values())
    tb, to = sum(b["traps"].values()), sum(o["traps"].values())
    rows = ["| | OCR-Text → LLM (Mistral Large 3) | Get Well OCR |", "|---|---|---|",
            f"| **Kritische Fakten gefunden** | **{nb}/{len(b['needles'])}** | **{no}/{len(o['needles'])}** |",
            f"| **Fallen vermieden** | **{tb}/{len(b['traps'])}** | **{to}/{len(o['traps'])}** |"]
    rows += [f"| {name} | {mark(b['traps'][name])} | {mark(o['traps'][name])} |" for name in b["traps"]]
    rows += [f"| Quellseite pro Angabe | {b['source_share']:.0%} der Zeilen | {o['source_share']:.0%} der Zeilen |",
             f"| Zahlen, die in keinem Dokument stehen | {len(b['invented_numbers'])}"
             f"{' (' + ', '.join(b['invented_numbers'][:6]) + ')' if b['invented_numbers'] else ''} | "
             f"{len(o['invented_numbers'])}"
             f"{' (' + ', '.join(o['invented_numbers'][:6]) + ')' if o['invented_numbers'] else ''} |"]
    missed_b = [n["fact"] for n in answers["needles"] if not b["needles"][n["id"]]]
    missed_o = [n["fact"] for n in answers["needles"] if not o["needles"][n["id"]]]
    rows += ["", "Nicht gefunden (Baseline): " + ("; ".join(missed_b) or "–"),
             "", "Nicht gefunden (Get Well OCR): " + ("; ".join(missed_o) or "–")]
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="case01")
    ap.add_argument("--engine", default="tesseract", help="whose OCR text both sides get (default tesseract)")
    ap.add_argument("--fresh", action="store_true", help="ask Mistral again instead of using the cache")
    args = ap.parse_args()

    if not mistral.chat_available():
        sys.exit("Mistral is not configured: set MISTRAL_API_KEY and MISTRAL_CHAT_ENDPOINT in .env.")
    case_dir = config.DATA_DIR / "cases" / args.case
    answers = json.loads((case_dir / f"{args.case}_answers.json").read_text(encoding="utf-8"))
    out_dir = config.OUTPUT_DIR / "cases" / args.case

    print("1/3 Get Well OCR pipeline (uses cached OCR if present) ...")
    result = process_case(case_dir / "pages_photo", out_dir, args.engine, progress=lambda *_: None)
    ours = er_report(result, show_sources=True)

    pages = ocr_pages(out_dir, args.engine)
    documents = "\n".join(t for _, t in pages)
    print(f"2/3 Baseline: {len(pages)} pages of OCR text ({len(documents):,} characters) -> Mistral Large 3 ...")
    baseline = baseline_summary(pages, args.fresh)

    print("3/3 Same checks on both texts ...\n")
    b, o = check(baseline, answers, documents), check(ours, answers, documents)
    md = table(b, o, answers)
    print(md)

    dest = config.OUTPUT_DIR / "baseline"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / f"{args.case}_baseline.txt").write_text(baseline, encoding="utf-8")
    (dest / f"{args.case}_ours.txt").write_text(ours, encoding="utf-8")
    (dest / f"{args.case}_comparison.md").write_text(
        f"# Baseline comparison: {args.case} (fictional)\n\nSame OCR text ({args.engine}) for both. "
        f"Baseline = Mistral Large 3, temperature 0, one call with all pages.\n\n{md}\n", encoding="utf-8")
    print(f"\nSaved {dest / f'{args.case}_comparison.md'} (+ both texts, read them side by side)")


if __name__ == "__main__":
    main()
