"""
Scripts du pipeline Jenkins (scripts/ci_*.py, evaluer_mistral.py) : la partie
qui ne dépend ni de Mistral ni de Qdrant. Données fictives.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ci_rejouer_acceptes as rejeu  # noqa: E402
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

    def test_comparaison_des_valeurs(self):
        self.assertEqual(rejeu.proche("TECRES S.P.A.", "Tecres SpA"), "partiel")
        self.assertEqual(rejeu.proche("Chirurgie orthopédique", "Chirurgie Orthopedique"), "juste")
        self.assertEqual(rejeu.proche("Store below 25°C", "Conservé à l'abri de la chaleur"), "different")


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
