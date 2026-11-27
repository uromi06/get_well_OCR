r"""Run the whole case pipeline on a folder of page photos and score it.

Run:   python scripts\process_case.py
       python scripts\process_case.py --pages data\cases\case01\pages_photo --engine azure
       add --fresh to ignore cached OCR

Output: outputs/cases/<case>/case_result.json  (same shape as case01_mock_api.json)
        plus a scorecard against the answer file, if one exists.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config
from src.case import process_case
from src.evaluate import score_case
from src.report import er_report

def print_score(sc: dict):
    print("\n=== Scorecard ===")
    for n in sc["needles"]:
        print(f"  {'✓' if n['found'] else '✗'} {n['id']:<4} {n['fact']}")
    print(f"\nCritical facts found: {sc['needles_found']}/{sc['needles_total']}")
    print(f"Page classification: {sc['pages_correct']}/{sc['pages_classified']} correct "
          f"(pages not judged because sent back for retake: {sc['retake']})")
    for w in sc["misclassified"]:
        print(f"   page {w['page']}: predicted {w['predicted']}, truth {w['truth']}")
    print(f"Conflicts flagged: {sc['conflicts_flagged']} (answer file lists {sc['conflicts_truth']})")
    print(f"Medication status (active vs stopped): {sc['meds_status_correct']}/{sc['meds_total']} correct")
    for w in sc["meds_status_wrong"]:
        print(f"   {w['name']}: predicted {w['predicted']}, truth {w['truth']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", default=str(config.DATA_DIR / "cases" / "case01" / "pages_photo"))
    ap.add_argument("--engine", default=config.OCR_ENGINE)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--classifier", choices=["rules", "model", "hybrid"], help="default: CLASSIFIER in .env / config")
    args = ap.parse_args()

    if args.classifier:
        config.CLASSIFIER = args.classifier
    folder = Path(args.pages)
    case_dir = folder.parent if folder.name.startswith("pages") else folder
    out_dir = config.OUTPUT_DIR / "cases" / case_dir.name
    if config.CLASSIFIER != "rules":
        from src.doc_classifier import available_backend
        backend = available_backend()
        print(f"Classifier: {config.CLASSIFIER} (model backend: {backend})"
              + ("  <- install sentence-transformers for the real model" if backend == "tfidf" else ""))
    result = process_case(folder, out_dir, args.engine, args.fresh)

    report = er_report(result)
    (out_dir / "er_report_de.txt").write_text(report, encoding="utf-8")
    print("\n=== ER handover text (rules, " + args.engine + ") ===")
    print(report)
    print(f"\nSaved {out_dir / 'case_result.json'}")

    answers_file = case_dir / f"{case_dir.name}_answers.json"
    if answers_file.exists():
        print_score(score_case(result, json.loads(answers_file.read_text(encoding="utf-8"))))


if __name__ == "__main__":
    main()
