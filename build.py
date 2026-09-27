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
DONNEES = ("index.html", "serveur.py", "app.py", "veilleur.py", "make_icon.py", "build.py",
           "build-macos.py", "installer.py",
           "README.md", "LICENSE", "THIRD-PARTY.md", "requirements.txt", "requirements-app.txt",
           "requirements-build.txt", "Editeur PDF.bat", "Editeur PDF (navigateur).bat")


VERSION = "1.0.0"
NOM = "Editeur PDF BPO"      # sans accent : il sert de nom de dossier et de clé de registre

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
    # --onedir ET NON --onefile. Le lanceur « un seul fichier » relance le vrai
    # processus, et en mode fenêtré la fenêtre n'est JAMAIS montrée : créée,
    # placée, page chargée, et rien à l'écran. Mesuré le 27/09 sur le même code,
    # le même poste, la même minute : --onefile 0 essai sur 4, --onedir 3 sur 3,
    # visible en 3 à 7 s. Trois contournements tentés avant d'en arriver là
    # (forcer ShowWindow depuis un fil voisin, appeler show() sur l'événement
    # « page chargée », figer le profil WebView2) n'ont rien donné : le défaut
    # est dans l'emballage, pas dans l'application.
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--noconsole",
            "--name", NOM, "--icon", "icon.ico",
            "--version-file", ecrire_version(),
            "--collect-all", "webview", "--collect-all", "pymupdf",
            "--hidden-import", "veilleur"]
    for f in DONNEES:
        args += ["--add-data", f"{f}{os.pathsep}."]
    args.append("app.py")
    subprocess.check_call(args)

    dossier = os.path.join(ICI, "dist", NOM)
    exe = os.path.join(dossier, NOM + ".exe")
    if not os.path.isfile(exe):
        raise SystemExit("La construction n'a pas produit %s" % exe)
    poids = sum(os.path.getsize(os.path.join(r, f))
                for r, _, fs in os.walk(dossier) for f in fs)
    print("\nApplication : %s (%.1f Mo, %d fichiers)"
          % (dossier, poids / 1e6, sum(len(fs) for _, _, fs in os.walk(dossier))))

    # Un seul fichier à se passer entre collègues, malgré le dossier : une archive.
    zip_ = os.path.join(ICI, "dist", NOM + ".zip")
    if os.path.exists(zip_):
        os.remove(zip_)
    shutil.make_archive(zip_[:-4], "zip", os.path.join(ICI, "dist"), NOM)
    print("Archive    : %s (%.1f Mo)" % (zip_, os.path.getsize(zip_) / 1e6))
    shutil.rmtree(os.path.join(ICI, "build"), ignore_errors=True)


if __name__ == "__main__":
    main()
