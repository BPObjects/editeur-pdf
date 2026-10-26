# SPDX-License-Identifier: AGPL-3.0-or-later
"""Banc du veilleur d'impression : un gros tirage ne doit pas être tronqué.

    python banc/impression.py              le banc
    python banc/impression.py --sabotages  …puis on remet le défaut d'origine

CE QUE CE BANC DÉFEND. L'imprimante « PDF BPO » écrit toujours au même fichier,
et le veilleur le ramasse. La question est : QUAND un tirage est-il fini ?

La première réponse — « quand la taille n'a plus bougé depuis deux secondes » —
était fausse, et elle a coûté quatre tirages à AL les 18 et 19 octobre. Sur un
gros tirage, Archicad met plus de deux secondes à préparer la planche suivante,
et le spouleur vide son tampon par tranches d'un mégaoctet. Le veilleur
concluait « terminé », renommait le fichier, et la suite de l'impression
n'avait plus où aller.

La preuve était dans les tailles : 9 437 184, 9 437 184, 15 728 640 et
17 825 792 octets — 9, 9, 15 et 17 mégaoctets PILE. Des frontières de tampon.
Aucun ne portait « %%EOF », aucun n'était lisible.

Ce banc rejoue ce scénario : une écriture en tranches, une PAUSE plus longue
que l'ancien critère, et la marque de fin seulement à la fin.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import time

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
sys.path.insert(0, os.path.dirname(ICI))

from commun import Banc                                        # noqa: E402
import veilleur                                                # noqa: E402

TRANCHE = b"x" * (1024 * 1024)          # le spouleur écrit par mégaoctet
FIN_PDF = b"\ntrailer\n<<>>\nstartxref\n9\n%%EOF\n"


class Veille:
    """Fait tourner le vrai veilleur sur un dossier à nous, sans rien ouvrir."""

    def __init__(self):
        self.dossier = tempfile.mkdtemp(prefix="banc-impression-")
        self.attendu = os.path.join(self.dossier, "impression.pdf")
        self.ouverts = []
        self._gardes = (veilleur.DOSSIER, veilleur.ATTENDU, veilleur.ouvrir)
        veilleur.DOSSIER = self.dossier
        veilleur.ATTENDU = self.attendu
        veilleur.ouvrir = self.ouverts.append          # on note, on n'ouvre pas
        self.fil = threading.Thread(target=veilleur.boucle, daemon=True)
        self.fil.start()
        time.sleep(0.5)

    def tirages(self):
        return sorted(f for f in os.listdir(self.dossier) if f != "impression.pdf")

    def fermer(self):
        veilleur.DOSSIER, veilleur.ATTENDU, veilleur.ouvrir = self._gardes
        shutil.rmtree(self.dossier, ignore_errors=True)


def _ajouter(chemin: str, bloc: bytes):
    """Écrit une tranche PUIS REFERME, comme le fait le spouleur.

    Garder le fichier ouvert tout du long fausserait le banc : sous Windows,
    une poignée ouverte sans FILE_SHARE_DELETE empêche le renommage — le
    veilleur semblerait alors sage pour une raison qui n'est pas la sienne, et
    le sabotage ne mordrait pas. Mesuré : le premier jet de ce banc passait au
    vert même avec le critère fautif remis.
    """
    with open(chemin, "ab") as f:
        f.write(bloc)
        f.flush()
        os.fsync(f.fileno())


def banc_gros_tirage(b: Banc):
    """Le cas qui a échoué : des tranches, une longue pause, la fin après."""
    v = Veille()
    try:
        _ajouter(v.attendu, b"%PDF-1.4\n" + TRANCHE)
        # Archicad prépare la planche suivante. L'ancien critère — deux regards
        # à une seconde d'intervalle — se déclenchait ICI.
        time.sleep(5)
        pendant = v.tirages()
        taille_pendant = os.path.getsize(v.attendu) if os.path.exists(v.attendu) else 0
        _ajouter(v.attendu, TRANCHE)
        time.sleep(4)
        pendant2 = v.tirages()
        _ajouter(v.attendu, FIN_PDF)                    # fin du document
        time.sleep(6)
        apres = v.tirages()

        b.dire("pendant la pause de 5 s, rien n'est ramassé", pendant, [])
        b.dire("...alors que le fichier était à une frontière de tampon",
               taille_pendant % (1024 * 1024) == 9, True)
        b.dire("après la 2e tranche non plus", pendant2, [])
        b.dire("une fois la marque de fin écrite, le tirage est ramassé",
               len(apres), 1)
        if apres:
            p = os.path.join(v.dossier, apres[0])
            n = os.path.getsize(p)
            b.dire("le tirage ramassé est ENTIER",
                   n, 9 + 2 * len(TRANCHE) + len(FIN_PDF))
            b.dire("...il porte sa marque de fin", veilleur.pdf_complet(p), True)
            b.dire("...et il a été présenté une fois", len(v.ouverts), 1)
        b.dire("le chemin du port est libéré pour le tirage suivant",
               os.path.exists(v.attendu), False)
    finally:
        v.fermer()


def banc_petit_tirage(b: Banc):
    """Le cas courant ne doit pas devenir lent pour autant."""
    v = Veille()
    try:
        t0 = time.time()
        with open(v.attendu, "wb") as f:
            f.write(b"%PDF-1.4\n" + b"y" * 50000 + FIN_PDF)
        for _ in range(80):
            time.sleep(0.25)
            if v.tirages():
                break
        delai = time.time() - t0
        b.dire("un petit tirage est ramassé", len(v.tirages()), 1)
        b.dire("...en moins de dix secondes", delai < 10, True)
    finally:
        v.fermer()


SABOTAGE = ("on revient au critere d'origine : la taille seule",
            lambda: setattr(veilleur, "pdf_complet", lambda chemin: True),
            ["pendant la pause de 5 s, rien n'est ramassé",
             "le tirage ramassé est ENTIER"])


def main():
    b = Banc("VEILLEUR D'IMPRESSION")
    banc_gros_tirage(b)
    banc_petit_tirage(b)
    ok = b.bilan()

    muet = 0
    if "--sabotages" in sys.argv:
        print("\n=== SABOTAGE : le banc mord-il ? ===")
        nom, casser, vises = SABOTAGE
        garde = veilleur.pdf_complet
        casser()
        import contextlib
        import io as _io
        with contextlib.redirect_stdout(_io.StringIO()):
            bb = Banc()
            try:
                banc_gros_tirage(bb)
            except Exception:
                pass
        veilleur.pdf_complet = garde
        joues = [n for n, _ in bb.lignes]
        absents = set(vises) - set(joues)
        tombes = set(bb.tombes) & set(vises)
        etat = ("%d témoin(s) visé(s) tombé(s) : %s" % (len(tombes), ", ".join(sorted(tombes)))) \
            if tombes else ">>> AUCUN TÉMOIN NE TOMBE <<<"
        if absents:
            etat += "  [JAMAIS JOUÉ : %s]" % ", ".join(sorted(absents))
        print("  %-44s %s" % (nom, etat))
        muet = 0 if tombes else 1
        print("\n  %d sabotage(s) sur 1 passent inaperçus" % muet)

    sys.exit(0 if (ok and not muet) else 1)


if __name__ == "__main__":
    main()
