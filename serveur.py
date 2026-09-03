#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Éditeur PDF BPO — Copyright (C) 2026 BPO / Antoine Lacronique
#
# Ce programme est un logiciel libre : vous pouvez le redistribuer et le modifier
# selon les termes de la GNU Affero General Public License, version 3 ou
# ultérieure, publiée par la Free Software Foundation. Il est fourni SANS AUCUNE
# GARANTIE. Texte complet : fichier LICENSE, ou https://www.gnu.org/licenses/.
# Le code source correspondant est proposé à tout utilisateur par l'application
# elle-même (lien « Source », route /source.zip), comme l'exige l'article 13.
"""Éditeur PDF BPO — serveur local.

Sert l'interface (index.html) et une petite API JSON qui manipule les PDF
avec PyMuPDF : compression, texte, signature, pages, fusion.

Tout reste sur la machine : rien n'est envoyé sur Internet.

Lancer :  python serveur.py            (ouvre le navigateur)
          python serveur.py --sans-navigateur
          python serveur.py --port 8790
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import mimetypes
import os
import sys
import threading
import time
import traceback
import urllib.parse
import uuid
import webbrowser
import zipfile
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pymupdf

ICI = os.path.dirname(os.path.abspath(__file__))
PORT_DEFAUT = 8790
MAX_HIST = 30           # profondeur d'annulation
MAX_UPLOAD = 1 << 30    # 1 Go
FAVICON_SVG = (b"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='6' fill='#e8590c'/>"
               b"<text x='16' y='22' font-family='Segoe UI,Arial' font-size='15' font-weight='700' fill='white' text-anchor='middle'>PDF</text></svg>")

# ---------------------------------------------------------------------------
# Modèle : un document ouvert
# ---------------------------------------------------------------------------


class Document:
    """Un PDF ouvert, avec son historique pour Annuler."""

    def __init__(self, octets: bytes, nom: str):
        self.id = uuid.uuid4().hex[:12]
        self.nom = nom
        self.doc = pymupdf.open(stream=octets, filetype="pdf")
        if self.doc.needs_pass:
            raise ValueError("Ce PDF est protégé par un mot de passe.")
        self.hist: list[bytes] = []
        self.version = 0
        self.epoque = 0     # change quand le contenu peut bouger sans que les pages le montrent (compression, annulation)
        self.verrou = threading.Lock()
        self.dernier_acces = time.time()

    # -- historique ---------------------------------------------------------
    def _octets(self) -> bytes:
        return self.doc.tobytes(garbage=0, deflate=True)

    def point_de_reprise(self):
        self.hist.append(self._octets())
        if len(self.hist) > MAX_HIST:
            self.hist.pop(0)

    def recharger(self, octets: bytes):
        self.doc.close()
        self.doc = pymupdf.open(stream=octets, filetype="pdf")
        self.epoque += 1

    def annuler(self) -> bool:
        if not self.hist:
            return False
        self.recharger(self.hist.pop())
        self.version += 1
        return True

    # -- état -----------------------------------------------------------------
    def taille(self) -> int:
        return len(self.doc.tobytes(garbage=4, deflate=True))

    def etat(self, avec_taille=True) -> dict:
        pages = []
        for p in self.doc:
            r = p.rect  # déjà tourné
            try:
                empreinte = zlib.crc32(p.read_contents()) & 0xFFFFFFFF
            except Exception:
                empreinte = self.version
            cle = "%d-%d-%08x-%d" % (self.epoque, p.xref, empreinte, p.rotation)
            pages.append({"w": round(r.width, 2), "h": round(r.height, 2), "rot": p.rotation, "cle": cle})
        d = {"id": self.id, "nom": self.nom, "version": self.version,
             "pages": pages, "annulable": bool(self.hist)}
        if avec_taille:
            d["taille"] = self.taille()
        return d

    # -- rendu ----------------------------------------------------------------
    def rendu_png(self, n: int, zoom: float) -> bytes:
        page = self.doc[n]
        zoom = max(0.05, min(zoom, 6.0))
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")

    # -- texte ---------------------------------------------------------------
    def lignes_texte(self, n: int) -> list[dict]:
        """Lignes de texte de la page, avec leur boîte dans l'espace AFFICHÉ
        (page tournée) et les données brutes nécessaires pour les réécrire."""
        page = self.doc[n]
        M = page.rotation_matrix
        lignes = []
        d = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_PRESERVE_LIGATURES)
        for b in d["blocks"]:
            if b.get("type", 0) != 0:
                continue
            for l in b["lines"]:
                spans = [s for s in l["spans"] if s["text"].strip()]
                if not spans:
                    continue
                s0 = spans[0]
                bbox = pymupdf.Rect(l["bbox"])
                for s in spans:
                    bbox |= pymupdf.Rect(s["bbox"])
                texte = "".join(s["text"] for s in l["spans"]).rstrip()
                if not texte.strip():
                    continue
                rb = bbox * M
                rb.normalize()
                lignes.append({
                    "bbox_aff": [round(v, 2) for v in rb],
                    "texte": texte,
                    "brut": {
                        "bbox": [round(v, 3) for v in bbox],
                        "origin": [round(v, 3) for v in s0["origin"]],
                        "font": s0["font"], "size": round(s0["size"], 2),
                        "flags": s0["flags"], "color": s0["color"],
                        "dir": [round(v, 4) for v in l["dir"]],
                    },
                    "taille_aff": round(s0["size"] * (1.0), 2),
                })
        return lignes

    POLICES_STD = ("helv", "hebo", "heit", "hebi", "tiro", "tibo", "tiit", "tibi", "cour", "cobo", "coit", "cobi")
    _TAMPON_POLICES: dict[str, bytes] = {}

    def _police_std(self, page, code: str) -> str:
        """Enregistre sur la page (une fois) la police standard `code` comme police
        CID : tout l'Unicode couvert par la police (—, €, œ…) devient écrivable,
        au lieu des 256 codes de l'encodage Latin des polices de base."""
        if code not in self.POLICES_STD:
            code = "helv"
        alias = "BPO_" + code
        try:
            tampon = self._TAMPON_POLICES.get(code)
            if tampon is None:
                tampon = pymupdf.Font(code).buffer
                self._TAMPON_POLICES[code] = tampon
            page.insert_font(fontname=alias, fontbuffer=tampon)
            return alias
        except Exception:
            return code

    def _police_texte(self, page, brut: dict, texte: str) -> str:
        """Choisit une police pour réécrire `texte` : la police d'origine si elle
        est embarquée et possède tous les glyphes, sinon une police standard
        de même famille (sans/serif/mono, gras, italique)."""
        nom_voulu = brut.get("font", "")
        flags = int(brut.get("flags", 0))
        # 1) police d'origine embarquée ?
        try:
            for xref, ext, ftype, basefont, nom, enc, _ in page.get_fonts(full=True):
                base = basefont.split("+")[-1]
                if base != nom_voulu and basefont != nom_voulu:
                    continue
                if ext in ("n/a", "") or ftype == "Type3":
                    break
                _, ext2, _, buf = self.doc.extract_font(xref)
                if not buf or ext2 not in ("ttf", "otf", "cff"):
                    break
                f = pymupdf.Font(fontbuffer=buf)
                if all(f.has_glyph(ord(c)) for c in texte if not c.isspace()):
                    alias = "BPO_%d" % xref
                    page.insert_font(fontname=alias, fontbuffer=buf)
                    return alias
                break
        except Exception:
            pass
        # 2) police standard
        nom_bas = nom_voulu.lower()
        gras = bool(flags & 16) or "bold" in nom_bas or "semibold" in nom_bas or "black" in nom_bas
        ital = bool(flags & 2) or "italic" in nom_bas or "oblique" in nom_bas
        if flags & 8 or "courier" in nom_bas or "mono" in nom_bas:
            fam = "co"
        elif flags & 4 or "times" in nom_bas or "georgia" in nom_bas or "garamond" in nom_bas or "serif" in nom_bas and "sans" not in nom_bas:
            fam = "ti"
        else:
            fam = "he"
        suffixe = {(False, False): "", (True, False): "bo", (False, True): "it", (True, True): "bi"}[(gras, ital)]
        code = {"he": "helv", "ti": "tiro", "co": "cour"}[fam] if not suffixe else fam + suffixe
        return self._police_std(page, code)

    def _zone_redaction(self, page, brut: dict) -> pymupdf.Rect:
        """Zone à effacer pour une ligne. MuPDF retire tout caractère dont la
        boîte TOUCHE la zone : une bande fine à hauteur d'x suffit à retirer
        toute la ligne, et elle est rognée pour ne pas toucher les boîtes des
        lignes voisines (les interlignes serrés se chevauchent)."""
        bbox = pymupdf.Rect(brut["bbox"])
        taille = float(brut["size"])
        ox, oy = brut["origin"]
        dx, dy = brut.get("dir", [1, 0])
        if abs(dx) < 0.99:  # texte vertical / incliné : boîte légèrement rétrécie
            m = min(1.0, bbox.height * 0.12)
            return pymupdf.Rect(bbox.x0, bbox.y0 + m, bbox.x1, bbox.y1 - m)
        haut, bas = oy - 0.55 * taille, oy - 0.05 * taille
        x0, x1 = bbox.x0 + 0.3, bbox.x1 - 0.3
        d = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
        for b in d["blocks"]:
            if b.get("type", 0) != 0:
                continue
            for l in b["lines"]:
                o = pymupdf.Rect(l["bbox"])
                if abs(o.y0 - bbox.y0) < 0.5 and abs(o.x0 - bbox.x0) < 0.5:
                    continue  # la ligne elle-même
                if o.x1 <= x0 or o.x0 >= x1:
                    continue  # pas de recouvrement horizontal
                if o.y1 <= oy and haut < o.y1 < bas:
                    haut = o.y1 + 0.2   # ligne du dessus qui descend dans la bande
                if o.y0 >= haut and haut < o.y0 < bas:
                    bas = o.y0 - 0.2    # ligne du dessous qui monte dans la bande
        if bas - haut < 0.6:
            c = oy - 0.3 * taille
            haut, bas = c - 0.3, c + 0.3
        return pymupdf.Rect(x0, haut, x1, bas)

    def remplacer_texte(self, n: int, brut: dict, nouveau: str):
        page = self.doc[n]
        zone = self._zone_redaction(page, brut)
        page.add_redact_annot(zone, fill=False)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
        if not nouveau.strip():
            return
        c = int(brut.get("color", 0))
        couleur = ((c >> 16 & 255) / 255, (c >> 8 & 255) / 255, (c & 255) / 255)
        police = self._police_texte(page, brut, nouveau)
        dx, dy = brut.get("dir", [1, 0])
        rot = 0
        if abs(dx) < 0.5:
            rot = 90 if dy < 0 else 270
        elif dx < 0:
            rot = 180
        origine = pymupdf.Point(brut["origin"])
        try:
            page.insert_text(origine, nouveau, fontsize=brut["size"], fontname=police,
                             color=couleur, rotate=rot)
        except Exception:
            page.insert_text(origine, nouveau, fontsize=brut["size"], fontname=self._police_std(page, "helv"),
                             color=couleur, rotate=rot)

    def texte_libre(self, n: int, x: float, y: float, texte: str, taille: float, couleur_hex: str, police: str = "helv"):
        """Ajoute du texte à la position (x, y) = coin bas-gauche dans l'espace affiché."""
        page = self.doc[n]
        pt = pymupdf.Point(x, y) * page.derotation_matrix
        couleur = _hex_rgb(couleur_hex)
        page.insert_text(pt, texte, fontsize=taille, fontname=self._police_std(page, police),
                         color=couleur, rotate=page.rotation)

    # -- images / signature --------------------------------------------------
    def inserer_image(self, n: int, rect_aff: list[float], png: bytes):
        page = self.doc[n]
        r = pymupdf.Rect(rect_aff) * page.derotation_matrix
        r.normalize()
        page.insert_image(r, stream=png, rotate=page.rotation, keep_proportion=True)

    # -- pages ----------------------------------------------------------------
    def supprimer_pages(self, pages: list[int]):
        pages = sorted(set(p for p in pages if 0 <= p < len(self.doc)))
        if len(pages) >= len(self.doc):
            raise ValueError("Impossible de supprimer toutes les pages.")
        self.doc.delete_pages(pages)

    def tourner_pages(self, pages: list[int], angle: int):
        for p in pages:
            pg = self.doc[p]
            pg.set_rotation((pg.rotation + angle) % 360)

    def reordonner(self, ordre: list[int]):
        if sorted(ordre) != list(range(len(self.doc))):
            raise ValueError("Ordre de pages invalide.")
        self.doc.select(ordre)

    def extraire(self, pages: list[int]) -> bytes:
        d = pymupdf.open()
        d.insert_pdf(self.doc, from_page=0, to_page=-1)
        d.select(sorted(set(pages)))
        return d.tobytes(garbage=4, deflate=True)

    def inserer_document(self, octets: bytes, nom: str, position: int | None):
        """Fusionne un PDF (ou une image convertie en page) à `position`
        (index de la page avant laquelle insérer ; None = à la fin)."""
        ext = os.path.splitext(nom)[1].lower()
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"):
            img = pymupdf.open(stream=octets, filetype=ext[1:])
            octets = img.convert_to_pdf()
            img.close()
        autre = pymupdf.open(stream=octets, filetype="pdf")
        if autre.needs_pass:
            raise ValueError("Le fichier %s est protégé par un mot de passe." % nom)
        n = len(autre)
        if position is None or position >= len(self.doc):
            self.doc.insert_pdf(autre)
        else:
            self.doc.insert_pdf(autre, start_at=position)
        autre.close()
        return n

    # -- compression ----------------------------------------------------------
    NIVEAUX = {
        # dpi max des images, qualité JPEG
        "leger": (None, None),
        "moyen": (150, 78),
        "fort": (110, 60),
        "extreme": (72, 42),
    }

    def compresser(self, niveau: str) -> dict:
        dpi_max, qualite = self.NIVEAUX.get(niveau, self.NIVEAUX["moyen"])
        avant = self.taille()
        n_img = 0
        n_reduites = 0
        if dpi_max:
            n_img, n_reduites = self._recompresser_images(dpi_max, qualite)
        try:
            self.doc.subset_fonts()
        except Exception:
            pass
        octets = self.doc.tobytes(garbage=4, deflate=True, deflate_images=True,
                                  deflate_fonts=True, clean=True)
        self.recharger(octets)
        return {"avant": avant, "apres": len(octets), "images": n_img, "reduites": n_reduites}

    def _recompresser_images(self, dpi_max: int, qualite: int) -> tuple[int, int]:
        """Réencode les images en JPEG (et les rééchantillonne au-dessus de
        `dpi_max`) en réécrivant le flux de l'objet image lui-même : les masques
        de transparence (/SMask) sont conservés et rééchantillonnés à part."""
        doc = self.doc
        vus: set[int] = set()
        masques: set[int] = set()
        total = 0
        reduites = 0
        for page in doc:
            for im in page.get_images(full=True):
                if im[1]:
                    masques.add(im[1])
        for page in doc:
            for im in page.get_images(full=True):
                xref, smask, w, h, bpc, cs, _, _, filtre, _ = im
                if xref in vus or xref in masques:
                    continue
                vus.add(xref)
                total += 1
                if bpc == 1 or w * h < 48 * 48:
                    continue  # noir & blanc (scans, fax), icônes
                if filtre in ("JBIG2Decode", "CCITTFaxDecode", "JPXDecode") and bpc == 1:
                    continue
                try:
                    # masque par couleur (/Mask tableau) : le JPEG déplacerait les valeurs
                    mk = doc.xref_get_key(xref, "Mask")
                    if mk[0] == "array":
                        continue
                    rects = page.get_image_rects(xref)
                    largeur_pts = max((r.width for r in rects), default=0) or 0
                    hauteur_pts = max((r.height for r in rects), default=0) or 0
                    facteur = 1.0
                    if largeur_pts > 0 and hauteur_pts > 0:
                        dpi = max(w / (largeur_pts / 72.0), h / (hauteur_pts / 72.0))
                        if dpi > dpi_max * 1.15:
                            facteur = dpi_max / dpi
                    pix = pymupdf.Pixmap(doc, xref)
                    if pix.alpha:
                        pix = pymupdf.Pixmap(pix, 0)
                    if pix.n not in (1, 3):
                        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                    nw, nh = w, h
                    if facteur < 1.0:
                        nw, nh = max(1, int(w * facteur)), max(1, int(h * facteur))
                        pix = pymupdf.Pixmap(pix, nw, nh, None)
                    jpg = pix.tobytes("jpeg", jpg_quality=qualite)
                    taille_anc = _taille_flux(doc, xref)
                    if len(jpg) >= taille_anc * 0.92:
                        continue
                    _ecrire_image_jpeg(doc, xref, jpg, pix)
                    reduites += 1
                    if smask and facteur < 1.0:
                        self._reduire_masque(smask, nw, nh)
                except Exception:
                    traceback.print_exc()
                    continue
        return total, reduites

    def _reduire_masque(self, xref: int, nw: int, nh: int):
        """Rééchantillonne un masque de transparence (gris 8 bits, sans perte)."""
        doc = self.doc
        if doc.xref_get_key(xref, "Decode")[0] != "null":
            return
        pix = pymupdf.Pixmap(doc, xref)
        if pix.n != 1 or pix.alpha:
            return
        if pix.width <= nw and pix.height <= nh:
            return
        pix = pymupdf.Pixmap(pix, nw, nh, None)
        doc.update_stream(xref, pix.samples, compress=True)
        doc.xref_set_key(xref, "Width", str(pix.width))
        doc.xref_set_key(xref, "Height", str(pix.height))
        doc.xref_set_key(xref, "BitsPerComponent", "8")
        doc.xref_set_key(xref, "ColorSpace", "/DeviceGray")
        doc.xref_set_key(xref, "DecodeParms", "null")

    # -- export ---------------------------------------------------------------
    def octets_export(self) -> bytes:
        """PDF final : polices réduites aux glyphes utilisés (sur une copie), nettoyé."""
        try:
            copie = pymupdf.open(stream=self.doc.tobytes(), filetype="pdf")
            copie.subset_fonts()
            octets = copie.tobytes(garbage=4, deflate=True)
            copie.close()
            return octets
        except Exception:
            return self.doc.tobytes(garbage=4, deflate=True)


