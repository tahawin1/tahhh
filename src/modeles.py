"""
Modèles de rédaction tirés des dossiers réellement acceptés par l'administration.

Chaque pièce « à rédiger » d'un dossier accepté (lettre de demande, fiche
signalétique, certificat de l'annexe II…) devient le modèle de la même pièce
pour les dossiers suivants : Mistral reprend sa structure, son destinataire,
ses formules et l'en-tête de l'entreprise, et n'y remplace que les données du
nouveau dispositif.

Les dossiers acceptés restent sur le serveur, jamais sur GitHub :

    data/dossiers_valides/<pays_origine>/<produit>/**/<numéro>-<nom>.pdf
    ex. data/dossiers_valides/union_europeenne/Ciment osseux/MODULES/1/1-1-Lettre de Demande.pdf

Le numéro en tête du nom de fichier est celui de la pièce dans le dossier
déposé ; il est rapproché de la pièce par le champ `numero` des règles
(rules/maroc.yaml) — c'est le code, pas l'IA, qui décide quel fichier est
le modèle de quelle pièce.

    python src/modeles.py                      # indexe data/dossiers_valides
    python src/modeles.py --racine AUTRE/DOSSIER
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import os
import re
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from embeddings import Embedder
from memoire import produit_et_classe
from rule_engine import charger_regles

COLLECTION_MODELES = "modeles_dossiers"
RACINE_DEFAUT = Path(__file__).resolve().parent.parent / "data" / "dossiers_valides"
TEXTE_MAX = 7000  # caractères gardés par modèle (contexte de Mistral limité)
NUMERO_FICHIER = re.compile(r"^\s*(\d{1,2})\s*[-_. ]")


def pieces_a_rediger_par_numero() -> dict[int, str]:
    """{numéro dans le dossier : id de la pièce}, pour les pièces à rédiger,
    d'après les règles (jamais d'après le contenu du fichier)."""
    regles = charger_regles("maroc")
    return {d["numero"]: d["id"] for d in regles["socle_commun"]
             if d.get("nature") == "a_rediger" and d.get("numero") is not None}


def _client(host: str | None = None, port: int | None = None) -> QdrantClient:
    return QdrantClient(host=host or os.environ.get("QDRANT_HOST", "localhost"),
                        port=port or int(os.environ.get("QDRANT_PORT", "6333")))


def fichiers_modeles(racine: Path) -> list[dict]:
    """Repère, sans rien lire, les fichiers qui serviront de modèles."""
    trouves = []
    for pays_dir in sorted(p for p in racine.iterdir() if p.is_dir()):
        table = pieces_a_rediger_par_numero()
        for produit_dir in sorted(p for p in pays_dir.iterdir() if p.is_dir()):
            for fichier in sorted(produit_dir.rglob("*.pdf")):
                m = NUMERO_FICHIER.match(fichier.name)
                if not m or int(m.group(1)) not in table:
                    continue
                produit, classe = produit_et_classe(produit_dir.name)
                trouves.append({
                    "fichier": fichier,
                    "pays_origine": pays_dir.name,
                    "produit": produit,
                    "classe": classe,
                    "numero": int(m.group(1)),
                    "piece_id": table[int(m.group(1))],
                })
    return trouves


def indexer(racine: Path = RACINE_DEFAUT, client: QdrantClient | None = None, embedder: Embedder | None = None) -> list[dict]:
    """Lit chaque modèle (texte ou OCR) et l'enregistre dans Qdrant. Relançable :
    un fichier déjà indexé est remplacé (identifiant stable)."""
    from extraction import lire_document

    client = client or _client()
    embedder = embedder or Embedder()
    trouves = fichiers_modeles(racine)
    if not trouves:
        return []
    points = []
    for m in trouves:
        try:
            texte = lire_document(m["fichier"]).strip()
        except Exception as e:  # un fichier illisible ne bloque pas les autres
            print(f"  ✗ {m['fichier'].name} : lecture impossible ({type(e).__name__}: {e}), ignoré")
            continue
        if not texte:
            print(f"  ! {m['fichier'].name} : aucun texte lisible, ignoré")
            continue
        relatif = str(m["fichier"].relative_to(racine))
        points.append(PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"modele:{relatif}")),
            vector=embedder.encoder_un(f"{m['produit']} — {texte[:1500]}"),
            payload={
                "piece_id": m["piece_id"],
                "numero": m["numero"],
                "pays_origine": m["pays_origine"],
                "produit": m["produit"],
                "classe": m["classe"],
                "fichier": relatif,
                "empreinte": hashlib.sha256(m["fichier"].read_bytes()).hexdigest()[:12],
                "texte": texte[:TEXTE_MAX],
                "indexe_le": datetime.date.today().isoformat(),
            },
        ))
        print(f"  ✓ pièce {m['numero']} ({m['piece_id']}) — {m['produit']} — {len(texte)} caractères")
    if not points:
        return []
    if not client.collection_exists(COLLECTION_MODELES):
        client.create_collection(COLLECTION_MODELES, vectors_config=VectorParams(size=len(points[0].vector), distance=Distance.COSINE))
    client.upsert(COLLECTION_MODELES, points=points)
    return [p.payload for p in points]


def modele_pour(piece_id: str, pays_origine: str, produit: str,
                client: QdrantClient, embedder: Embedder, classe: str | None = None) -> dict | None:
    """Le modèle accepté le plus proche pour cette pièce : même pièce
    obligatoirement ; de préférence même pays d'origine ET même classe, puis
    même pays, puis même classe ; produit le plus ressemblant. None s'il n'y
    en a pas (la rédaction se fait alors sans modèle)."""
    try:
        if not client.collection_exists(COLLECTION_MODELES):
            return None
    except Exception:
        return None
    vecteur = embedder.encoder_un(produit)
    piece = FieldCondition(key="piece_id", match=MatchValue(value=piece_id))
    pays = FieldCondition(key="pays_origine", match=MatchValue(value=pays_origine))
    essais = [[piece, pays], [piece]]
    if classe:
        meme_classe = FieldCondition(key="classe", match=MatchValue(value=str(classe).upper()))
        essais = [[piece, pays, meme_classe], [piece, pays], [piece, meme_classe], [piece]]
    for filtres in essais:
        points = client.query_points(COLLECTION_MODELES, query=vecteur, query_filter=Filter(must=filtres),
                                     limit=1, with_payload=True).points
        if points:
            return {**points[0].payload, "score": points[0].score}
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Indexe les dossiers acceptés comme modèles de rédaction.")
    parser.add_argument("--racine", type=Path, default=RACINE_DEFAUT)
    args = parser.parse_args()
    if not args.racine.is_dir():
        raise SystemExit(f"Dossier introuvable : {args.racine}")
    print(f"Modèles cherchés dans {args.racine}")
    resultat = indexer(args.racine)
    print(f"{len(resultat)} modèle(s) indexé(s) dans la collection « {COLLECTION_MODELES} ».")
