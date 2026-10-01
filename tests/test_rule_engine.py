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
    "demande_signee", "fiche_signaletique", "attestation_fabricant", "declaration_conformite",
    "etiquetage", "notice", "echantillon", "catalogue", "certificat_enregistrement_annexe2",
    "quittance_droits",
]
A_REDIGER = ("demande_signee", "fiche_signaletique", "certificat_enregistrement_annexe2")


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
            piece = {d.id: d for d in documents_requis_maroc(pays, classe="IIB")}[f"piece_specifique_{pays}"]
            self.assertEqual(piece.numero, 4)
            self.assertIn(mot_cle, piece.nom)
            self.assertEqual(piece.traduction_requise, traduction, pays)
            self.assertEqual(piece.legalisation_requise, legalisation, pays)

    def test_origine_non_listee_retombe_sur_autre(self):
        piece = {d.id: d for d in documents_requis_maroc("japon", classe="IIB")}["piece_specifique_japon"]
        self.assertIn("libre vente", piece.nom)
        self.assertTrue(piece.traduction_requise)


class TestDossierReelAccepte(unittest.TestCase):
    """Dossier réel accepté par l'AMMPS (UE, classe IIb) : pièces 1 à 9, 14, 16."""

    def test_liste_et_ordre_du_dossier_accepte_ue_iib(self):
        docs = documents_requis_maroc("union_europeenne", classe="IIB")
        numerotees = [(d.numero, d.id) for d in docs if d.numero is not None]
        self.assertEqual(numerotees, [
            (1, "demande_signee"), (2, "fiche_signaletique"), (3, "attestation_fabricant"),
            (4, "piece_specifique_union_europeenne"), (5, "iso_13485"), (6, "declaration_conformite"),
            (7, "etiquetage"), (8, "notice"), (9, "echantillon"), (14, "catalogue"),
            (16, "certificat_enregistrement_annexe2"),
        ])
        self.assertEqual([d.id for d in docs if d.numero is None], ["quittance_droits"])  # arrêté 2855-15

    def test_pieces_retirees_en_v2(self):
        for pays in ["chine", "inde", "union_europeenne", "autre"]:
            for retiree in ("bulletin_analyse", "dossier_technique", "mandataire_maroc"):
                self.assertNotIn(retiree, ids(pays, "IIB"))

    def test_certificat_ce_selon_classe(self):
        # arrêté 2855-15 : IIA, IIB, III et sous-classes Is, Im ; pas la classe I simple
        self.assertNotIn("piece_specifique_union_europeenne", ids("union_europeenne", "I"))
        for classe in ("IS", "IM", "IR", "IIA", "IIB", "III", None):
            self.assertIn("piece_specifique_union_europeenne", ids("union_europeenne", classe))
        self.assertNotIn("iso_13485", ids("union_europeenne", "IS"))
        self.assertNotIn("iso_13485", ids("union_europeenne", "IR"))  # classe I réutilisable : comme Is/Im

    def test_lettre_de_confirmation_2023_607_signalee(self):
        ce = {d.id: d for d in documents_requis_maroc("union_europeenne", "IIB")}["piece_specifique_union_europeenne"]
        self.assertIn("2023/607", ce.remarque)

    def test_autorite_ammps(self):
        from rule_engine import charger_regles
        regles = charger_regles("maroc")
        self.assertIn("AMMPS", regles["autorite"])
        self.assertIn("Directeur Général", regles["destinataire_demande"])
        self.assertEqual(regles["version"], 2.2)


class TestNatureDesPieces(unittest.TestCase):
    def test_certificats_et_pieces_tierces_jamais_a_rediger(self):
        for pays in ["chine", "inde", "union_europeenne", "autre"]:
            docs = {d.id: d for d in documents_requis_maroc(pays, classe="IIB")}
            for code, doc in docs.items():
                if code not in A_REDIGER:
                    self.assertEqual(doc.nature, "a_fournir", f"{code} ({pays})")
                    self.assertTrue(doc.fourni_par, f"{code} : émetteur manquant")
            for code in A_REDIGER:
                self.assertEqual(docs[code].nature, "a_rediger", code)
                self.assertTrue(docs[code].consigne_redaction, f"{code} : consigne de rédaction manquante")

    def test_champs_a_lire_dans_les_documents_recus(self):
        for pays in ["chine", "inde", "union_europeenne", "autre"]:
            docs = {d.id: d for d in documents_requis_maroc(pays, classe="IIB")}
            for code in (f"piece_specifique_{pays}", "iso_13485", "attestation_fabricant", "declaration_conformite"):
                noms = [c["nom"] for c in docs[code].champs_a_extraire]
                self.assertTrue(noms, f"{code} ({pays}) : aucun champ à lire")
                self.assertEqual(len(noms), len(set(noms)))
            self.assertEqual(docs["echantillon"].champs_a_extraire, [])  # pièce physique
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
