"""
Nouvelles origines (États-Unis, Corée du Sud, Pakistan) et rapprochement des
sept réglementations (rules/correspondances.yaml).

    python -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import classement  # noqa: E402
import correspondances  # noqa: E402
from rule_engine import charger_regles, documents_requis_maroc  # noqa: E402

NOUVEAUX = ("etats_unis", "coree_du_sud", "pakistan")


class TestNouvellesOrigines(unittest.TestCase):
    def test_piece_4_propre_au_pays(self):
        attendus = {"etats_unis": "Certificate to Foreign Government", "coree_du_sud": "MFDS", "pakistan": "DRAP"}
        for pays, mot in attendus.items():
            docs = {d.id: d for d in documents_requis_maroc(pays, "IIB")}
            piece = docs[f"piece_specifique_{pays}"]
            self.assertEqual(piece.numero, 4)
            self.assertIn(mot, piece.nom)
            self.assertTrue(piece.traduction_requise and piece.legalisation_requise)
            self.assertIn("2855-15", piece.source)
            self.assertTrue(piece.champs_a_extraire)
            self.assertIn("iso_13485", docs)
        self.assertIn("piece_specifique_pakistan", [d.id for d in documents_requis_maroc("pakistan", "I")])  # 2.5 : FSC toutes classes

    def test_regles_des_pays_provisoires_signalees(self):
        attendus = {"etats_unis": "partiel", "coree_du_sud": "partiel", "pakistan": "provisoire"}
        for pays in NOUVEAUX:
            regles = charger_regles(pays)
            self.assertEqual(regles["statut"], attendus[pays])
            self.assertTrue(regles["autorite"] and regles["classification"])

    def test_certificat_americain_range_en_piece_4(self):
        from types import SimpleNamespace as N
        pieces = [N(code=d.id, numero=d.numero, nom=d.nom) for d in documents_requis_maroc("etats_unis", "IIB")
                  if d.nature == "a_fournir"]
        for nom in ("CFG Certificate to Foreign Government.pdf", "K123456 510k clearance.pdf"):
            p, _ = classement.classer(nom, pieces)
            self.assertEqual(p.numero if p else None, 4, nom)


class TestCorrespondances(unittest.TestCase):
    def test_sept_pays_et_quatre_niveaux(self):
        t = correspondances.tableau()
        self.assertEqual([n["id"] for n in t["niveaux"]], ["A", "B", "C", "D"])
        self.assertEqual({p["id"] for p in t["pays"]},
                         {"maroc", "union_europeenne", "chine", "inde", "etats_unis", "coree_du_sud", "pakistan"})
        for p in t["pays"]:
            self.assertEqual(set(p["classes"]), {"A", "B", "C", "D"}, p["id"])
            self.assertIn(p["statut"], ("verifie", "partiel", "provisoire"))
        statuts = {p["id"]: p["statut"] for p in t["pays"]}
        self.assertEqual(statuts["pakistan"], "provisoire")  # texte DRAP pas encore indexé
        self.assertEqual(statuts["coree_du_sud"], "partiel")

    def test_classes_marocaines_toutes_placees(self):
        placees = {c for classes in correspondances.charger()["pays"]["maroc"]["classes"].values() for c in classes}
        self.assertEqual(placees, set(charger_regles("maroc")["classification"]))

    def test_equivalents(self):
        eq = correspondances.equivalents("coree_du_sud", "II")
        self.assertEqual(eq["maroc"], ["IIA"])
        self.assertEqual(eq["inde"], ["B"])
        eq = correspondances.equivalents("maroc", "IIB")
        self.assertEqual(eq["etats_unis"], ["II", "III"])  # trois classes américaines : correspondance approximative
        self.assertEqual(eq["coree_du_sud"], ["III"])
        self.assertEqual(correspondances.equivalents("coree_du_sud", "IV")["maroc"], ["III"])


if __name__ == "__main__":
    unittest.main()


class FauxGenerateur:
    """RAG et Mistral factices : un extrait par pays, réponse JSON imposée."""
    def __init__(self, reponse):
        self.reponse = reponse

    def rechercher_references(self, pays, question, k=2):
        if pays != "maroc":
            return []
        return [{"texte_source": "Arrêtés 2853/2854/2855/2856-15", "date_version": "2015-08-04", "fichier": "x.pdf",
                 "chunk_index": 3, "score": 0.9,
                 "texte": "le certificat de marquage CE, ou l'attestation FDA, ou l'autorisation de mise en vente"}]

    def interroger_json(self, prompt, schema):
        return self.reponse


class TestRapprochementArticles(unittest.TestCase):
    def test_chaque_theme_cite_les_sept_pays(self):
        pays = set(correspondances.charger()["pays"])
        for theme in correspondances.charger()["themes"]:
            self.assertEqual(set(theme["articles"]), pays, theme["id"])
        self.assertIn("attestation FDA", next(t for t in correspondances.charger()["themes"]
                                              if t["id"] == "preuve_pays_origine")["articles"]["maroc"])

    def test_fiche_pays_pour_mistral(self):
        fiche = correspondances.fiche_pays("coree_du_sud", "IIB")
        self.assertIn("MFDS", fiche)
        self.assertIn("≈ classe(s) III", fiche)
        self.assertIn("arrêté 2855-15", fiche)
        self.assertIn("Établissement importateur", correspondances.fiche_pays("autre"))

    def test_synthese_citation_verifiee_par_le_code(self):
        bon = '{"resume": "Le Maroc accepte le marquage CE ou l\'attestation FDA.", "citation": "le certificat de marquage CE, ou l\'attestation FDA"}'
        r = correspondances.synthese("preuve_pays_origine", FauxGenerateur(bon))["pays"]
        self.assertTrue(r["maroc"]["verifiee"])
        self.assertIsNone(r["inde"]["resume"])  # aucun extrait : pas de réponse inventée
        invente = '{"resume": "x", "citation": "le Maroc exige un essai clinique local"}'
        r = correspondances.synthese("preuve_pays_origine", FauxGenerateur(invente))["pays"]
        self.assertFalse(r["maroc"]["verifiee"])
