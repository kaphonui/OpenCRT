@echo off
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -r requirements.txt
pyinstaller --noconfirm --clean --onefile --windowed ^
  --name OpenCRT ^
  --add-data "data;data" ^
  --collect-all PySide6 ^
  --collect-all paramiko ^
  app.py
echo.
echo EXE: dist\OpenCRT.exe
pause
