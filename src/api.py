"""
Backend FastAPI — suivi des dossiers, génération et validation humaine.

C'est la couche que consomme l'interface de validation (frontend/).
Principes (voir CLAUDE.md) :
- le rule_engine décide seul des pièces requises (déterministe, aucun appel
  IA) ; un dossier fige cette décision à sa création ;
- seules les pièces `a_rediger` sont rédigées par Mistral, en tâche de fond ;
  les pièces `a_fournir` (certificats, bulletins, échantillons) ne sont
  jamais générées : elles sont réclamées au fournisseur puis vérifiées ;
- seul un humain nommé valide ou rejette une pièce, et tout est journalisé ;
- AUCUN endpoint de dépôt : un dossier entièrement validé est « prêt pour
  dépôt manuel », le dépôt reste une démarche humaine hors du système.

Démarrage :
    uvicorn src.api:app --reload --port 8000

Variables d'environnement :
    DATABASE_URL   PostgreSQL (défaut : celui de docker-compose.yml)
    API_KEY        si définie, exigée dans l'en-tête X-API-Key (sauf /health)
    EXIGER_API_KEY "1" : refuse de démarrer si API_KEY n'est pas définie (serveur)
    CORS_ORIGINS   origines autorisées, séparées par des virgules (défaut : *)
    QDRANT_HOST, QDRANT_PORT, OLLAMA_BASE_URL : voir generate.py / embeddings.py

Documentation interactive générée automatiquement : http://localhost:8000/docs
"""
from __future__ import annotations

import datetime
import logging
import os
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import requests
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

# Les modules de src/ s'importent entre eux par leur nom (rule_engine,
# embeddings…) pour rester lançables en script (python3 src/generate.py).
# Lancée via `uvicorn src.api:app`, l'API doit donc ajouter src/ au path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import db  # noqa: E402
import taches  # noqa: E402
from db import Document, Dossier, journaliser, maintenant  # noqa: E402
from embeddings import OLLAMA_BASE_URL  # noqa: E402
from rule_engine import (  # noqa: E402
    charger_regles,
    documents_requis_maroc,
    empreinte_regles,
    prochain_creneau_depot,
)

log = logging.getLogger("api")

QDRANT_URL = f"http://{os.environ.get('QDRANT_HOST', 'localhost')}:{os.environ.get('QDRANT_PORT', '6333')}"
API_KEY = os.environ.get("API_KEY")
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
OUTPUT_DIR = (Path(__file__).resolve().parent.parent / "output").resolve()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.environ.get("EXIGER_API_KEY") == "1" and not API_KEY:
        # Déploiement serveur (docker-compose, profil api) : jamais d'API exposée sans clé
        raise RuntimeError("EXIGER_API_KEY=1 mais API_KEY n'est pas définie — refus de démarrer.")
    try:
        db.initialiser_base()
        n = taches.reprendre_apres_redemarrage()
        if n:
            log.warning("%d génération(s) interrompue(s) par le redémarrage, marquée(s) en erreur", n)
    except Exception as e:  # l'API démarre quand même : /health signale PostgreSQL indisponible
        log.error("Initialisation de la base impossible : %s", e)
    yield


def verifier_cle_api(request: Request) -> None:
    """Si API_KEY est définie, toutes les routes sauf /health l'exigent.
    Protection minimale le temps de mettre en place Keycloak (CLAUDE.md)."""
    if not API_KEY or request.url.path == "/health" or request.method == "OPTIONS":
        return
    fournie = request.headers.get("X-API-Key", "")
    if not secrets.compare_digest(fournie.encode(), API_KEY.encode()):
        raise HTTPException(status_code=401, detail="Clé d'API absente ou invalide (en-tête X-API-Key).")


