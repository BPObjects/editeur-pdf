# SPDX-License-Identifier: AGPL-3.0-or-later
"""Installe l'Éditeur PDF BPO pour l'utilisateur courant — Windows, sans droits d'administrateur.

    python installer.py                 installe ou met à jour
    python installer.py --etat          dit ce qui est posé, sans rien écrire
    python installer.py --desinstaller  retire tout
    python installer.py --diffuser      recopie AUSSI le build dans le dossier de diffusion
    python installer.py --diffuser "<dossier>"   dit une fois où, et le retient
    python installer.py --sans-imprimante   installe sans poser l'imprimante « PDF BPO »

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
import time
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
# Le dossier de diffusion — la copie qu'on laisse aux collègues — dépend du
# poste et de l'agence : il n'a rien à faire dans un source publié. On le donne
# une fois, il est retenu à côté du script (fichier ignoré par git).
MEMO_DIFFUSION = os.path.join(ICI, "diffusion.txt")
IMPRIMANTE = "PDF BPO"
PILOTE = "Microsoft Print To PDF"
DOSSIER_IMPR = os.path.join(os.path.expanduser("~"), "Documents", "Impressions BPO")
PORT_IMPR = os.path.join(DOSSIER_IMPR, "impression.pdf")
DEMARRAGE = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                         "Start Menu", "Programs", "Startup")
LNK_VEILLEUR = os.path.join(DEMARRAGE, "Veilleur PDF BPO.lnk")
CLE_DESINST = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\\" + APPID


def argument_apres(drapeau: str):
    """La valeur qui suit un drapeau, si ce n'en est pas un autre."""
    try:
        suivant = sys.argv[sys.argv.index(drapeau) + 1]
    except (ValueError, IndexError):
        return None
    return None if suivant.startswith("-") else suivant


def dossier_diffusion(explicite=None):
    """Par ordre : ce qui est donné sur la ligne de commande (et retenu pour la
    prochaine fois), la variable EDITEUR_PDF_DIFFUSION, puis ce qui est retenu."""
    if explicite:
        try:
            with open(MEMO_DIFFUSION, "w", encoding="utf-8") as f:
                f.write(explicite)
        except OSError:
            pass
        return explicite
    par_env = os.environ.get("EDITEUR_PDF_DIFFUSION", "").strip()
    if par_env:
        return par_env
    try:
        with open(MEMO_DIFFUSION, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def echo(msg=""):
    print(msg)


def stop(msg: str):
    echo()
    echo("  " + msg)
    echo()
    sys.exit(1)


# ---------------------------------------------------------------- l'application tourne-t-elle ?
def instances(avec_veilleur=True) -> list:
    """Les exemplaires en cours, avec leur ligne de commande.

    On lit la LIGNE DE COMMANDE et pas seulement le nom : le veilleur
    d'impression est le même exécutable, lancé avec --veilleur. Sans cette
    distinction, l'installateur se refuserait lui-même à chaque fois, puisque
    c'est lui qui a démarré le veilleur.
    """
    cmd = ("Get-CimInstance Win32_Process -Filter \"Name='%s'\" | "
           "ForEach-Object { $_.ProcessId.ToString() + '|' + $_.CommandLine }" % NOM_FICHIER)
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=40)
    except Exception:
        return []
    sortie = []
    for ligne in (r.stdout or "").splitlines():
        if "|" not in ligne:
            continue
        pid, _, ligne_cmd = ligne.partition("|")
        veilleur = "--veilleur" in ligne_cmd
        if veilleur and not avec_veilleur:
            continue
        sortie.append((pid.strip(), veilleur))
    return sortie


def arreter_veilleur():
    for pid, veilleur in instances():
        if veilleur:
            subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)


def processus_en_cours() -> bool:
    """Une FENÊTRE de travail est-elle ouverte ? Le veilleur ne compte pas : on
    l'arrête et on le relance autour de la mise à jour."""
    if instances(avec_veilleur=False):
        return True
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
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
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


# ---------------------------------------------------------------- imprimante
# Windows ne sait pas faire une imprimante qui APPELLE une application : un port
# d'impression écrit dans un fichier, un point c'est tout. On pose donc une
# imprimante qui écrit toujours au même endroit, et un veilleur qui ramasse.
# Un vrai pilote virtuel ferait cela seul, mais il faudrait le signer et
# l'installer en administrateur ; ce détour ne demande ni l'un ni l'autre.
def _ps(commande: str):
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", commande],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)


