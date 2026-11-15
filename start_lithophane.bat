@echo off
rem Startet den Lithophan-Generator ohne Konsolenfenster
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" main.py
    exit /b 0
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw main.py
    exit /b 0
)

echo Python wurde nicht gefunden.
echo Bitte Python von python.org installieren und dann im Projektordner:
echo     pip install -r requirements.txt
pause
exit /b 1