app = FastAPI(
    title="API Conformité Dispositifs Médicaux",
    description="Détermine les documents requis, orchestre la rédaction des pièces à rédiger "
                "et trace leur validation humaine. Aucun dépôt automatique.",
    version="0.2.0",
    lifespan=lifespan,
    dependencies=[Depends(verifier_cle_api)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

PaysOrigine = Literal["chine", "inde", "union_europeenne", "autre"]
Classe = Literal["I", "IIA", "IIB", "III"]


# ---------------------------------------------------------------- schémas


class DocumentRequisOut(BaseModel):
    id: str
    nom: str
    nature: str
    fourni_par: str | None
    traduction_requise: bool
    legalisation_requise: bool
    origine_regle: str


class DossierRequete(BaseModel):
    pays_origine: PaysOrigine
    produit: str = Field(min_length=1, max_length=300)
    classe: Classe | None = None


class DossierDocumentsReponse(BaseModel):
    produit: str
    pays_origine: str
    pays_destination: str = "maroc"
    documents: list[DocumentRequisOut]
    prochain_creneau_depot: str


class DossierCreation(DossierRequete):
    fournisseur: str | None = Field(default=None, max_length=300)
    cree_par: str = Field(min_length=2, max_length=120)


class Acteur(BaseModel):
    acteur: str = Field(min_length=2, max_length=120)


class Decision(BaseModel):
    validateur: str = Field(min_length=2, max_length=120)
    commentaire: str | None = Field(default=None, max_length=2000)


class DocumentOut(BaseModel):
    id: int
    code: str
    nom: str
    nature: str
    fourni_par: str | None
    traduction_requise: bool
    legalisation_requise: bool
    origine_regle: str
    statut: str
    fichier_disponible: bool
    sources: list | None
    erreur: str | None
    genere_le: datetime.datetime | None
    valide_par: str | None
    valide_le: datetime.datetime | None
    commentaire: str | None


class EvenementOut(BaseModel):
    horodatage: datetime.datetime
    acteur: str
    action: str
    detail: str | None
    document_id: int | None


class DossierResume(BaseModel):
    id: int
    produit: str
    pays_origine: str
    pays_destination: str
    classe: str | None
    fournisseur: str | None
    cree_par: str
    cree_le: datetime.datetime
    regles_version: str
    statut: str
    compteurs: dict[str, int]


class DossierDetail(DossierResume):
    documents: list[DocumentOut]
    evenements: list[EvenementOut]
    prochain_creneau_depot: str | None


# ---------------------------------------------------------------- utilitaires


def _service_joignable(url: str) -> bool:
    try:
        session = requests.Session()
        session.trust_env = False  # services locaux, pas de proxy
        return session.get(url, timeout=2).ok
    except requests.exceptions.RequestException:
        return False


def _postgres_joignable() -> bool:
    try:
        with db.engine.connect() as conn:
            conn.execute(text("select 1"))
        return True
    except Exception:
        return False


def _compteurs(documents: list[Document]) -> dict[str, int]:
    c = {"total": len(documents), "valides": 0, "a_valider": 0, "a_obtenir": 0,
         "a_generer": 0, "en_cours": 0, "erreurs": 0, "rejetes": 0}
    cle = {"valide": "valides", "a_valider": "a_valider", "a_obtenir": "a_obtenir", "a_generer": "a_generer",
           "en_file": "en_cours", "en_generation": "en_cours", "erreur": "erreurs", "rejete": "rejetes"}
    for d in documents:
        c[cle[d.statut]] += 1
    return c


def _statut_dossier(documents: list[Document]) -> str:
    if documents and all(d.statut == "valide" for d in documents):
        return "pret_pour_depot_manuel"
    if any(d.statut in db.STATUTS_EN_COURS for d in documents):
        return "generation_en_cours"
    return "en_preparation"


def _resume(dossier: Dossier) -> dict:
    return {
        "id": dossier.id,
        "produit": dossier.produit,
        "pays_origine": dossier.pays_origine,
        "pays_destination": dossier.pays_destination,
        "classe": dossier.classe,
        "fournisseur": dossier.fournisseur,
        "cree_par": dossier.cree_par,
        "cree_le": dossier.cree_le,
        "regles_version": dossier.regles_version,
        "statut": _statut_dossier(dossier.documents),
        "compteurs": _compteurs(dossier.documents),
    }


def _detail(dossier: Dossier) -> dict:
    statut = _statut_dossier(dossier.documents)
    return {
        **_resume(dossier),
        "documents": [
            {
                **{k: getattr(d, k) for k in DocumentOut.model_fields if k != "fichier_disponible"},
                "fichier_disponible": bool(d.fichier) and Path(d.fichier).exists(),
            }
            for d in dossier.documents
        ],
        "evenements": [
            {"horodatage": e.horodatage, "acteur": e.acteur, "action": e.action,
             "detail": e.detail, "document_id": e.document_id}
            for e in reversed(dossier.evenements)
        ],
        "prochain_creneau_depot": str(prochain_creneau_depot()) if statut == "pret_pour_depot_manuel" else None,
    }


def _charger_dossier(session, dossier_id: int) -> Dossier:
    dossier = session.get(Dossier, dossier_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail=f"Dossier {dossier_id} introuvable.")
    return dossier


def _charger_document(session, dossier_id: int, document_id: int) -> Document:
    doc = session.get(Document, document_id)
    if doc is None or doc.dossier_id != dossier_id:
        raise HTTPException(status_code=404, detail=f"Pièce {document_id} introuvable dans le dossier {dossier_id}.")
    return doc


def _mettre_en_file(session, doc: Document, acteur: str) -> None:
    doc.statut = "en_file"
    doc.erreur = None
    journaliser(session, doc.dossier_id, acteur, "generation_demandee", doc.nom, document_id=doc.id)


# ---------------------------------------------------------------- endpoints : règles


@app.get("/health")
def health():
    """L'API répond toujours ; `services` indique si les dépendances sont disponibles."""
    return {
        "statut": "ok",
        "services": {
            "postgres": _postgres_joignable(),
            "qdrant": _service_joignable(f"{QDRANT_URL}/readyz"),
            "ollama": _service_joignable(f"{OLLAMA_BASE_URL}/api/version"),
        },
        "authentification": "cle_api" if API_KEY else "aucune",
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
    aucun appel IA sur cet endpoint. N'enregistre rien (aperçu).
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
                nature=d.nature,
                fourni_par=d.fourni_par,
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
    [Ancien mode, synchrone, sans suivi] Rédige toutes les pièces à rédiger
    et répond à la fin (plusieurs dizaines de minutes sur CPU). Préférer
    POST /dossiers puis POST /dossiers/{id}/generer, qui tracent la
    validation. Ne dépose jamais rien.
    """
    try:
        from generate import traiter_dossier
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Dépendances de génération non installées : {e}.")

    try:
        return traiter_dossier(requete.pays_origine, requete.produit, requete.classe)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Échec de la génération : {e}")


# ---------------------------------------------------------------- endpoints : suivi des dossiers


@app.get("/dossiers", response_model=list[DossierResume])
def lister_dossiers():
    with db.SessionLocal() as session:
        dossiers = session.query(Dossier).order_by(Dossier.id.desc()).all()
        return [_resume(d) for d in dossiers]


@app.post("/dossiers", response_model=DossierDetail, status_code=201)
def creer_dossier(requete: DossierCreation):
    """Crée un dossier et fige la liste des pièces décidée par le moteur de règles."""
    from generate import nouveau_dossier_sortie

    try:
        requis = documents_requis_maroc(requete.pays_origine, classe=requete.classe)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    with db.SessionLocal() as session:
        dossier = Dossier(
            produit=requete.produit,
            pays_origine=requete.pays_origine,
            classe=requete.classe,
            fournisseur=requete.fournisseur,
            regles_version=empreinte_regles("maroc"),
            dossier_sortie=str(nouveau_dossier_sortie(requete.pays_origine, requete.produit)),
            cree_par=requete.cree_par,
        )
        for ordre, d in enumerate(requis):
            dossier.documents.append(
                Document(
                    ordre=ordre,
                    code=d.id,
                    nom=d.nom,
                    nature=d.nature,
                    fourni_par=d.fourni_par,
                    consigne_redaction=d.consigne_redaction,
                    traduction_requise=d.traduction_requise,
                    legalisation_requise=d.legalisation_requise,
                    origine_regle=d.origine_regle,
                    statut="a_generer" if d.a_rediger else "a_obtenir",
                )
            )
        session.add(dossier)
        session.flush()
        journaliser(
            session, dossier.id, requete.cree_par, "dossier_cree",
            f"{len(requis)} pièces décidées par le moteur de règles (règles {dossier.regles_version})",
        )
        session.commit()
        return _detail(dossier)


@app.get("/dossiers/{dossier_id}", response_model=DossierDetail)
def lire_dossier(dossier_id: int):
    with db.SessionLocal() as session:
        return _detail(_charger_dossier(session, dossier_id))


@app.post("/dossiers/{dossier_id}/generer", response_model=DossierDetail, status_code=202)
def generer_pieces(dossier_id: int, requete: Acteur):
    """Met en file de rédaction toutes les pièces à rédiger pas encore rédigées
    (ou en erreur, ou rejetées). Répond immédiatement ; suivre via GET /dossiers/{id}."""
    with db.SessionLocal() as session:
        dossier = _charger_dossier(session, dossier_id)
        a_lancer = [d for d in dossier.documents
                    if d.nature == "a_rediger" and d.statut in ("a_generer", "erreur", "rejete")]
        if not a_lancer:
            raise HTTPException(status_code=409, detail="Aucune pièce à rédiger en attente de génération.")
        for doc in a_lancer:
            _mettre_en_file(session, doc, requete.acteur)
        session.commit()
        for doc in a_lancer:
            taches.soumettre(doc.id)
        session.expire_all()  # relire l'état réel en base (le worker a pu déjà avancer)
        return _detail(_charger_dossier(session, dossier_id))


@app.post("/dossiers/{dossier_id}/documents/{document_id}/generer", response_model=DossierDetail, status_code=202)
def generer_piece(dossier_id: int, document_id: int, requete: Acteur):
    """(Re)lance la rédaction d'une seule pièce à rédiger (une pièce validée
    doit d'abord être rejetée pour être régénérée)."""
    with db.SessionLocal() as session:
        doc = _charger_document(session, dossier_id, document_id)
        if doc.nature != "a_rediger":
            raise HTTPException(status_code=409, detail=f"'{doc.nom}' est une pièce à fournir par {doc.fourni_par} : "
                                                        "elle n'est jamais rédigée par le système.")
        if doc.statut not in ("a_generer", "erreur", "rejete", "a_valider"):
            raise HTTPException(status_code=409, detail=f"Pièce au statut '{doc.statut}' : génération impossible.")
        _mettre_en_file(session, doc, requete.acteur)
        session.commit()
        taches.soumettre(doc.id)
        session.expire_all()  # relire l'état réel en base (le worker a pu déjà avancer)
        return _detail(_charger_dossier(session, dossier_id))


@app.post("/dossiers/{dossier_id}/documents/{document_id}/valider", response_model=DossierDetail)
def valider_piece(dossier_id: int, document_id: int, decision: Decision):
    """Validation humaine explicite d'une pièce :
    - pièce à rédiger : le projet a été relu et est approuvé ;
    - pièce à fournir : la pièce a été reçue et vérifiée (commentaire obligatoire :
      référence du certificat, date de réception…)."""
    with db.SessionLocal() as session:
        doc = _charger_document(session, dossier_id, document_id)
        if doc.nature == "a_rediger" and doc.statut != "a_valider":
            raise HTTPException(status_code=409, detail=f"Pièce au statut '{doc.statut}' : seul un projet rédigé "
                                                        "(statut a_valider) peut être validé.")
        if doc.nature == "a_fournir":
            if doc.statut not in ("a_obtenir", "rejete"):
                raise HTTPException(status_code=409, detail=f"Pièce au statut '{doc.statut}' : déjà validée.")
            if not (decision.commentaire or "").strip():
                raise HTTPException(status_code=422, detail="Pour une pièce à fournir, indiquer en commentaire ce qui "
                                                            "a été reçu et vérifié (référence, date…).")
        doc.statut = "valide"
        doc.valide_par = decision.validateur
        doc.valide_le = maintenant()
        doc.commentaire = decision.commentaire
        journaliser(session, dossier_id, decision.validateur, "piece_validee",
                    f"{doc.nom}" + (f" — {decision.commentaire}" if decision.commentaire else ""), document_id=doc.id)
        session.commit()
        return _detail(_charger_dossier(session, dossier_id))


@app.post("/dossiers/{dossier_id}/documents/{document_id}/rejeter", response_model=DossierDetail)
def rejeter_piece(dossier_id: int, document_id: int, decision: Decision):
    """Rejet humain d'une pièce (motif obligatoire). Une pièce à rédiger rejetée
    peut être régénérée ; une pièce à fournir rejetée doit être redemandée."""
    if not (decision.commentaire or "").strip():
        raise HTTPException(status_code=422, detail="Le motif du rejet (commentaire) est obligatoire.")
    with db.SessionLocal() as session:
        doc = _charger_document(session, dossier_id, document_id)
        autorises = ("a_valider", "valide") if doc.nature == "a_rediger" else ("a_obtenir", "valide")
        if doc.statut not in autorises:
            raise HTTPException(status_code=409, detail=f"Pièce au statut '{doc.statut}' : rejet impossible.")
        doc.statut = "rejete"
        doc.valide_par = decision.validateur
        doc.valide_le = maintenant()
        doc.commentaire = decision.commentaire
        journaliser(session, dossier_id, decision.validateur, "piece_rejetee",
                    f"{doc.nom} — {decision.commentaire}", document_id=doc.id)
        session.commit()
        return _detail(_charger_dossier(session, dossier_id))


@app.get("/dossiers/{dossier_id}/documents/{document_id}/fichier")
def telecharger_piece(dossier_id: int, document_id: int):
    """Télécharge le projet DOCX d'une pièce rédigée, pour relecture."""
    with db.SessionLocal() as session:
        doc = _charger_document(session, dossier_id, document_id)
        if not doc.fichier:
            raise HTTPException(status_code=404, detail="Aucun fichier généré pour cette pièce.")
        chemin = Path(doc.fichier).resolve()
        if not chemin.is_relative_to(OUTPUT_DIR) or not chemin.exists():
            raise HTTPException(status_code=404, detail="Fichier introuvable sur le serveur.")
        return FileResponse(
            chemin,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"dossier{dossier_id}_{doc.code}.docx",
        )
