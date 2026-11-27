r"""Checks that everything is installed and configured.

Run from the project folder:   python scripts\check_setup.py
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OK, FAIL, WARN = "[ OK ]", "[FAIL]", "[WARN]"
problems = 0


def report(status, msg, fix=""):
    global problems
    print(f"{status} {msg}")
    if fix:
        print(f"       -> {fix}")
    if status == FAIL:
        problems += 1


# 1. Python version
v = sys.version_info
if v >= (3, 10):
    report(OK, f"Python {v.major}.{v.minor}")
else:
    report(FAIL, f"Python {v.major}.{v.minor} is too old", "Install Python 3.12: winget install Python.Python.3.12")

# 2. Virtual environment
if sys.prefix != sys.base_prefix:
    report(OK, "Virtual environment is active")
else:
    report(WARN, "Virtual environment is NOT active", "Run the app with ./start.sh or start.bat (it uses .venv automatically)")

# 3. Packages
packages = {
    "streamlit": "streamlit", "cv2": "opencv-python-headless", "PIL": "pillow",
    "numpy": "numpy", "pypdfium2": "pypdfium2", "pytesseract": "pytesseract",
    "azure.ai.documentintelligence": "azure-ai-documentintelligence",
    "pydantic": "pydantic", "dotenv": "python-dotenv", "pandas": "pandas",
    "rapidfuzz": "rapidfuzz", "matplotlib": "matplotlib", "reportlab": "reportlab",
    "faker": "faker",
}
for module, pip_name in packages.items():
    try:
        importlib.import_module(module)
        report(OK, f"package {pip_name}")
    except Exception:
        report(FAIL, f"package {pip_name} missing", f"pip install {pip_name}")

try:
    importlib.import_module("pylibdmtx.pylibdmtx")
    report(OK, "package pylibdmtx (barcode bonus)")
except Exception:
    report(WARN, "pylibdmtx not working (optional barcode feature)",
           "Install the Microsoft Visual C++ Redistributable, or just skip this feature")

# 4. Tesseract program + German language
try:
    import pytesseract
    from src import config
    if config.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
    report(OK, f"Tesseract {pytesseract.get_tesseract_version()}")
    langs = pytesseract.get_languages(config="")
    if "deu" in langs:
        report(OK, "Tesseract German language pack")
    else:
        report(FAIL, "Tesseract German language pack missing",
               "Re-run the Tesseract installer and tick 'German' under additional languages")
except Exception as e:
    report(FAIL, f"Tesseract not found ({type(e).__name__})",
           r"winget install UB-Mannheim.TesseractOCR, then set TESSERACT_CMD in .env")

# 5. .env and Azure
root = Path(__file__).resolve().parents[1]
if (root / ".env").exists():
    report(OK, ".env file exists")
    from src import config
    if config.AZURE_DI_ENDPOINT and "<" not in config.AZURE_DI_ENDPOINT and config.AZURE_DI_KEY and "<" not in config.AZURE_DI_KEY:
        report(OK, "Azure endpoint and key are filled in")
    else:
        report(WARN, "Azure endpoint/key not filled in yet", "Paste them into .env (Tesseract works without Azure)")
else:
    report(FAIL, ".env file missing", "Copy .env.example to .env")

print()
print("All good, you're ready to build!" if problems == 0 else f"{problems} problem(s) to fix above.")
