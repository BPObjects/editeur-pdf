# SPDX-License-Identifier: AGPL-3.0-or-later
"""Banc du veilleur d'images : 72 dpi aux images SANS résolution qui arrivent.

    python banc/images.py              le banc
    python banc/images.py --sabotages  …puis on casse chaque prudence, une à une

CE QUE CE BANC DÉFEND. Les images de Gemini et Copilot ne déclarent aucune
résolution ; Archicad les imprime alors rognées au coin haut-gauche sur un
écran à 150 % (constat du 02/11/2026). Le veilleur d'impression tamponne donc
à 72 dpi ce qui arrive dans Téléchargements. Mais il écrit dans un dossier de
l'utilisateur sans qu'on le lui demande à chaque fois : chaque prudence a son
témoin, et chaque témoin doit TOMBER quand on retire sa prudence.

Le vrai veilleur tourne ici, dans sa vraie boucle, sur des dossiers à nous.
Il faut PyMuPDF (l'environnement .venv) pour fabriquer et décoder les images.
"""
from __future__ import annotations

import contextlib
import io
import os
import shutil
import struct
import sys
import tempfile
import threading
import time
import zlib

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
sys.path.insert(0, os.path.dirname(ICI))

import pymupdf                                                 # noqa: E402

from commun import Banc                                        # noqa: E402
import image_dpi                                               # noqa: E402
import veilleur                                                # noqa: E402

# Le veilleur ne doit JAMAIS voir le vrai dossier d'impression ni ouvrir quoi
# que ce soit pendant le banc. Ses boucles ne s'arrêtent pas : on ne rend donc
# pas ces réglages avant la fin du processus.
_BAC = tempfile.mkdtemp(prefix="banc-images-")
veilleur.DOSSIER = os.path.join(_BAC, "impressions")
veilleur.ATTENDU = os.path.join(veilleur.DOSSIER, "impression.pdf")
OUVERTS = []
veilleur.ouvrir = OUVERTS.append
JOURNAL = []
veilleur.dire = JOURNAL.append
veilleur.PAUSE = 0.2
veilleur.REGARD_IMAGES = 0.3


# ------------------------------------------------------------ fabrication
def _pixmap():
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 160, 90), False)
    pix.clear_with(200)
    for k in range(8):
        pix.set_rect(pymupdf.IRect(k * 20, 0, k * 20 + 10, 90), (k * 30, 255 - k * 30, 90))
    return pix


def _jpeg_nu() -> bytes:
    """Un JPEG sans aucun segment APPn : on pose ensuite l'en-tête voulu."""
    b = _pixmap().tobytes("jpeg")
    segs, reste = image_dpi._segments_jpeg(b)
    out = bytearray(b"\xff\xd8")
    for m, s in segs:
        if 0xE0 <= m <= 0xEF:
            continue
        out += bytes([0xFF, m]) + struct.pack(">H", len(s) + 2) + s
    return bytes(out + b[reste:])


def _avec(seg_marqueur: int, seg: bytes) -> bytes:
    nu = _jpeg_nu()
    return nu[:2] + bytes([0xFF, seg_marqueur]) + struct.pack(">H", len(seg) + 2) + seg + nu[2:]


