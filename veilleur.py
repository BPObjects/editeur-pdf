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

SECONDE TÂCHE, depuis le 02/11/2026 : il donne 72 dpi aux images SANS
résolution qui arrivent dans le dossier Téléchargements (Gemini, Copilot…).
Archicad imprime ces images rognées au coin haut-gauche sur un écran à 150 % ;
voir image_dpi.py. Il ne touche jamais une résolution déclarée, ni une image
déjà là quand il démarre, ni un fichier qui n'a pas encore sa marque de fin.
"""
from __future__ import annotations

import datetime
import os
import subprocess
import sys
import time

import image_dpi

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
# Au-delà de ce délai sans que le fichier change NI porte sa marque de fin, on
# tient l'impression pour ÉCHOUÉE : le spouleur l'a abandonnée (événement 372,
# vu le 27/10 avec un tirage de 14 Mo), et le fichier tronqué, laissé sur le
# chemin du port, bloquerait tous les tirages suivants.
ABANDON = 600        # secondes


# ------------------------------------------------- images sans résolution
def _telechargements() -> str:
    """Le VRAI dossier Téléchargements : il peut avoir été déplacé (autre
    disque, OneDrive), et ~/Downloads ne serait alors plus le bon."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD),
                            ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]
            # FOLDERID_Downloads {374DE290-123F-4565-9164-39C4925E467B}
            g = GUID(0x374DE290, 0x123F, 0x4565,
                     (ctypes.c_ubyte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B))
            p = ctypes.c_wchar_p()
            f = ctypes.windll.shell32.SHGetKnownFolderPath
            f.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
                          ctypes.POINTER(ctypes.c_wchar_p)]
            if f(ctypes.byref(g), 0, None, ctypes.byref(p)) == 0 and p.value:
                chemin = p.value
                ctypes.windll.ole32.CoTaskMemFree(p)
                return chemin
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Downloads")


DOSSIERS_IMAGES = [_telechargements()]
EXT_IMAGES = (".jpg", ".jpeg", ".png")
REGARD_IMAGES = 2.0      # secondes entre deux regards sur ces dossiers
DEJA_LA = 600            # au démarrage, une image plus vieille que cela est laissée


class VeilleImages:
    """Tamponne à 72 dpi les images sans résolution qui ARRIVENT dans un dossier.

    Trois prudences, chacune payée ailleurs :
      · une image n'est touchée qu'ENTIÈRE (marque de fin JPEG/PNG) et stable
        sur deux regards — la taille seule ne prouve rien (cf. pdf_complet) ;
      · au démarrage, ce qui est déjà là depuis plus de DEJA_LA est laissé :
        on ne réécrit pas l'historique d'un dossier sans qu'on l'ait demandé ;
      · une résolution DÉCLARÉE n'est jamais réécrite (mode prudent).
    """

    def __init__(self, dossiers):
        self.dossiers = [d for d in dossiers if d]
        self.vus = {}            # chemin -> signature (taille, date) déjà jugée
        self.candidats = {}      # chemin -> signature vue au regard précédent
        self.premier = True
        self.depart = time.time()

    def regarder(self):
        for d in self.dossiers:
            try:
                entrees = list(os.scandir(d))
            except OSError:
                continue
            for e in entrees:
                if not e.name.lower().endswith(EXT_IMAGES):
                    continue
                try:
                    if not e.is_file():
                        continue
                    st = e.stat()
                except OSError:
                    continue
                sig = (st.st_size, st.st_mtime_ns)
                p = e.path
                if self.vus.get(p) == sig:
                    continue
                if self.premier and st.st_mtime < self.depart - DEJA_LA:
                    self.vus[p] = sig
                    continue
                if self.candidats.get(p) != sig or not libre(p):
                    self.candidats[p] = sig          # on attend un regard de plus
                    continue
                self._tamponner(p, sig)
        self.premier = False

    def _tamponner(self, p, sig):
        try:
            modifie, msg = image_dpi.traiter(p, seulement_sans=True)
        except ValueError as e:
            # Pas de marque de fin : soit le fichier s'écrit encore (sa
            # signature changera et on y reviendra), soit il est ainsi fait.
            # Dans les deux cas, on ne le redit pas à chaque regard.
            self.vus[p] = sig
            self.candidats.pop(p, None)
            dire("image %s laissée : %s" % (os.path.basename(p), e))
            return
        except OSError as e:
            dire("image %s : %s, on réessaiera" % (os.path.basename(p), e))
            return
        try:
            st = os.stat(p)
            self.vus[p] = (st.st_size, st.st_mtime_ns)
        except OSError:
            self.vus[p] = sig
        self.candidats.pop(p, None)
        if modifie:
            dire("image %s : %s" % (os.path.basename(p), msg))