def poser_imprimante():
    os.makedirs(DOSSIER_IMPR, exist_ok=True)
    echo("  Dossier    : %s" % DOSSIER_IMPR)

    r = _ps("Get-Printer -Name '%s' -ErrorAction SilentlyContinue" % IMPRIMANTE)
    if IMPRIMANTE not in (r.stdout or ""):
        _ps("Add-PrinterPort -Name %s -ErrorAction SilentlyContinue" % _ps_txt(PORT_IMPR))
        a = _ps("Add-Printer -Name '%s' -DriverName '%s' -PortName %s"
                % (IMPRIMANTE, PILOTE, _ps_txt(PORT_IMPR)))
        if a.returncode != 0:
            echo("  Imprimante : ÉCHEC — %s" % (a.stderr or "").strip().splitlines()[:1])
            return False
    echo("  Imprimante : « %s » (pilote %s)" % (IMPRIMANTE, PILOTE))

    # Le veilleur au démarrage de la session : c'est l'exécutable lui-même,
    # lancé avec --veilleur, donc aucun Python requis sur le poste.
    if os.path.isdir(DEMARRAGE):
        ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut(%s);"
              "$s.TargetPath=%s; $s.Arguments='--veilleur'; $s.WorkingDirectory=%s;"
              "$s.IconLocation=%s; $s.Description='Ramasse les impressions PDF BPO'; $s.Save()"
              % (_ps_txt(LNK_VEILLEUR), _ps_txt(CIBLE), _ps_txt(CIBLE_DIR), _ps_txt(CIBLE + ",0")))
        if _ps(ps).returncode == 0 and os.path.isfile(LNK_VEILLEUR):
            echo("  Veilleur   : lancé à chaque ouverture de session")
    # et tout de suite, sans attendre la prochaine session
    try:
        subprocess.Popen([CIBLE, "--veilleur"], close_fds=True)
        echo("  Veilleur   : démarré")
    except Exception as e:
        echo("  Veilleur   : non démarré (%s)" % e)
    return True


def deposer_imprimante():
    _ps("Remove-Printer -Name '%s' -ErrorAction SilentlyContinue" % IMPRIMANTE)
    _ps("Remove-PrinterPort -Name %s -ErrorAction SilentlyContinue" % _ps_txt(PORT_IMPR))
    echo("  Imprimante retirée : %s" % IMPRIMANTE)
    if os.path.isfile(LNK_VEILLEUR):
        try:
            os.remove(LNK_VEILLEUR); echo("  Veilleur retiré    : %s" % LNK_VEILLEUR)
        except OSError:
            pass
    echo("  Le dossier %s est conservé : il contient vos impressions." % DOSSIER_IMPR)


def _ps_txt(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


# ---------------------------------------------------------------- actions
def version_du_build() -> str:
    horo = "inconnue"
    if os.path.isfile(SOURCE):
        import datetime
        horo = datetime.datetime.fromtimestamp(os.path.getmtime(SOURCE)).strftime("%Y-%m-%d %H:%M")
    court = ""
    try:
        r = subprocess.run(["git", "-C", ICI, "log", "-1", "--format=%h"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
        if r.returncode == 0:
            court = " " + r.stdout.strip()
    except Exception:
        pass
    return "1.0.0 (%s%s)" % (horo, court)


def installer(diffuser: bool):
    # On arrête le veilleur AVANT le contrôle : c'est le même exécutable, il
    # tient donc le fichier qu'on s'apprête à remplacer, et le contrôle de
    # verrou le prendrait pour une fenêtre de travail ouverte.
    arreter_veilleur()
    time.sleep(0.4)
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

    if "--sans-imprimante" not in sys.argv:
        echo()
        poser_imprimante()

    if diffuser:
        dossier = dossier_diffusion(argument_apres("--diffuser"))
        if not dossier:
            echo("  Diffusion  : aucun dossier connu. Donnez-le une fois :")
            echo('               python installer.py --diffuser "<dossier>"')
        elif os.path.isdir(dossier):
            arrivee = os.path.join(dossier, NOM_FICHIER)
            shutil.copy2(SOURCE, arrivee)
            echo("  Diffusion  : %s" % arrivee)
        else:
            echo("  Diffusion  : dossier introuvable, ignoré (%s)" % dossier)

    echo()
    echo("  Lancez l'application par son raccourci, jamais par un exe trouvé")
    echo("  dans Dropbox : Windows n'a qu'une entrée pour tous les exemplaires")
    echo("  qui portent le même nom de fichier.")


def desinstaller():
    if processus_en_cours():
        stop("L'Éditeur PDF BPO est en cours d'exécution. Fermez-le d'abord.")
    arreter_veilleur()
    deposer_imprimante()
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
    ins = instances()
    echo("  Fenêtres        : %d" % len([1 for _, v in ins if not v]))
    echo("  Veilleur actif  : %s" % ("oui" if any(v for _, v in ins) else "non"))
    r = _ps("Get-Printer -Name '%s' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty PortName" % IMPRIMANTE)
    port = (r.stdout or "").strip()
    echo("  Imprimante      : %s" % (("« %s » → %s" % (IMPRIMANTE, port)) if port else "(absente)"))
    echo("  Veilleur        : %s" % ("au démarrage" if os.path.isfile(LNK_VEILLEUR) else "(pas au démarrage)"))
    diff = dossier_diffusion()
    echo("  Diffusion       : %s" % (diff if diff else "(aucun dossier retenu)"))
    if os.path.isdir(DOSSIER_IMPR):
        n = len([f for f in os.listdir(DOSSIER_IMPR) if f.lower().endswith(".pdf")])
        echo("  Impressions     : %d fichier(s) dans %s" % (n, DOSSIER_IMPR))


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
