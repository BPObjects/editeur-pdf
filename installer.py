# SPDX-License-Identifier: AGPL-3.0-or-later
"""Installe l'Éditeur PDF BPO pour l'utilisateur courant — Windows, sans droits d'administrateur.

    python installer.py                 installe ou met à jour
    python installer.py --etat          dit ce qui est posé, sans rien écrire
    python installer.py --desinstaller  retire tout
    python installer.py --diffuser      recopie AUSSI le build dans le dossier de diffusion

POURQUOI CE SCRIPT EXISTE. L'exécutable était lancé depuis là où il avait été
déposé — un dossier Dropbox, la sortie de build, une copie d'un collègue — et
Windows enregistrait ce chemin-là. On se retrouvait avec quatre exemplaires de
dates différentes et un double-clic qui ouvrait le plus ancien. Il faut UN
emplacement stable, que la mise à jour remplace sur place.

CE QUE CE SCRIPT NE FAIT PAS, ET NE PEUT PAS FAIRE. Il ne se désigne pas
lui-même « application par défaut » pour le .pdf. Windows protège ce choix par
un hachage lié au compte, à l'extension et à l'application ; le forger est ce
que fait un logiciel indésirable, et Windows le défait. Le script se contente de
s'enregistrer proprement pour APPARAÎTRE dans « Ouvrir avec » — le choix reste à
la personne, et c'est ainsi que cela doit être.
"""
from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import winreg

ICI = os.path.dirname(os.path.abspath(__file__))
NOM_FICHIER = "Editeur PDF BPO.exe"      # sans accent : il sert de clé de registre
NOM_AFFICHE = "Éditeur PDF BPO"
PROGID = "EditeurPdfBpo.Document"
APPID = "EditeurPdfBpo"
SOURCE = os.path.join(ICI, "dist", NOM_FICHIER)
CIBLE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                         "Programs", "Editeur PDF BPO")
CIBLE = os.path.join(CIBLE_DIR, NOM_FICHIER)
DIFFUSION = os.path.join(os.path.expanduser("~"), "Dropbox", "AL's shared workspace",
                         "Architecture-AL", "2- logiciels et objets", "SOFT PC", NOM_FICHIER)
CLE_DESINST = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\\" + APPID


def echo(msg=""):
    print(msg)


def stop(msg: str):
    echo()
    echo("  " + msg)
    echo()
    sys.exit(1)


# ---------------------------------------------------------------- l'application tourne-t-elle ?
def processus_en_cours() -> bool:
    """Deux contrôles, parce qu'ils n'attrapent pas la même chose : la liste des
    tâches voit N'IMPORTE QUEL exemplaire ouvert (y compris une copie Dropbox),
    l'ouverture en écriture voit le verrou réel du fichier qu'on veut remplacer."""
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + NOM_FICHIER, "/NH", "/FO", "CSV"],
                           capture_output=True, text=True, timeout=20)
        if NOM_FICHIER.lower() in (r.stdout or "").lower():
            return True
    except Exception:
        pass
    if os.path.isfile(CIBLE):
        try:
            with open(CIBLE, "r+b"):
                pass
        except PermissionError:
            return True
        except OSError:
            pass
    return False


# ---------------------------------------------------------------- registre
def poser(chemin: str, valeurs: dict, racine=winreg.HKEY_CURRENT_USER):
    with winreg.CreateKeyEx(racine, chemin, 0, winreg.KEY_WRITE) as k:
        for nom, (typ, val) in valeurs.items():
            winreg.SetValueEx(k, nom, 0, typ, val)


def lire(chemin: str, nom: str = ""):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chemin) as k:
            return winreg.QueryValueEx(k, nom)[0]
    except OSError:
        return None


