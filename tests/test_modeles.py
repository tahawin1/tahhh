"""
Tests du repérage des modèles (dossiers acceptés) — sans Qdrant ni Mistral.
C'est le numéro de pièce dans le nom de fichier, rapproché des règles, qui
décide quel fichier est le modèle de quelle pièce.

    python -m unittest discover -s tests
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from modeles import fichiers_modeles, pieces_a_rediger_par_numero  # noqa: E402


class TestReperageDesModeles(unittest.TestCase):
    def test_table_des_numeros_vient_des_regles(self):
        self.assertEqual(pieces_a_rediger_par_numero(),
                         {1: "demande_signee", 2: "fiche_signaletique", 16: "certificat_enregistrement_annexe2"})

    def test_seules_les_pieces_a_rediger_sont_des_modeles(self):
        with tempfile.TemporaryDirectory() as d:
            racine = Path(d)
            dossier = racine / "union_europeenne" / "Ciment osseux" / "MODULES" / "1"
            dossier.mkdir(parents=True)
            for nom in ("1-1-Lettre de Demande.pdf", "2-2-fiche signalétique.pdf", "16-16-Certificat.pdf",
                        "4-4-EC_Certificate.pdf", "5-5-ISO13485.pdf", "Thumbs.db", "sans numero.pdf"):
                (dossier / nom).write_bytes(b"%PDF")
            trouves = {(m["numero"], m["piece_id"], m["pays_origine"], m["produit"]) for m in fichiers_modeles(racine)}
        self.assertEqual(trouves, {
            (1, "demande_signee", "union_europeenne", "Ciment osseux"),
            (2, "fiche_signaletique", "union_europeenne", "Ciment osseux"),
            (16, "certificat_enregistrement_annexe2", "union_europeenne", "Ciment osseux"),
        })  # certificats CE / ISO : émis par des tiers, jamais des modèles de rédaction


if __name__ == "__main__":
    unittest.main()


class TestRecadrageSurLeModele(unittest.TestCase):
    MODELE = """SOCIETE EXEMPLE SARL
Rabat, le 29/04/2026
A Monsieur le Directeur Général de l'AMMPS
Cachet et signature du représentant Légal de l'établissement
M. Représentant Exemple
ICE : 000000000000000-IF: 000 000 00-RC : 00000 Patente : 000 000 00 – BANQUE : RIB 000 00 000 000
000 000 000 00 00 Adresse: 1 rue de l'Exemple, immeuble Exemple, Quartier Exemple
RABAT / Tel : 05 00 00 00 00"""

    # sortie réelle de Mistral 7B (essai du 2026-10-01), abrégée
    SORTIE = """ Voici la lettre de demande d'enregistrement pour le dispositif médical Plaque d'ostéosynthèse en titane :

SOCIETE EXEMPLE SARL
Rabat, le [À COMPLÉTER]
A Monsieur le Directeur Général de l'AMMPS
Désignation scientifique : Plaque d'ostéosynthèse en titane
Cachet et signature du représentant Légal de l’établissement
M. Représentant Exemple

ICE : 000000000000000-IF: 000 000 00-RC : 00000 Patente : 000 000 00 – BANQUE : RIB 000 00 000 000 000 000 000 00 00 Adresse: 1 rue de l'Exemple, immeuble Exemple, Quartier Exemple RABAT / Tel : 05 00 00 00 00

Pour le dossier complet, veuillez trouver ci-dessous la liste des pièces :
- Certificat de transport
- Certificat de publicité"""

    def test_preambule_et_liste_inventee_retires(self):
        from generate import recadrer_sur_modele
        texte, retirees = recadrer_sur_modele(self.SORTIE, self.MODELE)
        self.assertTrue(texte.startswith("SOCIETE EXEMPLE SARL"))
        self.assertTrue(texte.endswith("Tel : 05 00 00 00 00"))
        self.assertNotIn("Certificat de transport", texte)
        self.assertEqual(retirees, 3)

    def test_sortie_conforme_inchangee(self):
        from generate import recadrer_sur_modele
        propre = self.SORTIE.split("Pour le dossier")[0].split(":\n\n", 1)[1].strip()
        texte, retirees = recadrer_sur_modele(propre, self.MODELE)
        self.assertEqual((texte, retirees), (propre, 0))

    def test_fin_du_modele_introuvable_rien_coupe(self):
        from generate import recadrer_sur_modele
        texte, retirees = recadrer_sur_modele("Lettre sans pied de page\nSignature", self.MODELE)
        self.assertEqual((texte, retirees), ("Lettre sans pied de page\nSignature", 0))
