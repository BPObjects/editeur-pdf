@echo off
rem Variante navigateur : le meme editeur, servi sur http://localhost:8790/
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Installation de l'environnement Python, patientez...
    python -m venv .venv || goto :nopython
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements-app.txt || goto :fail
)

echo Editeur PDF BPO : http://localhost:8790/  (fermez cette fenetre pour arreter)
".venv\Scripts\python.exe" serveur.py %*
exit /b 0

:nopython
echo.
echo Python 3.10 ou plus recent est introuvable. Installez-le depuis python.org
echo en cochant "Add python.exe to PATH", puis relancez ce raccourci.
pause
exit /b 1

:fail
echo.
echo L'installation des dependances a echoue.
pause
exit /b 1
