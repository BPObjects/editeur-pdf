@echo off
rem Glisser des JPEG / PNG sur ce fichier : ils recoivent 72 dpi (pixels intacts),
rem et Archicad les imprime entiers au lieu d'en rogner le coin haut-gauche.
rem Le veilleur le fait deja tout seul pour ce qui arrive dans Telechargements.
python -I "%~dp0..\image_dpi.py" --pause %*
