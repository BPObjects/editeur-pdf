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
DONNEES = ("index.html", "serveur.py", "app.py", "make_icon.py", "build.py", "build-macos.py",
           "README.md", "LICENSE", "THIRD-PARTY.md", "requirements.txt", "requirements-app.txt",
           "requirements-build.txt", "Editeur PDF.bat", "Editeur PDF (navigateur).bat")


VERSION = "1.0.0"

# Sans ce bloc, les Propriétés du fichier sont VIDES sous Windows : ni nom, ni
# éditeur, ni version. Sur un poste qui n'est pas le nôtre, c'est la première
# chose qu'un collègue méfiant regarde — et SmartScreen n'a rien à afficher non
# plus que le nom du fichier.
GABARIT_VERSION = """VSVersionInfo(
  ffi=FixedFileInfo(filevers=(%(n)s), prodvers=(%(n)s),
                    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040C04B0', [
          StringStruct('CompanyName', 'BPO — Antoine Lacronique'),
          StringStruct('FileDescription', 'Éditeur PDF BPO'),
          StringStruct('FileVersion', '%(v)s'),
          StringStruct('InternalName', 'EditeurPdfBpo'),
          StringStruct('LegalCopyright', '© 2026 BPO — licence GNU AGPL v3'),
          StringStruct('OriginalFilename', 'Editeur PDF BPO.exe'),
          StringStruct('ProductName', 'Éditeur PDF BPO'),
          StringStruct('ProductVersion', '%(v)s')])]),
        VarFileInfo([VarStruct('Translation', [0x040C, 1200])])]
)
"""


def ecrire_version() -> str:
    """Fichier de ressource de version, en français (0x040C) et Unicode (1200)."""
    chemin = os.path.join(ICI, "version.txt")
    n = ", ".join(VERSION.split(".") + ["0"])
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(GABARIT_VERSION % {"n": n, "v": VERSION + ".0"})
    return chemin


def main():
    os.chdir(ICI)
    if not os.path.isfile("icon.ico"):
        subprocess.check_call([sys.executable, "make_icon.py"])
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--noconsole",
            "--name", "Editeur PDF BPO", "--icon", "icon.ico",
            "--version-file", ecrire_version(),
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
