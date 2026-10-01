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

    def test_iso_13485_toutes_classes(self):
        # règles 2.4 : décision de l'entreprise (checklist), plus exigeante que l'arrêté 2855-15
        for classe in ["I", "IS", "IM", "IR", "IIA", "IIB", "III"]:
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


class TestConditionsChecklist(unittest.TestCase):
    """Règles 2.4 : décisions de l'entreprise sur sa checklist."""

    def test_echantillon_ou_proforma_selon_la_valeur(self):
        moins = [d.id for d in documents_requis_maroc("union_europeenne", "IIB", valeur_usd=499)]
        plus = [d.id for d in documents_requis_maroc("union_europeenne", "IIB", valeur_usd=500)]
        self.assertIn("echantillon_modele_vente", moins)
        self.assertNotIn("facture_proforma", moins)
        self.assertIn("facture_proforma", plus)
        self.assertNotIn("echantillon_modele_vente", plus)
        self.assertIn("echantillon", plus)  # les photos restent demandées

    def test_equipement(self):
        equipement = [d.id for d in documents_requis_maroc("chine", "IIA", equipement=True, valeur_usd=100)]
        for code in ("note_descriptive", "documentation_technique", "manuel_utilisation"):
            self.assertIn(code, equipement)
            self.assertNotIn(code, ids("chine", "IIA"))
        self.assertNotIn("echantillon_modele_vente", equipement)  # arrêté 2855-15 : sauf équipement médical
        note = next(d for d in documents_requis_maroc("chine", "IIA", equipement=True) if d.id == "note_descriptive")
        self.assertTrue(note.a_rediger and note.consigne_redaction)


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
        # sans numéro : échantillon (valeur non saisie -> retenu par défaut) et quittance (arrêté 2855-15)
        self.assertEqual([d.id for d in docs if d.numero is None],
                         ["echantillon_modele_vente", "declaration_etablissement", "quittance_droits"])
        self.assertIn("Valeur unitaire du produit non saisie", next(d for d in docs if d.id == "echantillon_modele_vente").remarque)

    def test_pieces_retirees_en_v2(self):
        for pays in ["chine", "inde", "union_europeenne", "autre"]:
            for retiree in ("bulletin_analyse", "dossier_technique", "mandataire_maroc"):
                self.assertNotIn(retiree, ids(pays, "IIB"))

    def test_certificat_ce_selon_classe(self):
        # arrêté 2855-15 : IIA, IIB, III et sous-classes Is, Im ; pas la classe I simple
        self.assertNotIn("piece_specifique_union_europeenne", ids("union_europeenne", "I"))
        for classe in ("IS", "IM", "IR", "IIA", "IIB", "III", None):
            self.assertIn("piece_specifique_union_europeenne", ids("union_europeenne", classe))
        self.assertIn("iso_13485", ids("union_europeenne", "IR"))  # règles 2.4 : ISO pour toutes les classes

    def test_lettre_de_confirmation_2023_607_signalee(self):
        ce = {d.id: d for d in documents_requis_maroc("union_europeenne", "IIB")}["piece_specifique_union_europeenne"]
        self.assertIn("2023/607", ce.remarque)

    def test_autorite_ammps(self):
        from rule_engine import charger_regles
        regles = charger_regles("maroc")
        self.assertIn("AMMPS", regles["autorite"])
        self.assertIn("Directeur Général", regles["destinataire_demande"])
        self.assertEqual(regles["version"], 2.5)


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


class TestReponsesTirees(unittest.TestCase):
    """Règles 2.5 : points de la checklist tranchés d'après les textes."""

    def test_libre_vente(self):
        ue_i = ids("union_europeenne", "I")
        self.assertIn("certificat_libre_vente_ue", ue_i)  # MDR art. 60 : classe I sans organisme notifié
        self.assertNotIn("piece_specifique_union_europeenne", ue_i)
        self.assertNotIn("certificat_libre_vente_ue", ids("union_europeenne", "IIB"))  # le certificat CE suffit
        for pays in ("chine", "inde", "etats_unis", "coree_du_sud", "pakistan", "autre"):
            self.assertIn(f"piece_specifique_{pays}", ids(pays, "I"))

    def test_classe_iii_ue_et_donnees_cliniques(self):
        self.assertIn("certificat_evaluation_classe_iii", ids("union_europeenne", "III"))
        self.assertNotIn("certificat_evaluation_classe_iii", ids("union_europeenne", "IIB"))
        self.assertNotIn("evaluation_clinique", ids("union_europeenne", "III"))  # couvert par le certificat CE
        self.assertIn("evaluation_clinique", ids("chine", "IIB"))
        self.assertNotIn("evaluation_clinique", ids("chine", "IIA"))

    def test_lettre_de_lien_declaration_quittance(self):
        self.assertNotIn("lettre_de_lien", ids("inde", "IIA"))
        self.assertIn("lettre_de_lien", [d.id for d in documents_requis_maroc("inde", "IIA", distributeur=True)])
        for pays in ("chine", "union_europeenne"):
            self.assertIn("declaration_etablissement", ids(pays, "I"))
            self.assertIn("quittance_droits", ids(pays, "I"))
