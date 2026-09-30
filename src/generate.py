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


class GenerateurDocuments:
    def __init__(self, host: str = "localhost", port: int = 6333):
        self.client = QdrantClient(host=host, port=port)
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
        references = self.rechercher_references(pays_destination, document.nom, k=3)
        if document.origine_regle.startswith("piece_specifique") and pays_origine in PAYS_INDEXES:
            references += self.rechercher_references(pays_origine, document.nom, k=2)
        return references

    def generer_contenu(self, document: DocumentRequis, pays_destination: str, produit: str, pays_origine: str) -> tuple[str, list[dict]]:
        """Appelle Mistral (via Ollama) pour rédiger le contenu d'un document,
        en s'appuyant sur les extraits réglementaires retrouvés par RAG.
        Retourne (contenu, références utilisées) — les références sont
        remontées à la validation humaine pour vérification."""
        references = self.references_pour_document(document, pays_destination, pays_origine)
        contexte = "\n---\n".join(
            f"[Source: {r['texte_source']} (version du {r['date_version']})]\n{r['texte'][:800]}"
            for r in references
        ) or "(aucune référence trouvée dans la base — signaler ce point à la validation humaine)"
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

        prompt = f"""Tu es un assistant spécialisé en constitution de dossiers réglementaires pour dispositifs médicaux au Maroc.

Voici des extraits de textes réglementaires officiels, à utiliser comme référence :
{contexte}

Génère maintenant le contenu du document suivant :
- Type de document : {document.nom}
- Dispositif médical : {produit}
- Pays d'origine du fournisseur : {pays_origine}
- Pays de destination du dossier : {pays_destination}

Consignes strictes :
- Respecte exactement la structure attendue par la réglementation citée dans les extraits.
- N'invente aucune information factuelle qui ne serait pas cohérente avec les extraits fournis.
- Si une information manque (numéro de certificat, date, etc.), indique clairement [À COMPLÉTER] plutôt que d'inventer une valeur.
- Rédige en français, dans un style administratif sobre."""

        try:
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
            reponse.raise_for_status()
            return reponse.json()["response"], sources
        except requests.exceptions.ConnectionError:
            return (
                "[GÉNÉRATION INDISPONIBLE — Ollama n'est pas démarré sur "
                f"{OLLAMA_URL}. Lancer `ollama serve` puis `ollama pull mistral`.]\n\n"
                f"Contexte qui aurait été utilisé :\n{contexte}"
            ), sources
        except requests.exceptions.Timeout:
            return (
                f"[GÉNÉRATION INTERROMPUE — Mistral n'a pas répondu en {OLLAMA_TIMEOUT}s. "
                "Augmenter OLLAMA_TIMEOUT ou utiliser une machine avec GPU.]\n\n"
                f"Contexte qui aurait été utilisé :\n{contexte}"
            ), sources

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


def traiter_dossier(pays_origine: str, produit: str, classe: str | None = None) -> dict:
    """
    Fonction principale : orchestre rule_engine (décision) + RAG + Mistral
    (rédaction) + mise en forme DOCX. Retourne un résumé du dossier généré,
    prêt pour la validation humaine — jamais pour un dépôt automatique.
    """
    documents = documents_requis_maroc(pays_origine, classe=classe)
    generateur = GenerateurDocuments()

    # Un dossier de sortie par génération : deux dossiers ne s'écrasent jamais
    horodatage = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dossier_sortie = OUTPUT_DIR / f"{horodatage}_{pays_origine}_{_slug(produit)}"

    fichiers = []
    for doc in documents:
        contenu, sources = generateur.generer_contenu(doc, pays_destination="maroc", produit=produit, pays_origine=pays_origine)
        nom_fichier = f"{doc.id}.docx".replace(" ", "_")
        chemin = generateur.creer_fichier_docx(doc.nom, contenu, dossier_sortie / nom_fichier, document=doc, sources=sources)
        fichiers.append({
            "id": doc.id,
            "document": doc.nom,
            "fichier": str(chemin),
            "traduction_requise": doc.traduction_requise,
            "legalisation_requise": doc.legalisation_requise,
            "origine_regle": doc.origine_regle,
            "sources": sources,
        })

    return {
        "produit": produit,
        "pays_origine": pays_origine,
        "pays_destination": "maroc",
        "classe": classe,
        "dossier_sortie": str(dossier_sortie),
        "nombre_documents": len(fichiers),
        "documents": fichiers,
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
        print(f"  - {d['document']}{suffix}\n    -> {d['fichier']}")
    print(f"\nProchain créneau de dépôt : {resultat['prochain_creneau_depot']}")
    print(f"Statut : {resultat['statut']}")


if __name__ == "__main__":
    main()
