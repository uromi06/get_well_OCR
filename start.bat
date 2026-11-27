@echo off
REM Start Get Well OCR on Windows. First run sets everything up automatically.
REM   start.bat            (options: --setup-only, --port N, --no-browser)
setlocal
cd /d "%~dp0"

where py >nul 2>nul && (py -3 start.py %* & goto :end)
where python >nul 2>nul && (python start.py %* & goto :end)

echo [get-well] No Python found, installing Python 3.12 ...
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" start.py %*
) else (
  echo Python was installed. Close this window, open a new one and run start.bat again.
)

:end
if errorlevel 1 pause
endlocal
