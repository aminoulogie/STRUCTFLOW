@echo off
REM Compile l'application Windows (dossier dist\SemellesRPA2024\SemellesRPA2024.exe)
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller pywin32
python -m PyInstaller --noconfirm --windowed --name SemellesRPA2024 ^
  --exclude-module streamlit --exclude-module pyarrow --exclude-module altair --exclude-module tornado ^
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets --exclude-module PySide6.QtPdf ^
  --exclude-module tkinter --exclude-module IPython --distpath dist --hidden-import openpyxl --collect-submodules openpyxl --hidden-import win32com.client --hidden-import pythoncom --hidden-import pywintypes --collect-all latex2mathml --collect-all ifcopenshell ^
  semelles_app.py
pause
