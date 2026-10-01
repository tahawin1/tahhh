"""
Formulaires remplis par le code (fiche signalétique, annexe II), données du
dispositif et dépôt groupé des documents du fournisseur — sans Mistral.

    python -m unittest discover -s tests
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as N

TMP = Path(tempfile.mkdtemp(prefix="conformite-formulaires-"))
os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{TMP / 'test.db'}")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pymupdf  # noqa: E402
from docx import Document as Docx  # noqa: E402

import classement  # noqa: E402
import formulaires  # noqa: E402
from rule_engine import documents_requis_maroc  # noqa: E402

PROFIL = {"raison_sociale": "SOCIETE EXEMPLE SARL", "adresse": "12 rue Exemple, Fès", "telephone": "05 00 00 00 00",
          "email": "contact@exemple.ma", "representant_legal": "M. Exemple"}


def lu(nom, valeur, verification="verifie", normalisee=None):
    return {"nom": nom, "libelle": nom, "type": "texte", "valeur": valeur, "valeur_normalisee": normalisee or valeur,
            "citation": valeur, "verification": verification}


def dossier(pays="union_europeenne", lectures=None, saisies=None):
    """Dossier factice : pièces du moteur de règles, documents « lus »."""
    documents = []
    for d in documents_requis_maroc(pays, classe="IIB"):
        champs = (lectures or {}).get(d.id)
        documents.append(N(code=d.id, numero=d.numero, nom=d.nom, nature=d.nature,
                           extraction_statut="terminee" if champs else None,
                           extraction={"champs": champs} if champs else None))
    return N(produit="Ciment 2", classe="IIB", pays_origine=pays, documents=documents, donnees_dispositif=saisies)


LECTURES_UE = {
    "piece_specifique_union_europeenne": [lu("numero", "CE 641427"), lu("numero_organisme_notifie", "2797"),
                                          lu("date_expiration", "26.05.2024", normalisee="2024-05-26"),
                                          lu("titulaire", "TECRES S.P.A.")],
    "declaration_conformite": [lu("fabricant", "TECRES S.P.A."),
                               lu("adresse_fabricant", "Via Andrea Doria 6, 37066 Sommacampagna, Italy")],
    "notice": [lu("indications", "Fixation de prothèses", verification="citation_introuvable"),
               lu("contact_fabricant", "Tel +39 045 9217311")],
    "catalogue": [lu("nom_marque", "TECRES"), lu("references", "TECRES | CEMEX RX | 1200/A\nTECRES | CEMEX FAST | 12A3000")],
}


class TestResolution(unittest.TestCase):
    def test_priorites_et_provenances(self):
        r = formulaires.resoudre(dossier(lectures=LECTURES_UE), PROFIL)
        self.assertEqual((r["designation"]["valeur"], r["designation"]["provenance"]), ("Ciment 2", "dossier"))
        self.assertEqual(r["classe"]["valeur"], "IIb")  # écrite comme sur le formulaire
        self.assertEqual((r["ce_numero"]["valeur"], r["ce_numero"]["provenance"]), ("CE 641427", "piece"))
        self.assertIn("pièce 4", r["ce_numero"]["detail"])
        self.assertEqual(r["ce_validite"]["valeur"], "26/05/2024")
        self.assertEqual(r["ce_organisme"]["valeur"], "2797")
        self.assertEqual(r["cvl_numero"]["valeur"], "NA")  # dispositif marqué CE : pas de certificat de vente libre
        self.assertEqual(r["importateur_nom"]["valeur"], "SOCIETE EXEMPLE SARL")
        self.assertEqual(r["fabricant_nom"]["valeur"], "TECRES S.P.A.")
        self.assertEqual(r["site_fabrication"]["valeur"], "TECRES S.P.A.")  # repris d'une autre donnée
        self.assertEqual(r["fabrication"]["valeur"], "Importé")
        self.assertTrue(r["objet"]["a_verifier"])  # valeur habituelle : à confirmer
        self.assertTrue(r["indications"]["a_verifier"])  # citation introuvable dans la notice
        self.assertFalse(r["ce_numero"]["a_verifier"])

    def test_rien_n_est_invente(self):
        r = formulaires.resoudre(dossier(), {})
        for ident in ("indications", "nom_marque", "fabricant_nom", "contient_latex", "importateur_nom", "ce_numero"):
            self.assertIsNone(r[ident]["valeur"], ident)
            self.assertEqual(r[ident]["provenance"], "manquant")

    def test_saisie_prioritaire(self):
        r = formulaires.resoudre(dossier(lectures=LECTURES_UE, saisies={"fabricant_nom": "TECRES SpA"}), PROFIL)
        self.assertEqual((r["fabricant_nom"]["valeur"], r["fabricant_nom"]["provenance"]), ("TECRES SpA", "saisie"))

    def test_origine_chine_certificat_ce_sans_objet(self):
        r = formulaires.resoudre(dossier("chine"), PROFIL)
        self.assertEqual(r["ce_numero"]["valeur"], "NA")
        self.assertIsNone(r["cvl_numero"]["valeur"])

    def test_toutes_les_lignes_des_formulaires_sont_definies(self):
        regles = formulaires.charger()
        for code, f in regles["formulaires"].items():
            for s in f["sections"]:
                for ligne in s["lignes"]:
                    ident = next(iter(ligne)) if isinstance(ligne, dict) else ligne
                    self.assertIn(ident, regles["donnees"], f"{code} : {ident}")
        self.assertEqual(formulaires.formulaires(), {"fiche_signaletique", "certificat_enregistrement_annexe2"})


class TestDocx(unittest.TestCase):
    def tearDown(self):
        shutil.rmtree(TMP / "sortie", ignore_errors=True)

    def texte(self, chemin):
        d = Docx(chemin)
        cellules = [c.text for t in d.tables for row in t.rows for c in row.cells]
        return "\n".join([p.text for p in d.paragraphs] + cellules), d

    def test_fiche_signaletique(self):
        res = formulaires.generer_formulaire(dossier(lectures=LECTURES_UE), "fiche_signaletique", "Fiche signalétique",
                                            TMP / "sortie", PROFIL)
        texte, d = self.texte(res["fichier"])
        for attendu in ("FICHE SIGNALÉTIQUE", "1- OBJET DE LA DEMANDE", "☒ Nouvel enregistrement", "☐ Mise à jour",
                        "☒ Importé", "CE 641427", "2797", "SOCIETE EXEMPLE SARL", "TECRES S.P.A.",
                        "CEMEX FAST", "12A3000", "[À COMPLÉTER]", "M. Exemple", "EN ATTENTE DE VALIDATION HUMAINE"):
            self.assertIn(attendu, texte)
        self.assertGreater(len(d.tables), 7)  # une table par section + l'annexe
        self.assertGreater(res["bilan"]["remplies"], 20)
        self.assertIn("rempli par le code", res["sources"][0]["texte_source"])

    def test_annexe2_partie_ministere_jamais_remplie(self):
        res = formulaires.generer_formulaire(dossier(lectures=LECTURES_UE), "certificat_enregistrement_annexe2",
                                            "Annexe II", TMP / "sortie", PROFIL)
        texte, _ = self.texte(res["fichier"])
        self.assertIn("Code CE (pour les dispositifs médicaux marqués CE)", texte)
        self.assertIn("ne pas remplir", texte)
        self.assertNotIn("Suite à l'avis de la Commission", texte)


def pdf(texte):
    d = pymupdf.open()
    d.new_page().insert_text((72, 72), texte)
    return d.tobytes()


class TestClassement(unittest.TestCase):
    PIECES = [N(code=d.id, numero=d.numero, nom=d.nom) for d in documents_requis_maroc("union_europeenne", "IIB")
              if d.nature == "a_fournir"]

    def numero(self, nom):
        p, _ = classement.classer(nom, self.PIECES)
        return p.numero if p else None

    def test_noms_du_dossier_accepte(self):
        attendus = {
            "3-3-Authorization Letter 2026.pdf": 3, "Confirmation Letter TECRES (ID 658919).pdf": 4,
            "EC_Certificate_FQA_CE641427_26.02.2024.pdf": 4, "ISO13485.pdf": 5, "Certificat CE ISO 13485.pdf": 5,
            "DoC for Morocco_Cemex_DRAFT (1).pdf": 6, "1200A_Cemex RX_Label.pdf": 7, "IFU PAGE 27.pdf": 8,
            "CATALOGUE.pdf": 14, "facture.pdf": None,
        }
        for nom, numero in attendus.items():
            self.assertEqual(self.numero(nom), numero, nom)

    def test_plusieurs_fichiers_reunis_en_un_pdf(self):
        nom, extension, contenu = classement.reunir([("b.pdf", ".pdf", pdf("lettre")), ("a.pdf", ".pdf", pdf("certificat"))])
        self.assertEqual(extension, ".pdf")
        d = pymupdf.open(stream=contenu, filetype="pdf")
        self.assertEqual([p.get_text().strip() for p in d], ["certificat", "lettre"])  # dans l'ordre des noms
        self.assertEqual(nom, "a.pdf + b.pdf.pdf")


if __name__ == "__main__":
    unittest.main()
