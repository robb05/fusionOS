@echo off
cd /d "%~dp0"
echo Installazione iniziale: richiede Internet e Python 3.11 o 3.12.
py -3.11 -m venv .venv
if errorlevel 1 py -3.12 -m venv .venv
if errorlevel 1 (
  echo Installa Python 3.11 o 3.12 e riprova.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install .
if errorlevel 1 (
  echo Installazione non completata. Leggi l'errore sopra.
  pause
  exit /b 1
)
echo Installazione completata. Avvia-fusionOS.bat funziona anche offline.
pause
