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
        return Reponse(self.codes.pop(0), self.contenu)


def generateur(session):
    g = object.__new__(generate.GenerateurDocuments)  # sans Qdrant ni embeddings
    g._session_ollama = session
    g.references_pour_document = lambda *a, **k: []
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
