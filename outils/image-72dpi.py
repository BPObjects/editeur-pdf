# SPDX-License-Identifier: AGPL-3.0-or-later
"""Donne une résolution de 72 dpi aux images qui n'en déclarent aucune (ou qui en
déclarent une supérieure à 96), sans toucher aux pixels.

    python image-72dpi.py image1.jpg image2.png ...      (ou glisser les fichiers sur le .bat)

POURQUOI. Les images produites par Gemini, Copilot et consorts sortent sans
résolution (JFIF « rapport 1:1 », PNG sans pHYs). Sur un écran Windows réglé à
150 %, Archicad imprime alors le coin haut-gauche de l'image, réduit d'un
facteur 1,5 (1365×768 → 910×512 pixels pris tels quels), et le PDF est « tronqué ».
Constaté le 02/11/2026 ; le même JPEG passé par Copilot avec 72 dpi en EXIF sort
entier. Le pilote « Microsoft Print To PDF » n'y est pour rien (témoin GDI).

Ne dépend de rien d'autre que Python : les en-têtes sont réécrits à la main.
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


def _lire_dpi_jfif(seg: bytes):
    if seg[:5] != b"JFIF\0" or len(seg) < 12:
        return None
    unit, xd, yd = seg[7], struct.unpack(">H", seg[8:10])[0], struct.unpack(">H", seg[10:12])[0]
    if xd == 0:
        return None                   # « 0 dpi » (Microsoft Print To PDF en écrit) : pas une résolution
    if unit == 1:
        return xd
    if unit == 2:
        return xd * 2.54
    return None                       # unit 0 = simple rapport d'aspect, pas une résolution


def _exif_patch(seg: bytes) -> tuple[bytes, float | None, bool]:
    """Réécrit XResolution/YResolution (tags 0x11A/0x11B) à DPI dans l'IFD0.
    Rend (segment, dpi lu, modifié)."""
    if seg[:6] != b"Exif\0\0":
        return seg, None, False
    t = bytearray(seg[6:])
    le = t[:2] == b"II"
    e = "<" if le else ">"
    def u(o, n): return int.from_bytes(t[o:o + n], "little" if le else "big")
    try:
        off = u(4, 4); n = u(off, 2)
    except Exception:
        return seg, None, False
    dpi = None; unit = 2; modif = False; pos = {}
    for k in range(n):
        ent = off + 2 + k * 12
        if ent + 12 > len(t):
            return seg, None, False
        tag, typ, cnt, val = u(ent, 2), u(ent + 2, 2), u(ent + 4, 4), u(ent + 8, 4)
        if tag == 0x128 and typ == 3:
            unit = u(ent + 8, 2)
        if tag in (0x11A, 0x11B) and typ == 5 and val + 8 <= len(t):
            pos[tag] = val
            num, den = u(val, 4), u(val + 4, 4)
            if den:
                dpi = num / den
    if dpi is not None and unit == 3:
        dpi *= 2.54
    if pos and (dpi is None or dpi > 96):
        for v in pos.values():
            t[v:v + 8] = struct.pack(e + "II", DPI, 1)
        # l'unité : on force le pouce si le tag existe
        for k in range(n):
            ent = off + 2 + k * 12
            if u(ent, 2) == 0x128 and u(ent + 2, 2) == 3:
                t[ent + 8:ent + 10] = struct.pack(e + "H", 2)
        modif = True
    return b"Exif\0\0" + bytes(t), dpi, modif


def traiter_jpeg(b: bytes) -> tuple[bytes, str]:
    out = bytearray(b[:2]); i = 2
    jfif_vu = False; jfif_dpi = None; exif_dpi = None; modif = False
    segments = []
    while i + 4 <= len(b) and b[i] == 0xFF:
        m = b[i + 1]
        if m == 0xD8 or 0xD0 <= m <= 0xD7:
            i += 2; continue
        L = struct.unpack(">H", b[i + 2:i + 4])[0]
        seg = b[i + 4:i + 2 + L]
        if m == 0xDA:
            break
        if m == 0xE0 and seg[:5] == b"JFIF\0":
            jfif_vu = True
            jfif_dpi = _lire_dpi_jfif(seg)
            if jfif_dpi is None or jfif_dpi > 96:
                seg = seg[:7] + bytes([1]) + struct.pack(">HH", DPI, DPI) + seg[12:]
                modif = True
        elif m == 0xE1 and seg[:6] == b"Exif\0\0":
            seg, exif_dpi, ch = _exif_patch(seg)   # (l'autre APP1, XMP, ne porte pas la résolution)
            modif = modif or ch
        segments.append((m, seg))
        i += 2 + L
    reste = b[i:]
    if not jfif_vu and (exif_dpi is None or exif_dpi > 96):
        # pas de JFIF : on l'ajoute en tête (APP0 doit suivre SOI)
        jf = b"JFIF\0" + bytes([1, 1, 1]) + struct.pack(">HH", DPI, DPI) + b"\0\0"
        segments.insert(0, (0xE0, jf)); modif = True
    if not modif:
        avant = jfif_dpi if jfif_dpi is not None else exif_dpi
        return b, "déjà %g dpi, rien à faire" % avant
    for m, seg in segments:
        out += bytes([0xFF, m]) + struct.pack(">H", len(seg) + 2) + seg
    out += reste
    avant = jfif_dpi if jfif_dpi is not None else exif_dpi
    return bytes(out), ("sans résolution" if avant is None else "%g dpi" % avant) + " -> %d dpi" % DPI


def traiter_png(b: bytes) -> tuple[bytes, str]:
    out = bytearray(b[:8]); i = 8; phys_vu = False; avant = None; modif = False
    while i + 8 <= len(b):
        L = struct.unpack(">I", b[i:i + 4])[0]; t = b[i + 4:i + 8]; data = b[i + 8:i + 8 + L]
        if t == b"pHYs":
            phys_vu = True
            x, y, unit = struct.unpack(">IIB", data)
            if unit == 1:
                avant = x * 0.0254
            if unit != 1 or x > 96 / 0.0254 + 1:
                data = struct.pack(">IIB", PPM, PPM, 1); modif = True
        chunk = struct.pack(">I", len(data)) + t + data
        out += chunk + struct.pack(">I", zlib.crc32(t + data) & 0xFFFFFFFF)
        i += 12 + L
        if t == b"IHDR" and not phys_vu:
            # le pHYs se place avant IDAT ; juste après IHDR convient
            pass
        if t == b"IDAT" or t == b"IEND":
            out += b[i:]
            break
    if not phys_vu:
        # insérer après IHDR (8 + 25 octets)
        data = struct.pack(">IIB", PPM, PPM, 1)
        chunk = struct.pack(">I", 9) + b"pHYs" + data + struct.pack(">I", zlib.crc32(b"pHYs" + data) & 0xFFFFFFFF)
        out = bytearray(b[:33]) + chunk + b[33:]; modif = True
    if not modif:
        return b, "déjà %g dpi, rien à faire" % avant
    return bytes(out), ("sans résolution" if avant is None else "%g dpi" % avant) + " -> %d dpi" % DPI


def traiter(chemin: str) -> str:
    with open(chemin, "rb") as f:
        b = f.read()
    if b[:2] == b"\xff\xd8":
        nb, msg = traiter_jpeg(b)
    elif b[:8] == b"\x89PNG\r\n\x1a\n":
        nb, msg = traiter_png(b)
    else:
        return "format inconnu (ni JPEG ni PNG), laissé tel quel"
    if nb is not b:
        tmp = chemin + ".tmp"
        with open(tmp, "wb") as f:
            f.write(nb)
        os.replace(tmp, chemin)
    return msg


def main(argv):
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(errors="replace")
        except Exception:
            pass
    pause = "--pause" in argv
    fichiers = [a for a in argv[1:] if a != "--pause"]
    if not fichiers:
        print(__doc__); return 1
    for c in fichiers:
        try:
            print("%s : %s" % (os.path.basename(c), traiter(c)))
        except Exception as e:
            print("%s : ÉCHEC — %s" % (os.path.basename(c), e))
    return 0


if __name__ == "__main__":
    code = main(sys.argv)
    if "--pause" in sys.argv:         # lancé par le .bat : laisser lire le résultat
        try:
            input("\nEntrée pour fermer.")
        except EOFError:
            pass
    sys.exit(code)
