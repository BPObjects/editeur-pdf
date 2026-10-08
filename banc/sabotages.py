# SPDX-License-Identifier: AGPL-3.0-or-later
"""Saboter le code AVANT d'annoncer un banc vert.

Un banc qui ne mord pas ne protège rien. Chaque sabotage remet sciemment un
défaut que le code corrige, et doit faire tomber le témoin qui le vise.

DEUX PIÈGES DU HARNAIS LUI-MÊME, payés ailleurs et évités ici :
  · un témoin qui n'a PAS TOURNÉ n'est pas un témoin vert — si le banc s'arrête
    en route, les suivants sont absents, et compter les seuls tombés lit cette
    absence comme un silence rassurant ;
  · on ne peut remplacer qu'une DÉCLARATION de fonction : elle atterrit sur
    l'objet global. Un `const` fléché de premier niveau vit dans l'environnement
    lexical — lisible depuis une autre évaluation, pas remplaçable.
"""
from __future__ import annotations

import contextlib
import io
import time


# --- ce qu'on casse côté serveur : des fonctions de module, remplaçables ----
def _sans_quadrilateres(m):
    m._texte_porte = lambda page, a: " ".join(page.get_text("text", clip=a.rect).split())[:300]


def _sans_analyse_de_date(m):
    m._date_pdf = lambda s: s or ""


def _sans_couleur(m):
    m._couleur_annot = lambda a: ""


SERVEUR = [
    ("le texte porté revient à la boîte d'ensemble", _sans_quadrilateres,
     ["texte porté par le surlignage"]),
    ("les dates ne sont plus analysées", _sans_analyse_de_date,
     ["date complète", "date sans heure", "date illisible rendue vide, pas inventée"]),
    ("la couleur n'est plus lue", _sans_couleur, ["couleur du cadre"]),
]

INTERFACE = [
    ("les repères ne sont plus dessinés",
     "window.dessinerReperes = () => {};",
     ["huit repères posés sur les pages", "...et marque son repère"]),
    ("le filtre par relecteur ne filtre plus",
     "window.cmRetenus = () => CM.map((c, k) => ({ c, k }));",
     ["filtrer un relecteur ne laisse que ses fiches", "...et que ses repères"]),
    ("la pastille n'annonce plus rien",
     "window.majPastilleCommentaires = () => {};",
     ["la pastille annonce le nombre, sans entrer dans le mode"]),
]


def _mordre(nom, attendus, joues, tombes, incident):
    absents = set(attendus) - set(joues)
    vises = set(tombes) & set(attendus)
    etat = ("%d témoin(s) visé(s) tombé(s) : %s" % (len(vises), ", ".join(sorted(vises)))) \
        if vises else ">>> AUCUN TÉMOIN NE TOMBE <<<"
    if absents:
        etat += "  [JAMAIS JOUÉ : %s]" % ", ".join(sorted(absents))
    if incident:
        etat += "  [banc arrêté : %s]" % incident
    print("  %-46s %s" % (nom, etat))
    return bool(vises)


def _rejouer(fabrique):
    """Rejoue un banc en silence et rend (témoins joués, témoins tombés, incident)."""
    incident = None
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            b = fabrique()
            return [n for n, _ in b.lignes], b.tombes, None
        except Exception as e:
            incident = "%s: %s" % (type(e).__name__, str(e)[:90])
    return [], [], incident


def passer(banc_serveur, banc_interface, port, nav, attendre_interface, reference):
    import serveur as mod
    print("\n=== SABOTAGES : le banc mord-il ? ===")
    muets = 0
    ref = set(reference)

    gardes = {k: getattr(mod, k) for k in ("_texte_porte", "_date_pdf", "_couleur_annot")}
    for nom, casser, attendus in SERVEUR:
        casser(mod)
        joues, tombes, incident = _rejouer(lambda: banc_serveur(port))
        muets += not _mordre(nom, attendus, joues, set(tombes) - ref, incident)
        for k, v in gardes.items():
            setattr(mod, k, v)

    for nom, code, attendus in INTERFACE:
        nav.js("location.reload(); return 1", attendre=False)
        time.sleep(2.5)
        attendre_interface(nav)
        nav.js(code + " return 1")
        joues, tombes, incident = _rejouer(lambda: banc_interface(nav))
        muets += not _mordre(nom, attendus, joues, set(tombes) - ref, incident)

    total = len(SERVEUR) + len(INTERFACE)
    print("\n  %d sabotage(s) sur %d passent inaperçus" % (muets, total))
    return muets
