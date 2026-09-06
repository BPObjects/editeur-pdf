# SPDX-License-Identifier: AGPL-3.0-or-later
"""Construit « Editeur PDF BPO.app » puis le .dmg — À LANCER SUR UN MAC.

    python3 build-macos.py [--sans-argv-emulation]

PyInstaller ne sait pas fabriquer une application macOS depuis Windows : il n'y
a pas de compilation croisée, le lanceur et les extensions natives sont ceux du
système courant. Ce fichier est donc versionné avec le reste, mais il ne
s'exécute que sur le Mac. Le premier contrôle ci-dessous le rappelle.

Résultat : dist/Editeur PDF BPO.app et dist/Editeur PDF BPO.dmg
"""
from __future__ import annotations

import os
import platform
import plistlib
import shutil
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
NOM = "Editeur PDF BPO"
IDENT = "archi.bpo.editeur-pdf"
VERSION = "1.0.0"
DONNEES = ("index.html", "serveur.py", "app.py", "make_icon.py", "build.py", "build-macos.py",
           "README.md", "LICENSE", "THIRD-PARTY.md", "requirements.txt", "requirements-app.txt",
           "requirements-build.txt", "Editeur PDF.bat", "Editeur PDF (navigateur).bat")


def stop(msg: str):
    print("\n  " + msg + "\n", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- contrôles
def controles():
    if sys.platform != "darwin":
        stop("PyInstaller ne sait pas fabriquer une application macOS depuis "
             "Windows.\n  Copiez ce dossier sur un Mac et relancez « python3 build-macos.py » là-bas.")
    if sys.version_info < (3, 10):
        stop("Python 3.10 ou plus récent est nécessaire (trouvé %d.%d)." % sys.version_info[:2])
    for outil in ("codesign", "lipo", "hdiutil"):
        if not shutil.which(outil):
            stop("L'outil « %s » est introuvable.\n  Installez les outils Xcode : xcode-select --install" % outil)
    manquants = []
    for module in ("pymupdf", "webview", "PyInstaller"):
        try:
            __import__(module)
        except ImportError:
            manquants.append(module)
    if manquants:
        stop("Modules absents : %s\n  python3 -m pip install -r requirements-app.txt -r requirements-build.txt"
             % ", ".join(manquants))
    print("  Machine    : %s (%s)" % (platform.machine(), platform.mac_ver()[0]))
    print("  Python     : %s" % platform.python_version())
    if not os.path.isfile(os.path.join(ICI, "icon.icns")):
        print("  ⚠ icon.icns absent : l'icône sera celle de PyInstaller.")
        print("    Fabriquez-la depuis icon-256.png (voir la fonction icone_depuis_png ci-dessous).")


def icone_depuis_png():
    """Fabrique icon.icns depuis icon-256.png si l'outil iconutil est là.

    macOS veut un jeu complet, Retina comprise. On part du PNG le plus grand
    dont on dispose ; à défaut de 1024 px, l'icône sera un peu molle sur les
    grandes tailles — mieux vaut cela que pas d'icône.
    """
    src = os.path.join(ICI, "icon-256.png")
    if not os.path.isfile(src) or not shutil.which("iconutil"):
        return False
    jeu = os.path.join(ICI, "build", "icon.iconset")
    shutil.rmtree(jeu, ignore_errors=True)
    os.makedirs(jeu, exist_ok=True)
    for taille in (16, 32, 128, 256, 512):
        for facteur, suffixe in ((1, ""), (2, "@2x")):
            px = taille * facteur
            sortie = os.path.join(jeu, "icon_%dx%d%s.png" % (taille, taille, suffixe))
            subprocess.run(["sips", "-z", str(px), str(px), src, "--out", sortie],
                           check=False, capture_output=True)
    r = subprocess.run(["iconutil", "-c", "icns", jeu, "-o", os.path.join(ICI, "icon.icns")],
                       capture_output=True)
    return r.returncode == 0


# ---------------------------------------------------------------- le .spec
def info_plist() -> dict:
    # Le socle minimal suit l'architecture : les roues de PyMuPDF sont
    # étiquetées macosx_11_0_arm64 d'un côté, macosx_10_15_x86_64 de l'autre.
    mini = "11.0" if platform.machine() == "arm64" else "10.15"
    return {
        "CFBundleName": "Editeur PDF BPO",
        "CFBundleDisplayName": "Éditeur PDF BPO",
        "CFBundleIdentifier": IDENT,
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "NSHumanReadableCopyright": "© 2026 BPO / Antoine Lacronique — GNU AGPL v3",
        "LSMinimumSystemVersion": mini,
        "LSApplicationCategoryType": "public.app-category.productivity",
        "NSHighResolutionCapable": True,
        # Ceinture : l'application parle à son propre serveur en http sur la
        # boucle locale. Sans cette clé, une fenêtre blanche au lancement est
        # le symptôme le plus probable.
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        "CFBundleDocumentTypes": [
            {"CFBundleTypeName": "PDF", "LSItemContentTypes": ["com.adobe.pdf"],
             "CFBundleTypeRole": "Editor", "LSHandlerRank": "Alternate"},
            {"CFBundleTypeName": "Image", "CFBundleTypeRole": "Viewer", "LSHandlerRank": "Alternate",
             "LSItemContentTypes": ["public.png", "public.jpeg", "public.tiff",
                                    "com.microsoft.bmp", "org.webmproject.webp"]},
        ],
    }


def ecrire_spec(argv_emulation: bool) -> str:
    """Un .spec est obligatoire : seule cette forme permet de poser info_plist.

    Trois options de la version Windows sont volontairement absentes :
      · --onefile, déprécié pour une application graphique macOS et promis à
        devenir une erreur ;
      · --target-arch universal2, qui échouerait — les roues de PyMuPDF sont
        des binaires MINCES, et PyInstaller exige des binaires gras ;
      · upx, qui abîme les binaires signés.
    """
    chemin = os.path.join(ICI, "build", "%s.spec" % NOM)
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    icone = "icon.icns" if os.path.isfile(os.path.join(ICI, "icon.icns")) else None
    with open(chemin, "w", encoding="utf-8") as f:
        f.write("# engendré par build-macos.py — ne pas modifier à la main\n")
        f.write("from PyInstaller.utils.hooks import collect_all\n")
        f.write("DONNEES = %r\n" % (DONNEES,))
        f.write("datas = [(f, '.') for f in DONNEES]\n")
        f.write("binaries, hiddenimports = [], []\n")
        f.write("for p in ('webview', 'pymupdf'):\n")
        f.write("    d, b, h = collect_all(p); datas += d; binaries += b; hiddenimports += h\n")
        f.write("a = Analysis(['app.py'], datas=datas, binaries=binaries, hiddenimports=hiddenimports)\n")
        f.write("pyz = PYZ(a.pure)\n")
        f.write("exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=%r,\n" % NOM)
        f.write("          console=False, upx=False, argv_emulation=%r,\n" % argv_emulation)
        f.write("          target_arch=None, codesign_identity=None, entitlements_file=None%s)\n"
                % (", icon=%r" % icone if icone else ""))
        f.write("coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=%r)\n" % NOM)
        f.write("app = BUNDLE(coll, name=%r, bundle_identifier=%r, version=%r,\n"
                % (NOM + ".app", IDENT, VERSION))
        f.write("             info_plist=%r%s)\n"
                % (info_plist(), ", icon=%r" % icone if icone else ""))
    return chemin


# ---------------------------------------------------------------- vérifs
def verifier_bundle(app: str):
    plist = os.path.join(app, "Contents", "Info.plist")
    if not os.path.isfile(plist):
        stop("Le paquet ne contient pas d'Info.plist : la construction a échoué.")
    with open(plist, "rb") as f:
        d = plistlib.load(f)
    for cle in ("CFBundleIdentifier", "LSMinimumSystemVersion", "NSAppTransportSecurity"):
        if cle not in d:
            stop("Clé absente de l'Info.plist : %s" % cle)
    res = os.path.join(app, "Contents", "Resources")
    for fichier in ("index.html", "serveur.py"):
        p = os.path.join(res, fichier)
        if not os.path.isfile(p) or os.path.getsize(p) == 0:
            stop("Ressource absente ou vide dans le paquet : %s" % fichier)
    print("  Info.plist et ressources : ok")

    # PyInstaller signe déjà en ad hoc et en profondeur, mais un échec n'y est
    # qu'un avertissement — et sur Apple Silicon, une signature est obligatoire
    # pour que le binaire s'exécute. On vérifie, on ne re-signe qu'au besoin.
    r = subprocess.run(["codesign", "--verify", "--deep", "--strict", app], capture_output=True)
    if r.returncode != 0:
        print("  Signature absente ou invalide : signature ad hoc…")
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", app], check=True)
    print("  Signature ad hoc : ok")


def faire_dmg(app: str) -> str:
    scene = os.path.join(ICI, "build", "dmg")
    shutil.rmtree(scene, ignore_errors=True)
    os.makedirs(scene, exist_ok=True)
    shutil.copytree(app, os.path.join(scene, os.path.basename(app)), symlinks=True)
    os.symlink("/Applications", os.path.join(scene, "Applications"))
    dmg = os.path.join(ICI, "dist", "%s.dmg" % NOM)
    if os.path.exists(dmg):
        os.remove(dmg)
    subprocess.run(["hdiutil", "create", "-volname", NOM, "-srcfolder", scene,
                    "-ov", "-format", "UDZO", dmg], check=True)
    return dmg


def main():
    os.chdir(ICI)
    controles()
    if not os.path.isfile("icon.icns"):
        icone_depuis_png()
    shutil.rmtree("build", ignore_errors=True)
    shutil.rmtree("dist", ignore_errors=True)
    spec = ecrire_spec(argv_emulation="--sans-argv-emulation" not in sys.argv)
    print("\n  Construction…")
    subprocess.check_call([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                           "--distpath", "dist", "--workpath", "build", spec])
    app = os.path.join(ICI, "dist", NOM + ".app")
    print("\n  Contrôles…")
    verifier_bundle(app)
    print("\n  Image disque…")
    dmg = faire_dmg(app)
    print("\n  Terminé : %s (%.1f Mo)" % (dmg, os.path.getsize(dmg) / 1e6))
    print("  Architecture : %s — ce .dmg ne vaut que pour les Mac de ce type." % platform.machine())


if __name__ == "__main__":
    main()
