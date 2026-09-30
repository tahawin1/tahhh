"""
Tests de l'API (suivi, génération en file, validation humaine), sans
infrastructure : base SQLite temporaire, générateur factice à la place de
Mistral, génération exécutée immédiatement au lieu d'une tâche de fond.

    python -m unittest discover -s tests
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="conformite-tests-"))
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{TMP / 'test.db'}"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docx import Document as Docx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402
import db  # noqa: E402
import generate  # noqa: E402
import taches  # noqa: E402

APPELS_GENERATION: list[str] = []
CONTEXTES: list[dict] = []


def faux_generer_document(_generateur, doc, produit, pays_origine, dossier_sortie, **contexte):
    """Remplace RAG + Mistral : écrit un vrai DOCX minimal, et refuse comme le vrai une pièce à fournir."""
    if not doc.a_rediger:
        raise generate.GenerationImpossible("pièce à fournir")
    APPELS_GENERATION.append(doc.id)
    CONTEXTES.append(contexte)
    dossier_sortie.mkdir(parents=True, exist_ok=True)
    chemin = dossier_sortie / f"{doc.id}.docx"
    d = Docx()
    d.add_paragraph(f"Projet : {doc.nom} — {produit}")
    d.save(chemin)
    return {"fichier": str(chemin), "sources": [{"texte_source": "Arrêtés 2853-2856", "date_version": "2015-08-04"}]}


class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        generate.OUTPUT_DIR = TMP / "output"
        api.OUTPUT_DIR = (TMP / "output").resolve()
        generate.generer_document = faux_generer_document
        taches._obtenir_generateur = lambda: None
        taches.soumettre = taches.executer_generation  # exécution immédiate
        cls.client = TestClient(api.app)
        cls.client.__enter__()  # déclenche le lifespan (création des tables)

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        shutil.rmtree(TMP, ignore_errors=True)

    def setUp(self):
        APPELS_GENERATION.clear()
        api.API_KEY = None

    def creer(self, pays="chine", classe="IIB"):
        r = self.client.post("/dossiers", json={
            "pays_origine": pays, "produit": "Prothèse orthopédique de hanche",
            "classe": classe, "fournisseur": "Fournisseur test", "cree_par": "Testeur"})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    @staticmethod
    def piece(dossier, code):
        return next(d for d in dossier["documents"] if d["code"] == code)

    def test_creation_fige_la_decision_du_moteur_de_regles(self):
        d = self.creer()
        self.assertEqual(d["compteurs"]["total"], 8)
        natures = {x["code"]: (x["nature"], x["statut"]) for x in d["documents"]}
        self.assertEqual(natures["demande_signee"], ("a_rediger", "a_generer"))
        self.assertEqual(natures["piece_specifique_chine"], ("a_fournir", "a_obtenir"))
        self.assertEqual(natures["iso_13485"], ("a_fournir", "a_obtenir"))
        self.assertEqual(d["statut"], "en_preparation")
        self.assertEqual(len(d["regles_version"]), 12)
        self.assertEqual(d["evenements"][0]["action"], "dossier_cree")

    def test_classe_I_sans_iso(self):
        d = self.creer(pays="union_europeenne", classe="I")
        self.assertNotIn("iso_13485", [x["code"] for x in d["documents"]])

    def test_generation_ne_redige_que_les_pieces_a_rediger(self):
        d = self.creer()
        r = self.client.post(f"/dossiers/{d['id']}/generer", json={"acteur": "Testeur"})
        self.assertEqual(r.status_code, 202, r.text)
        self.assertEqual(sorted(APPELS_GENERATION),
                         sorted(["demande_signee", "fiche_signaletique", "dossier_technique", "mandataire_maroc"]))
        d = self.client.get(f"/dossiers/{d['id']}").json()
        for x in d["documents"]:
            attendu = "a_valider" if x["nature"] == "a_rediger" else "a_obtenir"
            self.assertEqual(x["statut"], attendu, x["code"])
        self.assertTrue(self.piece(d, "demande_signee")["fichier_disponible"])

    def test_contexte_transmis_a_la_redaction(self):
        d = self.creer()
        CONTEXTES.clear()
        self.client.post(f"/dossiers/{d['id']}/generer", json={"acteur": "Testeur"})
        ctx = CONTEXTES[0]
        self.assertEqual(ctx["classe"], "IIB")
        self.assertEqual(ctx["fournisseur"], "Fournisseur test")
        # la liste des pièces transmise à Mistral est exactement celle du moteur de règles
        self.assertEqual(ctx["pieces_du_dossier"], [x["nom"] for x in d["documents"]])

    def test_piece_a_fournir_jamais_generee(self):
        d = self.creer()
        nmpa = self.piece(d, "piece_specifique_chine")
        r = self.client.post(f"/dossiers/{d['id']}/documents/{nmpa['id']}/generer", json={"acteur": "Testeur"})
        self.assertEqual(r.status_code, 409)
        self.assertIn("jamais rédigée", r.json()["detail"])
        self.assertEqual(APPELS_GENERATION, [])

    def test_cycle_complet_de_validation(self):
        d = self.creer(pays="union_europeenne", classe="IIA")
        self.client.post(f"/dossiers/{d['id']}/generer", json={"acteur": "Testeur"})
        d = self.client.get(f"/dossiers/{d['id']}").json()
        for x in d["documents"]:
            url = f"/dossiers/{d['id']}/documents/{x['id']}/valider"
            if x["nature"] == "a_fournir":
                r = self.client.post(url, json={"validateur": "Relecteur"})
                self.assertEqual(r.status_code, 422, "commentaire obligatoire pour une pièce à fournir")
                r = self.client.post(url, json={"validateur": "Relecteur", "commentaire": "Reçu le 30/09, réf. X"})
            else:
                r = self.client.post(url, json={"validateur": "Relecteur"})
            self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["statut"], "pret_pour_depot_manuel")
        self.assertIsNotNone(d["prochain_creneau_depot"])
        self.assertTrue(all(x["valide_par"] == "Relecteur" for x in d["documents"]))

    def test_rejet_motif_obligatoire_puis_regeneration(self):
        d = self.creer()
        self.client.post(f"/dossiers/{d['id']}/generer", json={"acteur": "Testeur"})
        demande = self.piece(self.client.get(f"/dossiers/{d['id']}").json(), "demande_signee")
        url = f"/dossiers/{d['id']}/documents/{demande['id']}"
        self.assertEqual(self.client.post(f"{url}/rejeter", json={"validateur": "Relecteur"}).status_code, 422)
        r = self.client.post(f"{url}/rejeter", json={"validateur": "Relecteur", "commentaire": "Recopie les sources"})
        self.assertEqual(self.piece(r.json(), "demande_signee")["statut"], "rejete")
        APPELS_GENERATION.clear()
        r = self.client.post(f"{url}/generer", json={"acteur": "Testeur"})
        self.assertEqual(r.status_code, 202)
        self.assertEqual(APPELS_GENERATION, ["demande_signee"])
        self.assertEqual(self.piece(r.json(), "demande_signee")["statut"], "a_valider")

    def test_validation_impossible_avant_redaction(self):
        d = self.creer()
        demande = self.piece(d, "demande_signee")
        r = self.client.post(f"/dossiers/{d['id']}/documents/{demande['id']}/valider", json={"validateur": "Relecteur"})
        self.assertEqual(r.status_code, 409)

    def test_telechargement_du_projet(self):
        d = self.creer()
        self.client.post(f"/dossiers/{d['id']}/generer", json={"acteur": "Testeur"})
        demande = self.piece(d, "demande_signee")
        r = self.client.get(f"/dossiers/{d['id']}/documents/{demande['id']}/fichier")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b"PK"))  # un .docx est une archive zip

    def test_apercu_du_projet(self):
        d = self.creer()
        self.client.post(f"/dossiers/{d['id']}/generer", json={"acteur": "Testeur"})
        demande = self.piece(d, "demande_signee")
        r = self.client.get(f"/dossiers/{d['id']}/documents/{demande['id']}/apercu")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("Projet : Demande signée", r.json()["paragraphes"][0]["texte"])
        nmpa = self.piece(d, "piece_specifique_chine")
        self.assertEqual(self.client.get(f"/dossiers/{d['id']}/documents/{nmpa['id']}/apercu").status_code, 404)

    def test_aucune_route_de_depot(self):
        chemins = [getattr(r, "path", "") for r in api.app.routes]
        for mot in ("depot", "deposer", "soumission", "envoi"):
            self.assertFalse(any(mot in c for c in chemins), f"route suspecte contenant '{mot}' : {chemins}")

    def test_cle_api(self):
        api.API_KEY = "secret-test"
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/dossiers").status_code, 401)
        self.assertEqual(self.client.get("/dossiers", headers={"X-API-Key": "mauvaise"}).status_code, 401)
        self.assertEqual(self.client.get("/dossiers", headers={"X-API-Key": "secret-test"}).status_code, 200)

    def test_generation_interrompue_marquee_en_erreur_au_redemarrage(self):
        d = self.creer()
        with db.SessionLocal() as s:
            doc = s.get(db.Document, self.piece(d, "demande_signee")["id"])
            doc.statut = "en_generation"
            s.commit()
        self.assertGreaterEqual(taches.reprendre_apres_redemarrage(), 1)
        d = self.client.get(f"/dossiers/{d['id']}").json()
        self.assertEqual(self.piece(d, "demande_signee")["statut"], "erreur")

    def test_dossier_inexistant(self):
        self.assertEqual(self.client.get("/dossiers/999999").status_code, 404)


if __name__ == "__main__":
    unittest.main()
