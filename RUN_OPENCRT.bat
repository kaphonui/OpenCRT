@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Khong tim thay Python trong PATH.
  pause
  exit /b 1
)
if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
