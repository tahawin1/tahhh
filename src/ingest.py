"""
Pipeline d'extraction et d'indexation des textes réglementaires et des
dossiers déjà réalisés, dans la base vectorielle Qdrant (RAG).

Usage :
    python3 src/ingest.py --source data/raw_pdfs/maroc_loi_84-12.pdf \\
        --pays maroc --type-document loi --date-version 2013-03-01

Chaque chunk indexé porte des métadonnées obligatoires (voir CLAUDE.md
section 4) : pays, texte_source, date_version, type_document.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

try:
    import pymupdf as fitz  # PyMuPDF (le nom `fitz` est déprécié)
except ImportError:
    fitz = None

try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None
    Image = None

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from embeddings import VECTOR_SIZE, Embedder  # bge-m3, multilingue, 1024 dimensions

COLLECTION = "dossiers_reference"
TAILLE_LOT_EMBEDDING = 16


SEUIL_CARACTERES_PAGE_VIDE = 20  # en-dessous, on considère la page comme un scan sans texte
# Page "scan + en-tête texte" : peu de texte natif (ex. seulement l'en-tête du
# Bulletin officiel) alors que l'essentiel de la page est une image. Cas réel :
# page 2 du Décret 2-14-607 (64 caractères natifs, corps du texte scanné).
SEUIL_CARACTERES_PAGE_PARTIELLE = 300
SEUIL_COUVERTURE_IMAGE = 0.5


def _couverture_images(page) -> float:
    """Fraction de la surface de la page couverte par des images."""
    surface_page = page.rect.width * page.rect.height or 1
    surface = 0.0
    for image in page.get_images(full=True):
        for rect in page.get_image_rects(image[0]):
            surface += rect.width * rect.height
    return min(surface / surface_page, 1.0)


def page_a_ocr(page, texte_natif: str) -> bool:
    """Décide si une page doit passer par l'OCR plutôt que l'extraction native."""
    n = len(texte_natif.strip())
    if n < SEUIL_CARACTERES_PAGE_VIDE:
        return True
    return n < SEUIL_CARACTERES_PAGE_PARTIELLE and _couverture_images(page) >= SEUIL_COUVERTURE_IMAGE


def extraire_texte(chemin: Path, langues_ocr: str = "fra") -> str:
    """
    Extrait le texte brut d'un PDF ou d'un fichier texte.

    Bascule automatiquement en OCR (Tesseract) page par page quand le PDF
    n'a pas de couche de texte native (cas fréquent des textes marocains
    scannés, ex. Loi 84-12 et les Arrêtés 2853-2856 — vérifié sur ce
    projet : 0 caractère en extraction directe).
    """
    if chemin.suffix.lower() == ".txt":
        return chemin.read_text(encoding="utf-8", errors="ignore")

    if fitz is None:
        raise RuntimeError("PyMuPDF n'est pas installé — pip install pymupdf")

    doc = fitz.open(chemin)
    nb_pages = doc.page_count
    pages_texte = []
    pages_ocr = 0

    for page in doc:
        texte_page = page.get_text()
        if not page_a_ocr(page, texte_page):
            pages_texte.append(texte_page)
            continue

        # Page vide/scannée : fallback OCR
        if pytesseract is None:
            print(f"  ! Page scannée dans {chemin.name}, OCR indisponible "
                  f"(pip install pytesseract pillow + apt install tesseract-ocr-fra tesseract-ocr-ara)",
                  file=sys.stderr)
            continue

        pix = page.get_pixmap(dpi=200)
        image = Image.open(__import__("io").BytesIO(pix.tobytes("png")))
        texte_ocr = pytesseract.image_to_string(image, lang=langues_ocr)
        pages_texte.append(texte_ocr)
        pages_ocr += 1

    doc.close()

    if pages_ocr:
        print(f"  (OCR appliqué sur {pages_ocr}/{nb_pages} page(s) de {chemin.name})")

    return "\n".join(pages_texte).strip()


def decouper_en_chunks(texte: str, taille: int = 500, chevauchement: int = 50) -> list[str]:
    """Découpe un texte en segments d'environ `taille` mots, avec chevauchement."""
    mots = texte.split()
    if not mots:
        return []
    chunks = []
    i = 0
    while i < len(mots):
        chunks.append(" ".join(mots[i : i + taille]))
        i += max(taille - chevauchement, 1)
    return chunks


