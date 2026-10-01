"""
Contrôles automatiques de la checklist (src/controles.py) — sans Mistral :
résultats de lecture factices au format réel.

    python -m unittest discover -s tests
"""
import datetime
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as N

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import controles  # noqa: E402
from rule_engine import documents_requis_maroc  # noqa: E402

AUJOURDHUI = datetime.date(2026, 10, 1)


def champ(nom, valeur, verification="verifie", normalisee=None):
    return {"nom": nom, "libelle": nom, "type": "texte", "valeur": valeur, "valeur_normalisee": normalisee or valeur,
            "citation": valeur, "verification": verification}


def dossier(pays="union_europeenne", classe="IIB", lectures=None, textes=None, humains=None):
    pieces = []
    for d in documents_requis_maroc(pays, classe):
        champs = (lectures or {}).get(d.id)
        pieces.append(N(code=d.id, numero=d.numero, nom=d.nom, nature=d.nature, statut="a_obtenir" if d.nature == "a_fournir" else "a_generer",
                        fourni_par=d.fourni_par, fichier_recu="x.pdf" if champs is not None else None,
                        extraction_statut="terminee" if champs is not None else None,
                        extraction={"champs": champs} if champs is not None else None,
                        texte_recu=(textes or {}).get(d.id, "")))
    return N(produit="Ciment 2", classe=classe, pays_origine=pays, documents=pieces, controles_humains=humains)


def element(resultat, doc_id, texte_debut):
    doc = next(d for d in resultat["documents"] if d["id"] == doc_id)
    return next(e for e in doc["elements"] if e["texte"].startswith(texte_debut))


class TestChecklistAppliquee(unittest.TestCase):
    def test_documents_applicables_selon_le_dossier(self):
        ue = {d["id"] for d in controles.evaluer(dossier(), AUJOURDHUI)["documents"]}
        self.assertIn("certificat_ce_mdd_mdr", ue)
        self.assertNotIn("free_sales_certificate_fsc", ue)  # UE IIb : le certificat CE suffit
        self.assertNotIn("etude_clinique", ue)
        chine = {d["id"] for d in controles.evaluer(dossier("chine"), AUJOURDHUI)["documents"]}
        self.assertIn("free_sales_certificate_fsc", chine)
        self.assertIn("etude_clinique", chine)
        self.assertNotIn("certificat_ce_mdd_mdr", chine)

    def test_points_lus_dans_le_checklist_des_pieces(self):
        noms = [c["nom"] for c in controles.champs_checklist("declaration_conformite")]
        self.assertEqual(len(noms), 22)  # 30 points de la DoC dont 22 « lecture »
        self.assertIn(controles.element_id("declaration_de_conformite", 0), noms)  # code EMDN


