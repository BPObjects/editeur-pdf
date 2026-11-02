# SPDX-License-Identifier: AGPL-3.0-or-later
"""Donne 72 dpi aux images qui ne déclarent aucune résolution, sans toucher aux pixels.

    python image_dpi.py image1.jpg image2.png ...
    (ou glisser les fichiers sur « outils/Image 72 dpi (glisser ici).bat »)

Le veilleur d'impression s'en sert aussi : il tamponne tout seul les images qui
arrivent dans le dossier Téléchargements (mode prudent, voir `tamponner`).

POURQUOI. Les images produites par Gemini, Copilot et consorts sortent sans
résolution (JFIF « rapport 1:1 », PNG sans pHYs). Sur un écran Windows réglé à
150 %, Archicad imprime alors le coin haut-gauche de l'image, réduit d'un
facteur 1,5 (1365×768 → 910×512 pixels pris tels quels) : le PDF est
« tronqué ». Constaté le 02/11/2026 ; le JPEG Copilot qui portait 72 dpi en
EXIF est sorti entier, et une image tamponnée à 72 dpi aussi (vérifié par AL).
Le pilote « Microsoft Print To PDF » n'y est pour rien (témoin GDI).

Aucune dépendance : les en-têtes sont réécrits à la main.
JPEG : segment APP0 JFIF (ajouté s'il manque) + XResolution/YResolution EXIF.
PNG  : chunk pHYs (ajouté ou remplacé), 2835 px/m = 72 dpi.
"""
from __future__ import annotations

import os
import struct
import sys
import zlib

DPI = 72
PPM = int(round(DPI / 0.0254))     # 2835 pixels par mètre
PLAFOND = 96                       # au-delà, le mode manuel ramène aussi à 72

SIG_PNG = b"\x89PNG\r\n\x1a\n"
FIN_PNG = b"\x00\x00\x00\x00IEND\xaeB`\x82"
EXIF = b"Exif\x00\x00"
JFIF = b"JFIF\x00"


# ------------------------------------------------------------------- lecture
def _segments_jpeg(b: bytes):
    """Les segments d'en-tête jusqu'au début des données (SOS exclu), et
    l'indice où commence le reste du fichier."""
    segs = []
    i = 2
    while i + 4 <= len(b) and b[i] == 0xFF:
        m = b[i + 1]
        if m == 0xFF:                      # octet de bourrage
            i += 1
            continue
        if m == 0xD8 or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        if m == 0xDA:
            break
        L = struct.unpack(">H", b[i + 2:i + 4])[0]
        segs.append((m, b[i + 4:i + 2 + L]))
        i += 2 + L
    return segs, i


def _dpi_jfif(seg: bytes):
    if seg[:5] != JFIF or len(seg) < 12:
        return None
    unit = seg[7]
    xd = struct.unpack(">H", seg[8:10])[0]
    if xd == 0:
        return None          # « 0 dpi » (Microsoft Print To PDF en écrit) : pas une résolution
    if unit == 1:
        return float(xd)
    if unit == 2:
        return xd * 2.54
    return None              # unité 0 = simple rapport d'aspect


def _ifd0_exif(seg: bytes):
    """(tiff, petit-boutiste, entrées de l'IFD0 {tag: (type, valeur, position)})."""
    t = seg[len(EXIF):]
    if t[:2] not in (b"II", b"MM"):
        return None
    le = t[:2] == b"II"

    def u(o, n):
        return int.from_bytes(t[o:o + n], "little" if le else "big")
    off = u(4, 4)
    if off + 2 > len(t):
        return None
    n = u(off, 2)
    entrees = {}
    for k in range(n):
        e = off + 2 + k * 12
        if e + 12 > len(t):
            return None
        entrees[u(e, 2)] = (u(e + 2, 2), u(e + 8, 4), e)
    return t, le, entrees


