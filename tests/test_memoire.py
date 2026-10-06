"""
Mémoire des dossiers acceptés (src/memoire.py) — sans Mistral : réponse
simulée au format réel ; données fictives uniquement (dépôt public).

    python -m unittest discover -s tests
"""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as N
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pymupdf  # noqa: E402

import formulaires  # noqa: E402
import memoire  # noqa: E402
from rule_engine import documents_requis_maroc  # noqa: E402

FICHE = """FICHE SIGNALETIQUE
Domaine thérapeutique Chirurgie orthopédique
Présentation(s) Boîte contenant un sachet de poudre et un flacon de liquide
Durée de validité (si applicable) 3 ans
Coordonnées de l'établissement de fabrication Nom: EXEMPLE MEDICAL S.P.A.
Adresse : Via Esempio 1, 00100 Roma, Italia
Annexe Nom de marque Noms commerciaux Référence
EXEMPLE OSTEO RX 1100/A
EXEMPLE OSTEO FAST 11A2000
"""

REPONSE = {  # ce que Mistral répondrait (une valeur inventée, une reformatée)
    "domaine_therapeutique": {"valeur": "Chirurgie orthopédique", "citation": "Domaine thérapeutique Chirurgie orthopédique"},
    "presentation": {"valeur": "Boîte contenant un sachet de poudre et un flacon de liquide",
                     "citation": "Présentation(s) Boîte contenant un sachet de poudre et un flacon de liquide"},
    "duree_validite": {"valeur": "5 ans", "citation": "Durée de validité 5 ans"},  # inventée : rejetée
    "fabricant_nom": {"valeur": "EXEMPLE MEDICAL S.P.A.", "citation": "Nom: EXEMPLE MEDICAL S.P.A."},
    "references": {"valeur": "EXEMPLE | OSTEO RX | 1100/A\nEXEMPLE | OSTEO FAST | 11A2000", "citation": None},
}


def pdf(chemin: Path, texte: str) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((40, 60), texte, fontsize=9)
    doc.save(chemin)


