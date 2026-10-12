@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Prima esegui Installa-Windows.bat. Serve Python 3.11 o 3.12.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m fusionos
if errorlevel 1 pause
