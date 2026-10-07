"""Ordre de lecture des documents reçus (taches.ORDRE_LECTURE)."""
from __future__ import annotations

import heapq
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import taches  # noqa: E402


class TestOrdreLecture(unittest.TestCase):
    def test_pieces_utiles_aux_formulaires_lues_d_abord(self):
        codes = ["iso_13485", "notice", "attestation_fabricant", "etiquetage", "piece_specifique_inde",
                 "declaration_conformite", "catalogue"]
        self.assertEqual(sorted(codes, key=taches.rang_lecture),
                         ["piece_specifique_inde", "etiquetage", "notice", "catalogue", "declaration_conformite",
                          "attestation_fabricant", "iso_13485"])

    def test_une_soumission_une_lecture_la_plus_utile(self):
        lues, vraie = [], taches.executer_extraction
        taches.executer_extraction = lues.append
        try:
            for numero, (code, ident) in enumerate([("iso_13485", 1), ("notice", 2), ("iso_13485", 3), ("etiquetage", 4)]):
                heapq.heappush(taches._lectures_en_attente, (taches.rang_lecture(code), numero, ident))
            for _ in range(5):  # une soumission de trop : rien à lire, sans erreur
                taches._lecture_suivante()
        finally:
            taches.executer_extraction = vraie
        self.assertEqual(lues, [4, 2, 1, 3])  # étiquettes, notice, puis les autres dans l'ordre d'arrivée


if __name__ == "__main__":
    unittest.main()
