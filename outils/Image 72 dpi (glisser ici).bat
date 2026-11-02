@echo off
rem Glisser des JPEG / PNG sur ce fichier : ils recoivent 72 dpi (pixels intacts),
rem et Archicad les imprime entiers au lieu d'en rogner le coin haut-gauche.
cd /d "%~dp0"
python -I "%~dp0image-72dpi.py" --pause %*
