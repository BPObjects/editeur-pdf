# SPDX-License-Identifier: AGPL-3.0-or-later
"""Icône de l'application : carré orange arrondi, « PDF » en blanc ; aux petites
tailles le mot devient illisible, on dessine une feuille au coin plié à la place.

    python make_icon.py            -> icon.ico (et icon-256.png)
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

ORANGE = (232, 89, 12, 255)
BLANC = (255, 255, 255, 255)
TAILLES = (256, 128, 64, 48, 32, 24, 16)
POLICES = (r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf")


def police(taille: int):
    for p in POLICES:
        if os.path.isfile(p):
            return ImageFont.truetype(p, taille)
    return ImageFont.load_default()


def dessiner(n: int) -> Image.Image:
    k = 4  # suréchantillonnage pour des bords propres
    im = Image.new("RGBA", (n * k, n * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = n * k * 0.2
    d.rounded_rectangle((0, 0, n * k - 1, n * k - 1), radius=r, fill=ORANGE)
    if n >= 48:
        f = police(int(n * k * 0.40))
        d.text((n * k / 2, n * k / 2 + n * k * 0.02), "PDF", font=f, fill=BLANC, anchor="mm")
    else:
        # feuille blanche au coin plié
        m = n * k * 0.22
        x0, y0, x1, y1 = m, m * 0.8, n * k - m, n * k - m * 0.8
        pli = (x1 - x0) * 0.32
        d.polygon([(x0, y0), (x1 - pli, y0), (x1, y0 + pli), (x1, y1), (x0, y1)], fill=BLANC)
        d.polygon([(x1 - pli, y0), (x1 - pli, y0 + pli), (x1, y0 + pli)], fill=(255, 200, 170, 255))
    return im.resize((n, n), Image.LANCZOS)


def main():
    ici = os.path.dirname(os.path.abspath(__file__))
    images = [dessiner(n) for n in TAILLES]
    images[0].save(os.path.join(ici, "icon-256.png"))
    images[0].save(os.path.join(ici, "icon.ico"), format="ICO", sizes=[(n, n) for n in TAILLES],
                   append_images=images[1:])
    print("icon.ico :", TAILLES)


if __name__ == "__main__":
    main()
