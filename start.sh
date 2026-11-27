#!/usr/bin/env bash
# Start Get Well OCR on macOS / Linux. First run sets everything up automatically.
#   ./start.sh            (options: --setup-only, --port N, --no-browser)
set -euo pipefail
cd "$(dirname "$0")"

# Any Python 3.8+ can run the bootstrap; it then picks/installs 3.10-3.13 for the app.
find_py() {
  for c in python3.12 python3.11 python3.13 python3.10 python3 python; do
    if command -v "$c" >/dev/null 2>&1 &&
       "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
      echo "$c"; return 0
    fi
  done
  return 1
}

if ! PY="$(find_py)"; then
  echo "[get-well] No Python 3 found, installing it ..."
  if [ "$(uname)" = "Darwin" ]; then
    command -v brew >/dev/null 2>&1 || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
    brew install python@3.12
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3.12
  else
    echo "Please install Python 3.12 and run this again."; exit 1
  fi
  hash -r
  PY="$(find_py)"
fi

exec "$PY" start.py "$@"
