"""
Calcul des embeddings (vecteurs) pour le RAG — un seul point d'entrée
partagé par ingest.py (indexation) et generate.py (recherche).

Le modèle est toujours BAAI/bge-m3 (multilingue, 1024 dimensions) ; seul
le moteur qui l'exécute change, via la variable d'environnement
EMBEDDING_BACKEND :

- "ollama" (défaut) : bge-m3 servi par Ollama (/api/embed), le même serveur
  que Mistral. Aucune dépendance torch, aucun accès à Hugging Face requis.
    ollama pull bge-m3
- "sentence-transformers" : bge-m3 chargé en local depuis Hugging Face.

IMPORTANT : une collection Qdrant doit être indexée ET interrogée avec le
même backend (les vecteurs des deux moteurs sont proches mais pas
identiques). Le backend utilisé est enregistré dans le payload de chaque
chunk (champ `embedding`) pour la traçabilité — ré-indexer si on en change.
"""
from __future__ import annotations

import os

import requests

VECTOR_SIZE = 1024

BACKEND = os.environ.get("EMBEDDING_BACKEND", "ollama")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBEDDING_MODEL = os.environ.get("OLLAMA_EMBEDDING_MODEL", "bge-m3")
ST_EMBEDDING_MODEL = "BAAI/bge-m3"


class Embedder:
    def __init__(self, backend: str = BACKEND):
        self.backend = backend
        if backend == "ollama":
            self.nom_modele = OLLAMA_EMBEDDING_MODEL
            # Session sans proxy : Ollama tourne en local
            self._session = requests.Session()
            self._session.trust_env = False
        elif backend == "sentence-transformers":
            from sentence_transformers import SentenceTransformer

            self.nom_modele = ST_EMBEDDING_MODEL
            self._model = SentenceTransformer(ST_EMBEDDING_MODEL)
        else:
            raise ValueError(
                f"EMBEDDING_BACKEND inconnu : '{backend}' (attendu : ollama, sentence-transformers)"
            )

    @property
    def identifiant(self) -> str:
        """Identifiant stocké dans le payload Qdrant, ex. 'ollama:bge-m3'."""
        return f"{self.backend}:{self.nom_modele}"

    def encoder(self, textes: list[str]) -> list[list[float]]:
        """Retourne un vecteur de VECTOR_SIZE dimensions par texte."""
        if not textes:
            return []
        if self.backend == "sentence-transformers":
            return self._model.encode(textes).tolist()

        try:
            reponse = self._session.post(
                f"{OLLAMA_BASE_URL}/api/embed",
                json={"model": self.nom_modele, "input": textes},
                timeout=600,
            )
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(
                f"Ollama injoignable sur {OLLAMA_BASE_URL} — lancer `ollama serve` "
                f"et `ollama pull {self.nom_modele}`."
            ) from e
        if reponse.status_code == 404:
            raise RuntimeError(
                f"Modèle d'embedding '{self.nom_modele}' absent d'Ollama — "
                f"lancer `ollama pull {self.nom_modele}`."
            )
        reponse.raise_for_status()
        vecteurs = reponse.json()["embeddings"]
        if vecteurs and len(vecteurs[0]) != VECTOR_SIZE:
            raise RuntimeError(
                f"Le modèle '{self.nom_modele}' produit des vecteurs de {len(vecteurs[0])} "
                f"dimensions, {VECTOR_SIZE} attendues (bge-m3)."
            )
        return vecteurs

    def encoder_un(self, texte: str) -> list[float]:
        return self.encoder([texte])[0]
