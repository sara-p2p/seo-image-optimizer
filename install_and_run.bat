@echo off
setlocal
cd /d "%~dp0"
set STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
set STREAMLIT_SERVER_HEADLESS=true

where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher not found.
  echo Install Python 3.11+ from https://www.python.org/downloads/windows/ and make sure "Add python.exe to PATH" is checked.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating app environment...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Failed to create the virtual environment.
    pause
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo Package installation failed.
  pause
  exit /b 1
)

streamlit run app.py
pause