def effacer_arbre(chemin: str):
    """Supprime une clé et tout ce qu'elle contient. winreg ne sait effacer
    qu'une clé vide : on descend d'abord."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chemin, 0, winreg.KEY_READ) as k:
            while True:
                try:
                    effacer_arbre(chemin + "\\" + winreg.EnumKey(k, 0))
                except OSError:
                    break
    except OSError:
        return
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, chemin)
    except OSError:
        pass


S = winreg.REG_SZ


def enregistrer(version: str):
    app = r"Software\Classes\Applications\\" + NOM_FICHIER
    cmd = '"%s" "%%1"' % CIBLE
    icone = '"%s",0' % CIBLE

    # (a) La clé que Windows consulte pour « Ouvrir avec » — et celle vers
    #     laquelle pointait l'ancien chemin. C'est la ligne qui corrige tout.
    poser(app, {"FriendlyAppName": (S, NOM_AFFICHE)})
    poser(app + r"\DefaultIcon", {"": (S, icone)})
    poser(app + r"\SupportedTypes", {".pdf": (S, "")})
    poser(app + r"\shell\open\command", {"": (S, cmd)})

    # (b) Un type de document en propre, pour que la ligne des Paramètres
    #     affiche autre chose que le nom du fichier.
    pg = r"Software\Classes\\" + PROGID
    poser(pg, {"": (S, "Document PDF (%s)" % NOM_AFFICHE),
               "FriendlyTypeName": (S, "Document PDF (%s)" % NOM_AFFICHE)})
    poser(pg + r"\DefaultIcon", {"": (S, icone)})
    poser(pg + r"\shell\open\command", {"": (S, cmd)})

    # (c) Se PROPOSER sur le .pdf sans le prendre : on ajoute une valeur à la
    #     liste, on ne touche jamais à la valeur par défaut de .pdf.
    poser(r"Software\Classes\.pdf\OpenWithProgids", {PROGID: (winreg.REG_NONE, b"")})

    # (d) Se déclarer aux Paramètres de Windows.
    cap = r"Software\BPO\Editeur PDF BPO\Capabilities"
    poser(cap, {"ApplicationName": (S, NOM_AFFICHE),
                "ApplicationDescription": (S, "Compresser, modifier, signer et assembler des PDF"),
                "ApplicationIcon": (S, icone)})
    poser(cap + r"\FileAssociations", {".pdf": (S, PROGID)})
    poser(r"Software\RegisteredApplications", {APPID: (S, cap)})

    # (e) Apparaître dans « Applications installées », avec de quoi désinstaller.
    taille = int(os.path.getsize(CIBLE) / 1024) if os.path.isfile(CIBLE) else 0
    poser(CLE_DESINST, {
        "DisplayName": (S, NOM_AFFICHE),
        "DisplayIcon": (S, CIBLE + ",0"),
        "DisplayVersion": (S, version),
        "Publisher": (S, "BPO — Antoine Lacronique"),
        "InstallLocation": (S, CIBLE_DIR),
        "UninstallString": (S, '"%s" "%s" --desinstaller' % (sys.executable, os.path.join(ICI, "installer.py"))),
        "NoModify": (winreg.REG_DWORD, 1),
        "NoRepair": (winreg.REG_DWORD, 1),
        "EstimatedSize": (winreg.REG_DWORD, taille),
    })


def prevenir_le_shell():
    """Sans cela, l'explorateur garde son ancienne idée des associations
    jusqu'à son redémarrage."""
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)  # SHCNE_ASSOCCHANGED
    except Exception:
        pass


# ---------------------------------------------------------------- raccourcis
def dossiers_raccourcis() -> list:
    bureau = os.path.join(os.path.expanduser("~"), "Desktop")
    demarrer = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                            "Start Menu", "Programs")
    return [d for d in (bureau, demarrer) if os.path.isdir(d)]


def poser_raccourcis():
    """Par WScript.Shell : c'est l'objet COM que Windows fournit d'origine, et
    il évite d'ajouter une dépendance pour écrire trois octets de .lnk."""
    poses = []
    for d in dossiers_raccourcis():
        lnk = os.path.join(d, NOM_AFFICHE + ".lnk")
        ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut(%s);"
              "$s.TargetPath=%s; $s.WorkingDirectory=%s; $s.IconLocation=%s;"
              "$s.Description='Éditeur PDF BPO'; $s.Save()"
              % (_ps(lnk), _ps(CIBLE), _ps(CIBLE_DIR), _ps(CIBLE + ",0")))
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, text=True)
        if r.returncode == 0 and os.path.isfile(lnk):
            poses.append(lnk)
    return poses