def _dpi_exif(seg: bytes):
    lu = _ifd0_exif(seg) if seg[:6] == EXIF else None
    if not lu:
        return None
    t, le, ent = lu
    if 0x11A not in ent or ent[0x11A][0] != 5:
        return None
    v = ent[0x11A][1]
    if v + 8 > len(t):
        return None
    num = int.from_bytes(t[v:v + 4], "little" if le else "big")
    den = int.from_bytes(t[v + 4:v + 8], "little" if le else "big")
    if not den or not num:
        return None
    dpi = num / den
    if 0x128 in ent and ent[0x128][0] == 3:
        brut = ent[0x128][1]
        unite = (brut & 0xFFFF) if le else (brut >> 16)
        if unite == 3:
            dpi *= 2.54
        elif unite == 1:
            return None
    return dpi


def resolution(b: bytes):
    """La résolution que l'image DÉCLARE, en dpi, ou None si elle n'en déclare pas."""
    if b[:2] == b"\xff\xd8":
        segs, _ = _segments_jpeg(b)
        jf = next((_dpi_jfif(s) for m, s in segs if m == 0xE0 and s[:5] == JFIF), None)
        if jf is not None:
            return jf
        return next((_dpi_exif(s) for m, s in segs if m == 0xE1 and s[:6] == EXIF), None)
    if b[:8] == SIG_PNG:
        i = 8
        while i + 8 <= len(b):
            L = struct.unpack(">I", b[i:i + 4])[0]
            ty = b[i + 4:i + 8]
            if ty == b"pHYs" and L == 9:
                x, _, unit = struct.unpack(">IIB", b[i + 8:i + 17])
                return x * 0.0254 if unit == 1 and x else None
            if ty in (b"IDAT", b"IEND"):
                return None
            i += 12 + L
    return None


def complet(b: bytes) -> bool:
    """Le fichier est-il ENTIER ? JPEG : il finit par EOI. PNG : par IEND.
    Même leçon que pour les PDF du veilleur : « la taille ne bouge plus » ne
    prouve pas qu'un fichier est fini ; sa marque de fin, si."""
    if b[:2] == b"\xff\xd8":
        return b.rstrip(b"\x00")[-2:] == b"\xff\xd9"
    if b[:8] == SIG_PNG:
        return b.endswith(FIN_PNG)
    return False


# ------------------------------------------------------------------ écriture
def _a_faire(dpi, seulement_sans: bool) -> bool:
    if dpi is None:
        return True
    return not seulement_sans and dpi > PLAFOND


def _jpeg(b: bytes, seulement_sans: bool):
    segs, reste = _segments_jpeg(b)
    avant = resolution(b)
    if not _a_faire(avant, seulement_sans):
        return b, avant
    neufs = []
    jfif_vu = False
    for m, s in segs:
        if m == 0xE0 and s[:5] == JFIF and len(s) >= 12:
            jfif_vu = True
            s = s[:7] + bytes([1]) + struct.pack(">HH", DPI, DPI) + s[12:]
        elif m == 0xE1 and s[:6] == EXIF:
            lu = _ifd0_exif(s)
            if lu:
                t, le, ent = lu
                t = bytearray(t)
                e = "<" if le else ">"
                for tag in (0x11A, 0x11B):
                    if tag in ent and ent[tag][0] == 5 and ent[tag][1] + 8 <= len(t):
                        v = ent[tag][1]
                        t[v:v + 8] = struct.pack(e + "II", DPI, 1)
                if 0x128 in ent and ent[0x128][0] == 3:
                    p = ent[0x128][2] + 8
                    t[p:p + 2] = struct.pack(e + "H", 2)          # pouces
                s = EXIF + bytes(t)
        neufs.append((m, s))
    if not jfif_vu:
        neufs.insert(0, (0xE0, JFIF + bytes([1, 1, 1]) + struct.pack(">HH", DPI, DPI) + b"\x00\x00"))
    out = bytearray(b"\xff\xd8")
    for m, s in neufs:
        out += bytes([0xFF, m]) + struct.pack(">H", len(s) + 2) + s
    out += b[reste:]
    return bytes(out), avant


