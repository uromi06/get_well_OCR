# One-time project setup for Windows (kept for compatibility).
# You no longer need this: start.bat (or "python start.py") sets everything up and starts the app.
#   .\setup_windows.ps1        -> same as: python start.py --setup-only
if (Get-Command py -ErrorAction SilentlyContinue) { py -3 start.py --setup-only }
else { python start.py --setup-only }