class TestEvaluation(unittest.TestCase):
    def test_en_attente_puis_lecture(self):
        r = controles.evaluer(dossier(), AUJOURDHUI)
        self.assertEqual(element(r, "declaration_de_conformite", "Doit contenir le code EMDN")["statut"], "en_attente")
        emdn = controles.element_id("declaration_de_conformite", 0)
        r = controles.evaluer(dossier(lectures={"declaration_conformite": [champ(emdn, "EMDN P099001")]}), AUJOURDHUI)
        e = element(r, "declaration_de_conformite", "Doit contenir le code EMDN")
        self.assertEqual((e["statut"], e["detail"]), ("ok", "EMDN P099001"))

    def test_absent_ko_sauf_si_applicable(self):
        lu = [champ(controles.element_id("declaration_de_conformite", 0), None, "absent"),
              champ(controles.element_id("declaration_de_conformite", 6), None, "absent")]
        r = controles.evaluer(dossier(lectures={"declaration_conformite": lu}), AUJOURDHUI)
        self.assertEqual(element(r, "declaration_de_conformite", "Doit contenir")["statut"], "ko")
        self.assertEqual(element(r, "declaration_de_conformite", "UDI-DI")["statut"], "a_verifier")  # (si applicable)

    def test_expiration_et_exception_2023_607(self):
        expire = [champ("date_expiration", "26.05.2024", normalisee="2024-05-26")]
        r = controles.evaluer(dossier(lectures={"iso_13485": expire}), AUJOURDHUI)
        self.assertEqual(element(r, "certificat_iso", "Statut valide")["statut"], "ko")
        r = controles.evaluer(dossier(lectures={"piece_specifique_union_europeenne": expire},
                                      textes={"piece_specifique_union_europeenne": "Confirmation letter Regulation (EU) 2023/607"}), AUJOURDHUI)
        e = element(r, "certificat_ce_mdd_mdr", "Date de validité")
        self.assertEqual(e["statut"], "a_verifier")  # comme le dossier Ciment osseux accepté
        self.assertIn("2023/607", e["detail"])
        valide = [champ("date_expiration", "31/12/2028", normalisee="2028-12-31")]
        r = controles.evaluer(dossier(lectures={"iso_13485": valide}), AUJOURDHUI)
        self.assertEqual(element(r, "certificat_iso", "Statut valide")["statut"], "ok")

    def test_classe_comparee_au_dossier(self):
        r = controles.evaluer(dossier(lectures={"declaration_conformite": [champ("classe_indiquee", "Class IIb")]}), AUJOURDHUI)
        self.assertEqual(element(r, "declaration_de_conformite", "Classe du DM")["statut"], "ok")
        r = controles.evaluer(dossier(lectures={"declaration_conformite": [champ("classe_indiquee", "Class III")]}), AUJOURDHUI)
        e = element(r, "declaration_de_conformite", "Classe du DM")
        self.assertEqual(e["statut"], "ko")
        self.assertIn("III", e["detail"])

    def test_coherence_fabricant_et_numero_ce(self):
        num_doc = controles.element_id("declaration_de_conformite", 14)  # « Numéro du certificat »
        lectures = {
            "declaration_conformite": [champ("fabricant", "TECRES S.P.A."), champ(num_doc, "CE 641427")],
            "piece_specifique_union_europeenne": [champ("titulaire", "Tecres SpA"), champ("numero", "CE641427")],
            "etiquetage": [champ("fabricant", "TECRES S.p.A.")],
        }
        r = controles.evaluer(dossier(lectures=lectures), AUJOURDHUI)
        e = element(r, "declaration_de_conformite", "Cohérence avec le certificat CE")
        self.assertEqual(e["statut"], "ok", e["detail"])
        self.assertIn("n° de certificat CE 641427", e["detail"])
        lectures["declaration_conformite"][1] = champ(num_doc, "CE 999999")
        e = element(controles.evaluer(dossier(lectures=lectures), AUJOURDHUI), "declaration_de_conformite", "Cohérence avec le certificat CE")
        self.assertEqual(e["statut"], "ko")
        lectures["declaration_conformite"][1] = champ(num_doc, "CE 641427")
        lectures["etiquetage"] = [champ("fabricant", "Autre Fabricant Ltd")]
        r = controles.evaluer(dossier(lectures=lectures), AUJOURDHUI)
        e = element(r, "declaration_de_conformite", "Cohérence avec l’étiquetage")
        self.assertEqual(e["statut"], "ko")
        self.assertIn("Autre Fabricant", e["detail"])

    def test_points_humains_et_relance(self):
        sig = controles.element_id("declaration_de_conformite", 19)
        r = controles.evaluer(dossier(humains={sig: {"par": "Taha", "le": "2026-10-01T10:00:00"}}), AUJOURDHUI)
        self.assertEqual(element(r, "declaration_de_conformite", "Signature d’une personne autorisée")["statut"], "humain_fait")
        self.assertGreater(r["resume"]["humain_a_faire"], 0)
        noms = [d["nom"] for d in r["a_reclamer"]]
        self.assertTrue(any("ISO 13485" in n for n in noms))  # rien reçu : tout est à réclamer
        self.assertIn("AMMPS", r["relance"])
        self.assertIn("Ciment 2", r["relance"])


if __name__ == "__main__":
    unittest.main()
