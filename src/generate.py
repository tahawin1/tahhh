"""
Pipeline de génération documentaire : Rule Engine → RAG → Mistral → DOCX.

Le LLM ne décide jamais des documents requis (c'est rule_engine.py qui
décide) — il ne fait que rédiger le contenu de chaque document en
s'appuyant sur des extraits réels retrouvés dans la base vectorielle
(dossiers déjà réalisés + textes réglementaires).

Usage :
    python3 src/generate.py --pays-origine chine --produit "Prothèse orthopédique de hanche" --classe IIB
"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import time
import unicodedata
from pathlib import Path

import requests
from docx import Document
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from embeddings import OLLAMA_BASE_URL, Embedder
from rule_engine import DocumentRequis, documents_requis_maroc, prochain_creneau_depot

COLLECTION = "dossiers_reference"
OLLAMA_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral")
# Sur CPU seul, Mistral 7B rédige ~5 tokens/s : prévoir large.
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "900"))
# Longueur maximale de chaque document généré (tokens) ; -1 = sans limite.
OLLAMA_NUM_PREDICT = int(os.environ.get("OLLAMA_NUM_PREDICT", "700"))
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"

# Pays dont les textes sont indexés dans Qdrant (voir scripts/indexer_tout.sh)
PAYS_INDEXES = {"maroc", "chine", "inde", "union_europeenne"}

MENTION_VALIDATION = (
    "PROJET GÉNÉRÉ AUTOMATIQUEMENT — EN ATTENTE DE VALIDATION HUMAINE. "
    "Ne pas déposer avant relecture et validation explicite."
)


class GenerationImpossible(RuntimeError):
    """La génération d'un document n'a pas pu aboutir (ou n'est pas permise)."""


class GenerateurDocuments:
    def __init__(self, host: str | None = None, port: int | None = None):
        self.client = QdrantClient(
            host=host or os.environ.get("QDRANT_HOST", "localhost"),
            port=port or int(os.environ.get("QDRANT_PORT", "6333")),
        )
        self.embedder = Embedder()
        self._session_ollama = requests.Session()
        self._session_ollama.trust_env = False  # Ollama tourne en local, pas de proxy

    def rechercher_references(self, pays: str, requete: str, k: int = 3) -> list[dict]:
        """Recherche les chunks les plus pertinents pour un pays donné (RAG)."""
        vecteur = self.embedder.encoder_un(requete)
        resultats = self.client.query_points(
            collection_name=COLLECTION,
            query=vecteur,
            query_filter=Filter(must=[FieldCondition(key="pays", match=MatchValue(value=pays))]),
            limit=k,
            with_payload=True,
        ).points
        return [{**r.payload, "score": r.score} for r in resultats]

    def references_pour_document(self, document: DocumentRequis, pays_destination: str, pays_origine: str) -> list[dict]:
        """
        Choisit (par le code, pas par le LLM) dans quels textes chercher :
        toujours ceux du pays de destination ; en plus, pour la pièce
        spécifique à l'origine (certificat NMPA / CDSCO / CE), ceux du pays
        d'origine qui délivre ce certificat.
        """
        requete = f"{document.nom}. {document.consigne_redaction or ''}".strip()
        references = self.rechercher_references(pays_destination, requete, k=3)
        if document.origine_regle.startswith("piece_specifique") and pays_origine in PAYS_INDEXES:
            references += self.rechercher_references(pays_origine, document.nom, k=2)
        return references

    def generer_contenu(
        self,
        document: DocumentRequis,
        pays_destination: str,
        produit: str,
        pays_origine: str,
        classe: str | None = None,
        fournisseur: str | None = None,
        pieces_du_dossier: list[str] | None = None,
    ) -> tuple[str, list[dict]]:
        """Appelle Mistral (via Ollama) pour rédiger le contenu d'un document,
        en s'appuyant sur les extraits réglementaires retrouvés par RAG.
        Retourne (contenu, références utilisées) — les références sont
        remontées à la validation humaine pour vérification.

        Lève GenerationImpossible si le document n'est pas à rédiger ou si
        Mistral ne répond pas : jamais de document de remplacement."""
        if not document.a_rediger:
            raise GenerationImpossible(
                f"'{document.nom}' est une pièce à fournir par {document.fourni_par} : "
                "elle n'est jamais rédigée par le système."
            )

        references = self.references_pour_document(document, pays_destination, pays_origine)
        contexte = "\n\n".join(
            f"<<< EXTRAIT {i} — {r['texte_source']} (version du {r['date_version']})\n{r['texte'][:800]}\n>>>"
            for i, r in enumerate(references, 1)
        ) or "(aucun extrait trouvé dans la base — le signaler à la validation humaine)"
        sources = [
            {
                "texte_source": r["texte_source"],
                "pays": r["pays"],
                "date_version": r["date_version"],
                "fichier": r["fichier"],
                "chunk_index": r["chunk_index"],
                "score": round(r["score"], 4),
            }
            for r in references
        ]

        consigne = document.consigne_redaction or document.nom
        # La liste des pièces vient du moteur de règles, jamais du LLM
        liste_pieces = (
            "Pièces composant le dossier (liste fixée par le moteur de règles — ne rien ajouter ni retirer) :\n"
            + "\n".join(f"  {i}. {nom}" for i, nom in enumerate(pieces_du_dossier, 1))
            + "\n"
        ) if pieces_du_dossier else ""
        prompt = f"""Tu es un assistant spécialisé en constitution de dossiers réglementaires pour dispositifs médicaux au Maroc.

DOCUMENT À RÉDIGER : {document.nom}
Ce que ce document doit contenir : {consigne}

Informations connues sur le dossier (à reprendre telles quelles) :
- Dispositif médical : {produit}
- Classe du dispositif (classification marocaine) : {classe or "[À COMPLÉTER]"}
- Fabricant / fournisseur : {fournisseur or "[À COMPLÉTER]"}
- Pays d'origine du fournisseur : {pays_origine}
- Pays de destination du dossier : {pays_destination}
{liste_pieces}
Extraits de textes réglementaires officiels, fournis UNIQUEMENT comme référence (pour les exigences et le vocabulaire) :
{contexte}

Consignes strictes :
- Rédige le document demandé lui-même, prêt à être complété et signé. Ne recopie PAS les extraits, ne reproduis pas d'en-têtes du Bulletin officiel, ne cite pas les extraits dans le document.
- N'invente aucune information factuelle (nom, adresse, numéro, date, référence) : écris [À COMPLÉTER] à la place.
- N'aborde que ce document, sans parler d'autres procédures (publicité, inspection, sanctions…).
- Si le document énumère les pièces du dossier, reprends EXACTEMENT la liste fixée ci-dessus, sans en ajouter ni en retirer.
- Rédige en français, dans le registre administratif marocain (formule d'appel « Monsieur le Ministre, », formule de politesse administrative, aucune formule familière), sans commentaire avant ou après le document."""

        try:
            # Une erreur 500 passagère d'Ollama (génération interrompue) est
            # relancée une fois ; à la seconde, la pièce passe en erreur.
            for tentative in (1, 2):
                reponse = self._session_ollama.post(
                    OLLAMA_URL,
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"num_predict": OLLAMA_NUM_PREDICT},
                    },
                    timeout=OLLAMA_TIMEOUT,
                )
                if reponse.status_code < 500 or tentative == 2:
                    break
                time.sleep(5)
            if reponse.status_code >= 500:
                raise GenerationImpossible(
                    f"Mistral a échoué deux fois (erreur {reponse.status_code} d'Ollama) — "
                    "voir `journalctl -u ollama`, puis relancer la rédaction."
                )
            reponse.raise_for_status()
            return reponse.json()["response"], sources
        except requests.exceptions.ConnectionError as e:
            raise GenerationImpossible(
                f"Ollama n'est pas démarré sur {OLLAMA_URL} — lancer `ollama serve` puis `ollama pull {OLLAMA_MODEL}`."
            ) from e
        except requests.exceptions.Timeout as e:
            raise GenerationImpossible(
                f"Mistral n'a pas répondu en {OLLAMA_TIMEOUT}s — augmenter OLLAMA_TIMEOUT ou utiliser un GPU."
            ) from e

    def creer_fichier_docx(
        self,
        titre: str,
        contenu: str,
        chemin_sortie: Path,
        document: DocumentRequis | None = None,
        sources: list[dict] | None = None,
    ) -> Path:
        doc = Document()
        doc.add_heading(titre, level=1)
        doc.add_paragraph().add_run(MENTION_VALIDATION).bold = True
        if document is not None:
            if document.traduction_requise:
                doc.add_paragraph("⚠ Traduction assermentée requise pour la pièce justificative.")
            if document.legalisation_requise:
                doc.add_paragraph("⚠ Légalisation / apostille requise pour la pièce justificative.")
        for paragraphe in contenu.split("\n"):
            if paragraphe.strip():
                doc.add_paragraph(paragraphe)
        if sources:
            doc.add_heading("Sources réglementaires utilisées (à vérifier)", level=2)
            for s in sources:
                doc.add_paragraph(
                    f"{s['texte_source']} — version du {s['date_version']} "
                    f"({s['fichier']}, extrait n°{s['chunk_index']})",
                    style="List Bullet",
                )
        chemin_sortie.parent.mkdir(parents=True, exist_ok=True)
        doc.save(chemin_sortie)
        return chemin_sortie


