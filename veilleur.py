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


def pdf_complet(chemin: str) -> bool:
    """Le PDF est-il ENTIER ? On cherche sa marque de fin, « %%EOF ».

    C'EST LE CŒUR DU PROBLÈME, et il a coûté quatre tirages. Juger qu'une
    impression est finie parce que la taille n'a pas bougé pendant deux
    secondes est faux : sur un gros tirage, Archicad met bien plus que cela à
    préparer la planche suivante, et le spouleur vide son tampon par tranches
    d'un mégaoctet. Le veilleur concluait « terminé », renommait le fichier, et
    la suite de l'impression n'avait plus où aller.

    La preuve était dans les tailles : quatre fichiers du 18 au 19 octobre
    pesaient 9, 9, 15 et 17 mégaoctets PILE — des frontières de tampon — sans
    « %%EOF » et illisibles. Un PDF entier ne tombe jamais sur un compte rond.

    Un PDF se termine par sa table de références et « %%EOF ». Tant que cette
    marque n'est pas là, le document n'est pas fini : c'est le seul critère qui
    porte, et il ne dépend d'aucun délai.
    """
    try:
        taille = os.path.getsize(chemin)
        if taille < 1024:
            return False
        with open(chemin, "rb") as f:
            f.seek(max(0, taille - 4096))
            return b"%%EOF" in f.read()
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
    ouvrir(cible)
    return True


def ouvrir(cible: str):
    """Montre le tirage. Fonction à part pour que le banc puisse la remplacer :
    éprouver la veille ne doit pas ouvrir de fenêtres."""
    if os.path.isfile(EDITEUR):
        try:
            subprocess.Popen([EDITEUR, cible], close_fds=True)
            dire("ouvert dans l'éditeur")
        except Exception as e:
            dire("ouverture impossible : %s" % e)
        return
    # L'éditeur n'est pas installé à l'endroit attendu : on laisse Windows
    # décider plutôt que de perdre l'impression.
    try:
        os.startfile(cible)
    except Exception:
        pass


def boucle():
    os.makedirs(DOSSIER, exist_ok=True)
    dire("veille sur %s" % DOSSIER)
    tailles = []
    # En mode « une fois » on tourne quand même quelques secondes : il faut au
    # moins deux regards pour constater qu'un fichier a fini d'être écrit.
    une_fois = "--une-fois" in sys.argv
    fin = time.time() + 12
    attente_depuis = None        # depuis quand un tirage est-il en cours ?
    dernier_mot = 0.0            # dernière fois qu'on l'a dit au journal
    while True:
        try:
            if os.path.isfile(ATTENDU):
                t = os.path.getsize(ATTENDU)
                tailles.append(t)
                if len(tailles) > STABLE:
                    tailles.pop(0)
                # Un tirage est fini quand le PDF porte sa marque de fin, que le
                # spouleur l'a lâché, et que la taille ne bouge plus. Les trois,
                # et dans cet ordre d'importance : la marque de fin ne dépend
                # d'aucun délai, les deux autres ne sont que des ceintures.
                assez_stable = len(tailles) == STABLE and len(set(tailles)) == 1
                if t > 0 and pdf_complet(ATTENDU) and libre(ATTENDU) and assez_stable:
                    if traiter(ATTENDU):
                        tailles = []
                        attente_depuis = None
                        if une_fois:
                            return
                elif t > 0:
                    # On le dit une fois, puis toutes les trente secondes : un
                    # gros tirage prend du temps, et un silence total ne permet
                    # pas de distinguer « ça travaille » de « c'est bloqué ».
                    maintenant = time.time()
                    if attente_depuis is None:
                        attente_depuis = maintenant
                        dernier_mot = 0.0
                        dire("impression en cours (%.1f Mo)…" % (t / 1e6))
                    elif maintenant - dernier_mot > 30:
                        dernier_mot = maintenant
                        dire("toujours en cours depuis %.0f s, %.1f Mo%s"
                             % (maintenant - attente_depuis, t / 1e6,
                                "" if pdf_complet(ATTENDU) else " (pas encore de %%EOF)"))
            else:
                tailles = []
                attente_depuis = None
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