def id_stable(texte: str, index: int) -> int:
    """Génère un id numérique stable à partir du contenu (évite les doublons à ré-indexation identique)."""
    h = hashlib.sha256(f"{texte}-{index}".encode()).hexdigest()
    return int(h[:12], 16)


class Indexeur:
    def __init__(self, host: str = "localhost", port: int = 6333):
        self.client = QdrantClient(host=host, port=port)
        self.embedder = Embedder()
        self._assurer_collection()

    def _assurer_collection(self):
        collections = [c.name for c in self.client.get_collections().collections]
        if COLLECTION not in collections:
            self.client.create_collection(
                collection_name=COLLECTION,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )

    def indexer_fichier(
        self,
        chemin: Path,
        pays: str,
        type_document: str,
        date_version: str,
        texte_source: str | None = None,
        langues_ocr: str = "fra",
    ) -> int:
        """Extrait, découpe, embed et indexe un fichier. Retourne le nombre de chunks indexés."""
        texte = extraire_texte(chemin, langues_ocr=langues_ocr)
        chunks = decouper_en_chunks(texte)
        if not chunks:
            print(f"  ! Aucun texte extrait de {chemin.name}", file=sys.stderr)
            return 0

        source = texte_source or chemin.stem
        vecteurs = []
        for debut in range(0, len(chunks), TAILLE_LOT_EMBEDDING):
            vecteurs.extend(self.embedder.encoder(chunks[debut : debut + TAILLE_LOT_EMBEDDING]))

        points = []
        for i, (chunk, vecteur) in enumerate(zip(chunks, vecteurs)):
            points.append(
                PointStruct(
                    id=id_stable(str(chemin), i),
                    vector=vecteur,
                    payload={
                        "texte": chunk,
                        "pays": pays,
                        "texte_source": source,
                        "type_document": type_document,
                        "date_version": date_version,
                        "fichier": chemin.name,
                        "chunk_index": i,
                        "embedding": self.embedder.identifiant,
                    },
                )
            )

        self.client.upsert(collection_name=COLLECTION, points=points)
        return len(points)


def main():
    parser = argparse.ArgumentParser(description="Indexe un texte réglementaire dans Qdrant")
    parser.add_argument("--source", required=True, help="Chemin du fichier PDF ou TXT")
    parser.add_argument("--pays", required=True, choices=["maroc", "chine", "inde", "union_europeenne"])
    parser.add_argument("--type-document", required=True, choices=["loi", "decret", "arrete", "reglement", "annexe_technique"])
    parser.add_argument("--date-version", required=True, help="Date de la version du texte, format AAAA-MM-JJ")
    parser.add_argument("--texte-source", help="Nom lisible du texte (ex: 'Loi 84-12')")
    parser.add_argument("--langues-ocr", default="fra", help="Langues Tesseract si le PDF est scanné (ex: fra, eng, fra+ara)")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=6333)
    args = parser.parse_args()

    chemin = Path(args.source)
    if not chemin.exists():
        print(f"Fichier introuvable : {chemin}", file=sys.stderr)
        sys.exit(1)

    print(f"Indexation de {chemin.name} (pays={args.pays}, type={args.type_document})...")
    indexeur = Indexeur(host=args.host, port=args.port)
    n = indexeur.indexer_fichier(
        chemin,
        pays=args.pays,
        type_document=args.type_document,
        date_version=args.date_version,
        texte_source=args.texte_source,
        langues_ocr=args.langues_ocr,
    )
    print(f"{n} chunks indexés.")


if __name__ == "__main__":
    main()
