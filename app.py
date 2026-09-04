#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Éditeur PDF BPO — Copyright (C) 2026 BPO / Antoine Lacronique
# Logiciel libre sous GNU AGPL v3 ou ultérieure, sans aucune garantie (voir LICENSE).
"""Éditeur PDF BPO — application bureau.

Le serveur local (serveur.py) tourne dans un fil, sur un port libre ; la fenêtre
native (pywebview, WebView2 sous Windows) affiche l'interface. Les boîtes de
dialogue Ouvrir / Enregistrer sont celles du système : les fichiers sont lus et
écrits directement, sans passer par un téléchargement.

    python app.py [fichier.pdf ...]
"""
from __future__ import annotations

import os
import sys
import threading
import webbrowser

import webview

import serveur


def _nom(chemin: str) -> str:
    return os.path.basename(chemin)


class Api:
    """Méthodes appelées depuis la page via window.pywebview.api.*

    La fenêtre est rangée sous un nom PRIVÉ : pywebview parcourt les attributs
    publics de cet objet pour construire l'API JavaScript, et un objet Window
    l'entraîne dans une récursion sans fin à travers l'objet .NET sous-jacent
    (window.native.DefaultFont.FontFamily…), ce qui fige la fenêtre au démarrage.
    """

    def __init__(self):
        self._window = None

    # -- utilitaires --------------------------------------------------------
    def _dialogue_ouvrir(self, multiple=True):
        fichiers = self._window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=multiple,
            file_types=("PDF et images (*.pdf;*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.webp;*.bmp)",
                        "Tous les fichiers (*.*)"))
        return list(fichiers) if fichiers else []

    def _dialogue_enregistrer(self, nom: str, types=("PDF (*.pdf)",), ext=".pdf"):
        chemin = self._window.create_file_dialog(webview.SAVE_DIALOG, save_filename=nom, file_types=types)
        if not chemin:
            return None
        chemin = chemin[0] if isinstance(chemin, (list, tuple)) else chemin
        if not chemin.lower().endswith(ext):
            chemin += ext
        return chemin

    # -- appels depuis la page ----------------------------------------------
    def ouvrir_fichiers(self):
        chemins = self._dialogue_ouvrir()
        if not chemins:
            return None
        return ouvrir_chemins(chemins)

    def fusionner_fichiers(self, id_doc: str, position=None):
        chemins = self._dialogue_ouvrir()
        if not chemins:
            return None
        d = serveur.doc_ou_404(id_doc)
        ajoutees = 0
        with d.verrou:
            d.point_de_reprise()
            for c in chemins:
                with open(c, "rb") as f:
                    n = d.inserer_document(f.read(), _nom(c), position)
                ajoutees += n
                if position is not None:
                    position += n
            d.version += 1
            e = d.etat()
        e["ajoutees"] = ajoutees
        return e

    def enregistrer(self, id_doc: str, nom: str):
        d = serveur.doc_ou_404(id_doc)
        chemin = self._dialogue_enregistrer(nom)
        if not chemin:
            return None
        with d.verrou:
            octets = d.octets_export()
        with open(chemin, "wb") as f:
            f.write(octets)
        return chemin

    def extraire(self, id_doc: str, pages: list, nom: str):
        d = serveur.doc_ou_404(id_doc)
        chemin = self._dialogue_enregistrer(nom)
        if not chemin:
            return None
        with d.verrou:
            octets = d.extraire([int(p) for p in pages])
        with open(chemin, "wb") as f:
            f.write(octets)
        return chemin

    def enregistrer_source(self):
        chemin = self._dialogue_enregistrer("editeur-pdf-bpo-source.zip", ("Archive zip (*.zip)",), ".zip")
        if not chemin:
            return None
        with open(chemin, "wb") as f:
            f.write(serveur.archive_source())
        return chemin

    def ouvrir_lien(self, url: str):
        webbrowser.open(url)
        return True


def ouvrir_chemins(chemins: list) -> dict:
    """Ouvre le premier fichier comme document, fusionne les suivants ; renvoie l'état."""
    with open(chemins[0], "rb") as f:
        octets = f.read()
    nom = _nom(chemins[0])
    ext = os.path.splitext(nom)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"):
        import pymupdf
        img = pymupdf.open(stream=octets, filetype=ext[1:])
        octets = img.convert_to_pdf()
        nom = os.path.splitext(nom)[0] + ".pdf"
    d = serveur.Document(octets, nom)
    with serveur.DOCS_VERROU:
        serveur.DOCS[d.id] = d
    for c in chemins[1:]:
        with open(c, "rb") as f:
            d.inserer_document(f.read(), _nom(c), None)
    return d.etat()


def main():
    srv = serveur.creer_serveur(0)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d/" % port

    # Fichiers passés en argument (double-clic, « Ouvrir avec », glisser sur l'icône)
    fichiers = [a for a in sys.argv[1:] if os.path.isfile(a)]
    if fichiers:
        try:
            e = ouvrir_chemins(fichiers)
            url += "?doc=" + e["id"]
        except Exception as ex:  # fichier illisible : on ouvre quand même l'application
            print("Ouverture impossible :", ex, file=sys.stderr)

    try:
        webview.settings["ALLOW_DOWNLOADS"] = True
    except Exception:
        pass
    api = Api()
    fenetre = webview.create_window("Éditeur PDF BPO", url, js_api=api, width=1400, height=900,
                                    min_size=(960, 600), text_select=True)
    api._window = fenetre
    webview.start()
    srv.shutdown()


if __name__ == "__main__":
    main()