def _taille_flux(doc, xref: int) -> int:
    L = doc.xref_get_key(xref, "Length")
    if L[0] == "int":
        return int(L[1])
    return len(doc.xref_stream_raw(xref))


def _ecrire_image_jpeg(doc, xref: int, jpg: bytes, pix):
    """Remplace le flux d'un objet image par un JPEG, en conservant ses autres
    clés (/SMask, /Mask stencil, /Interpolate...)."""
    doc.update_stream(xref, jpg, compress=False)
    doc.xref_set_key(xref, "Filter", "/DCTDecode")
    doc.xref_set_key(xref, "Width", str(pix.width))
    doc.xref_set_key(xref, "Height", str(pix.height))
    doc.xref_set_key(xref, "BitsPerComponent", "8")
    doc.xref_set_key(xref, "ColorSpace", "/DeviceRGB" if pix.n == 3 else "/DeviceGray")
    for k in ("DecodeParms", "Decode", "Length1", "Length2", "Length3"):
        doc.xref_set_key(xref, k, "null")


def _hex_rgb(h: str):
    h = (h or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except Exception:
        return (0, 0, 0)


# ---------------------------------------------------------------------------
# Registre des documents ouverts
# ---------------------------------------------------------------------------
DOCS: dict[str, Document] = {}
DOCS_VERROU = threading.Lock()


def doc_ou_404(id_: str) -> Document:
    d = DOCS.get(id_)
    if d is None:
        raise KeyError("Document inconnu (le serveur a peut-être redémarré). Rouvrez le fichier.")
    d.dernier_acces = time.time()
    return d


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    server_version = "BPO-PDF/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # journal plus discret
        premier = args[0] if args and isinstance(args[0], str) else ""
        if "/api/doc/" in premier and (".png" in premier or "/texte" in premier):
            return
        try:
            sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))
        except Exception:
            pass

    def do_HEAD(self):   # sondes du navigateur / outils
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "GET, POST, HEAD, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # -- utilitaires --------------------------------------------------------
    def _envoyer(self, code: int, corps: bytes, ctype: str, entetes: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (entetes or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(corps)

    def _json(self, obj, code=200):
        self._envoyer(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _erreur(self, code: int, msg: str):
        self._json({"erreur": msg}, code)

    def _corps(self) -> bytes:
        """Corps de la requête, lu une seule fois (un second appel renvoie le même)."""
        if getattr(self, "_corps_lu", None) is None:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_UPLOAD:
                raise ValueError("Fichier trop volumineux.")
            self._corps_lu = self.rfile.read(n) if n else b""
        return self._corps_lu

    def _nom_fichier(self) -> str:
        nom = self.headers.get("X-Nom") or "document.pdf"
        return urllib.parse.unquote(nom)

    # -- GET ----------------------------------------------------------------
    def do_GET(self):
        self._corps_lu = None
        try:
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            chemin = u.path
            if chemin == "/" or chemin == "/index.html":
                return self._fichier("index.html")
            if chemin == "/source.zip":
                return self._envoyer(200, archive_source(), "application/zip",
                                     {"Content-Disposition": "attachment; filename=editeur-pdf-bpo-source.zip"})
            if chemin == "/favicon.ico":
                return self._envoyer(200, FAVICON_SVG, "image/svg+xml", {"Cache-Control": "public, max-age=86400"})
            if chemin.startswith("/api/"):
                return self._api_get(chemin, q)
            return self._fichier(chemin.lstrip("/"))
        except KeyError as e:
            self._erreur(404, str(e))
        except Exception as e:
            traceback.print_exc()
            self._erreur(500, str(e))

    def _fichier(self, rel: str):
        rel = os.path.normpath(rel).replace("\\", "/")
        if rel.startswith("..") or rel.startswith("/"):
            return self._erreur(404, "Introuvable")
        chemin = os.path.join(ICI, rel)
        if not os.path.isfile(chemin):
            return self._erreur(404, "Introuvable")
        ctype = mimetypes.guess_type(chemin)[0] or "application/octet-stream"
        if ctype.startswith("text/"):
            ctype += "; charset=utf-8"
        with open(chemin, "rb") as f:
            self._envoyer(200, f.read(), ctype)

    def _api_get(self, chemin: str, q: dict):
        parts = chemin.split("/")[2:]  # après /api/
        if parts[0] == "sante":
            return self._json({"ok": True, "pymupdf": pymupdf.VersionBind, "docs": len(DOCS)})
        if parts[0] != "doc" or len(parts) < 2:
            return self._erreur(404, "Route inconnue")
        d = doc_ou_404(parts[1])
        if len(parts) == 2:
            return self._json(d.etat())
        if parts[2] in ("telecharger", "imprimer"):
            with d.verrou:
                octets = d.octets_export()
            nom = q.get("nom", [None])[0] or _nom_export(d.nom)
            disposition = "inline" if parts[2] == "imprimer" else "attachment"
            return self._envoyer(200, octets, "application/pdf",
                                 {"Content-Disposition": disposition + "; filename*=UTF-8''" + urllib.parse.quote(nom)})
        if parts[2] == "extraire":
            pages = [int(x) for x in q.get("pages", [""])[0].split(",") if x != ""]
            with d.verrou:
                octets = d.extraire(pages)
            nom = _nom_export(d.nom, "-extrait")
            return self._envoyer(200, octets, "application/pdf",
                                 {"Content-Disposition": "attachment; filename*=UTF-8''" + urllib.parse.quote(nom)})
        if parts[2] == "page" and len(parts) >= 4:
            n = int(parts[3].split(".")[0])
            if n < 0 or n >= len(d.doc):
                return self._erreur(404, "Page hors limites")
            if len(parts) >= 5 and parts[4] == "texte":
                with d.verrou:
                    return self._json({"lignes": d.lignes_texte(n)})
            zoom = float(q.get("zoom", ["1"])[0])
            with d.verrou:
                png = d.rendu_png(n, zoom)
            return self._envoyer(200, png, "image/png", {"Cache-Control": "private, max-age=3600"})
        return self._erreur(404, "Route inconnue")

    # -- POST ---------------------------------------------------------------
    def do_POST(self):
        self._corps_lu = None
        try:
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            parts = u.path.split("/")[2:]
            if parts[0] == "ouvrir":
                octets = self._corps()
                nom = self._nom_fichier()
                ext = os.path.splitext(nom)[1].lower()
                if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"):
                    img = pymupdf.open(stream=octets, filetype=ext[1:])
                    octets = img.convert_to_pdf()
                    nom = os.path.splitext(nom)[0] + ".pdf"
                d = Document(octets, nom)
                with DOCS_VERROU:
                    DOCS[d.id] = d
                    _purger()
                return self._json(d.etat())
            if parts[0] == "doc" and len(parts) >= 3:
                corps = self._corps()
                d = doc_ou_404(parts[1])
                if parts[2] == "fusionner":
                    octets = corps
                    nom = self._nom_fichier()
                    pos = q.get("position", [None])[0]
                    pos = int(pos) if pos not in (None, "") else None
                    with d.verrou:
                        d.point_de_reprise()
                        n = d.inserer_document(octets, nom, pos)
                        d.version += 1
                        e = d.etat()
                    e["ajoutees"] = n
                    return self._json(e)
                if parts[2] == "op":
                    op = json.loads(corps.decode("utf-8"))
                    return self._json(self._operation(d, op))
                if parts[2] == "fermer":
                    with DOCS_VERROU:
                        DOCS.pop(d.id, None)
                    return self._json({"ok": True})
            self._corps()
            return self._erreur(404, "Route inconnue")
        except KeyError as e:
            self._erreur(404, str(e))
        except ValueError as e:
            self._erreur(400, str(e))
        except Exception as e:
            traceback.print_exc()
            self._erreur(500, "%s: %s" % (type(e).__name__, e))

    def _operation(self, d: Document, op: dict) -> dict:
        t = op.get("type")
        extra = {}
        with d.verrou:
            if t == "annuler":
                if not d.annuler():
                    raise ValueError("Rien à annuler.")
                return d.etat()
            d.point_de_reprise()
            try:
                if t == "supprimer":
                    d.supprimer_pages(op["pages"])
                elif t == "rotation":
                    d.tourner_pages(op["pages"], int(op.get("angle", 90)))
                elif t == "ordre":
                    d.reordonner(op["ordre"])
                elif t == "texte":
                    d.remplacer_texte(int(op["page"]), op["brut"], op.get("texte", ""))
                elif t == "texte_libre":
                    d.texte_libre(int(op["page"]), float(op["x"]), float(op["y"]), op["texte"],
                                  float(op.get("taille", 12)), op.get("couleur", "#000000"), op.get("police", "helv"))
                elif t == "image":
                    png = base64.b64decode(op["png"].split(",")[-1])
                    d.inserer_image(int(op["page"]), op["rect"], png)
                elif t == "compresser":
                    extra["compression"] = d.compresser(op.get("niveau", "moyen"))
                else:
                    raise ValueError("Opération inconnue : %s" % t)
            except Exception:
                # l'opération a échoué : on revient à l'état précédent
                d.recharger(d.hist.pop())
                raise
            d.version += 1
            e = d.etat()
        e.update(extra)
        return e


FICHIERS_SOURCE = ("serveur.py", "index.html", "README.md", "LICENSE", "THIRD-PARTY.md",
                   "requirements.txt", "Editeur PDF.bat")


def archive_source() -> bytes:
    """Archive du code source correspondant (obligation AGPL, article 13)."""
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        for nom in FICHIERS_SOURCE:
            chemin = os.path.join(ICI, nom)
            if os.path.isfile(chemin):
                z.write(chemin, "editeur-pdf-bpo/" + nom)
    return tampon.getvalue()


def _nom_export(nom: str, suffixe: str = "-modifie") -> str:
    base, _ = os.path.splitext(nom)
    return base + suffixe + ".pdf"


def _purger(age_max=6 * 3600):
    """Oublie les documents non touchés depuis longtemps (mémoire)."""
    t = time.time()
    for k in [k for k, d in DOCS.items() if t - d.dernier_acces > age_max]:
        try:
            DOCS[k].doc.close()
        except Exception:
            pass
        DOCS.pop(k, None)


def main():
    ap = argparse.ArgumentParser(description="Éditeur PDF BPO")
    ap.add_argument("--port", type=int, default=PORT_DEFAUT)
    ap.add_argument("--sans-navigateur", action="store_true")
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    srv.daemon_threads = True
    url = "http://localhost:%d/" % a.port
    print("Éditeur PDF BPO — %s  (PyMuPDF %s)" % (url, pymupdf.VersionBind))
    print("Ctrl+C pour arrêter.")
    if not a.sans_navigateur:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
