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

    def test_classe_tiree_du_nom_du_dossier(self):
        with tempfile.TemporaryDirectory() as d:
            dossier = Path(d) / "chine" / "Seringue (IIb)"
            dossier.mkdir(parents=True)
            (dossier / "1-1-Lettre.pdf").write_bytes(b"%PDF")
            m = fichiers_modeles(Path(d))[0]
        self.assertEqual((m["produit"], m["classe"]), ("Seringue", "IIB"))

    def test_preuve_tiree_de_la_piece_4(self):
        # fabricant chinois accepté avec son certificat CE : rangé en Chine, preuve « ce »
        with tempfile.TemporaryDirectory() as d:
            dossier = Path(d) / "chine" / "Agrafeuse (IIa)"
            dossier.mkdir(parents=True)
            for nom in ("1-1-Lettre.pdf", "4-4- certificat de marquage CE.pdf"):
                (dossier / nom).write_bytes(b"%PDF")
            autre = Path(d) / "chine" / "Scie (IIa)"
            autre.mkdir(parents=True)
            for nom in ("1-1-Lettre.pdf", "4-4- Free Sale.pdf"):
                (autre / nom).write_bytes(b"%PDF")
            preuves = {m["produit"]: m["preuve"] for m in fichiers_modeles(Path(d))}
        self.assertEqual(preuves, {"Agrafeuse": "ce", "Scie": "nationale"})

    def test_modele_de_la_meme_classe_d_abord(self):
        from modeles import modele_pour

        class Point:
            def __init__(self, payload):
                self.payload, self.score = payload, 0.9

        class FauxClient:
            def __init__(self):
                self.filtres = []

            def collection_exists(self, _):
                return True

            def query_points(self, _c, query, query_filter, limit, with_payload):
                cles = {c.key: c.match.value for c in query_filter.must}
                self.filtres.append(cles)
                ok = cles.get("classe") in (None, "IIB") and cles.get("pays_origine") in (None, "chine")
                return type("R", (), {"points": [Point({"produit": "Seringue", **cles})] if ok else []})()

        class FauxEmbedder:
            def encoder_un(self, _):
                return [0.0]

        client = FauxClient()
        m = modele_pour("demande_signee", "chine", "Seringue 5 ml", client, FauxEmbedder(), classe="iib")
        self.assertEqual(client.filtres[0], {"piece_id": "demande_signee", "pays_origine": "chine", "classe": "IIB"})
        self.assertEqual(m["classe"], "IIB")
        # avec la preuve : même pays + même preuve + même classe d'abord
        client = FauxClient()
        modele_pour("demande_signee", "chine", "Seringue", client, FauxEmbedder(), classe="IIB", preuve="ce")
        self.assertEqual(client.filtres[0], {"piece_id": "demande_signee", "pays_origine": "chine", "preuve": "ce",
                                             "classe": "IIB"})


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

    def test_pied_de_page_absent_consignes_apres_la_signature_retirees(self):
        # essai réel : sans pied de page, Mistral a recopié ses consignes après la signature
        from generate import recadrer_sur_modele
        sortie = ("SOCIETE EXEMPLE SARL\nRabat, le 01/01/2026\nDésignation scientifique : Vis\n"
                  "Cachet et signature du représentant Légal de l’établissement\nM. Représentant Exemple\n"
                  "Ici, il est important de remplacer toutes les informations concernant l'ancien dispositif "
                  "par les données du nouveau dossier.\nLe document doit être écrit en français.")
        texte, retirees = recadrer_sur_modele(sortie, self.MODELE)
        self.assertTrue(texte.endswith("M. Représentant Exemple"))
        self.assertEqual(retirees, 2)
        # essai Jenkins : titre du prompt recopié juste après le pied de page
        texte, retirees = recadrer_sur_modele(self.SORTIE.split("Pour le dossier")[0] + "Consignes strictes :", self.MODELE)
        self.assertTrue(texte.endswith("Tel : 05 00 00 00 00"))
        self.assertEqual(retirees, 1)

    def test_date_du_jour_et_ville_du_profil(self):
        import datetime
        from generate import dater
        lettre = "SOCIETE EXEMPLE SARL\nCasablanca, le 29/04/2026\nA Monsieur le Directeur Général"
        self.assertEqual(dater(lettre, "Fès", datetime.date(2026, 10, 2)).splitlines()[1], "Fès, le 02/10/2026")
        self.assertEqual(dater(lettre, None, datetime.date(2026, 10, 2)).splitlines()[1], "Casablanca, le 02/10/2026")

    def test_profil_accents_repares_et_exemple_ignore(self):
        from generate import _reparer
        self.assertEqual(_reparer("repr├®sentant l├®gal"), "représentant légal")
        self.assertEqual(_reparer("reprÃ©sentant"), "représentant")
        self.assertEqual(_reparer("Fès"), "Fès")

    def test_profil_valeurs_d_exemple_ignorees(self):
        import shutil
        import tempfile
        from pathlib import Path
        from unittest import mock
        import generate
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(Path(__file__).resolve().parent.parent / "config" / "entreprise.exemple.yaml", tmp)
            profil = Path(tmp) / "entreprise.yaml"
            profil.write_text('raison_sociale: "SOCIETE EXEMPLE SARL"\nville: "Ville"\n'
                              'representant_legal: "Nom du repr├®sentant l├®gal"\n', encoding="utf-8")
            with mock.patch.object(generate, "PROFIL_ENTREPRISE", profil):
                self.assertEqual(generate.profil_entreprise(), {"raison_sociale": "SOCIETE EXEMPLE SARL"})

    def test_fin_du_modele_introuvable_rien_coupe(self):
        from generate import recadrer_sur_modele
        texte, retirees = recadrer_sur_modele("Lettre sans pied de page\nSignature", self.MODELE)
        self.assertEqual((texte, retirees), ("Lettre sans pied de page\nSignature", 0))