def jpeg_gemini() -> bytes:
    """Comme Gemini : JFIF « unité 0, densité 1×1 » — aucune résolution."""
    return _avec(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")


def jpeg_300() -> bytes:
    return _avec(0xE0, b"JFIF\x00\x01\x01\x01" + struct.pack(">HH", 300, 300) + b"\x00\x00")


def jpeg_exif72() -> bytes:
    """Comme le JPEG Copilot qui sortait entier : 72 dpi en EXIF, pas de JFIF."""
    n = 3
    ifd = 8
    donnees = ifd + 2 + n * 12 + 4
    t = bytearray(b"II*\x00" + struct.pack("<I", ifd) + struct.pack("<H", n))
    t += struct.pack("<HHII", 0x11A, 5, 1, donnees)
    t += struct.pack("<HHII", 0x11B, 5, 1, donnees + 8)
    t += struct.pack("<HHI", 0x128, 3, 1) + struct.pack("<HH", 2, 0)
    t += struct.pack("<I", 0)
    t += struct.pack("<II", 720000, 10000) + struct.pack("<II", 720000, 10000)
    return _avec(0xE1, b"Exif\x00\x00" + bytes(t))


def png_sans_phys() -> bytes:
    b = _pixmap().tobytes("png")
    out = bytearray(b[:8])
    i = 8
    while i < len(b):
        L = struct.unpack(">I", b[i:i + 4])[0]
        if b[i + 4:i + 8] != b"pHYs":
            out += b[i:i + 12 + L]
        i += 12 + L
    return bytes(out)


def _ecrire(chemin, octets, mode="wb"):
    with open(chemin, mode) as f:
        f.write(octets)


def _lire(chemin):
    with open(chemin, "rb") as f:
        return f.read()


def _donnees_jpeg(b):
    return b[image_dpi._segments_jpeg(b)[1]:]


def _pixels(b):
    p = pymupdf.Pixmap(b)
    return (p.width, p.height, bytes(p.samples))


def _crc_ok(b):
    i = 8
    while i < len(b):
        L = struct.unpack(">I", b[i:i + 4])[0]
        ty, d = b[i + 4:i + 8], b[i + 8:i + 8 + L]
        if struct.unpack(">I", b[i + 8 + L:i + 12 + L])[0] != zlib.crc32(ty + d) & 0xFFFFFFFF:
            return False
        i += 12 + L
    return True


def _attendre(cond, secondes=6.0):
    fin = time.time() + secondes
    while time.time() < fin:
        if cond():
            return True
        time.sleep(0.1)
    return cond()


# -------------------------------------------------------------------- banc
def banc_images(b: Banc):
    dl = tempfile.mkdtemp(prefix="telechargements-", dir=_BAC)
    os.makedirs(veilleur.DOSSIER, exist_ok=True)
    JOURNAL.clear()
    OUVERTS.clear()

    # Déjà là AVANT que le veilleur démarre : une vieille, une toute récente.
    vieille = os.path.join(dl, "vieille gemini.jpg")
    _ecrire(vieille, jpeg_gemini())
    il_y_a_2h = time.time() - 7200
    os.utime(vieille, (il_y_a_2h, il_y_a_2h))
    vieille_avant = _lire(vieille)
    recente = os.path.join(dl, "recente.jpg")
    _ecrire(recente, jpeg_gemini())

    veilleur.DOSSIERS_IMAGES = [dl]
    threading.Thread(target=veilleur.boucle, daemon=True).start()
    time.sleep(0.8)

    # 1. Un téléchargement de navigateur : .crdownload, puis renommage.
    gem = os.path.join(dl, "Gemini_Generated_Image.jpg")
    gem_avant = jpeg_gemini()
    _ecrire(gem + ".crdownload", gem_avant)
    zone = b"[ZoneTransfer]\r\nZoneId=3\r\n"
    if os.name == "nt":
        _ecrire(gem + ".crdownload:Zone.Identifier", zone)
    date = time.time() - 30
    os.utime(gem + ".crdownload", (date, date))
    os.replace(gem + ".crdownload", gem)
    date_gem = os.stat(gem).st_mtime_ns

    # 2. Un PNG Copilot, un JPEG à 72 dpi en EXIF, un JPEG à 300 dpi.
    png = os.path.join(dl, "Designer.png")
    png_avant = png_sans_phys()
    _ecrire(png, png_avant)
    ex = os.path.join(dl, "Designer.jpg")
    ex_avant = jpeg_exif72()
    _ecrire(ex, ex_avant)
    trois = os.path.join(dl, "scan 300 dpi.jpg")
    trois_avant = jpeg_300()
    _ecrire(trois, trois_avant)

    # 3. Une image écrite EN DEUX FOIS, avec une pause bien plus longue que
    #    deux regards : la taille ne bouge plus, mais elle n'est pas finie.
    lente = os.path.join(dl, "lente.jpg")
    lente_entiere = jpeg_gemini()
    moitie = len(lente_entiere) // 2
    _ecrire(lente, lente_entiere[:moitie])

    # 4. Et un tirage, pendant ce temps : la veille d'impression continue.
    _ecrire(veilleur.ATTENDU, b"%PDF-1.4\n" + b"x" * 5000
            + b"\ntrailer\n<<>>\nstartxref\n9\n%%EOF\n")

    time.sleep(3.0)
    pendant = _lire(lente)
    _ecrire(lente, lente_entiere[moitie:], "ab")

    _attendre(lambda: image_dpi.resolution(_lire(gem)) == 72
              and image_dpi.resolution(_lire(lente)) == 72
              and image_dpi.resolution(_lire(png)) is not None)
    time.sleep(1.5)                 # quelques regards de plus : aucune reprise

    g = _lire(gem)
    b.dire("Gemini : reçoit 72 dpi", image_dpi.resolution(g), 72.0)
    b.dire("...pixels intacts (données JPEG identiques)", _donnees_jpeg(g) == _donnees_jpeg(gem_avant), True)
    b.dire("...date de modification gardée", os.stat(gem).st_mtime_ns, date_gem)
    if os.name == "nt":
        try:
            z = _lire(gem + ":Zone.Identifier")
        except OSError:
            z = b""
        b.dire("...marque « téléchargé d'Internet » gardée", z, zone)
    p = _lire(png)
    b.dire("PNG Copilot : reçoit 72 dpi", round(image_dpi.resolution(p) or 0), 72)
    b.dire("...pixels intacts", _pixels(p) == _pixels(png_avant), True)
    b.dire("...chunks valides (CRC)", _crc_ok(p), True)
    b.dire("JPEG déjà à 72 dpi en EXIF : octet pour octet", _lire(ex) == ex_avant, True)
    b.dire("JPEG à 300 dpi : laissé (résolution déclarée)", _lire(trois) == trois_avant, True)
    b.dire("image d'il y a 2 h, déjà là : laissée", _lire(vieille) == vieille_avant, True)
    b.dire("image récente déjà là au démarrage : tamponnée", image_dpi.resolution(_lire(recente)), 72.0)
    b.dire("image à moitié écrite : pas touchée pendant la pause",
           pendant == lente_entiere[:moitie], True)
    fin = _lire(lente)
    b.dire("...tamponnée une fois finie", image_dpi.resolution(fin), 72.0)
    b.dire("...et entière", _donnees_jpeg(fin) == _donnees_jpeg(lente_entiere), True)
    tampons = [l for l in JOURNAL if isinstance(l, str) and l.startswith("image ") and "-> 72 dpi" in l]
    b.dire("un tampon par image, aucune reprise en boucle", len(tampons), 4)
    b.dire("aucun fichier temporaire laissé",
           [f for f in os.listdir(dl) if f.endswith(".tmp")], [])
    b.dire("le tirage pendant ce temps est ramassé", len(OUVERTS), 1)
    shutil.rmtree(dl, ignore_errors=True)


def _sans_marque_de_fin():
    image_dpi.complet = lambda b: True


def _ecrase_les_resolutions():
    vrai = image_dpi.traiter
    image_dpi.traiter = lambda chemin, seulement_sans=False: vrai(chemin, False)


def _tout_l_historique():
    veilleur.DEJA_LA = 10 ** 10


SABOTAGES = [
    ("une image est tamponnée sans attendre sa marque de fin", _sans_marque_de_fin,
     ["image à moitié écrite : pas touchée pendant la pause"]),
    ("le mode prudent réécrit aussi les résolutions déclarées", _ecrase_les_resolutions,
     ["JPEG à 300 dpi : laissé (résolution déclarée)"]),
    ("au démarrage, tout le dossier est repris", _tout_l_historique,
     ["image d'il y a 2 h, déjà là : laissée"]),
]


def main():
    b = Banc("VEILLEUR D'IMAGES (72 dpi)")
    banc_images(b)
    ok = b.bilan()

    muets = 0
    if "--sabotages" in sys.argv:
        print("\n=== SABOTAGES : le banc mord-il ? ===")
        for nom, casser, vises in SABOTAGES:
            gardes = (image_dpi.complet, image_dpi.traiter, veilleur.DEJA_LA)
            casser()
            with contextlib.redirect_stdout(io.StringIO()):
                bb = Banc()
                try:
                    banc_images(bb)
                except Exception as e:
                    bb.lignes.append(("incident : %s" % e, False))
            image_dpi.complet, image_dpi.traiter, veilleur.DEJA_LA = gardes
            joues = [n for n, _ in bb.lignes]
            absents = set(vises) - set(joues)
            tombes = set(bb.tombes) & set(vises)
            etat = ("%d témoin(s) visé(s) tombé(s)" % len(tombes)) if tombes \
                else ">>> AUCUN TÉMOIN NE TOMBE <<<"
            if absents:
                etat += "  [JAMAIS JOUÉ : %s]" % ", ".join(sorted(absents))
            print("  %-58s %s" % (nom, etat))
            muets += 0 if tombes else 1
        print("\n  %d sabotage(s) sur %d passent inaperçus" % (muets, len(SABOTAGES)))

    shutil.rmtree(_BAC, ignore_errors=True)
    sys.exit(0 if (ok and not muets) else 1)


if __name__ == "__main__":
    main()