def nouveau_dossier_sortie(pays_origine: str, produit: str) -> Path:
    """Un dossier de sortie par dossier : deux dossiers ne s'écrasent jamais."""
    horodatage = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return OUTPUT_DIR / f"{horodatage}_{pays_origine}_{_slug(produit)}"


def generer_document(
    generateur: GenerateurDocuments,
    doc: DocumentRequis,
    produit: str,
    pays_origine: str,
    dossier_sortie: Path,
    classe: str | None = None,
    fournisseur: str | None = None,
    pieces_du_dossier: list[str] | None = None,
) -> dict:
    """Rédige UN document à rédiger (RAG + Mistral) et l'enregistre en DOCX.
    Lève GenerationImpossible pour une pièce à fournir ou si Mistral échoue."""
    contenu, sources = generateur.generer_contenu(
        doc, pays_destination="maroc", produit=produit, pays_origine=pays_origine,
        classe=classe, fournisseur=fournisseur, pieces_du_dossier=pieces_du_dossier,
    )
    chemin = generateur.creer_fichier_docx(
        doc.nom, contenu, dossier_sortie / f"{doc.id}.docx".replace(" ", "_"), document=doc, sources=sources
    )
    return {"fichier": str(chemin), "sources": sources}


def traiter_dossier(pays_origine: str, produit: str, classe: str | None = None) -> dict:
    """
    Fonction principale : orchestre rule_engine (décision) + RAG + Mistral
    (rédaction) + mise en forme DOCX. Retourne un résumé du dossier généré,
    prêt pour la validation humaine — jamais pour un dépôt automatique.

    Seules les pièces `a_rediger` sont rédigées ; les pièces `a_fournir`
    sont listées comme à obtenir auprès de leur émetteur.
    """
    documents = documents_requis_maroc(pays_origine, classe=classe)
    generateur = GenerateurDocuments()
    dossier_sortie = nouveau_dossier_sortie(pays_origine, produit)

    resultats = []
    for doc in documents:
        entree = {
            "id": doc.id,
            "document": doc.nom,
            "nature": doc.nature,
            "fourni_par": doc.fourni_par,
            "traduction_requise": doc.traduction_requise,
            "legalisation_requise": doc.legalisation_requise,
            "origine_regle": doc.origine_regle,
            "fichier": None,
            "sources": [],
            "erreur": None,
        }
        if doc.a_rediger:
            try:
                entree.update(generer_document(
                    generateur, doc, produit, pays_origine, dossier_sortie,
                    classe=classe, pieces_du_dossier=[d.nom for d in documents],
                ))
            except GenerationImpossible as e:
                entree["erreur"] = str(e)
        resultats.append(entree)

    return {
        "produit": produit,
        "pays_origine": pays_origine,
        "pays_destination": "maroc",
        "classe": classe,
        "dossier_sortie": str(dossier_sortie),
        "nombre_documents": len(resultats),
        "documents": resultats,
        "prochain_creneau_depot": str(prochain_creneau_depot()),
        "statut": "EN ATTENTE DE VALIDATION HUMAINE — aucun dépôt automatique",
    }


