"""
Tests du moteur de règles (déterministe, sans infrastructure).

    python -m unittest discover -s tests
"""
import datetime
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rule_engine import documents_requis_maroc, prochain_creneau_depot  # noqa: E402

SOCLE = [
    "demande_signee", "fiche_signaletique", "dossier_technique", "bulletin_analyse",
    "echantillon_etiquetage", "mandataire_maroc",
]


def ids(pays, classe=None):
    return [d.id for d in documents_requis_maroc(pays, classe=classe)]


class TestDocumentsRequisMaroc(unittest.TestCase):
    def test_socle_commun_present_pour_toutes_origines(self):
        for pays in ["chine", "inde", "union_europeenne", "autre"]:
            for doc in SOCLE:
                self.assertIn(doc, ids(pays, "IIB"), f"{doc} manquant pour {pays}")

    def test_iso_13485_selon_classe(self):
        self.assertNotIn("iso_13485", ids("chine", "I"))
        for classe in ["IIA", "IIB", "III"]:
            self.assertIn("iso_13485", ids("chine", classe))

    def test_iso_13485_conserve_si_classe_inconnue(self):
        self.assertIn("iso_13485", ids("chine", None))

    def test_piece_specifique_et_flags(self):
        attendu = {
            "chine": ("NMPA", True, True),
            "inde": ("CDSCO", True, True),
            "union_europeenne": ("marquage CE", False, False),
            "autre": ("libre vente", True, True),
        }
        for pays, (mot_cle, traduction, legalisation) in attendu.items():
            piece = documents_requis_maroc(pays, classe="IIB")[-1]
            self.assertEqual(piece.id, f"piece_specifique_{pays}")
            self.assertIn(mot_cle, piece.nom)
            self.assertEqual(piece.traduction_requise, traduction, pays)
            self.assertEqual(piece.legalisation_requise, legalisation, pays)

    def test_origine_non_listee_retombe_sur_autre(self):
        piece = documents_requis_maroc("japon", classe="IIB")[-1]
        self.assertIn("libre vente", piece.nom)
        self.assertTrue(piece.traduction_requise)


class TestCreneauDepot(unittest.TestCase):
    def test_mercredi_ou_jeudi_uniquement(self):
        lundi = datetime.date(2026, 9, 28)
        for i in range(14):
            jour = prochain_creneau_depot(depuis=lundi + datetime.timedelta(days=i))
            self.assertIn(jour.weekday(), (2, 3))

    def test_depuis_vendredi_donne_mercredi_suivant(self):
        self.assertEqual(prochain_creneau_depot(depuis=datetime.date(2026, 10, 2)), datetime.date(2026, 10, 7))


if __name__ == "__main__":
    unittest.main()
