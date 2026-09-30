"""
Tests de la relance après une erreur 500 passagère d'Ollama (observée sur
une génération interrompue au bout de 3 min) — sans Ollama ni Qdrant.

    python -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import extraction  # noqa: E402
import generate  # noqa: E402
from rule_engine import documents_requis_maroc  # noqa: E402


class Reponse:
    def __init__(self, code, contenu='{"response": "Texte rédigé"}'):
        self.status_code = code
        self._contenu = contenu

    def json(self):
        import json
        return json.loads(self._contenu)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError("raise_for_status ne doit pas être atteint sur une 500")


class FausseSession:
    def __init__(self, codes, contenu='{"response": "Texte rédigé"}'):
        self.codes = list(codes)
        self.appels = 0
        self.contenu = contenu
        self.trust_env = True

    def post(self, *a, **k):
        self.appels += 1
        self.dernier_json = k.get("json")
        return Reponse(self.codes.pop(0), self.contenu)


def generateur(session, modele=None):
    g = object.__new__(generate.GenerateurDocuments)  # sans Qdrant ni embeddings
    g._session_ollama = session
    g.references_pour_document = lambda *a, **k: []
    g.modele_pour = lambda *a, **k: modele
    return g


PIECE = next(d for d in documents_requis_maroc("union_europeenne", "IIB") if d.a_rediger)


@mock.patch("time.sleep", lambda s: None)
class TestRelanceRedaction(unittest.TestCase):
    def test_500_puis_succes(self):
        s = FausseSession([500, 200])
        texte, _ = generateur(s).generer_contenu(PIECE, "maroc", "Ciment osseux", "union_europeenne")
        self.assertEqual(texte, "Texte rédigé")
        self.assertEqual(s.appels, 2)

    def test_deux_500_erreur_claire(self):
        s = FausseSession([500, 500])
        with self.assertRaisesRegex(generate.GenerationImpossible, "échoué deux fois"):
            generateur(s).generer_contenu(PIECE, "maroc", "Ciment osseux", "union_europeenne")
        self.assertEqual(s.appels, 2)

    def test_succes_direct_un_seul_appel(self):
        s = FausseSession([200])
        generateur(s).generer_contenu(PIECE, "maroc", "Ciment osseux", "union_europeenne")
        self.assertEqual(s.appels, 1)


MODELE = {"numero": 1, "produit": "Ciment osseux", "pays_origine": "union_europeenne",
          "fichier": "union_europeenne/Ciment osseux/1-1-Lettre.pdf", "indexe_le": "2026-10-01", "score": 0.8,
          "texte": "SOCIETE EXEMPLE SARL — A Monsieur le Directeur Général de l'AMMPS — Désignation : Ciment osseux"}


class TestModeleDansLePrompt(unittest.TestCase):
    def test_modele_transmis_et_trace(self):
        s = FausseSession([200])
        _, sources = generateur(s, MODELE).generer_contenu(PIECE, "maroc", "Vis d'ostéosynthèse", "union_europeenne")
        prompt = s.dernier_json["prompt"]
        self.assertIn("MODÈLE À SUIVRE", prompt)
        self.assertIn("SOCIETE EXEMPLE SARL", prompt)
        self.assertIn("Ne laisse aucune donnée propre à l'ancien dispositif", prompt)
        self.assertIn("Vis d'ostéosynthèse", prompt)
        self.assertTrue(sources[0]["texte_source"].startswith("Modèle : pièce 1"))  # visible à la validation
        self.assertEqual(s.dernier_json["options"]["num_ctx"], 8192)

    def test_sans_modele_redaction_quand_meme(self):
        s = FausseSession([200])
        _, sources = generateur(s).generer_contenu(PIECE, "maroc", "Vis", "union_europeenne")
        self.assertNotIn("MODÈLE À SUIVRE", s.dernier_json["prompt"])
        self.assertEqual(sources, [])

    def test_destinataire_ammps_lu_dans_les_regles(self):
        s = FausseSession([200])
        generateur(s).generer_contenu(PIECE, "maroc", "Vis", "union_europeenne")
        self.assertIn("Directeur Général de l'Agence Marocaine des Médicaments", s.dernier_json["prompt"])
        self.assertNotIn("Monsieur le Ministre", s.dernier_json["prompt"])


@mock.patch("time.sleep", lambda s: None)
class TestRelanceLecture(unittest.TestCase):
    CHAMPS = [{"nom": "numero", "libelle": "Numéro", "type": "texte", "description": "numéro"}]
    JSON = '{"response": "{\\"numero\\": {\\"valeur\\": \\"CE 641427\\", \\"citation\\": \\"CE 641427\\"}}"}'

    def test_500_puis_succes(self):
        s = FausseSession([500, 200], self.JSON)
        with mock.patch.object(extraction.requests, "Session", return_value=s):
            r = extraction.interroger_mistral("Certificat CE 641427", self.CHAMPS, "certificat CE")
        self.assertEqual(r["numero"]["valeur"], "CE 641427")
        self.assertEqual(s.appels, 2)

    def test_deux_500_erreur_claire(self):
        s = FausseSession([500, 500], self.JSON)
        with mock.patch.object(extraction.requests, "Session", return_value=s):
            with self.assertRaisesRegex(extraction.ExtractionImpossible, "échoué deux fois"):
                extraction.interroger_mistral("Certificat CE 641427", self.CHAMPS, "certificat CE")


if __name__ == "__main__":
    unittest.main()
