# SPDX-License-Identifier: AGPL-3.0-or-later
"""Banc du mode « Commentaires » : lire les annotations d'un PDF relu.

    python banc/commentaires.py              le banc
    python banc/commentaires.py --sabotages  le banc, puis on casse le code exprès

Un banc vert ne vaut rien tant qu'il n'a pas mordu : les sabotages remettent
sciemment les défauts que ce code corrige, et chacun doit faire tomber le témoin
qui le vise.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import time
import urllib.request

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

import sabotages                                              # noqa: E402
from cdp import Navigateur                                    # noqa: E402
from commun import Banc, LARG, HAUT, attendre_interface, demarrer_serveur, ouvrir_pdf  # noqa: E402

PDF = os.path.join(ICI, "essai-commente.pdf")


# ===================================================================== serveur
def banc_serveur(port: int) -> Banc:
    """Ce que l'API rend, sans passer par l'interface."""
    b = Banc("LECTURE DES ANNOTATIONS (serveur)")
    octets = io.open(PDF, "rb").read()
    req = urllib.request.Request("http://127.0.0.1:%d/api/ouvrir" % port, data=octets,
                                 headers={"Content-Type": "application/octet-stream",
                                          "X-Nom": "essai-commente.pdf"})
    e = json.load(urllib.request.urlopen(req, timeout=30))
    cs = json.load(urllib.request.urlopen(
        "http://127.0.0.1:%d/api/doc/%s/commentaires" % (port, e["id"]), timeout=30))["commentaires"]
    par = lambda g: next((c for c in cs if c["genre"] == g), {})

    b.dire("huit commentaires lus", len(cs), 8)
    b.dire("trois relecteurs distincts", len({c["auteur"] for c in cs}), 3)
    b.dire("la page sans annotation n'en rend aucune",
           [c for c in cs if c["page"] == 2], [])
    b.dire("la page tournée rend la sienne",
           len([c for c in cs if c["page"] == 3]), 1)
    # Le texte PORTÉ : sans lui, « Lire 56 m2 » ne dit pas sur quoi il porte.
    b.dire("texte porté par le surlignage", par("Surlignage").get("texte"), "443 m2")
    b.dire("texte porté par le souligné", par("Souligné").get("texte"), "CMU de 3 T")
    b.dire("texte porté par le barré", par("Barré").get("texte"), "75 m2")
    # Les dates : PDF les écrit « D:AAAAMMJJHHMMSS+zz'zz' ».
    b.dire("date complète", par("Note").get("date"), "07/10/2026 14:30")
    b.dire("date sans heure", par("Surlignage").get("date"), "08/10/2026")
    b.dire("date illisible rendue vide, pas inventée", par("Dessin").get("date"), "")
    b.dire("couleur du cadre", par("Rectangle").get("couleur"), "#ff0000")
    b.dire("une bulle Popup n'est pas comptée pour un commentaire",
           [c for c in cs if c["type"] == "Popup"], [])
    return b


# ================================================================== interface
def banc_interface(nav) -> Banc:
    b = Banc("MODE COMMENTAIRES (interface)")
    ouvrir_pdf(nav, PDF)
    time.sleep(1.2)

    b.dire("la pastille annonce le nombre, sans entrer dans le mode",
           nav.js("return document.querySelector('#cm-pastille').textContent"), "8")
    b.dire("...et elle est visible",
           nav.js("return !document.querySelector('#cm-pastille').classList.contains('masque')"), True)

    nav.js("setMode('commentaires'); return 1")
    time.sleep(1.2)
    b.dire("le panneau s'ouvre",
           nav.js("return !document.querySelector('#pan-commentaires').classList.contains('masque')"), True)
    b.dire("huit fiches dans la liste",
           nav.js("return document.querySelectorAll('#cm-liste .cm').length"), 8)
    b.dire("le filtre propose les trois relecteurs, plus « tous »",
           nav.js("return document.querySelectorAll('#cm-qui option').length"), 4)

    r = nav.js("""
      const d = [...document.querySelectorAll('#cm-liste .cm')].find(x => x.textContent.includes('443 m2'));
      if (!d) return null;
      return {auteur: d.querySelector('b').textContent,
              ou: d.querySelector('.ou').textContent,
              porte: d.querySelector('.porte') ? d.querySelector('.porte').textContent : null,
              dit: d.querySelector('.dit') ? d.querySelector('.dit').textContent : null};
    """)
    b.dire("la fiche nomme son auteur", (r or {}).get("auteur"), "Marie DUBOIS")
    b.dire("...dit la page et le genre", (r or {}).get("ou"), "page 1 · Surlignage")
    b.dire("...montre le texte porté", (r or {}).get("porte"), "443 m2")
    b.dire("...et ce que le relecteur en dit", (r or {}).get("dit"),
           "Le programme dit 450 m2 au chapitre 4.")

    b.dire("huit repères posés sur les pages",
           nav.js("return document.querySelectorAll('#pile .repere').length"), 8)
    b.dire("la page sans commentaire n'en porte aucun",
           nav.js("""const d = [...document.querySelectorAll('#pile .page')].find(x => +x.dataset.i === 2);
                     return d ? d.querySelectorAll('.repere').length : -1;"""), 0)

    # Le repère est posé en coordonnées de page : sa largeur à l'écran doit
    # suivre le zoom. On compare au RAPPORT DES ZOOMS et non à un facteur
    # supposé : zoomFixe() pose une valeur ABSOLUE, et le document s'ouvre
    # ajusté à la page — pas à 100 %.
    # Chaque lecture tolère l'ABSENCE de repère : sans cela le banc lève et
    # s'arrête, et tous les témoins suivants disparaissent — ce qui se lit
    # ensuite comme un silence rassurant au lieu d'un défaut.
    lire = """const r = document.querySelector('#pile .repere');
              return r ? {l: r.getBoundingClientRect().width, z: S.zoom} : null;"""
    avant = nav.js(lire)
    nav.js("zoomFixe(2); return 1")
    time.sleep(1.0)
    apres = nav.js(lire)
    if avant and apres and avant["z"]:
        b.proche("le repère suit le zoom", apres["l"], avant["l"] * (apres["z"] / avant["z"]), 0.03)
    else:
        b.dire("le repère suit le zoom", "aucun repère à mesurer", True)
    nav.js("zoomFixe(1); return 1")
    time.sleep(0.8)

    nav.js("""const d = [...document.querySelectorAll('#cm-liste .cm')].find(x => x.textContent.includes('voie pompier'));
              d.click(); return 1;""")
    time.sleep(1.2)
    b.dire("cliquer une fiche amène à sa page", nav.js("return S.page"), 1)
    b.dire("...et marque son repère",
           nav.js("return document.querySelectorAll('#pile .repere.vise').length"), 1)
    b.dire("...et marque sa fiche",
           nav.js("return document.querySelectorAll('#cm-liste .cm.vise').length"), 1)

    nav.js("""const s = document.querySelector('#cm-qui'); s.value = 'Marie DUBOIS'; s.onchange(); return 1;""")
    time.sleep(0.7)
    b.dire("filtrer un relecteur ne laisse que ses fiches",
           nav.js("return document.querySelectorAll('#cm-liste .cm').length"), 3)
    b.dire("...et que ses repères",
           nav.js("return document.querySelectorAll('#pile .repere').length"), 3)
    nav.js("""const s = document.querySelector('#cm-qui'); s.value = ''; s.onchange(); return 1;""")
    time.sleep(0.6)

    # Quitter le mode doit enlever les repères : ils gêneraient l'édition.
    nav.js("setMode('select'); return 1")
    time.sleep(0.8)
    b.dire("quitter le mode retire les repères",
           nav.js("return document.querySelectorAll('#pile .repere').length"), 0)
    return b


# =================================================================== sabotages
def main():
    if not os.path.isfile(PDF):
        subprocess.check_call([sys.executable, os.path.join(ICI, "faire-pdf-commente.py")])
    srv, port = demarrer_serveur()
    nav = None
    try:
        b1 = banc_serveur(port)
        b1.bilan()
        nav = Navigateur("http://127.0.0.1:%d/" % port, LARG, HAUT)
        attendre_interface(nav)
        b2 = banc_interface(nav)
        b2.bilan()
        tombes = b1.tombes + b2.tombes
        print("\n===== %d témoin(s) sur %d tombé(s) ====="
              % (len(tombes), len(b1.lignes) + len(b2.lignes)))
        muets = 0
        if "--sabotages" in sys.argv:
            muets = sabotages.passer(banc_serveur, banc_interface, port, nav,
                                     attendre_interface, tombes)
        sys.exit(1 if (tombes or muets) else 0)
    finally:
        if nav:
            nav.fermer()
        srv.shutdown()


if __name__ == "__main__":
    main()
