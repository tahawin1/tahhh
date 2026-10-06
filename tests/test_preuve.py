"""
Détection de la preuve de mise sur le marché (pièce 4) par le code : textes
et noms de fichiers fictifs.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import preuve  # noqa: E402


class TestDetection(unittest.TestCase):
    def test_certificat_ce(self):
        self.assertEqual(preuve.detecter("EC Certificate — Notified Body 0123 — Directive 93/42/EEC"), "ce")
        self.assertEqual(preuve.detecter("", ["4-4- certificat de marquage CE.pdf"]), "ce")  # scan sans texte
        self.assertEqual(preuve.detecter("Notified Body Confirmation Letter, Regulation (EU) 2023/607"), "ce")

    def test_autorite_du_pays(self):
        self.assertEqual(preuve.detecter("CERTIFICATE FOR EXPORTATION OF MEDICAL PRODUCTS 京药监械出"), "nationale")
        self.assertEqual(preuve.detecter("", ["4-4- Free Sale.pdf"]), "nationale")
        # « MDR » indien (Medical Devices Rules) : ce n'est pas le règlement européen
        self.assertEqual(preuve.detecter("Licence under the Medical Devices Rules (MDR), 2017 — CDSCO"), "nationale")

    def test_rien_de_concluant(self):
        self.assertIsNone(preuve.detecter("Attestation", ["4-4-scan.pdf"]))


if __name__ == "__main__":
    unittest.main()
