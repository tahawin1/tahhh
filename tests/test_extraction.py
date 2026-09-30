"""
Tests du contrôle des extractions (sans Mistral) : c'est ce contrôle qui
empêche une valeur inventée par l'IA d'être présentée comme vérifiée.

    python -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from extraction import (  # noqa: E402
    ABSENT, CITATION_INTROUVABLE, VALEUR_HORS_CITATION, VERIFIE,
    citation_trouvee, controler, normaliser_date,
)

TEXTE = """SPECIMEN CERTIFICATION BODY
CERTIFICATE No. SCB-MD-2024-0457
This is to certify that the quality management system of
Hangzhou Specimen Orthopaedics Co., Ltd.
has been assessed and found to comply with ISO 13485:2016
Scope: Design and manufacture of hip joint prostheses
Date of issue: 12 March 2024      Valid until: 11 March 2027"""

CHAMPS = [
    {"nom": "numero", "libelle": "Numéro", "type": "texte"},
    {"nom": "titulaire", "libelle": "Titulaire", "type": "texte"},
    {"nom": "date_expiration", "libelle": "Valable jusqu'au", "type": "date"},
    {"nom": "classe_indiquee", "libelle": "Classe", "type": "texte"},
]


class TestDates(unittest.TestCase):
    def test_formats(self):
        for brut, attendu in [
            ("12 March 2024", "2024-03-12"), ("March 12, 2024", "2024-03-12"), ("12/03/2024", "2024-03-12"),
            ("2024-03-12", "2024-03-12"), ("12 mars 2024", "2024-03-12"), ("1er août 2025", "2025-08-01"),
            ("2024年3月12日", "2024-03-12"), ("12.03.2024", "2024-03-12"),
        ]:
            self.assertEqual(normaliser_date(brut), attendu, brut)

    def test_illisible_ou_impossible(self):
        for brut in ("bientôt", "31/02/2024", "", None):
            self.assertIsNone(normaliser_date(brut), brut)


class TestCitations(unittest.TestCase):
    def test_exacte_malgre_casse_espaces_accents(self):
        self.assertTrue(citation_trouvee("certificate  no. scb-md-2024-0457", TEXTE))

    def test_tolere_une_erreur_ocr(self):
        self.assertTrue(citation_trouvee("Hangzhou Specimen 0rthopaedics Co., Ltd. has been assessed", TEXTE))

    def test_refuse_une_citation_inventee(self):
        self.assertFalse(citation_trouvee("Rue du Trône, Rabat, Maroc", TEXTE))

    def test_refuse_des_mots_pioches_dans_tout_le_document(self):
        self.assertFalse(citation_trouvee("certificate hip valid 2027 specimen", TEXTE))


class TestControle(unittest.TestCase):
    def test_verdicts(self):
        reponse = {
            "numero": {"valeur": "SCB-MD-2024-0457", "citation": "CERTIFICATE No. SCB-MD-2024-0457"},
            "titulaire": {"valeur": "Beijing Invented Medical", "citation": "Beijing Invented Medical Co."},
            "date_expiration": {"valeur": "11 March 2027", "citation": "Date of issue: 12 March 2024"},
            "classe_indiquee": {"valeur": None, "citation": None},
        }
        r = {c["nom"]: c for c in controler(reponse, CHAMPS, TEXTE)}
        self.assertEqual(r["numero"]["verification"], VERIFIE)
        self.assertEqual(r["titulaire"]["verification"], CITATION_INTROUVABLE)
        self.assertEqual(r["date_expiration"]["verification"], VALEUR_HORS_CITATION)
        self.assertEqual(r["date_expiration"]["valeur_normalisee"], "2027-03-11")
        self.assertEqual(r["classe_indiquee"]["verification"], ABSENT)


if __name__ == "__main__":
    unittest.main()
