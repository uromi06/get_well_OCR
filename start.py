"""One-command launcher: sets up everything on first run, then starts the app.

    macOS / Linux:   ./start.sh
    Windows:         start.bat        (double-click works too)
    Any OS:          python start.py

What it does, every time (fast when nothing changed):
  1. Finds a suitable Python (3.10 - 3.13, prefers 3.12); installs one if none is found.
  2. Creates .venv (or rebuilds it if it is broken or from another machine).
  3. Installs requirements.txt, but only when the file changed since the last install.
  4. Makes sure Tesseract with German + English + orientation data is available
     (installs it with brew / apt / dnf / winget, or downloads the language files).
  5. Creates .env from .env.example if it does not exist yet.
  6. Starts Streamlit and opens the browser.

Options:
  --setup-only     do steps 1-5, do not start the app
  --port N         port for the app (default 8501, or the next free one)
  --no-browser     do not open the browser
  Anything else is passed on to "streamlit run app.py".

Only the standard library is used here, so this runs before anything is installed.
Works with Python 3.8+ as the bootstrap interpreter.
"""
import hashlib
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
STAMP = VENV / ".requirements.sha256"
LOCAL_TESSDATA = ROOT / ".tessdata"
TESSDATA_URL = "https://github.com/tesseract-ocr/tessdata/raw/main/{}.traineddata"
TESS_LANGS = ("eng", "deu", "osd")

SUPPORTED = [(3, 12), (3, 11), (3, 13), (3, 10)]   # order = preference
IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"


def say(msg):
    print("[get-well] " + msg, flush=True)


def die(msg):
    print("\n[get-well] ERROR: " + msg, file=sys.stderr, flush=True)
    sys.exit(1)


def run(cmd, check=True, **kw):
    say("$ " + " ".join(str(c) for c in cmd))
    return subprocess.run([str(c) for c in cmd], check=check, **kw)


def has(cmd):
    return shutil.which(cmd) is not None


# ---------------------------------------------------------------- 1. Python

