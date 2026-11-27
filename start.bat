@echo off
REM Start Get Well OCR on Windows. First run sets everything up automatically.
REM   start.bat            (options: --setup-only, --self-test, --port N, --no-browser)
setlocal
cd /d "%~dp0"
set "CHECK=import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)"

REM Any Python 3.8+ can run the bootstrap; it then picks/installs 3.10-3.13 for the app.
set PY=
py -3 -c "%CHECK%" >nul 2>nul && set PY=py -3
if not defined PY python -c "%CHECK%" >nul 2>nul && set PY=python
if not defined PY call :install_python
if not defined PY (
  echo [get-well] Python could not be installed automatically.
  echo Install Python 3.12 from https://www.python.org/downloads/ and run start.bat again.
  goto :fail
)

%PY% start.py %*
if errorlevel 1 goto :fail
exit /b 0

:install_python
echo [get-well] No Python found, installing Python 3.12 ...
where winget >nul 2>nul && winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%ProgramFiles%\Python312\python.exe" set PY="%ProgramFiles%\Python312\python.exe"
exit /b 0

:fail
if not defined CI pause
exit /b 1
