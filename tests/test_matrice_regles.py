"""
Matrice des règles (scripts/ci_regles.py) : toutes les origines × classes ×
situations donnent la liste de pièces de référence, sans anomalie.
Changement voulu des règles : python scripts/ci_regles.py --mettre-a-jour.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ci_regles  # noqa: E402


class TestMatriceRegles(unittest.TestCase):
    def test_aucune_anomalie(self):
        self.assertEqual(ci_regles.anomalies(ci_regles.calculer()), [])

    def test_conforme_a_la_reference(self):
        reference = json.loads(ci_regles.REFERENCE.read_text(encoding="utf-8"))
        diff = ci_regles.differences(reference["matrice"], ci_regles.calculer())
        self.assertEqual(diff, [], "règles changées : python scripts/ci_regles.py --mettre-a-jour si c'est voulu")

    def test_toutes_les_combinaisons(self):
        self.assertEqual(len(ci_regles.calculer()), 7 * 7 * 5)


if __name__ == "__main__":
    unittest.main()