def _ps(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def retirer_raccourcis():
    retires = []
    for d in dossiers_raccourcis():
        lnk = os.path.join(d, NOM_AFFICHE + ".lnk")
        if os.path.isfile(lnk):
            try:
                os.remove(lnk); retires.append(lnk)
            except OSError:
                pass
    return retires


# ---------------------------------------------------------------- actions
def version_du_build() -> str:
    horo = "inconnue"
    if os.path.isfile(SOURCE):
        import datetime
        horo = datetime.datetime.fromtimestamp(os.path.getmtime(SOURCE)).strftime("%Y-%m-%d %H:%M")
    court = ""
    try:
        r = subprocess.run(["git", "-C", ICI, "log", "-1", "--format=%h"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            court = " " + r.stdout.strip()
    except Exception:
        pass
    return "1.0.0 (%s%s)" % (horo, court)


def installer(diffuser: bool):
    if processus_en_cours():
        stop("L'Éditeur PDF BPO est en cours d'exécution.\n"
             "  Fermez toutes ses fenêtres, puis relancez : python installer.py")
    if not os.path.isfile(SOURCE) or os.path.getsize(SOURCE) < 40 * 1024 * 1024:
        stop("dist\\%s est introuvable ou incomplet.\n"
             "  Lancez d'abord : python build.py" % NOM_FICHIER)

    version = version_du_build()
    os.makedirs(CIBLE_DIR, exist_ok=True)
    # Copie puis bascule : jamais d'exécutable à moitié écrit à l'arrivée.
    temp = CIBLE + ".neuf"
    shutil.copy2(SOURCE, temp)
    os.replace(temp, CIBLE)
    echo("  Installé   : %s" % CIBLE)
    echo("  Version    : %s" % version)

    enregistrer(version)
    prevenir_le_shell()
    echo("  Registre   : enregistré pour « Ouvrir avec » et les Paramètres")

    for lnk in poser_raccourcis():
        echo("  Raccourci  : %s" % lnk)

    if diffuser:
        if os.path.isdir(os.path.dirname(DIFFUSION)):
            shutil.copy2(SOURCE, DIFFUSION)
            echo("  Diffusion  : %s" % DIFFUSION)
        else:
            echo("  Diffusion  : dossier introuvable, ignoré")

    echo()
    echo("  Lancez l'application par son raccourci, jamais par un exe trouvé")
    echo("  dans Dropbox : Windows n'a qu'une entrée pour tous les exemplaires")
    echo("  qui portent le même nom de fichier.")


def desinstaller():
    if processus_en_cours():
        stop("L'Éditeur PDF BPO est en cours d'exécution. Fermez-le d'abord.")
    for lnk in retirer_raccourcis():
        echo("  Raccourci retiré : %s" % lnk)
    for cle in (r"Software\Classes\Applications\\" + NOM_FICHIER,
                r"Software\Classes\\" + PROGID,
                r"Software\BPO\Editeur PDF BPO",
                CLE_DESINST):
        effacer_arbre(cle)
    for chemin, nom in ((r"Software\Classes\.pdf\OpenWithProgids", PROGID),
                        (r"Software\RegisteredApplications", APPID)):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chemin, 0, winreg.KEY_WRITE) as k:
                winreg.DeleteValue(k, nom)
        except OSError:
            pass
    echo("  Registre nettoyé")
    if os.path.isdir(CIBLE_DIR):
        shutil.rmtree(CIBLE_DIR, ignore_errors=True)
        echo("  Dossier retiré   : %s" % CIBLE_DIR)
    prevenir_le_shell()
    echo()
    echo("  Le choix de l'application par défaut, lui, reste à Windows :")
    echo("  s'il pointait ici, Windows vous en redemandera une au prochain PDF.")


def etat():
    echo("  Source du build : %s" % (SOURCE if os.path.isfile(SOURCE) else "(absente)"))
    echo("  Installé        : %s" % (CIBLE if os.path.isfile(CIBLE) else "(non)"))
    cmd = lire(r"Software\Classes\Applications\\" + NOM_FICHIER + r"\shell\open\command")
    echo("  Commande        : %s" % (cmd or "(aucune)"))
    if cmd and CIBLE.lower() not in cmd.lower():
        echo("     ⚠ elle ne désigne PAS l'exemplaire installé — relancez installer.py")
    echo("  Version posée   : %s" % (lire(CLE_DESINST, "DisplayVersion") or "(aucune)"))
    for d in dossiers_raccourcis():
        lnk = os.path.join(d, NOM_AFFICHE + ".lnk")
        echo("  Raccourci       : %s" % (lnk if os.path.isfile(lnk) else "(absent de %s)" % d))
    echo("  En cours        : %s" % ("oui" if processus_en_cours() else "non"))


def main():
    if os.name != "nt":
        stop("Ce script installe l'application sous Windows.\n"
             "  Sur Mac, glissez l'application du .dmg vers Applications.")
    echo()
    echo("  Éditeur PDF BPO — installation pour %s" % os.environ.get("USERNAME", "cet utilisateur"))
    echo()
    if "--etat" in sys.argv:
        etat()
    elif "--desinstaller" in sys.argv:
        desinstaller()
    else:
        installer("--diffuser" in sys.argv)
    echo()


if __name__ == "__main__":
    main()