def py_version(exe):
    """(major, minor) of an interpreter, or None if it does not run."""
    try:
        out = subprocess.run([str(exe), "-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
                             capture_output=True, text=True, timeout=30)
        major, minor = out.stdout.split()
        return int(major), int(minor)
    except Exception:
        return None


def candidate_pythons():
    yield sys.executable                      # the one running this script
    for major, minor in SUPPORTED:
        yield "python{}.{}".format(major, minor)
        if IS_WIN:
            yield "py -{}.{}".format(major, minor)
    yield "python3"
    yield "python"
    if IS_MAC:
        for major, minor in SUPPORTED:
            yield "/opt/homebrew/bin/python{}.{}".format(major, minor)
            yield "/usr/local/bin/python{}.{}".format(major, minor)
    if IS_WIN:
        local = os.environ.get("LOCALAPPDATA", "")
        for major, minor in SUPPORTED:
            yield str(Path(local) / "Programs" / "Python" / "Python{}{}".format(major, minor) / "python.exe")


def resolve(cand):
    """Turn a candidate into a real interpreter path (handles the Windows 'py -3.12' launcher)."""
    if cand.startswith("py -"):
        if not has("py"):
            return None
        out = subprocess.run(["py", cand[3:], "-c", "import sys; print(sys.executable)"],
                             capture_output=True, text=True)
        return out.stdout.strip() if out.returncode == 0 else None
    if os.path.isabs(cand):
        return cand if Path(cand).is_file() else None
    return shutil.which(cand)


def find_python():
    best = None
    for cand in candidate_pythons():
        exe = resolve(cand)
        if not exe:
            continue
        ver = py_version(exe)
        if ver in SUPPORTED and (best is None or SUPPORTED.index(ver) < SUPPORTED.index(best[1])):
            best = (exe, ver)
            if ver == SUPPORTED[0]:
                break
    return best


def install_python():
    say("No Python 3.10 - 3.13 found, installing Python 3.12 ...")
    if IS_MAC and has("brew"):
        run(["brew", "install", "python@3.12"])
    elif IS_WIN and has("winget"):
        run(["winget", "install", "-e", "--id", "Python.Python.3.12",
             "--accept-package-agreements", "--accept-source-agreements"], check=False)
    elif has("apt-get"):
        run(["sudo", "apt-get", "update"], check=False)
        run(["sudo", "apt-get", "install", "-y", "python3", "python3-venv", "python3-pip"])
    elif has("dnf"):
        run(["sudo", "dnf", "install", "-y", "python3.12"])
    else:
        die("Please install Python 3.12 from https://www.python.org/downloads/ and run this again.")


def ensure_python():
    found = find_python()
    if not found:
        install_python()
        found = find_python()
    if not found:
        die("Python 3.12 was installed but cannot be found yet. Open a new terminal and run this again.")
    say("Using Python {}.{} ({})".format(found[1][0], found[1][1], found[0]))
    return found[0]


# ---------------------------------------------------------------- 2. venv + 3. packages

def venv_python():
    return VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")


def ensure_venv(base_python):
    vpy = venv_python()
    if VENV.exists() and py_version(vpy) not in SUPPORTED:
        say(".venv is broken or was made on another machine, rebuilding it ...")
        shutil.rmtree(VENV)
    if not VENV.exists():
        say("Creating virtual environment (.venv) ...")
        res = run([base_python, "-m", "venv", VENV], check=False)
        if res.returncode != 0:
            if has("apt-get"):     # Debian/Ubuntu ship venv separately
                ver = py_version(base_python)
                run(["sudo", "apt-get", "install", "-y", "python{}.{}-venv".format(*ver)], check=False)
                shutil.rmtree(VENV, ignore_errors=True)
                run([base_python, "-m", "venv", VENV])
            else:
                die("Could not create the virtual environment.")
    return vpy


def ensure_packages(vpy):
    digest = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    if STAMP.exists() and STAMP.read_text().strip() == digest:
        say("Python packages are up to date.")
        return
    say("Installing Python packages (first time takes a few minutes) ...")
    run([vpy, "-m", "pip", "install", "--upgrade", "pip"])
    run([vpy, "-m", "pip", "install", "-r", REQUIREMENTS])
    STAMP.write_text(digest)


# ---------------------------------------------------------------- 4. Tesseract

def find_tesseract():
    exe = shutil.which("tesseract")
    if exe:
        return exe
    guesses = []
    if IS_WIN:
        for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(var)
            if base:
                guesses.append(Path(base) / "Tesseract-OCR" / "tesseract.exe")
                guesses.append(Path(base) / "Programs" / "Tesseract-OCR" / "tesseract.exe")
    else:
        guesses += [Path("/opt/homebrew/bin/tesseract"), Path("/usr/local/bin/tesseract"), Path("/usr/bin/tesseract")]
    for g in guesses:
        if g.is_file():
            return str(g)
    return None


def tesseract_langs(exe, env=None):
    try:
        out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, env=env, timeout=30)
        lines = (out.stdout + out.stderr).splitlines()
        return {l.strip() for l in lines if l.strip() and " " not in l.strip()}
    except Exception:
        return set()


def install_tesseract():
    say("Tesseract (the OCR program) is missing, installing it ...")
    if IS_MAC:
        if not has("brew"):
            die("Install Homebrew first (https://brew.sh), then run this again.")
        run(["brew", "install", "tesseract", "tesseract-lang"])
    elif IS_WIN:
        if not has("winget"):
            die("Install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki, then run this again.")
        run(["winget", "install", "-e", "--id", "UB-Mannheim.TesseractOCR",
             "--accept-package-agreements", "--accept-source-agreements"], check=False)
    elif has("apt-get"):
        run(["sudo", "apt-get", "update"], check=False)
        run(["sudo", "apt-get", "install", "-y", "tesseract-ocr", "tesseract-ocr-deu", "tesseract-ocr-eng"])
    elif has("dnf"):
        run(["sudo", "dnf", "install", "-y", "tesseract", "tesseract-langpack-deu"])
    elif has("pacman"):
        run(["sudo", "pacman", "-S", "--noconfirm", "tesseract", "tesseract-data-deu", "tesseract-data-eng"])
    else:
        die("Please install Tesseract 5 with the German language pack, then run this again.")


