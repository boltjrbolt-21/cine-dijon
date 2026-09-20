#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fabrique l'icone du site et l'image d'apercu partagee sur les messageries.

    python scripts/images.py

Produit, a la racine du projet :
    icone.svg        favicon vectoriel (net a toutes les tailles)
    icone-180.png    icone d'ecran d'accueil iOS
    icone-512.png    icone generique
    partage.png      1200x630, la vignette affichee par WhatsApp, SMS, Slack...

Depend de Pillow. Les images produites sont versionnees : ce script ne sert
qu'a les regenerer si la charte change.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RACINE = Path(__file__).resolve().parent.parent

ENCRE = (20, 19, 17)
ROUGE = (180, 35, 31)
BLANC = (246, 245, 243)
GRIS = (161, 154, 146)

# Polices Windows ; on retombe sur la police par defaut si elles manquent.
POLICES = {
    "grasse": ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"],
    "normale": ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"],
}


def police(genre: str, taille: int):
    for chemin in POLICES[genre]:
        if Path(chemin).exists():
            return ImageFont.truetype(chemin, taille)
    print(f"  (police {genre} introuvable, rendu approximatif)", file=sys.stderr)
    return ImageFont.load_default(taille)


def pellicule(dessin: ImageDraw.ImageDraw, boite, couleur, perforation) -> None:
    """Une photo de pellicule : un cadre plein borde de perforations."""
    gauche, haut, droite, bas = boite
    largeur = droite - gauche
    dessin.rounded_rectangle(boite, radius=perforation, fill=couleur)

    # Les perforations sont evidees en haut et en bas du cadre.
    nombre = 4
    pas = largeur / nombre
    cote = perforation * 1.1
    for i in range(nombre):
        centre = gauche + pas * (i + 0.5)
        for y in (haut + perforation * 1.6, bas - perforation * 1.6):
            dessin.rounded_rectangle(
                [centre - cote / 2, y - cote / 2, centre + cote / 2, y + cote / 2],
                radius=cote * 0.3, fill=ROUGE,
            )


def icone(taille: int = 1024) -> Image.Image:
    """Carre rouge arrondi, cadre de pellicule blanc au centre."""
    image = Image.new("RGBA", (taille, taille), (0, 0, 0, 0))
    dessin = ImageDraw.Draw(image)
    dessin.rounded_rectangle([0, 0, taille, taille], radius=taille * 0.22, fill=ROUGE)

    marge = taille * 0.17
    pellicule(dessin, [marge, marge * 1.25, taille - marge, taille - marge * 1.25],
              BLANC, taille * 0.052)
    return image


def horaires(dessin: ImageDraw.ImageDraw, x: int, y: int) -> None:
    """Reprend les pastilles d'horaires de la page, pour que la vignette dise
    d'un coup d'oeil de quoi il s'agit."""
    f_salle = police("grasse", 25)
    f_heure = police("grasse", 30)

    for salle, heures in (("PATHÉ DIJON", ["13h15", "15h30", "20h00"]),
                          ("ELDORADO", ["14h00", "20h45"])):
        dessin.text((x, y), salle, font=f_salle, fill=GRIS)
        y += 46
        gauche = x
        for h in heures:
            largeur = dessin.textlength(h, font=f_heure) + 44
            dessin.rounded_rectangle([gauche, y, gauche + largeur, y + 62],
                                     radius=13, outline=(60, 56, 51), width=3)
            dessin.text((gauche + 22, y + 14), h, font=f_heure, fill=BLANC)
            gauche += largeur + 16
        y += 104


def apercu() -> Image.Image:
    """1200x630 : le visuel qui accompagne le lien quand on le partage."""
    largeur, hauteur = 1200, 630
    image = Image.new("RGB", (largeur, hauteur), ENCRE)
    dessin = ImageDraw.Draw(image)

    # Bande de pellicule rouge en pied de vignette.
    bande = 56
    dessin.rectangle([0, hauteur - bande, largeur, hauteur], fill=ROUGE)
    for i in range(14):
        x = 54 + i * 86
        dessin.rounded_rectangle([x, hauteur - 40, x + 38, hauteur - 16],
                                 radius=6, fill=ENCRE)

    vignette = icone(150)
    image.paste(vignette, (86, 74), vignette)

    titre_a, titre_b = "Ciné ", "Dijon"
    f_titre = police("grasse", 96)
    f_sous = police("normale", 38)
    f_note = police("normale", 29)

    x, y = 86, 258
    dessin.text((x, y), titre_a, font=f_titre, fill=BLANC)
    dessin.text((x + dessin.textlength(titre_a, font=f_titre), y), titre_b,
                font=f_titre, fill=(255, 107, 94))

    dessin.text((x, y + 124),
                "Tous les films à l'affiche dans les six", font=f_sous, fill=BLANC)
    dessin.text((x, y + 124 + 48),
                "salles de l'agglo, résumés en une ligne.", font=f_sous, fill=BLANC)
    dessin.text((x, y + 124 + 110),
                "VF et VO · mis à jour chaque jour", font=f_note, fill=GRIS)

    horaires(dessin, 742, 148)
    return image


SVG = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect width="100" height="100" rx="22" fill="rgb{ROUGE}"/>
  <rect x="17" y="21" width="66" height="58" rx="5" fill="rgb{BLANC}"/>
  {"".join(
      f'<rect x="{20.5 + i * 16.5:.1f}" y="{y}" width="9" height="9" rx="2.5" fill="rgb{ROUGE}"/>'
      for i in range(4) for y in (25, 66)
  )}
</svg>
'''


def main() -> int:
    icone_max = icone()
    for taille in (180, 512):
        chemin = RACINE / f"icone-{taille}.png"
        icone_max.resize((taille, taille), Image.LANCZOS).save(chemin)
        print(f"  {chemin.name}")

    (RACINE / "icone.svg").write_text(SVG, encoding="utf-8")
    print("  icone.svg")

    apercu().save(RACINE / "partage.png", optimize=True)
    print("  partage.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
