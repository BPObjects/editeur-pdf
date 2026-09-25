# SPDX-License-Identifier: AGPL-3.0-or-later
"""Surveille le dossier de l'imprimante « PDF BPO » et ouvre ce qui y tombe.

    pythonw veilleur.py            surveille en silence (usage normal, au démarrage)
    python  veilleur.py --console  surveille en affichant ce qu'il fait
    python  veilleur.py --une-fois traite ce qui est déjà là, puis s'arrête

POURQUOI CE PROGRAMME EXISTE. Windows ne sait pas fabriquer une imprimante qui
appelle une application : un port d'impression écrit dans un FICHIER, et rien
de plus. L'imprimante « PDF BPO » écrit donc toujours au même endroit, et ce
veilleur fait le reste — il attend que le fichier soit complet, lui donne un nom
daté, et l'ouvre dans l'éditeur.

Un vrai pilote d'imprimante virtuelle ferait cela seul, mais il faut le signer
et l'installer en administrateur. Ce détour ne demande aucun de ces deux droits.
"""
from __future__ import annotations

import datetime
import os
import subprocess
import sys
import time

DOSSIER = os.path.join(os.path.expanduser("~"), "Documents", "Impressions BPO")
ATTENDU = os.path.join(DOSSIER, "impression.pdf")
def _editeur() -> str:
    """Quand le veilleur tourne DANS l'exécutable empaqueté, l'éditeur est cet
    exécutable même : inutile d'en chercher un autre, et cela évite d'exiger
    Python sur le poste d'un collègue."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs",
                        "Editeur PDF BPO", "Editeur PDF BPO.exe")


EDITEUR = _editeur()
PAUSE = 1.0          # secondes entre deux regards
STABLE = 2           # nombre de regards consécutifs à taille identique


def dire(msg: str):
    if "--console" in sys.argv or "--une-fois" in sys.argv:
        print(time.strftime("%H:%M:%S"), msg, flush=True)


def libre(chemin: str) -> bool:
    """Le spouleur a-t-il lâché le fichier ? Tant qu'il écrit, il le verrouille."""
    try:
        with open(chemin, "r+b"):
            return True
    except OSError:
        return False


def nom_date() -> str:
    h = datetime.datetime.now()
    return h.strftime("Impression %Y-%m-%d %Hh%M-%S.pdf")


def traiter(chemin: str) -> bool:
    """Renomme puis ouvre. Le renommage vient en PREMIER : il libère le chemin
    du port, sans quoi l'impression suivante trouverait le fichier occupé."""
    cible = os.path.join(DOSSIER, nom_date())
    n = 1
    while os.path.exists(cible):
        n += 1
        cible = os.path.join(DOSSIER, nom_date().replace(".pdf", " (%d).pdf" % n))
    try:
        os.replace(chemin, cible)
    except OSError as e:
        dire("renommage impossible (%s), on réessaiera" % e)
        return False
    dire("reçu : %s" % os.path.basename(cible))
    if os.path.isfile(EDITEUR):
        try:
            subprocess.Popen([EDITEUR, cible], close_fds=True)
            dire("ouvert dans l'éditeur")
        except Exception as e:
            dire("ouverture impossible : %s" % e)
    else:
        # L'éditeur n'est pas installé à l'endroit attendu : on laisse Windows
        # décider plutôt que de perdre l'impression.
        try:
            os.startfile(cible)
        except Exception:
            pass
    return True


def boucle():
    os.makedirs(DOSSIER, exist_ok=True)
    dire("veille sur %s" % DOSSIER)
    tailles = []
    # En mode « une fois » on tourne quand même quelques secondes : il faut au
    # moins deux regards pour constater qu'un fichier a fini d'être écrit.
    une_fois = "--une-fois" in sys.argv
    fin = time.time() + 12
    while True:
        try:
            if os.path.isfile(ATTENDU):
                t = os.path.getsize(ATTENDU)
                tailles.append(t)
                if len(tailles) > STABLE:
                    tailles.pop(0)
                # complet = taille non nulle, stable, et plus verrouillée
                if len(tailles) == STABLE and len(set(tailles)) == 1 and t > 0 and libre(ATTENDU):
                    if traiter(ATTENDU):
                        tailles = []
                        if une_fois:
                            return
            else:
                tailles = []
                if une_fois and time.time() > fin:
                    dire("rien à traiter")
                    return
        except Exception as e:
            dire("incident : %s" % e)
        if une_fois and time.time() > fin:
            dire("rien à traiter")
            return
        time.sleep(PAUSE)


def main():
    if os.name != "nt":
        print("Ce veilleur accompagne l'imprimante « PDF BPO », qui est propre à Windows.")
        return
    boucle()


if __name__ == "__main__":
    main()