def install_optional_system_libs():
    """libdmtx for the medication-plan barcode (optional; failures are ignored)."""
    if IS_MAC and has("brew"):
        run(["brew", "install", "libdmtx"], check=False, capture_output=True)
    elif has("apt-get"):
        run(["sudo", "apt-get", "install", "-y", "libdmtx0b"], check=False, capture_output=True)


def download_tessdata():
    """Language files into ./.tessdata when the installed Tesseract lacks German/OSD."""
    LOCAL_TESSDATA.mkdir(exist_ok=True)
    for lang in TESS_LANGS:
        target = LOCAL_TESSDATA / (lang + ".traineddata")
        if target.exists() and target.stat().st_size > 0:
            continue
        say("Downloading Tesseract language data: " + lang)
        tmp = target.with_suffix(".part")
        urllib.request.urlretrieve(TESSDATA_URL.format(lang), str(tmp))
        tmp.replace(target)


def ensure_tesseract(env):
    """Returns the env for the app (PATH / TESSDATA_PREFIX adjusted as needed)."""
    exe = find_tesseract()
    if not exe:
        install_tesseract()
        install_optional_system_libs()
        exe = find_tesseract()
    if not exe:
        die("Tesseract was installed but cannot be found. Open a new terminal and run this again.")

    # Tesseract installed but not on PATH (typical right after winget): add its folder
    tess_dir = str(Path(exe).parent)
    if shutil.which("tesseract") is None:
        env["PATH"] = tess_dir + os.pathsep + env.get("PATH", "")

    if not set(TESS_LANGS) <= tesseract_langs(exe, env):
        download_tessdata()
        env["TESSDATA_PREFIX"] = str(LOCAL_TESSDATA)
        if not set(TESS_LANGS) <= tesseract_langs(exe, env):
            die("Tesseract cannot load the German language data. Please install it manually.")
        say("Using language data from .tessdata/")
    say("Tesseract OK ({})".format(exe))
    return env


# ---------------------------------------------------------------- 5. .env

def ensure_dotenv():
    env_file, example = ROOT / ".env", ROOT / ".env.example"
    if not env_file.exists() and example.exists():
        shutil.copyfile(example, env_file)
        say("Created .env from .env.example (edit it to add Azure keys; Tesseract works without them).")


# ---------------------------------------------------------------- 6. start

def port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def wait_until_up(url, proc, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline and proc.poll() is None:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def start_app(vpy, env, port, open_browser, extra):
    if port is None:
        port = 8501
        while not port_free(port):
            port += 1
    url = "http://localhost:{}".format(port)
    # headless: skips Streamlit's first-run e-mail prompt; we open the browser ourselves
    cmd = [str(vpy), "-m", "streamlit", "run", str(ROOT / "app.py"),
           "--server.port", str(port), "--server.headless", "true",
           "--browser.gatherUsageStats", "false"] + extra
    say("Starting the app at " + url + "  (Ctrl+C to stop)")
    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env)
    try:
        if open_browser and wait_until_up(url + "/_stcore/health", proc):
            webbrowser.open(url)
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        try:
            return proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            return 130


def parse_args(argv):
    opts = {"setup_only": False, "port": None, "browser": True, "extra": []}
    it = iter(argv)
    for a in it:
        if a == "--setup-only":
            opts["setup_only"] = True
        elif a == "--no-browser":
            opts["browser"] = False
        elif a == "--port":
            opts["port"] = int(next(it))
        elif a.startswith("--port="):
            opts["port"] = int(a.split("=", 1)[1])
        else:
            opts["extra"].append(a)
    return opts


def main():
    opts = parse_args(sys.argv[1:])
    os.chdir(str(ROOT))
    say("Checking environment on {} {} ...".format(platform.system(), platform.machine()))
    base = ensure_python()
    vpy = ensure_venv(base)
    ensure_packages(vpy)
    env = ensure_tesseract(dict(os.environ))
    ensure_dotenv()
    if opts["setup_only"]:
        say("Setup complete. Start the app with ./start.sh (macOS/Linux) or start.bat (Windows).")
        return 0
    return start_app(vpy, env, opts["port"], opts["browser"], opts["extra"])


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:
        die("A setup step failed (exit code {}). See the output above.".format(e.returncode))