class TestMemoire(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        racine = Path(self.tmp.name)
        self.acceptes = racine / "dossiers_valides"
        produit = self.acceptes / "union_europeenne" / "Ciment exemple (IIb)"  # classe dans le nom : retirée
        produit.mkdir(parents=True)
        pdf(produit / "2-2-fiche signaletique.pdf", FICHE)
        (produit / "1-1-Lettre.pdf").write_bytes(b"")  # la lettre n'est pas lue par la mémoire
        self.patch = mock.patch.object(memoire, "DOSSIER_MEMOIRE", racine / "memoire")
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def apprendre(self):
        with mock.patch("extraction.interroger_mistral", return_value=REPONSE):
            return memoire.apprendre(self.acceptes)

    def test_seules_les_valeurs_retrouvees_dans_le_formulaire_accepte_sont_apprises(self):
        (entree,) = self.apprendre()
        self.assertEqual(entree["fabricant"], "EXEMPLE MEDICAL S.P.A.")
        self.assertIn("domaine_therapeutique", entree["valeurs"])
        self.assertIn("references", entree["valeurs"])  # chaque cellule figure dans le document
        self.assertNotIn("duree_validite", entree["valeurs"])  # « 5 ans » n'est pas dans le document
        self.assertEqual(entree["valeurs"]["presentation"]["piece"], 2)

    def test_reponse_coupee_relue_par_moities(self):
        # Mistral rend un JSON coupé quand on lui demande trop de champs d'un coup :
        # relu par moitiés, le dossier est quand même appris
        from extraction import ExtractionImpossible

        def repondre(texte, champs, piece):
            if len(champs) > 5:
                raise ExtractionImpossible("Réponse de Mistral illisible (JSON invalide).")
            return {k: v for k, v in REPONSE.items() if k in {c["nom"] for c in champs}}

        with mock.patch("extraction.interroger_mistral", side_effect=repondre):
            (entree,) = memoire.apprendre(self.acceptes)
        self.assertEqual(entree["fabricant"], "EXEMPLE MEDICAL S.P.A.")
        self.assertIn("references", entree["valeurs"])

    def test_champ_illisible_seul_abandonne(self):
        # les références (longue liste) font échouer Mistral : le fabricant est quand même appris
        from extraction import ExtractionImpossible

        def repondre(texte, champs, piece):
            if any(c["nom"] == "references" for c in champs):
                raise ExtractionImpossible("Réponse de Mistral illisible (JSON invalide).")
            return {k: v for k, v in REPONSE.items() if k in {c["nom"] for c in champs}}

        with mock.patch("extraction.interroger_mistral", side_effect=repondre):
            (entree,) = memoire.apprendre(self.acceptes)
        self.assertEqual(entree["fabricant"], "EXEMPLE MEDICAL S.P.A.")
        self.assertNotIn("references", entree["valeurs"])

    def test_incremental_dossier_inchange_non_relu(self):
        with mock.patch("extraction.interroger_mistral", return_value=REPONSE) as mistral:
            memoire.apprendre(self.acceptes)
            appels = mistral.call_count
            (entree,) = memoire.apprendre(self.acceptes)  # rien n'a changé : pas un appel de plus
            self.assertEqual(mistral.call_count, appels)
            self.assertEqual(entree["fabricant"], "EXEMPLE MEDICAL S.P.A.")
            memoire.apprendre(self.acceptes, forcer=True)
            self.assertGreater(mistral.call_count, appels)

    def test_memoire_anterieure_adoptee_sans_relecture(self):
        # mémoire écrite par une version précédente (sans empreinte), après les formulaires : gardée
        import json
        with mock.patch("extraction.interroger_mistral", return_value=REPONSE):
            memoire.apprendre(self.acceptes)
        fichier = memoire.fichier_memoire("union_europeenne", "Ciment exemple")
        entree = json.loads(fichier.read_text(encoding="utf-8"))
        del entree["empreinte"]
        fichier.write_text(json.dumps(entree), encoding="utf-8")
        with mock.patch("extraction.interroger_mistral", return_value=REPONSE) as mistral:
            memoire.apprendre(self.acceptes)
        self.assertEqual(mistral.call_count, 0)
        self.assertIn("empreinte", json.loads(fichier.read_text(encoding="utf-8")))

    def test_dossier_deplace_memoire_nettoyee(self):
        with mock.patch("extraction.interroger_mistral", return_value=REPONSE):
            memoire.apprendre(self.acceptes)
            ancien = memoire.fichier_memoire("union_europeenne", "Ciment exemple")
            self.assertTrue(ancien.exists())
            (self.acceptes / "chine").mkdir()
            (self.acceptes / "union_europeenne" / "Ciment exemple (IIb)").rename(
                self.acceptes / "chine" / "Ciment exemple (IIb)")
            (entree,) = memoire.apprendre(self.acceptes)
        self.assertEqual(entree["pays"], "chine")
        self.assertFalse(ancien.exists())

    def dossier(self, fabricant):
        lectures = {"declaration_conformite": [{"nom": "fabricant", "valeur": fabricant, "valeur_normalisee": fabricant,
                                                "verification": "verifie"}]}
        docs = [N(code=d.id, numero=d.numero, nom=d.nom, extraction_statut="terminee" if d.id in lectures else None,
                  extraction={"champs": lectures[d.id]} if d.id in lectures else None)
                for d in documents_requis_maroc("union_europeenne", "IIB")]
        return N(produit="Ciment exemple 2", classe="IIB", pays_origine="union_europeenne", documents=docs,
                 donnees_dispositif={"presentation": "Saisie à la main"})

    def test_reprise_pour_le_meme_fabricant_uniquement(self):
        self.apprendre()
        r = formulaires.resoudre(self.dossier("Exemple Medical SpA"), {})
        self.assertEqual(r["domaine_therapeutique"]["valeur"], "Chirurgie orthopédique")
        self.assertEqual(r["domaine_therapeutique"]["provenance"], "memoire")
        self.assertTrue(r["domaine_therapeutique"]["a_verifier"])
        self.assertIn("Ciment exemple", r["domaine_therapeutique"]["detail"])
        self.assertEqual(r["presentation"]["valeur"], "Saisie à la main")  # la saisie prime
        self.assertIn("OSTEO FAST | 11A2000", r["references"]["valeur"])
        autre = formulaires.resoudre(self.dossier("Autre Fabricant Ltd"), {})
        self.assertIsNone(autre["domaine_therapeutique"]["valeur"])  # jamais les données d'un autre fabricant


if __name__ == "__main__":
    unittest.main()
