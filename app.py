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

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

import webview

import serveur

# Flux du journal quand l'application est empaquetée (voir journal_si_fenetre_muette).
JOURNAL = None

# ---------------------------------------------------------------------
# Le poste d'accueil : chaque système range les réglages ailleurs.
# ---------------------------------------------------------------------


def dossier_config() -> str:
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    d = os.path.join(base, "Editeur PDF BPO")
    os.makedirs(d, exist_ok=True)
    return d


# ---------------------------------------------------------------------
# WebView2 : sans lui, pywebview ne lève RIEN — il retombe en silence sur
# Internet Explorer, que l'interface ne sait pas faire tourner, et son
# avertissement se perd puisque l'exécutable n'a pas de console. On le
# cherche donc AVANT d'ouvrir la fenêtre : lire le moteur choisi par
# pywebview obligerait à importer le module, ce qui déclencherait déjà le
# repli et une écriture dans le registre.
# ---------------------------------------------------------------------
_WV2 = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


def version_webview2():
    if os.name != "nt":
        return "sans objet"
    import winreg
    cles = ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients" "\\" + _WV2),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients" "\\" + _WV2),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\EdgeUpdate\Clients" "\\" + _WV2))
    for racine, chemin in cles:
        try:
            with winreg.OpenKey(racine, chemin) as k:
                pv, _ = winreg.QueryValueEx(k, "pv")
        except OSError:
            continue
        if pv and pv not in ("", "0.0.0.0"):
            return pv
    return None


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

    # -- signatures ---------------------------------------------------
    # Elles vivaient dans le localStorage du moteur. Deux causes les
    # effaçaient à chaque lancement : pywebview démarre en mode privé, et
    # le port est tiré au sort — or le stockage local est cloisonné par
    # origine, donc par port. Les ranger côté Python règle les deux d'un
    # coup, sans imposer un port fixe (que deux fenêtres se disputeraient)
    # ni un profil de navigateur permanent sur le poste.
    def _fichier_signatures(self) -> str:
        return os.path.join(dossier_config(), "signatures.json")

    def signatures_lire(self):
        try:
            with open(self._fichier_signatures(), encoding="utf-8") as f:
                l = json.load(f)
            return l if isinstance(l, list) else []
        except Exception:
            return []

    def signatures_ecrire(self, liste):
        try:
            liste = [x for x in (liste or []) if isinstance(x, str)][:8]
            chemin = self._fichier_signatures()
            temp = chemin + ".tmp"
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(liste, f)
            os.replace(temp, chemin)      # écriture atomique : jamais de fichier à moitié écrit
            return True
        except Exception:
            return False

    # -- impression ---------------------------------------------------
    # Sous Windows, la page imprime elle-même par un cadre invisible et
    # cela fonctionne. Sous macOS, WKWebView rend window.print() inerte
    # dans un cadre : on confie donc le PDF au système.
    def imprimer(self, id_doc: str, nom: str):
        if sys.platform != "darwin":
            return "cadre"
        d = serveur.doc_ou_404(id_doc)
        with d.verrou:
            octets = d.octets_export()
        dossier = os.path.join(dossier_config(), "impression")
        os.makedirs(dossier, exist_ok=True)
        chemin = os.path.join(dossier, nom)
        with open(chemin, "wb") as f:
            f.write(octets)
        # « Preview » est le nom du paquet sur le disque ; « Aperçu » n'est
        # que son nom traduit et ne s'ouvrirait pas.
        try:
            if subprocess.run(["open", "-a", "Preview", chemin]).returncode != 0:
                subprocess.run(["open", chemin])
        except Exception:
            subprocess.run(["open", chemin])
        return "systeme"


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


def nettoyer_impressions():
    """Vide les PDF laissés par l'impression du tour précédent.

    Au DÉMARRAGE et non à la sortie : sur macOS, quitter par Cmd+Q ne rend
    jamais la main à Python — le code qui suit webview.start() ne s'exécute
    pas, et un atexit non plus.
    """
    try:
        shutil.rmtree(os.path.join(dossier_config(), "impression"), ignore_errors=True)
    except Exception:
        pass