def dire(msg: str):
    # Empaqueté, le veilleur parle TOUJOURS : app.py a fait de stdout le journal
    # (%LOCALAPPDATA%\Editeur PDF BPO\journal.txt). Ne parler qu'avec --console
    # a rendu ce journal muet pendant un mois — le 27/10, un tirage de 14 Mo a
    # échoué et il n'y avait pas une ligne pour le dire.
    if getattr(sys, "frozen", False) or "--console" in sys.argv or "--une-fois" in sys.argv:
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


def mettre_de_cote(chemin: str, taille: int) -> bool:
    """Une impression que le spouleur a abandonnée : on la range sous un nom qui
    dit ce qu'elle est, on le dit au journal, et on libère le chemin du port."""
    cible = os.path.join(DOSSIER, time.strftime("TRONQUE %Y-%m-%d %Hh%M-%S.pdf"))
    try:
        os.replace(chemin, cible)
    except OSError as e:
        dire("impression abandonnée, mais impossible à mettre de côté (%s)" % e)
        return False
    dire("IMPRESSION ÉCHOUÉE : %.1f Mo sans marque de fin, rien ne bouge depuis "
         "%d s. Mise de côté sous %s. Windows a sans doute journalisé un "
         "événement 372 (Observateur d'événements > PrintService)."
         % (taille / 1e6, ABANDON, os.path.basename(cible)))
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
    taille_vue = -1              # dernière taille lue…
    change_depuis = 0.0          # …et depuis quand elle n'a pas bougé
    # Les images : pas en mode « une fois », qui ne sert qu'à ramasser un tirage.
    images = None
    if not une_fois and DOSSIERS_IMAGES:
        images = VeilleImages(DOSSIERS_IMAGES)
        dire("images sans résolution : veille sur %s" % ", ".join(images.dossiers))
    regard_images = 0.0
    while True:
        # À part, et avant l'impression : une erreur ici ne doit jamais
        # empêcher de ramasser un tirage.
        if images is not None and time.time() - regard_images >= REGARD_IMAGES:
            regard_images = time.time()
            try:
                images.regarder()
            except Exception as e:
                dire("incident (images) : %s" % e)
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
                    if t != taille_vue:
                        taille_vue, change_depuis = t, maintenant
                    if attente_depuis is None:
                        attente_depuis = maintenant
                        dernier_mot = 0.0
                        dire("impression en cours (%.1f Mo)…" % (t / 1e6))
                    elif maintenant - dernier_mot > 30:
                        dernier_mot = maintenant
                        dire("toujours en cours depuis %.0f s, %.1f Mo%s"
                             % (maintenant - attente_depuis, t / 1e6,
                                "" if pdf_complet(ATTENDU) else " (pas encore de %%EOF)"))
                    # Plus rien ne bouge depuis longtemps, pas de marque de fin,
                    # et plus personne ne tient le fichier : l'impression a
                    # ÉCHOUÉ. On met le fichier de côté — sans quoi il reste sur
                    # le chemin du port et bloque tous les tirages suivants.
                    if (maintenant - change_depuis > ABANDON and libre(ATTENDU)
                            and not pdf_complet(ATTENDU)):
                        if mettre_de_cote(ATTENDU, t):
                            tailles = []
                            attente_depuis = None
                            taille_vue = -1
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
