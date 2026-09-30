"""
Génère des documents SPÉCIMEN (fictifs, marqués comme tels) pour tester la
lecture des documents reçus du fournisseur, en attendant de vrais dossiers.

    python tests/fixtures/generer_specimens.py

Toutes les entreprises, numéros et dates sont inventés.
"""
import io
import random
from pathlib import Path

import pymupdf
from PIL import Image, ImageFilter

ICI = Path(__file__).resolve().parent
MENTION = "SPECIMEN - DOCUMENT FICTIF POUR TESTS - SANS VALEUR"


def page_texte(lignes: list[tuple[str, float, bool]]) -> pymupdf.Document:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 40), MENTION, fontsize=10, color=(0.75, 0, 0))
    y = 90
    for texte, taille, gras in lignes:
        if texte:
            page.insert_text((60, y), texte, fontsize=taille, fontname="hebo" if gras else "helv")
        y += taille * 1.9
    page.insert_text((60, 810), MENTION, fontsize=10, color=(0.75, 0, 0))
    return doc


ISO = [
    ("SPECIMEN CERTIFICATION BODY GmbH", 16, True),
    ("Notified quality system registrar (fictitious)", 10, False),
    ("", 10, False),
    ("CERTIFICATE", 22, True),
    ("Certificate No. SCB-MD-2024-0457", 13, True),
    ("", 10, False),
    ("This is to certify that the quality management system of", 11, False),
    ("Hangzhou Specimen Orthopaedics Co., Ltd.", 13, True),
    ("No. 88 Fictional Road, Binjiang District, Hangzhou, China", 11, False),
    ("has been assessed and found to comply with the requirements of", 11, False),
    ("ISO 13485:2016", 14, True),
    ("Scope: Design and manufacture of hip joint prostheses", 11, False),
    ("(femoral stems, acetabular cups, femoral heads).", 11, False),
    ("", 10, False),
    ("Date of issue: 12 March 2024", 11, False),
    ("Valid until: 11 March 2027", 11, False),
    ("", 10, False),
    ("For the certification body: Dr. A. Placeholder, Head of Certification", 10, False),
]

NMPA = [
    ("TRADUCTION ASSERMENTÉE (SPÉCIMEN)", 14, True),
    ("Traduction du chinois vers le français", 10, False),
    ("", 10, False),
    ("Administration nationale des produits médicaux (NMPA)", 12, True),
    ("CERTIFICAT D'ENREGISTREMENT DE DISPOSITIF MÉDICAL", 14, True),
    ("", 10, False),
    ("Numéro d'enregistrement : Guo Xie Zhu Zhun 20213130457", 11, False),
    ("Titulaire de l'enregistrement : Hangzhou Specimen Orthopaedics Co., Ltd.", 11, False),
    ("Adresse : No. 88 Fictional Road, Binjiang District, Hangzhou, Chine", 11, False),
    ("Nom du produit : Prothèse totale de hanche non cimentée", 11, False),
    ("Classe de gestion : Classe III", 11, False),
    ("Composition : tige fémorale en alliage de titane, cotyle, tête fémorale en céramique", 11, False),
    ("", 10, False),
    ("Date d'approbation : 15/06/2021", 11, False),
    ("Date d'expiration : 14/06/2026", 11, False),
    ("", 10, False),
    ("Traduction certifiée conforme, M. Traducteur Fictif, traducteur assermenté", 10, False),
]


def enregistrer(doc: pymupdf.Document, nom: str) -> Path:
    chemin = ICI / nom
    doc.save(chemin)
    return chemin


def version_scannee(source: Path, nom: str) -> Path:
    """Simule un scan : rendu en image, légère rotation, flou et bruit, sans couche texte."""
    random.seed(4)
    page = pymupdf.open(source)[0]
    image = Image.open(io.BytesIO(page.get_pixmap(dpi=150).tobytes("png"))).convert("L")
    image = image.rotate(0.8, expand=True, fillcolor=255).filter(ImageFilter.GaussianBlur(0.6))
    pixels = image.load()
    for _ in range(4000):
        x, y = random.randrange(image.width), random.randrange(image.height)
        pixels[x, y] = random.choice((0, 255))
    tampon = io.BytesIO()
    image.save(tampon, format="PNG")
    doc = pymupdf.open()
    p = doc.new_page(width=595, height=842)
    p.insert_image(p.rect, stream=tampon.getvalue())
    return enregistrer(doc, nom)


if __name__ == "__main__":
    iso = enregistrer(page_texte(ISO), "specimen_iso13485.pdf")
    version_scannee(iso, "specimen_iso13485_scanne.pdf")
    enregistrer(page_texte(NMPA), "specimen_nmpa_traduction.pdf")
    for f in sorted(ICI.glob("specimen_*.pdf")):
        print(f.name, f.stat().st_size // 1024, "Ko")
