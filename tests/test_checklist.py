"""
Checklist de l'entreprise (rules/checklist_maroc.yaml) : transcription fidèle
et rapprochement avec les pièces des règles marocaines.

    python -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))

from rule_engine import charger_regles  # noqa: E402

CHECKLIST = yaml.safe_load((RACINE / "rules" / "checklist_maroc.yaml").read_text(encoding="utf-8"))


class TestChecklist(unittest.TestCase):
    def test_transcription_complete(self):
        docs = CHECKLIST["documents"]
        self.assertEqual(len(docs), 23)
        self.assertEqual(sum(len(d["elements"]) for d in docs), 197)
        self.assertEqual(CHECKLIST["statut"], "a_valider")  # aucun contrôle codé avant validation
        doc = next(d for d in docs if d["id"] == "declaration_de_conformite")
        self.assertIn("Doit contenir le code EMDN", [e["texte"] for e in doc["elements"]])

    def test_pieces_rattachees_existent(self):
        maroc = charger_regles("maroc")
        codes = {p["id"] for p in maroc["socle_commun"]} | {"piece_specifique"}
        for d in CHECKLIST["documents"]:
            if d["piece_maroc"]:
                self.assertIn(d["piece_maroc"], codes, d["id"])
            self.assertTrue(d["fondement"], d["id"])
            for e in d["elements"]:
                self.assertIn(e["controle"], ("lecture", "coherence", "humain"))

    def test_ecarts_avec_la_loi_signales(self):
        par_id = {d["id"]: d for d in CHECKLIST["documents"]}
        self.assertEqual(par_id["certificat_iso"]["rapprochement"], "valide_entreprise")  # loi : IIa, IIb, III ; entreprise : toutes
        self.assertEqual(par_id["free_sales_certificate_fsc"]["rapprochement"], "ecart_classes")  # en attente de réponse
        decisions = {d["id"]: d for d in CHECKLIST["decisions"]}
        self.assertTrue(decisions["iso_toutes_classes"]["reponse"])
        self.assertIsNone(decisions["quittance"]["reponse"])
        self.assertIn("I", par_id["certificat_iso"]["classes"])
        self.assertEqual(par_id["certificat_ce_mdd_mdr"]["classes"], ["IS", "IM", "IIA", "IIB", "III"])  # = la loi


if __name__ == "__main__":
    unittest.main()
