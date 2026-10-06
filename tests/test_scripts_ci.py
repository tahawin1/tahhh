"""
Scripts du pipeline Jenkins (scripts/ci_*.py, evaluer_mistral.py) : la partie
qui ne dépend ni de Mistral ni de Qdrant. Données fictives.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ci_rejouer_acceptes as rejeu  # noqa: E402
import ci_rapport  # noqa: E402
import evaluer_mistral  # noqa: E402


class TestRejeu(unittest.TestCase):
    def test_classe_et_pieces_du_dossier_accepte(self):
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            a = racine / "chine" / "Gants d'examen (Is)" / "MODULES"
            a.mkdir(parents=True)
            for nom in ("1-1-Lettre.pdf", "4-4-NMPA.pdf", "4-4-FSC.pdf", "7-7-Label.pdf", "notes.txt"):
                (a / nom).write_bytes(b"%PDF")
            b = racine / "inde" / "Seringue"
            b.mkdir(parents=True)
            (b / "classe.txt").write_text("iib\n", encoding="utf-8")
            trouves = {d["dossier"]: d for d in rejeu.dossiers_acceptes(racine)}
        gants = trouves["Gants d'examen (Is)"]
        self.assertEqual((gants["classe"], gants["produit"], gants["pays"]), ("IS", "Gants d'examen", "chine"))
        self.assertEqual(sorted(gants["fichiers"]), [1, 4, 7])
        self.assertEqual(len(gants["fichiers"][4]), 2)  # NMPA + FSC : même pièce
        self.assertEqual(trouves["Seringue"]["classe"], "IIB")

    def test_dossiers_rejoues_a_tour_de_role(self):
        tous = [{"dossier": str(i)} for i in range(13)]
        vus = set()
        for build in range(1, 5):  # 4 builds de 4 dossiers : les 13 dossiers au moins une fois
            choix = rejeu.choisir(tous, 4, build)
            self.assertEqual(len(choix), 4)
            vus |= {d["dossier"] for d in choix}
        self.assertEqual(len(vus), 13)
        self.assertEqual(rejeu.choisir(tous, 0, 7), tous)  # 0 = tous

    def test_comparaison_des_valeurs(self):
        self.assertEqual(rejeu.proche("TECRES S.P.A.", "Tecres SpA"), "partiel")
        self.assertEqual(rejeu.proche("Chirurgie orthopédique", "Chirurgie Orthopedique"), "juste")
        self.assertEqual(rejeu.proche("Store below 25°C", "Conservé à l'abri de la chaleur"), "different")


class TestRapport(unittest.TestCase):
    def test_une_ligne_par_etape(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "tests-python.xml").write_text('<testsuite><testcase name="a"/><testcase name="b">'
                                                '<failure message="cassé"/></testcase></testsuite>', encoding="utf-8")
            (d / "regles.xml").write_text('<testsuite><testcase name="x"/></testsuite>', encoding="utf-8")
            page, resume = ci_rapport.construire(d, "rapide", "12")
        self.assertIn("Code ✗ 1/2 réussis", resume)
        self.assertIn("Lois → pièces ✓ 1/1", resume)
        self.assertIn("non exécutée (niveau rapide)", page)  # étapes IA : pas lancées en rapide
        self.assertIn("cassé", page)  # section « À corriger »
        self.assertNotIn("<style", page)  # Jenkins bloque le CSS des artefacts : HTML simple

    def test_etape_sans_rien_a_rejouer_pas_verte(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "dossiers-acceptes.xml").write_text('<testsuite><testcase name="x"><skipped message="aucun dossier '
                                                     'accepté"/></testcase></testsuite>', encoding="utf-8")
            page, resume = ci_rapport.construire(d, "complet", "9")
        self.assertIn("rien contrôlé — aucun dossier accepté", page)
        self.assertNotIn("Dossiers acceptés rejoués ✓", resume)

    def test_lecture_mistral_jugee_au_seuil(self):
        # 19/20 justes, une valeur manquée (signalée), aucune fausse acceptée : étape réussie
        detail = [{"specimen": "s.txt", "champ": f"c{i}", "verdict": "juste", "attendu": "a", "lu": "a",
                   "verification": "verifie", "erreur": None, "duree_s": 1} for i in range(19)]
        detail.append({"specimen": "s.txt", "champ": "date", "verdict": "manquee", "attendu": "2027-03-11",
                       "lu": None, "verification": "absent", "erreur": None, "duree_s": 1})
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            evaluer_mistral.junit(detail, d / "evaluation-mistral.xml")
            (d / "evaluation-mistral.json").write_text(json.dumps(
                {"modele": "m", "exactitude": 0.95, "seuil": 0.75, "justes": 19, "total": 20, "dangereuses": 0,
                 "detail": detail}), encoding="utf-8")
            page, resume = ci_rapport.construire(d, "complet", "8")
        self.assertIn("Lecture par Mistral ✓ 19/20 justes", resume)
        self.assertIn("2027-03-11", page)  # la valeur manquée reste visible
        self.assertNotIn("À corriger", page)


class TestEvaluationMistral(unittest.TestCase):
    def test_verdicts(self):
        juste = {"valeur": "SCB-MD-2024-0457", "verification": "verifie"}
        faux = {"valeur": "SCB-MD-2024-9999", "verification": "verifie"}
        prudent = {"valeur": "SCB-MD-2024-9999", "verification": "citation_introuvable"}
        self.assertEqual(evaluer_mistral.juger(juste, "SCB-MD-2024-0457"), "juste")
        self.assertEqual(evaluer_mistral.juger(faux, "SCB-MD-2024-0457"), "dangereuse")  # le code l'a acceptée
        self.assertEqual(evaluer_mistral.juger(prudent, "SCB-MD-2024-0457"), "manquee")  # signalée : pas dangereuse
        date = {"valeur": "11 March 2027", "valeur_normalisee": "2027-03-11", "type": "date", "verification": "verifie"}
        self.assertEqual(evaluer_mistral.juger(date, "2027-03-11"), "juste")

    def test_specimens_presents(self):
        for fichier, *_ in evaluer_mistral.SPECIMENS:
            self.assertTrue((evaluer_mistral.FIXTURES / fichier).exists(), fichier)


if __name__ == "__main__":
    unittest.main()
