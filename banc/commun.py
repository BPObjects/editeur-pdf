# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ce que tous les bancs partagent : un serveur, un document, des témoins."""
from __future__ import annotations

import base64
import io
import os
import sys
import threading
import time

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(ICI))          # pour importer serveur.py

import serveur                                     # noqa: E402

LARG, HAUT = 1400, 900


def demarrer_serveur():
    srv = serveur.creer_serveur(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.4)
    return srv, srv.server_address[1]


def attendre_interface(nav, secondes=14):
    fin = time.time() + secondes
    while time.time() < fin:
        time.sleep(0.2)
        if nav.js("return typeof S !== 'undefined' && !!document.querySelector('#zone-vue')"):
            return True
    raise RuntimeError("l'interface ne s'est pas chargée")


def ouvrir_pdf(nav, chemin: str, nom: str | None = None):
    """Dépose un PDF dans l'application comme le ferait l'utilisateur : par
    l'API d'ouverture, depuis la page elle-même."""
    b64 = base64.b64encode(io.open(chemin, "rb").read()).decode()
    nav.js("""
      const b = Uint8Array.from(atob('%s'), c => c.charCodeAt(0));
      const e = await api('/api/ouvrir', {method:'POST',
        headers:{'Content-Type':'application/octet-stream','X-Nom':'%s'}, body:b});
      apresOuverture(e);
      return S.pages.length;
    """ % (b64, (nom or os.path.basename(chemin)).replace("'", "")))
    for _ in range(80):
        time.sleep(0.15)
        if nav.js("return document.querySelectorAll('#pile .page').length"):
            break
    time.sleep(0.8)


class Banc:
    """Un témoin porte un NOM, une valeur mesurée et une valeur attendue. On
    n'écrit jamais « ça marche » : on écrit ce qu'on a lu."""

    def __init__(self, titre=""):
        self.lignes = []
        if titre:
            print("\n=== %s ===" % titre)

    def dire(self, nom, obtenu, attendu=True):
        ok = obtenu == attendu
        self.lignes.append((nom, ok))
        print("  %-52s %-6s %r" % (nom, "ok" if ok else "FAUX", obtenu))
        return ok

    def proche(self, nom, obtenu, attendu, tol):
        ok = bool(attendu) and abs(obtenu - attendu) / abs(attendu) <= tol
        self.lignes.append((nom, ok))
        print("  %-52s %-6s %.0f (attendu %.0f ±%d%%)"
              % (nom, "ok" if ok else "FAUX", obtenu, attendu, tol * 100))
        return ok

    @property
    def tombes(self):
        return [n for n, ok in self.lignes if not ok]

    def bilan(self):
        print("\n  %d témoin(s) sur %d tombé(s) : %s"
              % (len(self.tombes), len(self.lignes), ", ".join(self.tombes) or "aucun"))
        return not self.tombes
