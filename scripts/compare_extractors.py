"""Compare the rules and Mistral extraction on the same cached case OCR."""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config
from src.case import process_case
from src.evaluate import score_case


def _copy_ocr(src: Path, dst: Path):
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", type=Path, default=config.DATA_DIR / "cases" / "case01",
                    help="case folder or its pages_photo subfolder")
    ap.add_argument("--engine", default="tesseract")
    ap.add_argument("--classifier", choices=["rules", "model", "hybrid"])
    args = ap.parse_args()

    if args.classifier:
        config.CLASSIFIER = args.classifier
    if args.case.name.startswith("pages"):
        folder, case_dir = args.case, args.case.parent
    else:
        case_dir = args.case
        folder = case_dir / "pages_photo"
    if not folder.is_dir():
        ap.error(f"Page folder not found: {folder}")
    answers_file = case_dir / f"{case_dir.name}_answers.json"
    if not answers_file.is_file():
        ap.error(f"Answer file not found: {answers_file}")
    answers = json.loads(answers_file.read_text(encoding="utf-8"))

    root = config.OUTPUT_DIR / "cases"
    rules_out = root / f"{case_dir.name}_rules"
    llm_out = root / f"{case_dir.name}_llm"
    _copy_ocr(root / case_dir.name / "ocr", rules_out / "ocr")
    print("\n=== Rules ===")
    rules = process_case(folder, rules_out, engine=args.engine, extractor="rules")
    _copy_ocr(rules_out / "ocr", llm_out / "ocr")
    print("\n=== Mistral Large 3 ===")
    llm = process_case(folder, llm_out, engine=args.engine, extractor="llm")

    a, b = score_case(rules, answers), score_case(llm, answers)
    print(f"\n{'Metric':<24} {'Rules':>12} {'Mistral':>12}")
    for label, numerator, denominator in [
        ("Critical facts found", "needles_found", "needles_total"),
        ("Pages correct", "pages_correct", "pages_classified"),
        ("Med status correct", "meds_status_correct", "meds_total"),
        ("Conflicts flagged/truth", "conflicts_flagged", "conflicts_truth"),
    ]:
        left, right = f"{a[numerator]}/{a[denominator]}", f"{b[numerator]}/{b[denominator]}"
        print(f"{label:<24} {left:>12} {right:>12}")
    for label, key in [("AI corrections", "corrections"), ("Pages using fallback", "extract_errors")]:
        print(f"{label:<24} {len(rules['summary'].get(key, [])):>12} {len(llm['summary'].get(key, [])):>12}")
    print(f"\nResults: {rules_out} and {llm_out}")


if __name__ == "__main__":
    main()
