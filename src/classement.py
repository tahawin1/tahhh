"""
Dépôt groupé : range chaque fichier reçu du fournisseur dans sa pièce.

Décision prise par le CODE, jamais par l'IA, et seulement sur des indices
sûrs :
1. le numéro en tête du nom de fichier (« 4-4-EC_Certificate….pdf » -> pièce 4),
   convention des dossiers déposés ;
2. sinon des mots caractéristiques du nom (ISO 13485, EC certificate, DoC,
   label, IFU, catalogue…).
Un fichier sans indice sûr, ou qui correspond à deux pièces, n'est pas rangé :
il est signalé pour un dépôt à la main.
"""
from __future__ import annotations

import re
import unicodedata

NUMERO = re.compile(r"^\s*(\d{1,2})\s*[-_. ]")

# (code de pièce, motifs sur le nom normalisé) — « piece_specifique » : certificat
# CE / NMPA / CDSCO / de libre vente selon l'origine (pièce 4)
MOTS = [
    ("iso_13485", [r"13485"]),
    ("piece_specifique", [r"\bec\b.*certif", r"\bce\b.*certif", r"certif.*\bc?e\b", r"\bce\d{3,}", r"marquage\s*ce",
                          r"\bnmpa\b", r"\bcdsco\b", r"free\s*sale", r"\bfsc\b", r"libre\s*vente",
                          r"confirmation\s*letter", r"lettre\s*de\s*confirmation", r"2023\s*607"]),
    ("declaration_conformite", [r"\bdoc\b", r"declaration\s*(of|de)\s*conformit", r"\bconformity\b"]),
    ("attestation_fabricant", [r"authori[sz]ation", r"autorisation", r"attestation", r"\bmandat"]),
    ("etiquetage", [r"\blabels?\b", r"etiquet"]),
    ("notice", [r"\bifu\b", r"notice", r"instructions?\s*(for|d)"]),
    ("catalogue", [r"catalog"]),
    ("echantillon", [r"\bphotos?\b"]),
]


def _normaliser(nom: str) -> str:
    t = unicodedata.normalize("NFKD", nom)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"\.(pdf|png|jpe?g)$", "", t)
    return re.sub(r"[_\-.()\[\]]+", " ", t)


def _correspond(code_regle: str, code_piece: str) -> bool:
    return code_piece == code_regle or (code_regle == "piece_specifique" and code_piece.startswith("piece_specifique"))


def classer(nom_fichier: str, pieces: list) -> tuple[object | None, str]:
    """(pièce, raison) ou (None, raison). `pieces` : pièces à fournir du dossier
    (objets avec code, numero, nom)."""
    if m := NUMERO.match(nom_fichier):
        numero = int(m.group(1))
        trouvees = [p for p in pieces if p.numero == numero]
        if trouvees:
            return trouvees[0], f"numéro {numero} en tête du nom du fichier"
    nom = _normaliser(nom_fichier)
    candidats = []
    for code, motifs in MOTS:
        if any(re.search(m, nom) for m in motifs):
            candidats += [p for p in pieces if _correspond(code, p.code) and p not in candidats]
    if len(candidats) > 1 and re.search(r"13485", nom):  # « certificat CE ISO 13485 » : c'est l'ISO
        candidats = [p for p in candidats if p.code == "iso_13485"]
    if len(candidats) == 1:
        return candidats[0], "mots du nom du fichier"
    if len(candidats) > 1:
        return None, "plusieurs pièces possibles (" + ", ".join(f"pièce {p.numero}" for p in candidats) + ") : déposer à la main"
    return None, "nom du fichier non reconnu : déposer à la main dans la bonne pièce"


def reunir(elements: list[tuple[str, str, bytes]]) -> tuple[str, str, bytes]:
    """Un seul fichier : inchangé. Plusieurs (certificat + lettre de
    confirmation, plusieurs étiquettes) : réunis en un PDF, dans l'ordre des noms."""
    if len(elements) == 1:
        return elements[0]
    import pymupdf

    sortie = pymupdf.open()
    for nom, extension, contenu in sorted(elements):
        source = pymupdf.open(stream=contenu, filetype=extension.lstrip("."))
        if extension != ".pdf":
            source = pymupdf.open("pdf", source.convert_to_pdf())
        sortie.insert_pdf(source)
    noms = " + ".join(nom for nom, _, _ in sorted(elements))
    return (noms[:280] + ".pdf", ".pdf", sortie.tobytes(garbage=3, deflate=True))
