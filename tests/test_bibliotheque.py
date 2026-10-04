"""
Pièces fournies par l'agent depuis les DOSSIERS ACCEPTÉS (src/bibliotheque.py,
rules/bibliotheque.yaml) — dossier accepté fictif sur disque, mémoire fictive.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as N
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pymupdf  # noqa: E402

import bibliotheque  # noqa: E402
import memoire  # noqa: E402
from rule_engine import documents_requis_maroc  # noqa: E402


def pdf(chemin: Path, texte: str):
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 60), texte)
    doc.save(chemin)


def dossier(produit, fournisseur, sortie, pays="union_europeenne"):
    pieces = [N(id=i, code=d.id, numero=d.numero, nom=d.nom, nature=d.nature, statut="a_obtenir", fichier_recu=None,
                extraction=None, extraction_statut=None, texte_recu=None, champs_a_extraire=d.champs_a_extraire,
                nom_fichier_recu=None, origine_recu=None, recu_le=None, extraction_erreur=None)
              for i, d in enumerate(documents_requis_maroc(pays, "IIB"))]
    return N(id=99, produit=produit, fournisseur=fournisseur, pays_origine=pays, documents=pieces, dossier_sortie=str(sortie))


class TestDossiersAcceptes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        racine = Path(self.tmp.name)
        self.acceptes = racine / "dossiers_valides"
        produit = self.acceptes / "union_europeenne" / "Ciment exemple (IIb)" / "MODULES"
        produit.mkdir(parents=True)
        for nom in ("1-1-Lettre.pdf", "3-3-Authorization.pdf", "4-4-EC certificate.pdf", "5-5-ISO13485.pdf",
                    "6-6-DoC.pdf", "7-7-Label RX.pdf", "7-7-Label Fast.pdf", "8-8-IFU.pdf", "14-14-Catalogue.pdf"):
            pdf(produit / nom, f"SPECIMEN {nom}")
        (racine / "memoire").mkdir()
        (racine / "memoire" / "ue.json").write_text(json.dumps({
            "pays": "union_europeenne", "produit": "Ciment exemple (IIb)", "fabricant": "EXEMPLE MEDICAL S.P.A.",
            "valeurs": {}}), encoding="utf-8")
        self.patchs = [mock.patch.object(memoire, "DOSSIER_MEMOIRE", racine / "memoire"),
                       mock.patch.object(memoire, "RACINE_DEFAUT", self.acceptes)]
        for p in self.patchs:
            p.start()
        self.sortie = racine / "sortie"

    def tearDown(self):
        for p in self.patchs:
            p.stop()
        self.tmp.cleanup()

    def test_meme_produit_tout_sauf_les_certificats(self):
        d = dossier("Ciment exemple", "Exemple Medical", self.sortie)
        faits = {p.code: (p, t, relire) for p, t, relire in bibliotheque.reprendre(d, [])}
        self.assertEqual(set(faits), {"attestation_fabricant", "declaration_conformite", "etiquetage", "notice", "catalogue"})
        etiquettes, trouve, relire = faits["etiquetage"]
        self.assertTrue(relire)  # document jamais lu dans l'outil : Mistral le lit
        self.assertEqual(etiquettes.extraction_statut, "en_file")
        self.assertEqual(len(pymupdf.open(etiquettes.fichier_recu)), 2)  # deux étiquettes réunies en un PDF
        self.assertIn("Ciment exemple (IIb)", etiquettes.origine_recu)
        codes_vides = {p.code for p in d.documents if not p.fichier_recu}
        self.assertIn("iso_13485", codes_vides)  # certificats : toujours du fournisseur
        self.assertIn("piece_specifique_union_europeenne", codes_vides)

    def test_autre_produit_pieces_du_fabricant_seulement(self):
        d = dossier("Vis pédiculaire", "EXEMPLE MEDICAL", self.sortie)
        self.assertEqual({p.code for p, *_ in bibliotheque.reprendre(d, [])}, {"attestation_fabricant", "catalogue"})

    def test_autre_fabricant_ou_autre_pays_rien(self):
        self.assertEqual(bibliotheque.reprendre(dossier("Ciment exemple", "Autre SA", self.sortie), []), [])
        self.assertEqual(bibliotheque.reprendre(dossier("Ciment exemple", "Exemple Medical", self.sortie, "chine"), []), [])

    def test_politique(self):
        self.assertIsNone(bibliotheque.portee("iso_13485"))
        self.assertIsNone(bibliotheque.portee("piece_specifique_chine"))
        self.assertEqual(bibliotheque.portee("notice"), "meme_produit")
        self.assertEqual(bibliotheque.portee("attestation_fabricant"), "meme_fabricant")
        self.assertTrue(bibliotheque.meme_produit("Ciment osseux (IIb)", "ciment osseux"))
        self.assertFalse(bibliotheque.meme_produit("Ciment osseux", "Vis pédiculaire"))


if __name__ == "__main__":
    unittest.main()
