# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fabrique le PDF de relecture qui sert de témoin au banc des commentaires.

On ne prend pas un vrai document de projet : il contiendrait des données de
chantier, et ce dépôt est public. On fabrique donc un document qui porte les
mêmes CAS : six types d'annotation, trois relecteurs, une page sans aucun
commentaire, une page tournée à 90°, et trois formes de date — complète, sans
heure, et illisible.
"""
import os
import pymupdf

ICI = os.path.dirname(os.path.abspath(__file__))
SORTIE = os.path.join(ICI, "essai-commente.pdf")


def main():
    d = pymupdf.open()

    # ------------------------------------------------------------- page 1
    p = d.new_page(width=595, height=842)
    p.insert_text((60, 90), "Programme technique - Batiment L1", fontsize=18)
    p.insert_text((60, 130), "La hauteur libre sous ferme est de 9,50 m.", fontsize=11)
    p.insert_text((60, 160), "L'atelier d'assemblage final occupe 443 m2.", fontsize=11)
    p.insert_text((60, 190), "Les ponts roulants ont une CMU de 3 T.", fontsize=11)

    a = p.add_text_annot((520, 85), "Verifier avec le lot structure : 9,50 m est-il\n"
                                    "compatible avec la retombee des fermes ?")
    a.set_info(title="Olivier HART", subject="Hauteur libre",
               creationDate="D:20261006091500+02'00'", modDate="D:20261007143022+02'00'")
    a.update()

    r = p.search_for("443 m2")
    if r:
        a = p.add_highlight_annot(r[0])
        a.set_info(title="Marie DUBOIS", content="Le programme dit 450 m2 au chapitre 4.",
                   modDate="D:20261008")                     # date sans heure
        a.update()

    r = p.search_for("CMU de 3 T")
    if r:
        a = p.add_underline_annot(r[0])
        a.set_info(title="Olivier HART", content="A confirmer : le CCTP annonce 5 T.")
        a.update()

    a = p.add_freetext_annot(pymupdf.Rect(60, 230, 300, 280),
                             "Manque le plan de calepinage des dalles.", fontsize=10)
    a.set_info(title="Marie DUBOIS", subject="Piece manquante")
    a.update()

    # ------------------------------- page 2 : paysage, pour éprouver la rotation
    p = d.new_page(width=842, height=595)
    p.insert_text((60, 90), "Folio 16 - Plan de masse", fontsize=18)
    p.insert_text((60, 130), "Zone de stockage hors LOG : 75 m2.", fontsize=11)

    a = p.add_rect_annot(pymupdf.Rect(300, 200, 520, 340))
    a.set_info(title="Jean-Claude LAISNE", content="Cette zone empiete sur la voie pompier.")
    a.set_colors(stroke=(1, 0, 0))
    a.update()

    a = p.add_ink_annot([[(100, 300), (160, 330), (220, 300), (280, 340)]])
    a.set_info(title="Jean-Claude LAISNE", content="Trace a reprendre.",
               modDate="pas une date")                       # forme inattendue
    a.update()

    r = p.search_for("75 m2")
    if r:
        a = p.add_strikeout_annot(r[0])
        a.set_info(title="Marie DUBOIS", content="Lire 56 m2.")
        a.update()

    # ------------------------------------------ page 3 : aucun commentaire
    p = d.new_page(width=595, height=842)
    p.insert_text((60, 90), "Page sans aucun commentaire", fontsize=14)

    # ------------------------------------------------- page 4 : tournée 90°
    p = d.new_page(width=595, height=842)
    p.insert_text((60, 90), "Page tournee a 90 degres", fontsize=14)
    a = p.add_text_annot((400, 500), "Commentaire sur une page tournee.")
    a.set_info(title="Olivier HART")
    a.update()
    p.set_rotation(90)

    d.save(SORTIE)
    d.close()

    v = pymupdf.open(SORTIE)
    total = sum(1 for pg in v for _ in pg.annots())
    print("  %s" % SORTIE)
    print("  %d annotations sur %d pages (rotation p4 = %d°)"
          % (total, len(v), v[3].rotation))
    v.close()


if __name__ == "__main__":
    main()