def _png(b: bytes, seulement_sans: bool):
    avant = resolution(b)
    if not _a_faire(avant, seulement_sans):
        return b, avant
    data = struct.pack(">IIB", PPM, PPM, 1)
    phys = (struct.pack(">I", 9) + b"pHYs" + data
            + struct.pack(">I", zlib.crc32(b"pHYs" + data) & 0xFFFFFFFF))
    out = bytearray(b[:8])
    i = 8
    pose = False
    while i + 8 <= len(b):
        L = struct.unpack(">I", b[i:i + 4])[0]
        ty = b[i + 4:i + 8]
        bloc = b[i:i + 12 + L]
        if ty == b"pHYs":
            bloc = phys if not pose else b""
            pose = True
        elif ty in (b"IDAT", b"IEND") and not pose:
            out += phys                    # pHYs se place avant les données
            pose = True
        out += bloc
        i += 12 + L
        if ty == b"IEND":
            break
    out += b[i:]
    return bytes(out), avant


def tamponner(b: bytes, seulement_sans: bool = False):
    """Rend (octets, résolution d'avant, modifié). Les pixels ne sont pas touchés.

    seulement_sans=False (glisser-déposer, geste volontaire) : tamponne une
    image sans résolution OU qui en déclare plus de 96.
    seulement_sans=True (veilleur, automatique) : ne remplit QUE l'absence —
    une résolution déclarée est une intention, on ne la réécrit pas dans le dos
    de l'utilisateur."""
    if b[:2] == b"\xff\xd8":
        nb, avant = _jpeg(b, seulement_sans)
    elif b[:8] == SIG_PNG:
        nb, avant = _png(b, seulement_sans)
    else:
        raise ValueError("ni JPEG ni PNG")
    return nb, avant, nb != b


def traiter(chemin: str, seulement_sans: bool = False):
    """Tamponne le fichier sur place. Rend (modifié, message).

    Écrit dans un fichier voisin puis le substitue : jamais d'image à moitié
    écrite. La date de modification est GARDÉE (le tri du dossier ne bouge
    pas), et la marque « téléchargé d'Internet » (flux Zone.Identifier) suit."""
    st = os.stat(chemin)
    with open(chemin, "rb") as f:
        b = f.read()
    if not complet(b):
        raise ValueError("fichier incomplet (pas de marque de fin)")
    nb, avant, modifie = tamponner(b, seulement_sans)
    if not modifie:
        return False, "déjà %g dpi, rien à faire" % avant
    tmp = chemin + ".dpi72.tmp"
    with open(tmp, "wb") as f:
        f.write(nb)
    if os.name == "nt":
        try:
            with open(chemin + ":Zone.Identifier", "rb") as f:
                zone = f.read()
            with open(tmp + ":Zone.Identifier", "wb") as f:
                f.write(zone)
        except OSError:
            pass
    try:
        os.replace(tmp, chemin)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    try:
        os.utime(chemin, ns=(st.st_atime_ns, st.st_mtime_ns))
    except OSError:
        pass
    return True, ("sans résolution" if avant is None else "%g dpi" % avant) + " -> %d dpi" % DPI


def main(argv):
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(errors="replace")
        except Exception:
            pass
    fichiers = [a for a in argv[1:] if a != "--pause"]
    if not fichiers:
        print(__doc__)
        return 1
    code = 0
    for c in fichiers:
        try:
            print("%s : %s" % (os.path.basename(c), traiter(c)[1]))
        except Exception as e:
            print("%s : ÉCHEC — %s" % (os.path.basename(c), e))
            code = 1
    return code


if __name__ == "__main__":
    code = main(sys.argv)
    if "--pause" in sys.argv:         # lancé par le .bat : laisser lire le résultat
        try:
            input("\nEntrée pour fermer.")
        except EOFError:
            pass
    sys.exit(code)
