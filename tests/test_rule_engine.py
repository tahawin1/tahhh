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


class TestNatureDesPieces(unittest.TestCase):
    def test_certificats_et_pieces_tierces_jamais_a_rediger(self):
        for pays in ["chine", "inde", "union_europeenne", "autre"]:
            docs = {d.id: d for d in documents_requis_maroc(pays, classe="IIB")}
            for code in (f"piece_specifique_{pays}", "iso_13485", "bulletin_analyse", "echantillon_etiquetage"):
                self.assertEqual(docs[code].nature, "a_fournir", f"{code} ({pays})")
                self.assertTrue(docs[code].fourni_par, f"{code} : émetteur manquant")
            for code in ("demande_signee", "fiche_signaletique", "dossier_technique", "mandataire_maroc"):
                self.assertEqual(docs[code].nature, "a_rediger", code)
                self.assertTrue(docs[code].consigne_redaction, f"{code} : consigne de rédaction manquante")

    def test_champs_a_lire_dans_les_documents_recus(self):
        for pays in ["chine", "inde", "union_europeenne", "autre"]:
            docs = {d.id: d for d in documents_requis_maroc(pays, classe="IIB")}
            for code in (f"piece_specifique_{pays}", "iso_13485", "bulletin_analyse"):
                noms = [c["nom"] for c in docs[code].champs_a_extraire]
                self.assertTrue(noms, f"{code} ({pays}) : aucun champ à lire")
                self.assertEqual(len(noms), len(set(noms)))
            self.assertEqual(docs["echantillon_etiquetage"].champs_a_extraire, [])  # pièce physique
            certificat = {c["nom"]: c for c in docs[f"piece_specifique_{pays}"].champs_a_extraire}
            self.assertEqual(certificat["date_expiration"]["type"], "date")

    def test_nature_absente_refusee(self):
        import rule_engine

        original = rule_engine.charger_regles
        def regles_sans_nature(pays):
            regles = original(pays)
            del regles["socle_commun"][0]["nature"]
            return regles
        rule_engine.charger_regles = regles_sans_nature
        try:
            with self.assertRaisesRegex(ValueError, "nature"):
                documents_requis_maroc("chine", classe="IIB")
        finally:
            rule_engine.charger_regles = original


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
