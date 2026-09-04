# SPDX-License-Identifier: AGPL-3.0-or-later
"""Construit l'exécutable Windows « Editeur PDF BPO.exe » (PyInstaller, un seul fichier).

    python build.py

Résultat : dist/Editeur PDF BPO.exe. Les sources sont embarquées pour que le lien
« Source » de l'application (obligation AGPL) fonctionne aussi depuis l'exécutable.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
DONNEES = ("index.html", "serveur.py", "app.py", "make_icon.py", "build.py", "README.md", "LICENSE",
           "THIRD-PARTY.md", "requirements.txt", "requirements-app.txt", "requirements-build.txt",
           "Editeur PDF.bat", "Editeur PDF (navigateur).bat")


def main():
    os.chdir(ICI)
    if not os.path.isfile("icon.ico"):
        subprocess.check_call([sys.executable, "make_icon.py"])
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--noconsole",
            "--name", "Editeur PDF BPO", "--icon", "icon.ico",
            "--collect-all", "webview", "--collect-all", "pymupdf"]
    for f in DONNEES:
        args += ["--add-data", f"{f}{os.pathsep}."]
    args.append("app.py")
    subprocess.check_call(args)
    exe = os.path.join(ICI, "dist", "Editeur PDF BPO.exe")
    print("\nExécutable :", exe, "(%.1f Mo)" % (os.path.getsize(exe) / 1e6))
    shutil.rmtree(os.path.join(ICI, "build"), ignore_errors=True)


if __name__ == "__main__":
    main()