def journal_si_fenetre_muette():
    """Un exécutable FENÊTRÉ n'a ni sortie standard ni sortie d'erreur : PyInstaller
    les laisse à None. Toute écriture y lève, et l'erreur qui l'a provoquée
    disparaît avec elle — c'est exactement ce qui manquait le jour où la fenêtre
    a cessé de s'ouvrir et où l'application n'avait rien à raconter. On les
    remplace par un journal sur disque, à un endroit qu'on peut citer.
    """
    if not getattr(sys, "frozen", False):
        return None
    chemin = None
    flux = None
    try:
        d = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                         "Editeur PDF BPO")
        os.makedirs(d, exist_ok=True)
        chemin = os.path.join(d, "journal.txt")
        flux = open(chemin, "a", encoding="utf-8", errors="replace", buffering=1)
    except Exception:
        import io as _io
        flux, chemin = _io.StringIO(), None
    # On remplace les deux flux dans TOUS les cas quand on est empaqueté : un
    # exécutable fenêtré peut très bien avoir un stdout qui n'écrit nulle part,
    # ce qui revient au même qu'un None — mesuré le 27/09, où stdout n'était pas
    # None et où pourtant rien n'arrivait jamais nulle part.
    global JOURNAL
    JOURNAL = flux
    sys.stdout = flux
    sys.stderr = flux
    print("===== %s  demarrage  argv=%r"
          % (time.strftime("%Y-%m-%d %H:%M:%S"), sys.argv[1:]))
    return chemin


def main():
    journal_si_fenetre_muette()
    # Le même exécutable sert de veilleur d'impression : c'est ce qui évite
    # d'exiger Python sur le poste où l'imprimante « PDF BPO » est posée.
    if "--veilleur" in sys.argv:
        import veilleur
        veilleur.boucle()
        return

    nettoyer_impressions()
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

    if os.name == "nt" and version_webview2() is None:
        # Le mode navigateur est déjà complet dans l'interface : tout ce qui
        # passe par pywebview y est derrière un test, et le serveur écoute
        # déjà. On bascule donc, en le disant.
        import ctypes
        webbrowser.open(url)
        ctypes.windll.user32.MessageBoxW(
            0,
            "Le composant Windows « WebView2 » n'est pas installé sur ce poste.\n\n"
            "L'Éditeur PDF vient de s'ouvrir dans votre navigateur : vous pouvez\n"
            "travailler normalement.\n\nAdresse : " + url + "\n\n"
            "Fermez cette fenêtre pour arrêter l'Éditeur PDF.",
            "Éditeur PDF BPO", 0x40 | 0x10000 | 0x40000)
        srv.shutdown()
        return

    try:
        webview.settings["ALLOW_DOWNLOADS"] = True
    except Exception:
        pass
    api = Api()
    fenetre = webview.create_window("Éditeur PDF BPO", url, js_api=api, width=1400, height=900,
                                    min_size=(960, 600), text_select=True)
    api._window = fenetre

    # LA FENÊTRE NE SE MONTRE PAS TOUTE SEULE dans l'exécutable « un seul fichier »
    # en mode fenêtré : elle est créée, placée, la page est chargée — et rien à
    # l'écran. On la montre donc nous-mêmes, depuis l'événement « page chargée »,
    # c'est-à-dire DANS le fil qui possède la fenêtre. Tenter la même chose depuis
    # un fil voisin ne marche pas : vu le 27/09, EnumWindows n'y voit même pas nos
    # propres fenêtres.
    def au_chargement():
        try:
            fenetre.show()
            print("fenetre.show() appele depuis l'evenement loaded")
        except Exception as ex:
            print("fenetre.show() a echoue : %r" % (ex,))

    try:
        fenetre.events.loaded += au_chargement
    except Exception as ex:
        print("impossible de brancher l'evenement loaded : %r" % (ex,))
    # Une exception ici est la pire de toutes : la fenêtre existe déjà, mais elle
    # n'est jamais montrée, et l'application reste vivante SANS RIEN AFFICHER.
    # C'est ce qui est arrivé le 27/09. On la journalise, et on se rabat sur le
    # navigateur plutôt que de laisser un processus muet.
    # Un profil WebView2 STABLE, et non le dossier temporaire neuf que pywebview
    # fabrique à chaque lancement en mode privé. Repartir d'un profil vierge
    # oblige WebView2 à tout initialiser à chaque fois : c'est lent, et surtout
    # c'est intermittent — mesuré le 27/09, un lancement sur quatre affichait sa
    # fenêtre, les autres n'allaient même pas jusqu'à demander la page.
    rangement = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                             "Editeur PDF BPO", "webview")
    try:
        os.makedirs(rangement, exist_ok=True)
    except Exception:
        rangement = None
    try:
        print("webview.start(storage_path=%r)..." % rangement)
        if rangement:
            webview.start(private_mode=False, storage_path=rangement)
        else:
            webview.start()
        print("webview.start() rendu")
    except BaseException as ex:
        import traceback
        print("ECHEC de webview.start() : %r" % (ex,))
        traceback.print_exc()
        try:
            webbrowser.open(url)
            print("repli navigateur ouvert sur %s" % url)
        except Exception:
            pass
        try:
            srv.serve_forever()          # on tient le serveur pour le navigateur
        except Exception:
            pass
    srv.shutdown()


if __name__ == "__main__":
    main()