def _slug(texte: str) -> str:
    """'Prothèse orthopédique de hanche' -> 'prothese-orthopedique-de-hanche'"""
    ascii_ = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")[:60] or "dossier"


def main():
    parser = argparse.ArgumentParser(description="Génère un dossier de conformité complet")
    parser.add_argument("--pays-origine", required=True, choices=["chine", "inde", "union_europeenne", "autre"])
    parser.add_argument("--produit", required=True)
    parser.add_argument("--classe", default=None, choices=["I", "IIA", "IIB", "III"])
    args = parser.parse_args()

    resultat = traiter_dossier(args.pays_origine, args.produit, args.classe)

    print(f"\nDossier généré : {resultat['produit']} (origine : {resultat['pays_origine']})")
    print(f"Nombre de documents : {resultat['nombre_documents']}")
    for d in resultat["documents"]:
        flags = []
        if d["traduction_requise"]:
            flags.append("traduction requise")
        if d["legalisation_requise"]:
            flags.append("légalisation requise")
        suffix = f" [{', '.join(flags)}]" if flags else ""
        if d["nature"] == "a_fournir":
            cible = f"à obtenir auprès de {d['fourni_par']}"
        elif d["erreur"]:
            cible = f"ÉCHEC : {d['erreur']}"
        else:
            cible = d["fichier"]
        print(f"  - {d['document']}{suffix}\n    -> {cible}")
    print(f"\nProchain créneau de dépôt : {resultat['prochain_creneau_depot']}")
    print(f"Statut : {resultat['statut']}")


if __name__ == "__main__":
    main()
