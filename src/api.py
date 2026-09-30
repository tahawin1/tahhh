"""
Backend FastAPI — expose le moteur de règles et la génération de dossiers.

C'est la couche que l'interface de validation humaine (React) consommera.
Le principe reste le même que dans le reste du projet : le rule_engine
décide seul des documents requis (déterministe, aucun appel IA), et
/dossiers/generer est le seul endpoint qui appelle le RAG + Mistral —
jamais de dépôt automatique exposé par cette API.

Démarrage :
    uvicorn src.api:app --reload --port 8000

Documentation interactive générée automatiquement : http://localhost:8000/docs
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Les modules de src/ s'importent entre eux par leur nom (rule_engine,
# embeddings…) pour rester lançables en script (python3 src/generate.py).
# Lancée via `uvicorn src.api:app`, l'API doit donc ajouter src/ au path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from embeddings import OLLAMA_BASE_URL  # noqa: E402
from rule_engine import charger_regles, documents_requis_maroc, prochain_creneau_depot  # noqa: E402

QDRANT_URL = "http://localhost:6333"

app = FastAPI(
    title="API Conformité Dispositifs Médicaux",
    description="Détermine les documents requis et orchestre leur génération, "
                 "sous validation humaine obligatoire avant tout dépôt.",
    version="0.1.0",
)

# CORS ouvert en dev uniquement — à restreindre à l'origine du frontend en production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PaysOrigine = Literal["chine", "inde", "union_europeenne", "autre"]
Classe = Literal["I", "IIA", "IIB", "III"]


class DocumentRequisOut(BaseModel):
    id: str
    nom: str
    traduction_requise: bool
    legalisation_requise: bool
    origine_regle: str


class DossierRequete(BaseModel):
    pays_origine: PaysOrigine
    produit: str
    classe: Classe | None = None


class DossierDocumentsReponse(BaseModel):
    produit: str
    pays_origine: str
    pays_destination: str = "maroc"
    documents: list[DocumentRequisOut]
    prochain_creneau_depot: str


def _service_joignable(url: str) -> bool:
    try:
        session = requests.Session()
        session.trust_env = False  # services locaux, pas de proxy
        return session.get(url, timeout=2).ok
    except requests.exceptions.RequestException:
        return False


@app.get("/health")
def health():
    """L'API répond toujours ; `services` indique si la génération
    (/dossiers/generer) a ses dépendances disponibles."""
    return {
        "statut": "ok",
        "services": {
            "qdrant": _service_joignable(f"{QDRANT_URL}/readyz"),
            "ollama": _service_joignable(f"{OLLAMA_BASE_URL}/api/version"),
        },
    }


@app.get("/pays")
def liste_pays():
    """Liste les pays dont les règles sont chargées, avec un résumé de chacun."""
    resultat = {}
    for pays in ["maroc", "chine", "inde", "union_europeenne"]:
        regles = charger_regles(pays)
        resultat[pays] = {
            "autorite": regles["autorite"],
            "classification": regles["classification"],
        }
    return resultat


@app.post("/dossiers/documents-requis", response_model=DossierDocumentsReponse)
def documents_requis(requete: DossierRequete):
    """
    Détermine la liste des documents requis pour un dossier marocain, selon
    le pays d'origine du fournisseur — logique 100% déterministe (YAML),
    aucun appel IA sur cet endpoint.
    """
    try:
        documents = documents_requis_maroc(requete.pays_origine, classe=requete.classe)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return DossierDocumentsReponse(
        produit=requete.produit,
        pays_origine=requete.pays_origine,
        documents=[
            DocumentRequisOut(
                id=d.id,
                nom=d.nom,
                traduction_requise=d.traduction_requise,
                legalisation_requise=d.legalisation_requise,
                origine_regle=d.origine_regle,
            )
            for d in documents
        ],
        prochain_creneau_depot=str(prochain_creneau_depot()),
    )


@app.post("/dossiers/generer")
def generer_dossier(requete: DossierRequete):
    """
    Lance la génération complète (RAG + Mistral + DOCX) pour un dossier.
    Nécessite Qdrant indexé et Ollama démarré — voir README.md.
    Le résultat est TOUJOURS marqué en attente de validation humaine ;
    cet endpoint ne dépose jamais rien automatiquement.
    """
    try:
        # Import différé : generate.py charge sentence-transformers au niveau
        # module, ce qui est coûteux — on ne paie ce coût que si l'endpoint
        # est réellement appelé, pas à chaque démarrage de l'API.
        from generate import traiter_dossier
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Dépendances de génération non installées : {e}. "
                    "Voir README.md (qdrant-client, sentence-transformers).",
        )

    try:
        resultat = traiter_dossier(requete.pays_origine, requete.produit, requete.classe)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Échec de la génération : {e}")

    return resultat
